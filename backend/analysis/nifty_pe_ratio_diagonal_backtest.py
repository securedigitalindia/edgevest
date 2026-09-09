"""
NIFTY PE ratio diagonal — multi-entry-date backtest from local option_chain_5m.

Runs the 4-leg diagonal construction (docs/prd/pe-ratio-diagonal-strategy.md)
across every valid trading day in [--from-date, --to-date] as an entry-date,
sourcing every leg's premium primarily from the locally captured
option_chain_5m table instead of Upstox's per-instrument History API. This
is what makes backtesting an already-settled expiry cycle possible at all:
Upstox itself can no longer resolve instrument_keys or price history for a
settled expiry (confirmed empirically — see
docs/prd/pe-ratio-diagonal-strategy.md), but the raw chain was captured into
option_chain_5m before it settled.

2026-09-09 correctness fix: local option_chain_5m is captured with a
rank-window (weekly ranks 0-2) — a far expiry can exist and be live-priced
on Upstox well before our own local capture happens to start tracking it
(confirmed: the 2026-09-22 contract has real Upstox history from 2026-08-28,
but local capture didn't pick it up until 2026-09-02, since it only entered
the rank-2 window then). Treating "no local rows yet" as "no data" silently
shifted an entry's whole start forward and understated its true debit by
more than 2x in one observed case (Aug 31 entry: reported 51.25, true value
22.95). `chain_series` now falls back to a live Upstox pull to backfill
that gap whenever local coverage doesn't reach back to the requested start
— this only works for an expiry that hasn't settled yet; once settled, the
live fallback fails silently and local-only data is genuinely the ceiling
(the original, unavoidable limit this script was built to work around).

Each entry-date resolves its own K/expiry-triplet independently, same rule
as v1/v2 (nifty_pe_ratio_diagonal_simulator.py's resolve_expiry_triplet /
floor_strike_100) — this script reuses those, not a re-implementation.

Usage:
    cd backend && source venv/bin/activate
    FLASK_ENV=dev python analysis/nifty_pe_ratio_diagonal_backtest.py \
        --from-date 2026-08-25 --to-date 2026-09-01
    FLASK_ENV=dev python analysis/nifty_pe_ratio_diagonal_backtest.py \
        --from-date 2026-08-25 --to-date 2026-09-01 --export-json /tmp/backtest.json
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from live.holidays import is_trading_day
from live.expiry import expiry_cache
from db.queries import get_merged_cadence_dates, write_option_chain_snapshot
from db.init_db import get_connection
from nifty_pe_ratio_diagonal_simulator import resolve_expiry_triplet, floor_strike_100
from nifty_fut_ref import (
    resolve_front_month_future, fetch_candles_utc, nearest_price,
    resolve_option_instrument_keys, IST,
)

SYMBOL = "NIFTY50"
ENTRY_TIME = time(9, 30)


def ist_ts_for(day: str, t: time) -> str:
    dt_ist = datetime.combine(date.fromisoformat(day), t, tzinfo=IST)
    return dt_ist.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def business_days(from_date: str, to_date: str) -> list[str]:
    d, end = date.fromisoformat(from_date), date.fromisoformat(to_date)
    out = []
    while d <= end:
        if is_trading_day(d):
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _resolve_expiry_type(conn, symbol: str, expiry_date: str) -> str:
    """
    Best-effort expiry_type for a date we're about to backfill a row for.
    Prefers whatever type any already-captured local row for this same
    expiry_date used (cheap, and correct by construction); falls back to
    scanning the live expiry_cache's weekly/monthly/quarterly rank lists
    for a date we've never captured locally under any type yet.
    """
    cur = conn.execute(
        "SELECT expiry_type FROM option_chain_5m WHERE symbol = ? AND expiry_date = ? LIMIT 1",
        (symbol, expiry_date),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    for t in ("weekly", "monthly", "quarterly"):
        for rank in range(6):
            d = expiry_cache.pick(symbol, t, rank)
            if d and d.isoformat() == expiry_date:
                return t
    return "unknown"


def _persist_backfill(conn, symbol: str, expiry_date: str, strike: float,
                       opt_type: str, live_series: dict) -> None:
    """
    Write a live-Upstox-fetched backfill series into option_chain_5m so a
    later run of this same (expiry_date, strike, opt_type) never needs to
    hit Upstox again for it. expiry_rank=-1 and spot_ltp=0.0 are sentinels
    (this row didn't come from a real full-chain snapshot, so there's no
    real rank or spot to record) — neither is read by get_merged_cadence_dates
    or chain_series, both of which only key on (ts, expiry_date, strike, opt_type).
    """
    expiry_type = _resolve_expiry_type(conn, symbol, expiry_date)
    rows = [{
        "ts": ts, "symbol": symbol, "spot_ltp": 0.0,
        "expiry_type": expiry_type, "expiry_rank": -1,
        "expiry_date": expiry_date, "strike": strike, "opt_type": opt_type,
        "ltp": ltp, "oi": None, "iv": None,
    } for ts, ltp in live_series.items()]
    write_option_chain_snapshot(rows)


def chain_series(conn, expiry_date: str, strike: float, opt_type: str, symbol: str,
                  backfill_from_ts: str | None = None) -> dict:
    """
    Full ts->ltp series for one (expiry_date, strike, opt_type), from local
    option_chain_5m. If backfill_from_ts is given and local coverage doesn't
    reach back that far, falls back to a live Upstox History pull for the
    missing earlier range, merges it in (local wins on any overlap), and
    PERSISTS the fetched rows back into option_chain_5m — so the next run
    of this same leg finds it locally and skips Upstox entirely. Covers the
    case where our own rank-window capture started tracking this contract
    later than Upstox itself has price history for. If the expiry has
    already settled, that live fetch fails/returns nothing and this
    silently proceeds with local-only data — the genuine, unavoidable
    ceiling for a settled expiry, not a bug.

    2026-09-09 correctness fix: a captured ltp of exactly 0 means Upstox had
    NO TRADE yet on that specific contract at that tick — not that the
    option was genuinely worthless. Confirmed empirically: a far-OTM,
    longer-dated NIFTY CE strike read ltp=0 for days (24800 CE @ 2026-09-15,
    ~455pts OTM/21 DTE on 2026-08-25 — nowhere near actually worthless) then
    jumped straight to a real price the moment trading started. NIFTY calls
    this far OTM are much thinner than equivalent-distance puts (skew/hedging
    demand), so this hits the CE side hard and the PE side rarely. Treating
    ltp=0 as "no data yet" (same as NULL) makes every caller's timestamp
    intersection naturally skip forward to the first tick where every leg
    has genuine price discovery, instead of pricing a leg at a false zero.
    """
    cur = conn.execute("""
        SELECT ts, ltp FROM option_chain_5m
        WHERE symbol = ? AND expiry_date = ? AND strike = ? AND opt_type = ?
        ORDER BY ts
    """, (symbol, expiry_date, strike, opt_type))
    series = {row[0]: row[1] for row in cur.fetchall() if row[1]}

    if backfill_from_ts and (not series or min(series) > backfill_from_ts):
        try:
            ikeys = resolve_option_instrument_keys(symbol, expiry_date, {strike}, opt_type=opt_type)
            if strike in ikeys:
                gap_to_date = (min(series)[:10] if series else backfill_from_ts[:10])
                live = fetch_candles_utc(ikeys[strike], backfill_from_ts[:10], gap_to_date)
                if live:
                    _persist_backfill(conn, symbol, expiry_date, strike, opt_type, live)
                series = {**{ts: v for ts, v in live.items() if v}, **series}
        except Exception:
            pass

    return series


def run_one_entry(conn, entry_date: str, merged: list[str], leg_gap: float,
                   fut_series: dict, symbol: str, lot_size: int) -> dict:
    try:
        expiry1, expiry2, expiry3 = resolve_expiry_triplet(entry_date, merged)
    except ValueError as e:
        return {"entry_date": entry_date, "error": str(e)}

    entry_target_ts = ist_ts_for(entry_date, ENTRY_TIME)
    fut_price = nearest_price(fut_series, entry_target_ts)
    if fut_price is None:
        return {"entry_date": entry_date, "error": "no futures price available at entry"}

    k_strike = floor_strike_100(fut_price)
    k2_strike = k_strike - leg_gap

    l1 = chain_series(conn, expiry1, k_strike, "PE", symbol, backfill_from_ts=entry_target_ts)
    l2 = chain_series(conn, expiry2, k2_strike, "PE", symbol, backfill_from_ts=entry_target_ts)
    l3 = chain_series(conn, expiry2, k_strike, "PE", symbol, backfill_from_ts=entry_target_ts)
    l4 = chain_series(conn, expiry3, k2_strike, "PE", symbol, backfill_from_ts=entry_target_ts)

    meta = {
        "entry_date": entry_date, "entry_fut": fut_price,
        "k_strike": k_strike, "k2_strike": k2_strike,
        "expiry1": expiry1, "expiry2": expiry2, "expiry3": expiry3,
        "leg_ticks": {"leg1": len(l1), "leg2": len(l2), "leg3": len(l3), "leg4": len(l4)},
    }

    common_ts = sorted(set(l1) & set(l2) & set(l3) & set(l4))
    common_ts = [ts for ts in common_ts if ts >= entry_target_ts]
    # Drop any tick captured on a non-trading day — a stale/repeated closed-market
    # quote (confirmed: some weekend days have full 75-snapshot captures, all
    # identical LTP, apparently from the poller having been run with --force) is
    # not a real data point and would misrepresent a frozen day as a trading day.
    common_ts = [ts for ts in common_ts if is_trading_day(date.fromisoformat(ts[:10]))]
    if not common_ts:
        meta["error"] = "no overlapping local chain data for all 4 legs from entry onward"
        return meta

    # Flag if the actual first common tick is later than the requested entry time —
    # means at least one leg (usually the far one) wasn't in the captured rank window yet.
    if common_ts[0] > entry_target_ts:
        meta["entry_shifted_to"] = common_ts[0]

    points = []
    entry_value = None
    for ts in common_ts:
        value = l1[ts] - 2 * l2[ts] - l3[ts] + 2 * l4[ts]
        if entry_value is None:
            entry_value = value
        points.append({
            "ts": ts, "day": ts[:10], "fut": nearest_price(fut_series, ts),
            "leg1_ltp": l1[ts], "leg2_ltp": l2[ts], "leg3_ltp": l3[ts], "leg4_ltp": l4[ts],
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

    meta.update({
        "entry_ts": points[0]["ts"], "entry_value": entry_value,
        "latest_ts": points[-1]["ts"], "latest_value": points[-1]["value"],
        "latest_pnl_pts": points[-1]["pnl_pts"], "latest_pnl_rs": points[-1]["pnl_rs"],
        "n_ticks": len(points), "lot_size": lot_size,
        "points": points, "daily": daily,
    })
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-date", required=True, help="earliest entry-date, e.g. 2026-08-25")
    ap.add_argument("--to-date", required=True, help="latest entry-date, e.g. 2026-09-01")
    ap.add_argument("--leg-gap", type=float, default=400)
    ap.add_argument("--symbol", default=SYMBOL)
    ap.add_argument("--export-json", default=None)
    args = ap.parse_args()

    expiry_cache.refresh([args.symbol])  # so _resolve_expiry_type's fallback path has data to scan

    merged = get_merged_cadence_dates(args.symbol, include_quarterly=True)
    if len(merged) < 3:
        print(f"Not enough expiry history in option_chain_5m: {merged}")
        sys.exit(1)

    entry_dates = business_days(args.from_date, args.to_date)
    if not entry_dates:
        print(f"No trading days in [{args.from_date}, {args.to_date}].")
        sys.exit(1)

    fut = resolve_front_month_future("NIFTY")
    conn = get_connection()

    # Each entry tracks forward until whatever the local chain data actually reaches,
    # not just --to-date (which is the entry-date range, not the tracking horizon) —
    # so the futures reference series must cover that full span too.
    cur = conn.execute("SELECT MAX(ts) FROM option_chain_5m")
    chain_max_ts = cur.fetchone()[0]
    chain_max_date = chain_max_ts[:10] if chain_max_ts else args.to_date
    fut_to = max(args.to_date, chain_max_date)
    pad_from = (date.fromisoformat(args.from_date) - timedelta(days=1)).isoformat()
    fut_series = fetch_candles_utc(fut["instrument_key"], pad_from, fut_to)
    if not fut_series:
        print(f"No futures history for {fut['trading_symbol']} over [{pad_from}, {fut_to}] — aborting.")
        sys.exit(1)

    print(f"Backtesting {len(entry_dates)} entry-date(s) in [{args.from_date}, {args.to_date}], "
          f"tracked through {fut_to}, leg_gap={args.leg_gap}, futures={fut['trading_symbol']}\n")

    results = []
    for d in entry_dates:
        res = run_one_entry(conn, d, merged, args.leg_gap, fut_series, args.symbol, fut["lot_size"])
        results.append(res)
        if "error" in res and "entry_value" not in res:
            print(f"{d}: FAILED — {res['error']}"
                  + (f"  (K={res['k_strike']}/{res['k2_strike']}, "
                     f"expiries={res.get('expiry1')}/{res.get('expiry2')}/{res.get('expiry3')}, "
                     f"leg ticks={res['leg_ticks']})" if "k_strike" in res else ""))
            continue
        shift_note = f"  [entry shifted to {res['entry_shifted_to']} — a leg wasn't captured yet at 09:30]" \
            if "entry_shifted_to" in res else ""
        print(f"{d}: K={res['k_strike']:.0f}/{res['k2_strike']:.0f}  "
              f"expiries={res['expiry1']}/{res['expiry2']}/{res['expiry3']}  "
              f"entry={res['entry_value']:.2f}  latest={res['latest_value']:.2f}  "
              f"pnl_pts={res['latest_pnl_pts']:+.2f}  ({res['n_ticks']} ticks, "
              f"through {res['latest_ts']}){shift_note}")
    conn.close()

    ok = [r for r in results if "points" in r]
    print(f"\n{len(ok)}/{len(results)} entry-date(s) produced a usable series.")

    if args.export_json:
        with open(args.export_json, "w") as f:
            json.dump({
                "symbol": args.symbol, "from_date": args.from_date, "to_date": args.to_date,
                "leg_gap": args.leg_gap, "fut_trading_symbol": fut["trading_symbol"],
                "results": results,
            }, f, indent=2)
        print(f"Exported to {args.export_json}")


if __name__ == "__main__":
    main()
