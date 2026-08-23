"""
NIFTY CE ladder-with-averaging backtest — a separate strategy from
nifty_dec_ce_ladder_backtest.py, sharing only its low-level plumbing
(strike snapping, premium fetch, charges, margin).

Strategy (as specified conversationally):

BASE (tracks spot continuously, not trigger-gated)
    base = compute_strike_a(spot): nearest 1000-multiple strike that is
    at least 800pts OTM from spot, re-evaluated on every hourly bar. A
    new base fires the first time this value reaches a level not yet
    seen — i.e. spot has crossed into a 1000-strike band with no base
    of its own yet. Example: base is 26000 while spot sits in (24200,
    25200]; the moment spot falls to 24200 or below, base rolls to
    25000 and fires (if this is the first time 25000 has come up).
    Symmetric — a base can roll up just as easily as down. A level
    that already has a base does NOT refire on a later revisit (spot
    oscillating back across a boundary would otherwise stack duplicate
    parallel ladders at the same strikes) — its averaging chain, live
    since its first appearance, simply keeps running.

ENTRY STRUCTURE, per base (a 1:1:1 call ladder)
    BUY  1 lot @ base
    SELL 1 lot @ base+1000
    SELL 1 lot @ base+2000
    All three snapped to the nearest strike actually listed AND priced
    for the chosen expiry on that date (see snap_to_listed in the
    sibling module — nearer monthlies can't be assumed to have every
    round-1000 strike; Dec, this script's default, generally does).

AVERAGING, independently per base, unbounded to --to-date
    Once a base's ladder is on, its OWN three strikes (never
    recomputed) are watched going forward: whenever the cost to open
    that same 1:1:1 set again has fallen --avg-debit-drop-pct (default
    5%) from the debit last paid for it, buy another 1:1:1 set at the
    identical three strikes. Chained — each fresh average resets the
    5%-drop threshold off its own debit. A base's chain runs for the
    entire remaining backtest window regardless of whether spot has
    since moved on to other bases — every base keeps averaging in
    parallel, independently, for as long as the window lasts.

NO EXITS — nothing in this script closes. Every base's ladder and every
average it accumulates is held open to --to-date and marked at the
latest available premium.

Usage:
    python analysis/nifty_ce_ladder_avg_backtest.py --from-date 2026-04-01
    python analysis/nifty_ce_ladder_avg_backtest.py --avg-debit-drop-pct 0.03
    python analysis/nifty_ce_ladder_avg_backtest.py --export-json /tmp/avg_ladder.json
"""
import argparse
import bisect
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from nifty_dec_ce_ladder_backtest import (
    compute_strike_a, make_strike_snapper, load_strike_to_ikey,
    fetch_hourly, fetch_daily,
)
from live.upstox_client import get_margin, get_brokerage
from config import UPSTOX_INSTRUMENT_KEYS


def run_backtest(
    from_date: date, to_date: date, expiry: date, lot_size: int,
    avg_debit_drop_pct: float = 0.05, skip_first_hourly_candle: bool = True,
    include_charges: bool = True,
):
    nifty_ikey = UPSTOX_INSTRUMENT_KEYS["NIFTY50"]
    bars = fetch_hourly(nifty_ikey, from_date, to_date)
    daily_close = fetch_daily(nifty_ikey, from_date, to_date)
    daily_dates = sorted(daily_close.keys())
    latest_day = daily_dates[-1]

    trigger_bars = [(ts, spot) for ts, spot in bars if not skip_first_hourly_candle or ts.hour != 9]

    strike_to_ikey = load_strike_to_ikey(expiry)
    snap_strike = make_strike_snapper(strike_to_ikey, from_date, to_date)

    # ---- bases: fire the first time compute_strike_a(spot) reaches each new level ----
    # A level already seen doesn't refire on a later revisit (spot oscillating back across a
    # boundary would otherwise stack duplicate parallel ladders at the same strikes) — its
    # averaging chain, already running since its first appearance, just continues.
    bases = []
    seen_raw = set()
    current_base_raw = None
    for ts, spot in trigger_bars:
        raw = compute_strike_a(spot)
        if raw != current_base_raw:
            current_base_raw = raw
            if raw not in seen_raw:
                seen_raw.add(raw)
                strike_a = snap_strike(raw, ts.date())
                strike_b = snap_strike(raw + 1000, ts.date())
                strike_c = snap_strike(raw + 2000, ts.date())
                bases.append({"base_id": len(bases), "ts": ts, "date": ts.date(), "spot": spot,
                              "strikeA": strike_a, "strikeB": strike_b, "strikeC": strike_c})

    # ---- premium history for every strike used ----
    needed_strikes = sorted({b[k] for b in bases for k in ("strikeA", "strikeB", "strikeC")})
    missing = [s for s in needed_strikes if s not in strike_to_ikey]
    if missing:
        print(f"!! Strikes with no listed {expiry} CE contract: {missing}", file=sys.stderr)

    premium_history = {}
    premium_history_hourly = {}
    for s in needed_strikes:
        ikey = strike_to_ikey.get(s)
        if not ikey:
            continue
        premium_history[s] = fetch_daily(ikey, from_date, to_date)
        premium_history_hourly[s] = fetch_hourly(ikey, from_date, to_date)  # [(ts, close), ...] sorted

    def premium_on_or_before(strike, target_date):
        hist = premium_history.get(strike, {})
        if target_date in hist:
            return hist[target_date]
        avail = [d for d in hist if d <= target_date]
        return hist[max(avail)] if avail else None

    def premiums_of(b, target_date):
        return (premium_on_or_before(b["strikeA"], target_date),
                premium_on_or_before(b["strikeB"], target_date),
                premium_on_or_before(b["strikeC"], target_date))

    # Hourly premium lookup — used for the entry/averaging DECISION so the trigger check runs
    # at the same time-resolution as the hourly spot bars driving it. A daily-close-only premium
    # smears a fast intraday move into one number per day; hourly avoids that. Falls back to the
    # daily series (which covers a slightly wider range/gaps) if no hourly candle exists yet at
    # that exact point (e.g. very first bars of a newly-listed contract).
    def premium_on_or_before_hourly(strike, target_ts):
        hist = premium_history_hourly.get(strike, [])
        idx = bisect.bisect_right([h[0] for h in hist], target_ts) - 1
        if idx >= 0:
            return hist[idx][1]
        return premium_on_or_before(strike, target_ts.date())

    def premiums_of_ts(b, target_ts):
        return (premium_on_or_before_hourly(b["strikeA"], target_ts),
                premium_on_or_before_hourly(b["strikeB"], target_ts),
                premium_on_or_before_hourly(b["strikeC"], target_ts))

    def debit_of(b, target_date):
        a, s, c = premiums_of(b, target_date)
        return (a - s - c) * lot_size

    def value_of(b, target_date):
        return debit_of(b, target_date)  # same leg shape (1 buy, 2 sell) — mark-to-date value

    LEGS = lambda b: [{"strike": b["strikeA"], "side": "BUY", "lots": 1},
                       {"strike": b["strikeB"], "side": "SELL", "lots": 1},
                       {"strike": b["strikeC"], "side": "SELL", "lots": 1}]

    # A drop of `pct` always means "pct of the position's own size, in the cheaper direction" —
    # multiplying by (1-pct) directly would flip that direction for a net-credit (negative) debit,
    # since e.g. -100 * 0.95 = -95 is HIGHER than -100, not lower. Subtracting a magnitude-based
    # step keeps "fell by pct" correct regardless of sign.
    def step_down(debit, pct):
        return debit - abs(debit) * pct

    # ---- unified event list: one "base" entry + N "avg" entries per base ----
    events = []
    for b in bases:
        entry_prems = premiums_of_ts(b, b["ts"])
        entry_debit = (entry_prems[0] - entry_prems[1] - entry_prems[2]) * lot_size
        events.append({"type": "base", "base_id": b["base_id"], "ts": b["ts"], "date": b["date"],
                        "spot": b["spot"], "legs": LEGS(b), "debit": entry_debit, "leg_premiums": entry_prems,
                        "value_now": value_of(b, latest_day), "pnl_now": value_of(b, latest_day) - entry_debit})

        next_threshold = step_down(entry_debit, avg_debit_drop_pct)
        for ts, spot in trigger_bars:
            if ts <= b["ts"]:
                continue
            cur_prems = premiums_of_ts(b, ts)
            cur_debit = (cur_prems[0] - cur_prems[1] - cur_prems[2]) * lot_size
            if cur_debit <= next_threshold:
                events.append({"type": "avg", "base_id": b["base_id"], "ts": ts, "date": ts.date(),
                                "spot": spot, "legs": LEGS(b), "debit": cur_debit, "leg_premiums": cur_prems,
                                "value_now": value_of(b, latest_day), "pnl_now": value_of(b, latest_day) - cur_debit})
                next_threshold = step_down(cur_debit, avg_debit_drop_pct)

    events.sort(key=lambda e: e["ts"])
    for i, e in enumerate(events):
        e["idx"] = i

    # ---- per-event P&L-over-time: this one set's own mark-to-market, from its entry date on ----
    base_by_id = {b["base_id"]: b for b in bases}
    for e in events:
        b = base_by_id[e["base_id"]]
        e["pnl_history"] = [{"date": d, "pnl": value_of(b, d) - e["debit"]}
                             for d in daily_dates if d >= e["date"]]

    # ---- real per-leg charges at entry ----
    if include_charges:
        for e in events:
            leg_charges = []
            total_charges = 0.0
            for leg in e["legs"]:
                ikey = strike_to_ikey.get(leg["strike"])
                entry_prem = premium_on_or_before_hourly(leg["strike"], e["ts"])
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
    daily_pnl_curve = []
    for d in daily_dates:
        total = charges_total = 0.0
        n_open = 0
        for e in events:
            if e["date"] > d:
                continue
            n_open += 1
            b = next(bb for bb in bases if bb["base_id"] == e["base_id"])
            value_d = value_of(b, d)
            total += value_d - e["debit"]
            charges_total += e.get("charges_total", 0.0)
        daily_pnl_curve.append({"date": d, "spot": daily_close[d], "total_pnl": total,
                                 "n_open": n_open, "charges_to_date": charges_total,
                                 "total_pnl_net": total - charges_total})

    # ---- final net legs + margin (nothing exits, so everything ever opened is still on) ----
    net_lots = {}
    for e in events:
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

    # ---- per-base summary: sets accumulated + blended average price per leg ----
    base_summary = []
    for b in bases:
        b_events = [e for e in events if e["base_id"] == b["base_id"]]
        n_sets = len(b_events)
        avg_a = sum(e["leg_premiums"][0] for e in b_events) / n_sets
        avg_b = sum(e["leg_premiums"][1] for e in b_events) / n_sets
        avg_c = sum(e["leg_premiums"][2] for e in b_events) / n_sets
        total_debit = sum(e["debit"] for e in b_events)
        total_pnl = sum(e["pnl_now"] for e in b_events)
        total_charges = sum(e.get("charges_total", 0.0) for e in b_events)

        # Combined P&L over time for this base = base + every averaged-in set at its strikes,
        # summed — each set contributes from its own entry date on, marked at that day's value,
        # against its own entry debit; charges land as a one-time hit on the date they're paid.
        b_events_by_date = sorted(b_events, key=lambda e: e["date"])
        pnl_history = []
        for d in daily_dates:
            open_events = [e for e in b_events_by_date if e["date"] <= d]
            if not open_events:
                continue
            v = value_of(b, d)
            gross = sum(v - e["debit"] for e in open_events)
            charges_to_date = sum(e.get("charges_total", 0.0) for e in open_events)
            pnl_history.append({"date": d, "pnl": gross, "pnl_net": gross - charges_to_date, "n_open": len(open_events)})

        base_summary.append({
            "base_id": b["base_id"], "strikeA": b["strikeA"], "strikeB": b["strikeB"], "strikeC": b["strikeC"],
            "entry_ts": b["ts"], "entry_spot": b["spot"], "n_sets": n_sets,
            "avg_price_a": avg_a, "avg_price_b": avg_b, "avg_price_c": avg_c,
            "total_debit": total_debit, "total_pnl": total_pnl, "total_charges": total_charges,
            "pnl_history": pnl_history,
        })

    return {
        "meta": {
            "lot_size": lot_size, "expiry": expiry.isoformat(), "from_date": from_date.isoformat(),
            "to_date": latest_day.isoformat(), "avg_debit_drop_pct": avg_debit_drop_pct,
            "skip_first_hourly_candle": skip_first_hourly_candle,
            "n_bases": len(bases), "n_avg": len(events) - len(bases), "n_total": len(events),
            "include_charges": include_charges,
        },
        "bars": bars, "daily_close": daily_close, "bases": bases,
        "events": events, "daily_pnl_curve": daily_pnl_curve,
        "final_legs": final_legs, "margin": margin_result, "base_summary": base_summary,
    }


def print_report(result: dict):
    events, meta = result["events"], result["meta"]
    print(f"\nBases: {meta['n_bases']}   Averages: {meta['n_avg']}   "
          f"(avg trigger: debit falls {meta['avg_debit_drop_pct']:.0%})")
    print("=" * 100)
    for e in events:
        buy_leg = e["legs"][0]
        sell_legs = e["legs"][1:]
        tag = f"base#{e['base_id']}" if e["type"] == "base" else f"avg->base#{e['base_id']}"
        charges_tag = f"  charges=Rs{e['charges_total']:,.0f}" if "charges_total" in e else ""
        sell_str = " ".join(f"SELL 1x {l['strike']}CE" for l in sell_legs)
        print(f"  [{tag:12s}] {e['ts']}  spot={e['spot']:.2f}  "
              f"BUY 1x {buy_leg['strike']}CE  {sell_str}  "
              f"debit=Rs{e['debit']:,.0f}  pnl=Rs{e['pnl_now']:+,.0f}{charges_tag}")
    print("=" * 100)
    total_debit = sum(e["debit"] for e in events)
    total_pnl = sum(e["pnl_now"] for e in events)
    print(f"COMBINED        : debit=Rs{total_debit:,.0f}   pnl=Rs{total_pnl:+,.0f}")
    if any("charges_total" in e for e in events):
        total_charges = sum(e.get("charges_total", 0) for e in events)
        print(f"Total charges (brokerage+STT+exchange+GST+stamp duty, entry legs only): Rs{total_charges:,.0f}")
        print(f"COMBINED, net of charges: pnl=Rs{total_pnl-total_charges:+,.0f}")
    print("=" * 100)
    print("\nFinal net legs:")
    for l in result["final_legs"]:
        print(f"  {l['side']:4s} {abs(l['lots'])} lot(s)  {l['strike']} CE  @ {l['ltp']:.2f}")
    if result["margin"]:
        print(f"\nRequired margin: Rs {result['margin']['required_margin']:,.0f}")
        print(f"Final margin   : Rs {result['margin']['final_margin']:,.0f}")


def to_json_payload(result: dict) -> dict:
    def ev_json(e):
        d = {"idx": e["idx"], "type": e["type"], "base_id": e["base_id"],
             "ts": e["ts"].isoformat(), "date": e["date"].isoformat(), "spot": round(e["spot"], 2),
             "legs": e["legs"], "debit": round(e["debit"], 2), "pnl_now": round(e["pnl_now"], 2),
             "leg_premiums": [round(p, 2) for p in e["leg_premiums"]]}
        charges = e.get("charges_total", 0.0)
        if "charges_total" in e:
            d["charges_total"] = round(charges, 2)
            d["leg_charges"] = [({k: round(v, 2) for k, v in c.items()} if c else None) for c in e["leg_charges"]]
            d["pnl_net_of_charges"] = round(e["pnl_now"] - charges, 2)
        d["pnl_history"] = [{"date": p["date"].isoformat(), "pnl": round(p["pnl"], 2),
                              "pnl_net": round(p["pnl"] - charges, 2)} for p in e["pnl_history"]]
        return d

    events_json = [ev_json(e) for e in result["events"]]
    totals = {
        "combined_debit": round(sum(e["debit"] for e in result["events"]), 2),
        "combined_pnl": round(sum(e["pnl_now"] for e in result["events"]), 2),
    }
    if result["meta"]["include_charges"]:
        totals["total_charges"] = round(sum(e.get("charges_total", 0) for e in result["events"]), 2)
        totals["combined_pnl_net_of_charges"] = round(totals["combined_pnl"] - totals["total_charges"], 2)

    return {
        "meta": result["meta"],
        "hourly_spot": [[ts.isoformat(), round(c, 2)] for ts, c in result["bars"]],
        "events": events_json,
        "daily_pnl_curve": [{"date": r["date"].isoformat(), "spot": round(r["spot"], 2),
                              "total_pnl": round(r["total_pnl"], 2), "n_open": r["n_open"],
                              "charges_to_date": round(r.get("charges_to_date", 0), 2),
                              "total_pnl_net": round(r.get("total_pnl_net", r["total_pnl"]), 2)}
                             for r in result["daily_pnl_curve"]],
        "final_legs": result["final_legs"],
        "margin": result["margin"],
        "totals": totals,
        "base_summary": [{
            "base_id": b["base_id"], "strikeA": b["strikeA"], "strikeB": b["strikeB"], "strikeC": b["strikeC"],
            "entry_ts": b["entry_ts"].isoformat(), "entry_spot": round(b["entry_spot"], 2), "n_sets": b["n_sets"],
            "avg_price_a": round(b["avg_price_a"], 2), "avg_price_b": round(b["avg_price_b"], 2),
            "avg_price_c": round(b["avg_price_c"], 2), "total_debit": round(b["total_debit"], 2),
            "total_pnl": round(b["total_pnl"], 2), "total_charges": round(b["total_charges"], 2),
            "total_pnl_net": round(b["total_pnl"] - b["total_charges"], 2),
            "pnl_history": [{"date": p["date"].isoformat(), "pnl": round(p["pnl"], 2),
                              "pnl_net": round(p["pnl_net"], 2), "n_open": p["n_open"]} for p in b["pnl_history"]],
        } for b in result["base_summary"]],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from-date", type=date.fromisoformat, default=date(2026, 4, 1))
    p.add_argument("--to-date", type=date.fromisoformat, default=date.today())
    p.add_argument("--expiry", type=date.fromisoformat, default=date(2026, 12, 29))
    p.add_argument("--lot-size", type=int, default=65)
    p.add_argument("--avg-debit-drop-pct", type=float, default=0.05,
                    help="Average in (buy another 1:1:1 set at the same 3 strikes) once the cost to open "
                         "that set again has fallen this fraction from the last time it was paid (default 5%%).")
    p.add_argument("--allow-first-hourly-candle", action="store_true",
                    help="Don't skip the 09:15 candle when checking triggers (skipped by default).")
    p.add_argument("--no-charges", action="store_true",
                    help="Skip the real per-leg brokerage/STT/GST/stamp-duty charge calls.")
    p.add_argument("--export-json", type=str, default=None,
                    help="Write the JSON payload to this path.")
    args = p.parse_args()

    result = run_backtest(
        from_date=args.from_date, to_date=args.to_date, expiry=args.expiry, lot_size=args.lot_size,
        avg_debit_drop_pct=args.avg_debit_drop_pct,
        skip_first_hourly_candle=not args.allow_first_hourly_candle,
        include_charges=not args.no_charges,
    )
    print_report(result)

    if args.export_json:
        with open(args.export_json, "w") as f:
            json.dump(to_json_payload(result), f)
        print(f"\nWrote {args.export_json}")


if __name__ == "__main__":
    main()
