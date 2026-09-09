"""
backend/strategies/service.py — orchestration for the strategy admin
dashboard (docs/prd/admin-strategies-dashboard.md). No Flask/HTTP concerns;
routes.py calls into this, this calls into db/queries.py for all SQL.
"""
from datetime import datetime, timezone

from db import queries
from db.init_db import get_connection
from live.expiry import expiry_cache

from . import registry  # import first — triggers registry's sys.path.insert for backend/analysis/
from nifty_fut_ref import IST  # noqa: E402 — only importable after the line above

DEFAULT_SYMBOL = "NIFTY50"


def list_strategies() -> list[dict]:
    out = []
    for p in registry.list_providers():
        cfg = queries.get_strategy_config(p.id)
        out.append({
            "id": p.id, "label": p.label, "default_params": p.default_params,
            "configured": cfg is not None,
        })
    return out


def get_config(strategy_id: str) -> dict | None:
    if registry.get_provider(strategy_id) is None:
        raise ValueError(f"unknown strategy_id: {strategy_id}")
    return queries.get_strategy_config(strategy_id)


def _merge_params(defaults: dict, override: dict) -> dict:
    """One level deeper than a plain shallow merge — a nested dict value
    (e.g. "trigger") is merged key-by-key rather than replaced wholesale, so
    a caller submitting only {"trigger": {"up_move": 150}} doesn't silently
    drop "type"/"first_trigger_time" from the provider's defaults."""
    out = dict(defaults)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def set_config(strategy_id: str, start_date: str, params: dict | None, confirmed_by: str) -> None:
    provider = registry.get_provider(strategy_id)
    if provider is None:
        raise ValueError(f"unknown strategy_id: {strategy_id}")
    merged_params = _merge_params(provider.default_params, params or {})
    queries.upsert_strategy_config(strategy_id, start_date, merged_params, confirmed_by)


def _data_as_of() -> str | None:
    """Later of MAX(ts) across option_chain_5m (the local data this actually reads),
    converted to IST. Futures price itself is fetched live per request, not persisted
    locally (docs/prd/nifty-futures-price-capture.md, deferred) — so this banner
    reflects option-chain freshness, the thing that actually only updates on the
    poller's ~5-min cadence."""
    max_ts = queries.get_option_chain_max_ts()
    if not max_ts:
        return None
    dt_utc = datetime.strptime(max_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def _run_pe_ce_ratio_diagonal_cached(strategy_id: str, start_date: str, end_date: str | None,
                                      params: dict) -> dict | None:
    """
    Settle-once, recompute-only-the-open-window (PRD Mechanics §2). Every
    window except the newest is looked up in strategy_backtest_windows
    first; a cache miss (a window seen for the first time, e.g. right after
    a rollover) is computed and written once. The newest/still-open window
    is always recomputed live, never cached. The one Upstox call this still
    makes per request (the futures price series, prepare_run_inputs) is
    unavoidable per the 2026-09-09 decision to defer local futures capture
    — it happens once per request regardless of window count, not once per
    window, so it doesn't scale with history length the way per-window
    compute would have.
    """
    trigger = params.get("trigger") or {}
    up_move = trigger.get("up_move", 100)
    leg_gap = params.get("leg_gap", 400)
    strike_multiple = params.get("strike_multiple", 100)
    initial_gap = params.get("initial_gap", 0)
    side = params.get("side", "BOTH")
    symbol = params.get("symbol", DEFAULT_SYMBOL)

    # The cache key MUST fold in every param that changes what a window
    # actually computes to — not just strategy_id+window_start. Without
    # this, reconfiguring (leg_gap/strike_multiple/initial_gap/up_move/
    # side) would silently keep serving settled windows computed under the
    # OLD params forever, since the cache table has no other way to know
    # they're stale. This doesn't touch the DB schema — it's folded into
    # the same TEXT strategy_id column as a composite key, so a reconfigure
    # just starts a new cache lineage; old rows under the previous
    # fingerprint are simply never read again (same "no retention job"
    # posture as everything else in this data family).
    cache_key = f"{strategy_id}#lg{leg_gap}_sm{strike_multiple}_ig{initial_gap}_um{up_move}_sd{side}"

    expiry_cache.refresh([symbol])
    conn = get_connection()
    try:
        inputs = registry.prepare_run_inputs(conn, start_date, end_date, symbol, "fut")
        if inputs is None:
            return None
        window_starts = inputs["window_starts"]

        windows_out = []
        for i, ws in enumerate(window_starts):
            is_last = (i + 1 == len(window_starts))
            window_end_ts = None if is_last else registry.ist_ts_for(window_starts[i + 1], registry.ENTRY_TIME)

            if not is_last:
                cached = queries.get_cached_strategy_window(cache_key, ws)
                if cached is not None:
                    windows_out.append(cached)
                    continue

            embed = registry.compute_window_embed(conn, ws, window_end_ts, inputs["merged"], up_move, leg_gap,
                                                    inputs["fut_series"], symbol, inputs["lot_size"],
                                                    strike_multiple, initial_gap, side)
            if embed is None:
                continue
            windows_out.append(embed)
            if not is_last:  # settled, first time seen — cache so it's never recomputed again
                queries.write_cached_strategy_window(cache_key, ws, embed)

        if not windows_out:
            return None

        return {
            "windows": windows_out, "up_move": up_move, "leg_gap": leg_gap, "strike_multiple": strike_multiple,
            "initial_gap": initial_gap, "side": side,
            "fut_trading_symbol": inputs["price_label"], "lot_size": inputs["lot_size"],
            "start_date": start_date, "end_date": inputs["end_date"], "data_as_of": _data_as_of(),
        }
    finally:
        conn.close()


def run_strategy(strategy_id: str, start_date: str, end_date: str | None, params: dict) -> dict:
    """
    Callers (routes.py) are responsible for confirming a config exists
    first (GET .../config / the 400-if-missing check the PRD's API table
    specifies) — this function just runs whatever start_date/params it's
    given. Raises LookupError if the run produces no usable result (no
    local data yet for this range, or every window failed) — routes.py
    maps that to whatever status it prefers (kept separate from the
    "not configured" 400, which is a routes-level check against
    get_config(), not this function's concern).
    """
    provider = registry.get_provider(strategy_id)
    if provider is None:
        raise ValueError(f"unknown strategy_id: {strategy_id}")

    if strategy_id == "pe_ce_ratio_diagonal":
        result = _run_pe_ce_ratio_diagonal_cached(strategy_id, start_date, end_date, params)
    else:
        # No bespoke per-window cache wired up for this provider yet — full
        # recompute every call. Only pe_ce_ratio_diagonal is registered
        # today; a future provider that needs the settle-once cache should
        # get the same treatment as the block above.
        result = provider.run(start_date, end_date, params)

    if result is None:
        raise LookupError(f"{strategy_id}: no usable result for start_date={start_date} (no local data yet?)")
    return result
