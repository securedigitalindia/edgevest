"""
NIFTY CE zone-averaging ladder backtest — a fourth, separate strategy from
the other CE/PE scripts, sharing only low-level plumbing (strike listing/
pricing fetch, charges, margin, strike snapping).

Strategy (as specified conversationally, incl. a worked example):

BASE ZONE (re-evaluated continuously off hourly spot, exactly like
nifty_ce_ladder_avg_backtest.py's base rule)
    base_raw = compute_strike_a(spot): nearest 1000-multiple strike that is
    at least --base-min-gap (default 800) points OTM from spot. This value
    is constant while spot sits inside a 1000-wide band and only changes
    when spot crosses a band edge — e.g. base_raw = 27000 for any spot in
    (25200, 26200]; the moment spot drops to 25200 or below, base_raw
    rolls down to 26000. A brand new base fires the first time a band is
    ever reached (a later revisit of an already-fired band does not
    refire it) — example: spot=26100 -> base 27000, entry BUY 1x 27000CE /
    SELL 2x 29000CE.

WITHIN-ZONE AVERAGING (chained, roughly doubling each time, capped)
    While spot stays inside its own base's band, every further --step
    (default 200) points of fall adds one more trade at the SAME two
    strikes: the ADDED size is (current running total + 1) lots, so with
    lot_start=1 the running total goes 1 -> 3 -> 7 -> 15 -> 31 (adds of
    1, 2, 4, 8, 16). Continuing the example: base 27000/29000 (1 lot)
    averages in +2 (total 3) on the first 200pt fall while spot is still
    above 25200, +4 (total 7) on the next, and so on. Capped at
    --max-avg averages per base (default 5, i.e. base + up to 5
    adjustments); pass 0 for unlimited.

ZONE EXIT ENDS THE CHAIN
    The instant spot leaves the base's own band (crosses either edge),
    that base's averaging chain is done — frozen at whatever lot count it
    reached. No more trades are added to it, even if spot later re-enters
    the same band. A new base fires for whichever band spot moves into
    next (continuing the example: once spot <= 25200, a new base fires at
    26000/28000, entry BUY 1x 26000CE / SELL 2x 28000CE, and its own
    within-zone averaging starts from there).

NO EXITS (yet) — nothing in this script closes a position by itself.
Every base and every averaged-in trade is held open to --to-date and
marked at the latest available premium. An exit rule (e.g. close on a
--exit-rise-pts move back up from a trade's own entry) is a likely
follow-up but is deliberately NOT implemented in this pass — this run is
entry-only, exactly as requested.

Premiums are looked up on the SAME hourly grid as the spot trigger (falls
back to the daily series only if no hourly candle exists yet at that
exact point).

Usage:
    python analysis/nifty_ce_zone_ladder_backtest.py --from-date 2026-01-01
    python analysis/nifty_ce_zone_ladder_backtest.py --export-json /tmp/ce_zone.json
"""
import argparse
import bisect
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from nifty_dec_ce_ladder_backtest import make_strike_snapper, load_strike_to_ikey, fetch_hourly, fetch_daily
from live.upstox_client import get_margin, get_brokerage
from config import UPSTOX_INSTRUMENT_KEYS


def run_backtest(
    from_date: date, to_date: date, expiry: date, lot_size: int,
    ratio: int = 2, step: int = 200, gap: int = 2000, base_min_gap: int = 800, lot_start: int = 1,
    max_avg: int | None = 5, skip_first_hourly_candle: bool = True, include_charges: bool = True,
):
    def compute_base_raw(spot):
        x = int(spot) + base_min_gap
        return ((x // 1000) + (1 if x % 1000 else 0)) * 1000

    nifty_ikey = UPSTOX_INSTRUMENT_KEYS["NIFTY50"]
    bars = fetch_hourly(nifty_ikey, from_date, to_date)
    daily_close = fetch_daily(nifty_ikey, from_date, to_date)
    daily_dates = sorted(daily_close.keys())
    latest_day = daily_dates[-1]

    trigger_bars = [(ts, spot) for ts, spot in bars if not skip_first_hourly_candle or ts.hour != 9]
    if not trigger_bars:
        raise RuntimeError("No trigger bars in window")

    strike_to_ikey = load_strike_to_ikey(expiry, option_type="CE")
    snap_strike = make_strike_snapper(strike_to_ikey, from_date, to_date)

    # ---- bases: fire the first time compute_base_raw(spot) reaches each new band ----
    bases = []
    seen_raw = set()
    current_base_raw = None
    for ts, spot in trigger_bars:
        raw = compute_base_raw(spot)
        if raw != current_base_raw:
            current_base_raw = raw
            if raw not in seen_raw:
                seen_raw.add(raw)
                bases.append({"base_id": len(bases), "raw": raw, "ts": ts, "date": ts.date(), "spot": spot})

    for b in bases:
        b["buy_strike"] = snap_strike(b["raw"], b["date"])
        b["sell_strike"] = snap_strike(b["raw"] + gap, b["date"])

    # ---- premium history: hourly (decision-grade) + daily (mark-to-market / fallback) ----
    needed_strikes = sorted({s for b in bases for s in (b["buy_strike"], b["sell_strike"])})
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
        premium_history_hourly[s] = fetch_hourly(ikey, from_date, to_date)

    def premium_on_or_before(strike, target_date):
        hist = premium_history.get(strike, {})
        if target_date in hist:
            return hist[target_date]
        avail = [d for d in hist if d <= target_date]
        return hist[max(avail)] if avail else None

    def premium_on_or_before_hourly(strike, target_ts):
        hist = premium_history_hourly.get(strike, [])
        idx = bisect.bisect_right([h[0] for h in hist], target_ts) - 1
        if idx >= 0:
            return hist[idx][1]
        return premium_on_or_before(strike, target_ts.date())

    def debit_of_ts(b, lots_buy, target_ts):
        lots_sell = lots_buy * ratio
        buy_p = premium_on_or_before_hourly(b["buy_strike"], target_ts)
        sell_p = premium_on_or_before_hourly(b["sell_strike"], target_ts)
        return (buy_p * lots_buy - sell_p * lots_sell) * lot_size, buy_p, sell_p

    def value_of(b, lots_buy, target_date):
        lots_sell = lots_buy * ratio
        buy_p = premium_on_or_before(b["buy_strike"], target_date)
        sell_p = premium_on_or_before(b["sell_strike"], target_date)
        return (buy_p * lots_buy - sell_p * lots_sell) * lot_size

    def LEGS(b, lots_buy):
        return [{"strike": b["buy_strike"], "side": "BUY", "lots": lots_buy},
                {"strike": b["sell_strike"], "side": "SELL", "lots": lots_buy * ratio}]

    # ---- unified event list: one "base" entry + N "avg" entries per base, chain frozen on zone exit ----
    # Each average ADDS (current running total + 1) more lots — e.g. base=1 lot (total 1); avg1 adds
    # 1+1=2 (total 3); avg2 adds 3+1=4 (total 7); avg3 adds 7+1=8 (total 15) — roughly doubling each
    # time. An event's own "lots_buy" is the size of THAT trade (the amount added), not the running
    # total; final position size is the sum across all of a base's events.
    events = []
    for b in bases:
        debit, buy_p, sell_p = debit_of_ts(b, lot_start, b["ts"])
        events.append({"type": "base", "base_id": b["base_id"], "ts": b["ts"], "date": b["date"],
                        "spot": b["spot"], "lots_buy": lot_start, "legs": LEGS(b, lot_start), "debit": debit,
                        "leg_premiums": (buy_p, sell_p), "value_now": value_of(b, lot_start, latest_day),
                        "pnl_now": value_of(b, lot_start, latest_day) - debit})

        next_threshold = b["spot"] - step
        running_total = lot_start
        n_avg_fired = 0
        for ts, spot in trigger_bars:
            if ts <= b["ts"]:
                continue
            if compute_base_raw(spot) != b["raw"]:
                break  # spot has left this base's own band — chain frozen for good
            if max_avg is not None and n_avg_fired >= max_avg:
                break  # base + max_avg adjustments reached — chain done
            if spot <= next_threshold:
                add_lots = running_total + 1
                running_total += add_lots
                n_avg_fired += 1
                debit, buy_p, sell_p = debit_of_ts(b, add_lots, ts)
                events.append({"type": "avg", "base_id": b["base_id"], "ts": ts, "date": ts.date(),
                                "spot": spot, "lots_buy": add_lots, "legs": LEGS(b, add_lots), "debit": debit,
                                "leg_premiums": (buy_p, sell_p), "value_now": value_of(b, add_lots, latest_day),
                                "pnl_now": value_of(b, add_lots, latest_day) - debit})
                next_threshold -= step

    events.sort(key=lambda e: e["ts"])
    for i, e in enumerate(events):
        e["idx"] = i

    base_by_id = {b["base_id"]: b for b in bases}
    for e in events:
        b = base_by_id[e["base_id"]]
        e["pnl_history"] = [{"date": d, "pnl": value_of(b, e["lots_buy"], d) - e["debit"]}
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
            b = base_by_id[e["base_id"]]
            value_d = value_of(b, e["lots_buy"], d)
            total += value_d - e["debit"]
            charges_total += e.get("charges_total", 0.0)
        daily_pnl_curve.append({"date": d, "spot": daily_close[d], "total_pnl": total,
                                 "n_open": n_open, "charges_to_date": charges_total,
                                 "total_pnl_net": total - charges_total})

    # ---- final net legs + margin (nothing exits) ----
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

    # ---- per-base summary ----
    base_summary = []
    for b in bases:
        b_events = [e for e in events if e["base_id"] == b["base_id"]]
        n_sets = len(b_events)
        total_debit = sum(e["debit"] for e in b_events)
        total_pnl = sum(e["pnl_now"] for e in b_events)
        total_charges = sum(e.get("charges_total", 0.0) for e in b_events)
        final_lots = b_events[-1]["lots_buy"]
        total_lots = sum(e["lots_buy"] for e in b_events)
        avg_price_buy = sum(e["leg_premiums"][0] * e["lots_buy"] for e in b_events) / total_lots
        avg_price_sell = sum(e["leg_premiums"][1] * e["lots_buy"] for e in b_events) / total_lots

        b_events_by_date = sorted(b_events, key=lambda e: e["date"])
        pnl_history = []
        for d in daily_dates:
            open_events = [e for e in b_events_by_date if e["date"] <= d]
            if not open_events:
                continue
            gross = sum(value_of(b, e["lots_buy"], d) - e["debit"] for e in open_events)
            charges_to_date = sum(e.get("charges_total", 0.0) for e in open_events)
            pnl_history.append({"date": d, "pnl": gross, "pnl_net": gross - charges_to_date, "n_open": len(open_events)})

        base_summary.append({
            "base_id": b["base_id"], "buy_strike": b["buy_strike"], "sell_strike": b["sell_strike"],
            "entry_ts": b["ts"], "entry_spot": b["spot"], "n_sets": n_sets, "final_lots_buy": final_lots,
            "avg_price_buy": avg_price_buy, "avg_price_sell": avg_price_sell,
            "total_debit": total_debit, "total_pnl": total_pnl, "total_charges": total_charges,
            "pnl_history": pnl_history,
        })

    return {
        "meta": {
            "lot_size": lot_size, "expiry": expiry.isoformat(), "from_date": from_date.isoformat(),
            "to_date": latest_day.isoformat(), "ratio": ratio, "step": step, "gap": gap,
            "base_min_gap": base_min_gap, "lot_start": lot_start, "max_avg": max_avg,
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
          f"(within-zone every {meta['step']}pt fall, add=(total+1) lots, capped at {meta['max_avg']}/base, "
          f"1:{meta['ratio']} ratio, {meta['gap']}pt gap)")
    print("=" * 100)
    for e in events:
        buy_leg, sell_leg = e["legs"]
        tag = f"base#{e['base_id']}" if e["type"] == "base" else f"avg->base#{e['base_id']}"
        charges_tag = f"  charges=Rs{e['charges_total']:,.0f}" if "charges_total" in e else ""
        print(f"  [{tag:12s}] {e['ts']}  spot={e['spot']:.2f}  "
              f"BUY {buy_leg['lots']}x {buy_leg['strike']}CE  SELL {sell_leg['lots']}x {sell_leg['strike']}CE  "
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
        buy_leg, sell_leg = e["legs"]
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
            "base_id": b["base_id"], "buy_strike": b["buy_strike"], "sell_strike": b["sell_strike"],
            "entry_ts": b["entry_ts"].isoformat(), "entry_spot": round(b["entry_spot"], 2),
            "n_sets": b["n_sets"], "final_lots_buy": b["final_lots_buy"],
            "avg_price_buy": round(b["avg_price_buy"], 2), "avg_price_sell": round(b["avg_price_sell"], 2),
            "total_debit": round(b["total_debit"], 2), "total_pnl": round(b["total_pnl"], 2),
            "total_charges": round(b["total_charges"], 2),
            "total_pnl_net": round(b["total_pnl"] - b["total_charges"], 2),
            "pnl_history": [{"date": p["date"].isoformat(), "pnl": round(p["pnl"], 2),
                              "pnl_net": round(p["pnl_net"], 2), "n_open": p["n_open"]} for p in b["pnl_history"]],
        } for b in result["base_summary"]],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from-date", type=date.fromisoformat, default=date(2026, 1, 1))
    p.add_argument("--to-date", type=date.fromisoformat, default=date.today())
    p.add_argument("--expiry", type=date.fromisoformat, default=date(2026, 12, 29))
    p.add_argument("--lot-size", type=int, default=65)
    p.add_argument("--ratio", type=int, default=2, help="Sell:buy lot ratio (default 2, i.e. 1:2).")
    p.add_argument("--step", type=int, default=200, help="Points of further within-zone fall that adds a new average.")
    p.add_argument("--gap", type=int, default=2000, help="Points between each base's buy and sell strike.")
    p.add_argument("--base-min-gap", type=int, default=800, help="Base strike must be at least this many points OTM.")
    p.add_argument("--lot-start", type=int, default=1, help="Lots bought at a base's entry (default 1).")
    p.add_argument("--max-avg", type=int, default=5,
                    help="Max averages per base (base + up to this many adjustments). 0 = unlimited (default 5).")
    p.add_argument("--allow-first-hourly-candle", action="store_true")
    p.add_argument("--no-charges", action="store_true")
    p.add_argument("--export-json", type=str, default=None)
    args = p.parse_args()

    result = run_backtest(
        from_date=args.from_date, to_date=args.to_date, expiry=args.expiry, lot_size=args.lot_size,
        ratio=args.ratio, step=args.step, gap=args.gap, base_min_gap=args.base_min_gap, lot_start=args.lot_start,
        max_avg=(args.max_avg or None),
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
