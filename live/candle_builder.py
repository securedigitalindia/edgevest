"""
Builds intraday OHLCV candles from stored LTP ticks.

Supports 5m, 15m, and 1h timeframes. Called at each candle close boundary:
  5m  → every :00/:05/:10/... past market open (09:20, 09:25, ..., 15:30)
  15m → every :00/:15/:30/... past market open (09:30, 09:45, ..., 15:30)
  1h  → every :15 past each hour              (10:15, 11:15, ..., 15:15)

All boundaries are counted from NSE market open at 09:15 IST.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from db.queries import get_ticks, upsert_candles

IST          = ZoneInfo("Asia/Kolkata")
MIN_TICKS    = 3
MIN_COVERAGE = 0.5

# Minutes per candle for each supported intraday timeframe
TF_MINUTES = {
    "5m":  5,
    "15m": 15,
    "1h":  60,
}

_MARKET_OPEN_H = 9
_MARKET_OPEN_M = 15


def _candle_window_utc(tf_key: str) -> tuple[datetime, datetime]:
    """Return (start_utc, end_utc) for the candle that just closed."""
    interval_min = TF_MINUTES[tf_key]
    now_ist = datetime.now(timezone.utc).astimezone(IST)
    market_open = now_ist.replace(
        hour=_MARKET_OPEN_H, minute=_MARKET_OPEN_M, second=0, microsecond=0
    )
    elapsed_min = (now_ist - market_open).total_seconds() / 60
    n         = int(elapsed_min // interval_min)
    end_ist   = market_open + timedelta(minutes=n * interval_min)
    start_ist = end_ist - timedelta(minutes=interval_min)
    return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)


def build_all(symbol_names: list[str], tf_key: str) -> dict[str, int]:
    """
    Build and upsert the candle that just closed for every symbol.
    Returns {symbol_name: 1 if built, 0 if skipped}.
    """
    start_utc, end_utc = _candle_window_utc(tf_key)

    results: dict[str, int] = {}
    for name in symbol_names:
        ticks = get_ticks(name, start_utc, end_utc)

        if len(ticks) < MIN_TICKS:
            print(f"  [candle/{tf_key}]  {name:<14}  only {len(ticks)} tick(s) — skipped",
                  flush=True)
            results[name] = 0
            continue

        window_secs = (end_utc - start_utc).total_seconds()
        first_tick  = datetime.strptime(
            ticks["ts"].iloc[0], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        coverage = (end_utc - first_tick).total_seconds() / window_secs
        if coverage < MIN_COVERAGE:
            print(f"  [candle/{tf_key}]  {name:<14}  {coverage:.0%} coverage — keeping yfinance data",
                  flush=True)
            results[name] = 0
            continue

        ltps   = ticks["ltp"].astype(float)
        candle = pd.DataFrame([{
            "ts":     start_utc.strftime("%Y-%m-%d %H:%M:%S+00:00"),
            "open":   float(ltps.iloc[0]),
            "high":   float(ltps.max()),
            "low":    float(ltps.min()),
            "close":  float(ltps.iloc[-1]),
            "volume": None,
        }])
        upsert_candles(name, tf_key, candle)

        print(
            f"  [candle/{tf_key}]  {name:<14}  {len(ticks)} ticks → "
            f"O={ltps.iloc[0]:.2f}  H={ltps.max():.2f}  "
            f"L={ltps.min():.2f}  C={ltps.iloc[-1]:.2f}",
            flush=True,
        )
        results[name] = 1

    return results
