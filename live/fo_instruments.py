"""
Looks up Upstox instrument keys for NSE F&O contracts.

Keys are numeric IDs (e.g. NSE_FO|66071) — they cannot be constructed
from symbol/expiry/strike strings. This module downloads the NSE instrument
file once per session and builds an index for fast lookups.

Call refresh() at startup to pre-load the index.

Nifty-specific helpers (backward compat):
    nifty_fut_ikey(expiry)
    nifty_pe_ikey(expiry, strike, weekly)
    nifty_lot_size(expiry)

Generic helpers (any NSE F&O underlying):
    fo_ikey(symbol, instrument_type, expiry, strike, weekly)
    fo_lot_size(symbol, expiry)
    resolve_expiry(symbol, expiry_str)   — "May 2026" → date(2026,5,28)
"""

import gzip
import json
import requests
from datetime import date, datetime, timezone, timedelta

_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"

# Nifty-specific index (kept for backward compat)
_NIFTY_UNDERLYING = "NSE_INDEX|Nifty 50"
_index:     dict = {}
_LOT_SIZES: dict[date, int] = {}

# Generic index — all NSE_FO underlyings
# key: (underlying_key, instrument_type, expiry_date, strike_int, weekly) → ikey
_generic_index:     dict[tuple, str] = {}
# key: (underlying_key, expiry_date) → lot_size
_generic_lot_sizes: dict[tuple, int] = {}

_loaded = False

# Map from friendly symbol name → underlying_key in NSE instrument file
_UNDERLYING_KEYS: dict[str, str] = {
    "NIFTY50":    "NSE_INDEX|Nifty 50",
    "BANKNIFTY":  "NSE_INDEX|Nifty Bank",
    "FINNIFTY":   "NSE_INDEX|Nifty Fin Services",
    "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
    "SENSEX":     "BSE_INDEX|SENSEX",
}

# Spot price instrument key for each symbol (used in manual_trade to fetch LTP)
SPOT_IKEYS: dict[str, str] = {
    "NIFTY50":    "NSE_INDEX|Nifty 50",
    "BANKNIFTY":  "NSE_INDEX|Nifty Bank",
    "FINNIFTY":   "NSE_INDEX|Nifty Fin Services",
    "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
}


def refresh():
    """Download and index the NSE F&O instrument file. Call once at startup."""
    global _index, _LOT_SIZES, _generic_index, _generic_lot_sizes, _loaded

    print("  Downloading NSE F&O instrument list from Upstox...", flush=True)
    resp = requests.get(_INSTRUMENTS_URL, timeout=30)
    resp.raise_for_status()
    instruments = json.loads(gzip.decompress(resp.content))

    nifty_idx = {}
    nifty_lot_sizes: dict[date, int] = {}
    gen_idx:       dict[tuple, str] = {}
    gen_lot_sizes: dict[tuple, int] = {}

    for row in instruments:
        if row.get("segment") != "NSE_FO":
            continue

        underlying_key = row.get("underlying_key", "")
        expiry_ms = row.get("expiry")
        if not expiry_ms:
            continue

        expiry_date = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc).date()
        itype  = row.get("instrument_type")
        ikey   = row["instrument_key"]
        weekly = row.get("weekly", False)

        # Generic index — all underlyings
        if itype == "FUT":
            gen_idx[(underlying_key, "FUT", expiry_date, 0, False)] = ikey
            gen_lot_sizes[(underlying_key, expiry_date)] = int(row.get("lot_size", 0))
        elif itype in ("PE", "CE"):
            strike = int(round(row.get("strike_price", 0)))
            gen_idx[(underlying_key, itype, expiry_date, strike, weekly)] = ikey

        # Nifty-specific index (backward compat)
        if underlying_key != _NIFTY_UNDERLYING:
            continue
        if itype == "FUT":
            nifty_idx[("FUT", expiry_date)] = ikey
            nifty_lot_sizes[expiry_date] = int(row.get("lot_size", 0))
        elif itype in ("PE", "CE"):
            strike = int(round(row.get("strike_price", 0)))
            nifty_idx[(itype, expiry_date, strike, weekly)] = ikey

    _index          = nifty_idx
    _LOT_SIZES      = nifty_lot_sizes
    _generic_index  = gen_idx
    _generic_lot_sizes = gen_lot_sizes
    _loaded = True
    print(f"  Indexed {len(gen_idx)} NSE F&O instruments across all underlyings.", flush=True)


def _ensure_loaded():
    if not _loaded:
        refresh()


# -----------------------------------------------------------
# Nifty-specific helpers (backward compat)
# -----------------------------------------------------------

def nifty_fut_ikey(expiry: date) -> str | None:
    _ensure_loaded()
    key = _index.get(("FUT", expiry))
    if key is None:
        print(f"  [fo_instruments]  Nifty FUT {expiry} not found", flush=True)
    return key


def nifty_pe_ikey(expiry: date, strike: int, weekly: bool = False) -> str | None:
    _ensure_loaded()
    key = _index.get(("PE", expiry, strike, weekly))
    if key is None:
        print(f"  [fo_instruments]  Nifty {strike} PE {expiry} (weekly={weekly}) not found",
              flush=True)
    return key


def nifty_lot_size(expiry: date) -> int | None:
    _ensure_loaded()
    return _LOT_SIZES.get(expiry)


# -----------------------------------------------------------
# Generic helpers — any NSE F&O underlying
# -----------------------------------------------------------

def fo_ikey(
    symbol: str,
    instrument_type: str,
    expiry: date,
    strike: int = 0,
    weekly: bool = False,
) -> str | None:
    """
    Instrument key for any NSE F&O contract.

    symbol          : 'NIFTY50' | 'BANKNIFTY' | 'FINNIFTY' | 'MIDCPNIFTY'
    instrument_type : 'FUT' | 'PE' | 'CE'
    expiry          : date object — use resolve_expiry() to convert from string
    strike          : 0 for FUT, actual strike for PE/CE
    weekly          : True for weekly options
    """
    _ensure_loaded()
    underlying = _UNDERLYING_KEYS.get(symbol.upper())
    if not underlying:
        print(f"  [fo_instruments]  unknown symbol {symbol!r} — "
              f"supported: {list(_UNDERLYING_KEYS)}", flush=True)
        return None
    key = _generic_index.get((underlying, instrument_type.upper(), expiry, strike, weekly))
    if key is None:
        print(f"  [fo_instruments]  {symbol} {instrument_type} {strike or ''} "
              f"{expiry} (weekly={weekly}) not found in index", flush=True)
    return key


def fo_lot_size(symbol: str, expiry: date) -> int | None:
    """Lot size for any NSE F&O underlying at the given expiry."""
    _ensure_loaded()
    underlying = _UNDERLYING_KEYS.get(symbol.upper())
    if not underlying:
        return None
    return _generic_lot_sizes.get((underlying, expiry))


def resolve_expiry(symbol: str, expiry_str: str) -> date | None:
    """
    Resolve an expiry string to an exact date.

    Accepts:
        '26 May 2026'   → date(2026, 5, 26)   (parsed directly)
        'May 2026'      → monthly expiry date for that symbol/month
                          (found via FUT entry in index — one per month)
    Returns None if not found.
    """
    _ensure_loaded()
    expiry_str = expiry_str.strip()

    # Full date format
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(expiry_str, fmt).date()
        except ValueError:
            pass

    # Month+year only — look up monthly FUT expiry for that symbol/month
    for fmt in ("%b %Y", "%B %Y"):
        try:
            ref = datetime.strptime(expiry_str, fmt)
            break
        except ValueError:
            pass
    else:
        print(f"  [fo_instruments]  cannot parse expiry {expiry_str!r}", flush=True)
        return None

    underlying = _UNDERLYING_KEYS.get(symbol.upper())
    if not underlying:
        return None

    # FUT entries have weekly=False and strike=0; one per calendar month
    candidates = [
        exp for (uk, itype, exp, strike, weekly) in _generic_index
        if uk == underlying
        and itype == "FUT"
        and exp.month == ref.month
        and exp.year  == ref.year
    ]
    if not candidates:
        print(f"  [fo_instruments]  no FUT expiry found for {symbol} {expiry_str}", flush=True)
        return None
    return min(candidates)   # earliest = only monthly FUT for that month


# -----------------------------------------------------------
# Instrument search — used by manage_trades.py CLI
# -----------------------------------------------------------

_SYMBOL_ALIASES: dict[str, str] = {
    "nifty":       "NIFTY50",
    "nifty50":     "NIFTY50",
    "bank":        "BANKNIFTY",
    "banknifty":   "BANKNIFTY",
    "fin":         "FINNIFTY",
    "finnifty":    "FINNIFTY",
    "midcap":      "MIDCPNIFTY",
    "mid":         "MIDCPNIFTY",
    "midcpnifty":  "MIDCPNIFTY",
}

_MONTH_NUMS: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,  "may": 5,  "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3,    "april": 4,
    "june": 6,    "july": 7,     "august": 8,   "september": 9,
    "october": 10, "november": 11, "december": 12,
}


def search_instruments(query: str) -> list[dict]:
    """
    Search for F&O instruments by natural language query.

    Examples:
        'nifty 25000 ce'
        'banknifty 57000 pe may'
        'banknifty fut'
        'finnifty 24000 ce jun'

    Returns list of dicts (sorted by expiry, monthly before weekly):
        symbol, instrument_type, strike, expiry (date), expiry_str, weekly, instrument_key
    Only includes expiries on or after today.
    """
    _ensure_loaded()

    symbol: str | None = None
    itype:  str | None = None
    strike: int | None = None
    month:  int | None = None

    for token in query.lower().split():
        if token in _SYMBOL_ALIASES:
            symbol = _SYMBOL_ALIASES[token]
        elif token in ("pe", "ce", "fut", "eq"):
            itype = token.upper()
        elif token.lstrip("-").isdigit():
            strike = int(token)
        elif token in _MONTH_NUMS:
            month = _MONTH_NUMS[token]

    if not symbol or not itype:
        return []

    underlying = _UNDERLYING_KEYS.get(symbol)
    if not underlying:
        return []

    today = date.today()
    results: list[dict] = []

    for (uk, it, expiry, s, weekly), ikey in _generic_index.items():
        if uk != underlying or it != itype:
            continue
        if expiry < today:
            continue
        if itype in ("PE", "CE") and strike is not None and s != strike:
            continue
        if month is not None and expiry.month != month:
            continue

        results.append({
            "symbol":          symbol,
            "instrument_type": it,
            "strike":          s if it in ("PE", "CE") else None,
            "expiry":          expiry,
            "expiry_str":      expiry.strftime("%d %b %Y"),
            "weekly":          weekly,
            "instrument_key":  ikey,
        })

    # Monthly expiries before weekly, then sort by date
    results.sort(key=lambda r: (r["expiry"], r["weekly"]))
    return results
