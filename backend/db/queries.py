# ============================================================
#  Drishti — db/queries.py
#  All database read/write helpers.
#  No raw SQL anywhere else in the codebase.
# ============================================================

import itertools
import sqlite3
from datetime import datetime, timezone, timedelta, date
from typing import Optional
import pandas as pd

from db.init_db import get_connection, TF_TABLE


# -----------------------------------------------------------
# Write helpers
# -----------------------------------------------------------

def upsert_candles(symbol: str, tf_key: str, df: pd.DataFrame) -> int:
    """
    Insert or replace candles from a DataFrame.
    df must have columns: ts, open, high, low, close, volume (oi optional).
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
            _float_or_none(row.get("oi")),
        ))

    conn = get_connection()
    cur = conn.cursor()
    cur.executemany(f"""
        INSERT OR REPLACE INTO {tbl}
            (symbol, ts, open, high, low, close, volume, oi)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        SELECT ts, open, high, low, close, volume, oi
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


def delete_candles(symbol: str, tf_key: str) -> int:
    """
    Delete all candles for a symbol+TF. Used by bootstrap to guarantee a
    clean reseed — starting from an empty table means the fresh Upstox
    fetch that follows can never collide with (and thus never leave
    behind) a stale duplicate row from an earlier provider/run.
    Returns number of rows deleted.
    """
    tbl = TF_TABLE[tf_key]
    conn = get_connection()
    cur = conn.execute(f"DELETE FROM {tbl} WHERE symbol = ?", (symbol,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


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


def write_option_chain_snapshot(rows: list[dict]) -> int:
    """
    Batch-write option-chain snapshot rows to option_chain_5m.
    Each row is a dict with keys matching the table columns:
    ts, symbol, spot_ltp, expiry_type, expiry_rank, expiry_date,
    strike, opt_type, ltp, oi, iv.

    Uses INSERT OR IGNORE — the UNIQUE(ts, symbol, expiry_date, strike, opt_type)
    constraint is idempotency protection against a poller restart re-capturing
    the same 5-min slot, not a dedup-and-overwrite pattern.

    Returns number of rows actually inserted (rows silently skipped by the
    UNIQUE constraint are not counted).
    """
    if not rows:
        return 0

    records = [(
        r["ts"], r["symbol"], float(r["spot_ltp"]), r["expiry_type"],
        int(r["expiry_rank"]), r["expiry_date"], float(r["strike"]), r["opt_type"],
        _float_or_none(r.get("ltp")), _float_or_none(r.get("oi")), _float_or_none(r.get("iv")),
    ) for r in rows]

    conn = get_connection()
    cur = conn.executemany("""
        INSERT OR IGNORE INTO option_chain_5m
            (ts, symbol, spot_ltp, expiry_type, expiry_rank, expiry_date, strike, opt_type, ltp, oi, iv)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, records)
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def get_merged_cadence_dates(symbol: str) -> list[str]:
    """
    Distinct expiry_date values captured for a symbol, merging the
    'weekly' and 'monthly' expiry_type buckets and sorting ascending.

    Upstox's own weekly/monthly split excludes the monthly-coinciding
    date from the weekly bucket even though it's calendar-wise 7 days
    from its neighbors (e.g. weekly=[07-21,08-04,08-11], monthly=[07-28,08-25]
    — all 7 days apart). The stored expiry_rank column is bucket-relative,
    not cadence-relative, so callers needing a true weekly-spaced sequence
    (calendar-spread strategies) must use this merged rank instead —
    see docs/prd/calendar-spread-strike-scoring.md.
    """
    conn = get_connection()
    cur = conn.execute("""
        SELECT DISTINCT expiry_date FROM option_chain_5m
        WHERE symbol = ? AND expiry_type IN ('weekly', 'monthly')
        ORDER BY expiry_date
    """, (symbol,))
    dates = [row[0] for row in cur.fetchall()]
    conn.close()
    return dates


def get_option_chain_ltp(symbol: str, opt_type: str, expiry_date: str, strike: float, ts: str) -> Optional[float]:
    """Single CE/PE ltp lookup at an exact captured strike/expiry/timestamp, or None if not captured."""
    conn = get_connection()
    cur = conn.execute("""
        SELECT ltp FROM option_chain_5m
        WHERE symbol = ? AND opt_type = ? AND expiry_date = ? AND strike = ? AND ts = ?
    """, (symbol, opt_type, expiry_date, strike, ts))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_latest_option_chain_ts(symbol: str, date_prefix: str | None = None) -> Optional[str]:
    """
    Most recent option_chain_5m ts for a symbol. Pass date_prefix (e.g. '2026-07-21')
    to get the latest ts within just that UTC calendar day instead of overall latest.
    """
    conn = get_connection()
    if date_prefix:
        cur = conn.execute(
            "SELECT MAX(ts) FROM option_chain_5m WHERE symbol = ? AND ts LIKE ?",
            (symbol, f"{date_prefix}%"),
        )
    else:
        cur = conn.execute("SELECT MAX(ts) FROM option_chain_5m WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else None


def get_option_chain_capture_days(symbol: str, expiry_date: str) -> list[str]:
    """
    Distinct UTC calendar dates (as 'YYYY-MM-DD' prefixes) on which any row for the
    given expiry_date contract was captured. Used to enumerate which DTE values are
    available for the DTE-proxy method (one calendar day of capture = one DTE data
    point for whichever contract is 'imminent' that day) — see the
    calendar-spread-debit-proxy skill.
    """
    conn = get_connection()
    cur = conn.execute("""
        SELECT DISTINCT substr(ts, 1, 10) FROM option_chain_5m
        WHERE symbol = ? AND expiry_date = ?
        ORDER BY 1
    """, (symbol, expiry_date))
    days = [row[0] for row in cur.fetchall()]
    conn.close()
    return days


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
    "margin_required", "margin_final", "display_code", "note", "risk_level",
]
_TRADE_SELECT = ", ".join(_TRADE_COLS)

_ACCT_TRADE_COLS = [
    "id", "recommended_trade_id", "account_id", "status",
    "entry_time", "exit_time", "note", "margin",
]

_ACCT_LEG_COLS = [
    "id", "account_trade_id", "action", "side", "instrument_type",
    "instrument_key", "strike", "expiry_str", "lots", "lot_size", "price", "ts",
    "adjustment_id", "margin",
]

_ADJ_COLS = ["id", "trade_id", "adj_type", "note", "ts"]

_LEG_COLS = [
    "id", "trade_id", "action", "side", "instrument_type",
    "instrument_key", "strike", "expiry_str", "lots", "lot_size", "price", "ts",
    "adjustment_id", "auto_adjust",
]
_LEG_SELECT = ", ".join(_LEG_COLS)


def display_code_prefix(expiry_strs) -> str:
    """
    {MON}{YY} for the NEAREST (earliest) expiry among the given legs'
    expiry_str values (e.g. "AUG26") — or "EQ" if none of them have one at
    all (a pure equity trade, no F&O legs). expiry_strs is any iterable of
    strings/None, each expected in "%d %b %Y" form (e.g. "25 Aug 2026"),
    matching how it's stored on trade_legs everywhere else — unparseable or
    missing entries are ignored, not treated as an error.

    Deliberately picks the nearest, not just whichever leg happens to be
    first — a calendar spread's legs (e.g. a near/far PE pair) aren't
    necessarily inserted in expiry order, so "first leg" would be fragile.
    """
    from datetime import datetime
    dates = []
    for s in expiry_strs:
        if not s:
            continue
        try:
            dates.append(datetime.strptime(s, "%d %b %Y"))
        except ValueError:
            continue
    if not dates:
        return "EQ"
    nearest = min(dates)
    return nearest.strftime("%b").upper() + nearest.strftime("%y")


def _compute_display_code(conn, expiry_strs) -> str:
    """
    Human-friendly trade identifier: {MON}{YY}-{N} for the nearest expiry
    among the given legs (e.g. AUG26-1, SEP26-2), or EQ-{N} for a pure
    equity trade with no expiry at all. N increments per prefix across every
    trade ever assigned it, in creation order. expiry_strs is any iterable
    of each leg's expiry_str (some may be None/missing).
    """
    prefix = display_code_prefix(expiry_strs)
    count = conn.execute(
        "SELECT COUNT(*) FROM recommended_trades WHERE display_code LIKE ?",
        (f"{prefix}-%",),
    ).fetchone()[0]
    return f"{prefix}-{count + 1}"


def open_recommended_trade(
    trigger_name: str, symbol: str,
    entry_level: float, entry_ltp: float, entry_time: str,
    exit_level: float,
    parent_trade_id:  int   | None = None,
    margin_required:  float | None = None,
    margin_final:     float | None = None,
    margin_at_entry:  float | None = None,
    expiry_strs       = None,  # iterable of each leg's expiry_str, for display_code
    note:             str   | None = None,
    risk_level:       str   | None = None,
) -> int:
    """Insert a new open trade header. Returns the new row id."""
    conn = get_connection()
    display_code = _compute_display_code(conn, expiry_strs or [])
    cur = conn.execute("""
        INSERT INTO recommended_trades
            (trigger_name, symbol, parent_trade_id,
             entry_level, entry_ltp, entry_time, exit_level, status,
             margin_required, margin_final, margin_at_entry, display_code, note, risk_level)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)
    """, (trigger_name, symbol, parent_trade_id,
          entry_level, entry_ltp, entry_time, exit_level,
          margin_required, margin_final, margin_at_entry, display_code, note or None, risk_level))
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


def get_monthly_report(year: int, month: int) -> dict:
    """
    Live rollup of recommended_trades/trade_legs for one IST calendar month
    (see docs/prd/monthly-recommendation-report.md for full mechanics).

    "Month" = [month_start_utc, effective_end_utc) where effective_end_utc is
    min(next_month_start_utc, now_utc) — this is what makes an in-progress
    "current month" and a finished past month share the exact same code path.
    A month whose start is still in the future naturally yields an inverted
    (empty) range and zeroed results, with no special-casing required.

    Returns:
        {
          "positions_entered":      int,   # every row entered in [month_start, effective_end) — a pure date-range count, unrelated to the two counts below
          "new_position_count":     int,   # of margin_positions (below): entered THIS month (rolls included — see note)
          "carried_position_count": int,   # of margin_positions: entered in an EARLIER month, still touching margin this month
          "margin_series":      [{"date": "YYYY-MM-DD", "margin": float}, ...],
          "peak_margin_used":   float,
          "avg_margin_used":    float,  # mean of margin_series' own values — the ROI denominator (not peak_margin_used)
          "margin_positions":   [{"trade_id": int, "symbol": str, "display_code": str|None,
                                   "entry_date": "YYYY-MM-DD", "exit_date": "YYYY-MM-DD"|None,
                                   "margin_at_entry": float, "realized_pnl": float|None}, ...],
          "pnl_events":         [{"entry_date": "YYYY-MM-DD", "exit_date": "YYYY-MM-DD", "trade_id": int,
                                   "symbol": str, "display_code": str|None, "realized_pnl": float}, ...],
          "realized_pnl_total": float,
        }

    margin_positions lists every row that contributes to margin_series at any
    point in this month (open positions carried forward included) — this is
    what actually makes up peak_margin_used, not just its number. Its
    realized_pnl is non-null only when that same row also exited within this
    month (i.e. it also appears in pnl_events) — null for anything still open
    or carried forward, since there's no outcome to show yet.

    new_position_count/carried_position_count are a two-way, mutually-
    exclusive partition of margin_positions (always sum to
    len(margin_positions)), purely by entry timing — parent_trade_id plays
    no role: a roll that happened this month counts as "new" (a rollover
    creates a genuinely new trade row with its own freshly-computed margin;
    parent_trade_id only records lineage, it doesn't make the row a
    continuation of the parent's own identity — see roll_recommended_
    trade()'s docstring), exactly like a non-rollover fresh open; a roll
    from an earlier month that's still touching margin this month is
    "carried", exactly like any other still-running older position.
    Rollover status as a third, separate axis was tried (2026-08-31) and
    reverted — readers only care "did this show up on the desk this month
    or not," not the underlying lineage mechanics; a two-way split by timing
    alone answers that directly. This is a different split than
    positions_entered, which is a pure date-range count unrelated to
    margin_positions' membership — don't conflate the two.
    """
    IST_OFFSET = timedelta(hours=5, minutes=30)

    month_start_utc = datetime(year, month, 1, tzinfo=timezone.utc) - IST_OFFSET
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    next_month_start_utc = datetime(next_year, next_month, 1, tzinfo=timezone.utc) - IST_OFFSET
    now_utc = datetime.now(timezone.utc)
    effective_end_utc = min(next_month_start_utc, now_utc)

    month_start_str   = month_start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    effective_end_str = effective_end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _ist_date(utc_str: str):
        dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return (dt + IST_OFFSET).date()

    conn = get_connection()

    # --- 1. Positions entered ---------------------------------------------
    positions_entered = conn.execute(
        "SELECT COUNT(*) FROM recommended_trades WHERE entry_time >= ? AND entry_time < ?",
        (month_start_str, effective_end_str),
    ).fetchone()[0]

    # --- 2. Margin day-by-day series + peak ---------------------------------
    # One query fetches every row that could possibly overlap the month's day
    # range, then we walk IST calendar days in Python (avoids N per-day queries).
    margin_rows = conn.execute("""
        SELECT id, symbol, display_code, entry_time, exit_time, status, margin_at_entry, parent_trade_id
        FROM recommended_trades
        WHERE entry_time < ? AND (status = 'open' OR exit_time >= ?)
    """, (effective_end_str, month_start_str)).fetchall()

    # A roll's exit and its replacement's entry share the exact same instant
    # (roll_recommended_trade() stamps both with the same exit_time —
    # queries.py's own roll function, see its "atomically close old_trade_id
    # ... open replacement" docstring) — the old position was never actually
    # live at the same time as its replacement, not even for a moment. At
    # day granularity that self-roll pair still lands on the same calendar
    # day, so naively summing "every row live at any point on day d" double-
    # counts that one day's margin (old row's exit day + new row's entry day
    # both include it). Map parent id -> child's entry_date so the day-walk
    # below can treat the parent's own exit_date as *exclusive* only in this
    # specific same-day-rollover case — every other exit (including a normal
    # exit with no rollover) keeps the inclusive-exit-day rule the PRD's
    # carry-forward rule locks in (recommended-report PRD, "Margin" section).
    child_entry_date_by_parent_id = {}
    for row in margin_rows:
        if row[7] is not None:  # parent_trade_id
            child_entry_date_by_parent_id[row[7]] = _ist_date(row[3])  # entry_time

    intervals = []        # (entry_date, exit_date_or_None, margin_at_entry, exit_inclusive) — for the day-walk below
    margin_positions = []  # display-friendly version of the same rows, for the UI
    # Two-way split of margin_positions, mutually exclusive, summing to
    # len(margin_positions) always — purely by entry timing, parent_trade_id
    # plays no role: a roll that happened this month is "new" (its own row,
    # its own freshly-computed margin — a roll is a genuinely new position,
    # not a continuation of the parent's own identity, see roll_recommended_
    # trade()'s docstring), exactly the same as a non-rollover fresh open;
    # a roll from an earlier month that's still open/still touched margin
    # this month is "carried forward", exactly the same as any other
    # position that's just still running from before this month. Rollover
    # status was tried as a third axis (2026-08-31) and rejected — the
    # reader only cares "did this show up on the desk this month or not",
    # not the underlying lineage mechanics.
    # A row with margin_at_entry IS NULL (unrecoverable — e.g. a rolled
    # trade whose contract expired before its margin could ever be
    # backfilled, see scripts/backfill_exited_rolled_trade_margins.py)
    # still touched margin this month in every sense that matters to the
    # Booked/Open and New/Carried counts below — it just contributes 0 to
    # the margin *sum*, exactly like the PRD's original data-model note for
    # margin_series already says NULL rows should. Skipping it from
    # margin_positions entirely (as this used to do) silently shrank
    # totalPositions while pnl_events (bookedCount)'s own query has no such
    # filter — Total and Booked drift out of the "Total = Booked + Open"
    # invariant the moment one exists, deflating "Open" below its true
    # value (2026-09 incident: a prod month showed 6 open at month-end but
    # 8 still open today, which is impossible if the invariant holds — the
    # missing 2 were NULL-margin trades subtracted via bookedCount without
    # ever being added to totalPositions). Only `intervals` (which feeds the
    # margin day-by-day sum/peak/avg) still excludes NULL-margin rows —
    # correctly, since there's no real number to contribute there.
    new_position_count, carried_position_count = 0, 0
    for trade_id, symbol, display_code, entry_time, exit_time, status, margin_at_entry, parent_trade_id in margin_rows:
        entry_date = _ist_date(entry_time)
        exit_date  = _ist_date(exit_time) if (status != "open" and exit_time) else None
        if margin_at_entry is not None:
            exit_inclusive = not (exit_date is not None and child_entry_date_by_parent_id.get(trade_id) == exit_date)
            intervals.append((entry_date, exit_date, margin_at_entry, exit_inclusive))
        entered_this_month = month_start_str <= entry_time < effective_end_str
        if entered_this_month:
            new_position_count += 1
        else:
            carried_position_count += 1
        margin_positions.append({
            "trade_id":        trade_id,
            "symbol":          symbol,
            "display_code":    display_code,
            "entry_date":      entry_date.isoformat(),
            "exit_date":       exit_date.isoformat() if exit_date else None,
            "margin_at_entry": round(margin_at_entry, 2) if margin_at_entry is not None else None,
        })

    first_day = date(year, month, 1)
    last_day  = date(next_year, next_month, 1) - timedelta(days=1)
    today_ist = (now_utc + IST_OFFSET).date()
    walk_end  = min(last_day, today_ist)

    margin_series  = []
    peak_margin    = 0.0
    margin_sum     = 0.0
    d = first_day
    while d <= walk_end:
        total = sum(
            margin for entry_date, exit_date, margin, exit_inclusive in intervals
            if entry_date <= d and (exit_date is None or (exit_date >= d if exit_inclusive else exit_date > d))
        )
        margin_series.append({"date": d.isoformat(), "margin": round(total, 2)})
        peak_margin = max(peak_margin, total)
        margin_sum += total
        d += timedelta(days=1)
    avg_margin = margin_sum / len(margin_series) if margin_series else 0.0

    # --- 3. Realized P&L — per-exit + month total ---------------------------
    # Match legs by instrument_key (not positional zip()) — see PRD for why
    # the positional method used by GET /api/recommendations can mis-pair legs.
    exited_rows = conn.execute(f"""
        SELECT {_TRADE_SELECT} FROM recommended_trades
        WHERE status = 'exited' AND exit_time >= ? AND exit_time < ?
        ORDER BY exit_time
    """, (month_start_str, effective_end_str)).fetchall()
    exited_trades = [dict(zip(_TRADE_COLS, r)) for r in exited_rows]

    conn.close()

    pnl_events = []
    realized_pnl_total = 0.0
    for t in exited_trades:
        legs       = get_trade_legs(t["id"])
        entry_legs = [l for l in legs if l["action"] == "entry"]
        exit_legs  = [l for l in legs if l["action"] == "exit"]

        total, has_pnl = 0.0, False
        for e in entry_legs:
            x = next((xl for xl in exit_legs
                      if xl["instrument_key"] and xl["instrument_key"] == e["instrument_key"]),
                     None)
            if x is None or e["price"] is None or x["price"] is None:
                continue
            qty = e["lots"] * (e["lot_size"] or 1)
            total += (e["price"] - x["price"]) * qty if e["side"] == "SELL" \
                     else (x["price"] - e["price"]) * qty
            has_pnl = True

        if has_pnl:
            pnl_events.append({
                "entry_date":   _ist_date(t["entry_time"]).isoformat(),
                "exit_date":    _ist_date(t["exit_time"]).isoformat(),
                "trade_id":     t["id"],
                "symbol":       t["symbol"],
                "display_code": t["display_code"],
                "realized_pnl": round(total, 2),
            })
            realized_pnl_total += total

    # A row that both blocked margin AND exited within this same month shows
    # up in both lists — attach its realized P&L onto the margin_positions
    # entry too, so "what did this position that closed this month actually
    # make" is visible right next to the margin it was holding, not just in
    # the separate P&L list.
    pnl_by_trade = {e["trade_id"]: e["realized_pnl"] for e in pnl_events}
    for p in margin_positions:
        p["realized_pnl"] = pnl_by_trade.get(p["trade_id"])

    # Sort so the UI can show the biggest margin contributors / most recent
    # exits first without re-sorting client-side. A None margin_at_entry
    # (unrecoverable, see the note above) sorts last, not first — treating
    # it as 0 for ordering purposes only, never for the actual margin math.
    margin_positions.sort(key=lambda p: p["margin_at_entry"] if p["margin_at_entry"] is not None else -1, reverse=True)

    return {
        "positions_entered":      positions_entered,
        "new_position_count":     new_position_count,
        "carried_position_count": carried_position_count,
        "margin_series":          margin_series,
        "peak_margin_used":       round(peak_margin, 2),
        "avg_margin_used":        round(avg_margin, 2),
        "margin_positions":       margin_positions,
        "pnl_events":             pnl_events,
        "realized_pnl_total":     round(realized_pnl_total, 2),
    }


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


def get_user_by_email(email: str) -> dict | None:
    conn = get_connection()
    row  = conn.execute(
        "SELECT id,google_id,email,name,picture,role,mobile,note,active FROM users WHERE email=?",
        (email,)
    ).fetchone()
    conn.close()
    if not row: return None
    return dict(zip(["id","google_id","email","name","picture","role","mobile","note","active"], row))


def upsert_user(google_id: str, email: str, name: str, picture: str,
                 referrer_user_id: int | None = None) -> dict:
    """
    Create or update a Google user. First-ever user becomes super_admin.

    referrer_user_id: the resolved referrer's user id (already looked up
    from a valid ?ref= code by /auth/google — never a raw code here), only
    ever applied inside the new-row branch below, i.e. only for a genuinely
    brand-new google_id, never retroactively on a returning user. See
    docs/prd/refer-and-earn.md's "Signup flow" / "Self-referral guard".
    """
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
        if role == "client":
            new_uid = conn.execute("SELECT id FROM users WHERE google_id=?", (google_id,)).fetchone()[0]
            # Defensive self-referral guard (structurally unreachable — new_uid
            # is freshly INSERT-ed and can't equal a pre-existing referrer_user_id
            # — kept cheap and future-proof, see PRD).
            if referrer_user_id and referrer_user_id != new_uid:
                from config import REFERRAL_SIGNUP_BONUS_GEMS
                _award_credits_tx(conn, new_uid, REFERRAL_SIGNUP_BONUS_GEMS, "referral_signup_bonus",
                                  ref_id=str(referrer_user_id), note="Referral signup bonus")
                conn.execute("""
                    INSERT INTO referrals (referrer_user_id, referee_user_id, status, created_at)
                    VALUES (?, ?, 'pending', ?)
                """, (referrer_user_id, new_uid, now))
            else:
                from config import SIGNUP_CREDITS
                _award_credits_tx(conn, new_uid, SIGNUP_CREDITS, "signup_bonus", ref_id=None, note="Welcome bonus")
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


# ── Refer & Earn — docs/prd/refer-and-earn.md ─────────────────

# Uppercase, unambiguous alphabet — excludes 0/O/1/I.
_REFERRAL_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_REFERRAL_CODE_LENGTH   = 7


def _generate_referral_code() -> str:
    import random
    return "".join(random.choices(_REFERRAL_CODE_ALPHABET, k=_REFERRAL_CODE_LENGTH))


def get_user_by_referral_code(code: str) -> dict | None:
    """Case-insensitive lookup by users.referral_code."""
    if not code:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT id,google_id,email,name,picture,role,mobile,note,active"
        " FROM users WHERE referral_code IS NOT NULL AND UPPER(referral_code)=UPPER(?)",
        (code,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return dict(zip(["id","google_id","email","name","picture","role","mobile","note","active"], row))


def get_or_create_referral_code(user_id: int) -> str:
    """
    Lazily generate + persist this user's referral_code on first read (first
    call to GET /api/my-referrals) — no backfill for pre-existing rows, same
    "generate on demand" posture as recommended_trades.display_code. Retries
    on UNIQUE collision (7-char, 33-symbol alphabet — collisions are rare;
    this loop exists for correctness, not because collisions are expected).
    """
    conn = get_connection()
    try:
        row = conn.execute("SELECT referral_code FROM users WHERE id=?", (user_id,)).fetchone()
        if row and row[0]:
            return row[0]
        for _ in range(10):
            code = _generate_referral_code()
            try:
                conn.execute("UPDATE users SET referral_code=? WHERE id=?", (code, user_id))
                conn.commit()
                return code
            except sqlite3.IntegrityError:
                conn.rollback()
                continue
        raise RuntimeError(f"Could not generate a unique referral code for user {user_id}")
    finally:
        conn.close()


def get_referral_stats(user_id: int) -> dict:
    """
    Counts from `referrals`; gems_earned from `credit_transactions` (the
    ledger is the source of truth, not a redundant running total — same
    posture as user_credits.balance elsewhere).
    """
    conn = get_connection()
    try:
        referred_count = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_user_id=?", (user_id,)
        ).fetchone()[0]
        rewarded_count = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_user_id=? AND status='rewarded'", (user_id,)
        ).fetchone()[0]
        gems_earned = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM credit_transactions"
            " WHERE user_id=? AND reason='referral_reward'",
            (user_id,)
        ).fetchone()[0]
        return {
            "referred_count": referred_count,
            "rewarded_count": rewarded_count,
            "gems_earned":    gems_earned,
        }
    finally:
        conn.close()


def get_referral_history(user_id: int) -> list[dict]:
    """Referrer's own referral list — referee name/status/dates only (no email; see PRD open questions)."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT r.id, r.referee_user_id, u.name AS referee_name,
                   r.status, r.created_at, r.rewarded_at
            FROM referrals r
            JOIN users u ON u.id = r.referee_user_id
            WHERE r.referrer_user_id = ?
            ORDER BY r.created_at DESC
        """, (user_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_accounts_for_user(user_id: int) -> list[dict]:
    """All accounts (real + game virtual) belonging to a specific user."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.id, a.label, a.account_no, a.active, a.game_id, a.capital,
               u.id, u.name, u.mobile, b.id, b.name, g.status
        FROM accounts a
        LEFT JOIN users u ON u.id = a.user_id
        LEFT JOIN brokers b ON b.id = a.broker_id
        LEFT JOIN games g ON g.id = a.game_id
        WHERE a.user_id = ?
        ORDER BY a.game_id IS NOT NULL, b.name
    """, (user_id,)).fetchall()
    conn.close()
    return [
        {"id": r[0], "label": r[1], "account_no": r[2], "active": bool(r[3]),
         "game_id": r[4], "capital": r[5],
         "user_id": r[6], "user_name": r[7], "user_mobile": r[8],
         "broker_id": r[9], "broker": r[10], "game_status": r[11]}
        for r in rows
    ]


def create_game_virtual_account(game_id: int, user_id: int, label: str, capital: float) -> int:
    """Create a virtual account for a user in a leaderboard game. Idempotent."""
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM accounts WHERE game_id = ? AND user_id = ?", (game_id, user_id)
    ).fetchone()
    if existing:
        conn.close()
        return existing[0]
    cur = conn.execute(
        "INSERT INTO accounts (user_id, broker_id, game_id, capital, label, active) VALUES (?, NULL, ?, ?, ?, 1)",
        (user_id, game_id, capital, label)
    )
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    return aid


def get_game_virtual_account(game_id: int, user_id: int) -> dict | None:
    """Return the virtual account for a user in a leaderboard game."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, label, capital FROM accounts WHERE game_id = ? AND user_id = ?",
        (game_id, user_id)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "label": row[1], "capital": row[2] or 0}


def get_account_portfolio(account_id: int, prices: dict) -> dict:
    """
    Compute portfolio summary for any account (real or game virtual).
    prices = {instrument_key: ltp}
    Returns label, capital, positions (open legs), realized_pnl, unrealized_pnl, total_pnl.
    """
    conn = get_connection()
    row  = conn.execute("SELECT id, label, capital FROM accounts WHERE id = ?", (account_id,)).fetchone()
    conn.close()
    if not row:
        return {"account_id": None, "label": None, "capital": None, "pnl": 0,
                "realized_pnl": 0, "unrealized_pnl": 0, "positions": []}

    label   = row[1]
    capital = row[2]

    # Realized P&L from closed trades
    realized_pnl = 0.0
    for t in get_closed_account_trades(account_id=account_id):
        legs = get_account_trade_legs(t["id"])
        entry_legs = [l for l in legs if l["action"] == "entry"]
        exit_legs  = [l for l in legs if l["action"] == "exit"]
        for xl in exit_legs:
            el = next((l for l in entry_legs if l["instrument_key"] == xl["instrument_key"]), None)
            if not el:
                continue
            qty = el["lots"] * (el["lot_size"] or 1)
            if el["side"] == "BUY":
                realized_pnl += (xl["price"] - el["price"]) * qty
            else:
                realized_pnl += (el["price"] - xl["price"]) * qty

    # Unrealized P&L and used capital from open trades
    unrealized_pnl = 0.0
    used_capital   = 0.0
    positions = []
    for t in get_open_account_trades(account_id=account_id):
        used_capital += t.get("margin") or 0
        legs = get_account_trade_legs(t["id"])
        exited_ikeys = {l["instrument_key"] for l in legs if l["action"] == "exit"}
        current_legs = [l for l in legs if l["action"] == "entry"
                        and l["instrument_key"] not in exited_ikeys
                        and not l["adjustment_id"]]
        for l in current_legs:
            ltp = prices.get(l["instrument_key"]) if l["instrument_key"] else None
            qty = l["lots"] * (l["lot_size"] or 1)
            leg_pnl = 0.0
            if ltp:
                leg_pnl = (ltp - l["price"]) * qty if l["side"] == "BUY" \
                          else (l["price"] - ltp) * qty
            unrealized_pnl += leg_pnl
            positions.append({
                "trade_id":        t["id"],
                "symbol":          t["symbol"],
                "side":            l["side"],
                "instrument_type": l["instrument_type"],
                "strike":          l["strike"],
                "expiry_str":      l["expiry_str"],
                "lots":            l["lots"],
                "lot_size":        l["lot_size"],
                "entry_price":     l["price"],
                "instrument_key":  l["instrument_key"],
                "ltp":             ltp,
                "pnl":             round(leg_pnl, 2),
            })

    total_pnl = realized_pnl + unrealized_pnl
    return {
        "account_id":     account_id,
        "label":          label,
        "capital":        capital,
        "used_capital":   round(used_capital, 2),
        "realized_pnl":   round(realized_pnl, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "pnl":            round(total_pnl, 2),
        "positions":      positions,
    }


def get_game_portfolio(game_id: int, user_id: int, prices: dict) -> dict:
    """Compute portfolio for a user's virtual game account. Delegates to get_account_portfolio."""
    acct = get_game_virtual_account(game_id, user_id)
    if not acct:
        return {"account_id": None, "label": None, "capital": 0, "pnl": 0,
                "realized_pnl": 0, "unrealized_pnl": 0, "positions": []}
    return get_account_portfolio(acct["id"], prices)


def update_account_capital(account_id: int, capital: float) -> None:
    """Set (or replace) the capital for an account."""
    conn = get_connection()
    conn.execute("UPDATE accounts SET capital = ? WHERE id = ?", (capital, account_id))
    conn.commit()
    conn.close()


def add_account_capital(account_id: int, amount: float) -> float:
    """Add amount to existing capital (top-up). Returns new capital."""
    conn = get_connection()
    conn.execute(
        "UPDATE accounts SET capital = COALESCE(capital, 0) + ? WHERE id = ?",
        (amount, account_id)
    )
    conn.commit()
    new_cap = conn.execute("SELECT capital FROM accounts WHERE id = ?", (account_id,)).fetchone()[0]
    conn.close()
    return new_cap


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

        if setup_done:
            # Referrer payout (docs/prd/refer-and-earn.md — "Referrer payout,
            # triggered by setup_done"). This upsert runs unconditionally on
            # every POST /api/profile, incl. repeat setup_done=true saves from
            # ProfileDetails.jsx — idempotency is enforced at the DB layer:
            # only the first call for this referee finds a 'pending' row to
            # flip (referee_user_id is UNIQUE), every subsequent call affects
            # 0 rows and is a guaranteed no-op.
            cur = conn.execute("""
                UPDATE referrals SET status='rewarded', rewarded_at=?
                WHERE referee_user_id=? AND status='pending'
            """, (now, user_id))
            if cur.rowcount == 1:
                ref_row = conn.execute(
                    "SELECT referrer_user_id FROM referrals WHERE referee_user_id=?",
                    (user_id,)
                ).fetchone()
                if ref_row:
                    from config import REFERRAL_REWARD_GEMS
                    _award_credits_tx(conn, ref_row[0], REFERRAL_REWARD_GEMS, "referral_reward",
                                      ref_id=str(user_id), note="Referral reward")

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
            SELECT id, name, description, price, gem_cost, duration_days, active, created_at
            FROM subscription_plans WHERE active = 1 ORDER BY price ASC
        """).fetchall()
        cols = ["id", "name", "description", "price", "gem_cost", "duration_days", "active", "created_at"]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def get_all_plans() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, name, description, price, gem_cost, duration_days, active, created_at
            FROM subscription_plans ORDER BY id DESC
        """).fetchall()
        cols = ["id", "name", "description", "price", "gem_cost", "duration_days", "active", "created_at"]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def create_plan(name: str, description: str, price: int, duration_days: int, gem_cost: int = 0) -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO subscription_plans (name, description, price, gem_cost, duration_days, active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (name.strip(), description.strip(), price, gem_cost, duration_days, now))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_plan(plan_id: int, **kwargs) -> None:
    allowed = {"name", "description", "price", "gem_cost", "duration_days"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn = get_connection()
    try:
        conn.execute(f"UPDATE subscription_plans SET {set_clause} WHERE id = ?",
                     list(fields.values()) + [plan_id])
        conn.commit()
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
    account_no: str = "", label: str = "", capital: float | None = None,
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
        "INSERT INTO accounts (user_id, broker_id, account_no, label, capital) VALUES (?, ?, ?, ?, ?)",
        (user_id, broker_id, account_no.strip() or None, label.strip() or None, capital),
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
    margin: float | None = None,
) -> int:
    """Insert account_trade + account_trade_legs. Returns new id."""
    from datetime import datetime, timezone
    now = entry_time or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO account_trades
            (recommended_trade_id, account_id, status, entry_time, note, margin)
        VALUES (?, ?, 'open', ?, ?, ?)
    """, (recommended_trade_id, account_id, now, note or None, margin))
    at_id = cur.lastrowid
    conn.executemany("""
        INSERT INTO account_trade_legs
            (account_trade_id, action, side, instrument_type, instrument_key,
             strike, expiry_str, lots, lot_size, price, ts, adjustment_id, margin)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (at_id, l["action"], l["side"], l["instrument_type"],
         l.get("instrument_key"), _float_or_none(l.get("strike")),
         l.get("expiry_str"), l.get("lots", 1), l.get("lot_size", 0),
         _float_or_none(l.get("price")), l.get("ts", now), None,
         _float_or_none(l.get("margin")))
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
               rt.symbol, rt.trigger_name, rt.display_code, rt.risk_level
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
        d["display_code"]   = r[n + 7]
        d["risk_level"]     = r[n + 8]
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
               rt.symbol, rt.trigger_name, rt.display_code, rt.risk_level
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
        d["display_code"]  = r[n + 7]
        d["risk_level"]    = r[n + 8]

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
            if e.get("price") is not None and x.get("price") is not None:
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
    mark_exited: bool = True,
) -> None:
    """
    Persist exit legs. Marks account_trade as exited by default; pass
    mark_exited=False for a partial exit (e.g. auto-exiting only the legs a
    recommendation could price) that should leave the trade 'open' with its
    remaining unmatched legs still active.
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
         _float_or_none(l.get("price")), now_utc, None)
        for l in exit_legs
    ])
    if mark_exited:
        conn.execute(
            "UPDATE account_trades SET status='exited', exit_time=?, note=COALESCE(?,note) WHERE id=?",
            (now_utc, note or None, account_trade_id)
        )
    conn.commit()
    conn.close()


def get_current_legs(trade_id: int) -> list[dict]:
    """
    Return currently active legs by netting BUY vs SELL lots per instrument
    across ALL legs for the trade — action='entry' (original entry + same-
    side/opposite-side adjustments) and action='exit' alike.

    Adjustments use the same instrument_key with the opposite side to reduce
    the position, whether that offsetting leg is tagged 'entry' (the older
    convention — get_current_legs nets it out either way) or 'exit' (used for
    a mid-trade close that's been explicitly recorded as one, e.g. a rolled-
    away leg backfilled after the fact). Net zero = fully closed, excluded
    from result. The first-seen leg supplies display metadata (entry price,
    expiry, etc.) for the net position — always an 'entry' row in practice,
    since entries are always inserted before the exit that closes them.
    """
    conn = get_connection()
    rows = conn.execute(
        f"SELECT {_LEG_SELECT} FROM trade_legs"
        f" WHERE trade_id = ? ORDER BY id",
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


def get_pending_exit_for_account_trade(account_trade_id: int) -> dict | None:
    """
    Return the exit adjustment if the linked recommendation has been exited
    but this account trade is still open (status='open').
    Returns None if no exit is pending.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT at.recommended_trade_id, rt.status, rt.exit_time"
        " FROM account_trades at"
        " LEFT JOIN recommended_trades rt ON rt.id = at.recommended_trade_id"
        " WHERE at.id = ? AND at.status = 'open'",
        (account_trade_id,),
    ).fetchone()

    if not row or not row[0] or row[1] != "exited":
        conn.close()
        return None

    rec_id    = row[0]
    exit_time = row[2]

    exit_adj = conn.execute(
        "SELECT id, trade_id, adj_type, note, ts FROM trade_adjustments"
        " WHERE trade_id = ? AND adj_type = 'exit' ORDER BY id DESC LIMIT 1",
        (rec_id,),
    ).fetchone()

    if not exit_adj:
        conn.close()
        return {"exit_time": exit_time, "legs": []}

    adj = dict(zip(_ADJ_COLS, exit_adj))
    leg_rows = conn.execute(
        f"SELECT {_LEG_SELECT} FROM trade_legs"
        f" WHERE trade_id = ? AND adjustment_id = ? ORDER BY id",
        (rec_id, adj["id"]),
    ).fetchall()
    adj["legs"] = [dict(zip(_LEG_COLS, r)) for r in leg_rows]

    conn.close()
    return adj


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


def roll_recommended_trade(
    old_trade_id: int, exit_time: str, out_legs: list[dict],
    new_trigger_name: str, new_symbol: str, new_entry_level: float,
    new_entry_ltp: float, new_exit_level: float, in_legs: list[dict],
    note: str | None = None,
    risk_level: str | None = None,
    margin_required:  float | None = None,
    margin_final:     float | None = None,
    margin_at_entry:  float | None = None,
) -> int:
    """
    Roll a trade forward: atomically close old_trade_id (exit legs = out_legs)
    and open a new trade (parent_trade_id=old_trade_id) with in_legs as its
    entry legs — one transaction, so there's never a moment where neither the
    old nor the new trade satisfies (symbol, entry_level, status='open'), which
    would let the entry-signal dedup check (get_open_recommended_trade) think
    the level is free.

    Replaces the old add_trade_adjustment(adj_type='auto_roll') approach: every
    trade is now always either fully open or fully exited, so realized P&L
    from a roll is available immediately via the normal exit path instead of
    needing special handling for a partially-closed still-open trade.

    new_entry_level/new_symbol should normally just be the same as the old
    trade's, so get_open_recommended_trade() keeps recognizing the level as
    occupied — the trigger's dedup logic doesn't care whether a trade is an
    original or a rolled successor, only (symbol, entry_level, status).

    A roll is really two separate trade lifecycle events (the old trade
    exits, a genuinely new one opens) — parent_trade_id is lineage tracking
    only, not a reason to skip or defer margin computation. margin_required/
    margin_final/margin_at_entry must be computed by the caller for the new
    in_legs (the same way any freshly-opened trade's margin is computed,
    e.g. Nifty500MultipleTrigger's entry path) and passed in here so the new
    row gets its margin atomically, in the same INSERT as everything else —
    never left to a separate follow-up UPDATE that can silently fail or run
    too late (see backfill_exited_rolled_trade_margins.py for the 2026-08
    incident this caused when margin was patched on in a second step).

    Returns the new trade's id.
    """
    conn = get_connection()
    try:
        # --- close old trade ---
        cur = conn.execute(
            "INSERT INTO trade_adjustments (trade_id, adj_type, note, ts) VALUES (?, 'exit', 'Rolled forward', ?)",
            (old_trade_id, exit_time),
        )
        adj_id = cur.lastrowid
        for leg in out_legs:
            conn.execute("""
                INSERT INTO trade_legs
                    (trade_id, action, side, instrument_type, instrument_key,
                     strike, expiry_str, lots, lot_size, price, ts, adjustment_id)
                VALUES (?, 'exit', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                old_trade_id, leg["side"], leg["instrument_type"],
                leg.get("instrument_key"), _float_or_none(leg.get("strike")),
                leg.get("expiry_str"), leg.get("lots", 1), leg.get("lot_size", 0),
                _float_or_none(leg.get("price")), exit_time, adj_id,
            ))
        exit_ltp = out_legs[0]["price"] if out_legs else None
        conn.execute(
            "UPDATE recommended_trades SET status='exited', exit_ltp=?, exit_time=? WHERE id=?",
            (exit_ltp, exit_time, old_trade_id),
        )

        # --- open new, linked trade ---
        display_code = _compute_display_code(conn, [l.get("expiry_str") for l in in_legs])
        cur2 = conn.execute("""
            INSERT INTO recommended_trades
                (trigger_name, symbol, parent_trade_id,
                 entry_level, entry_ltp, entry_time, exit_level, status,
                 margin_required, margin_final, margin_at_entry, display_code, note, risk_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)
        """, (new_trigger_name, new_symbol, old_trade_id,
              new_entry_level, new_entry_ltp, exit_time, new_exit_level,
              margin_required, margin_final, margin_at_entry, display_code, note or None, risk_level))
        new_trade_id = cur2.lastrowid

        for leg in in_legs:
            conn.execute("""
                INSERT INTO trade_legs
                    (trade_id, action, side, instrument_type, instrument_key,
                     strike, expiry_str, lots, lot_size, price, ts, auto_adjust)
                VALUES (?, 'entry', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                new_trade_id, leg["side"], leg["instrument_type"],
                leg.get("instrument_key"), _float_or_none(leg.get("strike")),
                leg.get("expiry_str"), leg.get("lots", 1), leg.get("lot_size", 0),
                _float_or_none(leg.get("price")), exit_time,
                1 if leg.get("auto_adjust") else 0,
            ))

        conn.commit()
        return new_trade_id
    except Exception:
        conn.rollback()
        raise
    finally:
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
    IST     = ZoneInfo("Asia/Kolkata")
    now_utc = datetime.now(timezone.utc)
    ts      = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    today   = now_utc.astimezone(IST).strftime("%Y-%m-%d")

    keys = [k for k, v in prices.items() if v is not None]
    if not keys:
        return

    conn = get_connection()
    # One SELECT for all keys — avoids N round-trips inside the write transaction
    ph  = ",".join("?" * len(keys))
    existing = {
        r[0]: (r[1], r[2], r[3])
        for r in conn.execute(
            f"SELECT instrument_key, ltp, ts, prev_close FROM price_cache WHERE instrument_key IN ({ph})",
            keys,
        ).fetchall()
    }

    for k in keys:
        v = prices[k]
        if k not in existing:
            conn.execute(
                "INSERT INTO price_cache (instrument_key, ltp, ts, prev_close) VALUES (?, ?, ?, NULL)",
                (k, v, ts),
            )
        else:
            old_ltp, old_ts, prev_close = existing[k]
            if old_ts:
                old_date = (datetime.strptime(old_ts, "%Y-%m-%dT%H:%M:%SZ")
                            .replace(tzinfo=timezone.utc)
                            .astimezone(IST)
                            .strftime("%Y-%m-%d"))
                if old_date < today:
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




def delete_account_trade(account_trade_id: int) -> None:
    """Hard-delete an open account trade and all its legs."""
    conn = get_connection()
    conn.execute("DELETE FROM account_trade_legs WHERE account_trade_id = ?", (account_trade_id,))
    conn.execute("DELETE FROM account_trades WHERE id = ? AND status = 'open'", (account_trade_id,))
    conn.commit()
    conn.close()


def delete_recommendation(trade_id: int) -> None:
    """Hard-delete an open recommendation, its legs and adjustments."""
    conn = get_connection()
    linked = conn.execute(
        "SELECT COUNT(*) FROM account_trades WHERE recommended_trade_id = ?", (trade_id,)
    ).fetchone()[0]
    if linked:
        conn.close()
        raise ValueError(f"Cannot delete: {linked} account trade{'s' if linked > 1 else ''} linked to this recommendation")
    conn.execute("DELETE FROM trade_legs WHERE trade_id = ?", (trade_id,))
    conn.execute("DELETE FROM trade_adjustments WHERE trade_id = ?", (trade_id,))
    conn.execute("DELETE FROM recommended_trades WHERE id = ? AND status = 'open'", (trade_id,))
    conn.commit()
    conn.close()


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


# ============================================================
#  Games system
# ============================================================

import json as _json


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Game CRUD ────────────────────────────────────────────────

def create_game(title: str, description: str, game_type: str, symbol: str | None,
                start_time: str, end_time: str, reward_pool: int, winner_count: int,
                initial_cash: int, created_by: int) -> int:
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO games (title, description, game_type, symbol, status,
                           start_time, end_time, reward_pool, winner_count,
                           initial_cash, created_by, created_at)
        VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)
    """, (title, description, game_type, symbol, start_time, end_time,
          reward_pool, winner_count, initial_cash, created_by, _now_utc()))
    gid = cur.lastrowid
    conn.commit()
    conn.close()
    return gid


def get_game(game_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_games(status: str | None = None) -> list[dict]:
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM games WHERE status = ? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM games ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_game(game_id: int, **kwargs) -> None:
    allowed = {"title", "description", "symbol", "start_time", "end_time",
               "reward_pool", "winner_count", "initial_cash"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn = get_connection()
    conn.execute(f"UPDATE games SET {set_clause} WHERE id = ?",
                 list(fields.values()) + [game_id])
    conn.commit()
    conn.close()


def set_game_status(game_id: int, status: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE games SET status = ? WHERE id = ?", (status, game_id))
    conn.commit()
    conn.close()


def delete_game(game_id: int) -> None:
    conn = get_connection()
    status = conn.execute("SELECT status FROM games WHERE id = ?", (game_id,)).fetchone()
    if not status or status[0] != "draft":
        conn.close()
        raise ValueError("Only draft games can be deleted")
    conn.execute("DELETE FROM game_questions WHERE game_id = ?", (game_id,))
    conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
    conn.commit()
    conn.close()


# ── MCQ questions ────────────────────────────────────────────

def save_game_questions(game_id: int, questions: list[dict]) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM game_questions WHERE game_id = ?", (game_id,))
    for i, q in enumerate(questions):
        conn.execute("""
            INSERT INTO game_questions (game_id, order_num, question,
                                        option_a, option_b, option_c, option_d, correct_opt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (game_id, i, q["question"],
              q["option_a"], q["option_b"], q["option_c"], q["option_d"],
              q["correct_opt"].upper()))
    conn.commit()
    conn.close()


def get_game_questions(game_id: int, include_answer: bool = False) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM game_questions WHERE game_id = ? ORDER BY order_num", (game_id,)
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        if not include_answer:
            d.pop("correct_opt", None)
        out.append(d)
    return out


# ── Entries ──────────────────────────────────────────────────

def submit_entry(game_id: int, user_id: int, entry_data: dict) -> int:
    now = _now_utc()
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM game_entries WHERE game_id = ? AND user_id = ?", (game_id, user_id)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE game_entries SET entry_data = ?, submitted_at = ? WHERE id = ?",
            (_json.dumps(entry_data), now, existing[0])
        )
        eid = existing[0]
    else:
        cur = conn.execute("""
            INSERT INTO game_entries (game_id, user_id, entry_data, submitted_at)
            VALUES (?, ?, ?, ?)
        """, (game_id, user_id, _json.dumps(entry_data), now))
        eid = cur.lastrowid
    conn.commit()
    conn.close()
    return eid


def get_entry(game_id: int, user_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM game_entries WHERE game_id = ? AND user_id = ?", (game_id, user_id)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["entry_data"] = _json.loads(d["entry_data"])
    return d


def list_entries(game_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT ge.*, u.name as user_name
        FROM game_entries ge
        JOIN users u ON u.id = ge.user_id
        WHERE ge.game_id = ?
        ORDER BY ge.rank ASC NULLS LAST, ge.submitted_at ASC
    """, (game_id,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["entry_data"] = _json.loads(d["entry_data"])
        out.append(d)
    return out


def entry_count(game_id: int) -> int:
    conn = get_connection()
    n = conn.execute(
        "SELECT COUNT(*) FROM game_entries WHERE game_id = ?", (game_id,)
    ).fetchone()[0]
    conn.close()
    return n


# ── Virtual portfolio (leaderboard) ─────────────────────────

def add_virtual_trade(game_id: int, user_id: int, symbol: str,
                      action: str, price: float, quantity: int) -> None:
    conn = get_connection()
    game = conn.execute("SELECT initial_cash, status FROM games WHERE id = ?", (game_id,)).fetchone()
    if not game or game["status"] != "active":
        conn.close()
        raise ValueError("Game is not active")

    vtrades = conn.execute(
        "SELECT * FROM virtual_trades WHERE game_id = ? AND user_id = ? ORDER BY traded_at",
        (game_id, user_id)
    ).fetchall()

    cash = game["initial_cash"]
    holdings: dict[str, int] = {}
    for t in vtrades:
        sym, act, px, qty = t["symbol"], t["action"], t["price"], t["quantity"]
        if act == "BUY":
            cash -= px * qty
            holdings[sym] = holdings.get(sym, 0) + qty
        else:
            cash += px * qty
            holdings[sym] = holdings.get(sym, 0) - qty

    if action == "BUY":
        cost = price * quantity
        if cost > cash:
            conn.close()
            raise ValueError(f"Insufficient cash (available ₹{cash:,.0f})")
    else:
        held = holdings.get(symbol, 0)
        if quantity > held:
            conn.close()
            raise ValueError(f"Only {held} units held for {symbol}")

    conn.execute("""
        INSERT INTO virtual_trades (game_id, user_id, symbol, action, price, quantity, traded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (game_id, user_id, symbol, action.upper(), price, quantity, _now_utc()))
    conn.commit()
    conn.close()


def get_virtual_portfolio(game_id: int, user_id: int,
                          current_prices: dict[str, float] | None = None) -> dict:
    conn = get_connection()
    game = conn.execute("SELECT initial_cash FROM games WHERE id = ?", (game_id,)).fetchone()
    if not game:
        conn.close()
        return {}
    initial_cash = game["initial_cash"]

    vtrades = conn.execute(
        "SELECT * FROM virtual_trades WHERE game_id = ? AND user_id = ? ORDER BY traded_at",
        (game_id, user_id)
    ).fetchall()
    conn.close()

    cash = initial_cash
    positions: dict[str, dict] = {}  # symbol → {qty, cost}
    trades_out = []
    for t in vtrades:
        sym, act, px, qty = t["symbol"], t["action"], t["price"], t["quantity"]
        if act == "BUY":
            cash -= px * qty
            if sym not in positions:
                positions[sym] = {"qty": 0, "cost": 0.0}
            positions[sym]["qty"] += qty
            positions[sym]["cost"] += px * qty
        else:
            cash += px * qty
            if sym in positions:
                avg = positions[sym]["cost"] / positions[sym]["qty"] if positions[sym]["qty"] else 0
                positions[sym]["qty"] -= qty
                positions[sym]["cost"] -= avg * qty
                if positions[sym]["qty"] <= 0:
                    del positions[sym]
        trades_out.append(dict(t))

    portfolio_value = cash
    pos_out = []
    for sym, p in positions.items():
        ltp = (current_prices or {}).get(sym)
        cur_val = ltp * p["qty"] if ltp else None
        avg_price = p["cost"] / p["qty"] if p["qty"] else 0
        pos_out.append({
            "symbol": sym, "qty": p["qty"],
            "avg_price": round(avg_price, 2),
            "ltp": ltp,
            "value": round(cur_val, 2) if cur_val is not None else None,
            "pnl": round(cur_val - p["cost"], 2) if cur_val is not None else None,
        })
        if cur_val is not None:
            portfolio_value += cur_val

    pnl = portfolio_value - initial_cash
    return {
        "initial_cash": initial_cash,
        "cash": round(cash, 2),
        "portfolio_value": round(portfolio_value, 2),
        "pnl": round(pnl, 2),
        "positions": pos_out,
        "trades": trades_out,
    }


# ── Resolution ───────────────────────────────────────────────

def _award_credits_tx(conn, user_id: int, amount: int,
                      reason: str, ref_id: str | None, note: str | None) -> None:
    now = _now_utc()
    conn.execute("""
        INSERT INTO credit_transactions (user_id, amount, reason, ref_id, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, amount, reason, ref_id, note, now))
    conn.execute("""
        INSERT INTO user_credits (user_id, balance, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            balance = balance + excluded.balance,
            updated_at = excluded.updated_at
    """, (user_id, amount, now))


def resolve_game(game_id: int, result_value: str | None = None) -> int:
    conn = get_connection()
    game = dict(conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone())
    now = _now_utc()

    entries = conn.execute("""
        SELECT ge.*, u.name as user_name
        FROM game_entries ge JOIN users u ON u.id = ge.user_id
        WHERE ge.game_id = ?
    """, (game_id,)).fetchall()
    entries = [dict(e) for e in entries]

    if not entries:
        conn.execute(
            "UPDATE games SET status='resolved', result_value=?, resolved_at=? WHERE id=?",
            (result_value, now, game_id)
        )
        conn.commit()
        conn.close()
        return 0

    scored = []

    if game["game_type"] == "price_prediction":
        if not result_value:
            conn.close()
            raise ValueError("result_value required for price_prediction")
        actual = float(result_value)
        for e in entries:
            data = _json.loads(e["entry_data"])
            predicted = float(data.get("predicted_price", 0))
            scored.append({"id": e["id"], "user_id": e["user_id"],
                           "score": abs(predicted - actual), "ts": e["submitted_at"]})
        scored.sort(key=lambda x: (x["score"], x["ts"]))

    elif game["game_type"] == "mcq":
        questions = conn.execute(
            "SELECT id, correct_opt FROM game_questions WHERE game_id = ? ORDER BY order_num",
            (game_id,)
        ).fetchall()
        q_map = {str(q["id"]): q["correct_opt"] for q in questions}
        for e in entries:
            data = _json.loads(e["entry_data"])
            answers = data.get("answers", {})
            correct = sum(1 for qid, ans in answers.items() if q_map.get(qid) == ans)
            scored.append({"id": e["id"], "user_id": e["user_id"],
                           "score": correct, "ts": e["submitted_at"]})
        scored.sort(key=lambda x: (-x["score"], x["ts"]))

    elif game["game_type"] == "leaderboard":
        # Fetch current LTPs from price_cache (keyed by instrument_key)
        price_rows = conn.execute("SELECT instrument_key, ltp FROM price_cache").fetchall()
        prices = {r["instrument_key"]: r["ltp"] for r in price_rows}

        for e in entries:
            acct = get_game_virtual_account(game_id, e["user_id"])
            if not acct:
                scored.append({"id": e["id"], "user_id": e["user_id"],
                               "score": 0, "ts": e["submitted_at"]})
                continue

            # Auto square-off all open positions at current LTP (no Telegram)
            for t in get_open_account_trades(account_id=acct["id"]):
                legs = get_account_trade_legs(t["id"])
                exited_ikeys = {l["instrument_key"] for l in legs if l["action"] == "exit"}
                open_legs    = [l for l in legs if l["action"] == "entry"
                                and l["instrument_key"] not in exited_ikeys]
                if not open_legs:
                    continue
                exit_legs = [{
                    "action":          "exit",
                    "side":            "BUY" if l["side"] == "SELL" else "SELL",
                    "instrument_type": l["instrument_type"],
                    "instrument_key":  l["instrument_key"],
                    "strike":          l["strike"],
                    "expiry_str":      l["expiry_str"],
                    "lots":            l["lots"],
                    "lot_size":        l["lot_size"],
                    "price":           prices.get(l["instrument_key"]) or l["price"],
                } for l in open_legs]
                mark_account_trade_closed(t["id"], exit_legs, now, note="auto square-off at game close")

            pf = get_game_portfolio(game_id, e["user_id"], prices)
            scored.append({"id": e["id"], "user_id": e["user_id"],
                           "score": pf.get("pnl", 0), "ts": e["submitted_at"]})
        scored.sort(key=lambda x: (-x["score"], x["ts"]))

    reward_pool = game["reward_pool"]
    winner_count = min(game["winner_count"], len(scored))
    credits_per_winner = reward_pool // winner_count if winner_count else 0

    for i, s in enumerate(scored):
        rank = i + 1
        won = credits_per_winner if rank <= winner_count else 0
        conn.execute(
            "UPDATE game_entries SET score = ?, rank = ?, credits_won = ? WHERE id = ?",
            (s["score"], rank, won, s["id"])
        )
        if won:
            _award_credits_tx(conn, s["user_id"], won, "game_reward",
                              str(game_id), f"#{rank} in '{game['title']}'")

    conn.execute(
        "UPDATE games SET status = 'resolved', result_value = ?, resolved_at = ? WHERE id = ?",
        (result_value, now, game_id)
    )
    conn.commit()
    conn.close()
    return winner_count


# ── Credits ──────────────────────────────────────────────────

def get_user_credits(user_id: int) -> int:
    conn = get_connection()
    row = conn.execute(
        "SELECT balance FROM user_credits WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row["balance"] if row else 0


def award_credits(user_id: int, amount: int, reason: str,
                  ref_id: str | None = None, note: str | None = None) -> None:
    conn = get_connection()
    _award_credits_tx(conn, user_id, amount, reason, ref_id, note)
    conn.commit()
    conn.close()


def get_credit_history(user_id: int, limit: int = 30) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM credit_transactions
        WHERE user_id = ?
        ORDER BY created_at DESC LIMIT ?
    """, (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_subscription_history(user_id: int, limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.id, s.plan_id, s.status, s.start_date, s.end_date, s.amount_paid, s.created_at,
               p.name AS plan_name, p.gem_cost AS plan_gem_cost
        FROM subscriptions s
        JOIN subscription_plans p ON p.id = s.plan_id
        WHERE s.user_id = ?
        ORDER BY s.created_at DESC LIMIT ?
    """, (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def subscribe_with_credits(user_id: int, plan_id: int) -> dict:
    """
    Redeem gems to activate a subscription. Returns {ok, balance, error}.
    Atomic: deduct credits and activate subscription in one transaction.
    """
    conn = get_connection()
    try:
        plan = conn.execute(
            "SELECT id, name, gem_cost, duration_days, active FROM subscription_plans WHERE id = ?",
            (plan_id,)
        ).fetchone()
        if not plan or not plan["active"]:
            return {"ok": False, "error": "Invalid or inactive plan"}
        gem_cost = plan["gem_cost"]
        if gem_cost <= 0:
            return {"ok": False, "error": "This plan cannot be purchased with gems"}

        row = conn.execute(
            "SELECT balance FROM user_credits WHERE user_id = ?", (user_id,)
        ).fetchone()
        balance = row["balance"] if row else 0
        if balance < gem_cost:
            return {"ok": False, "error": f"Not enough gems — need {gem_cost}, have {balance}"}

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        today   = datetime.now(timezone.utc).date()
        from datetime import timedelta
        end_date = (today + timedelta(days=plan["duration_days"])).isoformat()

        # Deduct credits
        conn.execute("""
            INSERT INTO credit_transactions (user_id, amount, reason, ref_id, note, created_at)
            VALUES (?, ?, 'subscription_purchase', ?, ?, ?)
        """, (user_id, -gem_cost, str(plan_id), plan["name"], now_str))
        conn.execute("""
            UPDATE user_credits SET balance = balance - ?, updated_at = ?
            WHERE user_id = ?
        """, (gem_cost, now_str, user_id))

        # Activate subscription
        conn.execute("UPDATE subscriptions SET status='expired' WHERE user_id=? AND status='active'",
                     (user_id,))
        conn.execute("""
            INSERT INTO subscriptions (user_id, plan_id, status, start_date, end_date, amount_paid, created_at)
            VALUES (?, ?, 'active', ?, ?, 0, ?)
        """, (user_id, plan_id, today.isoformat(), end_date, now_str))

        conn.commit()
        new_balance = conn.execute(
            "SELECT balance FROM user_credits WHERE user_id = ?", (user_id,)
        ).fetchone()["balance"]
        return {"ok": True, "balance": new_balance}
    finally:
        conn.close()


# -----------------------------------------------------------
# Razorpay payments
# -----------------------------------------------------------

def create_payment_order(user_id: int, plan_id: int, razorpay_order_id: str,
                          amount: int, currency: str = "INR") -> int:
    """Record a freshly-created Razorpay order. Returns the new row id."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO payment_orders
                (user_id, plan_id, razorpay_order_id, amount, currency, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'created', ?)
        """, (user_id, plan_id, razorpay_order_id, amount, currency, now_str))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_payment_order_by_razorpay_id(razorpay_order_id: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT id, user_id, plan_id, razorpay_order_id, razorpay_payment_id,
                   amount, currency, status, created_at, updated_at
            FROM payment_orders WHERE razorpay_order_id = ?
        """, (razorpay_order_id,)).fetchone()
        if not row:
            return None
        cols = ["id", "user_id", "plan_id", "razorpay_order_id", "razorpay_payment_id",
                "amount", "currency", "status", "created_at", "updated_at"]
        return dict(zip(cols, row))
    finally:
        conn.close()


def activate_subscription_from_payment(user_id: int, plan_id: int, razorpay_order_id: str,
                                        razorpay_payment_id: str, amount: int) -> dict:
    """
    Mark a payment_orders row paid and activate the subscription it paid for,
    atomically. Re-checks the order is still 'created' and belongs to this
    user inside the same transaction, so a replayed/duplicate verify call
    can't double-activate or hijack someone else's order.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today    = datetime.now(timezone.utc).date()
    conn = get_connection()
    try:
        order = conn.execute("""
            SELECT id FROM payment_orders
            WHERE razorpay_order_id = ? AND user_id = ? AND status = 'created'
        """, (razorpay_order_id, user_id)).fetchone()
        if not order:
            return {"ok": False, "error": "Order not found or already processed"}

        plan = conn.execute(
            "SELECT duration_days FROM subscription_plans WHERE id=?", (plan_id,)
        ).fetchone()
        if not plan:
            return {"ok": False, "error": f"Plan {plan_id} not found"}

        conn.execute("""
            UPDATE payment_orders SET status='paid', razorpay_payment_id=?, updated_at=?
            WHERE id=?
        """, (razorpay_payment_id, now_str, order["id"]))

        from datetime import timedelta
        end_date = (today + timedelta(days=plan["duration_days"])).isoformat()
        conn.execute("UPDATE subscriptions SET status='expired' WHERE user_id=? AND status='active'",
                     (user_id,))
        conn.execute("""
            INSERT INTO subscriptions (user_id, plan_id, status, start_date, end_date, amount_paid, created_at)
            VALUES (?, ?, 'active', ?, ?, ?, ?)
        """, (user_id, plan_id, today.isoformat(), end_date, amount, now_str))

        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def get_pending_order_for_user_plan(user_id: int, plan_id: int, max_age_minutes: int = 30) -> dict | None:
    """Reuse an existing not-yet-paid order instead of minting a new Razorpay
    order every time a user retries a stalled checkout attempt."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT id, user_id, plan_id, razorpay_order_id, razorpay_payment_id,
                   amount, currency, status, created_at, updated_at
            FROM payment_orders
            WHERE user_id = ? AND plan_id = ? AND status = 'created' AND created_at >= ?
            ORDER BY id DESC LIMIT 1
        """, (user_id, plan_id, cutoff)).fetchone()
        if not row:
            return None
        cols = ["id", "user_id", "plan_id", "razorpay_order_id", "razorpay_payment_id",
                "amount", "currency", "status", "created_at", "updated_at"]
        return dict(zip(cols, row))
    finally:
        conn.close()


def get_stale_pending_orders(older_than_minutes: int) -> list[dict]:
    """All orders never synced via verify-payment, past the given grace period."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, user_id, plan_id, razorpay_order_id, razorpay_payment_id,
                   amount, currency, status, created_at, updated_at
            FROM payment_orders
            WHERE status = 'created' AND created_at < ?
            ORDER BY id ASC
        """, (cutoff,)).fetchall()
        cols = ["id", "user_id", "plan_id", "razorpay_order_id", "razorpay_payment_id",
                "amount", "currency", "status", "created_at", "updated_at"]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def get_covering_subscription_order(user_id: int, plan_id: int,
                                     exclude_payment_order_id: int) -> dict | None:
    """Is this exact plan already covered by an unexpired subscription right
    now? If so, a later-discovered paid order for the same user+plan is a
    duplicate (the user already got what they paid for) rather than a
    renewal (which only happens once the prior subscription has lapsed).

    Checks subscriptions.end_date directly rather than trusting
    subscriptions.status='active' — that field is only flipped to 'expired'
    by expire_stale_subscriptions(), called opportunistically from a few
    server.py routes, so it can lag behind the actual date and isn't safe
    to rely on from an independent reconcile cron.

    Returns the payment_orders row that activated the covering subscription
    (for the admin-facing duplicate_of_order_id audit link), if one can be
    found — the covering subscription itself may have come from a payment
    row that's since been superseded/deleted, or from gem redemption rather
    than Razorpay, in which case only {"covered": True} is returned with the
    rest of the fields None.
    """
    conn = get_connection()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sub = conn.execute("""
            SELECT id FROM subscriptions
            WHERE user_id = ? AND plan_id = ? AND end_date >= ?
            ORDER BY end_date DESC LIMIT 1
        """, (user_id, plan_id, today)).fetchone()
        if not sub:
            return None

        row = conn.execute("""
            SELECT id, razorpay_order_id, razorpay_payment_id, amount, currency, created_at
            FROM payment_orders
            WHERE user_id = ? AND plan_id = ? AND status = 'paid' AND id != ?
            ORDER BY id DESC LIMIT 1
        """, (user_id, plan_id, exclude_payment_order_id)).fetchone()
        cols = ["id", "razorpay_order_id", "razorpay_payment_id", "amount", "currency", "created_at"]
        result = dict(zip(cols, row)) if row else {c: None for c in cols}
        result["covered"] = True
        return result
    finally:
        conn.close()


def mark_order_reconciled(payment_order_id: int) -> None:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_connection()
    try:
        conn.execute("UPDATE payment_orders SET reconciled_at=? WHERE id=?", (now_str, payment_order_id))
        conn.commit()
    finally:
        conn.close()


def mark_order_duplicate_refunded(payment_order_id: int, razorpay_payment_id: str,
                                   duplicate_of_order_id: str, refund_id: str) -> None:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_connection()
    try:
        conn.execute("""
            UPDATE payment_orders
            SET status='duplicate_refunded', razorpay_payment_id=?, duplicate_of_order_id=?,
                refund_id=?, refunded_at=?, reconciled_at=?, updated_at=?
            WHERE id=?
        """, (razorpay_payment_id, duplicate_of_order_id, refund_id, now_str, now_str, now_str, payment_order_id))
        conn.commit()
    finally:
        conn.close()


def get_flagged_duplicate_orders(limit: int = 50) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT po.id, po.user_id, u.email, po.plan_id, p.name AS plan_name,
                   po.razorpay_order_id, po.razorpay_payment_id, po.amount, po.currency,
                   po.duplicate_of_order_id, po.refund_id, po.refunded_at, po.created_at
            FROM payment_orders po
            JOIN users u ON u.id = po.user_id
            JOIN subscription_plans p ON p.id = po.plan_id
            WHERE po.status = 'duplicate_refunded'
            ORDER BY po.id DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
