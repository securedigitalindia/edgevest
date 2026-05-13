"""
Trade suggestion templates.

All expiry dates come from Upstox API via live.expiry.expiry_cache.
No hardcoded or manually calculated dates.

Params for each template come entirely from config.TRIGGERS "trades" list.

Template types:
    nifty_pe_cal_qtrly              near=quarterly[0], far=quarterly[far_index]
    nifty_pe_cal_monthly            near=monthly[0],   far=monthly[far_index]
    nifty_pe_cal_weekly_to_monthly  near=weekly[0],    far=monthly[far_index]
    nifty_500_short_entry           short fut + sell PE on 500-multiple cross UP
    nifty_500_short_exit            close short — Nifty fell exit_distance pts

Common params (pe calendar types):
    itm_points   int   — strike = round(CMP + itm_points, strike_step)
    strike_step  int   — rounding multiple for strike
    far_index    int   — which expiry in the far bucket (0=nearest, 1=next, ...)

Params for nifty_500_short_entry:
    min_pe_distance_pct  float — PE strike must be at least this % below LTP (e.g. 3)
    strike_step          int   — PE strike rounded to this multiple (e.g. 500)
    exit_distance        int   — exit when Nifty falls this many pts from entry (e.g. 500)
    fut_lots             int   — number of lots for the short fut leg
    pe_lots              int   — number of lots for the sell PE leg

Params for nifty_500_short_exit (passed dynamically from recommended_trades DB row):
    entry_level, exit_level, pe_strike, expiry_str  — stored at entry time
    fut_lots, pe_lots                               — from config
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
# Nifty 500-multiple short strategy
# ---------------------------------------------------------------------------

def nifty_500_short_entry(ltp: float, symbol: str, params: dict) -> dict:
    """
    Entry trade when Nifty LTP crosses UP through a 500-multiple.
    SELL same-month monthly fut (fut_lots) + SELL same-month PE (pe_lots).
    PE strike: highest 500-multiple at least min_pe_distance_pct% below LTP.

    Returns a dict with private keys _pe_strike, _expiry_str, _exit_level for
    the trigger to store in recommended_trades before stripping them.
    """
    min_dist  = ltp * (params["min_pe_distance_pct"] / 100)
    step      = params["strike_step"]
    pe_strike = int((ltp - min_dist) // step) * step
    level     = int(ltp // 500) * 500
    exit_lvl  = level - params["exit_distance"]
    fut_lots  = params.get("fut_lots", 1)
    pe_lots   = params.get("pe_lots", 2)

    near = expiry_cache.pick(symbol, "monthly", 0)
    if near is None:
        return {
            "title": "Short Nifty 50",
            "legs":  [],
            "rationale": "Could not build trade — expiry dates unavailable from Upstox.",
            "_pe_strike":  pe_strike,
            "_expiry_str": None,
            "_exit_level": exit_lvl,
        }

    exp_str = near.strftime("%d %b %Y")
    return {
        "title": f"Short Nifty 50 @ {level:,}  [Exit target: {exit_lvl:,}]",
        "legs": [
            {
                "action":     "SELL",
                "instrument": f"NIFTY {exp_str} FUT",
                "note":       f"{fut_lots} lot{'s' if fut_lots > 1 else ''}",
            },
            {
                "action":     "SELL",
                "instrument": f"NIFTY {exp_str} {pe_strike:,} PE",
                "note":       f"{pe_lots} lots",
            },
        ],
        "rationale": (
            f"Nifty crossed {level:,} upward. Short fut + sell {pe_strike:,} PE "
            f"({int(ltp - pe_strike):,} pts / {(ltp - pe_strike) / ltp * 100:.1f}% below CMP). "
            f"Exit when Nifty falls to {exit_lvl:,} (−{params['exit_distance']} pts)."
        ),
        "_pe_strike":   pe_strike,
        "_expiry_str":  exp_str,
        "_expiry_date": near,       # date object — used by trigger to build F&O instrument keys
        "_exit_level":  exit_lvl,
    }


def nifty_500_short_exit(ltp: float, symbol: str, params: dict) -> dict:
    """
    Exit trade when Nifty falls exit_distance pts from the entry level.
    params come from the recommended_trades DB row merged with config params.
    """
    entry_lvl = int(params["entry_level"])
    exit_lvl  = int(params["exit_level"])
    pe_strike = int(params["pe_strike"])
    exp_str   = params["expiry_str"]
    fut_lots  = params.get("fut_lots", 1)
    pe_lots   = params.get("pe_lots", 2)

    return {
        "title": f"EXIT Short Nifty 50  [entered @ {entry_lvl:,}]",
        "legs": [
            {
                "action":     "BUY",
                "instrument": f"NIFTY {exp_str} FUT",
                "note":       f"{fut_lots} lot{'s' if fut_lots > 1 else ''} — close short",
            },
            {
                "action":     "BUY",
                "instrument": f"NIFTY {exp_str} {pe_strike:,} PE",
                "note":       f"{pe_lots} lots — buy back",
            },
        ],
        "rationale": (
            f"Nifty fell to {exit_lvl:,} (−{entry_lvl - exit_lvl} pts from entry {entry_lvl:,}). "
            f"Cover short fut and buy back {pe_strike:,} PE."
        ),
    }


def nifty_500_short_rollover(ltp: float, symbol: str, params: dict) -> dict:
    """
    Rollover trade when the active leg expires.
    4 legs: close old fut + PE, open new fut + PE.
    Params come from the trigger's _do_rollover() — includes old/new expiry,
    strikes, leg prices fetched live from Upstox, and lot sizes from DB snapshot.
    """
    old_exp  = params["old_expiry_str"]
    new_exp  = params["new_expiry_str"]
    old_pe   = params["old_pe_strike"]
    new_pe   = params["new_pe_strike"]
    fut_lots = params.get("fut_lots", 1)
    pe_lots  = params.get("pe_lots", 2)
    entry_lvl = params.get("entry_level", 0)

    def _price_note(price, suffix=""):
        return (f"@ {price:,.1f}  {suffix}").strip() if price is not None else suffix

    return {
        "title": f"ROLLOVER Short Nifty 50  [entry level: {entry_lvl:,}]",
        "legs": [
            {
                "action":     "BUY",
                "instrument": f"NIFTY {old_exp} FUT",
                "note":       _price_note(params.get("old_fut_price"),
                                          f"{fut_lots} lot — close expiring short fut"),
            },
            {
                "action":     "SELL",
                "instrument": f"NIFTY {new_exp} FUT",
                "note":       _price_note(params.get("new_fut_price"),
                                          f"{fut_lots} lot — open new month short fut"),
            },
            {
                "action":     "BUY",
                "instrument": f"NIFTY {old_exp} {old_pe:,} PE",
                "note":       _price_note(params.get("old_pe_price"),
                                          f"{pe_lots} lots — buy back expiring PE"),
            },
            {
                "action":     "SELL",
                "instrument": f"NIFTY {new_exp} {new_pe:,} PE",
                "note":       _price_note(params.get("new_pe_price"),
                                          f"{pe_lots} lots — sell new month PE"),
            },
        ],
        "rationale": (
            f"Expiry {old_exp} — rolling short to {new_exp}. "
            f"New PE strike: {new_pe:,} (>={params.get('min_pe_distance_pct', 3)}% below "
            f"CMP {ltp:,.0f})."
        ),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, callable] = {
    "nifty_pe_cal_qtrly":             nifty_pe_cal_qtrly,
    "nifty_pe_cal_monthly":           nifty_pe_cal_monthly,
    "nifty_pe_cal_weekly_to_monthly": nifty_pe_cal_weekly_to_monthly,
    "nifty_500_short_entry":    nifty_500_short_entry,
    "nifty_500_short_exit":     nifty_500_short_exit,
    "nifty_500_short_rollover": nifty_500_short_rollover,
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
