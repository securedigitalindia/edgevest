"""
Upstox API client using the official upstox-python-sdk.

Authentication:
    Upstox access tokens expire daily at midnight IST.
    Generate your token each morning from:
    https://developer.upstox.com → Your App → Get Token

    Then set it before running the poller:
        export UPSTOX_ACCESS_TOKEN="your_daily_token"

    For a 1-year read-only token (no daily renewal):
    https://developer.upstox.com → Your App → Analytics Token
"""

import upstox_client
from upstox_client.rest import ApiException
from config import UPSTOX_ACCESS_TOKEN

# Module-level singleton — created once on first call, reused every poll tick
_api: upstox_client.MarketQuoteApi | None = None


def _get_api() -> upstox_client.MarketQuoteApi:
    global _api
    if _api is not None:
        return _api

    if not UPSTOX_ACCESS_TOKEN:
        raise RuntimeError(
            "UPSTOX_ACCESS_TOKEN is not set.\n"
            "Run:  export UPSTOX_ACCESS_TOKEN='your_daily_token'\n"
            "Get it from: https://developer.upstox.com → Your App → Get Token\n"
            "Or generate a 1-year Analytics Token for hassle-free daily use."
        )

    cfg = upstox_client.Configuration()
    cfg.access_token = UPSTOX_ACCESS_TOKEN
    _api = upstox_client.MarketQuoteApi(upstox_client.ApiClient(cfg))
    return _api


def get_ltp(instrument_keys: list[str]) -> dict[str, float]:
    """
    Fetch Last Traded Price for one or more instrument keys.
    Returns {instrument_key: ltp_float} using pipe-format keys (matching input).

    The SDK response uses colon-separated keys (e.g. "NSE_INDEX:Nifty 50").
    This function normalises them back to pipe format so callers can do
    consistent dict lookups using the same keys they passed in.
    """
    api = _get_api()
    try:
        response = api.ltp(
            symbol=",".join(instrument_keys),
            api_version="2.0",
        )
    except ApiException as e:
        if e.status == 401:
            raise RuntimeError(
                "Upstox token rejected (401). "
                "Tokens expire daily — regenerate and re-export UPSTOX_ACCESS_TOKEN."
            ) from e
        raise RuntimeError(f"Upstox API error {e.status}: {e.reason}") from e

    result = {}
    for resp_key, quote in (response.data or {}).items():
        # For indices, resp_key normalises fine ("NSE_INDEX:Nifty 50" → pipe).
        # For equities, resp_key uses trading symbol ("NSE_EQ:RELIANCE") while
        # our input key uses ISIN ("NSE_EQ|INE002A01018").
        # instrument_token always mirrors the input key — use it for reliable lookup.
        key = quote.instrument_token or resp_key.replace(":", "|", 1)
        result[key] = float(quote.last_price)
    return result
