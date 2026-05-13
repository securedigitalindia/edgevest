"""
Manual trade entry — add a trade directly to the DB and fire a Telegram alert.

Usage:
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

Auto-derived (not needed from caller):
    instrument_key — looked up from Upstox instrument file
    lot_size       — looked up from instrument file
    entry_ltp      — current spot price fetched from Upstox
    margin         — calculated via Upstox ChargeApi
"""

from datetime import datetime, timezone
from math import gcd
from functools import reduce
from zoneinfo import ZoneInfo

from db.queries import open_recommended_trade, add_trade_legs
from live.fo_instruments import fo_ikey, fo_lot_size, resolve_expiry, SPOT_IKEYS
from live.alert import send_alert

IST = ZoneInfo("Asia/Kolkata")


def add_manual_trade(symbol: str, legs: list[dict], note: str = "") -> int:
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
