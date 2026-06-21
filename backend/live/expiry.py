"""
Expiry date fetcher — pulls live option expiry dates from Upstox API.

All expiry dates used in trade suggestions come from here.
No manual date calculation — whatever Upstox returns is authoritative.

Usage:
    cache = ExpiryCache()
    cache.refresh()                         # call once at startup
    expiries = cache.get("NIFTY50")
    near = expiries["quarterly"][0]         # nearest quarterly
    far  = expiries["quarterly"][2]         # 3rd quarterly out
"""

import upstox_client
from datetime import date
from config import UPSTOX_ACCESS_TOKEN, UPSTOX_INSTRUMENT_KEYS

# Quarterly expiry months (NSE convention)
_QUARTERLY_MONTHS = {3, 6, 9, 12}


def _categorise(instruments: list) -> dict[str, list[date]]:
    """
    Split InstrumentData list into weekly / monthly / quarterly buckets.
    Only PE contracts are checked (expiry dates are same for CE/PE).
    Returns lists sorted ascending (nearest first).
    """
    weekly, monthly, quarterly = set(), set(), set()

    for inst in instruments:
        if inst.instrument_type != "PE" or inst.expiry is None:
            continue
        d = inst.expiry.date()
        if inst.weekly:
            weekly.add(d)
        elif d.month in _QUARTERLY_MONTHS:
            quarterly.add(d)
        else:
            monthly.add(d)

    return {
        "weekly":    sorted(weekly),
        "monthly":   sorted(monthly),
        "quarterly": sorted(quarterly),
    }


class ExpiryCache:
    """
    Fetches and caches expiry dates per symbol from Upstox.
    Call refresh() once at poller startup.
    Thread-safety not required — single-threaded polling loop.
    """

    def __init__(self):
        self._cache: dict[str, dict[str, list[date]]] = {}
        self._api = None

    def _get_api(self) -> upstox_client.OptionsApi:
        if self._api is None:
            cfg = upstox_client.Configuration()
            cfg.access_token = UPSTOX_ACCESS_TOKEN
            self._api = upstox_client.OptionsApi(upstox_client.ApiClient(cfg))
        return self._api

    def refresh(self, symbol_names: list[str] | None = None):
        """
        Fetch expiry dates for all symbols (or a subset).
        symbol_names: list of names from config.SYMBOLS e.g. ["NIFTY50"]
        """
        targets = symbol_names or list(UPSTOX_INSTRUMENT_KEYS.keys())
        api     = self._get_api()

        for name in targets:
            ikey = UPSTOX_INSTRUMENT_KEYS.get(name)
            if not ikey:
                continue
            try:
                resp = api.get_option_contracts(ikey)
                self._cache[name] = _categorise(resp.data or [])
                exp = self._cache[name]
                print(f"  {name}  expiries loaded — "
                      f"weekly:{len(exp['weekly'])}  "
                      f"monthly:{len(exp['monthly'])}  "
                      f"quarterly:{len(exp['quarterly'])}")
            except Exception as e:
                print(f"  [expiry fetch failed — {name}]  {e}")
                self._cache[name] = {"weekly": [], "monthly": [], "quarterly": []}

    def get(self, symbol_name: str) -> dict[str, list[date]]:
        """Return cached expiry buckets for a symbol."""
        return self._cache.get(symbol_name, {"weekly": [], "monthly": [], "quarterly": []})

    def pick(self, symbol_name: str, expiry_type: str, index: int) -> date | None:
        """
        Pick a specific expiry.
        expiry_type : "weekly" | "monthly" | "quarterly"
        index       : 0 = nearest, 1 = next, 2 = one after, ...
        Returns None if not enough expiries available.
        """
        bucket = self.get(symbol_name).get(expiry_type, [])
        if index >= len(bucket):
            print(f"  [expiry] {symbol_name} {expiry_type}[{index}] — "
                  f"only {len(bucket)} available")
            return None
        return bucket[index]


# Module-level singleton — shared across trade_suggestions and poller
expiry_cache = ExpiryCache()
