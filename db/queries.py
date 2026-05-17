# ============================================================
#  Drishti — db/queries.py
#  All database read/write helpers.
#  No raw SQL anywhere else in the codebase.
# ============================================================

import itertools
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
    "adjustment_id",
]

_ADJ_COLS = ["id", "trade_id", "adj_type", "note", "ts"]

_LEG_COLS = [
    "id", "trade_id", "action", "side", "instrument_type",
    "instrument_key", "strike", "expiry_str", "lots", "lot_size", "price", "ts",
    "adjustment_id", "auto_adjust",
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
    Insert original entry leg rows for a new trade.

    Each leg dict must contain:
        action          : 'entry' | 'exit'
        side            : 'BUY' | 'SELL'
        instrument_type : 'FUT' | 'PE' | 'CE' | 'EQ'
        ts              : ISO-8601 UTC string

    Optional leg fields:
        instrument_key, strike, expiry_str, lots, lot_size, price, auto_adjust
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
            1 if leg.get("auto_adjust") else 0,
        ))
    conn = get_connection()
    conn.executemany("""
        INSERT INTO trade_legs
            (trade_id, action, side, instrument_type, instrument_key,
             strike, expiry_str, lots, lot_size, price, ts, auto_adjust)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def get_original_entry_legs(trade_id: int) -> list[dict]:
    """Original entry legs only — excludes adjustment legs (adjustment_id IS NULL)."""
    conn = get_connection()
    rows = conn.execute(
        f"SELECT {_LEG_SELECT} FROM trade_legs"
        f" WHERE trade_id = ? AND action = 'entry' AND adjustment_id IS NULL ORDER BY id",
        (trade_id,)
    ).fetchall()
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


def get_recommendation(rec_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        f"SELECT {', '.join(_TRADE_COLS)} FROM recommended_trades WHERE id=?", (rec_id,)
    ).fetchone()
    conn.close()
    return dict(zip(_TRADE_COLS, row)) if row else None


def get_all_recommendations() -> list[dict]:
    """All recommended_trades newest-first, with account push count."""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT {', '.join('rt.' + c for c in _TRADE_COLS)},
               COUNT(DISTINCT at.id) AS account_count
        FROM recommended_trades rt
        LEFT JOIN account_trades at ON at.recommended_trade_id = rt.id
        GROUP BY rt.id
        ORDER BY rt.entry_time DESC
    """).fetchall()
    conn.close()
    n = len(_TRADE_COLS)
    result = []
    for r in rows:
        d = dict(zip(_TRADE_COLS, r[:n]))
        d["account_count"] = r[n]
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
        WHERE status = 'exited'
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
        "SELECT id,google_id,email,name,picture,role,mobile,note,active FROM users WHERE google_id=?",
        (google_id,)
    ).fetchone()
    conn.close()
    if not row: return None
    return dict(zip(["id","google_id","email","name","picture","role","mobile","note","active"], row))


def upsert_user(google_id: str, email: str, name: str, picture: str) -> dict:
    """Create or update a Google user. First-ever user becomes super_admin."""
    from datetime import datetime, timezone
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_connection()

    existing = conn.execute(
        "SELECT id FROM users WHERE google_id=?", (google_id,)
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
        "SELECT id,google_id,email,name,picture,role,mobile,note,active FROM users WHERE google_id=?",
        (google_id,)
    ).fetchone()
    conn.close()
    return dict(zip(["id","google_id","email","name","picture","role","mobile","note","active"], row))


def get_all_users() -> list[dict]:
    from datetime import date
    today = date.today().isoformat()
    conn = get_connection()
    rows = conn.execute("""
        SELECT u.id, u.email, u.name, u.picture, u.role, u.active, u.mobile, u.note,
               p.segment, p.risk_type, p.trader_type, p.focus, p.setup_done,
               sp.name, s.status, s.end_date, s.amount_paid
        FROM users u
        LEFT JOIN user_profiles p  ON p.user_id = u.id
        LEFT JOIN subscriptions s  ON s.user_id = u.id AND s.status = 'active'
                                   AND s.end_date >= ?
        LEFT JOIN subscription_plans sp ON sp.id = s.plan_id
        ORDER BY u.created_at
    """, (today,)).fetchall()
    users = [
        {"id": r[0], "email": r[1], "name": r[2], "picture": r[3],
         "role": r[4], "active": bool(r[5]), "mobile": r[6], "note": r[7],
         "profile": {
             "segment":     r[8],
             "risk_type":   r[9],
             "trader_type": r[10],
             "focus":       r[11],
             "setup_done":  bool(r[12]) if r[12] is not None else False,
         },
         "subscription": {
             "plan_name":   r[13],
             "status":      r[14],
             "end_date":    r[15],
             "amount_paid": r[16],
         } if r[13] else None,
         "accounts": []}
        for r in rows
    ]
    uid_index = {u["id"]: u for u in users}
    acc_rows = conn.execute("""
        SELECT a.id, a.user_id, a.label, a.account_no, b.name
        FROM accounts a
        LEFT JOIN brokers b ON b.id = a.broker_id
        ORDER BY b.name
    """).fetchall()
    conn.close()
    for a in acc_rows:
        u = uid_index.get(a[1])
        if u:
            u["accounts"].append({"id": a[0], "label": a[2], "account_no": a[3], "broker": a[4]})
    return users


def update_user_role(user_id: int, role: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    conn.commit()
    conn.close()


def get_accounts_for_user(user_id: int) -> list[dict]:
    """All accounts belonging to a specific user."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.id, a.label, a.account_no, a.active,
               u.id, u.name, u.mobile, b.id, b.name
        FROM accounts a
        LEFT JOIN users u ON u.id = a.user_id
        LEFT JOIN brokers b ON b.id = a.broker_id
        WHERE a.user_id = ?
        ORDER BY b.name
    """, (user_id,)).fetchall()
    conn.close()
    return [
        {"id": r[0], "label": r[1], "account_no": r[2], "active": bool(r[3]),
         "user_id": r[4], "user_name": r[5], "user_mobile": r[6],
         "broker_id": r[7], "broker": r[8]}
        for r in rows
    ]


def update_user_profile(user_id: int, mobile: str = "", note: str = "") -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET mobile=?, note=? WHERE id=?",
            (mobile.strip() or None, note.strip() or None, user_id),
        )
        conn.commit()
    finally:
        conn.close()


# -----------------------------------------------------------
# User trading profiles (onboarding wizard)
# -----------------------------------------------------------

def get_user_trading_profile(user_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT user_id, segment, risk_type, trader_type, focus, setup_done, updated_at"
            " FROM user_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        cols = ["user_id", "segment", "risk_type", "trader_type", "focus", "setup_done", "updated_at"]
        return dict(zip(cols, row))
    finally:
        conn.close()


def upsert_user_trading_profile(
    user_id: int,
    segment: str,
    risk_type: str,
    trader_type: str,
    focus: str,
    setup_done: bool = True,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO user_profiles (user_id, segment, risk_type, trader_type, focus, setup_done, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                segment     = excluded.segment,
                risk_type   = excluded.risk_type,
                trader_type = excluded.trader_type,
                focus       = excluded.focus,
                setup_done  = excluded.setup_done,
                updated_at  = excluded.updated_at
        """, (user_id, segment, risk_type, trader_type, focus, int(setup_done), now))
        conn.commit()
    finally:
        conn.close()


# -----------------------------------------------------------
# Subscription plans
# -----------------------------------------------------------

def get_active_plans() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, name, description, price, duration_days, active, created_at
            FROM subscription_plans WHERE active = 1 ORDER BY price ASC
        """).fetchall()
        cols = ["id", "name", "description", "price", "duration_days", "active", "created_at"]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def get_all_plans() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, name, description, price, duration_days, active, created_at
            FROM subscription_plans ORDER BY id DESC
        """).fetchall()
        cols = ["id", "name", "description", "price", "duration_days", "active", "created_at"]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def create_plan(name: str, description: str, price: int, duration_days: int) -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO subscription_plans (name, description, price, duration_days, active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (name.strip(), description.strip(), price, duration_days, now))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def set_plan_active(plan_id: int, active: bool) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE subscription_plans SET active=? WHERE id=?",
                     (int(active), plan_id))
        conn.commit()
    finally:
        conn.close()


def get_user_subscription(user_id: int) -> dict | None:
    """Return the user's current active subscription, or None."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT s.id, s.user_id, s.plan_id, s.status, s.start_date, s.end_date,
                   s.amount_paid, s.created_at, p.name, p.price, p.duration_days
            FROM subscriptions s
            JOIN subscription_plans p ON p.id = s.plan_id
            WHERE s.user_id = ? AND s.status = 'active'
            ORDER BY s.end_date DESC LIMIT 1
        """, (user_id,)).fetchone()
        if not row:
            return None
        cols = ["id", "user_id", "plan_id", "status", "start_date", "end_date",
                "amount_paid", "created_at", "plan_name", "plan_price", "plan_duration_days"]
        return dict(zip(cols, row))
    finally:
        conn.close()


def is_subscription_valid(user_id: int) -> bool:
    """True if the user has an active subscription that hasn't expired."""
    sub = get_user_subscription(user_id)
    if not sub:
        return False
    from datetime import date
    end = datetime.strptime(sub["end_date"], "%Y-%m-%d").date()
    return end >= date.today()


def activate_subscription(user_id: int, plan_id: int, amount_paid: int = 0) -> int:
    """Expire any existing active sub then create a new active one. Returns new sub id."""
    now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today    = datetime.now(timezone.utc).date()
    conn = get_connection()
    try:
        plan = conn.execute(
            "SELECT duration_days FROM subscription_plans WHERE id=?", (plan_id,)
        ).fetchone()
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")
        duration = plan[0]
        from datetime import timedelta
        end_date = (today + timedelta(days=duration)).isoformat()
        conn.execute("""
            UPDATE subscriptions SET status='expired'
            WHERE user_id=? AND status='active'
        """, (user_id,))
        cur = conn.execute("""
            INSERT INTO subscriptions
                (user_id, plan_id, status, start_date, end_date, amount_paid, created_at)
            VALUES (?, ?, 'active', ?, ?, ?, ?)
        """, (user_id, plan_id, today.isoformat(), end_date, amount_paid, now_str))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def expire_stale_subscriptions() -> int:
    """Mark subscriptions past their end_date as expired. Returns count updated."""
    from datetime import date
    today = date.today().isoformat()
    conn = get_connection()
    try:
        cur = conn.execute("""
            UPDATE subscriptions SET status='expired'
            WHERE status='active' AND end_date < ?
        """, (today,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def get_all_subscriptions() -> list[dict]:
    """All subscriptions with user and plan info — for admin view."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT s.id, u.name, u.email, p.name, s.status,
                   s.start_date, s.end_date, s.amount_paid
            FROM subscriptions s
            JOIN users u ON u.id = s.user_id
            JOIN subscription_plans p ON p.id = s.plan_id
            ORDER BY s.id DESC
        """).fetchall()
        cols = ["id", "user_name", "email", "plan_name", "status",
                "start_date", "end_date", "amount_paid"]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


# -----------------------------------------------------------
# Brokers / Accounts
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


def get_accounts() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.id, a.label, a.account_no, a.active,
               u.id, u.name,
               b.id, b.name
        FROM accounts a
        LEFT JOIN users u ON u.id = a.user_id
        LEFT JOIN brokers b ON b.id = a.broker_id
        ORDER BY u.name, b.name
    """).fetchall()
    conn.close()
    return [
        {
            "id":         r[0],
            "label":      r[1],
            "account_no": r[2],
            "active":     bool(r[3]),
            "user_id":    r[4],
            "user_name":  r[5],
            "broker_id":  r[6],
            "broker":     r[7],
        }
        for r in rows
    ]


def add_account(
    user_id: int, broker_id: int,
    account_no: str = "", label: str = "",
) -> int:
    conn = get_connection()
    exists = conn.execute(
        "SELECT id FROM accounts WHERE user_id=? AND broker_id=?",
        (user_id, broker_id),
    ).fetchone()
    if exists:
        conn.close()
        raise ValueError("An account for this user with this broker already exists.")
    cur = conn.execute(
        "INSERT INTO accounts (user_id, broker_id, account_no, label) VALUES (?, ?, ?, ?)",
        (user_id, broker_id, account_no.strip() or None, label.strip() or None),
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
             strike, expiry_str, lots, lot_size, price, ts, adjustment_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (at_id, l["action"], l["side"], l["instrument_type"],
         l.get("instrument_key"), _float_or_none(l.get("strike")),
         l.get("expiry_str"), l.get("lots", 1), l.get("lot_size", 0),
         _float_or_none(l.get("price")), l.get("ts", now), None)
        for l in legs
    ])
    conn.commit()
    conn.close()
    return at_id


def get_account_trade_legs(account_trade_id: int) -> list[dict]:
    cols = ", ".join(_ACCT_LEG_COLS)
    conn = get_connection()
    rows = conn.execute(
        f"SELECT {cols} FROM account_trade_legs"
        f" WHERE account_trade_id = ? ORDER BY id",
        (account_trade_id,)
    ).fetchall()
    conn.close()
    return [dict(zip(_ACCT_LEG_COLS, r)) for r in rows]


def get_original_account_entry_legs(at_id: int) -> list[dict]:
    """Original entry legs only — excludes adjustment legs (adjustment_id IS NULL)."""
    cols = ", ".join(_ACCT_LEG_COLS)
    conn = get_connection()
    rows = conn.execute(
        f"SELECT {cols} FROM account_trade_legs"
        f" WHERE account_trade_id = ? AND action = 'entry' AND adjustment_id IS NULL ORDER BY id",
        (at_id,)
    ).fetchall()
    conn.close()
    return [dict(zip(_ACCT_LEG_COLS, r)) for r in rows]


def get_applied_account_adjustments(at_id: int) -> list[dict]:
    """Applied adjustments on an account_trade, each with their entry legs."""
    cols = ", ".join(_ACCT_LEG_COLS)
    conn = get_connection()

    rows = conn.execute(
        f"SELECT {cols} FROM account_trade_legs"
        f" WHERE account_trade_id = ? AND action = 'entry' AND adjustment_id IS NOT NULL ORDER BY id",
        (at_id,)
    ).fetchall()
    legs_by_adj: dict[int, list] = {}
    for r in rows:
        leg = dict(zip(_ACCT_LEG_COLS, r))
        legs_by_adj.setdefault(leg["adjustment_id"], []).append(leg)

    if not legs_by_adj:
        conn.close()
        return []

    ph = ",".join("?" * len(legs_by_adj))
    meta_rows = conn.execute(
        f"SELECT id, adj_type, note, ts FROM trade_adjustments WHERE id IN ({ph})",
        list(legs_by_adj.keys()),
    ).fetchall()
    conn.close()

    result = [
        {"id": row[0], "adj_type": row[1], "note": row[2], "ts": row[3],
         "legs": legs_by_adj.get(row[0], [])}
        for row in meta_rows
    ]
    result.sort(key=lambda a: a["id"])
    return result


def get_open_account_trades(account_id: int | None = None) -> list[dict]:
    """Open account_trades with account/user/broker/symbol info."""
    conn = get_connection()
    where = "WHERE at.status = 'open'"
    params: list = []
    if account_id is not None:
        where += " AND at.account_id = ?"
        params.append(account_id)
    rows = conn.execute(f"""
        SELECT {', '.join('at.' + c for c in _ACCT_TRADE_COLS)},
               a.label, a.account_no,
               u.name, u.mobile,
               b.name,
               rt.symbol, rt.trigger_name
        FROM account_trades at
        LEFT JOIN accounts  a  ON a.id  = at.account_id
        LEFT JOIN users     u  ON u.id  = a.user_id
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


def get_closed_account_trades(account_id: int | None = None, user_id: int | None = None) -> list[dict]:
    """Exited account_trades with entry+exit legs for P&L. Filter by account or user."""
    conn = get_connection()
    where = "WHERE at.status = 'exited'"
    params: list = []
    if account_id is not None:
        where += " AND at.account_id = ?"
        params.append(account_id)
    elif user_id is not None:
        where += " AND a.user_id = ?"
        params.append(user_id)
    rows = conn.execute(f"""
        SELECT {', '.join('at.' + c for c in _ACCT_TRADE_COLS)},
               a.label, a.account_no,
               u.name, u.mobile,
               b.name,
               rt.symbol, rt.trigger_name
        FROM account_trades at
        LEFT JOIN accounts  a  ON a.id  = at.account_id
        LEFT JOIN users     u  ON u.id  = a.user_id
        LEFT JOIN brokers   b  ON b.id  = a.broker_id
        LEFT JOIN recommended_trades rt ON rt.id = at.recommended_trade_id
        {where}
        ORDER BY at.exit_time DESC
    """, params).fetchall()

    n = len(_ACCT_TRADE_COLS)
    trades = []
    for r in rows:
        d = dict(zip(_ACCT_TRADE_COLS, r[:n]))
        d["account_label"] = r[n]
        d["account_no"]    = r[n + 1]
        d["trader_name"]   = r[n + 2]
        d["trader_mobile"] = r[n + 3]
        d["broker_name"]   = r[n + 4]
        d["symbol"]        = r[n + 5]
        d["trigger_name"]  = r[n + 6]

        # Fetch legs for this trade
        leg_rows = conn.execute(
            f"SELECT {', '.join(_ACCT_LEG_COLS)} FROM account_trade_legs"
            f" WHERE account_trade_id = ? ORDER BY id",
            (d["id"],)
        ).fetchall()
        legs = [dict(zip(_ACCT_LEG_COLS, lr)) for lr in leg_rows]
        d["entry_legs"] = [l for l in legs if l["action"] == "entry"]
        d["exit_legs"]  = [l for l in legs if l["action"] == "exit"]

        # Compute realized P&L
        pnl = 0.0
        for e, x in itertools.zip_longest(d["entry_legs"], d["exit_legs"], fillvalue={}):
            if e["price"] is not None and x["price"] is not None:
                qty  = e["lots"] * (e["lot_size"] or 1)
                pnl += (e["price"] - x["price"]) * qty if e["side"] == "SELL" \
                       else (x["price"] - e["price"]) * qty
        d["realized_pnl"] = pnl
        trades.append(d)

    conn.close()
    return trades


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
             strike, expiry_str, lots, lot_size, price, ts, adjustment_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (account_trade_id, l["action"], l["side"], l["instrument_type"],
         l.get("instrument_key"), _float_or_none(l.get("strike")),
         l.get("expiry_str"), l.get("lots", 1), l.get("lot_size", 0),
         _float_or_none(l.get("price")), now_utc, None)
        for l in exit_legs
    ])
    conn.execute(
        "UPDATE account_trades SET status='exited', exit_time=?, note=COALESCE(?,note) WHERE id=?",
        (now_utc, note or None, account_trade_id)
    )
    conn.commit()
    conn.close()


def get_current_legs(trade_id: int) -> list[dict]:
    """
    Return currently active legs by netting BUY vs SELL lots per instrument
    across all action='entry' legs (original entry + adjustments).

    Adjustments use the same instrument_key with the opposite side to reduce
    the position. Net zero = fully closed, excluded from result.
    The first-seen leg supplies display metadata (entry price, expiry, etc.)
    for the net position.
    """
    conn = get_connection()
    rows = conn.execute(
        f"SELECT {_LEG_SELECT} FROM trade_legs"
        f" WHERE trade_id = ? AND action = 'entry' ORDER BY id",
        (trade_id,)
    ).fetchall()
    conn.close()

    buy_lots:  dict[str, int]  = {}
    sell_lots: dict[str, int]  = {}
    first_leg: dict[str, dict] = {}

    for row in rows:
        leg = dict(zip(_LEG_COLS, row))
        key = leg["instrument_key"] or str(leg["id"])
        if key not in first_leg:
            first_leg[key] = leg
        if leg["side"] == "BUY":
            buy_lots[key] = buy_lots.get(key, 0) + leg["lots"]
        else:
            sell_lots[key] = sell_lots.get(key, 0) + leg["lots"]

    result = []
    for key in first_leg:
        b   = buy_lots.get(key, 0)
        s   = sell_lots.get(key, 0)
        net = abs(b - s)
        if net == 0:
            continue
        leg = dict(first_leg[key])
        leg["side"] = "BUY" if b > s else "SELL"
        leg["lots"] = net
        result.append(leg)
    return result


def add_trade_adjustment(
    trade_id: int,
    adj_type: str,
    note:     str | None,
    ts:       str,
    legs:     list[dict],
) -> int:
    """
    Record an adjustment on an existing trade.

    All legs are stored as action='entry' with their actual BUY/SELL side.
    get_current_legs nets BUY vs SELL lots per instrument to determine the
    live position — no separate 'exit' action needed for adjustments.

    Returns the new trade_adjustments.id.
    """
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO trade_adjustments (trade_id, adj_type, note, ts) VALUES (?, ?, ?, ?)",
        (trade_id, adj_type, note, ts),
    )
    adj_id = cur.lastrowid

    for leg in legs:
        conn.execute("""
            INSERT INTO trade_legs
                (trade_id, action, side, instrument_type, instrument_key,
                 strike, expiry_str, lots, lot_size, price, ts,
                 adjustment_id, auto_adjust)
            VALUES (?, 'entry', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id,
            leg["side"], leg["instrument_type"],
            leg.get("instrument_key"), _float_or_none(leg.get("strike")),
            leg.get("expiry_str"), leg.get("lots", 1), leg.get("lot_size", 0),
            _float_or_none(leg.get("price")), ts, adj_id,
            1 if leg.get("auto_adjust") else 0,
        ))

    conn.commit()
    conn.close()
    return adj_id


def get_trade_adjustments(trade_id: int) -> list[dict]:
    """
    Return all adjustments for a trade in chronological order.
    Each dict includes 'out_legs' (closed) and 'in_legs' (opened).
    """
    conn = get_connection()
    adj_rows = conn.execute(
        "SELECT id, trade_id, adj_type, note, ts FROM trade_adjustments"
        " WHERE trade_id = ? AND adj_type != 'exit' ORDER BY id",
        (trade_id,),
    ).fetchall()

    adjustments = []
    for row in adj_rows:
        adj = dict(zip(_ADJ_COLS, row))
        leg_rows = conn.execute(
            f"SELECT {_LEG_SELECT} FROM trade_legs"
            f" WHERE trade_id = ? AND adjustment_id = ? ORDER BY id",
            (trade_id, adj["id"]),
        ).fetchall()
        adj["legs"] = [dict(zip(_LEG_COLS, r)) for r in leg_rows]
        adjustments.append(adj)

    conn.close()
    return adjustments


def add_account_adjustment(
    account_trade_id:    int,
    trade_adjustment_id: int,
    legs:                list[dict],
    now_utc:             str,
    adj_type:            str = "",
) -> None:
    """
    Record that an account has applied a trade adjustment.
    Each leg is tagged with trade_adjustment_id so pending checks can skip it.
    If adj_type='exit', the account_trade is also marked exited.
    """
    conn = get_connection()
    conn.executemany("""
        INSERT INTO account_trade_legs
            (account_trade_id, action, side, instrument_type, instrument_key,
             strike, expiry_str, lots, lot_size, price, ts, adjustment_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (account_trade_id, l["action"], l["side"], l["instrument_type"],
         l.get("instrument_key"), _float_or_none(l.get("strike")),
         l.get("expiry_str"), l.get("lots", 1), l.get("lot_size", 0),
         _float_or_none(l.get("price")), now_utc, trade_adjustment_id)
        for l in legs
    ])
    if adj_type == "exit":
        conn.execute(
            "UPDATE account_trades SET status='exited', exit_time=? WHERE id=?",
            (now_utc, account_trade_id),
        )
    conn.commit()
    conn.close()


def get_pending_adjustments_for_account_trade(account_trade_id: int) -> list[dict]:
    """
    Return trade_adjustments on the linked recommendation that this account_trade
    has not yet applied (no account_trade_legs row with that adjustment_id).
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT recommended_trade_id FROM account_trades WHERE id = ?",
        (account_trade_id,),
    ).fetchone()

    if not row or row[0] is None:
        conn.close()
        return []

    rec_id = row[0]
    adj_rows = conn.execute(
        "SELECT id, trade_id, adj_type, note, ts FROM trade_adjustments"
        " WHERE trade_id = ? AND adj_type != 'exit' ORDER BY id",
        (rec_id,),
    ).fetchall()

    applied_ids = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT adjustment_id FROM account_trade_legs"
            " WHERE account_trade_id = ? AND adjustment_id IS NOT NULL",
            (account_trade_id,),
        ).fetchall()
    }

    pending = []
    for row in adj_rows:
        adj = dict(zip(_ADJ_COLS, row))
        if adj["id"] in applied_ids:
            continue
        leg_rows = conn.execute(
            f"SELECT {_LEG_SELECT} FROM trade_legs"
            f" WHERE trade_id = ? AND adjustment_id = ? ORDER BY id",
            (rec_id, adj["id"]),
        ).fetchall()
        adj["legs"] = [dict(zip(_LEG_COLS, r)) for r in leg_rows]
        pending.append(adj)

    conn.close()
    return pending


def close_recommended_trade(
    trade_id: int, exit_ltp: float, exit_time: str,
    exit_legs: list[dict] | None = None,
):
    """Mark a trade as fully exited. Stores exit legs with action='exit' for audit."""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO trade_adjustments (trade_id, adj_type, note, ts) VALUES (?, 'exit', NULL, ?)",
        (trade_id, exit_time),
    )
    adj_id = cur.lastrowid
    for leg in (exit_legs or []):
        conn.execute("""
            INSERT INTO trade_legs
                (trade_id, action, side, instrument_type, instrument_key,
                 strike, expiry_str, lots, lot_size, price, ts, adjustment_id)
            VALUES (?, 'exit', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id, leg["side"], leg["instrument_type"],
            leg.get("instrument_key"), _float_or_none(leg.get("strike")),
            leg.get("expiry_str"), leg.get("lots", 1), leg.get("lot_size", 0),
            _float_or_none(leg.get("price")), exit_time, adj_id,
        ))
    conn.execute(
        "UPDATE recommended_trades SET status='exited', exit_ltp=?, exit_time=? WHERE id=?",
        (exit_ltp, exit_time, trade_id),
    )
    conn.commit()
    conn.close()


def _float_or_none(val):
    try:
        f = float(val)
        return None if (f != f) else f   # NaN check
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Price cache — populated by live poller, read by trade server
# ─────────────────────────────────────────────────────────────────────────────

def update_price_cache(prices: dict):
    """
    Upsert {instrument_key: ltp} into price_cache each poll cycle.
    On the first update of a new trading day, the previous ltp is automatically
    snapshotted into prev_close before being overwritten — no separate API call needed.
    """
    if not prices:
        return
    from zoneinfo import ZoneInfo
    IST      = ZoneInfo("Asia/Kolkata")
    now_utc  = datetime.now(timezone.utc)
    ts       = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    today    = now_utc.astimezone(IST).strftime("%Y-%m-%d")

    conn = get_connection()
    for k, v in prices.items():
        if v is None:
            continue
        row = conn.execute(
            "SELECT ltp, ts, prev_close FROM price_cache WHERE instrument_key = ?", (k,)
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO price_cache (instrument_key, ltp, ts, prev_close) VALUES (?, ?, ?, NULL)",
                (k, v, ts),
            )
        else:
            old_ltp, old_ts, prev_close = row
            if old_ts:
                old_date = (datetime.strptime(old_ts, "%Y-%m-%dT%H:%M:%SZ")
                            .replace(tzinfo=timezone.utc)
                            .astimezone(IST)
                            .strftime("%Y-%m-%d"))
                if old_date < today:
                    # First poll of a new day — yesterday's ltp becomes prev_close
                    prev_close = old_ltp
            conn.execute(
                "UPDATE price_cache SET ltp = ?, ts = ?, prev_close = ? WHERE instrument_key = ?",
                (v, ts, prev_close, k),
            )
    conn.commit()
    conn.close()


def get_cached_prices(keys: list) -> tuple[dict, str | None]:
    """
    Read {instrument_key: ltp} from cache for the given keys.
    Returns (prices_dict, latest_ts_utc_str).
    """
    if not keys:
        return {}, None
    ph   = ",".join("?" * len(keys))
    conn = get_connection()
    rows = conn.execute(
        f"SELECT instrument_key, ltp, ts FROM price_cache WHERE instrument_key IN ({ph})",
        keys,
    ).fetchall()
    conn.close()
    prices = {r[0]: r[1] for r in rows}
    ts     = max((r[2] for r in rows), default=None)
    return prices, ts


def get_cached_spot(keys: list) -> tuple[dict, str | None]:
    """
    Read {instrument_key: {ltp, prev_close}} from cache for the given keys.
    Returns (spot_dict, latest_ts_utc_str).
    """
    if not keys:
        return {}, None
    ph   = ",".join("?" * len(keys))
    conn = get_connection()
    rows = conn.execute(
        f"SELECT instrument_key, ltp, prev_close, ts FROM price_cache WHERE instrument_key IN ({ph})",
        keys,
    ).fetchall()
    conn.close()
    spot = {r[0]: {"ltp": r[1], "prev_close": r[2]} for r in rows}
    ts   = max((r[3] for r in rows), default=None)
    return spot, ts




def get_open_trade_ikeys() -> list[str]:
    """All distinct instrument_keys currently held in open recommended + account trades."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT tl.instrument_key
        FROM   trade_legs tl
        JOIN   recommended_trades rt ON rt.id = tl.trade_id
        WHERE  rt.status = 'open'
          AND  tl.instrument_key IS NOT NULL
          AND  tl.action = 'entry'
        UNION
        SELECT DISTINCT atl.instrument_key
        FROM   account_trade_legs atl
        JOIN   account_trades at2 ON at2.id = atl.account_trade_id
        WHERE  at2.status = 'open'
          AND  atl.instrument_key IS NOT NULL
          AND  atl.action = 'entry'
    """).fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]
