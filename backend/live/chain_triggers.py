# ============================================================
#  Drishti — live/chain_triggers.py
#  Option-chain triggers: evaluated once per 5-min option_chain_5m
#  snapshot (called by live/poller.py right after run_capture()), and
#  on fire create a DRAFT trade — never an open one, no alert, no margin
#  until an admin publishes it (see add_manual_trade(status="draft")).
#
#  Config: config.CHAIN_TRIGGERS. One type today, "calendar_ratio_credit":
#    base     = next strike_step above (CE) / below (PE) the front-month
#               NIFTY future's live price
#    K1       = base moved itm_points into the money (default 0 = base itself)
#    K2       = K1 moved far_strike_offset out of the money (default 0 = same
#               strike, a pure calendar)
#    near     = nearest expiry with DTE > min_dte; far = the next one after it
#    trade    = BUY near_lots @ K1 near  +  SELL far_lots @ K2 far
#    credit   = far_lots * far_ltp - near_lots * near_ltp   (premium points;
#               negative = a net debit)
#    fires    = credit > min_credit_pts, once per trigger per side per IST day; each fire
#               sends a Telegram alert stating whether a draft trade is linked or not.
#               Or, for a debit rule, max_debit_pts = N: fires when near*near_lots -
#               far*far_lots < N (same as credit > -N; a net credit also qualifies).
# ============================================================
import math
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from config import CHAIN_TRIGGERS, UPSTOX_INSTRUMENT_KEYS
from db import queries
from live import fo_instruments
from live.upstox_client import get_ltp

IST = ZoneInfo("Asia/Kolkata")
_MAX_SNAPSHOT_AGE = timedelta(minutes=10)   # don't evaluate against a stale chain (capture failed)
_SIDE_ROUND = {"CE": math.ceil, "PE": math.floor}
_failure_alerted: set = set()   # (trigger, side, ist_date) whose draft-failure alert already went out — retries stay silent


def _send_alert(**kwargs) -> None:
    """Telegram alert for a fired trigger — never allowed to break the trigger loop or the draft that was already made."""
    try:
        from live.alert import send_chain_trigger_alert
        send_chain_trigger_alert(**kwargs)
    except Exception as e:
        print(f"  [chain_triggers] Telegram alert failed — {e}", flush=True)


def _evaluate_calendar_ratio_credit(cfg: dict) -> None:
    from live.manual_trade import add_manual_trade  # late import — manual_trade pulls in the whole trade stack

    symbol = cfg["symbol"]
    today = datetime.now(IST).date()

    ts = queries.get_option_chain_max_ts()
    if not ts:
        return
    age = datetime.now(timezone.utc) - datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if age > _MAX_SNAPSHOT_AGE:
        print(f"  [chain_triggers] {cfg['name']}: latest chain snapshot {ts} is stale — skipped", flush=True)
        return

    merged = queries.get_merged_cadence_dates(symbol, include_quarterly=True)
    upcoming = [e for e in merged if (datetime.strptime(e, "%Y-%m-%d").date() - today).days > cfg["min_dte"]]
    if len(upcoming) < 2:
        return
    near, far = upcoming[0], upcoming[1]

    front = fo_instruments.nifty_front_fut(today)
    if front is None:
        print(f"  [chain_triggers] {cfg['name']}: no front-month NIFTY future found — skipped", flush=True)
        return
    fut_ltp = get_ltp([front[0]]).get(front[0])
    if not fut_ltp:
        return

    for side in cfg["sides"]:
        otm = 1 if side == "CE" else -1   # direction of "further out of the money" on the strike axis
        base = _SIDE_ROUND[side](fut_ltp / cfg["strike_step"]) * cfg["strike_step"]
        strike = base - otm * cfg.get("itm_points", 0)          # K1 — near BUY leg
        far_strike = strike + otm * cfg.get("far_strike_offset", 0)  # K2 — far SELL leg
        near_ltp = queries.get_chain_ltp(ts, symbol, near, strike, side)
        far_ltp = queries.get_chain_ltp(ts, symbol, far, far_strike, side)
        if near_ltp is None or far_ltp is None:
            continue
        credit = round(cfg["far_lots"] * far_ltp - cfg["near_lots"] * near_ltp, 2)
        # Threshold: either min_credit_pts (fire when credit > N) or max_debit_pts (fire when
        # near_lots*near_ltp - far_lots*far_ltp < N, i.e. credit > -N — a net credit also qualifies).
        threshold = cfg["min_credit_pts"] if "min_credit_pts" in cfg else -cfg["max_debit_pts"]
        if credit <= threshold:
            continue

        fire_id = queries.claim_chain_trigger_fire(cfg["name"], side, today.isoformat(), credit)
        if fire_id is None:
            continue   # already fired for this side today
        fmt = lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%d %b %Y")
        legs = [
            {"side": "BUY",  "type": side, "strike": int(strike),     "expiry": fmt(near), "lots": cfg["near_lots"], "price": near_ltp},
            {"side": "SELL", "type": side, "strike": int(far_strike), "expiry": fmt(far),  "lots": cfg["far_lots"],  "price": far_ltp},
        ]
        strikes_txt = f"{int(strike)}" if far_strike == strike else f"{int(strike)}/{int(far_strike)}"
        kind = "CAL" if far_strike == strike else "DIAG"
        net_txt = f"credit {credit:g}" if credit >= 0 else f"debit {-credit:g}"
        note = f"{cfg['near_lots']}:{cfg['far_lots']} {kind} {side} {strikes_txt} (auto · {net_txt})"
        rule = f"credit > {cfg['min_credit_pts']:g}" if "min_credit_pts" in cfg else f"debit < {cfg['max_debit_pts']:g}"
        snap_ist = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(IST).strftime("%d %b %H:%M IST")
        alert_args = dict(trigger_name=cfg["name"], side=side, rule=rule, note=note, legs=legs, credit=credit,
                          fut_ltp=fut_ltp, snapshot_ts_ist=snap_ist)
        try:
            trade_id = add_manual_trade(symbol, legs, note=note, risk_level=cfg.get("risk_level"), status="draft")
            queries.set_chain_trigger_fire_trade(fire_id, trade_id)
            print(f"  [chain_triggers] {cfg['name']} FIRED {side} K={int(strike)}/{int(far_strike)} fut={fut_ltp:.1f} "
                  f"near={near}@{near_ltp} far={far}@{far_ltp} credit={credit} -> draft trade {trade_id}", flush=True)
            _send_alert(draft_code=(queries.get_recommendation(trade_id) or {}).get("display_code"), **alert_args)
        except Exception as e:
            queries.release_chain_trigger_fire(fire_id)   # let the next snapshot retry
            print(f"  [chain_triggers] {cfg['name']} {side}: draft creation failed — {e}", flush=True)
            key = (cfg["name"], side, today.isoformat())
            if key not in _failure_alerted:   # one failure alert per trigger/side/day, not one per 5-min retry
                _failure_alerted.add(key)
                _send_alert(draft_error=str(e), **alert_args)


_EVALUATORS = {"calendar_ratio_credit": _evaluate_calendar_ratio_credit}


def run_chain_triggers() -> None:
    """Evaluate every configured option-chain trigger. Callers wrap this in try/except (never crash the poll loop)."""
    for cfg in CHAIN_TRIGGERS:
        fn = _EVALUATORS.get(cfg["type"])
        if fn is None:
            print(f"  [chain_triggers] unknown type {cfg['type']!r} for {cfg.get('name')} — skipped", flush=True)
            continue
        try:
            fn(cfg)
        except Exception as e:
            print(f"  [chain_triggers] {cfg.get('name')} failed — {e}", flush=True)
