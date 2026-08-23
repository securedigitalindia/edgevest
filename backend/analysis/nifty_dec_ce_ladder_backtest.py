"""
NIFTY Dec-2026 CE ladder backtest — base ladder + 1000pt adjustment overlay.

Strategy (as specified across a series of conversational refinements):

BASE LADDER
    Hourly NIFTY spot triggers a new entry under one of two regimes,
    depending on where spot sits relative to the *last base entry's* spot:

      - At or below the last entry's spot: fire when spot falls
        --base-pullback-pct below it (chained) — the original rule.
      - Above the last entry's spot (i.e. market has rallied since):
        track the highest close in the trailing --weekly-window-days
        calendar days (this rolling-high window resets to empty at every
        new entry, so it only ever looks at the peak reached *since* the
        last entry); fire when spot is --weekly-pullback-pct below that
        peak. This catches corrections during an uptrend that never fall
        back near the last entry's absolute level.

    Either way: strikeA = nearest 1000-multiple strike that is >=800pts
    OTM from spot; strikeB = strikeA + 1000. BUY 1 lot strikeA / SELL 1
    lot strikeB — identical leg structure regardless of which rule fired.
    Both are then snapped UP to the nearest strike actually listed for the
    chosen expiry (see snap_to_listed) — nearer monthlies thin out their
    strike spacing well before a far-dated/quarterly expiry like Dec would,
    so the ideal round-1000 strike isn't always tradable.

ADJUSTMENT OVERLAY (layered on top, base positions untouched)
    Each base entry independently watches hourly spot, from its own entry
    point, for every --adj-step-points fall *from that base entry's own
    entry spot* (chained: -1000, -2000, ... below that base entry's spot).
    Each crossing: BUY 1 lot at a freshly-computed strike (same OTM rule,
    off the spot at that moment) / SELL --adj-sell-lots lots at
    (BUY strike + --adj-strike-gap).

EXIT RULE (optional, --exit-pct / --exit-direction)
    Each base entry watches hourly spot, from its own entry point onward,
    for the first bar where spot has moved --exit-pct in --exit-direction
    (default "up" — e.g. 0.04 = a 4% rally off that base entry's own entry
    spot; "down" or "both" are also available). On that bar: the base pair
    AND every adjustment pair already opened under that base entry are
    exited together, marked at that day's daily CLOSE (not the triggering
    bar's intraday price — same daily-close convention as entries). No
    further adjustments are generated for that base entry past its exit
    bar — the default "up" direction deliberately leaves the DOWNSIDE
    unguarded, since the adjustment overlay's whole job is to keep
    averaging in as spot keeps falling; a down-side exit would cut that
    mechanism off before it can work. A base entry with no qualifying
    move by --to-date is still open at the window's close, marked to the
    latest available premium as before. Without --exit-pct, nothing
    exits — everything is held to --to-date.

LIQUIDITY GUARD
    The day's first hourly candle (09:15-10:15, i.e. the candle starting
    at 09:15 IST) is excluded from triggering — thin early-session
    liquidity in the options can make that print unreliable. The first
    eligible candle each day is 10:15 onward. This applies to trigger
    detection only; option premiums always use that day's daily CLOSE
    (never the day's open), which was already the case before this flag
    existed.

Usage:
    python analysis/nifty_dec_ce_ladder_backtest.py
    python analysis/nifty_dec_ce_ladder_backtest.py --base-pullback-pct 0.005 --from-date 2026-01-01
    python analysis/nifty_dec_ce_ladder_backtest.py --export-json /tmp/artifact_data.json
"""
import argparse
import json
import os
import sys
from bisect import bisect_left
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from live.upstox_client import get_historical_candles, get_margin, get_brokerage
from config import UPSTOX_INSTRUMENT_KEYS

_INSTRUMENT_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def compute_strike_a(spot: float) -> int:
    """Nearest 1000-multiple strike that is at least 800 points OTM from spot."""
    x = int(spot) + 800
    return ((x // 1000) + (1 if x % 1000 else 0)) * 1000


def make_strike_snapper(strike_to_ikey: dict[int, str], from_date: date, to_date: date):
    """
    Round-1000 strikes assume a dense, fully-priced chain (true for far-dated/
    quarterly expiries like Dec). Nearer monthlies fall short two ways: (a) the
    strike spacing itself widens beyond ~ATM+2500 (NSE adds strikes in coarser
    steps once few traders are that far OTM) so the ideal strike sometimes
    isn't listed at all, and (b) even a listed strike may not have priced
    history back to the date it's needed — Upstox/NSE only backfills a strike's
    daily candles once spot gets close to it. Returns snap(strike, needed_by)
    that walks UP the listed chain (never down, so OTM-ness only increases)
    until it finds a strike that both exists and has a priced candle on or
    before `needed_by`; each strike's earliest-priced-date is fetched once
    and cached.
    """
    available_strikes = sorted(strike_to_ikey.keys())
    earliest_date_cache: dict[int, date | None] = {}

    def earliest_priced_date(strike: int) -> date | None:
        if strike not in earliest_date_cache:
            ikey = strike_to_ikey.get(strike)
            hist = fetch_daily(ikey, from_date, to_date) if ikey else {}
            earliest_date_cache[strike] = min(hist.keys()) if hist else None
        return earliest_date_cache[strike]

    def snap(strike: int, needed_by: date) -> int:
        idx = bisect_left(available_strikes, strike)
        for s in available_strikes[idx:]:
            d = earliest_priced_date(s)
            if d is not None and d <= needed_by:
                return s
        # nothing in range is priced that early — fall back to nearest listed
        # (premium lookup will simply have no data before its first candle)
        return available_strikes[idx] if idx < len(available_strikes) else available_strikes[-1]

    return snap


def _latest_instrument_master() -> str:
    candidates = [f for f in os.listdir(_INSTRUMENT_CACHE_DIR) if f.startswith("nse_instruments_")]
    if not candidates:
        raise RuntimeError(f"No cached nse_instruments_*.json in {_INSTRUMENT_CACHE_DIR} — "
                            f"run live/fo_instruments.refresh() first.")
    candidates.sort()
    return os.path.join(_INSTRUMENT_CACHE_DIR, candidates[-1])


def load_strike_to_ikey(expiry: date, option_type: str = "CE") -> dict[int, str]:
    with open(_latest_instrument_master()) as f:
        instruments = json.load(f)
    out = {}
    for row in instruments:
        if row.get("segment") != "NSE_FO":
            continue
        if row.get("name") != "NIFTY" or row.get("instrument_type") != option_type:
            continue
        expiry_d = datetime.fromtimestamp(row["expiry"] / 1000, tz=timezone.utc).date()
        if expiry_d != expiry:
            continue
        out[int(round(row["strike_price"]))] = row["instrument_key"]
    return out


def fetch_hourly(instrument_key: str, from_date: date, to_date: date) -> list[tuple[datetime, float]]:
    """Hourly closes, chunked to respect Upstox's ~90-day cap per request."""
    hourly = []
    cur = from_date
    while cur <= to_date:
        chunk_end = min(cur + timedelta(days=89), to_date)
        c = get_historical_candles(instrument_key, "hours", 1, cur.isoformat(), chunk_end.isoformat())
        hourly.extend(c)
        cur = chunk_end + timedelta(days=1)
    return sorted(((datetime.fromisoformat(c[0]), c[4]) for c in hourly), key=lambda x: x[0])


def fetch_daily(instrument_key: str, from_date: date, to_date: date) -> dict[date, float]:
    candles = get_historical_candles(instrument_key, "days", 1, from_date.isoformat(), to_date.isoformat())
    return {datetime.fromisoformat(c[0]).date(): c[4] for c in candles}


def run_backtest(
    from_date: date, to_date: date, expiry: date, lot_size: int,
    base_pullback_pct: float, adj_step_points: int, adj_strike_gap: int, adj_sell_lots: int,
    skip_first_hourly_candle: bool = True,
    weekly_pullback_pct: float = 0.02, weekly_window_days: int = 7,
    include_charges: bool = True, exit_pct: float | None = None, exit_direction: str = "up",
):
    nifty_ikey = UPSTOX_INSTRUMENT_KEYS["NIFTY50"]
    bars = fetch_hourly(nifty_ikey, from_date, to_date)
    daily_close = fetch_daily(nifty_ikey, from_date, to_date)
    daily_dates = sorted(daily_close.keys())
    latest_day = daily_dates[-1]

    trigger_bars = [(ts, spot) for ts, spot in bars if not skip_first_hourly_candle or ts.hour != 9]

    strike_to_ikey = load_strike_to_ikey(expiry)
    snap_strike = make_strike_snapper(strike_to_ikey, from_date, to_date)

    # ---- base ladder ----
    # Two trigger regimes depending on spot vs the last entry's own spot:
    #   at/below last entry  -> base_pullback_pct fall from it (chained)
    #   above last entry     -> weekly_pullback_pct fall from the highest
    #                           close in the trailing weekly_window_days,
    #                           where that rolling-high window resets
    #                           (empties) at every new entry.
    from collections import deque
    base_entries = []
    last_entry_spot = None
    last_entry_ts = None
    window = deque()  # (ts, spot) pairs since the last entry, for the rolling high
    window_span = timedelta(days=weekly_window_days)

    for ts, spot in trigger_bars:
        if last_entry_ts is not None:
            cutoff = max(last_entry_ts, ts - window_span)
            while window and window[0][0] < cutoff:
                window.popleft()

        if last_entry_spot is None:
            fire = True
            rule = "first"
        elif spot <= last_entry_spot:
            fire = spot <= last_entry_spot * (1 - base_pullback_pct)
            rule = "pullback_1pct"
        else:
            peak = max((s for _, s in window), default=spot)
            fire = spot <= peak * (1 - weekly_pullback_pct)
            rule = "weekly_pullback"

        window.append((ts, spot))

        if fire:
            strike_a = snap_strike(compute_strike_a(spot), ts.date())
            strike_b = snap_strike(strike_a + 1000, ts.date())
            base_entries.append({"ts": ts, "date": ts.date(), "spot": spot,
                                  "strikeA": strike_a, "strikeB": strike_b,
                                  "trigger_rule": rule})
            last_entry_spot = spot
            last_entry_ts = ts
            window.clear()
            window.append((ts, spot))

    # ---- exit scan: first bar (either direction) where spot has moved exit_pct from THIS base's own entry spot ----
    if exit_pct is not None:
        for be in base_entries:
            be["exit_ts"] = be["exit_date"] = be["exit_spot"] = be["exit_dir"] = None
            for ts, spot in trigger_bars:
                if ts <= be["ts"]:
                    continue
                move = (spot - be["spot"]) / be["spot"]
                hit = (move >= exit_pct if exit_direction == "up" else
                       -move >= exit_pct if exit_direction == "down" else
                       abs(move) >= exit_pct)
                if hit:
                    be["exit_ts"], be["exit_date"], be["exit_spot"] = ts, ts.date(), spot
                    be["exit_dir"] = "up" if move > 0 else "down"
                    break
    else:
        for be in base_entries:
            be["exit_ts"] = be["exit_date"] = be["exit_spot"] = be["exit_dir"] = None

    # ---- adjustment overlay ----
    adjustments = []
    for bi, be in enumerate(base_entries):
        next_threshold = be["spot"] - adj_step_points
        for ts, spot in trigger_bars:
            if ts <= be["ts"]:
                continue
            if be["exit_ts"] is not None and ts >= be["exit_ts"]:
                break  # no new adjustments on or after the exit bar itself
            while spot <= next_threshold:
                new_strike_a = snap_strike(compute_strike_a(spot), ts.date())
                new_strike_b = snap_strike(new_strike_a + adj_strike_gap, ts.date())
                adjustments.append({"base_idx": bi, "ts": ts, "date": ts.date(), "spot": spot,
                                     "strikeA": new_strike_a, "strikeB": new_strike_b,
                                     "base_spot": be["spot"], "base_ts": be["ts"]})
                next_threshold -= adj_step_points

    # ---- premium history for every strike used (always daily CLOSE) ----
    needed_strikes = sorted({be["strikeA"] for be in base_entries} | {be["strikeB"] for be in base_entries}
                             | {a["strikeA"] for a in adjustments} | {a["strikeB"] for a in adjustments})
    missing = [s for s in needed_strikes if s not in strike_to_ikey]
    if missing:
        print(f"!! Strikes with no listed {expiry} CE contract: {missing}", file=sys.stderr)

    premium_history = {}
    for s in needed_strikes:
        ikey = strike_to_ikey.get(s)
        if not ikey:
            continue
        premium_history[s] = fetch_daily(ikey, from_date, to_date)

    def premium_on_or_before(strike, target_date):
        hist = premium_history.get(strike, {})
        if target_date in hist:
            return hist[target_date]
        avail = [d for d in hist if d <= target_date]
        return hist[max(avail)] if avail else None

    def leg_pair_econ(strike_buy, strike_sell, entry_date, lots_buy, lots_sell, mark_date):
        be_ = premium_on_or_before(strike_buy, entry_date)
        bn_ = premium_on_or_before(strike_buy, mark_date)
        se_ = premium_on_or_before(strike_sell, entry_date)
        sn_ = premium_on_or_before(strike_sell, mark_date)
        debit = (be_ * lots_buy - se_ * lots_sell) * lot_size
        value_now = (bn_ * lots_buy - sn_ * lots_sell) * lot_size
        return debit, value_now, value_now - debit

    # ---- unified chronological event list ----
    # A base entry that exited is marked (both its own pair and every adjustment opened
    # under it) at its exit-day close — realized, not still floating with the market.
    # One still open at to_date is marked at the latest available premium, as before.
    events = []
    for i, be in enumerate(base_entries):
        mark_date = be["exit_date"] or latest_day
        debit, value_now, pnl = leg_pair_econ(be["strikeA"], be["strikeB"], be["date"], 1, 1, mark_date)
        events.append({"type": "base", "base_idx": i, "ts": be["ts"], "date": be["date"], "spot": be["spot"],
                        "trigger_rule": be["trigger_rule"], "mark_date": mark_date,
                        "exit_date": be["exit_date"], "exit_spot": be["exit_spot"], "exit_dir": be["exit_dir"],
                        "legs": [{"strike": be["strikeA"], "side": "BUY", "lots": 1},
                                 {"strike": be["strikeB"], "side": "SELL", "lots": 1}],
                        "debit": debit, "pnl_now": pnl})
    for adj in adjustments:
        be = base_entries[adj["base_idx"]]
        mark_date = be["exit_date"] or latest_day
        debit, value_now, pnl = leg_pair_econ(adj["strikeA"], adj["strikeB"], adj["date"], 1, adj_sell_lots, mark_date)
        events.append({"type": "adjustment", "base_idx": adj["base_idx"], "ts": adj["ts"], "date": adj["date"],
                        "spot": adj["spot"], "trigger_rule": "adjustment", "mark_date": mark_date,
                        "exit_date": be["exit_date"], "exit_spot": be["exit_spot"], "exit_dir": be["exit_dir"],
                        "legs": [{"strike": adj["strikeA"], "side": "BUY", "lots": 1},
                                 {"strike": adj["strikeB"], "side": "SELL", "lots": adj_sell_lots}],
                        "debit": debit, "pnl_now": pnl})
    events.sort(key=lambda e: e["ts"])
    for i, e in enumerate(events):
        e["idx"] = i

    # ---- real per-leg charges at entry (brokerage, STT, exchange, GST, stamp duty) ----
    if include_charges:
        for e in events:
            leg_charges = []
            total_charges = 0.0
            for leg in e["legs"]:
                ikey = strike_to_ikey.get(leg["strike"])
                entry_prem = premium_on_or_before(leg["strike"], e["date"])
                if not ikey or entry_prem is None:
                    leg_charges.append(None)
                    continue
                try:
                    c = get_brokerage(ikey, leg["lots"] * lot_size, leg["side"], entry_prem, product="D")
                except Exception as ex:
                    print(f"  [charges] failed for {leg['side']} {leg['strike']}CE @ {e['ts']}: {ex}", file=sys.stderr)
                    leg_charges.append(None)
                    continue
                leg_charges.append(c)
                total_charges += c["total"]
            e["leg_charges"] = leg_charges
            e["charges_total"] = total_charges

    # ---- daily total PnL curve ----
    # Before an event's exit_date (or if it never exits): mark-to-market against day d,
    # same as before. From exit_date onward: freeze the mark at exit_date — the position
    # is closed and realized, it no longer floats with the market.
    daily_pnl_curve = []
    for d in daily_dates:
        total = base_total = adj_total = charges_total = 0.0
        n_open = 0
        for e in events:
            if e["date"] > d:
                continue
            exited = e["exit_date"] is not None and d >= e["exit_date"]
            if not exited:
                n_open += 1
            mark_day = e["exit_date"] if exited else d
            buy_leg = next(l for l in e["legs"] if l["side"] == "BUY")
            sell_leg = next(l for l in e["legs"] if l["side"] == "SELL")
            b_entry = premium_on_or_before(buy_leg["strike"], e["date"])
            b_day = premium_on_or_before(buy_leg["strike"], mark_day)
            s_entry = premium_on_or_before(sell_leg["strike"], e["date"])
            s_day = premium_on_or_before(sell_leg["strike"], mark_day)
            debit = (b_entry * buy_leg["lots"] - s_entry * sell_leg["lots"]) * lot_size
            value = (b_day * buy_leg["lots"] - s_day * sell_leg["lots"]) * lot_size
            pnl = value - debit
            total += pnl
            if e["type"] == "base":
                base_total += pnl
            else:
                adj_total += pnl
            charges_total += e.get("charges_total", 0.0)
        daily_pnl_curve.append({"date": d, "spot": daily_close[d], "total_pnl": total,
                                 "base_pnl": base_total, "adj_pnl": adj_total, "n_open": n_open,
                                 "charges_to_date": charges_total, "total_pnl_net": total - charges_total})

    # ---- final net legs + margin ----
    # Exited events are closed positions — they contributed their realized P&L to the
    # curve/totals above but hold no book risk, so they're excluded from what's still on.
    net_lots = {}
    for e in events:
        if e["exit_date"] is not None:
            continue
        for l in e["legs"]:
            sign = 1 if l["side"] == "BUY" else -1
            net_lots[l["strike"]] = net_lots.get(l["strike"], 0) + sign * l["lots"]

    final_legs = []
    margin_legs = []
    for strike in sorted(net_lots):
        lots = net_lots[strike]
        if lots == 0:
            continue
        ltp = premium_on_or_before(strike, latest_day)
        side = "BUY" if lots > 0 else "SELL"
        final_legs.append({"strike": strike, "lots": lots, "side": side, "ltp": ltp})
        ikey = strike_to_ikey.get(strike)
        if ikey:
            margin_legs.append({"instrument_key": ikey, "transaction_type": side,
                                 "quantity": abs(lots) * lot_size, "price": ltp, "product": "D"})

    margin_result = None
    try:
        m = get_margin(margin_legs)
        margin_result = {
            "required_margin": m["required_margin"], "final_margin": m["final_margin"],
            "legs": [{"instrument_key": lb["instrument_key"], "span_margin": lb["span_margin"],
                      "exposure_margin": lb["exposure_margin"], "total_margin": lb["total_margin"]}
                     for lb in m["legs"]],
        }
    except Exception as e:
        print(f"Margin call failed: {e}", file=sys.stderr)

    return {
        "meta": {
            "lot_size": lot_size, "expiry": expiry.isoformat(), "from_date": from_date.isoformat(),
            "to_date": latest_day.isoformat(), "base_pullback_pct": base_pullback_pct,
            "adj_step_points": adj_step_points, "adj_strike_gap": adj_strike_gap,
            "adj_sell_lots": adj_sell_lots, "skip_first_hourly_candle": skip_first_hourly_candle,
            "weekly_pullback_pct": weekly_pullback_pct, "weekly_window_days": weekly_window_days,
            "n_base": len(base_entries), "n_adjustments": len(adjustments), "n_total": len(events),
            "n_base_weekly_rule": sum(1 for be in base_entries if be["trigger_rule"] == "weekly_pullback"),
            "include_charges": include_charges, "exit_pct": exit_pct,
            "exit_direction": exit_direction if exit_pct is not None else None,
            "n_exited": sum(1 for be in base_entries if be["exit_date"] is not None),
        },
        "bars": bars, "trigger_bars": trigger_bars, "daily_close": daily_close,
        "events": events, "daily_pnl_curve": daily_pnl_curve,
        "final_legs": final_legs, "margin": margin_result,
    }


def to_json_payload(result: dict) -> dict:
    """Serialize the run_backtest() result to the JSON shape the artifact expects."""
    def ev_json(e):
        d = {"idx": e["idx"], "type": e["type"], "base_idx": e["base_idx"],
             "trigger_rule": e["trigger_rule"],
             "ts": e["ts"].isoformat(), "date": e["date"].isoformat(), "spot": round(e["spot"], 2),
             "legs": e["legs"], "debit": round(e["debit"], 2), "pnl_now": round(e["pnl_now"], 2),
             "exit_date": e["exit_date"].isoformat() if e["exit_date"] else None,
             "exit_spot": round(e["exit_spot"], 2) if e["exit_spot"] is not None else None,
             "exit_dir": e["exit_dir"]}
        if "charges_total" in e:
            d["charges_total"] = round(e["charges_total"], 2)
            d["leg_charges"] = [
                ({k: round(v, 2) for k, v in c.items()} if c else None) for c in e["leg_charges"]
            ]
            d["pnl_net_of_charges"] = round(e["pnl_now"] - e["charges_total"], 2)
        return d

    events_json = [ev_json(e) for e in result["events"]]
    totals = {
        "base_debit": round(sum(e["debit"] for e in result["events"] if e["type"] == "base"), 2),
        "base_pnl": round(sum(e["pnl_now"] for e in result["events"] if e["type"] == "base"), 2),
        "adj_debit": round(sum(e["debit"] for e in result["events"] if e["type"] == "adjustment"), 2),
        "adj_pnl": round(sum(e["pnl_now"] for e in result["events"] if e["type"] == "adjustment"), 2),
    }
    totals["combined_debit"] = round(totals["base_debit"] + totals["adj_debit"], 2)
    totals["combined_pnl"] = round(totals["base_pnl"] + totals["adj_pnl"], 2)
    if result["meta"]["include_charges"]:
        totals["total_charges"] = round(sum(e.get("charges_total", 0) for e in result["events"]), 2)
        totals["combined_pnl_net_of_charges"] = round(totals["combined_pnl"] - totals["total_charges"], 2)

    return {
        "meta": result["meta"],
        "hourly_spot": [[ts.isoformat(), round(c, 2)] for ts, c in result["bars"]],
        "events": events_json,
        "daily_pnl_curve": [{"date": r["date"].isoformat(), "spot": round(r["spot"], 2),
                              "total_pnl": round(r["total_pnl"], 2), "base_pnl": round(r["base_pnl"], 2),
                              "adj_pnl": round(r["adj_pnl"], 2), "n_open": r["n_open"],
                              "charges_to_date": round(r.get("charges_to_date", 0), 2),
                              "total_pnl_net": round(r.get("total_pnl_net", r["total_pnl"]), 2)}
                             for r in result["daily_pnl_curve"]],
        "final_legs": result["final_legs"],
        "margin": result["margin"],
        "totals": totals,
    }


def print_report(result: dict):
    events, totals = result["events"], None
    base_debit = sum(e["debit"] for e in events if e["type"] == "base")
    base_pnl = sum(e["pnl_now"] for e in events if e["type"] == "base")
    adj_debit = sum(e["debit"] for e in events if e["type"] == "adjustment")
    adj_pnl = sum(e["pnl_now"] for e in events if e["type"] == "adjustment")

    exit_pct = result["meta"].get("exit_pct")
    exit_hdr = (f"   Exit: {exit_pct:.0%} {result['meta'].get('exit_direction')} move, "
                f"{result['meta'].get('n_exited', 0)} of {result['meta']['n_base']} base entries exited") if exit_pct else ""
    print(f"\nBase entries: {result['meta']['n_base']}   Adjustments: {result['meta']['n_adjustments']}{exit_hdr}")
    print("=" * 100)
    for e in events:
        buy_leg = next(l for l in e["legs"] if l["side"] == "BUY")
        sell_leg = next(l for l in e["legs"] if l["side"] == "SELL")
        tag = f"base#{e['base_idx']}" if e["type"] == "base" else f"adj->base#{e['base_idx']}"
        rule_tag = "" if e["type"] != "base" else (" [weekly-2%]" if e["trigger_rule"] == "weekly_pullback" else "")
        charges_tag = f"  charges=Rs{e['charges_total']:,.0f}" if "charges_total" in e else ""
        exit_tag = f"  EXIT@{e['exit_date']} spot={e['exit_spot']:.0f} ({e['exit_dir']})" if e["exit_date"] else ""
        print(f"  [{tag:14s}] {e['ts']}  spot={e['spot']:.2f}{rule_tag}{exit_tag}  "
              f"BUY {buy_leg['lots']}x {buy_leg['strike']}CE  SELL {sell_leg['lots']}x {sell_leg['strike']}CE  "
              f"debit=Rs{e['debit']:,.0f}  pnl=Rs{e['pnl_now']:+,.0f}{charges_tag}")
    print("=" * 100)
    print(f"Base ladder     : debit=Rs{base_debit:,.0f}   pnl=Rs{base_pnl:+,.0f}")
    print(f"Adjustment layer: debit=Rs{adj_debit:,.0f}   pnl=Rs{adj_pnl:+,.0f}")
    print(f"COMBINED        : debit=Rs{base_debit+adj_debit:,.0f}   pnl=Rs{base_pnl+adj_pnl:+,.0f}")
    if any("charges_total" in e for e in events):
        total_charges = sum(e.get("charges_total", 0) for e in events)
        print(f"Total charges (brokerage+STT+exchange+GST+stamp duty, entry legs only): Rs{total_charges:,.0f}")
        print(f"COMBINED, net of charges: pnl=Rs{base_pnl+adj_pnl-total_charges:+,.0f}")
    print("=" * 100)
    print("\nFinal net legs:")
    for l in result["final_legs"]:
        print(f"  {l['side']:4s} {abs(l['lots'])} lot(s)  {l['strike']} CE  @ {l['ltp']:.2f}")
    if result["margin"]:
        print(f"\nRequired margin: Rs {result['margin']['required_margin']:,.0f}")
        print(f"Final margin   : Rs {result['margin']['final_margin']:,.0f}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from-date", type=date.fromisoformat, default=date(2026, 1, 1))
    p.add_argument("--to-date", type=date.fromisoformat, default=date.today())
    p.add_argument("--expiry", type=date.fromisoformat, default=date(2026, 12, 29))
    p.add_argument("--lot-size", type=int, default=65)
    p.add_argument("--base-pullback-pct", type=float, default=0.01)
    p.add_argument("--adj-step-points", type=int, default=1000)
    p.add_argument("--adj-strike-gap", type=int, default=2000)
    p.add_argument("--adj-sell-lots", type=int, default=3)
    p.add_argument("--weekly-pullback-pct", type=float, default=0.02,
                    help="Fall from the trailing weekly high that triggers a new base entry "
                         "when spot is currently ABOVE the last entry's spot (default 2%%).")
    p.add_argument("--weekly-window-days", type=int, default=7,
                    help="Calendar-day window for the rolling high used by --weekly-pullback-pct "
                         "(resets to empty at every new entry).")
    p.add_argument("--allow-first-hourly-candle", action="store_true",
                    help="Don't skip the 09:15 candle when checking triggers (skipped by default).")
    p.add_argument("--no-charges", action="store_true",
                    help="Skip the real per-leg brokerage/STT/GST/stamp-duty charge calls "
                         "(one live Upstox call per leg — on by default).")
    p.add_argument("--exit-pct", type=float, default=None,
                    help="Exit a base entry (and every adjustment opened under it) the first time "
                         "spot moves this fraction, in --exit-direction, from that base entry's own "
                         "entry spot, e.g. 0.04 for 4%%. Off by default — nothing exits, everything "
                         "is held to --to-date.")
    p.add_argument("--exit-direction", choices=["up", "down", "both"], default="up",
                    help="Direction --exit-pct is measured in (default 'up' — a rally off the base "
                         "entry's spot). 'down' or 'both' also stop the adjustment overlay from "
                         "averaging in further, since that's exactly what it's meant to do on a fall.")
    p.add_argument("--export-json", type=str, default=None,
                    help="Write the artifact-ready JSON payload to this path.")
    args = p.parse_args()

    result = run_backtest(
        from_date=args.from_date, to_date=args.to_date, expiry=args.expiry, lot_size=args.lot_size,
        base_pullback_pct=args.base_pullback_pct, adj_step_points=args.adj_step_points,
        adj_strike_gap=args.adj_strike_gap, adj_sell_lots=args.adj_sell_lots,
        skip_first_hourly_candle=not args.allow_first_hourly_candle,
        weekly_pullback_pct=args.weekly_pullback_pct, weekly_window_days=args.weekly_window_days,
        include_charges=not args.no_charges, exit_pct=args.exit_pct, exit_direction=args.exit_direction,
    )
    print_report(result)

    if args.export_json:
        with open(args.export_json, "w") as f:
            json.dump(to_json_payload(result), f)
        print(f"\nWrote {args.export_json}")


if __name__ == "__main__":
    main()
