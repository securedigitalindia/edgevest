"""
Writes LTP ticks to the DB on every poll cycle.
Maintains a mapping of instrument_key → symbol_name for the write path.
"""

from db.queries import write_ticks

_ikey_to_name: dict[str, str] = {}


def init(ikey_to_name: dict[str, str]):
    """Call once at poller startup with the instrument_key → symbol_name map."""
    global _ikey_to_name
    _ikey_to_name = ikey_to_name


def record(prices: dict[str, float]):
    """
    Convert instrument_key → ltp prices to symbol_name → ltp and write to ticks.
    Silently skips any instrument key not in the map.
    """
    named = {_ikey_to_name[k]: v for k, v in prices.items() if k in _ikey_to_name}
    if named:
        write_ticks(named)
