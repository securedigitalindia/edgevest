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
import glob
import json
import os
import requests
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo

_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
_CACHE_DIR       = os.path.join(os.path.dirname(__file__), "..", "data")
_IST             = ZoneInfo("Asia/Kolkata")

# Nifty-specific index (kept for backward compat)
_NIFTY_UNDERLYING = "NSE_INDEX|Nifty 50"
_index:     dict = {}
_LOT_SIZES: dict[date, int] = {}

# Generic index — all NSE_FO underlyings
# key: (underlying_key, instrument_type, expiry_date, strike_int, weekly) → ikey
_generic_index:     dict[tuple, str] = {}
# key: (underlying_key, expiry_date) → lot_size
_generic_lot_sizes: dict[tuple, int] = {}
# trading symbol → underlying_key  (e.g. "HINDALCO" → "NSE_EQ|INE038A01020")
_symbol_to_underlying: dict[str, str] = {}
# equity index: uppercase trading_symbol → {instrument_key, name, lot_size}
_eq_index: dict[str, dict] = {}

_loaded = False


def _today_cache_path() -> str:
    today = datetime.now(timezone.utc).astimezone(_IST).strftime("%Y-%m-%d")
    return os.path.join(_CACHE_DIR, f"nse_instruments_{today}.json")


def _purge_old_cache():
    """Delete instrument cache files from previous days."""
    keep = _today_cache_path()
    for f in glob.glob(os.path.join(_CACHE_DIR, "nse_instruments_*.json")):
        if f != keep:
            try:
                os.remove(f)
            except OSError:
                pass

# Map from friendly symbol name → underlying_key in NSE instrument file
_UNDERLYING_KEYS: dict[str, str] = {
    "NIFTY50":    "NSE_INDEX|Nifty 50",
    "BANKNIFTY":  "NSE_INDEX|Nifty Bank",
    "FINNIFTY":   "NSE_INDEX|Nifty Fin Services",
    "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
    "SENSEX":     "BSE_INDEX|SENSEX",
}

from config import SPOT_IKEYS  # re-exported for backward compat with existing imports


def refresh(force: bool = False):
    """
    Load and index the NSE F&O instrument list.
    Reads from a local date-stamped cache if today's file exists;
    downloads from Upstox otherwise (or when force=True).
    """
    global _index, _LOT_SIZES, _generic_index, _generic_lot_sizes, _symbol_to_underlying, _eq_index, _loaded

    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_path = _today_cache_path()

    if not force and os.path.exists(cache_path):
        print(f"  Loading NSE F&O instrument list from cache ({os.path.basename(cache_path)})...",
              flush=True)
        with open(cache_path, "r") as f:
            instruments = json.load(f)
    else:
        print("  Downloading NSE F&O instrument list from Upstox...", flush=True)
        resp = requests.get(_INSTRUMENTS_URL, timeout=30)
        resp.raise_for_status()
        instruments = json.loads(gzip.decompress(resp.content))
        with open(cache_path, "w") as f:
            json.dump(instruments, f)
        _purge_old_cache()
        print(f"  Saved to cache ({os.path.basename(cache_path)}).", flush=True)

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
        lot_sz = int(row.get("lot_size", 0))
        if itype == "FUT":
            gen_idx[(underlying_key, "FUT", expiry_date, 0, False)] = ikey
            gen_lot_sizes[(underlying_key, expiry_date)] = lot_sz
        elif itype in ("PE", "CE"):
            strike = int(round(row.get("strike_price", 0)))
            gen_idx[(underlying_key, itype, expiry_date, strike, weekly)] = ikey
            # PE/CE share the same lot_size as FUT for the same expiry
            gen_lot_sizes.setdefault((underlying_key, expiry_date), lot_sz)

        # Nifty-specific index (backward compat)
        if underlying_key != _NIFTY_UNDERLYING:
            continue
        if itype == "FUT":
            nifty_idx[("FUT", expiry_date)] = ikey
            nifty_lot_sizes[expiry_date] = int(row.get("lot_size", 0))
        elif itype in ("PE", "CE"):
            strike = int(round(row.get("strike_price", 0)))
            nifty_idx[(itype, expiry_date, strike, weekly)] = ikey

    # Build symbol → underlying_key map from underlying_symbol field (for F&O stock search)
    sym_to_uk: dict[str, str] = {}
    for row in instruments:
        if row.get("segment") != "NSE_FO":
            continue
        us = row.get("underlying_symbol", "").strip().upper()
        uk = row.get("underlying_key", "")
        if us and uk and us not in sym_to_uk:
            sym_to_uk[us] = uk

    # Equity index: NSE_EQ instruments with instrument_type == 'EQ'
    eq_idx: dict[str, dict] = {}
    for row in instruments:
        if row.get("segment") != "NSE_EQ" or row.get("instrument_type") != "EQ":
            continue
        sym = row.get("trading_symbol", "").strip().upper()
        if sym:
            eq_idx[sym] = {
                "instrument_key": row["instrument_key"],
                "name":           row.get("name", sym),
                "lot_size":       int(row.get("lot_size", 1)),
            }

    _index                = nifty_idx
    _LOT_SIZES            = nifty_lot_sizes
    _generic_index        = gen_idx
    _generic_lot_sizes    = gen_lot_sizes
    _symbol_to_underlying = sym_to_uk
    _eq_index             = eq_idx
    _loaded = True
    print(f"  Indexed {len(gen_idx)} NSE F&O + {len(eq_idx)} NSE EQ instruments.", flush=True)


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
        elif token.upper() in _symbol_to_underlying:
            symbol = token.upper()

    if not itype:
        itype = "EQ"

    # Equity search — prefix match on trading symbol
    if itype == "EQ":
        q_upper = query.upper().replace(" EQ", "").replace("EQ ", "").strip()
        matches = [
            {
                "symbol":          sym,
                "instrument_type": "EQ",
                "strike":          None,
                "expiry":          None,
                "expiry_str":      "",
                "weekly":          False,
                "instrument_key":  info["instrument_key"],
                "lot_size":        info["lot_size"],
                "name":            info["name"],
            }
            for sym, info in _eq_index.items()
            if sym.startswith(q_upper) or q_upper in sym
        ]
        matches.sort(key=lambda r: (not r["symbol"].startswith(q_upper), r["symbol"]))
        return matches[:12]

    if not symbol:
        return []

    # Resolve underlying_key: known index aliases first, then stock symbol map
    underlying = _UNDERLYING_KEYS.get(symbol) or _symbol_to_underlying.get(symbol)
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

        lot_size = _generic_lot_sizes.get((uk, expiry)) or 0
        results.append({
            "symbol":          symbol,
            "instrument_type": it,
            "strike":          s if it in ("PE", "CE") else None,
            "expiry":          expiry,
            "expiry_str":      expiry.strftime("%d %b %Y"),
            "weekly":          weekly,
            "instrument_key":  ikey,
            "lot_size":        lot_size,
        })

    # Monthly expiries before weekly, then sort by date
    results.sort(key=lambda r: (r["expiry"], r["weekly"]))
    return results
