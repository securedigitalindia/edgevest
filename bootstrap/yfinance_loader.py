# ============================================================
#  Drishti — bootstrap/yfinance_loader.py
#  Seeds the database with full historical OHLCV data.
#  Run ONCE during initial setup (or to do a full re-seed).
# ============================================================

import sys
import os
import time
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import SYMBOLS, TIMEFRAMES, FETCH_DELAY_SECONDS
from db.queries import upsert_candles, update_sync_log, get_row_count


# -----------------------------------------------------------
# Core fetch
# -----------------------------------------------------------

def fetch_historical(ticker: str, interval: str, period: str) -> pd.DataFrame:
    """
    Fetch OHLCV data from yfinance and return a clean DataFrame
    with columns: ts, open, high, low, close, volume
    """
    try:
        raw = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=True,       # adjusts for splits/dividends
            progress=False,
            threads=False,
        )
    except Exception as e:
        print(f"    ✗  yfinance error: {e}")
        return pd.DataFrame()

    if raw is None or raw.empty:
        print(f"    ✗  No data returned for {ticker} [{interval}]")
        return pd.DataFrame()

    # yfinance returns MultiIndex columns when downloading single ticker
    # Flatten if needed
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw = raw.reset_index()

    # Normalise timestamp column (could be 'Date' or 'Datetime')
    ts_col = "Datetime" if "Datetime" in raw.columns else "Date"
    raw = raw.rename(columns={ts_col: "ts"})

    # Keep only what we need
    cols = ["ts", "Open", "High", "Low", "Close", "Volume"]
    available = [c for c in cols if c in raw.columns]
    raw = raw[available].copy()
    raw.columns = [c.lower() for c in raw.columns]

    # Ensure ts is UTC-aware
    if raw["ts"].dt.tz is None:
        raw["ts"] = raw["ts"].dt.tz_localize("UTC")
    else:
        raw["ts"] = raw["ts"].dt.tz_convert("UTC")

    # Drop rows with no close price
    raw = raw.dropna(subset=["close"])

    # Drop the current incomplete candle (last row for intraday)
    if interval in ("1h", "5m", "15m", "30m"):
        raw = raw.iloc[:-1]

    return raw.reset_index(drop=True)


# -----------------------------------------------------------
# Bootstrap runner
# -----------------------------------------------------------

def bootstrap_symbol(symbol_cfg: dict):
    """Bootstrap all timeframes for a single symbol."""
    ticker = symbol_cfg["ticker"]
    name   = symbol_cfg["name"]

    print(f"\n{'='*55}")
    print(f"  {name}  ({ticker})")
    print(f"{'='*55}")

    for tf in TIMEFRAMES:
        tf_key   = tf["key"]
        interval = tf["interval"]
        period   = tf["period"]

        print(f"\n  [{tf['description']}]  fetching {period} of data...")

        df = fetch_historical(ticker, interval, period)

        if df.empty:
            print(f"    ✗  Skipped — no data")
            continue

        rows = upsert_candles(name, tf_key, df)
        update_sync_log(name, tf_key, rows)

        total = get_row_count(name, tf_key)
        date_from = str(df["ts"].iloc[0])[:10]
        date_to   = str(df["ts"].iloc[-1])[:10]

        print(f"    ✓  {rows} rows written  |  {date_from} → {date_to}  |  total in DB: {total}")

        time.sleep(FETCH_DELAY_SECONDS)


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
    # e.g.  python bootstrap/yfinance_loader.py RELIANCE
    import argparse
    parser = argparse.ArgumentParser(description="Drishti bootstrap loader")
    parser.add_argument(
        "symbols", nargs="*",
        help="Symbol names to bootstrap (default: all). E.g. RELIANCE NIFTY50"
    )
    args = parser.parse_args()
    run_bootstrap(args.symbols if args.symbols else None)
