# ============================================================
#  Drishti — bootstrap/upstox_loader.py
#  Seeds the database with full historical OHLCV data via Upstox's
#  History V3 API. Run for initial setup, a full re-seed, or to
#  retroactively backfill any gap (e.g. a missed ad-hoc special session).
# ============================================================

import sys
import os
import time
from datetime import date, timedelta, datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import SYMBOLS, TIMEFRAMES, FETCH_DELAY_SECONDS, UPSTOX_INSTRUMENT_KEYS
from db.queries import upsert_candles, update_sync_log, get_row_count, delete_candles
from live.upstox_client import get_historical_candles

# -----------------------------------------------------------
# Upstox V3 constraints (confirmed against the live API):
#   minutes (interval 1-15) : data from 2022-01-01, max 30 days/request
#   hours                   : data from 2022-01-01, max 91 days/request
#   days                    : data from 2000-01-01, max ~10 years/request
#   weeks/months            : data from 2000-01-01, no request limit
# -----------------------------------------------------------
UPSTOX_TF_MAP = {
    # tf_key: (unit, interval, safe_chunk_days)
    "1m":  ("minutes", 1,  30),
    "5m":  ("minutes", 5,  30),
    "15m": ("minutes", 15, 30),
    "1h":  ("hours",   1,  90),
    "1d":  ("days",    1,  3650),
    "1wk": ("weeks",   1,  None),   # no cap
    "1mo": ("months",  1,  None),   # no cap
}

DATA_FLOOR = {
    "minutes": date(2022, 1, 1),
    "hours":   date(2022, 1, 1),
    "days":    date(2000, 1, 1),
    "weeks":   date(2000, 1, 1),
    "months":  date(2000, 1, 1),
}

# Approximate candle duration per timeframe, for in-progress-candle detection
_INTRADAY_DURATION = {
    "1m":  timedelta(minutes=1),
    "5m":  timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h":  timedelta(hours=1),
}

IST = timezone(timedelta(hours=5, minutes=30))


# -----------------------------------------------------------
# Chunking
# -----------------------------------------------------------

def _chunk_ranges(from_date: date, to_date: date, max_days: int | None) -> list[tuple[date, date]]:
    """Split [from_date, to_date] into chunks no larger than max_days each.
    max_days=None means no splitting needed (weeks/months have no cap)."""
    if from_date > to_date:
        return []
    if max_days is None:
        return [(from_date, to_date)]

    chunks = []
    start = from_date
    while start <= to_date:
        end = min(start + timedelta(days=max_days - 1), to_date)
        chunks.append((start, end))
        start = end + timedelta(days=1)
    return chunks


# -----------------------------------------------------------
# In-progress candle detection
# -----------------------------------------------------------

def _is_incomplete_last_candle(last_ts_utc: pd.Timestamp, tf_key: str) -> bool:
    """
    True if the most recent candle in a freshly-fetched batch might still be
    forming (i.e. its period hasn't fully elapsed yet), so it should be
    dropped before upserting.

    Replaces yfinance_loader's old hardcoded interval tuple (which silently
    excluded "1m", leaving 1m in-progress candles unfiltered) with one
    uniform rule covering every timeframe. Deliberately conservative — safe
    even if it occasionally drops a candle that's technically already
    closed, since the next sync run re-fetches from get_latest_ts()
    inclusive regardless.
    """
    now_utc = datetime.now(timezone.utc)
    last_ts_utc = last_ts_utc.to_pydatetime()

    if tf_key in _INTRADAY_DURATION:
        return (last_ts_utc + _INTRADAY_DURATION[tf_key]) > now_utc

    last_ist = last_ts_utc.astimezone(IST)
    now_ist = now_utc.astimezone(IST)

    if tf_key == "1d":
        return last_ist.date() == now_ist.date()
    if tf_key == "1wk":
        return last_ist.isocalendar()[:2] == now_ist.isocalendar()[:2]
    if tf_key == "1mo":
        return (last_ist.year, last_ist.month) == (now_ist.year, now_ist.month)
    return False


# -----------------------------------------------------------
# Core fetch
# -----------------------------------------------------------

def fetch_historical(
    instrument_key: str, tf_key: str,
    from_date: date, to_date: date,
    drop_incomplete: bool = True,
) -> pd.DataFrame:
    """
    Chunked fetch from Upstox's History V3 API for [from_date, to_date],
    clamped to Upstox's data floor for this timeframe's unit.

    Returns an ascending, deduped, UTC tz-aware DataFrame with columns:
    ts, open, high, low, close, volume, oi. Empty DataFrame if nothing
    available (e.g. the whole range predates Upstox's data floor).
    """
    unit, interval, max_days = UPSTOX_TF_MAP[tf_key]
    floor = DATA_FLOOR[unit]
    from_date = max(from_date, floor)

    if from_date > to_date:
        return pd.DataFrame()

    all_rows = []
    for chunk_start, chunk_end in _chunk_ranges(from_date, to_date, max_days):
        try:
            candles = get_historical_candles(
                instrument_key, unit, interval,
                from_date=chunk_start.isoformat(),
                to_date=chunk_end.isoformat(),
            )
        except RuntimeError as e:
            print(f"    ✗  Upstox error [{tf_key}] {chunk_start}→{chunk_end}: {e}")
            continue
        all_rows.extend(candles)
        time.sleep(FETCH_DELAY_SECONDS)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume", "oi"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.dropna(subset=["close"])
    df = df.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)

    if drop_incomplete and not df.empty and _is_incomplete_last_candle(df["ts"].iloc[-1], tf_key):
        df = df.iloc[:-1]

    return df.reset_index(drop=True)


# -----------------------------------------------------------
# Bootstrap runner
# -----------------------------------------------------------

def bootstrap_symbol(symbol_cfg: dict):
    """Bootstrap all timeframes for a single symbol."""
    name = symbol_cfg["name"]
    instrument_key = UPSTOX_INSTRUMENT_KEYS[name]
    today = date.today()

    print(f"\n{'='*55}")
    print(f"  {name}  ({instrument_key})")
    print(f"{'='*55}")

    for tf in TIMEFRAMES:
        tf_key = tf["key"]
        from_date = today - timedelta(days=tf["bootstrap_days"])

        # Bootstrap means "seed from scratch" — clear this symbol/timeframe
        # first so a fresh Upstox fetch can never collide with (and thus
        # never leave behind) a stale duplicate row from an earlier
        # provider or run. Only SYMBOLS' own 3 symbols ever have rows in
        # these tables, so this only ever clears data we're about to
        # replace with fresh, complete history in the same breath.
        cleared = delete_candles(name, tf_key)

        print(f"\n  [{tf['description']}]  cleared {cleared} existing row(s)  |  "
              f"fetching from {from_date} to {today}...")

        df = fetch_historical(instrument_key, tf_key, from_date, today)

        if df.empty:
            print(f"    ✗  No data returned — table is now empty for this timeframe")
            continue

        rows = upsert_candles(name, tf_key, df)
        update_sync_log(name, tf_key, rows)

        total = get_row_count(name, tf_key)
        date_from = str(df["ts"].iloc[0])[:10]
        date_to = str(df["ts"].iloc[-1])[:10]

        print(f"    ✓  {rows} rows written  |  {date_from} → {date_to}  |  total in DB: {total}")


def run_bootstrap(symbols=None):
    """
    Bootstrap all symbols (or a subset).
    Pass a list of name strings to bootstrap specific symbols only.
    """
    from db.init_db import init_db
    print("Initialising database tables...")
    init_db()

    targets = SYMBOLS
    if symbols:
        targets = [s for s in SYMBOLS if s["name"] in symbols]

    print(f"\nBootstrapping {len(targets)} symbol(s)...")
    start = time.time()

    for sym in targets:
        bootstrap_symbol(sym)

    elapsed = time.time() - start
    print(f"\n{'='*55}")
    print(f"  Bootstrap complete in {elapsed:.1f}s")
    print(f"{'='*55}\n")


# -----------------------------------------------------------
# Entry point
# -----------------------------------------------------------

if __name__ == "__main__":
    # Optional: pass symbol names as args to bootstrap specific ones
    # e.g.  python bootstrap/upstox_loader.py RELIANCE
    import argparse
    parser = argparse.ArgumentParser(description="Drishti bootstrap loader")
    parser.add_argument(
        "symbols", nargs="*",
        help="Symbol names to bootstrap (default: all). E.g. RELIANCE NIFTY50"
    )
    args = parser.parse_args()
    run_bootstrap(args.symbols if args.symbols else None)
