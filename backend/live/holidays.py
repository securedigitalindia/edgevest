"""
NSE trading day check.

Uses the BSE (XBOM) calendar from exchange-calendars.
BSE and NSE share the same holiday schedule.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import exchange_calendars as ec

IST = ZoneInfo("Asia/Kolkata")

_calendar = None


def _cal():
    global _calendar
    if _calendar is None:
        _calendar = ec.get_calendar("XBOM")
    return _calendar


def is_trading_day(d: date | None = None) -> bool:
    if d is None:
        d = date.today()
    return _cal().is_session(d)


def check_or_exit():
    """
    Print a message and exit cleanly if today is not an NSE trading day.
    Call once at poller startup.
    """
    today    = date.today()
    day_name = today.strftime("%A, %d %b %Y")

    if not is_trading_day(today):
        print(f"\n{day_name} is not an NSE trading day (market holiday or weekend).")
        print("Poller exiting. Run again on a trading day.\n")
        sys.exit(0)

    print(f"  Trading day confirmed: {day_name}")


def next_trading_day(after: date) -> date:
    """First NSE trading day strictly after `after` — skips weekends and
    holidays, so a Friday close can jump straight to Monday (or further,
    over a long weekend/festival block)."""
    d = after
    for _ in range(14):  # generous cap — no real NSE gap is anywhere close to this
        d = d + timedelta(days=1)
        if is_trading_day(d):
            return d
    raise RuntimeError(f"No trading day found within 14 days after {after}")
