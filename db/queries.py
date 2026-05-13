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
