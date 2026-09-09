"""
NIFTY PE ratio diagonal — averaging/laddered-entry backtest.

Extends the single-entry backtest (nifty_pe_ratio_diagonal_backtest.py) with
a scale-in trigger: starting from --entry-date's 09:30 IST entry, every time
the NIFTY future rises another --up-move points from the LAST triggered
entry's own fut price, a brand-new 4-leg set is entered — fresh expiry
triplet resolved at THAT trigger's own date (per user decision: not the
first entry's triplet reused), fresh K/K2 from THAT trigger's own fut
price. Uncapped — fires as many times as the future keeps climbing within
the tracked window. Every leg of every set is sourced primarily from local
option_chain_5m, same as the single-entry backtest, with the same
2026-09-09 live-Upstox-backfill fallback for a leg whose expiry our own
rank-window capture started tracking later than its trigger date (only
works pre-settlement — see nifty_pe_ratio_diagonal_backtest.py's docstring
for the bug this fixes).

Combined P&L at any tick = sum of every already-triggered set's own P&L
since its own entry. Once a set's own leg1 expiry settles (its data
naturally stops — an expired option's chain disappears, same limit as
everywhere else in this project), that set's contribution FREEZES at its
last known value rather than vanishing from the sum — a settled leg's
already-realized P&L doesn't disappear just because our data stops there.

Usage:
    cd backend && source venv/bin/activate
    FLASK_ENV=dev python analysis/nifty_pe_ratio_diagonal_averaging_backtest.py \
        --entry-date 2026-08-25 --up-move 100
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from live.holidays import is_trading_day
from live.expiry import expiry_cache
from db.queries import get_merged_cadence_dates
from db.init_db import get_connection
from nifty_pe_ratio_diagonal_simulator import resolve_expiry_triplet, floor_strike_100, ceil_strike_100
from nifty_pe_ratio_diagonal_backtest import chain_series, ist_ts_for
from nifty_fut_ref import resolve_front_month_future, fetch_candles_utc

SYMBOL = "NIFTY50"
ENTRY_TIME = time(9, 30)

# side="PE" (default): K floored (keeps the bought leg OTM, put OTM when strike<spot),
# K2=K-gap (further OTM downward, since puts gain on downside), triggers fire on up-moves
# (mechanical rule, unrelated to which direction favors the position).
# side="CE": mirrored — K ceiled (call OTM when strike>spot), K2=K+gap (further OTM
# upward, since calls gain on upside), triggers fire on DOWN-moves per user's explicit
# choice to mirror the trigger direction along with everything else, 2026-09-09.
SIDE_CONFIG = {
    "PE": {"opt_type": "PE", "strike_fn": floor_strike_100, "gap_sign": -1, "trigger_dir": +1},
    "CE": {"opt_type": "CE", "strike_fn": ceil_strike_100, "gap_sign": +1, "trigger_dir": -1},
}


def _priced_leg(conn, expiry_date: str, strike: float, opt_type: str, symbol: str,
                 trigger_ts: str) -> tuple[dict | None, float | None]:
    """
    2026-09-09: the nominal strike can be genuinely illiquid (real trades
    confirmed missing for DAYS on a far-OTM CE leg — see chain_series's
    zero-LTP fix) while the neighboring 100-pt strike is trading normally.
    Try the nominal strike first, then -100, then +100 (per user decision:
    exactly those three, no wider search) and use whichever has a real
    price SOMEWHERE on trigger_ts's own calendar day — a single missed
    5-min poll (e.g. right at 09:15 IST market open, confirmed to happen)
    still resolves within minutes on the same day and must not fail the
    whole set; only a genuine multi-day silence (nothing all day) counts
    as "not usable" and falls through to the next candidate. Returns
    (series, strike_used), or (None, None) if none of the three works —
    the caller fails the set rather than guessing further.
    """
    trigger_day = trigger_ts[:10]
    for candidate in (strike, strike - 100, strike + 100):
        series = chain_series(conn, expiry_date, candidate, opt_type, symbol, backfill_from_ts=trigger_ts)
        if any(ts >= trigger_ts and ts[:10] == trigger_day for ts in series):
            return series, candidate
    return None, None


def build_set(conn, trigger_ts: str, fut_price: float, merged: list[str],
              leg_gap: float, symbol: str, side: str = "PE",
              expiry_triplet: tuple[str, str, str] | None = None,
              strike_multiple: float = 100, initial_gap: float = 0) -> dict:
    """
    One triggered 4-leg set: K/K2 at trigger_ts's own date. Expiry triplet is
    fresh-resolved at trigger_ts's own date by default (this script's own
    standalone/non-windowed use) — but a caller that needs to lock every set
    in a group to one shared triplet (the windowed backtest, whose own
    windows are DEFINED by expiry-triplet boundaries) can pass expiry_triplet
    explicitly to skip that per-trigger resolution.

    strike_multiple (2026-09-09): the K-strike rounding step (floor for PE,
    ceil for CE) — defaults to 100, NIFTY's real strike spacing, but is a
    real config knob on the admin strategy dashboard now (leg_gap's sibling
    under "Strategy" params — see backend/strategies/registry.py).

    initial_gap (2026-09-09, user-specified sign convention): shifts the
    reference price BEFORE the strike_multiple rounding, using the same
    signed gap_sign convention SIDE_CONFIG already uses for K2 — so
    initial_gap=0 (default) reproduces the old "just round to the nearest
    multiple" behavior exactly; a positive initial_gap pushes K further OTM
    (PE: floor(fut - gap); CE: ceil(fut + gap)); a negative initial_gap
    pushes K toward/into ITM (PE: floor(fut + |gap|); CE: ceil(fut - |gap|)).
    Only affects K (leg 1/3's shared strike) — K2 is still K + gap_sign*leg_gap,
    computed from the already-shifted K, same as before.
    """
    cfg = SIDE_CONFIG[side]
    trigger_date = trigger_ts[:10]
    if expiry_triplet is not None:
        expiry1, expiry2, expiry3 = expiry_triplet
    else:
        try:
            expiry1, expiry2, expiry3 = resolve_expiry_triplet(trigger_date, merged)
        except ValueError as e:
            return {"trigger_ts": trigger_ts, "trigger_fut": fut_price, "error": str(e)}

    k_strike = cfg["strike_fn"](fut_price + cfg["gap_sign"] * initial_gap, strike_multiple)
    k2_strike = k_strike + cfg["gap_sign"] * leg_gap

    (l1, l1_strike), (l2, l2_strike), (l3, l3_strike), (l4, l4_strike) = (
        _priced_leg(conn, expiry1, k_strike, cfg["opt_type"], symbol, trigger_ts),
        _priced_leg(conn, expiry2, k2_strike, cfg["opt_type"], symbol, trigger_ts),
        _priced_leg(conn, expiry2, k_strike, cfg["opt_type"], symbol, trigger_ts),
        _priced_leg(conn, expiry3, k2_strike, cfg["opt_type"], symbol, trigger_ts),
    )

    meta = {
        "trigger_ts": trigger_ts, "trigger_fut": fut_price, "side": side,
        "k_strike": k_strike, "k2_strike": k2_strike,
        "expiry1": expiry1, "expiry2": expiry2, "expiry3": expiry3,
    }

    if None in (l1, l2, l3, l4):
        meta["error"] = "no tradeable strike (nominal or ±100) found for one or more legs from trigger onward"
        return meta

    leg_strikes_used = {"l1": l1_strike, "l2": l2_strike, "l3": l3_strike, "l4": l4_strike}
    nominal = {"l1": k_strike, "l2": k2_strike, "l3": k_strike, "l4": k2_strike}
    overrides = {leg: used for leg, used in leg_strikes_used.items() if used != nominal[leg]}
    if overrides:
        meta["strike_overrides"] = overrides

    common_ts = sorted(set(l1) & set(l2) & set(l3) & set(l4))
    common_ts = [ts for ts in common_ts
                 if ts >= trigger_ts and is_trading_day(date.fromisoformat(ts[:10]))]
    if not common_ts:
        meta["error"] = "no local chain data for this set from its trigger onward"
        return meta

    values = {ts: round(l1[ts] - 2 * l2[ts] - l3[ts] + 2 * l4[ts], 2) for ts in common_ts}
    meta.update({
        "trigger_ts": common_ts[0], "entry_value": values[common_ts[0]],
        "last_ts": common_ts[-1], "values": values, "n_ticks": len(values),
    })
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entry-date", required=True, help="first trigger's entry date, e.g. 2026-08-25")
    ap.add_argument("--up-move", type=float, default=100,
                     help="fut points move from the last trigger to fire the next (direction depends on --side: "
                          "up for PE, down for CE)")
    ap.add_argument("--leg-gap", type=float, default=400)
    ap.add_argument("--strike-multiple", type=float, default=100,
                     help="K-strike rounding step (floor for PE, ceil for CE) — defaults to 100, NIFTY's real strike spacing")
    ap.add_argument("--initial-gap", type=float, default=0,
                     help="shift K before rounding — positive pushes further OTM, negative toward/into ITM "
                          "(sign auto-flips PE vs CE, same convention as leg_gap)")
    ap.add_argument("--side", choices=["PE", "CE"], default="PE")
    ap.add_argument("--symbol", default=SYMBOL)
    ap.add_argument("--export-json", default=None)
    args = ap.parse_args()

    trigger_dir = SIDE_CONFIG[args.side]["trigger_dir"]

    if not is_trading_day(date.fromisoformat(args.entry_date)):
        print(f"{args.entry_date} is not a trading day — aborting.")
        sys.exit(1)

    expiry_cache.refresh([args.symbol])  # so chain_series's backfill-type resolution has data to scan

    merged = get_merged_cadence_dates(args.symbol, include_quarterly=True)
    if len(merged) < 3:
        print(f"Not enough expiry history in option_chain_5m: {merged}")
        sys.exit(1)

    fut = resolve_front_month_future("NIFTY")
    conn = get_connection()

    cur = conn.execute("SELECT MAX(ts) FROM option_chain_5m")
    chain_max_ts = cur.fetchone()[0]
    chain_max_date = chain_max_ts[:10] if chain_max_ts else args.entry_date

    pad_from = (date.fromisoformat(args.entry_date) - timedelta(days=1)).isoformat()
    fut_series = fetch_candles_utc(fut["instrument_key"], pad_from, chain_max_date)
    if not fut_series:
        print(f"No futures history for {fut['trading_symbol']} — aborting.")
        sys.exit(1)

    entry_target_ts = ist_ts_for(args.entry_date, ENTRY_TIME)
    all_ts = sorted(t for t in fut_series
                     if t >= entry_target_ts and is_trading_day(date.fromisoformat(t[:10])))
    if not all_ts:
        print("No futures ticks from entry onward — aborting.")
        sys.exit(1)

    # --- find every trigger point: first entry, then every +up_move from the LAST trigger ---
    trigger_points = [(all_ts[0], fut_series[all_ts[0]])]
    last_trigger_fut = fut_series[all_ts[0]]
    for ts in all_ts[1:]:
        f = fut_series[ts]
        if (f - last_trigger_fut) * trigger_dir >= args.up_move:
            trigger_points.append((ts, f))
            last_trigger_fut = f

    print(f"Entry {args.entry_date} 09:30 IST, side={args.side}, "
          f"trigger={'up' if trigger_dir > 0 else 'down'}-move {args.up_move}: "
          f"{len(trigger_points)} trigger(s) fired\n")

    sets = []
    for ts, f in trigger_points:
        s = build_set(conn, ts, f, merged, args.leg_gap, args.symbol, side=args.side,
                      strike_multiple=args.strike_multiple, initial_gap=args.initial_gap)
        sets.append(s)
        if "values" not in s:
            print(f"  SET @ {ts}  fut={f:.1f}: FAILED — {s['error']}")
        else:
            print(f"  SET @ {s['trigger_ts']}  fut={f:.1f}: K={s['k_strike']:.0f}/{s['k2_strike']:.0f}  "
                  f"expiries={s['expiry1']}/{s['expiry2']}/{s['expiry3']}  "
                  f"entry_value={s['entry_value']:.2f}  ({s['n_ticks']} ticks, through {s['last_ts']})")
    conn.close()

    ok_sets = [s for s in sets if "values" in s]
    if not ok_sets:
        print("\nNo usable sets — aborting.")
        sys.exit(1)

    # --- combined series: sum of each active set's own pnl since its own entry;
    #     once a set's data ends (its expiry1 settled), freeze its contribution
    #     at the last known value instead of dropping it from the sum. ---
    combined_ts = sorted(set().union(*[s["values"].keys() for s in ok_sets]))
    last_pnl_cache = {id(s): 0.0 for s in ok_sets}
    combined_points = []
    for ts in combined_ts:
        total_pnl = 0.0
        active_count = 0
        for s in ok_sets:
            if ts < s["trigger_ts"]:
                continue
            active_count += 1
            if ts in s["values"]:
                last_pnl_cache[id(s)] = round(s["values"][ts] - s["entry_value"], 2)
            total_pnl += last_pnl_cache[id(s)]
        combined_points.append({
            "ts": ts, "pnl_pts": round(total_pnl, 2), "active_sets": active_count,
        })

    lot_size = fut["lot_size"]
    print(f"\nCombined across {len(ok_sets)} set(s), {len(combined_points)} tick(s):")
    last = combined_points[-1]
    print(f"  final @ {last['ts']}: pnl_pts={last['pnl_pts']:+.2f}  "
          f"pnl_rs={last['pnl_pts'] * lot_size:+.2f}  active_sets={last['active_sets']}")

    if args.export_json:
        with open(args.export_json, "w") as f:
            json.dump({
                "entry_date": args.entry_date, "up_move": args.up_move, "leg_gap": args.leg_gap,
                "side": args.side, "fut_trading_symbol": fut["trading_symbol"], "lot_size": lot_size,
                "sets": sets, "combined": combined_points,
            }, f, indent=2)
        print(f"Exported to {args.export_json}")


if __name__ == "__main__":
    main()
