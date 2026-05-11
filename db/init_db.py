# ============================================================
#  Drishti — db/init_db.py
#  Creates the SQLite database and all timeframe tables.
#  Safe to re-run — uses CREATE TABLE IF NOT EXISTS.
# ============================================================

import sqlite3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import DB_PATH, TIMEFRAMES, SYMBOLS


def get_connection():
    """Return a configured SQLite connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")   # better concurrency
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def table_name(tf_key: str) -> str:
    """Canonical table name for a timeframe key."""
    return f"candles_{tf_key.replace('1', 'tf1').replace('wk', 'wk').replace('mo', 'mo')}"


# Simpler, readable table names
TF_TABLE = {
    "5m":  "candles_5m",
    "15m": "candles_15m",
    "1h":  "candles_1h",
    "1d":  "candles_1d",
    "1wk": "candles_1wk",
    "1mo": "candles_1mo",
}


def init_db():
    """Create all tables and indexes. Idempotent."""
    conn = get_connection()
    cur = conn.cursor()

    for tf in TIMEFRAMES:
        tbl = TF_TABLE[tf["key"]]

        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {tbl} (
                symbol      TEXT    NOT NULL,
                ts          TEXT    NOT NULL,   -- ISO-8601 UTC timestamp
                open        REAL,
                high        REAL,
                low         REAL,
                close       REAL,
                volume      REAL,               -- NULL for indices
                PRIMARY KEY (symbol, ts)
            )
        """)

        # Fast lookup by symbol + descending time (used by indicator engine)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{tbl}_sym_ts
            ON {tbl} (symbol, ts DESC)
        """)

        print(f"  ✓  Table ready: {tbl}")

    # Metadata table — tracks last sync per symbol+timeframe
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            symbol      TEXT NOT NULL,
            tf_key      TEXT NOT NULL,
            last_sync   TEXT NOT NULL,          -- ISO-8601 UTC
            rows_added  INTEGER DEFAULT 0,
            PRIMARY KEY (symbol, tf_key)
        )
    """)
    print("  ✓  Table ready: sync_log")

    # Raw LTP ticks — one row per 5s poll per symbol
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ticks (
            symbol  TEXT NOT NULL,
            ts      TEXT NOT NULL,   -- ISO-8601 UTC (second precision)
            ltp     REAL NOT NULL,
            PRIMARY KEY (symbol, ts)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ticks_sym_ts
        ON ticks (symbol, ts DESC)
    """)
    print("  ✓  Table ready: ticks")

    conn.commit()
    conn.close()
    print("\nDatabase initialised →", DB_PATH)


if __name__ == "__main__":
    print("Initialising Drishti database...\n")
    init_db()
