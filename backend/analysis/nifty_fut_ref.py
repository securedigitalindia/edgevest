"""
Shared Upstox-direct market-data helpers for the PE ratio diagonal simulator
(v1 live + v2 historical replay) — futures reference price, option
instrument-key resolution, and historical candles. Nothing in this module
touches the local DB: option_chain_5m is only ever a 5-min snapshot capture
(and has real gaps whenever the poller wasn't running), while Upstox's
History API works per-instrument for any individual contract — including
options — going back further than any local capture window, so v2 sources
every leg's historical price directly from Upstox rather than depending on
what happened to get captured locally.

Why futures, not index spot: option_chain_5m's spot_ltp column (and the
option-chain API response it comes from) is Upstox's underlying_spot_price
field — the NIFTY50 INDEX price, not the futures price. Strike selection and
every "if spot moved" simulation in this tool is meant to track the price
the trade is actually priced/executed off (the current-month future), which
carries a real basis over the index (observed 2026-09-07: index ~23900s,
front-month NIFTY26SEPFUT LTP exactly 24048 — a ~150pt gap, not noise).

Front-month contract, lot size, and its instrument_key are resolved live
via Upstox's instrument search rather than hardcoded, since both roll
over time (lot size in particular — this repo's older scripts assumed 65,
still correct as of 2026-09, but don't bake in a number a corporate action
could change without anyone noticing).
"""
from datetime import date, datetime, time, timedelta, timezone

import upstox_client

from config import UPSTOX_ACCESS_TOKEN, UPSTOX_INSTRUMENT_KEYS
from live.holidays import is_trading_day

_api_cache: dict[str, object] = {}

IST = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN = time(9, 15)


def _get_api(cls):
    if cls.__name__ not in _api_cache:
        cfg = upstox_client.Configuration()
        cfg.access_token = UPSTOX_ACCESS_TOKEN
        _api_cache[cls.__name__] = cls(upstox_client.ApiClient(cfg))
    return _api_cache[cls.__name__]


def resolve_front_month_future(underlying: str = "NIFTY") -> dict:
    """
    Nearest-expiry FUT contract for `underlying` (exact name match — Upstox's
    search also returns NIFTYNXT50/NIFTYFPI for a query of "NIFTY FUT").
    Returns {instrument_key, expiry, lot_size, trading_symbol}.
    """
    api = _get_api(upstox_client.InstrumentsApi)
    resp = api.search_instrument(f"{underlying} FUT")
    candidates = [
        d for d in (resp.data or [])
        if d["instrument_type"] == "FUT" and d["name"] == underlying
    ]
    if not candidates:
        raise RuntimeError(f"No FUT contracts found for {underlying} via search_instrument.")
    nearest = min(candidates, key=lambda d: d["expiry"])
    return {
        "instrument_key": nearest["instrument_key"],
        "expiry": nearest["expiry"],
        "lot_size": int(nearest["lot_size"]),
        "trading_symbol": nearest["trading_symbol"],
    }


def get_live_fut_ltp(instrument_key: str) -> float:
    """Live LTP for one instrument_key via Upstox's ltp quote endpoint."""
    api = _get_api(upstox_client.MarketQuoteApi)
    resp = api.ltp(instrument_key, "v2")
    row = next(iter(resp.data.values()))
    return float(row.last_price)


def fetch_candles_utc(instrument_key: str, from_date: str, to_date: str) -> dict:
    """
    5-min candles for ANY instrument_key (future, option, equity...) over
    [from_date, to_date] (inclusive, 'YYYY-MM-DD'), keyed by
    'YYYY-MM-DDTHH:MM:SSZ' (UTC, 5-min-boundary — matches option_chain_5m's
    ts convention so lookups line up), value = candle close. One call
    returns the whole date range, not one call per day. Upstox's history
    endpoint has no same-day data — from_date/to_date must be fully past
    trading days.
    """
    api = _get_api(upstox_client.HistoryV3Api)
    resp = api.get_historical_candle_data1(instrument_key, "minutes", "5", to_date, from_date)
    candles = resp.data.candles or []

    lookup = {}
    for row in candles:
        ist_ts = row[0]  # e.g. '2026-09-03T15:30:00+05:30'
        close = float(row[4])
        dt_ist = datetime.fromisoformat(ist_ts)
        dt_utc = dt_ist.astimezone(timezone.utc)
        lookup[dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")] = close
    return lookup


def fetch_intraday_candles_utc(instrument_key: str) -> dict:
    """
    Today's 5-min candles for ANY instrument_key, via Upstox's intra-day
    endpoint (`get_intra_day_candle_data`) — the complement to
    `fetch_candles_utc`, which has no same-day data. Same key/value shape
    ('YYYY-MM-DDTHH:MM:SSZ' -> close), so the two can be merged into one
    continuous lookup for "history through today".
    """
    api = _get_api(upstox_client.HistoryV3Api)
    resp = api.get_intra_day_candle_data(instrument_key, "minutes", "5")
    candles = resp.data.candles or []

    lookup = {}
    for row in candles:
        ist_ts = row[0]
        close = float(row[4])
        dt_ist = datetime.fromisoformat(ist_ts)
        dt_utc = dt_ist.astimezone(timezone.utc)
        lookup[dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")] = close
    return lookup


def resolve_option_instrument_keys(symbol: str, expiry_date: str, strikes: set[float],
                                    opt_type: str = "PE") -> dict[float, str]:
    """
    instrument_key per strike for one expiry, via one get_put_call_option_chain
    call (returns the whole chain — filtered down to just the strikes asked
    for and the requested opt_type, "PE" or "CE").
    """
    ikey = UPSTOX_INSTRUMENT_KEYS[symbol]
    api = _get_api(upstox_client.OptionsApi)
    resp = api.get_put_call_option_chain(ikey, expiry_date)
    leg_attr = "call_options" if opt_type == "CE" else "put_options"
    out = {}
    for row in resp.data or []:
        leg = getattr(row, leg_attr, None)
        if row.strike_price in strikes and leg is not None:
            out[row.strike_price] = leg.instrument_key
    return out


def resolve_pe_instrument_keys(symbol: str, expiry_date: str, strikes: set[float]) -> dict[float, str]:
    """Back-compat wrapper — PE-only, kept for any caller still using the old name."""
    return resolve_option_instrument_keys(symbol, expiry_date, strikes, opt_type="PE")


def resolve_reference_trading_day(now_utc: datetime | None = None) -> date:
    """
    The trading day whose close/last-trade a *live* quote right now actually
    reflects — not necessarily today. Upstox's LTP/quote endpoints return a
    price even outside market hours or on a holiday/weekend, but it's the
    previous session's last trade, not "today's" — before 09:15 IST on a
    trading day, or on a non-trading day at all, walk back to the most
    recent day the market was actually open, rather than labeling that
    stale price "today, DTE=1" when nothing has traded yet today.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST)
    d = now_ist.date()
    if is_trading_day(d) and now_ist.time() >= MARKET_OPEN:
        return d
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def nearest_price(lookup: dict, ts: str) -> float | None:
    """Exact-ts lookup first; falls back to the closest available ts (candle gaps happen)."""
    if ts in lookup:
        return lookup[ts]
    if not lookup:
        return None
    target = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    closest = min(lookup, key=lambda k: abs(datetime.strptime(k, "%Y-%m-%dT%H:%M:%SZ") - target))
    return lookup[closest]
