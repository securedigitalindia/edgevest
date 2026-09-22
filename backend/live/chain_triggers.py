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
import os
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from config import CHAIN_TRIGGERS, UPSTOX_INSTRUMENT_KEYS
from db import queries
from live import fo_instruments
from live.upstox_client import get_ltp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))
from nifty_pe_ratio_diagonal_simulator import resolve_expiry_triplet  # noqa: E402
from nifty_pe_ratio_diagonal_averaging_backtest import SIDE_CONFIG as _RATIO_SIDE_CONFIG  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
_MAX_SNAPSHOT_AGE = timedelta(minutes=10)   # don't evaluate against a stale chain (capture failed)
_SIDE_ROUND = {"CE": math.ceil, "PE": math.floor}
_failure_alerted: set = set()   # (trigger, side, ist_date) whose draft-failure alert already went out — retries stay silent
_fmt_expiry = lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%d %b %Y")


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
        net_label = f"credit {credit:g}" if credit >= 0 else f"debit {-credit:g}"
        rule_label = f"credit > {cfg['min_credit_pts']:g}" if "min_credit_pts" in cfg else f"debit < {cfg['max_debit_pts']:g}"
        # Always logged, fire or not — otherwise there's no visibility into how close a
        # trigger is on a 5-min cycle that doesn't fire (only a fire used to print anything).
        print(f"  [chain_triggers] {cfg['name']} {side}: K={int(strike)}/{int(far_strike)} fut={fut_ltp:.1f} "
              f"near={near_ltp} far={far_ltp} -> {net_label}  ({rule_label}: "
              f"{'MET' if credit > threshold else 'not met'})", flush=True)
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
        note = f"{cfg['near_lots']}:{cfg['far_lots']} {kind} {side} {strikes_txt} (auto · {net_label})"
        snap_ist = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(IST).strftime("%d %b %H:%M IST")
        alert_args = dict(trigger_name=cfg["name"], side=side, rule=rule_label, note=note, legs=legs, credit=credit,
                          fut_ltp=fut_ltp, snapshot_ts_ist=snap_ist)
        try:
            trade_id = add_manual_trade(symbol, legs, note=note, risk_level=cfg.get("risk_level"), status="draft")
            queries.set_chain_trigger_fire_trade(fire_id, trade_id)
            print(f"  [chain_triggers] {cfg['name']} FIRED {side} K={int(strike)}/{int(far_strike)} fut={fut_ltp:.1f} "
                  f"near={near}@{near_ltp} far={far}@{far_ltp} credit={credit} -> draft trade {trade_id}", flush=True)
            try:
                draft_code = (queries.get_recommendation(trade_id) or {}).get("display_code")
            except Exception:
                draft_code = None   # the draft exists either way — never let a lookup failure report it as missing
            _send_alert(draft_code=draft_code, **alert_args)
        except Exception as e:
            queries.release_chain_trigger_fire(fire_id)   # let the next snapshot retry
            print(f"  [chain_triggers] {cfg['name']} {side}: draft creation failed — {e}", flush=True)
            key = (cfg["name"], side, today.isoformat())
            if key not in _failure_alerted:   # one failure alert per trigger/side/day, not one per 5-min retry
                _failure_alerted.add(key)
                _send_alert(draft_error=str(e), **alert_args)


def _evaluate_pe_ratio_diagonal_credit(cfg: dict) -> None:
    """
    4-leg 1:2:1:2 ratio diagonal — the same shape as the already-backtested strategy
    (docs/prd/pe-ratio-diagonal-strategy.md, analysis/nifty_pe_ratio_diagonal_*):
        BUY  l1_lots @ K   expiry1 (nearest, DTE > min_dte)
        SELL l2_lots @ K2  expiry2 (next after expiry1)
        SELL l3_lots @ K   expiry2
        BUY  l4_lots @ K2  expiry3 (next after expiry2)
    K = base strike next to the futures price (PE floors, CE ceils); K2 = K -/+ leg_gap
    (same signed convention as the calendar family). value = l1_lots*l1 - l2_lots*l2 -
    l3_lots*l3 + l4_lots*l4 (points); credit = -value. Fires when credit > min_credit_pts —
    on real data this combo prices as a DEBIT under normal conditions (verified 2026-09-22:
    -19.25 on the reference snapshot with default lots/gap), so the condition is expected to
    rarely fire, not a bug.
    """
    from live.manual_trade import add_manual_trade

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
    try:
        expiry1, expiry2, expiry3 = resolve_expiry_triplet(today.isoformat(), merged)
    except ValueError as e:
        print(f"  [chain_triggers] {cfg['name']}: {e} — skipped", flush=True)
        return

    front = fo_instruments.nifty_front_fut(today)
    if front is None:
        print(f"  [chain_triggers] {cfg['name']}: no front-month NIFTY future found — skipped", flush=True)
        return
    fut_ltp = get_ltp([front[0]]).get(front[0])
    if not fut_ltp:
        return

    for side in cfg["sides"]:
        side_cfg = _RATIO_SIDE_CONFIG[side]
        k = side_cfg["strike_fn"](fut_ltp + side_cfg["gap_sign"] * cfg.get("initial_gap", 0), cfg["strike_step"])
        k2 = k + side_cfg["gap_sign"] * cfg["leg_gap"]
        l1 = queries.get_chain_ltp(ts, symbol, expiry1, k, side)
        l2 = queries.get_chain_ltp(ts, symbol, expiry2, k2, side)
        l3 = queries.get_chain_ltp(ts, symbol, expiry2, k, side)
        l4 = queries.get_chain_ltp(ts, symbol, expiry3, k2, side)
        if None in (l1, l2, l3, l4):
            continue

        l1_lots, l2_lots, l3_lots, l4_lots = cfg["l1_lots"], cfg["l2_lots"], cfg["l3_lots"], cfg["l4_lots"]
        value = round(l1_lots * l1 - l2_lots * l2 - l3_lots * l3 + l4_lots * l4, 2)
        credit = -value
        net_label = f"credit {credit:g}" if credit >= 0 else f"debit {-credit:g}"
        # Always logged, fire or not — same reasoning as the calendar_ratio_credit evaluator.
        print(f"  [chain_triggers] {cfg['name']} {side}: K={int(k)}/{int(k2)} fut={fut_ltp:.1f} "
              f"l1={l1} l2={l2} l3={l3} l4={l4} -> {net_label}  (credit > {cfg['min_credit_pts']:g}: "
              f"{'MET' if credit > cfg['min_credit_pts'] else 'not met'})", flush=True)
        if credit <= cfg["min_credit_pts"]:
            continue

        fire_id = queries.claim_chain_trigger_fire(cfg["name"], side, today.isoformat(), credit)
        if fire_id is None:
            continue   # already fired for this side today

        legs = [
            {"side": "BUY",  "type": side, "strike": int(k),  "expiry": _fmt_expiry(expiry1), "lots": l1_lots, "price": l1},
            {"side": "SELL", "type": side, "strike": int(k2), "expiry": _fmt_expiry(expiry2), "lots": l2_lots, "price": l2},
            {"side": "SELL", "type": side, "strike": int(k),  "expiry": _fmt_expiry(expiry2), "lots": l3_lots, "price": l3},
            {"side": "BUY",  "type": side, "strike": int(k2), "expiry": _fmt_expiry(expiry3), "lots": l4_lots, "price": l4},
        ]
        note = f"{l1_lots}:{l2_lots}:{l3_lots}:{l4_lots} RATIO DIAG {side} {int(k)}/{int(k2)} (auto · {net_label})"
        snap_ist = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(IST).strftime("%d %b %H:%M IST")
        alert_args = dict(trigger_name=cfg["name"], side=side, rule=f"credit > {cfg['min_credit_pts']:g}",
                          note=note, legs=legs, credit=credit, fut_ltp=fut_ltp, snapshot_ts_ist=snap_ist)
        try:
            trade_id = add_manual_trade(symbol, legs, note=note, risk_level=cfg.get("risk_level"), status="draft")
            queries.set_chain_trigger_fire_trade(fire_id, trade_id)
            print(f"  [chain_triggers] {cfg['name']} FIRED {side} K={int(k)}/{int(k2)} fut={fut_ltp:.1f} "
                  f"l1={l1} l2={l2} l3={l3} l4={l4} credit={credit} -> draft trade {trade_id}", flush=True)
            try:
                draft_code = (queries.get_recommendation(trade_id) or {}).get("display_code")
            except Exception:
                draft_code = None
            _send_alert(draft_code=draft_code, **alert_args)
        except Exception as e:
            queries.release_chain_trigger_fire(fire_id)
            print(f"  [chain_triggers] {cfg['name']} {side}: draft creation failed — {e}", flush=True)
            key = (cfg["name"], side, today.isoformat())
            if key not in _failure_alerted:
                _failure_alerted.add(key)
                _send_alert(draft_error=str(e), **alert_args)


_EVALUATORS = {
    "calendar_ratio_credit": _evaluate_calendar_ratio_credit,
    "pe_ratio_diagonal_credit": _evaluate_pe_ratio_diagonal_credit,
}


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
