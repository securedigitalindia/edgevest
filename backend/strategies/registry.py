"""
Strategy-provider registry — docs/prd/admin-strategies-dashboard.md.

A "strategy provider" is the thin adapter a backtested strategy plugs into
this framework with: id, label, default_params, and a pure run(start_date,
end_date, params) -> dict callable. service.py's caching orchestration
(run_strategy()) works against run()'s already-windowed output — a provider
doesn't need to expose any per-window internals separately.

Import wrinkle (documented in the PRD, repeated here so it isn't silently
hit and worked around ad hoc later): backend/analysis/ is a flat directory
of standalone scripts, not a package — every script there resolves its own
sibling imports as bare module imports, which only works when Python
auto-adds a script's own directory to sys.path[0] on direct execution
(`python analysis/foo.py`). A Flask process importing this module doesn't
get that for free, so backend/analysis/ is added to sys.path once, below,
before importing anything from it.
"""
import os
import sys
from dataclasses import dataclass, field
from typing import Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))

from nifty_pe_ratio_diagonal_merged_windows_artifact import (  # noqa: E402
    run_merged_windows_backtest, prepare_run_inputs, compute_window_embed,
)
from nifty_pe_ratio_diagonal_windowed_backtest import ist_ts_for, ENTRY_TIME  # noqa: E402


@dataclass
class StrategyProvider:
    id: str
    label: str
    default_params: dict
    run: Callable[[str, str | None, dict], dict | None]


def _run_pe_ce_ratio_diagonal(start_date: str, end_date: str | None, params: dict) -> dict | None:
    trigger = params.get("trigger") or {}
    return run_merged_windows_backtest(
        start_date, end_date,
        up_move=trigger.get("up_move", 100),
        leg_gap=params.get("leg_gap", 400),
        symbol=params.get("symbol", "NIFTY50"),
        price_source="fut",  # the only mode endorsed for real use — see the strategy PRD's payoff section
        strike_multiple=params.get("strike_multiple", 100),
        initial_gap=params.get("initial_gap", 0),
        side=params.get("side", "BOTH"),
    )


PROVIDERS: dict[str, StrategyProvider] = {
    "pe_ce_ratio_diagonal": StrategyProvider(
        id="pe_ce_ratio_diagonal",
        label="PE+CE Ratio Diagonal",
        # Split 2026-09-09 at the user's request: "leg_gap" is the STRATEGY's
        # own shape (the K/K2 strike spread — same for every entry, doesn't
        # change per trigger), kept separate from "trigger" (the rule that
        # decides WHEN a new 4-leg set gets added — today just one type,
        # "up_move": fire a fresh set every N fut points from the last
        # trigger). Nested under a "type" discriminator so a second trigger
        # rule (e.g. an EMA-cross entry, see
        # nifty_pe_ratio_diagonal_ema_entry_backtest.py) can be added later
        # without another reshape. NOTE: the first trigger's own time
        # (09:30 IST) is NOT a param here — it's part of the strategy's
        # locked live-execution rule (docs/prd/pe-ratio-diagonal-strategy.md:
        # "at 09:30 IST on entry day, snap the front-month future..."),
        # not a trigger-config knob; making it editable would change the
        # strategy's definition, not just when/how it re-enters, so it's
        # surfaced to the frontend as a fixed fact, not a form field.
        default_params={
            "leg_gap": 400,
            "strike_multiple": 100,  # K-strike rounding step (floor for PE, ceil for CE) — NIFTY's real strike spacing
            "initial_gap": 0,  # shifts K before rounding; +ve = further OTM, -ve = toward/into ITM (sign auto-flips PE/CE)
            "side": "BOTH",  # "PE" | "CE" | "BOTH" — a side not selected is never computed, not just hidden client-side
            "trigger": {"type": "up_move", "up_move": 100, "first_trigger_time": "09:30 IST (fixed)"},
        },
        run=_run_pe_ce_ratio_diagonal,
    ),
}


def get_provider(strategy_id: str) -> StrategyProvider | None:
    return PROVIDERS.get(strategy_id)


def list_providers() -> list[StrategyProvider]:
    return list(PROVIDERS.values())
