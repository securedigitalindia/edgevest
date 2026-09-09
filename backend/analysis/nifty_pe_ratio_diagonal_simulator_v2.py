"""
NIFTY PE ratio diagonal spread — entry-date position tracker (v2), sourced
entirely from Upstox's History API. No local DB involved for price data.

2026-09-08: rebuilt for the 4-leg/3-expiry strategy shape (see
nifty_pe_ratio_diagonal_simulator.py's docstring) and for a different job —
the old v2 explored an arbitrary --from-date/--as-of replay *window* against
one fixed (current, next) expiry pair. This version instead answers "I
opened this position on entry-date, what does it look like now?": the strike
and expiry triplet are resolved ONCE, at entry (09:30 IST that day, mirroring
v1's live execution rule), and then tracked tick-by-tick from entry through
the latest available data — the old exploratory window is gone since there's
only ever one real entry to track.

Expiry-triplet resolution still reads the merged expiry-date LIST from the
local DB (db.queries.get_merged_cadence_dates) — not for price data, just for
which expiry dates have ever existed. Upstox's live expiry search only
returns currently-active contracts, so an already-expired weekly silently
disappears from it, which would break resolving a triplet anchored to a past
entry-date. The DB's capture history still remembers it even though its own
5-min price captures have gaps. Never trust the raw bucket/rank column
alone, see the calendar-spread-debit-proxy skill for why.

Per-leg prices come from Upstox's History API, called once per leg
instrument for the whole [entry-date, today] span (historical candles up to
yesterday, merged with today's intraday candles when the market has opened
today) — same technique the old v2 used, just per-leg instrument instead of
a bulk chain pull.

Usage:
    cd backend && source venv/bin/activate
    python analysis/nifty_pe_ratio_diagonal_simulator_v2.py --entry-date 2026-09-01
    python analysis/nifty_pe_ratio_diagonal_simulator_v2.py --entry-date 2026-09-01 \
        --export-json /tmp/pe_ratio_sim_v2.json
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from live.holidays import is_trading_day
from db.queries import get_merged_cadence_dates
from nifty_pe_ratio_diagonal_simulator import resolve_expiry_triplet, floor_strike_100
from nifty_fut_ref import (
    resolve_front_month_future, fetch_candles_utc, fetch_intraday_candles_utc,
    nearest_price, resolve_pe_instrument_keys, resolve_reference_trading_day, IST,
)

SYMBOL = "NIFTY50"
ENTRY_TIME = time(9, 30)


def history_upper_bound(reference_day: date) -> date:
    """
    Upstox's history endpoint has no same-day data — if reference_day is
    today (market currently in session), cap the historical pull at the
    previous trading day instead.
    """
    today_ist = datetime.now(timezone.utc).astimezone(IST).date()
    if reference_day < today_ist:
        return reference_day
    d = today_ist - timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def ist_ts_for(day: str, t: time) -> str:
    """IST wall-clock day+time -> the UTC 'YYYY-MM-DDTHH:MM:SSZ' candle-key format."""
    dt_ist = datetime.combine(date.fromisoformat(day), t, tzinfo=IST)
    return dt_ist.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def full_series(ikey: str, entry_date: str, hist_to: str, include_today: bool) -> dict:
    """Historical candles [entry_date, hist_to] merged with today's intraday candles, if applicable."""
    series = fetch_candles_utc(ikey, entry_date, hist_to) if entry_date <= hist_to else {}
    if include_today:
        series = {**series, **fetch_intraday_candles_utc(ikey)}
    return series


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entry-date", required=True,
                     help="day the position is (or would be) opened, e.g. 2026-09-01")
    ap.add_argument("--k-strike", type=float, default=None,
                     help="override; default: entry-day 09:30 IST fut price floored to nearest 100")
    ap.add_argument("--leg-gap", type=float, default=400)
    ap.add_argument("--lot-size", type=int, default=None,
                     help="default: resolved live from the futures contract")
    ap.add_argument("--symbol", default=SYMBOL)
    ap.add_argument("--export-json", default=None)
    args = ap.parse_args()

    entry_date = args.entry_date
    if not is_trading_day(date.fromisoformat(entry_date)):
        print(f"{entry_date} is not a trading day — aborting.")
        sys.exit(1)

    merged = get_merged_cadence_dates(args.symbol, include_quarterly=True)
    if len(merged) < 4:
        print(f"Not enough expiry history in option_chain_5m to resolve a 3-expiry triplet: {merged}")
        sys.exit(1)

    try:
        expiry1, expiry2, expiry3 = resolve_expiry_triplet(entry_date, merged)
    except ValueError as e:
        print(f"{e} — aborting.")
        sys.exit(1)

    reference_day = resolve_reference_trading_day()
    today_ist = datetime.now(timezone.utc).astimezone(IST).date()
    hist_to = history_upper_bound(reference_day).isoformat()
    include_today = reference_day == today_ist

    fut = resolve_front_month_future("NIFTY")
    lot_size = args.lot_size or fut["lot_size"]

    # --- entry fut price at 09:30 IST on entry_date ---
    entry_is_today = entry_date == today_ist.isoformat()
    fut_entry_lookup = (
        fetch_intraday_candles_utc(fut["instrument_key"]) if entry_is_today
        else fetch_candles_utc(fut["instrument_key"], entry_date, entry_date)
    )
    if not fut_entry_lookup:
        print(f"No futures candle data on entry_date={entry_date} — aborting.")
        sys.exit(1)
    entry_target_ts = ist_ts_for(entry_date, ENTRY_TIME)
    entry_fut_price = nearest_price(fut_entry_lookup, entry_target_ts)

    k_strike = args.k_strike if args.k_strike is not None else floor_strike_100(entry_fut_price)
    k2_strike = k_strike - args.leg_gap
    name = f"{int(k_strike)}/{int(k2_strike)}"

    print(f"Entry date={entry_date}  09:30 fut={entry_fut_price}  -> k_strike={int(k_strike)}  k2_strike={int(k2_strike)}")
    print(f"Expiry triplet (resolved as of entry): expiry1={expiry1}  expiry2={expiry2}  expiry3={expiry3}")
    print(f"Futures reference: {fut['trading_symbol']}  lot_size={lot_size}")

    # --- resolve instrument keys per expiry, only the strikes actually needed ---
    e1_ikeys = resolve_pe_instrument_keys(args.symbol, expiry1, {k_strike})
    e2_ikeys = resolve_pe_instrument_keys(args.symbol, expiry2, {k_strike, k2_strike})
    e3_ikeys = resolve_pe_instrument_keys(args.symbol, expiry3, {k2_strike})

    missing = []
    if k_strike not in e1_ikeys:
        missing.append((expiry1, k_strike))
    if k_strike not in e2_ikeys:
        missing.append((expiry2, k_strike))
    if k2_strike not in e2_ikeys:
        missing.append((expiry2, k2_strike))
    if k2_strike not in e3_ikeys:
        missing.append((expiry3, k2_strike))
    if missing:
        print(f"No contract found for strike/expiry pair(s): {missing} — aborting.")
        sys.exit(1)

    # --- fetch full historical + intraday-today candle series for each leg instrument ---
    l1_series = full_series(e1_ikeys[k_strike], entry_date, hist_to, include_today)
    l2_series = full_series(e2_ikeys[k2_strike], entry_date, hist_to, include_today)
    l3_series = full_series(e2_ikeys[k_strike], entry_date, hist_to, include_today)
    l4_series = full_series(e3_ikeys[k2_strike], entry_date, hist_to, include_today)
    fut_series = full_series(fut["instrument_key"], entry_date, hist_to, include_today)

    common_ts = sorted(
        set(l1_series) & set(l2_series) & set(l3_series) & set(l4_series) & set(fut_series)
    )
    common_ts = [ts for ts in common_ts if ts >= entry_target_ts]
    if not common_ts:
        print("No overlapping tick data across all 4 legs + futures from entry onward — aborting.")
        sys.exit(1)

    points = []
    entry_value = None
    for ts in common_ts:
        l1, l2, l3, l4 = l1_series[ts], l2_series[ts], l3_series[ts], l4_series[ts]
        value = l1 - 2 * l2 - l3 + 2 * l4
        if entry_value is None:
            entry_value = value
        points.append({
            "ts": ts, "day": ts[:10], "fut": fut_series[ts],
            "leg1_ltp": l1, "leg2_ltp": l2, "leg3_ltp": l3, "leg4_ltp": l4,
            "value": round(value, 2),
            "pnl_pts": round(value - entry_value, 2),
            "pnl_rs": round((value - entry_value) * lot_size, 2),
        })

    days = sorted({p["day"] for p in points})
    daily = []
    for d in days:
        day_points = [p for p in points if p["day"] == d]
        daily.append({
            "day": d,
            "dte_expiry1": (date.fromisoformat(expiry1) - date.fromisoformat(d)).days,
            "open_value": day_points[0]["value"], "close_value": day_points[-1]["value"],
            "close_pnl_pts": day_points[-1]["pnl_pts"], "close_pnl_rs": day_points[-1]["pnl_rs"],
        })

    print(f"\nTracking {name}: BUY 1x {int(k_strike)}PE({expiry1}) / SELL 2x {int(k2_strike)}PE({expiry2}) "
          f"/ SELL 1x {int(k_strike)}PE({expiry2}) / BUY 2x {int(k2_strike)}PE({expiry3})")
    print(f"Entry {points[0]['ts']}  value={entry_value:.2f}  "
          f"({'credit' if entry_value < 0 else 'debit'} to open)")
    print(f"through {points[-1]['ts']}, across {len(days)} trading day(s):\n")
    print(f"{'day':<12} {'DTE(e1)':>8} {'open':>9} {'close':>9} {'pnl_pts':>9} {'pnl_rs':>10}")
    for row in daily:
        print(f"{row['day']:<12} {row['dte_expiry1']:>8} {row['open_value']:>9.2f} {row['close_value']:>9.2f} "
              f"{row['close_pnl_pts']:>+9.2f} {row['close_pnl_rs']:>+10.2f}")

    latest = points[-1]
    print(f"\nLatest: {latest['ts']}  value={latest['value']:.2f}  "
          f"pnl_pts={latest['pnl_pts']:+.2f}  pnl_rs={latest['pnl_rs']:+.2f}")

    if args.export_json:
        with open(args.export_json, "w") as f:
            json.dump({
                "symbol": args.symbol, "entry_date": entry_date, "entry_ts": points[0]["ts"],
                "k_strike": k_strike, "k2_strike": k2_strike, "leg_gap": args.leg_gap,
                "expiry1": expiry1, "expiry2": expiry2, "expiry3": expiry3,
                "lot_size": lot_size, "fut_trading_symbol": fut["trading_symbol"],
                "entry_value": entry_value, "points": points, "daily": daily,
            }, f, indent=2)
        print(f"\nExported to {args.export_json}")


if __name__ == "__main__":
    main()
