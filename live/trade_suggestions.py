"""
Trade suggestion templates.

All expiry dates come from Upstox API via live.expiry.expiry_cache.
No hardcoded or manually calculated dates.

Params for each template come entirely from config.TRIGGERS "trades" list.

Template types:
    nifty_pe_cal_qtrly              near=quarterly[0], far=quarterly[far_index]
    nifty_pe_cal_monthly            near=monthly[0],   far=monthly[far_index]
    nifty_pe_cal_weekly_to_monthly  near=weekly[0],    far=monthly[far_index]

Common params (all types):
    itm_points   int   — strike = round(CMP + itm_points, strike_step)
    strike_step  int   — rounding multiple for strike
    far_index    int   — which expiry in the far bucket (0=nearest, 1=next, ...)
"""

from live.expiry import expiry_cache
from datetime import date


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strike(ltp: float, itm_points: int, strike_step: int) -> int:
    return round((ltp + itm_points) / strike_step) * strike_step


def _build(title: str, ltp: float, symbol: str,
           near: date | None, far: date | None,
           near_label: str, far_label: str,
           strike: int, itm_points: int) -> dict:
    """Assemble the trade dict from computed parts."""
    if near is None or far is None:
        return {
            "title": title,
            "legs":  [],
            "rationale": "Could not build trade — expiry dates unavailable from Upstox.",
        }

    near_str = near.strftime("%d %b %Y")
    far_str  = far.strftime("%d %b %Y")

    return {
        "title": title,
        "legs": [
            {
                "action":     "SELL",
                "instrument": f"NIFTY {near_str} {strike:,} PE",
            },
            {
                "action":     "BUY",
                "instrument": f"NIFTY {far_str} {strike:,} PE",
            },
        ],
        "rationale": (
            f"Strike {strike:,} is {itm_points:,} pts above CMP {ltp:,.0f} (ITM put). "
            f"Sell {near_str}, buy {far_str}."
        ),
    }


# ---------------------------------------------------------------------------
# Trade templates
# ---------------------------------------------------------------------------

def nifty_pe_cal_qtrly(ltp: float, symbol: str, params: dict) -> dict:
    """
    PE Calendar Spread — both legs on quarterly expiries.
    SELL: next quarterly
    BUY:  quarterly[far_index]  (default 1 = second quarterly out)

    Params: itm_points, strike_step, far_index (default 1)
    """
    strike    = _strike(ltp, params["itm_points"], params["strike_step"])
    far_index = params.get("far_index", 1)

    near = expiry_cache.pick(symbol, "quarterly", 0)
    far  = expiry_cache.pick(symbol, "quarterly", far_index)

    return _build(
        "NIFTY ITM PE Calendar Spread (Quarterly)",
        ltp, symbol, near, far,
        "near quarterly", f"quarterly[{far_index}]",
        strike, params["itm_points"],
    )


def nifty_pe_cal_monthly(ltp: float, symbol: str, params: dict) -> dict:
    """
    PE Calendar Spread — both legs on monthly expiries.
    SELL: next monthly
    BUY:  monthly[far_index]  (default 1 = next monthly)

    Params: itm_points, strike_step, far_index (default 1)
    """
    strike    = _strike(ltp, params["itm_points"], params["strike_step"])
    far_index = params.get("far_index", 1)

    near = expiry_cache.pick(symbol, "monthly", 0)
    far  = expiry_cache.pick(symbol, "monthly", far_index)

    return _build(
        "NIFTY ITM PE Calendar Spread (Monthly)",
        ltp, symbol, near, far,
        "near monthly", f"monthly[{far_index}]",
        strike, params["itm_points"],
    )


def nifty_pe_cal_weekly_to_monthly(ltp: float, symbol: str, params: dict) -> dict:
    """
    PE Calendar Spread — sell weekly, buy monthly.
    SELL: next weekly
    BUY:  monthly[far_index]  (default 0 = nearest monthly)

    Params: itm_points, strike_step, far_index (default 0)
    """
    strike    = _strike(ltp, params["itm_points"], params["strike_step"])
    far_index = params.get("far_index", 0)

    near = expiry_cache.pick(symbol, "weekly",  0)
    far  = expiry_cache.pick(symbol, "monthly", far_index)

    return _build(
        "NIFTY ITM PE Calendar Spread (Weekly → Monthly)",
        ltp, symbol, near, far,
        "near weekly", f"monthly[{far_index}]",
        strike, params["itm_points"],
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, callable] = {
    "nifty_pe_cal_qtrly":             nifty_pe_cal_qtrly,
    "nifty_pe_cal_monthly":           nifty_pe_cal_monthly,
    "nifty_pe_cal_weekly_to_monthly": nifty_pe_cal_weekly_to_monthly,
}


def build_trade_suggestion(trade_cfg: dict, ltp: float, symbol: str) -> dict | None:
    fn = _REGISTRY.get(trade_cfg.get("type", ""))
    if fn is None:
        print(f"  [trade] unknown template: {trade_cfg.get('type')!r}. "
              f"Valid: {list(_REGISTRY)}")
        return None
    return fn(ltp, symbol, trade_cfg["params"])


def build_all_trades(trades_cfg: list, ltp: float, symbol: str) -> list[dict]:
    results = []
    for trade_cfg in trades_cfg:
        suggestion = build_trade_suggestion(trade_cfg, ltp, symbol)
        if suggestion:
            results.append(suggestion)
    return results
