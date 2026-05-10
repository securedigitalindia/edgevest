"""
Intraday 1h candle sync — keeps the DB current during live market hours.

Uses yfinance (same source as bootstrap/daily sync) to fetch the latest
1h candles and upsert them. Called at poller startup and each time a new
1h candle closes (every hour at :15 IST during market hours).

This ensures EMA/ST/RSI computed on 1h data always includes today's
closed candles, not just yesterday's historical data.
"""

import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bootstrap.yfinance_loader import fetch_historical
from db.queries import upsert_candles, get_latest_ts
from config import SYMBOLS, FETCH_DELAY_SECONDS

IST            = ZoneInfo("Asia/Kolkata")
_SYNC_PERIOD   = "5d"    # enough to cover today + a few days buffer
_SYNC_TF_KEY   = "1h"
_SYNC_INTERVAL = "1h"


def sync_1h_candles(symbol_names: list[str] | None = None) -> dict[str, int]:
    """
    Fetch latest 1h candles from yfinance and upsert to DB for each symbol.
    symbol_names: subset to sync, or None for all SYMBOLS.
    Returns {symbol_name: rows_upserted}.
    """
    targets = [s for s in SYMBOLS
               if symbol_names is None or s["name"] in symbol_names]
    results = {}

    for i, sym in enumerate(targets):
        name   = sym["name"]
        ticker = sym["ticker"]

        before = get_latest_ts(name, _SYNC_TF_KEY)

        df = fetch_historical(ticker, _SYNC_INTERVAL, _SYNC_PERIOD)

        if df.empty:
            print(f"  [1h sync]  {name}  — no data from yfinance", flush=True)
            results[name] = 0
            continue

        rows = upsert_candles(name, _SYNC_TF_KEY, df)
        after = get_latest_ts(name, _SYNC_TF_KEY)

        print(f"  [1h sync]  {name:<14}  {rows} rows upserted  "
              f"|  latest: {str(after)[:16]}", flush=True)
        results[name] = rows

        # Delay between fetches to avoid yfinance rate limiting
        if i < len(targets) - 1:
            time.sleep(FETCH_DELAY_SECONDS)

    return results


class HourlyCandleWatcher:
    """
    Tracks 1h candle closes during market hours.
    Call should_sync() on every poll tick — returns True once per candle close.

    NSE 1h candles close at :15 past each hour (market opens 9:15 IST):
        10:15, 11:15, 12:15, 13:15, 14:15, 15:15
    """

    def __init__(self):
        self._last_synced_hour: int | None = None

    def should_sync(self) -> bool:
        now_ist = datetime.now(timezone.utc).astimezone(IST)
        hour    = now_ist.hour
        minute  = now_ist.minute

        # A new 1h candle has closed when we're past :15 of a new hour
        if minute < 15:
            return False

        if self._last_synced_hour == hour:
            return False   # already synced this hour

        self._last_synced_hour = hour
        return True

    def mark_startup(self):
        """
        Call after the startup sync so the watcher doesn't immediately
        re-trigger a sync on the first poll tick.
        """
        now_ist = datetime.now(timezone.utc).astimezone(IST)
        if now_ist.minute >= 15:
            self._last_synced_hour = now_ist.hour
