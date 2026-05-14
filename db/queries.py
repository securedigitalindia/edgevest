# ============================================================
#  Drishti — db/queries.py
#  All database read/write helpers.
#  No raw SQL anywhere else in the codebase.
# ============================================================

import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional
import pandas as pd

from db.init_db import get_connection, TF_TABLE


# -----------------------------------------------------------
# Write helpers
# -----------------------------------------------------------

def upsert_candles(symbol: str, tf_key: str, df: pd.DataFrame) -> int:
    """
    Insert or replace candles from a DataFrame.
    df must have columns: ts, open, high, low, close, volume
    Returns number of rows written.
    """
    if df.empty:
        return 0

    tbl = TF_TABLE[tf_key]
    records = []
    for _, row in df.iterrows():
        records.append((
            symbol,
            str(row["ts"]),
            _float_or_none(row.get("open")),
            _float_or_none(row.get("high")),
            _float_or_none(row.get("low")),
            _float_or_none(row.get("close")),
            _float_or_none(row.get("volume")),
        ))

    conn = get_connection()
    cur = conn.cursor()
    cur.executemany(f"""
        INSERT OR REPLACE INTO {tbl}
            (symbol, ts, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, records)
    conn.commit()
    conn.close()
    return len(records)


def update_sync_log(symbol: str, tf_key: str, rows_added: int):
    """Record the latest sync timestamp and row count."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO sync_log (symbol, tf_key, last_sync, rows_added)
        VALUES (?, ?, ?, ?)
    """, (symbol, tf_key, now, rows_added))
    conn.commit()
    conn.close()


# -----------------------------------------------------------
# Read helpers
# -----------------------------------------------------------

def get_latest_ts(symbol: str, tf_key: str) -> Optional[str]:
    """Return the most recent candle timestamp for a symbol+TF, or None."""
    tbl = TF_TABLE[tf_key]
    conn = get_connection()
    cur = conn.execute(
        f"SELECT MAX(ts) FROM {tbl} WHERE symbol = ?", (symbol,)
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_candles(symbol: str, tf_key: str, limit: int = 500) -> pd.DataFrame:
    """
    Return the most recent `limit` candles for a symbol+TF as a DataFrame.
    Sorted ascending by ts (oldest first — ready for indicator calc).
    """
    tbl = TF_TABLE[tf_key]
    conn = get_connection()
    df = pd.read_sql_query(f"""
        SELECT ts, open, high, low, close, volume
        FROM {tbl}
        WHERE symbol = ?
        ORDER BY ts DESC
        LIMIT ?
    """, conn, params=(symbol, limit))
    conn.close()

    if df.empty:
        return df

    df = df.sort_values("ts").reset_index(drop=True)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def get_row_count(symbol: str, tf_key: str) -> int:
    """Return total candle count for a symbol+TF."""
    tbl = TF_TABLE[tf_key]
    conn = get_connection()
    cur = conn.execute(
        f"SELECT COUNT(*) FROM {tbl} WHERE symbol = ?", (symbol,)
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_sync_log() -> pd.DataFrame:
    """Return the full sync_log table as a DataFrame."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM sync_log ORDER BY symbol, tf_key", conn)
    conn.close()
    return df


# -----------------------------------------------------------
# Tick helpers (intraday LTP storage)
# -----------------------------------------------------------

def write_ticks(symbol_ltps: dict) -> int:
    """
    Write {symbol: ltp} pairs to the ticks table at the current UTC second.
    Returns number of rows inserted.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    records = [(sym, ts, float(ltp)) for sym, ltp in symbol_ltps.items()]
    conn = get_connection()
    cur = conn.executemany(
        "INSERT OR IGNORE INTO ticks (symbol, ts, ltp) VALUES (?, ?, ?)", records
    )
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def cleanup_ticks(days_to_keep: int = 7) -> int:
    """Delete ticks older than days_to_keep days. Returns number of rows deleted."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    conn = get_connection()
    cur  = conn.execute("DELETE FROM ticks WHERE ts < ?", (cutoff,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def get_ticks(symbol: str, start_utc, end_utc) -> pd.DataFrame:
    """
    Return ticks for symbol in [start_utc, end_utc) sorted ascending.
    start_utc / end_utc: datetime objects with tzinfo.
    """
    def _fmt(dt) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT ts, ltp FROM ticks
        WHERE symbol = ? AND ts >= ? AND ts < ?
        ORDER BY ts
    """, conn, params=(symbol, _fmt(start_utc), _fmt(end_utc)))
    conn.close()
    return df


# -----------------------------------------------------------
# recommended_trades — header table
# -----------------------------------------------------------

_TRADE_COLS = [
    "id", "trigger_name", "symbol", "parent_trade_id",
    "entry_level", "entry_ltp", "entry_time",
    "exit_level", "status", "exit_ltp", "exit_time",
    "margin_required", "margin_final",
]
_TRADE_SELECT = ", ".join(_TRADE_COLS)

_ACCT_TRADE_COLS = [
    "id", "recommended_trade_id", "account_id", "status",
    "entry_time", "exit_time", "note",
]

_ACCT_LEG_COLS = [
    "id", "account_trade_id", "action", "side", "instrument_type",
    "instrument_key", "strike", "expiry_str", "lots", "lot_size", "price", "ts",
]

_LEG_COLS = [
    "id", "trade_id", "action", "side", "instrument_type",
    "instrument_key", "strike", "expiry_str", "lots", "lot_size", "price", "ts",
]
_LEG_SELECT = ", ".join(_LEG_COLS)


def open_recommended_trade(
    trigger_name: str, symbol: str,
    entry_level: float, entry_ltp: float, entry_time: str,
    exit_level: float,
    parent_trade_id:  int   | None = None,
    margin_required:  float | None = None,
    margin_final:     float | None = None,
) -> int:
    """Insert a new open trade header. Returns the new row id."""
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO recommended_trades
            (trigger_name, symbol, parent_trade_id,
             entry_level, entry_ltp, entry_time, exit_level, status,
             margin_required, margin_final)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
    """, (trigger_name, symbol, parent_trade_id,
          entry_level, entry_ltp, entry_time, exit_level,
          margin_required, margin_final))
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def add_trade_legs(trade_id: int, legs: list[dict]) -> None:
    """
    Insert leg rows for a trade.

    Each leg dict must contain:
        action          : 'entry' | 'exit' | 'rollover_out' | 'rollover_in'
        side            : 'BUY' | 'SELL'
        instrument_type : 'FUT' | 'PE' | 'CE' | 'EQ'
        ts              : ISO-8601 UTC string

    Optional leg fields:
        instrument_key, strike, expiry_str, lots, lot_size, price
    """
    records = []
    for leg in legs:
        records.append((
            trade_id,
            leg["action"],
            leg["side"],
            leg["instrument_type"],
            leg.get("instrument_key"),
            _float_or_none(leg.get("strike")),
            leg.get("expiry_str"),
            leg.get("lots", 1),
            leg.get("lot_size", 0),
            _float_or_none(leg.get("price")),
            leg["ts"],
        ))
    conn = get_connection()
    conn.executemany("""
        INSERT INTO trade_legs
            (trade_id, action, side, instrument_type, instrument_key,
             strike, expiry_str, lots, lot_size, price, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, records)
    conn.commit()
    conn.close()


def get_trade_legs(trade_id: int) -> list[dict]:
    """Return all legs for a trade ordered by id (insertion order)."""
    conn = get_connection()
    cur = conn.execute(
        f"SELECT {_LEG_SELECT} FROM trade_legs WHERE trade_id = ? ORDER BY id",
        (trade_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(zip(_LEG_COLS, r)) for r in rows]


def get_open_recommended_trade(symbol: str, entry_level: float) -> Optional[dict]:
    """Return the open trade at entry_level for symbol, or None."""
    conn = get_connection()
    cur = conn.execute(f"""
        SELECT {_TRADE_SELECT} FROM recommended_trades
        WHERE symbol = ? AND entry_level = ? AND status = 'open'
        LIMIT 1
    """, (symbol, entry_level))
    row = cur.fetchone()
    conn.close()
    return dict(zip(_TRADE_COLS, row)) if row else None


def get_all_open_recommended_trades(symbol: str) -> list:
    """Return all open trades for symbol, ordered by entry time."""
    conn = get_connection()
    cur = conn.execute(f"""
        SELECT {_TRADE_SELECT} FROM recommended_trades
        WHERE symbol = ? AND status = 'open'
        ORDER BY entry_time
    """, (symbol,))
    rows = cur.fetchall()
    conn.close()
    return [dict(zip(_TRADE_COLS, r)) for r in rows]


def get_all_open_trades() -> list[dict]:
    """Return all open recommended_trades (used by briefing)."""
    conn = get_connection()
    cur = conn.execute(f"""
        SELECT {_TRADE_SELECT} FROM recommended_trades
        WHERE status = 'open'
        ORDER BY entry_time
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(zip(_TRADE_COLS, r)) for r in rows]


def get_all_recommendations() -> list[dict]:
    """All recommended_trades newest-first, with leg count and account push count."""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT {', '.join('rt.' + c for c in _TRADE_COLS)},
               COUNT(DISTINCT tl.id)  AS leg_count,
               COUNT(DISTINCT at.id)  AS account_count
        FROM recommended_trades rt
        LEFT JOIN trade_legs    tl ON tl.trade_id = rt.id AND tl.action = 'entry'
        LEFT JOIN account_trades at ON at.recommended_trade_id = rt.id
        GROUP BY rt.id
        ORDER BY rt.entry_time DESC
    """).fetchall()
    conn.close()
    n = len(_TRADE_COLS)
    result = []
    for r in rows:
        d = dict(zip(_TRADE_COLS, r[:n]))
        d["leg_count"]     = r[n]
        d["account_count"] = r[n + 1]
        result.append(d)
    return result


def get_today_closed_trades(ist_date) -> list[dict]:
    """
    Return trades exited or rolled today (IST calendar date).
    ist_date: a date object in IST.
    """
    # IST midnight = UTC 18:30 the previous day
    day_start_utc = datetime(ist_date.year, ist_date.month, ist_date.day,
                             tzinfo=timezone.utc) - timedelta(hours=5, minutes=30)
    day_end_utc   = day_start_utc + timedelta(days=1)
    start_str = day_start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str   = day_end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = get_connection()
    cur = conn.execute(f"""
        SELECT {_TRADE_SELECT} FROM recommended_trades
        WHERE status IN ('exited', 'rolled')
          AND exit_time >= ? AND exit_time < ?
        ORDER BY exit_time
    """, (start_str, end_str))
    rows = cur.fetchall()
    conn.close()
    return [dict(zip(_TRADE_COLS, r)) for r in rows]


# -----------------------------------------------------------
# Users
# -----------------------------------------------------------

def get_user_by_google_id(google_id: str) -> dict | None:
    conn = get_connection()
    row  = conn.execute(
        "SELECT id,google_id,email,name,picture,role,trader_id,active FROM users WHERE google_id=?",
        (google_id,)
    ).fetchone()
    conn.close()
    if not row: return None
    return dict(zip(["id","google_id","email","name","picture","role","trader_id","active"], row))


def upsert_user(google_id: str, email: str, name: str, picture: str) -> dict:
    """Create or update a Google user. First-ever user becomes super_admin."""
    from datetime import datetime, timezone
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_connection()

    existing = conn.execute(
        "SELECT id,role FROM users WHERE google_id=?", (google_id,)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE users SET name=?,picture=? WHERE google_id=?",
            (name, picture, google_id)
        )
        conn.commit()
    else:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role  = "super_admin" if count == 0 else "client"
        conn.execute(
            "INSERT INTO users (google_id,email,name,picture,role,created_at) VALUES (?,?,?,?,?,?)",
            (google_id, email, name, picture, role, now)
        )
        conn.commit()

    row = conn.execute(
        "SELECT id,google_id,email,name,picture,role,trader_id,active FROM users WHERE google_id=?",
        (google_id,)
    ).fetchone()
    conn.close()
    return dict(zip(["id","google_id","email","name","picture","role","trader_id","active"], row))


def get_all_users() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT u.id, u.email, u.name, u.picture, u.role, u.active,
               u.trader_id, t.name
        FROM users u
        LEFT JOIN traders t ON t.id = u.trader_id
        ORDER BY u.created_at
    """).fetchall()
    conn.close()
    return [
        {"id": r[0], "email": r[1], "name": r[2], "picture": r[3],
         "role": r[4], "active": bool(r[5]),
         "trader_id": r[6], "trader_name": r[7]}
        for r in rows
    ]


def update_user_role(user_id: int, role: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    conn.commit()
    conn.close()


def update_user_trader(user_id: int, trader_id: int | None) -> None:
    conn = get_connection()
    conn.execute("UPDATE users SET trader_id=? WHERE id=?", (trader_id, user_id))
    conn.commit()
    conn.close()


def get_accounts_for_trader(trader_id: int) -> list[dict]:
    """All accounts belonging to a specific trader."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.id, a.label, a.account_no, a.active,
               t.id, t.name, t.mobile, b.id, b.name
        FROM accounts a
        LEFT JOIN traders t ON t.id = a.trader_id
        LEFT JOIN brokers b ON b.id = a.broker_id
        WHERE a.trader_id = ?
        ORDER BY b.name
    """, (trader_id,)).fetchall()
    conn.close()
    return [
        {"id": r[0], "label": r[1], "account_no": r[2], "active": bool(r[3]),
         "trader_id": r[4], "trader": r[5], "mobile": r[6],
         "broker_id": r[7], "broker": r[8]}
        for r in rows
    ]


# -----------------------------------------------------------
# Brokers / Traders / Accounts
# -----------------------------------------------------------

def get_brokers() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT id, name FROM brokers ORDER BY name").fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1]} for r in rows]


def add_broker(name: str) -> int:
    conn = get_connection()
    cur = conn.execute("INSERT INTO brokers (name) VALUES (?)", (name.strip(),))
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_traders() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, mobile, note FROM traders ORDER BY name"
    ).fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "mobile": r[2], "note": r[3]} for r in rows]


def add_trader(name: str, mobile: str = "", note: str = "") -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO traders (name, mobile, note) VALUES (?, ?, ?)",
        (name.strip(), mobile.strip() or None, note.strip() or None),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_accounts() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.id, a.label, a.account_no, a.active,
               t.id, t.name, t.mobile,
               b.id, b.name
        FROM accounts a
        LEFT JOIN traders t ON t.id = a.trader_id
        LEFT JOIN brokers b ON b.id = a.broker_id
        ORDER BY t.name, b.name
    """).fetchall()
    conn.close()
    return [
        {
            "id":         r[0],
            "label":      r[1],
            "account_no": r[2],
            "active":     bool(r[3]),
            "trader_id":  r[4],
            "trader":     r[5],
            "mobile":     r[6],
            "broker_id":  r[7],
            "broker":     r[8],
        }
        for r in rows
    ]


def add_account(
    trader_id: int, broker_id: int,
    account_no: str = "", label: str = "",
) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO accounts (trader_id, broker_id, account_no, label) VALUES (?, ?, ?, ?)",
        (trader_id, broker_id, account_no.strip() or None, label.strip() or None),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


# -----------------------------------------------------------
# Account trades
# -----------------------------------------------------------

def create_account_trade(
    account_id: int,
    legs: list[dict],
    recommended_trade_id: int | None = None,
    note: str = "",
    entry_time: str | None = None,
) -> int:
    """Insert account_trade + account_trade_legs. Returns new id."""
    from datetime import datetime, timezone
    now = entry_time or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO account_trades
            (recommended_trade_id, account_id, status, entry_time, note)
        VALUES (?, ?, 'open', ?, ?)
    """, (recommended_trade_id, account_id, now, note or None))
    at_id = cur.lastrowid
    conn.executemany("""
        INSERT INTO account_trade_legs
            (account_trade_id, action, side, instrument_type, instrument_key,
             strike, expiry_str, lots, lot_size, price, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (at_id, l["action"], l["side"], l["instrument_type"],
         l.get("instrument_key"), _float_or_none(l.get("strike")),
         l.get("expiry_str"), l.get("lots", 1), l.get("lot_size", 0),
         _float_or_none(l.get("price")), l.get("ts", now))
        for l in legs
    ])
    conn.commit()
    conn.close()
    return at_id


def get_account_trade_legs(account_trade_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        f"SELECT {', '.join(_ACCT_LEG_COLS)} FROM account_trade_legs"
        f" WHERE account_trade_id = ? ORDER BY id",
        (account_trade_id,)
    ).fetchall()
    conn.close()
    return [dict(zip(_ACCT_LEG_COLS, r)) for r in rows]


def get_open_account_trades(account_id: int | None = None) -> list[dict]:
    """Open account_trades with account/trader/broker/symbol info."""
    conn = get_connection()
    where = "WHERE at.status = 'open'"
    params: list = []
    if account_id is not None:
        where += " AND at.account_id = ?"
        params.append(account_id)
    rows = conn.execute(f"""
        SELECT {', '.join('at.' + c for c in _ACCT_TRADE_COLS)},
               a.label, a.account_no,
               tr.name, tr.mobile,
               b.name,
               rt.symbol, rt.trigger_name
        FROM account_trades at
        LEFT JOIN accounts  a  ON a.id  = at.account_id
        LEFT JOIN traders   tr ON tr.id = a.trader_id
        LEFT JOIN brokers   b  ON b.id  = a.broker_id
        LEFT JOIN recommended_trades rt ON rt.id = at.recommended_trade_id
        {where}
        ORDER BY at.entry_time DESC
    """, params).fetchall()
    conn.close()
    n = len(_ACCT_TRADE_COLS)
    result = []
    for r in rows:
        d = dict(zip(_ACCT_TRADE_COLS, r[:n]))
        d["account_label"]  = r[n]
        d["account_no"]     = r[n + 1]
        d["trader_name"]    = r[n + 2]
        d["trader_mobile"]  = r[n + 3]
        d["broker_name"]    = r[n + 4]
        d["symbol"]         = r[n + 5]
        d["trigger_name"]   = r[n + 6]
        result.append(d)
    return result


def mark_account_trade_closed(
    account_trade_id: int,
    exit_legs: list[dict],
    now_utc: str,
    note: str = "",
) -> None:
    """Persist exit legs and mark account_trade as exited."""
    conn = get_connection()
    conn.executemany("""
        INSERT INTO account_trade_legs
            (account_trade_id, action, side, instrument_type, instrument_key,
             strike, expiry_str, lots, lot_size, price, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (account_trade_id, l["action"], l["side"], l["instrument_type"],
         l.get("instrument_key"), _float_or_none(l.get("strike")),
         l.get("expiry_str"), l.get("lots", 1), l.get("lot_size", 0),
         _float_or_none(l.get("price")), now_utc)
        for l in exit_legs
    ])
    conn.execute(
        "UPDATE account_trades SET status='exited', exit_time=?, note=COALESCE(?,note) WHERE id=?",
        (now_utc, note or None, account_trade_id)
    )
    conn.commit()
    conn.close()


def get_trade_chain(trade_id: int) -> list:
    """
    Return all trades in the rollover chain containing trade_id,
    ordered from oldest (root) to newest. Each dict includes a
    'legs' key with that trade's leg rows.
    """
    conn = get_connection()

    # Walk up to root
    root_id = trade_id
    while True:
        cur = conn.execute(
            "SELECT parent_trade_id FROM recommended_trades WHERE id = ?", (root_id,)
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            break
        root_id = row[0]

    # BFS down from root
    chain_ids, queue = [], [root_id]
    while queue:
        current = queue.pop(0)
        chain_ids.append(current)
        cur = conn.execute(
            "SELECT id FROM recommended_trades WHERE parent_trade_id = ?", (current,)
        )
        queue.extend(r[0] for r in cur.fetchall())

    if not chain_ids:
        conn.close()
        return []

    placeholders = ",".join("?" * len(chain_ids))
    cur = conn.execute(f"""
        SELECT {_TRADE_SELECT} FROM recommended_trades
        WHERE id IN ({placeholders})
        ORDER BY entry_time
    """, chain_ids)
    trades = [dict(zip(_TRADE_COLS, r)) for r in cur.fetchall()]

    # Attach legs to each trade
    for t in trades:
        cur2 = conn.execute(
            f"SELECT {_LEG_SELECT} FROM trade_legs WHERE trade_id = ? ORDER BY id",
            (t["id"],)
        )
        t["legs"] = [dict(zip(_LEG_COLS, r)) for r in cur2.fetchall()]

    conn.close()
    return trades


def close_recommended_trade(
    trade_id: int, exit_ltp: float, exit_time: str,
    exit_legs: list[dict] | None = None,
):
    """
    Mark a trade as exited. Optionally insert exit leg rows.
    exit_legs: list of leg dicts (action='exit') with current prices.
    """
    conn = get_connection()
    conn.execute("""
        UPDATE recommended_trades
        SET status = 'exited', exit_ltp = ?, exit_time = ?
        WHERE id = ?
    """, (exit_ltp, exit_time, trade_id))

    if exit_legs:
        records = []
        for leg in exit_legs:
            records.append((
                trade_id,
                leg["action"],
                leg["side"],
                leg["instrument_type"],
                leg.get("instrument_key"),
                _float_or_none(leg.get("strike")),
                leg.get("expiry_str"),
                leg.get("lots", 1),
                leg.get("lot_size", 0),
                _float_or_none(leg.get("price")),
                leg["ts"],
            ))
        conn.executemany("""
            INSERT INTO trade_legs
                (trade_id, action, side, instrument_type, instrument_key,
                 strike, expiry_str, lots, lot_size, price, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, records)

    conn.commit()
    conn.close()


def roll_recommended_trade(
    trade_id: int,
    exit_ltp: float, exit_time: str,
    new_entry_ltp: float, new_exit_level: float,
    rollover_out_legs:  list[dict],
    rollover_in_legs:   list[dict],
    new_margin_required: float | None = None,
    new_margin_final:    float | None = None,
) -> int:
    """
    Close current trade as 'rolled' and open a new row linked via parent_trade_id.
    rollover_out_legs : legs closing the expiring position (action='rollover_out')
    rollover_in_legs  : legs opening the new month position (action='rollover_in')
    Returns the new trade's row id.
    """
    conn = get_connection()

    cur = conn.execute(
        f"SELECT {_TRADE_SELECT} FROM recommended_trades WHERE id = ?", (trade_id,)
    )
    row = cur.fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"recommended_trades id={trade_id} not found")
    old = dict(zip(_TRADE_COLS, row))

    # Mark old as rolled
    conn.execute("""
        UPDATE recommended_trades
        SET status = 'rolled', exit_ltp = ?, exit_time = ?
        WHERE id = ?
    """, (exit_ltp, exit_time, trade_id))

    # Insert rollover_out legs on the old trade
    _insert_legs(conn, trade_id, rollover_out_legs)

    # Create new trade header
    cur2 = conn.execute("""
        INSERT INTO recommended_trades
            (trigger_name, symbol, parent_trade_id,
             entry_level, entry_ltp, entry_time, exit_level, status,
             margin_required, margin_final)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
    """, (
        old["trigger_name"], old["symbol"], trade_id,
        old["entry_level"], new_entry_ltp, exit_time, new_exit_level,
        new_margin_required, new_margin_final,
    ))
    new_id = cur2.lastrowid

    # Insert rollover_in legs on the new trade
    _insert_legs(conn, new_id, rollover_in_legs)

    conn.commit()
    conn.close()
    return new_id


# -----------------------------------------------------------
# Internal
# -----------------------------------------------------------

def _insert_legs(conn, trade_id: int, legs: list[dict]):
    records = []
    for leg in legs:
        records.append((
            trade_id,
            leg["action"],
            leg["side"],
            leg["instrument_type"],
            leg.get("instrument_key"),
            _float_or_none(leg.get("strike")),
            leg.get("expiry_str"),
            leg.get("lots", 1),
            leg.get("lot_size", 0),
            _float_or_none(leg.get("price")),
            leg["ts"],
        ))
    conn.executemany("""
        INSERT INTO trade_legs
            (trade_id, action, side, instrument_type, instrument_key,
             strike, expiry_str, lots, lot_size, price, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, records)


def _float_or_none(val):
    try:
        f = float(val)
        return None if (f != f) else f   # NaN check
    except (TypeError, ValueError):
        return None
