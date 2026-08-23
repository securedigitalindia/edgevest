# ============================================================
#  Drishti — sync/daily_sync.py
#  End-of-day sync: gap-fill from the last stored candle through today,
#  via Upstox's History V3 API. Run this every evening after market close
#  (after 3:35pm IST). Safe to run multiple times — upsert won't
#  duplicate rows.
# ============================================================

import sys
import os
import time
from datetime import date, datetime, timezone, timedelta

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import SYMBOLS, TIMEFRAMES, FETCH_DELAY_SECONDS, UPSTOX_INSTRUMENT_KEYS
from db.queries import (
    upsert_candles, update_sync_log,
    get_latest_ts, get_row_count
)
from bootstrap.upstox_loader import fetch_historical

# Always re-fetch at least this many trailing calendar days, even when
# there's no gap, as insurance against Upstox revising an already-published
# candle. A real gap (e.g. the poller was down for weeks) simply widens the
# fetched range further back than this — fetch_historical's own chunking
# handles catching up fully in one run regardless of how large the gap is.
SYNC_RECHECK_DAYS = 2


def sync_symbol(symbol_cfg: dict) -> dict:
    """
    Sync all timeframes for a single symbol.
    Returns a summary dict.
    """
    name = symbol_cfg["name"]
    instrument_key = UPSTOX_INSTRUMENT_KEYS[name]
    today = date.today()
    summary = {"symbol": name, "timeframes": {}}

    print(f"\n  {name}  ({instrument_key})")

    for tf in TIMEFRAMES:
        tf_key = tf["key"]

        latest_before = get_latest_ts(name, tf_key)
        count_before = get_row_count(name, tf_key)

        if count_before == 0 or latest_before is None:
            print(f"    [{tf['description']}]  No data in DB — run bootstrap first")
            summary["timeframes"][tf_key] = {"status": "skipped_empty"}
            continue

        latest_date = pd.Timestamp(latest_before).tz_convert("Asia/Kolkata").date()
        from_date = min(latest_date, today) - timedelta(days=SYNC_RECHECK_DAYS)

        df = fetch_historical(instrument_key, tf_key, from_date, today)

        if df.empty:
            print(f"    [{tf['description']}]  ✓  Already up to date")
            summary["timeframes"][tf_key] = {"status": "up_to_date", "new_rows": 0}
            continue

        rows = upsert_candles(name, tf_key, df)
        update_sync_log(name, tf_key, rows)

        count_after = get_row_count(name, tf_key)
        latest_after = get_latest_ts(name, tf_key)
        new_rows = count_after - count_before

        status = "updated" if new_rows > 0 else "corrected"
        emoji = "✓" if new_rows > 0 else "~"

        print(f"    [{tf['description']}]  {emoji}  "
              f"+{new_rows} new rows  |  "
              f"latest: {str(latest_after)[:16]}  |  "
              f"total: {count_after}")

        summary["timeframes"][tf_key] = {
            "status": status,
            "new_rows": new_rows,
            "latest": str(latest_after)[:16],
            "total": count_after,
        }

        time.sleep(FETCH_DELAY_SECONDS)

    return summary


def run_daily_sync(symbols=None):
    """
    Run end-of-day sync for all symbols (or a subset).
    """
    now = datetime.now(timezone.utc)
    print(f"\n{'='*55}")
    print(f"  Drishti — Daily Sync")
    print(f"  {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*55}")

    targets = SYMBOLS
    if symbols:
        targets = [s for s in SYMBOLS if s["name"] in symbols]

    print(f"\nSyncing {len(targets)} symbol(s)...\n")
    start = time.time()
    all_summaries = []

    for sym in targets:
        summary = sync_symbol(sym)
        all_summaries.append(summary)

    elapsed = time.time() - start

    # Print summary table
    print(f"\n{'='*55}")
    print(f"  Sync complete in {elapsed:.1f}s")
    print(f"{'='*55}")
    print(f"\n  {'Symbol':<14} {'1m':>6} {'5m':>6} {'15m':>6} {'1h':>6} {'1d':>6} {'1wk':>6} {'1mo':>6}")
    print(f"  {'-'*60}")
    for s in all_summaries:
        tfs = s["timeframes"]
        def fmt(tf_key):
            info = tfs.get(tf_key, {})
            if info.get("status") == "up_to_date":
                return "  ok"
            elif info.get("status") == "updated":
                return f"+{info.get('new_rows', 0):>3}"
            elif info.get("status") == "skipped_empty":
                return " ---"
            else:
                return "  ?"
        print(f"  {s['symbol']:<14} {fmt('1m'):>6} {fmt('5m'):>6} {fmt('15m'):>6} {fmt('1h'):>6} {fmt('1d'):>6} {fmt('1wk'):>6} {fmt('1mo'):>6}")
    print()


# -----------------------------------------------------------
# Entry point
# -----------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Drishti daily sync")
    parser.add_argument(
        "symbols", nargs="*",
        help="Symbol names to sync (default: all). E.g. RELIANCE NIFTY50"
    )
    args = parser.parse_args()
    run_daily_sync(args.symbols if args.symbols else None)
