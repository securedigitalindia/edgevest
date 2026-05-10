# ============================================================
#  Drishti — sync/daily_sync.py
#  End-of-day sync: fetches recent candles and upserts them.
#  Run this every evening after market close (after 3:35pm IST).
#  Safe to run multiple times — upsert won't duplicate rows.
# ============================================================

import sys
import os
import time
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import SYMBOLS, TIMEFRAMES, FETCH_DELAY_SECONDS, SYNC_LOOKBACK_CANDLES
from db.queries import (
    upsert_candles, update_sync_log,
    get_latest_ts, get_row_count
)
from bootstrap.yfinance_loader import fetch_historical


# -----------------------------------------------------------
# Sync period per timeframe
# Used to fetch "recent enough" data to catch today's candles
# -----------------------------------------------------------
SYNC_PERIODS = {
    "1h":  "30d",    # last 30 days covers all recent 1h candles
    "1d":  "30d",
    "1wk": "90d",
    "1mo": "90d",
}


def sync_symbol(symbol_cfg: dict) -> dict:
    """
    Sync all timeframes for a single symbol.
    Returns a summary dict.
    """
    ticker = symbol_cfg["ticker"]
    name   = symbol_cfg["name"]
    summary = {"symbol": name, "timeframes": {}}

    print(f"\n  {name}  ({ticker})")

    for tf in TIMEFRAMES:
        tf_key   = tf["key"]
        interval = tf["interval"]
        period   = SYNC_PERIODS[tf_key]

        latest_before = get_latest_ts(name, tf_key)
        count_before  = get_row_count(name, tf_key)

        if count_before == 0:
            print(f"    [{tf['description']}]  No data in DB — run bootstrap first")
            summary["timeframes"][tf_key] = {"status": "skipped_empty"}
            continue

        df = fetch_historical(ticker, interval, period)

        if df.empty:
            print(f"    [{tf['description']}]  ✗  No data from yfinance")
            summary["timeframes"][tf_key] = {"status": "fetch_failed"}
            continue

        # Filter to only rows newer than what we already have
        # We re-fetch SYNC_LOOKBACK_CANDLES to catch any late corrections
        if latest_before:
            cutoff = pd.Timestamp(latest_before, tz="UTC")
            # Keep rows >= cutoff to allow upsert of corrected candles
            df = df[df["ts"] >= cutoff].copy()

        if df.empty:
            print(f"    [{tf['description']}]  ✓  Already up to date")
            summary["timeframes"][tf_key] = {"status": "up_to_date", "new_rows": 0}
            continue

        rows = upsert_candles(name, tf_key, df)
        update_sync_log(name, tf_key, rows)

        count_after   = get_row_count(name, tf_key)
        latest_after  = get_latest_ts(name, tf_key)
        new_rows      = count_after - count_before

        status = "updated" if new_rows > 0 else "corrected"
        emoji  = "✓" if new_rows > 0 else "~"

        print(f"    [{tf['description']}]  {emoji}  "
              f"+{new_rows} new rows  |  "
              f"latest: {str(latest_after)[:16]}  |  "
              f"total: {count_after}")

        summary["timeframes"][tf_key] = {
            "status":   status,
            "new_rows": new_rows,
            "latest":   str(latest_after)[:16],
            "total":    count_after,
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
    print(f"\n  {'Symbol':<14} {'1h':>6} {'1d':>6} {'1wk':>6} {'1mo':>6}")
    print(f"  {'-'*42}")
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
        print(f"  {s['symbol']:<14} {fmt('1h'):>6} {fmt('1d'):>6} {fmt('1wk'):>6} {fmt('1mo'):>6}")
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
