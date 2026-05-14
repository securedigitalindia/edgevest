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

from db.queries import open_recommended_trade, add_trade_legs, close_recommended_trade, get_trade_legs
from live.fo_instruments import fo_ikey, fo_lot_size, resolve_expiry, SPOT_IKEYS
from live.alert import send_alert, send_telegram, _h, _DIV

IST = ZoneInfo("Asia/Kolkata")


def add_manual_trade(symbol: str, legs: list[dict], note: str = "", account_id: int | None = None) -> int:
    """
    Create a manual trade: resolve instrument keys, fetch spot + margin,
    write to DB, and send a Telegram alert.

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

            ikey   = fo_ikey(symbol, itype, expiry_date,
                             strike=(strike if itype in ("PE", "CE") else 0))
            lot_sz = fo_lot_size(symbol, expiry_date) or 0

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

    # --- 2. Fetch current spot price ---
    spot_ltp = 0.0
    try:
        from live.upstox_client import get_ltp
        spot_ikey = SPOT_IKEYS.get(symbol)
        if spot_ikey:
            prices   = get_ltp([spot_ikey])
            spot_ltp = prices.get(spot_ikey, 0.0)
    except Exception as e:
        print(f"  [manual_trade]  spot fetch failed: {e}", flush=True)

    # --- 3. Calculate margin ---
    margin_required = margin_final = None
    try:
        from live.upstox_client import get_margin
        margin_input = [
            {
                "instrument_key":   l["instrument_key"],
                "transaction_type": l["side"],
                "quantity":         l["lots"] * l["lot_size"],
                "price":            l["price"],
            }
            for l in resolved_legs if l["instrument_key"] and l["lot_size"]
        ]
        if margin_input:
            m = get_margin(margin_input)
            margin_required = m["required_margin"]
            margin_final    = m["final_margin"]
    except Exception as e:
        print(f"  [manual_trade]  margin fetch failed: {e}", flush=True)

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
        account_id      = account_id,
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

    # --- 6. Send Telegram alert ---
    _send_manual_alert(
        trade_id, symbol, resolved_legs,
        spot_ltp, margin_required, margin_final, note, now_utc,
    )

    now_ist = datetime.now(timezone.utc).astimezone(IST).strftime("%d %b %Y  %H:%M IST")
    print(f"  [manual_trade]  trade id={trade_id}  {symbol}  "
          f"{len(resolved_legs)} legs  added at {now_ist}", flush=True)
    return trade_id


def _send_manual_alert(
    trade_id, symbol, resolved_legs,
    spot_ltp, margin_required, margin_final,
    note, now_utc,
):
    # Number of positions entered — GCD of all leg lots
    all_lots = [l["lots"] for l in resolved_legs if l["lots"] > 0]
    n_pos    = reduce(gcd, all_lots) if all_lots else 1

    # Build display legs at 1-position scale
    display_legs = []
    for l in resolved_legs:
        if l["instrument_type"] == "FUT":
            instrument = f"{symbol} {l['expiry_str']} FUT"
        elif l["instrument_type"] in ("PE", "CE"):
            instrument = f"{symbol} {l['expiry_str']} {int(l['strike']):,} {l['instrument_type']}"
        else:
            instrument = f"{symbol} {l['instrument_type']}"

        base_lots  = l["lots"] // n_pos
        base_qty   = base_lots * l["lot_size"] if l["lot_size"] else base_lots
        note_parts = [f"{base_lots}L × {l['lot_size']} = {base_qty} qty" if l["lot_size"]
                      else f"{base_lots} lot(s)"]
        note_parts.append(f"@ ₹{l['price']:,.2f}")
        display_legs.append({
            "action":     l["side"],
            "instrument": instrument,
            "note":       "  ".join(note_parts),
        })

    # Rationale line — margin shown per position
    pos_label = f"{n_pos} positions" if n_pos > 1 else "1 position"
    rationale_parts = [pos_label]
    if margin_required is not None:
        per = margin_required / n_pos
        rationale_parts.append(f"Margin/pos: ₹{per:,.0f}")
    if margin_final is not None and margin_final != margin_required:
        per_final = margin_final / n_pos
        rationale_parts.append(f"final ₹{per_final:,.0f}")
    if note:
        rationale_parts.append(note)
    rationale = "  |  ".join(rationale_parts)

    pos_tag = f"  ×{n_pos} pos" if n_pos > 1 else ""
    trade_suggestion = {
        "title":     f"Manual Trade  ·  {symbol}  ·  id={trade_id}{pos_tag}",
        "legs":      display_legs,
        "rationale": rationale,
    }

    signal = {
        "trigger_name":  "MANUAL",
        "trigger_type":  "manual",
        "symbol":        symbol,
        "timeframe":     "—",
        "ltp":           spot_ltp,
        "indicator_val": spot_ltp,
        "event":         "MANUAL ENTRY",
        "candle_ts":     None,
        "trades":        [trade_suggestion],
    }

    send_alert(signal)


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

    # --- 4. Fetch spot LTP ---
    spot_ltp = 0.0
    try:
        from live.upstox_client import get_ltp
        spot_ikey = SPOT_IKEYS.get(symbol)
        if spot_ikey:
            spot_ltp = get_ltp([spot_ikey]).get(spot_ikey, 0.0)
    except Exception as e:
        print(f"  [close_manual_trade]  spot fetch failed: {e}", flush=True)

    # --- 5. Persist ---
    close_recommended_trade(trade_id, spot_ltp, now_utc, exit_legs)

    # --- 6. Send alert ---
    _send_exit_alert(trade_id, symbol, entry_legs, exit_legs, spot_ltp, note, now_utc)

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

    # Remove empty leading line if spot was blank
    text = "\n".join(l for l in lines)
    send_telegram(text)
