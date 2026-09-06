"""
Manual trade entry and exit — add/close trades directly and fire Telegram alerts.

--- ADD ---
    from live.manual_trade import add_manual_trade

    add_manual_trade(
        symbol = "BANKNIFTY",
        legs   = [
            {"side": "BUY",  "type": "PE", "strike": 57000, "expiry": "May 2026", "lots": 2, "price": 1548.17},
            {"side": "SELL", "type": "PE", "strike": 54500, "expiry": "May 2026", "lots": 6, "price": 550.40},
        ],
    )

Each leg dict fields:
    side     (required) : 'BUY' | 'SELL'
    type     (required) : 'PE' | 'CE' | 'FUT' | 'EQ'
    price    (required) : float — execution price
    lots     (required) : int   — number of lots
    expiry   (required for PE/CE/FUT) : str — 'May 2026' or '26 May 2026'
    strike   (required for PE/CE)     : int — strike price

--- CLOSE ---
    from live.manual_trade import close_manual_trade

    close_manual_trade(
        trade_id = 9,
        prices   = [1200.0, 700.0],   # exit price per leg, same order as entry
    )

    # To see leg order first:
    from db.queries import get_trade_legs
    for i, l in enumerate(get_trade_legs(9)):
        print(i, l['side'], l['instrument_type'], l.get('strike'), l['lots'], l['price'])
"""

from datetime import datetime, timezone
from math import gcd
from functools import reduce
from zoneinfo import ZoneInfo

from db.queries import (
    open_recommended_trade, add_trade_legs, close_recommended_trade, get_trade_legs,
    create_account_trade, get_account_trade_legs, mark_account_trade_closed,
    get_open_account_trades, _ACCT_TRADE_COLS,
    get_current_legs, get_recommendation, publish_recommended_trade,
)
from live.fo_instruments import fo_ikey, fo_lot_size, resolve_expiry, SPOT_IKEYS
from live.alert import send_new_trade_alert, send_telegram, _h, _DIV

IST = ZoneInfo("Asia/Kolkata")


def _compute_margin(legs: list[dict]) -> tuple[float | None, float | None]:
    """
    SPAN margin for a set of legs (any shape carrying instrument_key/side/
    lots/lot_size/price) — shared by add_manual_trade(),
    recalculate_recommendation_margin(), and preview_margin_for_trade().
    Never raises; (None, None) on any failure or an empty/unresolved leg set.
    """
    try:
        from live.upstox_client import get_margin
        margin_input = [
            {
                "instrument_key":   l["instrument_key"],
                "transaction_type": l["side"],
                "quantity":         l["lots"] * (l["lot_size"] or 1),
                "price":            l["price"],
            }
            for l in legs if l.get("instrument_key") and l.get("lot_size")
        ]
        if not margin_input:
            return None, None
        m = get_margin(margin_input)
        return m.get("required_margin"), m.get("final_margin")
    except Exception as e:
        print(f"  [manual_trade]  margin fetch failed: {e}", flush=True)
        return None, None


def preview_margin_for_trade(rec_id: int) -> tuple[float | None, float | None]:
    """
    Live SPAN margin for a trade's *current* legs — read-only, never writes
    margin_required/margin_final/margin_at_entry. Used to show a draft an
    on-screen margin estimate without persisting anything (margin is only
    ever persisted at publish, see publish_manual_trade() /
    docs/prd/manual-strategy-cli.md's "margin deferred to publish" decision —
    this function must stay strictly read-only or that guarantee breaks).
    """
    from db.queries import get_current_legs
    live_legs = get_current_legs(rec_id)
    if not live_legs:
        return None, None
    return _compute_margin(live_legs)


def add_manual_trade(symbol: str, legs: list[dict], note: str = "", risk_level: str | None = None,
                      status: str = "open") -> int:
    """
    Create a manual trade: resolve instrument keys, fetch spot, write to DB.

    status="open" (default): also computes margin and sends the Telegram
    alert immediately, exactly as this function has always behaved.
    status="draft": skips margin (deferred to publish_manual_trade(), same
    reasoning as strategy_cli.py's `create` — see docs/prd/manual-strategy-cli.md)
    and sends no alert — the trade sits invisible to clients until published.

    Returns the new trade_id.
    """
    symbol = symbol.upper()
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- 1. Resolve instrument keys, lot sizes, expiry dates ---
    resolved_legs = []
    for i, leg in enumerate(legs, 1):
        side  = leg["side"].upper()
        itype = leg["type"].upper()
        price = float(leg["price"])
        lots  = int(leg["lots"])
        strike = int(leg.get("strike", 0)) if leg.get("strike") else 0
        expiry_str = leg.get("expiry", "")

        expiry_date = None
        ikey        = None
        lot_sz      = 0

        if itype in ("PE", "CE", "FUT"):
            if not expiry_str:
                raise ValueError(f"Leg {i}: 'expiry' is required for {itype}")
            expiry_date = resolve_expiry(symbol, expiry_str)
            if expiry_date is None:
                raise ValueError(f"Leg {i}: could not resolve expiry {expiry_str!r} "
                                 f"for {symbol}")
            expiry_str = expiry_date.strftime("%d %b %Y")

            _strike = strike if itype in ("PE", "CE") else 0
            ikey = fo_ikey(symbol, itype, expiry_date, strike=_strike)
            if ikey is None:
                ikey = fo_ikey(symbol, itype, expiry_date, strike=_strike, weekly=True)
            lot_sz = fo_lot_size(symbol, expiry_date) or 0

        elif itype == "EQ":
            ikey   = leg.get("instrument_key")
            lot_sz = int(leg.get("lot_size") or 1)

        resolved_legs.append({
            "side":            side,
            "instrument_type": itype,
            "strike":          strike or None,
            "expiry_str":      expiry_str or None,
            "expiry_date":     expiry_date,
            "lots":            lots,
            "lot_size":        lot_sz,
            "price":           price,
            "instrument_key":  ikey,
        })

    # --- 2. Snapshot current spot price from shared price cache ---
    spot_ltp = 0.0
    try:
        from db.queries import get_cached_prices
        spot_ikey = SPOT_IKEYS.get(symbol)
        if spot_ikey:
            cached, _ = get_cached_prices([spot_ikey])
            spot_ltp  = cached.get(spot_ikey, 0.0)
    except Exception as e:
        print(f"  [manual_trade]  spot fetch failed: {e}", flush=True)

    # --- 3. Calculate margin (skipped for a draft — deferred to publish,
    #        same reasoning as strategy_cli.py's `create`: computing it now
    #        would be wasted work for legs that might still change, and
    #        margin_at_entry means "captured once at entry" everywhere else
    #        in the schema — a draft hasn't entered anything yet) ---
    margin_required = margin_final = None
    if status == "open":
        margin_required, margin_final = _compute_margin(resolved_legs)

    # --- 4. Insert trade header ---
    trade_id = open_recommended_trade(
        trigger_name    = "MANUAL",
        symbol          = symbol,
        entry_level     = 0,
        entry_ltp       = spot_ltp,
        entry_time      = now_utc,
        exit_level      = 0,
        margin_required = margin_required,
        margin_final    = margin_final,
        margin_at_entry = margin_final,
        expiry_strs     = [l.get("expiry_str") for l in resolved_legs],
        note            = note,
        risk_level      = risk_level,
        status          = status,
    )

    # --- 5. Insert legs ---
    leg_rows = [
        {
            "action":          "entry",
            "side":            l["side"],
            "instrument_type": l["instrument_type"],
            "instrument_key":  l["instrument_key"],
            "strike":          l["strike"],
            "expiry_str":      l["expiry_str"],
            "lots":            l["lots"],
            "lot_size":        l["lot_size"],
            "price":           l["price"],
            "ts":              now_utc,
        }
        for l in resolved_legs
    ]
    add_trade_legs(trade_id, leg_rows)

    # --- 6. Send Telegram alert (draft: silent — see publish_manual_trade()) ---
    now_ist = datetime.now(timezone.utc).astimezone(IST).strftime("%d %b %Y  %H:%M IST")
    if status == "open":
        try:
            display_code = get_recommendation(trade_id).get("display_code")
            send_new_trade_alert(trade_id, symbol, display_code, note, resolved_legs)
        except Exception as e:
            print(f"  [manual_trade]  alert failed: {e}", flush=True)
        print(f"  [manual_trade]  trade id={trade_id}  {symbol}  "
              f"{len(resolved_legs)} legs  added at {now_ist}", flush=True)
    else:
        print(f"  [manual_trade]  draft trade id={trade_id}  {symbol}  "
              f"{len(resolved_legs)} legs  staged at {now_ist} — no alert sent", flush=True)
    return trade_id


# ---------------------------------------------------------------------------
# Publish a draft (strategy_cli.py `create` -> `publish` workflow)
# ---------------------------------------------------------------------------

def publish_manual_trade(trade_id: int) -> dict:
    """
    Publish a draft recommended_trades row: flips status draft->open, stamps
    real entry_time/entry_ltp, computes margin for the first time, sends the
    one Telegram alert. Shared by strategy_cli.py's `publish` command and the
    admin HTTP `POST /api/recommendations/<id>/publish` route so the publish
    logic lives in exactly one place.

    Raises ValueError if the trade isn't currently a draft, or has no legs.
    Returns the updated recommendation dict (get_recommendation(trade_id)
    after the flip).
    """
    trade = get_recommendation(trade_id)
    if not trade:
        raise ValueError(f"trade {trade_id} not found")
    if trade["status"] != "draft":
        raise ValueError(f"trade {trade_id} is '{trade['status']}' — publish only works on a draft")

    legs = get_current_legs(trade_id)
    if not legs:
        raise ValueError(f"trade {trade_id} has no legs — cannot publish an empty draft")

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    spot_ltp = 0.0
    try:
        from db.queries import get_cached_prices
        spot_ikey = SPOT_IKEYS.get(trade["symbol"])
        if spot_ikey:
            cached, _ = get_cached_prices([spot_ikey])
            spot_ltp  = cached.get(spot_ikey, 0.0)
    except Exception as e:
        print(f"  [publish_manual_trade]  spot fetch failed: {e}", flush=True)

    flipped = publish_recommended_trade(trade_id, entry_time=now_utc, entry_ltp=spot_ltp)
    if not flipped:
        # Lost a race — another concurrent publish() call on this same draft
        # already flipped it (e.g. a double-click, or two admin tabs) between
        # our status check above and this UPDATE. Stop here: proceeding would
        # recompute margin redundantly and, worse, send a second "New Trade"
        # Telegram alert for one publish. The winning call already did all of
        # this correctly.
        raise ValueError(f"trade {trade_id} was published by a concurrent request — no action taken")
    recalculate_recommendation_margin(trade_id)

    updated = get_recommendation(trade_id)

    # Best-effort: the DB state above already committed (draft is live now
    # regardless), so a formatting/Telegram hiccup here must never surface
    # as a publish failure — same guarding pattern server.py's /adjust and
    # /exit routes already use around their own alert calls. Reads
    # symbol/note/display_code from `updated` (not the pre-flip `trade`
    # snapshot) throughout — all three happen to be immutable across publish
    # today, but sourcing them all from one dict removes any need to reason
    # about which fields are safe to read stale if that ever changes.
    try:
        send_new_trade_alert(trade_id, updated["symbol"], updated.get("display_code"),
                              updated.get("note") or "", legs)
    except Exception as e:
        print(f"  [publish_manual_trade]  alert failed: {e}", flush=True)

    return updated


# ---------------------------------------------------------------------------
# Close a trade manually
# ---------------------------------------------------------------------------

def close_manual_trade(trade_id: int, prices: list[float], note: str = "") -> None:
    """
    Exit an open trade: record exit legs, mark as exited, send Telegram alert.

    prices  : exit execution price for each entry leg, in the same order they
              were stored (use get_trade_legs(trade_id) to verify order).
    """
    from db.init_db import get_connection
    from db.queries import _TRADE_COLS, _TRADE_SELECT

    # --- 1. Load trade header ---
    conn = get_connection()
    cur  = conn.execute(
        f"SELECT {_TRADE_SELECT} FROM recommended_trades WHERE id = ?", (trade_id,)
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        raise ValueError(f"Trade id={trade_id} not found")

    trade = dict(zip(_TRADE_COLS, row))
    if trade["status"] != "open":
        raise ValueError(
            f"Trade id={trade_id} is already '{trade['status']}' — only open trades can be closed"
        )

    symbol = trade["symbol"]

    # --- 2. Load entry legs and validate price count ---
    entry_legs = [l for l in get_trade_legs(trade_id) if l["action"] == "entry"]
    if len(prices) != len(entry_legs):
        leg_lines = "\n".join(
            f"  {i+1}.  {l['side']:<4}  {l['instrument_type']}  "
            f"{'strike=' + str(int(l['strike'])) + '  ' if l.get('strike') else ''}"
            f"{l['lots']}L  @{l['price']}"
            for i, l in enumerate(entry_legs)
        )
        raise ValueError(
            f"Expected {len(entry_legs)} price(s), got {len(prices)}.\n"
            f"Entry legs for trade {trade_id}:\n{leg_lines}"
        )

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- 3. Build exit legs (opposite side to entry) ---
    exit_legs = [
        {
            "action":          "exit",
            "side":            "BUY" if leg["side"] == "SELL" else "SELL",
            "instrument_type": leg["instrument_type"],
            "instrument_key":  leg["instrument_key"],
            "strike":          leg["strike"],
            "expiry_str":      leg["expiry_str"],
            "lots":            leg["lots"],
            "lot_size":        leg["lot_size"],
            "price":           float(exit_price),
            "ts":              now_utc,
        }
        for leg, exit_price in zip(entry_legs, prices)
    ]

    # --- 4. Snapshot spot LTP from shared price cache ---
    spot_ltp = 0.0
    try:
        from db.queries import get_cached_prices
        spot_ikey = SPOT_IKEYS.get(symbol)
        if spot_ikey:
            cached, _ = get_cached_prices([spot_ikey])
            spot_ltp  = cached.get(spot_ikey, 0.0)
    except Exception as e:
        print(f"  [close_manual_trade]  spot fetch failed: {e}", flush=True)

    # --- 5. Persist ---
    close_recommended_trade(trade_id, spot_ltp, now_utc, exit_legs)

    # --- 6. Send alert ---
    _send_exit_alert(trade_id, symbol, entry_legs, exit_legs, spot_ltp, note, now_utc)

    # --- 7. Auto-exit any linked account trades ---
    try:
        auto_exit_linked_account_trades(trade_id, exit_legs, now_utc)
    except Exception as e:
        print(f"  [close_manual_trade]  auto-exit linked account trades failed: {e}", flush=True)

    now_ist = datetime.now(timezone.utc).astimezone(IST).strftime("%d %b %Y  %H:%M IST")
    print(f"  [close_manual_trade]  trade id={trade_id}  {symbol}  closed at {now_ist}",
          flush=True)


def _send_exit_alert(
    trade_id, symbol, entry_legs, exit_legs,
    spot_ltp, note, now_utc,
):
    n_pos     = reduce(gcd, [l["lots"] for l in entry_legs if l["lots"] > 0]) or 1
    alert_str = datetime.now(timezone.utc).astimezone(IST).strftime("%d %b  %H:%M IST")

    # Compute realized P&L
    total_pnl, has_pnl = 0.0, False
    for e_leg, x_leg in zip(entry_legs, exit_legs):
        if e_leg["price"] is not None and x_leg["price"] is not None:
            qty = e_leg["lots"] * (e_leg["lot_size"] or 1)
            total_pnl += (e_leg["price"] - x_leg["price"]) * qty if e_leg["side"] == "SELL" \
                else (x_leg["price"] - e_leg["price"]) * qty
            has_pnl = True

    pos_tag = f"  ×{n_pos} pos" if n_pos > 1 else ""

    lines = [
        f'✅ <b>{_h(symbol)}</b>  •  Manual Exit{pos_tag}',
        _DIV,
        f"<i>Spot  ₹{spot_ltp:,.2f}</i>" if spot_ltp else "",
        "",
    ]

    # Entry → Exit per leg
    for e_leg, x_leg in zip(entry_legs, exit_legs):
        strike_str = f"{int(e_leg['strike']):,} " if e_leg.get("strike") else ""
        base_lots  = e_leg["lots"] // n_pos
        entry_p    = e_leg["price"] or 0
        exit_p     = x_leg["price"] or 0
        leg_pnl    = None
        if e_leg["price"] is not None and x_leg["price"] is not None:
            qty = (e_leg["lots"] // n_pos) * (e_leg["lot_size"] or 1)
            leg_pnl = (entry_p - exit_p) * qty if e_leg["side"] == "SELL" \
                else (exit_p - entry_p) * qty
        pnl_str = f"   <i>(₹{leg_pnl:+,.0f})</i>" if leg_pnl is not None else ""
        icon    = "🔴" if e_leg["side"] == "SELL" else "🟢"
        lines.append(
            f"  {icon}  {e_leg['side']:<4}  {strike_str}{e_leg['instrument_type']}"
            f"  {base_lots}L   ₹{entry_p:,.0f} → ₹{exit_p:,.0f}{pnl_str}"
        )

    lines += ["", _DIV]
    if has_pnl:
        lines.append(f"<b>Net P&amp;L  ₹{total_pnl:+,.0f}</b>")
    if note:
        lines.append(f"<i>{_h(note)}</i>")
    lines += ["", f"Alert at  {alert_str}"]

    text = "\n".join(l for l in lines)
    send_telegram(text)


# ---------------------------------------------------------------------------
# Margin recalculation helper (used after adjustments and for backfill)
# ---------------------------------------------------------------------------

def recalculate_recommendation_margin(rec_id: int) -> float | None:
    """
    Re-compute SPAN margin for the current live legs of a recommended_trade and
    persist back to margin_required / margin_final.  Returns final_margin or None.
    """
    from db.queries import get_current_legs
    from db.init_db import get_connection

    live_legs = get_current_legs(rec_id)
    if not live_legs:
        return None

    margin_required, margin_final = _compute_margin(live_legs)

    if margin_required is not None:
        conn = get_connection()
        # margin_at_entry is immutable once set — COALESCE only populates it the
        # first time (e.g. right after a roll creates a fresh row with NULL
        # margin); later recalculations (e.g. after an /adjust) never overwrite
        # it, so the monthly report can always read back the true entry-time
        # margin. margin_required/margin_final keep being overwritten as before.
        conn.execute(
            "UPDATE recommended_trades "
            "SET margin_required=?, margin_final=?, margin_at_entry=COALESCE(margin_at_entry, ?) "
            "WHERE id=?",
            (margin_required, margin_final, margin_final, rec_id),
        )
        conn.commit()
        conn.close()

    return margin_final


def recalculate_account_trade_margin(at_id: int) -> float | None:
    """
    Re-compute SPAN margin for the current live legs of an account trade and
    persist it back to account_trades.margin.  Returns new margin or None on failure.
    """
    from db.queries import get_account_trade_legs
    from db.init_db import get_connection

    legs         = get_account_trade_legs(at_id)
    exited_ikeys = {l["instrument_key"] for l in legs if l["action"] == "exit"}
    live_legs    = [
        l for l in legs
        if l["action"] == "entry" and l["instrument_key"] not in exited_ikeys
    ]

    if not live_legs:
        return None

    margin = None
    try:
        from live.upstox_client import get_margin
        margin_input = [
            {
                "instrument_key":   l["instrument_key"],
                "transaction_type": l["side"],
                "quantity":         l["lots"] * (l["lot_size"] or 1),
                "price":            l["price"],
            }
            for l in live_legs if l["instrument_key"] and l["lot_size"]
        ]
        if margin_input:
            m      = get_margin(margin_input)
            margin = m.get("final_margin") or m.get("required_margin")
    except Exception as e:
        print(f"  [recalculate_margin at_id={at_id}]  {e}", flush=True)

    if margin is not None:
        conn = get_connection()
        conn.execute("UPDATE account_trades SET margin = ? WHERE id = ?", (margin, at_id))
        conn.commit()
        conn.close()

    return margin


# ---------------------------------------------------------------------------
# Push a recommendation to an account
# ---------------------------------------------------------------------------

def _resolve_legs(symbol: str, legs: list[dict], now_utc: str) -> list[dict]:
    """Resolve instrument keys + lot sizes for a list of leg dicts."""
    resolved = []
    for i, leg in enumerate(legs, 1):
        itype      = leg["type"].upper()
        strike     = int(leg.get("strike", 0)) if leg.get("strike") else 0
        expiry_str = leg.get("expiry", "")
        expiry_date = ikey = None
        lot_sz = 0
        if itype in ("PE", "CE", "FUT"):
            if not expiry_str:
                raise ValueError(f"Leg {i}: expiry required for {itype}")
            expiry_date = resolve_expiry(symbol, expiry_str)
            if expiry_date is None:
                raise ValueError(f"Leg {i}: cannot resolve expiry {expiry_str!r}")
            expiry_str  = expiry_date.strftime("%d %b %Y")
            _strike2 = strike if itype in ("PE", "CE") else 0
            ikey     = fo_ikey(symbol, itype, expiry_date, strike=_strike2)
            if ikey is None:
                ikey = fo_ikey(symbol, itype, expiry_date, strike=_strike2, weekly=True)
            lot_sz   = fo_lot_size(symbol, expiry_date) or 0
        elif itype == "EQ":
            ikey   = leg.get("instrument_key")
            lot_sz = int(leg.get("lot_size") or 1)
        resolved.append({
            "action":          "entry",
            "side":            leg["side"].upper(),
            "instrument_type": itype,
            "instrument_key":  ikey,
            "strike":          strike or None,
            "expiry_str":      expiry_str or None,
            "lots":            int(leg["lots"]),
            "lot_size":        lot_sz,
            "price":           float(leg["price"]),
            "ts":              now_utc,
        })
    return resolved


def push_to_account(
    recommended_trade_id: int | None,
    account_id: int,
    symbol: str,
    legs: list[dict],
    note: str = "",
) -> int:
    """
    Push a recommendation to an account with custom sizing.
    Creates account_trade + account_trade_legs, sends Telegram alert.
    Returns account_trade_id.
    """
    symbol  = symbol.upper()
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    resolved = _resolve_legs(symbol, legs, now_utc)

    # Calculate margin via Upstox (best-effort; None on failure)
    margin = None
    try:
        from live.upstox_client import get_margin
        margin_input = [
            {
                "instrument_key":   l["instrument_key"],
                "transaction_type": l["side"],
                "quantity":         l["lots"] * l["lot_size"],
                "price":            l["price"],
            }
            for l in resolved if l["instrument_key"] and l["lot_size"]
        ]
        if margin_input:
            m      = get_margin(margin_input)
            margin = m.get("final_margin") or m.get("required_margin")
    except Exception as e:
        print(f"  [push_to_account]  margin fetch failed: {e}", flush=True)

    # Margin sufficiency check: capital − already-used ≥ new trade margin
    if margin is not None:
        from db.init_db import get_connection as _gc
        _conn = _gc()
        cap_row  = _conn.execute("SELECT capital FROM accounts WHERE id = ?", (account_id,)).fetchone()
        _conn.close()
        capital = cap_row[0] if cap_row else None
        if capital is not None:
            used      = sum(t.get("margin") or 0 for t in get_open_account_trades(account_id=account_id))
            remaining = capital - used
            if margin > remaining:
                raise ValueError(
                    f"Insufficient margin — this trade needs ₹{margin:,.0f} but only "
                    f"₹{remaining:,.0f} is available "
                    f"(capital ₹{capital:,.0f} − used ₹{used:,.0f})"
                )

    # Fetch account info for alert
    from db.queries import get_accounts
    from db.init_db import get_connection as _gc2
    account_info = next((a for a in get_accounts() if a["id"] == account_id), None)
    account_label = (account_info or {}).get("label") or \
                    (account_info or {}).get("trader") or f"Account {account_id}"

    # Check if this is a game (virtual) account — skip Telegram for virtual trades
    _conn2 = _gc2()
    _game_row = _conn2.execute("SELECT game_id FROM accounts WHERE id = ?", (account_id,)).fetchone()
    _conn2.close()
    is_game_account = bool(_game_row and _game_row[0])

    at_id = create_account_trade(
        account_id           = account_id,
        legs                 = resolved,
        recommended_trade_id = recommended_trade_id,
        note                 = note,
        entry_time           = now_utc,
        margin               = margin,
    )

    # Telegram alert (skip for game/virtual accounts)
    if not is_game_account:
        try:
            n_pos    = reduce(gcd, [l["lots"] for l in resolved if l["lots"] > 0]) or 1
            now_ist  = datetime.now(timezone.utc).astimezone(IST).strftime("%d %b %Y  %H:%M IST")
            rec_tag  = f"  ·  rec#{recommended_trade_id}" if recommended_trade_id else ""
            lines    = [
                f'📥 <b>{_h(symbol)}</b>  ·  {_h(account_label)}{rec_tag}',
                _DIV,
            ]
            for l in resolved:
                strike_str = f"{int(l['strike']):,} " if l.get("strike") else ""
                base_lots  = l["lots"] // n_pos
                icon       = "🔴" if l["side"] == "SELL" else "🟢"
                lines.append(
                    f"  {icon}  {l['side']:<4}  {strike_str}{l['instrument_type']}"
                    f"  {base_lots}L  @₹{l['price']:,.2f}"
                )
            pos_tag = f"  ×{n_pos} pos" if n_pos > 1 else ""
            lines += ["", _DIV, f"{pos_tag}  {note}" if note else pos_tag,
                      f"Added at  {now_ist}"]
            send_telegram("\n".join(l for l in lines))
        except Exception as e:
            print(f"  [push_to_account]  Telegram alert failed (trade saved ok): {e}", flush=True)

    print(f"  [push_to_account]  account_trade id={at_id}  {symbol}  "
          f"account={account_label}  at {now_ist}", flush=True)
    return at_id


def close_account_trade(
    account_trade_id: int,
    prices: list[float],
    note: str = "",
) -> None:
    """Exit an account_trade: record exit legs, mark exited, send Telegram."""
    from db.queries import get_open_account_trades, get_accounts

    # Load trade
    conn_data = next(
        (t for t in get_open_account_trades() if t["id"] == account_trade_id), None
    )
    if conn_data is None:
        raise ValueError(f"Account trade id={account_trade_id} not found or already closed")

    # Must match the same "currently active legs" set the frontend shows and
    # collects prices for (server.py's /api/account-trades listing) — legs
    # already closed by an earlier adjustment (action='exit') don't need a
    # price here, or this rejects a correctly-filled-in exit as incomplete.
    all_legs    = get_account_trade_legs(account_trade_id)
    exited_keys = {l["instrument_key"] for l in all_legs if l["action"] == "exit"}
    entry_legs  = [l for l in all_legs
                   if l["action"] == "entry" and l["instrument_key"] not in exited_keys]
    if len(prices) != len(entry_legs):
        raise ValueError(f"Expected {len(entry_legs)} price(s), got {len(prices)}")

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    exit_legs = [
        {
            "action":          "exit",
            "side":            "BUY" if l["side"] == "SELL" else "SELL",
            "instrument_type": l["instrument_type"],
            "instrument_key":  l["instrument_key"],
            "strike":          l["strike"],
            "expiry_str":      l["expiry_str"],
            "lots":            l["lots"],
            "lot_size":        l["lot_size"],
            "price":           float(p),
        }
        for l, p in zip(entry_legs, prices)
    ]

    mark_account_trade_closed(account_trade_id, exit_legs, now_utc, note)

    # Telegram alert
    symbol        = conn_data.get("symbol") or "—"
    account_label = conn_data.get("account_label") or f"Account {conn_data['account_id']}"
    n_pos         = reduce(gcd, [l["lots"] for l in entry_legs if l["lots"] > 0]) or 1
    now_ist       = datetime.now(timezone.utc).astimezone(IST).strftime("%d %b  %H:%M IST")

    total_pnl = 0.0
    lines = [
        f'✅ <b>{_h(symbol)}</b>  ·  {_h(account_label)}  ·  Exit',
        _DIV,
    ]
    for e, x in zip(entry_legs, exit_legs):
        strike_str = f"{int(e['strike']):,} " if e.get("strike") else ""
        base_lots  = e["lots"] // n_pos
        qty        = (e["lots"] // n_pos) * (e["lot_size"] or 1)
        ep, xp     = e["price"] or 0, x["price"] or 0
        leg_pnl    = (ep - xp) * qty if e["side"] == "SELL" else (xp - ep) * qty
        total_pnl += leg_pnl * n_pos
        icon       = "🔴" if e["side"] == "SELL" else "🟢"
        lines.append(
            f"  {icon}  {e['side']:<4}  {strike_str}{e['instrument_type']}"
            f"  {base_lots}L   ₹{ep:,.0f} → ₹{xp:,.0f}"
            f"   <i>(₹{leg_pnl:+,.0f})</i>"
        )
    lines += ["", _DIV, f"<b>Net P&amp;L  ₹{total_pnl:+,.0f}</b>"]
    if note:
        lines.append(f"<i>{_h(note)}</i>")
    lines.append(f"Exit at  {now_ist}")
    send_telegram("\n".join(lines))

    print(f"  [close_account_trade]  id={account_trade_id}  {symbol}  "
          f"account={account_label}  closed at {now_ist}", flush=True)


def auto_exit_linked_account_trades(
    recommended_trade_id: int,
    rec_exit_legs: list[dict],
    exit_time: str,
) -> None:
    """
    Call right after close_recommended_trade() — auto-exits every still-open
    account_trade linked to this recommendation, using the recommendation's
    own exit prices. Matched to each account_trade's current legs by
    instrument_key (same option/future contract, so the same market price
    applies regardless of that account's own lot sizing).

    A leg an account added independently (its own adjustment, absent from
    the recommendation) has no price to auto-exit with — it's left open, and
    that account_trade stays 'open' with just the unmatched leg(s)
    remaining, same as today's pending-exit banner lets a client finish
    manually via Exit Trade (now for a narrower set of legs).
    """
    price_by_ikey = {
        l["instrument_key"]: l["price"]
        for l in rec_exit_legs
        if l.get("instrument_key") and l.get("price") is not None
    }
    if not price_by_ikey:
        return

    linked = [t for t in get_open_account_trades()
              if t.get("recommended_trade_id") == recommended_trade_id]

    for t in linked:
        all_legs    = get_account_trade_legs(t["id"])
        exited_keys = {l["instrument_key"] for l in all_legs if l["action"] == "exit"}
        entry_legs  = [l for l in all_legs
                       if l["action"] == "entry" and l["instrument_key"] not in exited_keys]

        matched = [l for l in entry_legs if l["instrument_key"] in price_by_ikey]
        if not matched:
            continue  # this recommendation's exit can't price anything currently open here

        exit_legs = [
            {
                "action":          "exit",
                "side":            "BUY" if l["side"] == "SELL" else "SELL",
                "instrument_type": l["instrument_type"],
                "instrument_key":  l["instrument_key"],
                "strike":          l["strike"],
                "expiry_str":      l["expiry_str"],
                "lots":            l["lots"],
                "lot_size":        l["lot_size"],
                "price":           price_by_ikey[l["instrument_key"]],
            }
            for l in matched
        ]
        full_exit = len(matched) == len(entry_legs)
        mark_account_trade_closed(t["id"], exit_legs, exit_time, mark_exited=full_exit)

        if not full_exit:
            try:
                recalculate_account_trade_margin(t["id"])
            except Exception as e:
                print(f"  [auto_exit_linked_account_trades]  margin recalc skipped: {e}", flush=True)

        # Telegram alert (skip for game/virtual accounts)
        try:
            from db.init_db import get_connection as _gc
            _conn   = _gc()
            _row    = _conn.execute("SELECT game_id FROM accounts WHERE id = ?", (t["account_id"],)).fetchone()
            _conn.close()
            is_game = bool(_row and _row[0])

            if not is_game:
                symbol        = t.get("symbol") or "—"
                account_label = t.get("account_label") or f"Account {t['account_id']}"
                n_pos         = reduce(gcd, [l["lots"] for l in matched if l["lots"] > 0]) or 1
                now_ist       = datetime.now(timezone.utc).astimezone(IST).strftime("%d %b  %H:%M IST")

                total_pnl = 0.0
                lines = [
                    f'🔔 <b>{_h(symbol)}</b>  ·  {_h(account_label)}  ·  Auto-exit (recommendation closed)',
                    _DIV,
                ]
                for e, x in zip(matched, exit_legs):
                    strike_str = f"{int(e['strike']):,} " if e.get("strike") else ""
                    base_lots  = e["lots"] // n_pos
                    qty        = (e["lots"] // n_pos) * (e["lot_size"] or 1)
                    ep, xp     = e["price"] or 0, x["price"] or 0
                    leg_pnl    = (ep - xp) * qty if e["side"] == "SELL" else (xp - ep) * qty
                    total_pnl += leg_pnl * n_pos
                    icon       = "🔴" if e["side"] == "SELL" else "🟢"
                    lines.append(
                        f"  {icon}  {e['side']:<4}  {strike_str}{e['instrument_type']}"
                        f"  {base_lots}L   ₹{ep:,.0f} → ₹{xp:,.0f}"
                        f"   <i>(₹{leg_pnl:+,.0f})</i>"
                    )
                lines += ["", _DIV, f"<b>Net P&amp;L  ₹{total_pnl:+,.0f}</b>"]
                if not full_exit:
                    lines.append("<i>Other leg(s) on this trade stay open — exit them manually.</i>")
                lines.append(f"Exit at  {now_ist}")
                send_telegram("\n".join(lines))
        except Exception as e:
            print(f"  [auto_exit_linked_account_trades]  Telegram alert failed (trade updated ok): {e}", flush=True)

        print(f"  [auto_exit_linked_account_trades]  account_trade id={t['id']}  "
              f"{'fully' if full_exit else 'partially'} exited via rec id={recommended_trade_id}", flush=True)
