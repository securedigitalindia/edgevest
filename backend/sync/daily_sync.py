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
from bootstrap.upstox_loader import fetch_historical, fetch_intraday, UPSTOX_INTRADAY_TF_MAP

# Always re-fetch at least this many trailing calendar days, even when
# there's no gap, as insurance against Upstox revising an already-published
# candle. A real gap (e.g. the poller was down for weeks) simply widens the
# fetched range further back than this — fetch_historical's own chunking
# handles catching up fully in one run regardless of how large the gap is.
SYNC_RECHECK_DAYS = 2


def sync_symbol(symbol_cfg: dict) -> dict:
    """
    Sync all timeframes for a single symbol.

    Two separate Upstox APIs, two separate jobs (confirmed 2026-09-22 — the
    Historical Candle API is documented to never include the current
    trading day, no matter how long after close you ask):
      - fetch_historical() (below): backfills/corrects everything OLDER
        than today — the gap-fill job it's always done.
      - fetch_intraday() (new): fills in TODAY specifically, via Upstox's
        separate Intraday Candle Data API — the one gap fetch_historical()
        structurally can never close. Only "1m"/"5m"/"15m"/"1h"/"1d" support
        this (no "weeks"/"months" unit on that endpoint) — "1wk"/"1mo" get
        historical-only, same as always ("this week"/"this month" being
        incomplete until it ends isn't a same-day gap anything needs).
    Both write through the same upsert_candles() — downstream readers
    (games, reports, strategies) just read candles_1d etc. normally and get
    complete, correct same-day data without knowing either of this exists.

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

        df_hist = fetch_historical(instrument_key, tf_key, from_date, today)
        if not df_hist.empty:
            update_sync_log(name, tf_key, upsert_candles(name, tf_key, df_hist))
        time.sleep(FETCH_DELAY_SECONDS)

        # Today specifically — fetch_historical() above never includes it,
        # by design. Independent of whether historical found anything, so
        # this always runs even when historical was already fully caught up.
        got_today = False
        if tf_key in UPSTOX_INTRADAY_TF_MAP:
            df_today = fetch_intraday(instrument_key, tf_key)
            if not df_today.empty:
                update_sync_log(name, tf_key, upsert_candles(name, tf_key, df_today))
                got_today = True
            time.sleep(FETCH_DELAY_SECONDS)

        count_after = get_row_count(name, tf_key)
        latest_after = get_latest_ts(name, tf_key)
        new_rows = count_after - count_before

        if new_rows == 0 and not got_today:
            print(f"    [{tf['description']}]  ✓  Already up to date")
            summary["timeframes"][tf_key] = {"status": "up_to_date", "new_rows": 0}
            continue

        status = "updated" if new_rows > 0 else "corrected"
        emoji = "✓" if new_rows > 0 else "~"

        print(f"    [{tf['description']}]  {emoji}  "
              f"+{new_rows} new rows{' (incl. today)' if got_today else ''}  |  "
              f"latest: {str(latest_after)[:16]}  |  "
              f"total: {count_after}")

        summary["timeframes"][tf_key] = {
            "status": status,
            "new_rows": new_rows,
            "latest": str(latest_after)[:16],
            "total": count_after,
        }

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
