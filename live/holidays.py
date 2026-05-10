"""
NSE trading day check.

Uses the BSE (XBOM) calendar from exchange-calendars.
BSE and NSE share the same holiday schedule.
"""

import sys
from datetime import date, datetime, timezone
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
