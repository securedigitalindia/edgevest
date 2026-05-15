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


def _migrate_traders_to_users(conn, cur):
    traders_exists = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='traders'"
    ).fetchone()
    if not traders_exists:
        return

    print("  ⚙  Migrating traders → users…", flush=True)
    conn.execute("PRAGMA foreign_keys=OFF")

    users_cols = {row[1] for row in cur.execute("SELECT * FROM pragma_table_info('users')")}
    if "mobile" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN mobile TEXT")
    if "note" not in users_cols:
        cur.execute("ALTER TABLE users ADD COLUMN note TEXT")

    cur.execute("""
        UPDATE users SET
            mobile = (SELECT t.mobile FROM traders t WHERE t.id = users.trader_id),
            note   = (SELECT t.note   FROM traders t WHERE t.id = users.trader_id)
        WHERE trader_id IS NOT NULL
    """)

    cur.execute("SELECT * FROM pragma_table_info('accounts')")
    accounts_cols = {row[1] for row in cur.fetchall()}

    if "user_id" not in accounts_cols:
        cur.execute("""
            ALTER TABLE accounts RENAME TO accounts_old
        """)
        cur.execute("""
            CREATE TABLE accounts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER REFERENCES users(id),
                broker_id  INTEGER REFERENCES brokers(id),
                account_no TEXT,
                label      TEXT,
                active     INTEGER NOT NULL DEFAULT 1
            )
        """)
        cur.execute("""
            INSERT INTO accounts (id, user_id, broker_id, account_no, label, active)
            SELECT a.id,
                   (SELECT u.id FROM users u WHERE u.trader_id = a.trader_id LIMIT 1),
                   a.broker_id, a.account_no, a.label, a.active
            FROM accounts_old a
        """)
        cur.execute("DROP TABLE accounts_old")

    cur.execute("DROP INDEX IF EXISTS idx_accounts_trader_broker")
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_user_broker
        ON accounts (user_id, broker_id)
    """)

    cur.execute("SELECT * FROM pragma_table_info('users')")
    user_col_info = [(row[0], row[1], row[2], row[3], row[4], row[5]) for row in cur.fetchall()]
    has_trader_id = any(row[1] == "trader_id" for row in user_col_info)

    if has_trader_id:
        cur.execute("SELECT id,google_id,email,name,picture,role,mobile,note,active,created_at FROM users")
        user_rows = cur.fetchall()
        cur.execute("ALTER TABLE users RENAME TO users_old")
        cur.execute("""
            CREATE TABLE users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                google_id   TEXT    NOT NULL UNIQUE,
                email       TEXT    NOT NULL UNIQUE,
                name        TEXT    NOT NULL,
                picture     TEXT,
                role        TEXT    NOT NULL DEFAULT 'client',
                mobile      TEXT,
                note        TEXT,
                active      INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT    NOT NULL
            )
        """)
        cur.executemany("""
            INSERT INTO users (id,google_id,email,name,picture,role,mobile,note,active,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, user_rows)
        cur.execute("DROP TABLE users_old")
        # Rebuild accounts FK — SQLite updates the FK text to reference the renamed table
        acc_rows = cur.execute("SELECT id,user_id,broker_id,account_no,label,active FROM accounts").fetchall()
        cur.execute("ALTER TABLE accounts RENAME TO accounts_fk_fix")
        cur.execute("""
            CREATE TABLE accounts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER REFERENCES users(id),
                broker_id  INTEGER REFERENCES brokers(id),
                account_no TEXT,
                label      TEXT,
                active     INTEGER NOT NULL DEFAULT 1
            )
        """)
        cur.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?)", acc_rows)
        cur.execute("DROP TABLE accounts_fk_fix")

        # account_trades references accounts — rebuild to fix its FK text
        at_rows = cur.execute(
            "SELECT id,recommended_trade_id,account_id,status,entry_time,exit_time,note FROM account_trades"
        ).fetchall()
        cur.execute("ALTER TABLE account_trades RENAME TO account_trades_fk_fix")
        cur.execute("""
            CREATE TABLE account_trades (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                recommended_trade_id INTEGER REFERENCES recommended_trades(id),
                account_id           INTEGER NOT NULL REFERENCES accounts(id),
                status               TEXT    NOT NULL DEFAULT 'open',
                entry_time           TEXT    NOT NULL,
                exit_time            TEXT,
                note                 TEXT
            )
        """)
        if at_rows:
            cur.executemany("INSERT INTO account_trades VALUES (?,?,?,?,?,?,?)", at_rows)
        cur.execute("DROP TABLE account_trades_fk_fix")

        # account_trade_legs references account_trades — rebuild too
        atl_rows = cur.execute(
            "SELECT id,account_trade_id,action,side,instrument_type,instrument_key,"
            "strike,expiry_str,lots,lot_size,price,ts FROM account_trade_legs"
        ).fetchall()
        cur.execute("ALTER TABLE account_trade_legs RENAME TO account_trade_legs_fk_fix")
        cur.execute("""
            CREATE TABLE account_trade_legs (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                account_trade_id INTEGER NOT NULL REFERENCES account_trades(id),
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
        if atl_rows:
            cur.executemany("INSERT INTO account_trade_legs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", atl_rows)
        cur.execute("DROP TABLE account_trade_legs_fk_fix")

    cur.execute("DROP TABLE IF EXISTS traders")
    conn.execute("PRAGMA foreign_keys=ON")
    print("  ✓  Migration complete", flush=True)


def init_db():
    """Create all tables and indexes. Idempotent."""
    conn = get_connection()
    cur = conn.cursor()

    _migrate_traders_to_users(conn, cur)

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

    # Strip stale account_id column that references accounts_old (breaks FK checks)
    if "account_id" in existing_cols:
        rt_sql = cur.execute(
            "SELECT sql FROM sqlite_master WHERE name='recommended_trades'"
        ).fetchone()
        if rt_sql and "accounts_old" in (rt_sql[0] or ""):
            keep_cols = ["id", "trigger_name", "symbol", "parent_trade_id",
                         "entry_level", "entry_ltp", "entry_time",
                         "exit_level", "status", "exit_ltp", "exit_time",
                         "margin_required", "margin_final"]
            conn.execute("PRAGMA foreign_keys=OFF")
            cur.execute("ALTER TABLE recommended_trades RENAME TO recommended_trades_acct_fix")
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
            cur.execute(f"""
                INSERT INTO recommended_trades
                SELECT {', '.join(keep_cols)} FROM recommended_trades_acct_fix
            """)
            cur.execute("DROP TABLE recommended_trades_acct_fix")
            conn.execute("PRAGMA foreign_keys=ON")
            existing_cols -= {"account_id"}
            print("  ⚙  Stripped stale account_id from recommended_trades")

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
    # trade_adjustments — one row per adjustment event on a trade
    # adj_type : auto_roll | replace_legs | add_legs | partial_exit | exit
    # -------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trade_adjustments (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id  INTEGER NOT NULL REFERENCES recommended_trades(id),
            adj_type  TEXT    NOT NULL,
            note      TEXT,
            ts        TEXT    NOT NULL
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trade_adjustments_trade_id
        ON trade_adjustments (trade_id)
    """)

    # -------------------------------------------------------
    # trade_legs — one row per leg per event
    # action       : entry | exit
    # side         : BUY | SELL
    # type         : FUT | PE | CE | EQ  (extensible)
    # adjustment_id: NULL = original entry; non-NULL = belongs to an adjustment
    # auto_adjust  : 1 = auto-roll this leg when its expiry arrives
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
            ts               TEXT    NOT NULL,
            adjustment_id    INTEGER REFERENCES trade_adjustments(id),
            auto_adjust      INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trade_legs_trade_id
        ON trade_legs (trade_id)
    """)

    # Add columns to existing DBs that pre-date this schema
    existing_leg_cols = {row[1] for row in cur.execute("SELECT * FROM pragma_table_info('trade_legs')")}
    for col, ddl in [
        ("adjustment_id", "ALTER TABLE trade_legs ADD COLUMN adjustment_id INTEGER REFERENCES trade_adjustments(id)"),
        ("auto_adjust",   "ALTER TABLE trade_legs ADD COLUMN auto_adjust INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col not in existing_leg_cols:
            cur.execute(ddl)

    # Migrate legacy rollover action values
    cur.execute("UPDATE trade_legs SET action='entry' WHERE action='rollover_in'")
    cur.execute("UPDATE trade_legs SET action='exit'  WHERE action='rollover_out'")
    # Migrate legacy 'rolled' trade status
    cur.execute("UPDATE recommended_trades SET status='exited' WHERE status='rolled'")

    print("  ✓  Table ready: recommended_trades + trade_legs + trade_adjustments")

    # -------------------------------------------------------
    # brokers / accounts / users
    # -------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS brokers (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT    NOT NULL UNIQUE
        )
    """)
    print("  ✓  Table ready: brokers")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER REFERENCES users(id),
            broker_id  INTEGER REFERENCES brokers(id),
            account_no TEXT,
            label      TEXT,
            active     INTEGER NOT NULL DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_user_broker
        ON accounts (user_id, broker_id)
    """)
    print("  ✓  Table ready: accounts")

    # -------------------------------------------------------
    # users — Google OAuth login + roles
    # -------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            google_id   TEXT    NOT NULL UNIQUE,
            email       TEXT    NOT NULL UNIQUE,
            name        TEXT    NOT NULL,
            picture     TEXT,
            role        TEXT    NOT NULL DEFAULT 'client',
            mobile      TEXT,
            note        TEXT,
            active      INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    NOT NULL
        )
    """)

    existing_user_cols = {row[1] for row in cur.execute("SELECT * FROM pragma_table_info('users')")}
    for col, ddl in [
        ("mobile", "ALTER TABLE users ADD COLUMN mobile TEXT"),
        ("note",   "ALTER TABLE users ADD COLUMN note   TEXT"),
    ]:
        if col not in existing_user_cols:
            cur.execute(ddl)

    print("  ✓  Table ready: users")

    # user_profiles — trading preferences set during onboarding wizard
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id      INTEGER PRIMARY KEY REFERENCES users(id),
            segment      TEXT,
            risk_type    TEXT,
            trader_type  TEXT,
            focus        TEXT,
            setup_done   INTEGER NOT NULL DEFAULT 0,
            updated_at   TEXT    NOT NULL
        )
    """)
    print("  ✓  Table ready: user_profiles")

    # account_trades — one row per account per recommendation
    cur.execute("""
        CREATE TABLE IF NOT EXISTS account_trades (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            recommended_trade_id INTEGER REFERENCES recommended_trades(id),
            account_id           INTEGER NOT NULL REFERENCES accounts(id),
            status               TEXT    NOT NULL DEFAULT 'open',
            entry_time           TEXT    NOT NULL,
            exit_time            TEXT,
            note                 TEXT
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_account_trades_account
        ON account_trades (account_id, status)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_account_trades_rec
        ON account_trades (recommended_trade_id)
    """)
    print("  ✓  Table ready: account_trades")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS account_trade_legs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            account_trade_id INTEGER NOT NULL REFERENCES account_trades(id),
            action           TEXT    NOT NULL,
            side             TEXT    NOT NULL,
            instrument_type  TEXT    NOT NULL,
            instrument_key   TEXT,
            strike           REAL,
            expiry_str       TEXT,
            lots             INTEGER NOT NULL DEFAULT 1,
            lot_size         INTEGER NOT NULL DEFAULT 0,
            price            REAL,
            ts               TEXT    NOT NULL,
            adjustment_id    INTEGER REFERENCES trade_adjustments(id)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_account_trade_legs_trade
        ON account_trade_legs (account_trade_id)
    """)
    existing_atl_cols = {row[1] for row in cur.execute("SELECT * FROM pragma_table_info('account_trade_legs')")}
    if "adjustment_id" not in existing_atl_cols:
        cur.execute("ALTER TABLE account_trade_legs ADD COLUMN adjustment_id INTEGER REFERENCES trade_adjustments(id)")
    print("  ✓  Table ready: account_trade_legs")

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
