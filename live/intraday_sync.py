"""
Intraday candle close watcher.

CandleWatcher fires should_build() once per candle close for a given
interval. Boundaries are counted from NSE market open (09:15 IST).

  CandleWatcher(5)   → fires at 09:20, 09:25, ..., 15:30 IST
  CandleWatcher(15)  → fires at 09:30, 09:45, ..., 15:30 IST
  CandleWatcher(60)  → fires at 10:15, 11:15, ..., 15:15 IST
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

IST            = ZoneInfo("Asia/Kolkata")
_MARKET_OPEN_H = 9
_MARKET_OPEN_M = 15


class CandleWatcher:
    def __init__(self, interval_minutes: int):
        self.interval_minutes         = interval_minutes
        self._last_boundary: datetime | None = None

    def _current_boundary(self, now_ist: datetime) -> datetime | None:
        """Most recently completed candle-close boundary, or None if before first close."""
        market_open = now_ist.replace(
            hour=_MARKET_OPEN_H, minute=_MARKET_OPEN_M,
            second=0, microsecond=0,
        )
        if now_ist < market_open:
            return None
        elapsed_min = (now_ist - market_open).total_seconds() / 60
        n = int(elapsed_min // self.interval_minutes)
        if n == 0:
            return None
        return market_open + timedelta(minutes=n * self.interval_minutes)

    def mark_startup(self):
        """Suppress any past-boundary fires on first poll after startup."""
        now_ist = datetime.now(timezone.utc).astimezone(IST)
        self._last_boundary = self._current_boundary(now_ist)

    def should_build(self) -> bool:
        """Returns True once per candle close. Call on every poll tick."""
        now_ist  = datetime.now(timezone.utc).astimezone(IST)
        boundary = self._current_boundary(now_ist)
        if boundary is None:
            return False
        if self._last_boundary is not None and boundary <= self._last_boundary:
            return False
        self._last_boundary = boundary
        return True
