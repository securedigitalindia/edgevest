# Admin Strategies Dashboard

**Depends on**: none for v1 (revised 2026-09-09 — see below). Futures price is fetched live from Upstox per request (`fetch_candles_utc`), same as the CLI scripts already do — an accepted cost, not a blocker. `docs/prd/nifty-futures-price-capture.md` (local `nifty_fut_5m` capture, zero-Upstox-call reads) is **deferred**: it remains a valid future optimization if the live-per-request cost ever becomes a real problem (e.g. once this dashboard's ~1-minute poll is actually driving repeated live futures fetches for the still-open window), but is explicitly not required to ship v1. Where this PRD's "cheap on-demand recompute" language below still assumes local futures data, read it as "aspirational, contingent on that follow-on landing" — the per-window *cache* (Mechanics §2) still holds regardless, since it caches computed embed output, not raw price data; only the always-recomputed open window still costs one live Upstox call per request until the capture PRD lands.

## Problem

The PE+CE ratio diagonal strategy's backtest results (`docs/prd/pe-ratio-diagonal-strategy.md`) currently live only as a manually-built, manually-republished Claude Artifact: `nifty_pe_ratio_diagonal_merged_windows_artifact.py --start-date ... --output /tmp/x.html`, then a human runs the Artifact tool with `url=` set to the existing artifact URL to update it in place. There is no persistent, always-current, in-app view of this data — refreshing it requires someone in a Claude Code session to rerun the CLI and manually republish. There is also no general mechanism for the other already-backtested strategies sitting in `backend/analysis/` (`calendar_spread_strike_scoring.py`, `nifty_ce_ladder_avg_backtest.py`, `nifty_pe_ratio_diagonal_ema_entry_backtest.py`, etc.) to get the same treatment without a bespoke one-off artifact/script per strategy.

## Goal

A new admin-only "Strategies" section in the dashboard where a registered, already-backtested strategy can be selected, its start date (and params) picked/confirmed once, and its full current state viewed natively — in-dashboard parity with the merged-windows-artifact's per-window tabs, PE/CE/Combined stat tiles, futures/P&L charts (solid=realized, dashed=if-held-to-settlement past a red Exit marker), and two daily tables (pre/post exit) per window — recomputed on demand via an API call, not rebuilt/republished by hand. Starts with the PE+CE ratio diagonal strategy as the first (and initially only) registered provider, behind a general contract other strategies can register into later without a new one-off page each time.

"Done" = an admin can open `/profile/strategies`, pick "PE+CE Ratio Diagonal," confirm a start date, and see exactly what the merged-windows artifact shows today — rendered as real dashboard components, refreshed on a ~1-minute poll, each screen clearly labeled with the data's actual last-capture timestamp in IST.

## Non-goals

- **Not a trading signal.** Same posture as the strategy PRD: research/monitoring only. No `trade_suggestions.py` template, no `recommended_trades` row, no Telegram alert. Not risk-validated (n=3 windows as of 2026-09-09 — nowhere near enough for a conclusion, and the dashboard must not visually imply otherwise).
- **Not migrating every existing `backend/analysis/` script into the framework now.** Only the PE+CE ratio diagonal strategy is wired in as the first registrant. The framework's *contract* is designed generally (see Mechanics below), but `calendar_spread_strike_scoring.py`, `nifty_ce_ladder_avg_backtest.py`, `nifty_pe_ratio_diagonal_ema_entry_backtest.py`, and anything else in that directory stay standalone scripts, unregistered, until someone deliberately wires each one in. See Open questions for why this is left undecided rather than resolved here.
- **No scheduled/cron recompute.** Explicit user decision: an admin's API call (or the dashboard's own ~1-minute poll) is what triggers a recompute, never a background job. See Mechanics for the caching design that makes this affordable.
- **No client-facing visibility whatsoever.** Every route here is `require_role("super_admin", "admin")`, matching every other admin screen in `frontend/src/screens/profile/`.
- **No in-dashboard param editing for v1.** The dashboard shows/confirms `start_date` and the strategy's params (`up_move`, `leg_gap` for PE+CE), defaulted from the provider's `default_params` — but there's no UI to sweep alternate values interactively. Changing params still means a fresh CLI run of the underlying script, or re-POSTing a new config (see Open questions on whether reconfiguring should be one-shot or richer).
- **Not replacing the existing artifact-generation scripts or templates.** `nifty_pe_ratio_diagonal_windows_artifact.py`/`_merged_windows_artifact.py` and their `.html` templates stay exactly as they are, for standalone/offline/shareable use — the dashboard is a new, additional consumer of the same underlying `run_window()`-shaped compute logic, not a replacement for the CLI+artifact workflow.
- **No margin/max-loss/risk computation added here** — carried over from the strategy PRD's own non-goals; this dashboard surfaces exactly the P&L data the backtest scripts already produce, nothing more.

## Mechanics / behavior

### 1. Strategy-provider contract

A "strategy provider" is the thin adapter a strategy plugs into this framework with. Concretely, a Python object/module in a new registry (`backend/strategies/registry.py`) exposing:

| Field | Type | Notes |
|---|---|---|
| `id` | `str` | stable slug, e.g. `"pe_ce_ratio_diagonal"` |
| `label` | `str` | display name, e.g. "PE+CE Ratio Diagonal" |
| `default_params` | `dict` | e.g. `{"leg_gap": 400, "trigger": {"type": "up_move", "up_move": 100, "first_trigger_time": "09:30 IST (fixed)"}}` (revised 2026-09-09 — was flat `{up_move, leg_gap}`; `leg_gap` is the strategy's own shape, `trigger` is a separate, extensible sub-object for whatever rule decides when a new set gets added) — seeds the config-confirm form |
| `run(start_date, end_date, params) -> dict` | callable | **pure** — no `argparse`, no `sys.exit`, no `print` — returns the exact per-window embed shape described below |

`run()` is deliberately the *only* required entry point — a provider doesn't need to expose per-window internals separately; the framework's caching (below) works against `run()`'s already-windowed output.

#### The PE+CE ratio diagonal provider — extraction, not reimplementation

`nifty_pe_ratio_diagonal_merged_windows_artifact.py`'s `main()` today mixes `argparse`/`print`/`sys.exit`/template-substitution/file-writing together with the actual compute (resolve inputs → `find_window_starts()` → per-window `run_window(side="PE")` + `run_window(side="CE")` → `build_merged_embed()` → collect into `windows_out`). Per this repo's own precedent for exactly this kind of extraction (`docs/prd/manual-strategy-cli.md`: "extracting `main()`'s CLI-only logic ... into a cleanly callable function is in scope"), this PRD requires the same treatment here:

- Extract the compute loop (`nifty_pe_ratio_diagonal_merged_windows_artifact.py`'s lines building `windows_out`, roughly its `main()` from after `fut_series` is resolved through the `windows_out` loop) into a new pure function in the **same file**, e.g. `run_merged_windows_backtest(start_date: str, end_date: str | None, up_move: float, leg_gap: float, symbol: str = "NIFTY50") -> dict`, returning exactly the dict `main()` currently JSON-dumps for `__DATA_PLACEHOLDER__`: `{"windows": windows_out, "up_move": ..., "leg_gap": ..., "fut_trading_symbol": ..., "lot_size": ...}`.
- `main()` becomes a thin wrapper: parse args, call `run_merged_windows_backtest()`, do the existing print/template-substitution/file-write around the result. Its CLI behavior/output is otherwise unchanged.
- The provider registered in `backend/strategies/registry.py` is then a ~10-line wrapper: `id="pe_ce_ratio_diagonal"`, `default_params={"up_move": 100, "leg_gap": 400}`, `run = lambda start_date, end_date, params: run_merged_windows_backtest(start_date, end_date, params["up_move"], params["leg_gap"])`.

#### A real import wrinkle, called out explicitly

`backend/analysis/` is a **flat directory of standalone scripts**, not a Python package — confirmed no `__init__.py` exists there. Every script in it (including `nifty_pe_ratio_diagonal_merged_windows_artifact.py`) resolves its own sibling imports (`from nifty_pe_ratio_diagonal_windowed_backtest import find_window_starts, run_window, ...`) as **bare** module imports, which only works because Python automatically puts a script's own directory on `sys.path[0]` when it's run directly (`python analysis/foo.py`). A Flask process importing this module (`server.py` runs from `backend/`, not `backend/analysis/`) will **not** get that for free — `backend/analysis/` itself needs to be added to `sys.path` before importing `nifty_pe_ratio_diagonal_merged_windows_artifact`, or its own internal bare imports of sibling analysis modules will fail with `ModuleNotFoundError`. `backend/strategies/registry.py` (or wherever the provider is registered) must do the same `sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))` pattern every analysis script already does for `backend/` itself, once, at import time. This is a known wrinkle of this repo's existing flat-script convention, not a new problem introduced here — flagged so it isn't silently hit and worked around ad hoc later.

### 2. Caching: settle-once, recompute-only-the-open-window

The task's explicit concern — recomputing an entire strategy's history from a fixed start date on every request gets slower every week — is addressed by exploiting a fact already true of `run_window()`'s own output: **all but the newest window are `is_bounded=True` (settled)** — a window becomes bounded the moment the *next* window's start date is known, which only happens at the next expiry-triplet rollover. A settled window's `combined_points`/`sets`/realized P&L are fully determined by historical `option_chain_5m`/`nifty_fut_5m` rows that (barring the edge case below) will never change again.

**New table**: `strategy_backtest_windows` — one cached row per `(strategy_id, window_start)`, written once, read thereafter:

```sql
CREATE TABLE IF NOT EXISTS strategy_backtest_windows (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id   TEXT    NOT NULL,
    window_start  TEXT    NOT NULL,   -- window's entry_date, "YYYY-MM-DD"
    payload_json  TEXT    NOT NULL,   -- full per-window embed dict (build_merged_embed() shape), json-dumped
    computed_at   TEXT    NOT NULL,   -- ISO-8601 UTC
    UNIQUE (strategy_id, window_start)
)
```

Recompute logic for `run_strategy(strategy_id, start_date, end_date, params)`:

1. Resolve the current list of window boundaries via `find_window_starts()` (cheap — pure date arithmetic against `get_merged_cadence_dates()`, no option-chain/futures reads) for `[start_date, latest local data date]`.
2. For every window **except the last** (i.e. every bounded/settled window): check `strategy_backtest_windows` for `(strategy_id, window_start)`. If cached, use it as-is. If not (first time this window has ever been seen — e.g. a rollover just happened), compute it (provider-specific — for PE+CE, one `run_window(side="PE")` + `run_window(side="CE")` + `build_merged_embed()` call) and write it to the cache.
3. The **last window** (unbounded/still open) is **always recomputed live**, every call, never cached — it's still accumulating new ticks as today's data comes in.
4. Request cost is therefore O(1) window's worth of real compute (the open one) plus a handful of fast indexed SQLite lookups for the rest — **flat over time**, not growing as more windows accumulate, resolving the scaling concern directly.

**A real cache-invalidation gap, not swept under the rug**: if a *past* window's underlying local data had a genuine capture gap that only gets backfilled *after* that window has already been cached as "settled" (e.g. `option_chain_5m`'s own live-Upstox-backfill fallback finally fires for a strike that was missing when this window was first cached), the cached `payload_json` would now be stale relative to what a fresh recompute would produce, and nothing here detects or fixes that automatically. No auto-invalidation is built for this. The only escape hatch in v1 is a manual `DELETE FROM strategy_backtest_windows WHERE strategy_id=? AND window_start=?` (or an admin "force recompute" action — see Open questions) run by a human who has reason to suspect a specific window's cached numbers are wrong.

`strategy_id` is a real column (not implicit to a single table) specifically so this cache is shared infrastructure for every future registered strategy, not something reinvented per strategy.

### 3. Per-strategy confirmed config

The task's flow is "pick/confirm a start date, see current status" — implying the admin sets a start date (and params) *once* per strategy, and the dashboard remembers it rather than requiring it on every view. New table:

```sql
CREATE TABLE IF NOT EXISTS strategy_configs (
    strategy_id   TEXT PRIMARY KEY,
    start_date    TEXT NOT NULL,
    params_json   TEXT NOT NULL DEFAULT '{}',
    confirmed_by  TEXT,              -- admin user's email
    confirmed_at  TEXT NOT NULL      -- ISO-8601 UTC
)
```

`GET /api/strategies/<id>/run` (below) requires a confirmed config to exist first (400 if not) — matching the "confirm a start date" step being a real, deliberate admin action before any compute happens, not an implicit default. Re-confirming (`POST .../config` again) is allowed at any time and does **not** by itself clear `strategy_backtest_windows` — a changed `start_date`/param set naturally produces different window boundaries and just accumulates new cache rows under the new boundaries; old cached rows for the previous config are simply never read again (not cleaned up — same "no retention job" posture as everything else in this data family, acceptable at this table's expected size).

### 4. Data-freshness indicator

Both `nifty_fut_5m` (piece 1) and `option_chain_5m` only update on the poller's ~5-min capture cadence, regardless of how often the dashboard itself is polled or how often an admin hits refresh. Every `run()` response includes a `data_as_of` field — the later of `MAX(ts)` across `option_chain_5m` and `nifty_fut_5m` for rows within the requested range, converted to IST — and the frontend renders it as a persistent "Data as of HH:MM IST" banner, not a live/pulsing indicator, so the UI never implies second-level freshness it can't actually provide even though the dashboard's own polling interval (below) is faster than the underlying data changes.

### 5. Frontend polling cadence

The dashboard itself polls `GET /api/strategies/<id>/run` roughly every 60 seconds (TanStack Query `refetchInterval: 60_000`, matching this repo's existing `useQuery` conventions) — independent of, and faster than, the underlying ~5-min data cadence; the `data_as_of` banner is what keeps this honest rather than the poll interval itself. This is a deliberate choice to keep the "currently open window" view reasonably current for an admin actively watching it, while the caching design (above) means this polling doesn't scale request cost with history length.

## Architecture impact

### Backend

- **New package `backend/strategies/`** (mirrors `backend/payments/`'s factory-blueprint precedent — the only existing precedent for a modular package in this otherwise-flat backend, chosen for the same reason: `require_login`/`require_role`/`current_user` live in `server.py`, so a module-level `Blueprint` importing them at load time would be circular; `server.py` passes them in at registration instead, exactly like `create_payments_blueprint(require_login, require_role, current_user)` at `server.py:1471-1472`):
  - `registry.py` — the `sys.path.insert` for `backend/analysis/` (see wrinkle above), the `StrategyProvider` shape, and a `PROVIDERS: dict[str, StrategyProvider]` populated with the one PE+CE entry for now.
  - `service.py` — `run_strategy(strategy_id, start_date, end_date, params)` (the caching orchestration described in Mechanics), `get_config(strategy_id)` / `set_config(strategy_id, start_date, params, admin_email)`. No Flask/HTTP concerns, matching `payments/service.py`'s own separation.
  - `routes.py` — `create_strategies_blueprint(require_role, current_user)`, registered into `server.py` the same way `create_payments_blueprint(...)` is at `server.py:1471-1472`.
  - SQL stays in `db/queries.py` per the project-wide convention (`backend/CLAUDE.md`: "SQL stays in `db/queries.py`... this package never touches SQL itself") — `strategies/service.py` calls new `db/queries.py` functions, never issues SQL directly.
- **`backend/db/init_db.py`** — additive. Two new `CREATE TABLE IF NOT EXISTS` blocks (`strategy_backtest_windows`, `strategy_configs`).
- **`backend/db/queries.py`** — additive. New functions: `get_cached_strategy_window(strategy_id, window_start)`, `write_cached_strategy_window(strategy_id, window_start, payload: dict)`, `get_strategy_config(strategy_id)`, `upsert_strategy_config(strategy_id, start_date, params: dict, confirmed_by)`.
- **`backend/analysis/nifty_pe_ratio_diagonal_merged_windows_artifact.py`** — refactored (not rewritten): extract `run_merged_windows_backtest()` as described above; `main()` becomes a thin wrapper around it. No behavioral change to the existing CLI/artifact workflow.
- **`backend/server.py`** — one addition: `from strategies.routes import create_strategies_blueprint` + `app.register_blueprint(create_strategies_blueprint(require_role, current_user))`, alongside the existing payments registration.

### API routes (`docs/apis.md` format)

| Method | Path | Auth | Body / Params | Response |
|---|---|---|---|---|
| GET | `/api/strategies` | `require_role(super_admin, admin)` | — | `{ strategies: [{ id, label, default_params, configured: bool }] }` — one entry per registered provider; `configured` reflects whether `strategy_configs` has a row yet. |
| GET | `/api/strategies/<id>/config` | `require_role(super_admin, admin)` | — | `{ config: {start_date, params, confirmed_by, confirmed_at} }` or `{ config: null }` if unconfigured |
| POST | `/api/strategies/<id>/config` | `require_role(super_admin, admin)` | `{ start_date, params? }` — `params` merged over `default_params` | `{ ok }` or 400 (unknown `id`, invalid `start_date`) |
| GET | `/api/strategies/<id>/run` | `require_role(super_admin, admin)` | `?end_date=` optional (default: latest local data date) | `{ ok, windows: [...], up_move, leg_gap, fut_trading_symbol, lot_size, data_as_of }` — `windows[]` is exactly `build_merged_embed()`'s per-window shape (see below); 400 if no config exists yet (`"not configured — POST .../config first"`) |

Per-window shape inside `windows[]` (unchanged from `build_merged_embed()`'s existing output — the framework does not reshape it, so the frontend components map directly onto what the artifact template already consumes):

```
{
  entry_date, is_bounded, exit_ts,
  pe_ok, ce_ok,
  pe_realized_pnl_pts, pe_realized_pnl_rs, ce_realized_pnl_pts, ce_realized_pnl_rs,
  pe_ref_pnl_pts, pe_ref_pnl_rs, ce_ref_pnl_pts, ce_ref_pnl_rs,
  sets: [...],                 // per-triggered-set metadata, both sides, sorted by trigger_ts
  combined: [...],              // tick-level points: ts, day, fut, pe_pnl_pts, ce_pnl_pts, total_pnl_pts, ..._rs, post_exit
  daily_realized: [...],        // one row per day, pre-exit
  daily_reference: [...],       // one row per day, full range (only present for bounded windows)
}
```

### Frontend

- **New API module** `frontend/src/api/strategies.js` (one per domain, matching `billing.js`/`prices.js` convention): `listStrategies()`, `getStrategyConfig(id)`, `setStrategyConfig(id, payload)`, `runStrategy(id, params)`.
- **New hooks** `frontend/src/hooks/useStrategies.js`: `useStrategies()`, `useStrategyConfig(id)`, `useSetStrategyConfig(id)` (mutation, invalidates `['strategy-config', id]` and `['strategy-run', id]`), `useStrategyRun(id, { enabled })` (`refetchInterval: 60_000`, matching cadence above; `enabled: false` until a config is confirmed).
- **New screen** `frontend/src/screens/profile/Strategies.jsx`, registered exactly like every other admin screen:
  - `ProfileHub.jsx` — new `<MenuRow icon={ChartIcon} label="Strategies" onClick={() => navigate('/profile/strategies')} />` inside the existing `isAdmin` block (`ProfileHub.jsx:59-69`, alongside Brokers/Users/Plans/Subscriptions/Payments/Refer & Earn). Reuses the already-imported `ChartIcon` (also used by "Monthly Report") rather than introducing a new icon — see Open questions if a distinct icon is wanted.
  - `App.jsx` — new `<Route path="/profile/strategies" element={<Strategies />} />` inside the same admin-route block as `/profile/brokers`, `/profile/users`, etc. (`App.jsx:85-92`), self-guarding `if (!isAdmin) return <Navigate to="/profile" replace />` per the existing convention for every other admin-only `/profile/*` route.
  - `Strategies.jsx` — top-level: strategy picker (one entry today), and either a config-confirm form (date input + `default_params`-seeded fields, shown when `configured: false`) or the detail view (below) once configured, with a "Reconfigure" affordance to re-POST `.../config`.
  - `StrategyWindowTabs.jsx` (or inline within `Strategies.jsx`) — the per-window tab strip + "Data as of HH:MM IST" banner, mirroring the artifact's own tab UI. Selecting a tab renders:
    - **Stat tiles** — PE realized, CE realized as the two primary tiles; a visibly secondary/muted "Combined (PE+CE)" tile — reusing the artifact's own visual hierarchy decision (`docs/prd/pe-ratio-diagonal-strategy.md`: "PE's and CE's own realized figures are the two primary stat tiles... never the headline").
    - **Futures + P&L charts** — solid line for realized (pre-`exit_ts`), dashed/muted continuation for the post-exit "if held to settlement" reference past a red "Exit" marker, three series (PE/CE/Combined) per the merged artifact's own chart design.
    - **Two daily tables** — `daily_realized` and (for bounded windows) `daily_reference`, the latter visually faded, matching the artifact's own two-tables-per-window layout.
  - **Charting library**: this repo currently has **no charting dependency** in `frontend/package.json` (confirmed — no `recharts`/`chart.js`/`d3`/etc.) — every chart in this codebase to date has only existed inside a standalone Claude Artifact's own embedded JS, never inside the actual React app. Building native tick-level charts here is therefore a genuinely new frontend dependency, not a reuse of an existing pattern. Flagged as an open question (below) for which library, rather than silently picking one.

## Data / storage

Two new tables (`backend/db/init_db.py`), both additive, both using the existing `get_connection()`/WAL setup unchanged:

- `strategy_backtest_windows` — see Mechanics §2 for full schema/semantics. Grows by roughly one row per `(strategy, settled window)` — for the PE+CE provider, one new row roughly every 1-2 weeks (a window = one expiry-triplet rollover cycle). No retention job; this is a small, slow-growing cache.
- `strategy_configs` — see Mechanics §3. One row per registered strategy that's ever been configured — trivially small.

Both are read/written exclusively through `backend/strategies/service.py` → `backend/db/queries.py`, never directly from `routes.py` or the frontend. Nothing here touches `option_chain_5m`, `nifty_fut_5m`, `recommended_trades`, or any existing table — purely additive.

## Success criteria

- `GET /api/strategies` (admin session) returns the PE+CE ratio diagonal provider; the same call with a `client`-role session returns 403.
- `POST /api/strategies/pe_ce_ratio_diagonal/config` with `{start_date: "2026-08-25"}` followed by `GET .../run` returns a `windows[]` array matching (bit-for-bit on the numeric fields) what `nifty_pe_ratio_diagonal_merged_windows_artifact.py --start-date 2026-08-25` produces for the same local data snapshot — confirms the extraction (`run_merged_windows_backtest()`) is behavior-preserving, not just structurally similar.
- A second `GET .../run` call immediately after the first is measurably faster and, per added instrumentation/logging, computes only the newest (unbounded) window — every earlier window served from `strategy_backtest_windows`.
- After a real rollover (a new window's start date appears), the *previously*-newest window (now bounded) gets cached on its first post-rollover request, and never recomputed again on subsequent requests.
- The frontend renders one tab per window with PE/CE/Combined tiles, futures+P&L charts (solid/dashed split at the exit marker), and two daily tables per bounded window — visually matching the published merged-windows artifact for the same date range, side by side.
- The "Data as of HH:MM IST" banner reflects the actual `MAX(ts)` from local capture, not wall-clock "now" — verified by comparing it against `SELECT MAX(ts) FROM option_chain_5m` / `nifty_fut_5m` directly.

## Open questions

- **Which charting library.** No charting dependency exists in `frontend/package.json` today (confirmed). A lightweight, actively-maintained React charting library needs to be chosen and added — flagged for the user/implementer rather than assumed; this is the one piece of "in-dashboard parity" that can't be built with existing frontend infrastructure alone.
- **Whether to inventory and register other `backend/analysis/` strategies now, or leave that entirely to later.** This PRD deliberately only wires in PE+CE ratio diagonal and designs the contract generally — whether `calendar_spread_strike_scoring.py`, `nifty_ce_ladder_avg_backtest.py`, and the standalone EMA-entry variant (`nifty_pe_ratio_diagonal_ema_entry_backtest.py`, itself already flagged in its own PRD as "not yet integrated with the windowed/averaging backtest or the artifact tooling") are worth registering soon, or whether the contract should just sit unused by anything but PE+CE until a second strategy actually needs it, is left to the user's judgment.
- **Cache-invalidation for a backfill that changes an already-settled window's numbers** (Mechanics §2) — no automatic detection/invalidation is built; only a manual delete/force-recompute escape hatch is proposed. Worth deciding whether a proper "force recompute this window" admin action belongs in v1 or is acceptable as a follow-up.
- **Whether `backend/analysis/` should gain an `__init__.py`** to become a real importable package (cleaner than the `sys.path.insert` wrinkle described in Mechanics §1), versus keeping the existing flat-script convention and accepting that wrinkle here too. Either is workable; this PRD assumes the latter (minimal diff, consistent with existing scripts) but flags the former as a reasonable alternative.
- **Whether re-confirming a strategy's config (a new `start_date`/params) should prune old, now-orphaned `strategy_backtest_windows` rows** for the previous config, or leave them (current design: leave them, matching this data family's general "no retention job" posture) — revisit if the table's growth ever becomes a real concern, which at the observed ~1-2 cached rows per strategy per rollover cycle seems unlikely soon.
- **Whether v1 needs any in-dashboard param-sweep UI** (trying alternate `up_move`/`leg_gap` values interactively) or whether "confirm once, view read-only thereafter, reconfigure via a fresh POST" is sufficient for now — this PRD assumes the latter per the task's framing ("pick/confirm a start date, see current status"), but flagging since it's a real product-scope call, not a technical constraint.
