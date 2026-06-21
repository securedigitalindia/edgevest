# ============================================================
#  Drishti — utils/verify_db.py
#  Sanity check: row counts, date ranges, gap detection.
#  Run after bootstrap or sync to confirm data looks correct.
# ============================================================

import sys
import os
import pandas as pd
from datetime import timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import SYMBOLS, TIMEFRAMES
from db.queries import get_candles, get_row_count, get_latest_ts, get_sync_log
from db.init_db import get_connection, TF_TABLE


# Expected minimum rows per timeframe (rough sanity thresholds)
MIN_ROWS = {
    "1h":  500,
    "1d":  500,
    "1wk": 100,
    "1mo": 50,
}

# NSE trading hours in UTC (IST is UTC+5:30)
# Market opens 09:15 IST = 03:45 UTC
# Market closes 15:30 IST = 10:00 UTC
NSE_OPEN_UTC_HOUR  = 3
NSE_OPEN_UTC_MIN   = 45
NSE_CLOSE_UTC_HOUR = 10
NSE_CLOSE_UTC_MIN  = 0

# For 1h gaps: max consecutive TRADING-HOUR candles that can be missing
# before we flag it as suspicious (weekends/nights are ignored)
MAX_MISSING_TRADING_CANDLES_1H = 3


def _is_market_gap(t1: pd.Timestamp, t2: pd.Timestamp) -> bool:
    """
    Return True if the gap between t1 and t2 is fully explained by
    overnight hours, weekends, or public holidays (i.e. not a real gap).
    For 1h data: a gap is normal if t1 is near market close and
    t2 is near next market open (possibly days later for weekends).
    """
    # If gap <= 1 trading day worth of hours it's fine
    # NSE has ~6.25 trading hours/day → 7 1h candles max per day
    # Overnight gap: ~18h. Weekend gap: ~66h. Both are normal.
    gap_hours = (t2 - t1).total_seconds() / 3600

    # Anything under 20h is just overnight — normal
    if gap_hours <= 20:
        return True

    # Weekend: Friday close to Monday open = ~66h
    # t1 is Friday, t2 is Monday → normal
    if t1.dayofweek == 4 and t2.dayofweek == 0 and gap_hours <= 72:
        return True

    # Long weekend (holiday on Monday or Friday): up to 4 days
    if gap_hours <= 96:
        return True

    return False


def check_gaps(df: pd.DataFrame, tf_key: str) -> list:
    """
    Detect genuine data gaps in the candle series.
    For 1h data, overnight/weekend gaps are ignored — only
    intra-session gaps (missing candles during market hours) are flagged.
    Returns a list of (gap_start, gap_end, missing_candles) tuples.
    """
    if df.empty or len(df) < 2:
        return []

    ts = df["ts"].sort_values().reset_index(drop=True)

    # For daily/weekly/monthly: simple approach — flag gaps > N periods
    if tf_key in ("1d", "1wk", "1mo"):
        diffs = ts.diff().dropna()
        median_interval = diffs.median()
        # Allow up to 5x median (covers long holidays)
        threshold = median_interval * 5

        gaps = []
        for i, diff in diffs.items():
            if diff > threshold:
                gap_start = str(ts.iloc[i - 1])[:16]
                gap_end   = str(ts.iloc[i])[:16]
                missing   = round(diff / median_interval) - 1
                gaps.append((gap_start, gap_end, missing))
        return gaps

    # For 1h: skip overnight/weekend gaps, only flag intra-session holes
    if tf_key == "1h":
        gaps = []
        for i in range(1, len(ts)):
            t1 = ts.iloc[i - 1]
            t2 = ts.iloc[i]
            diff = t2 - t1

            # Normal overnight/weekend gap → skip
            if _is_market_gap(t1, t2):
                continue

            # Genuine intra-session gap
            missing_hours = round(diff.total_seconds() / 3600) - 1
            if missing_hours >= MAX_MISSING_TRADING_CANDLES_1H:
                gaps.append((str(t1)[:16], str(t2)[:16], missing_hours))

        return gaps

    return []


def verify_all():
    """Run verification across all symbols and timeframes."""
    print(f"\n{'='*60}")
    print(f"  Drishti — Database Verification")
    print(f"{'='*60}\n")

    total_issues = 0

    for sym_cfg in SYMBOLS:
        name = sym_cfg["name"]
        print(f"  ▶  {name}")
        print(f"  {'-'*50}")

        for tf in TIMEFRAMES:
            tf_key = tf["key"]
            label  = tf["description"]

            count  = get_row_count(name, tf_key)
            latest = get_latest_ts(name, tf_key)

            # Row count check
            min_expected = MIN_ROWS[tf_key]
            count_ok = count >= min_expected
            count_flag = "✓" if count_ok else "✗"
            if not count_ok:
                total_issues += 1

            # Fetch data for gap check
            df = get_candles(name, tf_key, limit=2000)
            earliest = str(df["ts"].iloc[0])[:10] if not df.empty else "n/a"
            latest_str = str(df["ts"].iloc[-1])[:10] if not df.empty else "n/a"

            gaps = check_gaps(df, tf_key) if not df.empty else []
            gap_flag = f"  ⚠  {len(gaps)} gap(s) detected" if gaps else ""
            if gaps:
                total_issues += len(gaps)

            print(f"    [{label:8}]  {count_flag}  {count:>5} rows  "
                  f"|  {earliest} → {latest_str}{gap_flag}")

            # Print gap details if any
            for gap_start, gap_end, missing in gaps[:3]:   # show max 3
                print(f"               ⚠  Gap: {gap_start} → {gap_end}  "
                      f"(~{missing} missing candles)")

        print()

    # Sync log
    sync_df = get_sync_log()
    if not sync_df.empty:
        print(f"  Last sync times:")
        print(f"  {'-'*50}")
        for _, row in sync_df.iterrows():
            last = str(row["last_sync"])[:16]
            print(f"    {row['symbol']:<14}  {row['tf_key']:<6}  {last}  "
                  f"(+{row['rows_added']} rows)")
        print()

    # Final verdict
    print(f"{'='*60}")
    if total_issues == 0:
        print(f"  ✅  All checks passed — data looks good")
    else:
        print(f"  ⚠   {total_issues} issue(s) found — review above")
    print(f"{'='*60}\n")

    return total_issues


if __name__ == "__main__":
    verify_all()
