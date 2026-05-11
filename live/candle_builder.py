"""
Builds 1h candles from stored LTP ticks.

Called at each 1h NSE candle close (at :15 past each hour).
Aggregates ticks from the just-closed 1h window → OHLCV → upserts to candles_1h.

NSE 1h candle windows (IST):
  09:15–10:15, 10:15–11:15, ..., 14:15–15:15
Each closes at H:15 IST; start = (H-1):15 IST.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from db.queries import get_ticks, upsert_candles

IST              = ZoneInfo("Asia/Kolkata")
MIN_TICKS        = 3     # fewer than this → not enough data for a meaningful candle
MIN_COVERAGE     = 0.5   # ticks must span ≥50% of the window to trust over yfinance data


def _candle_window_utc(now_ist: datetime) -> tuple[datetime, datetime]:
    """
    Given a datetime at or after H:15 IST, return (start_utc, end_utc)
    of the 1h candle that just closed.
    """
    end_ist   = now_ist.replace(minute=15, second=0, microsecond=0)
    start_ist = end_ist - timedelta(hours=1)
    return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)


def build_all(symbol_names: list[str]) -> dict[str, int]:
    """
    Build and upsert the 1h candle that just closed for every symbol.
    Returns {symbol_name: 1 if built, 0 if skipped}.
    """
    now_ist = datetime.now(timezone.utc).astimezone(IST)
    start_utc, end_utc = _candle_window_utc(now_ist)

    results: dict[str, int] = {}
    for name in symbol_names:
        ticks = get_ticks(name, start_utc, end_utc)

        if len(ticks) < MIN_TICKS:
            print(f"  [candle]  {name:<14}  only {len(ticks)} tick(s) in window — skipped",
                  flush=True)
            results[name] = 0
            continue

        # Coverage check: if the poller started mid-window, ticks only cover part of
        # the candle. Don't overwrite the existing yfinance candle with partial data.
        window_secs = (end_utc - start_utc).total_seconds()
        first_tick  = datetime.strptime(
            ticks["ts"].iloc[0], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        coverage = (end_utc - first_tick).total_seconds() / window_secs
        if coverage < MIN_COVERAGE:
            print(f"  [candle]  {name:<14}  {coverage:.0%} tick coverage — keeping yfinance data",
                  flush=True)
            results[name] = 0
            continue

        ltps = ticks["ltp"].astype(float)
        candle = pd.DataFrame([{
            "ts":     start_utc.strftime("%Y-%m-%d %H:%M:%S+00:00"),
            "open":   float(ltps.iloc[0]),
            "high":   float(ltps.max()),
            "low":    float(ltps.min()),
            "close":  float(ltps.iloc[-1]),
            "volume": None,
        }])
        upsert_candles(name, "1h", candle)

        print(
            f"  [candle]  {name:<14}  {len(ticks)} ticks → "
            f"O={ltps.iloc[0]:.2f}  H={ltps.max():.2f}  "
            f"L={ltps.min():.2f}  C={ltps.iloc[-1]:.2f}",
            flush=True,
        )
        results[name] = 1

    return results
