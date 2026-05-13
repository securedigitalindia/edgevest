"""
Looks up Upstox instrument keys for Nifty F&O contracts.

Keys are numeric IDs (e.g. NSE_FO|66071) — they cannot be constructed
from symbol/expiry/strike strings. This module downloads the NSE instrument
file once per session and builds an index for fast lookups.

Call refresh() at startup to pre-load the index.
"""

import gzip
import json
import requests
from datetime import date, datetime, timezone

_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
_NIFTY_UNDERLYING = "NSE_INDEX|Nifty 50"

# In-memory index built from the instrument file
# Keys: ("FUT", expiry_date) | ("PE", expiry_date, strike_int) | ("CE", expiry_date, strike_int)
_index: dict = {}
_loaded = False


def refresh():
    """Download and index the NSE F&O instrument file. Call once at startup."""
    global _index, _loaded
    print("  Downloading NSE F&O instrument list from Upstox...", flush=True)
    resp = requests.get(_INSTRUMENTS_URL, timeout=30)
    resp.raise_for_status()
    instruments = json.loads(gzip.decompress(resp.content))

    idx = {}
    for row in instruments:
        if row.get("segment") != "NSE_FO":
            continue
        if row.get("underlying_key") != _NIFTY_UNDERLYING:
            continue

        expiry_ms = row.get("expiry")
        if not expiry_ms:
            continue
        expiry_date = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc).date()
        itype = row.get("instrument_type")
        ikey  = row["instrument_key"]

        if itype == "FUT":
            idx[("FUT", expiry_date)] = ikey
        elif itype in ("PE", "CE"):
            strike = int(round(row.get("strike_price", 0)))
            weekly = row.get("weekly", False)
            idx[(itype, expiry_date, strike, weekly)] = ikey

    _index = idx
    _loaded = True
    print(f"  Indexed {len(_index)} Nifty F&O instruments.", flush=True)


def _ensure_loaded():
    if not _loaded:
        refresh()


def nifty_fut_ikey(expiry: date) -> str | None:
    """Instrument key for the Nifty monthly futures contract expiring on `expiry`."""
    _ensure_loaded()
    key = _index.get(("FUT", expiry))
    if key is None:
        print(f"  [fo_instruments]  Nifty FUT {expiry} not found in index — "
              "run refresh() or check expiry date", flush=True)
    return key


def nifty_pe_ikey(expiry: date, strike: int, weekly: bool = False) -> str | None:
    """Instrument key for a Nifty PE option at given expiry and strike."""
    _ensure_loaded()
    key = _index.get(("PE", expiry, strike, weekly))
    if key is None:
        print(f"  [fo_instruments]  Nifty {strike} PE {expiry} (weekly={weekly}) "
              "not found in index", flush=True)
    return key


def nifty_lot_size(expiry: date) -> int | None:
    """Return the lot size for the Nifty contract at the given expiry (from instrument file)."""
    _ensure_loaded()
    # lot size is on the FUT row; options share the same lot size
    # re-scan for lot_size since we don't cache it in the index
    # (called rarely — acceptable cost)
    if not _loaded:
        return None
    return _LOT_SIZES.get(expiry)


# Secondary cache for lot sizes (populated during refresh)
_LOT_SIZES: dict[date, int] = {}


def refresh():  # noqa: F811 — intentional override to also populate _LOT_SIZES
    """Download and index the NSE F&O instrument file. Call once at startup."""
    global _index, _loaded, _LOT_SIZES
    print("  Downloading NSE F&O instrument list from Upstox...", flush=True)
    resp = requests.get(_INSTRUMENTS_URL, timeout=30)
    resp.raise_for_status()
    instruments = json.loads(gzip.decompress(resp.content))

    idx       = {}
    lot_sizes = {}
    for row in instruments:
        if row.get("segment") != "NSE_FO":
            continue
        if row.get("underlying_key") != _NIFTY_UNDERLYING:
            continue

        expiry_ms = row.get("expiry")
        if not expiry_ms:
            continue
        expiry_date = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc).date()
        itype  = row.get("instrument_type")
        ikey   = row["instrument_key"]
        weekly = row.get("weekly", False)

        if itype == "FUT":
            idx[("FUT", expiry_date)] = ikey
            lot_sizes[expiry_date] = int(row.get("lot_size", 0))
        elif itype in ("PE", "CE"):
            strike = int(round(row.get("strike_price", 0)))
            idx[(itype, expiry_date, strike, weekly)] = ikey

    _index     = idx
    _LOT_SIZES = lot_sizes
    _loaded    = True
    print(f"  Indexed {len(_index)} Nifty F&O instruments.", flush=True)
