# ============================================================
#  Drishti — db/init_db.py
#  Creates the SQLite database and all tables.
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
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def table_name(tf_key: str) -> str:
    """Canonical table name for a timeframe key."""
    return f"candles_{tf_key.replace('1', 'tf1').replace('wk', 'wk').replace('mo', 'mo')}"


# Simpler, readable table names
TF_TABLE = {
    "1m":  "candles_1m",
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
                ts          TEXT    NOT NULL,
                open        REAL,
                high        REAL,
                low         REAL,
                close       REAL,
                volume      REAL,
                PRIMARY KEY (symbol, ts)
            )
        """)

        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{tbl}_sym_ts
            ON {tbl} (symbol, ts DESC)
        """)

        print(f"  ✓  Table ready: {tbl}")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            symbol      TEXT NOT NULL,
            tf_key      TEXT NOT NULL,
            last_sync   TEXT NOT NULL,
            rows_added  INTEGER DEFAULT 0,
            PRIMARY KEY (symbol, tf_key)
        )
    """)
    print("  ✓  Table ready: sync_log")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ticks (
            symbol  TEXT NOT NULL,
            ts      TEXT NOT NULL,
            ltp     REAL NOT NULL,
            PRIMARY KEY (symbol, ts)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ticks_sym_ts
        ON ticks (symbol, ts DESC)
    """)
    print("  ✓  Table ready: ticks")

    # -------------------------------------------------------
    # recommended_trades — one row per trade (header only)
    # All leg details live in trade_legs.
    # -------------------------------------------------------

    # Detect old schema (had pe_strike column) and migrate before (re)creating
    existing_cols = {row[1] for row in cur.execute(
        "SELECT * FROM pragma_table_info('recommended_trades')"
    )}
    if "pe_strike" in existing_cols:
        _migrate_trades_to_legs(conn, cur)
        existing_cols = set()   # table was recreated — skip migrations below

    cur.execute("""
        CREATE TABLE IF NOT EXISTS recommended_trades (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_name     TEXT    NOT NULL,
            symbol           TEXT    NOT NULL,
            parent_trade_id  INTEGER REFERENCES recommended_trades(id),

            entry_level      REAL    NOT NULL,
            entry_ltp        REAL    NOT NULL,
            entry_time       TEXT    NOT NULL,

            exit_level       REAL    NOT NULL,
            status           TEXT    NOT NULL DEFAULT 'open',
            exit_ltp         REAL,
            exit_time        TEXT,

            margin_required  REAL,
            margin_final     REAL
        )
    """)

    # Add margin columns to existing DBs that pre-date this addition
    existing_cols = {row[1] for row in cur.execute(
        "SELECT * FROM pragma_table_info('recommended_trades')"
    )}
    for col, ddl in [
        ("margin_required", "ALTER TABLE recommended_trades ADD COLUMN margin_required REAL"),
        ("margin_final",    "ALTER TABLE recommended_trades ADD COLUMN margin_final    REAL"),
    ]:
        if col not in existing_cols:
            cur.execute(ddl)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_recommended_trades_sym_level_status
        ON recommended_trades (symbol, entry_level, status)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_recommended_trades_parent
        ON recommended_trades (parent_trade_id)
    """)

    # -------------------------------------------------------
    # trade_legs — one row per leg per event
    # action : entry | exit | rollover_out | rollover_in
    # side   : BUY | SELL
    # type   : FUT | PE | CE | EQ  (extensible)
    # -------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trade_legs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id         INTEGER NOT NULL REFERENCES recommended_trades(id),
            action           TEXT    NOT NULL,
            side             TEXT    NOT NULL,
            instrument_type  TEXT    NOT NULL,
            instrument_key   TEXT,
            strike           REAL,
            expiry_str       TEXT,
            lots             INTEGER NOT NULL DEFAULT 1,
            lot_size         INTEGER NOT NULL DEFAULT 0,
            price            REAL,
            ts               TEXT    NOT NULL
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trade_legs_trade_id
        ON trade_legs (trade_id)
    """)
    print("  ✓  Table ready: recommended_trades + trade_legs")

    # -------------------------------------------------------
    # brokers / traders / accounts
    # -------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS brokers (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT    NOT NULL UNIQUE
        )
    """)
    print("  ✓  Table ready: brokers")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS traders (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT    NOT NULL,
            mobile  TEXT,
            note    TEXT
        )
    """)
    print("  ✓  Table ready: traders")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            trader_id  INTEGER REFERENCES traders(id),
            broker_id  INTEGER REFERENCES brokers(id),
            account_no TEXT,
            label      TEXT,
            active     INTEGER NOT NULL DEFAULT 1
        )
    """)
    print("  ✓  Table ready: accounts")

    # Add account_id to recommended_trades for existing DBs
    existing_cols = {row[1] for row in cur.execute(
        "SELECT * FROM pragma_table_info('recommended_trades')"
    )}
    if "account_id" not in existing_cols:
        cur.execute(
            "ALTER TABLE recommended_trades ADD COLUMN account_id INTEGER REFERENCES accounts(id)"
        )

    conn.commit()
    conn.close()
    print("\nDatabase initialised →", DB_PATH)


# -------------------------------------------------------
# One-time migration: old flat schema → header + legs
# -------------------------------------------------------

def _migrate_trades_to_legs(conn, cur):
    """
    Migrate from the old schema (pe_strike, expiry_str, fut_lots, …
    columns on recommended_trades) to the new normalised schema where
    leg details live in trade_legs.

    Steps:
      1. Read all existing trade rows.
      2. Rename old table.
      3. Create new slim recommended_trades.
      4. Create trade_legs table.
      5. Copy header data; reconstruct legs from old columns.
      6. Drop old table.
    """
    print("  ⚙  Migrating recommended_trades to new schema…", flush=True)

    # 1. Read everything from the old table
    cur.execute("SELECT * FROM recommended_trades")
    col_names = [d[0] for d in cur.description]
    old_rows  = [dict(zip(col_names, r)) for r in cur.fetchall()]

    # 2. Rename old table out of the way
    cur.execute("ALTER TABLE recommended_trades RENAME TO recommended_trades_old")

    # 3. New slim header table
    cur.execute("""
        CREATE TABLE recommended_trades (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_name     TEXT    NOT NULL,
            symbol           TEXT    NOT NULL,
            parent_trade_id  INTEGER REFERENCES recommended_trades(id),
            entry_level      REAL    NOT NULL,
            entry_ltp        REAL    NOT NULL,
            entry_time       TEXT    NOT NULL,
            exit_level       REAL    NOT NULL,
            status           TEXT    NOT NULL DEFAULT 'open',
            exit_ltp         REAL,
            exit_time        TEXT,
            margin_required  REAL,
            margin_final     REAL
        )
    """)

    # 4. Legs table (may not exist yet)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trade_legs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id         INTEGER NOT NULL REFERENCES recommended_trades(id),
            action           TEXT    NOT NULL,
            side             TEXT    NOT NULL,
            instrument_type  TEXT    NOT NULL,
            instrument_key   TEXT,
            strike           REAL,
            expiry_str       TEXT,
            lots             INTEGER NOT NULL DEFAULT 1,
            lot_size         INTEGER NOT NULL DEFAULT 0,
            price            REAL,
            ts               TEXT    NOT NULL
        )
    """)

    # 5. Copy header rows + reconstruct entry/exit legs
    for t in old_rows:
        cur.execute("""
            INSERT INTO recommended_trades
                (id, trigger_name, symbol, parent_trade_id,
                 entry_level, entry_ltp, entry_time,
                 exit_level, status, exit_ltp, exit_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            t["id"],
            t.get("trigger_name", ""),
            t["symbol"],
            t.get("parent_trade_id"),
            t["entry_level"],
            t["entry_ltp"],
            t["entry_time"],
            t["exit_level"],
            t["status"],
            t.get("exit_ltp"),
            t.get("exit_time"),
        ))

        exp_str    = t.get("expiry_str")
        pe_strike  = t.get("pe_strike")
        entry_time = t["entry_time"]

        if exp_str and pe_strike is not None:
            # Entry legs
            cur.execute("""
                INSERT INTO trade_legs
                    (trade_id, action, side, instrument_type, instrument_key,
                     strike, expiry_str, lots, lot_size, price, ts)
                VALUES (?, 'entry', 'SELL', 'FUT', NULL,
                        NULL, ?, ?, ?, ?, ?)
            """, (t["id"], exp_str,
                  t.get("fut_lots", 1), t.get("fut_lot_size", 0),
                  t.get("entry_fut_price"), entry_time))

            cur.execute("""
                INSERT INTO trade_legs
                    (trade_id, action, side, instrument_type, instrument_key,
                     strike, expiry_str, lots, lot_size, price, ts)
                VALUES (?, 'entry', 'SELL', 'PE', NULL,
                        ?, ?, ?, ?, ?, ?)
            """, (t["id"], pe_strike, exp_str,
                  t.get("pe_lots", 2), t.get("pe_lot_size", 0),
                  t.get("entry_pe_price"), entry_time))

        # Exit / rollover legs
        if t.get("status") in ("exited", "rolled") and t.get("exit_time") and exp_str:
            exit_action = "rollover_out" if t["status"] == "rolled" else "exit"
            exit_time   = t["exit_time"]

            cur.execute("""
                INSERT INTO trade_legs
                    (trade_id, action, side, instrument_type, instrument_key,
                     strike, expiry_str, lots, lot_size, price, ts)
                VALUES (?, ?, 'BUY', 'FUT', NULL,
                        NULL, ?, ?, ?, ?, ?)
            """, (t["id"], exit_action, exp_str,
                  t.get("fut_lots", 1), t.get("fut_lot_size", 0),
                  t.get("exit_fut_price"), exit_time))

            cur.execute("""
                INSERT INTO trade_legs
                    (trade_id, action, side, instrument_type, instrument_key,
                     strike, expiry_str, lots, lot_size, price, ts)
                VALUES (?, ?, 'BUY', 'PE', NULL,
                        ?, ?, ?, ?, ?, ?)
            """, (t["id"], exit_action, pe_strike, exp_str,
                  t.get("pe_lots", 2), t.get("pe_lot_size", 0),
                  t.get("exit_pe_price"), exit_time))

    # 6. Drop old table
    cur.execute("DROP TABLE recommended_trades_old")
    print(f"  ✓  Migrated {len(old_rows)} trade(s) → new schema", flush=True)


if __name__ == "__main__":
    print("Initialising Drishti database...\n")
    init_db()
