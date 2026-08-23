"""
NIFTY PE ratio ladder backtest — a third, separate strategy from the two
CE scripts, sharing only low-level plumbing (strike listing/pricing fetch,
charges, margin).

Strategy (as specified conversationally):

BASE (fires once, at the first trigger bar in the window)
    base_level = spot floored to the nearest --base-multiple, at least
    --base-min-gap points OTM (e.g. multiple=1000, min_gap=800, spot=26175
    -> floor((26175-800)/1000)*1000 = 25000; min_gap=0 reduces to a plain
    floor, e.g. spot=26175 -> 26000).
    BUY  --lots-buy lots @ base_level PE
    SELL --lots-buy * --ratio lots @ (base_level - --gap) PE
    e.g. defaults: BUY 5x 26000PE / SELL 10x 24000PE (1:2 ratio, 2000pt gap).

LADDER (fires once per --step points of further fall, chained, unbounded)
    Purely spot-level driven, monotonically downward only (no re-trigger on
    a rally back up, no upside layers) — the next threshold is always
    base_level - step, then -2*step, etc. Each crossing adds one more layer
    at strikes shifted down by that many steps, same gap as the base every
    time:
        layer i: BUY <lots> @ (base_level - i*step) PE
                 SELL <lots>*--ratio @ (base_level - i*step - gap) PE
    A big single-bar gap-down that skips multiple bands fires every
    intervening layer in order, not just the nearest one.

    Adjacent layers' strikes overlap when gap == step (layer i's sell
    strike == layer i+1's buy strike) — these net against each other in
    the final position, same as the CE ladder's overlapping bases.

LOT SIZING (--lot-mode)
    "constant" (default): every layer buys --lots-buy lots (the original
    behaviour of this script).
    "increment": layer i buys (--lots-buy + i) lots — 1, 2, 3, ... each
    new layer one lot bigger than the last. Sell lots are always
    buy_lots * --ratio, in either mode.

NO EXITS — nothing in this script closes. Every layer is held open to
--to-date and marked at the latest available premium.

Premiums are looked up on the SAME hourly grid as the spot trigger (falls
back to the daily series only if no hourly candle exists yet at that exact
point) — a daily-close-only premium would smear a fast intraday move into
one number per day and miss real intraday level crossings.

Usage:
    python analysis/nifty_pe_ratio_ladder_backtest.py --from-date 2025-12-01
    python analysis/nifty_pe_ratio_ladder_backtest.py --export-json /tmp/pe_ladder.json
"""
import argparse
import bisect
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from nifty_dec_ce_ladder_backtest import (
    make_strike_snapper, load_strike_to_ikey, fetch_hourly, fetch_daily,
)
from live.upstox_client import get_margin, get_brokerage
from config import UPSTOX_INSTRUMENT_KEYS


def run_backtest(
    from_date: date, to_date: date, expiry: date, lot_size: int,
    lots_buy: int = 5, ratio: int = 2, step: int = 1000, gap: int = 2000,
    base_multiple: int = 1000, base_min_gap: int = 0, lot_mode: str = "constant",
    skip_first_hourly_candle: bool = True, include_charges: bool = True,
):
    def lots_for_layer(layer_id):
        return lots_buy + layer_id if lot_mode == "increment" else lots_buy

    nifty_ikey = UPSTOX_INSTRUMENT_KEYS["NIFTY50"]
    bars = fetch_hourly(nifty_ikey, from_date, to_date)
    daily_close = fetch_daily(nifty_ikey, from_date, to_date)
    daily_dates = sorted(daily_close.keys())
    latest_day = daily_dates[-1]

    trigger_bars = [(ts, spot) for ts, spot in bars if not skip_first_hourly_candle or ts.hour != 9]
    if not trigger_bars:
        raise RuntimeError("No trigger bars in window")

    strike_to_ikey = load_strike_to_ikey(expiry, option_type="PE")
    snap_strike = make_strike_snapper(strike_to_ikey, from_date, to_date)

    # ---- layers: base at floor((spot0-min_gap)/multiple)*multiple, then one more every `step`
    # points of further fall ----
    first_ts, first_spot = trigger_bars[0]
    base_level = (int(first_spot) - base_min_gap) // base_multiple * base_multiple
    layers = [{"layer_id": 0, "ts": first_ts, "date": first_ts.date(), "spot": first_spot,
               "buy_raw": base_level, "sell_raw": base_level - gap}]
    next_threshold = base_level - step
    for ts, spot in trigger_bars[1:]:
        while spot <= next_threshold:
            layers.append({"layer_id": len(layers), "ts": ts, "date": ts.date(), "spot": spot,
                            "buy_raw": next_threshold, "sell_raw": next_threshold - gap})
            next_threshold -= step

    for lyr in layers:
        lyr["buy_strike"] = snap_strike(lyr["buy_raw"], lyr["date"])
        lyr["sell_strike"] = snap_strike(lyr["sell_raw"], lyr["date"])

    # ---- premium history: hourly (decision-grade) + daily (mark-to-market / fallback) ----
    needed_strikes = sorted({s for lyr in layers for s in (lyr["buy_strike"], lyr["sell_strike"])})
    missing = [s for s in needed_strikes if s not in strike_to_ikey]
    if missing:
        print(f"!! Strikes with no listed {expiry} PE contract: {missing}", file=sys.stderr)

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

    def debit_of_ts(lyr, target_ts):
        lb = lots_for_layer(lyr["layer_id"]); ls = lb * ratio
        buy_p = premium_on_or_before_hourly(lyr["buy_strike"], target_ts)
        sell_p = premium_on_or_before_hourly(lyr["sell_strike"], target_ts)
        return (buy_p * lb - sell_p * ls) * lot_size, buy_p, sell_p

    def value_of(lyr, target_date):
        lb = lots_for_layer(lyr["layer_id"]); ls = lb * ratio
        buy_p = premium_on_or_before(lyr["buy_strike"], target_date)
        sell_p = premium_on_or_before(lyr["sell_strike"], target_date)
        return (buy_p * lb - sell_p * ls) * lot_size

    def LEGS(lyr):
        lb = lots_for_layer(lyr["layer_id"]); ls = lb * ratio
        return [{"strike": lyr["buy_strike"], "side": "BUY", "lots": lb},
                {"strike": lyr["sell_strike"], "side": "SELL", "lots": ls}]

    for lyr in layers:
        debit, buy_p, sell_p = debit_of_ts(lyr, lyr["ts"])
        lyr["legs"] = LEGS(lyr)
        lyr["debit"] = debit
        lyr["leg_premiums"] = (buy_p, sell_p)
        lyr["value_now"] = value_of(lyr, latest_day)
        lyr["pnl_now"] = lyr["value_now"] - debit

    # ---- real per-leg charges at entry ----
    if include_charges:
        for lyr in layers:
            leg_charges = []
            total_charges = 0.0
            for leg in lyr["legs"]:
                ikey = strike_to_ikey.get(leg["strike"])
                entry_prem = premium_on_or_before_hourly(leg["strike"], lyr["ts"])
                if not ikey or entry_prem is None:
                    leg_charges.append(None)
                    continue
                try:
                    c = get_brokerage(ikey, leg["lots"] * lot_size, leg["side"], entry_prem, product="D")
                except Exception as ex:
                    print(f"  [charges] failed for {leg['side']} {leg['strike']}PE @ {lyr['ts']}: {ex}", file=sys.stderr)
                    leg_charges.append(None)
                    continue
                leg_charges.append(c)
                total_charges += c["total"]
            lyr["leg_charges"] = leg_charges
            lyr["charges_total"] = total_charges

    # ---- per-layer P&L-over-time ----
    for lyr in layers:
        lyr["pnl_history"] = [{"date": d, "pnl": value_of(lyr, d) - lyr["debit"]}
                               for d in daily_dates if d >= lyr["date"]]

    # ---- daily total PnL curve ----
    daily_pnl_curve = []
    for d in daily_dates:
        total = charges_total = 0.0
        n_open = 0
        for lyr in layers:
            if lyr["date"] > d:
                continue
            n_open += 1
            total += value_of(lyr, d) - lyr["debit"]
            charges_total += lyr.get("charges_total", 0.0)
        daily_pnl_curve.append({"date": d, "spot": daily_close[d], "total_pnl": total,
                                 "n_open": n_open, "charges_to_date": charges_total,
                                 "total_pnl_net": total - charges_total})

    # ---- final net legs + margin (nothing exits) ----
    net_lots = {}
    for lyr in layers:
        for l in lyr["legs"]:
            sign = 1 if l["side"] == "BUY" else -1
            net_lots[l["strike"]] = net_lots.get(l["strike"], 0) + sign * l["lots"]

    final_legs = []
    margin_legs = []
    for strike in sorted(net_lots, reverse=True):
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
            "to_date": latest_day.isoformat(), "lots_buy": lots_buy, "ratio": ratio, "step": step, "gap": gap,
            "base_multiple": base_multiple, "base_min_gap": base_min_gap, "lot_mode": lot_mode,
            "skip_first_hourly_candle": skip_first_hourly_candle,
            "n_layers": len(layers), "include_charges": include_charges,
        },
        "bars": bars, "daily_close": daily_close, "layers": layers,
        "daily_pnl_curve": daily_pnl_curve, "final_legs": final_legs, "margin": margin_result,
    }


def print_report(result: dict):
    layers, meta = result["layers"], result["meta"]
    lot_desc = (f"lots {meta['lots_buy']}+1 per layer" if meta.get('lot_mode') == 'increment'
                else f"{meta['lots_buy']}:{meta['lots_buy']*meta['ratio']} ratio")
    print(f"\nLayers: {meta['n_layers']}   (base + every {meta['step']}pt further fall, "
          f"{lot_desc}, {meta['gap']}pt gap)")
    print("=" * 100)
    for lyr in layers:
        buy_leg, sell_leg = lyr["legs"]
        charges_tag = f"  charges=Rs{lyr['charges_total']:,.0f}" if "charges_total" in lyr else ""
        tag = f"layer#{lyr['layer_id']}"
        print(f"  [{tag:9s}] {lyr['ts']}  spot={lyr['spot']:.2f}  "
              f"BUY {buy_leg['lots']}x {buy_leg['strike']}PE  SELL {sell_leg['lots']}x {sell_leg['strike']}PE  "
              f"debit=Rs{lyr['debit']:,.0f}  pnl=Rs{lyr['pnl_now']:+,.0f}{charges_tag}")
    print("=" * 100)
    total_debit = sum(lyr["debit"] for lyr in layers)
    total_pnl = sum(lyr["pnl_now"] for lyr in layers)
    print(f"COMBINED        : debit=Rs{total_debit:,.0f}   pnl=Rs{total_pnl:+,.0f}")
    if any("charges_total" in lyr for lyr in layers):
        total_charges = sum(lyr.get("charges_total", 0) for lyr in layers)
        print(f"Total charges (brokerage+STT+exchange+GST+stamp duty, entry legs only): Rs{total_charges:,.0f}")
        print(f"COMBINED, net of charges: pnl=Rs{total_pnl-total_charges:+,.0f}")
    print("=" * 100)
    print("\nFinal net legs:")
    for l in result["final_legs"]:
        print(f"  {l['side']:4s} {abs(l['lots'])} lot(s)  {l['strike']} PE  @ {l['ltp']:.2f}")
    if result["margin"]:
        print(f"\nRequired margin: Rs {result['margin']['required_margin']:,.0f}")
        print(f"Final margin   : Rs {result['margin']['final_margin']:,.0f}")


def to_json_payload(result: dict) -> dict:
    def lyr_json(lyr):
        d = {"layer_id": lyr["layer_id"], "ts": lyr["ts"].isoformat(), "date": lyr["date"].isoformat(),
             "spot": round(lyr["spot"], 2), "legs": lyr["legs"], "debit": round(lyr["debit"], 2),
             "pnl_now": round(lyr["pnl_now"], 2),
             "leg_premiums": [round(p, 2) for p in lyr["leg_premiums"]]}
        charges = lyr.get("charges_total", 0.0)
        if "charges_total" in lyr:
            d["charges_total"] = round(charges, 2)
            d["leg_charges"] = [({k: round(v, 2) for k, v in c.items()} if c else None) for c in lyr["leg_charges"]]
            d["pnl_net_of_charges"] = round(lyr["pnl_now"] - charges, 2)
        d["pnl_history"] = [{"date": p["date"].isoformat(), "pnl": round(p["pnl"], 2),
                              "pnl_net": round(p["pnl"] - charges, 2)} for p in lyr["pnl_history"]]
        return d

    layers_json = [lyr_json(lyr) for lyr in result["layers"]]
    totals = {
        "combined_debit": round(sum(lyr["debit"] for lyr in result["layers"]), 2),
        "combined_pnl": round(sum(lyr["pnl_now"] for lyr in result["layers"]), 2),
    }
    if result["meta"]["include_charges"]:
        totals["total_charges"] = round(sum(lyr.get("charges_total", 0) for lyr in result["layers"]), 2)
        totals["combined_pnl_net_of_charges"] = round(totals["combined_pnl"] - totals["total_charges"], 2)

    return {
        "meta": result["meta"],
        "hourly_spot": [[ts.isoformat(), round(c, 2)] for ts, c in result["bars"]],
        "layers": layers_json,
        "daily_pnl_curve": [{"date": r["date"].isoformat(), "spot": round(r["spot"], 2),
                              "total_pnl": round(r["total_pnl"], 2), "n_open": r["n_open"],
                              "charges_to_date": round(r.get("charges_to_date", 0), 2),
                              "total_pnl_net": round(r.get("total_pnl_net", r["total_pnl"]), 2)}
                             for r in result["daily_pnl_curve"]],
        "final_legs": result["final_legs"],
        "margin": result["margin"],
        "totals": totals,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from-date", type=date.fromisoformat, default=date(2025, 12, 1))
    p.add_argument("--to-date", type=date.fromisoformat, default=date.today())
    p.add_argument("--expiry", type=date.fromisoformat, default=date(2026, 12, 29))
    p.add_argument("--lot-size", type=int, default=65)
    p.add_argument("--lots-buy", type=int, default=5,
                    help="Lots bought at layer 0 (default 5). In --lot-mode increment, later layers add 1 each.")
    p.add_argument("--ratio", type=int, default=2, help="Sell:buy lot ratio (default 2, i.e. 1:2).")
    p.add_argument("--step", type=int, default=1000, help="Points of further fall that adds a new layer.")
    p.add_argument("--gap", type=int, default=2000, help="Points between each layer's buy and sell strike.")
    p.add_argument("--base-multiple", type=int, default=1000, help="Base strike is floored to this multiple.")
    p.add_argument("--base-min-gap", type=int, default=0,
                    help="Base strike must be at least this many points OTM (0 = plain floor, no buffer).")
    p.add_argument("--lot-mode", choices=["constant", "increment"], default="constant",
                    help="constant: every layer buys --lots-buy lots. increment: layer i buys --lots-buy+i lots.")
    p.add_argument("--allow-first-hourly-candle", action="store_true")
    p.add_argument("--no-charges", action="store_true")
    p.add_argument("--export-json", type=str, default=None)
    args = p.parse_args()

    result = run_backtest(
        from_date=args.from_date, to_date=args.to_date, expiry=args.expiry, lot_size=args.lot_size,
        lots_buy=args.lots_buy, ratio=args.ratio, step=args.step, gap=args.gap,
        base_multiple=args.base_multiple, base_min_gap=args.base_min_gap, lot_mode=args.lot_mode,
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
