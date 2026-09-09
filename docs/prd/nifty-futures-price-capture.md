# NIFTY Futures Price Capture

**Status (2026-09-09): deferred, not required for `docs/prd/admin-strategies-dashboard.md` v1.** The user explicitly chose "one live Upstox call per request" for the admin dashboard's futures price (over building this local-capture pipeline first) — spot index candles were tried as a zero-Upstox alternative and rejected: comparing strike selection against the true futures price on the same trigger timestamps showed spot systematically mis-selects moneyness (CE strikes landing ITM instead of the intended OTM, PE strikes landing more deeply OTM than intended — see `docs/prd/pe-ratio-diagonal-strategy.md`'s payoff section for the concrete numbers), so futures pricing is staying, just fetched live rather than cached locally. This PRD remains a valid future optimization — worth revisiting if the dashboard's ~1-minute poll driving a live futures fetch per request (for the always-open, never-cached window) becomes an actual cost/rate-limit/latency problem — but nothing below should be built until that need is confirmed.

## Problem

`backend/analysis/nifty_fut_ref.py` — the shared price-reference module behind every PE/CE ratio diagonal backtest script (`docs/prd/pe-ratio-diagonal-strategy.md`, `docs/prd/pe-ratio-diagonal-simulator.md`) — is Upstox-direct for the NIFTY front-month future's price series: `fetch_candles_utc()`/`fetch_intraday_candles_utc()` hit Upstox's History API fresh on every single script run, for the entire requested date range, every time. This is the one remaining live-Upstox dependency in that whole tool chain — everything else (option premiums) already reads `option_chain_5m` locally, falling back to a live Upstox pull only for rare capture gaps (`nifty_pe_ratio_diagonal_backtest.py`'s `chain_series()`).

This matters concretely for `docs/prd/admin-strategies-dashboard.md` (piece 2 of this same effort): that PRD's whole "on-demand recompute, not a cron job" design depends on a backtest rerun costing "a handful of local SQLite reads," not a live external API round-trip on every dashboard request. Today, every `nifty_pe_ratio_diagonal_windowed_backtest.py`/`_merged_windows_artifact.py` run still makes one Upstox History API call for the futures series regardless of how many times the exact same date range has already been requested.

Confirmed by grep: `config.py`'s `SYMBOLS` (line ~14), `UPSTOX_INSTRUMENT_KEYS` (line ~272), and `SPOT_IKEYS` contain `NIFTY50`/`BANKNIFTY`/`RELIANCE` (the index/equity) but no entry for the NIFTY futures contract — the front-month future has never been part of this codebase's symbol-driven capture machinery. `nifty_fut_ref.py`'s `resolve_front_month_future()` exists specifically because nothing else in the repo resolves it.

## Goal

A new local, append-only 5-minute snapshot table for the NIFTY front-month future's LTP, captured on the poller's existing cadence — modeled directly on `option_chain_5m`'s shape and idempotency pattern (`backend/live/option_chain_capture.py`, `docs/prd/option-chain-capture.md`) — plus a local-DB-first read path in `nifty_fut_ref.py` with live-Upstox fallback-and-persist for gaps, mirroring `nifty_pe_ratio_diagonal_backtest.py`'s `chain_series()` exactly. "Done" = every PE/CE ratio diagonal script that currently calls `fetch_candles_utc()` for the futures series can instead read local data first, with Upstox only ever touched for a genuine gap (and never touched again for that same gap once backfilled).

## Non-goals

- **No other underlyings.** NIFTY only — matches every other tool in this analysis suite (BANKNIFTY futures, etc. are out of scope).
- **No intraday tick-level capture.** 5-minute cadence, matching `option_chain_5m` and matching what every consumer of this data already reads at (`fetch_candles_utc`'s own key format is 5-min-boundary; nothing in this project reads futures price at finer resolution than that).
- **No retention/pruning job.** Same as `option_chain_5m` — this is an analysis dataset, not a candle-building buffer like `ticks`; kept indefinitely.
- **No change to `resolve_front_month_future()`'s own live resolution.** It stays Upstox-direct (`search_instrument`) — cheap, metadata-only (instrument_key/expiry/lot_size/trading_symbol), called once per script run today, not the thing driving repeated cost. Only the *candle-history* pull is being localized. (An optional follow-on — resolving front-month via the already-loaded `live/fo_instruments.py` index instead of a fresh `search_instrument` call — is noted as an open question, not required here.)
- **No retroactive backfill of a contract's pre-front-month history at capture time.** Capture only ever writes rows for whichever contract *is* front-month *right now*, going forward — same forward-only limitation `option_chain_5m` already has, and same reason: `resolve_front_month_future()` can only discover currently-listed contracts, not ones that have already expired/rolled off Upstox's own live search. (Read-time backfill via Upstox's History API — which *can* serve a still-listed contract's older history — is a separate mechanism, see Mechanics below.)
- **No margin/brokerage data** — LTP only, same posture as everything else this project captures.

## Mechanics / behavior

### Capture: piggyback on the existing 5-min option-chain capture boundary, not the 5s tick loop

`live/poller.py`'s main loop already has a dedicated 5-minute timer for exactly this class of low-frequency analysis capture: `option_chain_watcher = CandleWatcher(5)` (poller.py:235-236), checked once per loop iteration (poller.py:294) and used to fire `option_chain_capture.run_capture()` inside its own `try/except` (poller.py:294-298), fully independent of the 5s `_all_ikeys`/`get_ltp()` trigger-instrument poll below it.

The new futures capture reuses the **same already-consumed `option_chain_watcher.should_build()` check**, calling a new `nifty_fut_capture.run_capture()` right alongside `option_chain_capture.run_capture()` inside that same `if` block — **not** a third `CandleWatcher` instance. `CandleWatcher.should_build()` is stateful (each call consumes that boundary's single `True` — this is explicitly why `option_chain_watcher` is its own instance rather than sharing the pre-existing 5m candle watcher, per `option_chain_capture.py`'s own header comment); since both captures should fire on the *exact same* 5-min boundary anyway, there is no reason to spend a second watcher instance on it — just call both functions, each independently `try/except`-wrapped, after the one `should_build()` check returns true.

Why not reuse `candles_5m` (the existing generic OHLCV table, already live-built for `config.SYMBOLS` via the 5s tick loop + `candle_builder.build_all()`) instead of a bespoke table: it's the same *shape* of data, but the wrong *identity* model. `candles_5m`/`candles_1h`/etc. and everything that feeds them (`config.SYMBOLS`, `UPSTOX_INSTRUMENT_KEYS`, `bootstrap/upstox_loader.py`, `sync/daily_sync.py`) assume **one instrument_key per symbol, fixed forever**, resolved once from a static config dict — correct for NIFTY50/BANKNIFTY/RELIANCE (none of which ever change identity) but wrong for a futures contract, which rolls to a new instrument_key every month. Critically, `candles_5m`'s schema has no per-row column recording *which contract* a given candle came from — so writing the front-month future's price into it under a fixed symbol name would silently blend contracts across every rollover with no way to audit which one priced any given candle. `option_chain_5m` already solved this identical problem for options by carrying `expiry_date` per row (rather than assuming one fixed contract per symbol); the new futures table follows that same precedent instead. (One narrower point that *does* hold, just isn't the deciding factor: this data is only ever consumed at 5-min-candle-boundary granularity — `fetch_candles_utc`'s own docstring says "5-min candles... value = candle close" — so there's no need for 5s/tick resolution regardless of which table it lands in.)

### New module: `backend/live/nifty_fut_capture.py`

Mirrors `option_chain_capture.py`'s structure and conventions (same file header-comment style, same idempotent capture pattern):

- `_boundary_ts()` — floor current UTC time to the nearest 5-min mark. Duplicated as a small (~5-line) private helper rather than imported from `option_chain_capture.py` — that function is underscore-prefixed/private-by-convention there, and this repo's flat-script style doesn't cross-import private helpers between sibling capture modules; both independently derive the same trivial floor logic from wall-clock time, so duplication carries no real correctness risk.
- `capture() -> dict | None` — one snapshot: `resolve_front_month_future("NIFTY")` (from `nifty_fut_ref.py`, unchanged) to get `{instrument_key, expiry, lot_size, trading_symbol}`, then `get_live_fut_ltp(instrument_key)` (also unchanged) for the price. Returns `None` (logs, doesn't raise) on any Upstox error, matching `option_chain_capture.py`'s per-fetch error isolation.
- `run_capture() -> int` — calls `capture()`, writes one row via a new `db.queries.write_nifty_fut_snapshot()`, returns rows written (0 or 1). Called from `poller.py`'s main loop, wrapped in its own `try/except` so a failure here never affects `option_chain_capture.run_capture()` or the rest of the loop.

This captures a **single LTP snapshot per 5-min boundary**, not a full OHLC candle — sufficient because every existing consumer of futures price history in this codebase already only reads the *close* value of Upstox's 5-min candles (`fetch_candles_utc`'s docstring, verbatim: "value = candle close"); open/high/low are never read anywhere in this tool chain. This exactly mirrors `option_chain_capture.py`'s own choice to store `ltp` (a snapshot), not a candle.

### Rollover handling

No special-case rollover code is needed at capture time: `resolve_front_month_future()` is already called fresh on *every* 5-min capture (a live "nearest unexpired FUT contract" search, never cached/hardcoded) — the moment the current front-month contract's expiry passes and a new contract becomes nearest, the very next capture naturally writes rows tagged with the new `instrument_key`/`trading_symbol`/`expiry_date`/`lot_size`. This is the same "resolve dynamically, don't hardcode" principle `live/expiry.py`'s `ExpiryCache` and every PE/CE diagonal script's `resolve_expiry_triplet()` already use for options expiries — applied here to the futures contract identity instead.

One real consequence worth being explicit about: reads of this table (below) are always scoped to **one specific `instrument_key`** at a time, matching exactly how `fetch_candles_utc(instrument_key, from_date, to_date)` is called today — every existing caller resolves `resolve_front_month_future()` *once* at the start of its run and reads that one contract's own historical candle series across the whole requested date range (this works today because a monthly NIFTY FUT contract is typically listed, and has its own price history, well before it becomes front-month). This PRD's local table preserves that same per-contract read shape — it is **not** a rollover-spliced continuous series across multiple contracts. If a future caller ever wants a roll-adjusted continuous series, that is new logic, out of scope here.

### Local-DB-first reads, live-Upstox fallback + persist for gaps

New function in `nifty_fut_ref.py`, e.g. `fetch_fut_series_local_first(instrument_key: str, from_date: str, to_date: str, trading_symbol: str, expiry_date: str, lot_size: int) -> dict`:

1. Read local coverage for `instrument_key` in `[from_date, to_date]` via a new `db.queries.get_nifty_fut_series(instrument_key, from_ts, to_ts) -> dict[str, float]` — returns the **same `{ts: value}` shape** `fetch_candles_utc`/`fetch_intraday_candles_utc` already return, so callers merge/consume it identically.
2. Determine missing sub-ranges against the trading-day calendar (`live/holidays.is_trading_day`), same gap-detection spirit as `chain_series()`'s `backfill_from_ts` check.
3. For any gap, fall back to `fetch_candles_utc()` (historical) and/or `fetch_intraday_candles_utc()` (today, if `to_date` includes today) — unchanged, already-existing functions.
4. **Persist the backfilled rows** into the new table via `write_nifty_fut_snapshot()`, tagged with the resolved `instrument_key`/`trading_symbol`/`expiry_date`/`lot_size` — mirroring `nifty_pe_ratio_diagonal_backtest.py`'s `_persist_backfill()` pattern exactly (same idempotent `INSERT OR IGNORE` writer, same "never fetch this gap from Upstox again" effect). Unlike `option_chain_5m`'s backfill (which only works pre-settlement, since Upstox's *option-chain resolution* stops working post-settlement), a futures contract's *History API* series has no such observed cliff in this codebase — the risk here is `resolve_front_month_future()` itself no longer surfacing an *expired* contract (see Non-goals), not the History API refusing an already-known `instrument_key`. Not verified against Upstox for a NIFTY FUT contract months post-expiry — flagged as an open question, not assumed.
5. Merge local + backfilled into one dict, return.

This is the mechanism that actually removes Upstox from steady-state reads: the forward-capture piece (above) covers new/current data with zero Upstox calls at read time; this backfill-and-persist-on-first-read piece covers older/gap history **the first time it's ever requested** — which matters a great deal for `docs/prd/admin-strategies-dashboard.md`'s design, since that dashboard's whole point is requesting the *same* strategy/date-range repeatedly. After the first backfill, every subsequent request for that range is a pure local read.

### Callers to update

Three call sites currently call `fetch_candles_utc(fut["instrument_key"], pad_from, pad_to)` (or equivalent) directly for the futures series and should switch to `fetch_fut_series_local_first(...)` instead — a one-line change per script, no other logic affected:

- `backend/analysis/nifty_pe_ratio_diagonal_windowed_backtest.py:253`
- `backend/analysis/nifty_pe_ratio_diagonal_averaging_backtest.py:180`
- `backend/analysis/nifty_pe_ratio_diagonal_merged_windows_artifact.py:154`

`nifty_pe_ratio_diagonal_simulator.py`/`_simulator_v2.py` (the live/entry-anchored tools, not the windowed backtests) are out of scope here — they track from one fixed entry-date through "now," a different, narrower access pattern than the windowed backtests' full-range re-fetch; whether they should also switch is a fair follow-up, not required for this PRD's stated goal.

## Architecture impact

- **New file**: `backend/live/nifty_fut_capture.py` — `_boundary_ts()`, `capture()`, `run_capture()`. Same construction/singleton pattern as `option_chain_capture.py`'s `_get_api()` for its Upstox client usage (via `nifty_fut_ref.py`'s existing `_get_api()` cache, reused as-is — no new Upstox client wiring).
- **`backend/live/poller.py`** — additive only. Import `nifty_fut_capture`; inside the existing `if option_chain_watcher.should_build():` block (poller.py:294-298), add a second `try/except` calling `nifty_fut_capture.run_capture()` alongside the existing `option_chain_capture.run_capture()` call. No new `CandleWatcher`, no change to `_all_ikeys`/the 5s loop/`tick_store`.
- **`backend/db/init_db.py`** — additive only. New `CREATE TABLE IF NOT EXISTS nifty_fut_5m` block plus two new indexes (see Data / storage).
- **`backend/db/queries.py`** — additive only. New `write_nifty_fut_snapshot(rows: list[dict]) -> int` (batch `INSERT OR IGNORE`, same shape as `write_option_chain_snapshot`) and `get_nifty_fut_series(instrument_key: str, from_ts: str, to_ts: str) -> dict[str, float]`.
- **`backend/analysis/nifty_fut_ref.py`** — additive. New `fetch_fut_series_local_first(...)` function; no change to `resolve_front_month_future`, `get_live_fut_ltp`, `fetch_candles_utc`, `fetch_intraday_candles_utc`, `resolve_option_instrument_keys`, `resolve_reference_trading_day`, or `nearest_price` — all reused as-is (the fallback calls straight into the existing `fetch_candles_utc`/`fetch_intraday_candles_utc`).
- **Three analysis scripts** — one-line call-site swap each (see "Callers to update" above). No change to their own compute/business logic.
- Does not touch `ticks`, `price_cache`, `candles_*`, `option_chain_5m`, `recommended_trades`, `TRIGGERS`, or any part of the trigger/alert pipeline.

## Data / storage

**New table**: `nifty_fut_5m` (`backend/db/init_db.py`)

```sql
CREATE TABLE IF NOT EXISTS nifty_fut_5m (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,   -- 5-min floored UTC boundary, "YYYY-MM-DDTHH:MM:SSZ"
    symbol          TEXT    NOT NULL,   -- "NIFTY" — the FUT-search resolution key used by
                                         -- resolve_front_month_future("NIFTY"); deliberately
                                         -- distinct from "NIFTY50" (the index/option-chain
                                         -- symbol used elsewhere) — see Open questions.
    instrument_key  TEXT    NOT NULL,   -- Upstox key of the contract that was front-month
                                         -- at capture time, e.g. "NSE_FO|68407"
    trading_symbol  TEXT    NOT NULL,   -- e.g. "NIFTY26SEPFUT" — changes at rollover
    expiry_date     TEXT    NOT NULL,   -- this contract's own expiry, "YYYY-MM-DD"
    lot_size        INTEGER,
    ltp             REAL    NOT NULL,
    UNIQUE (ts, symbol, instrument_key)
)
```

- Indexes: `idx_nifty_fut_5m_sym_ts` on `(symbol, ts DESC)`; `idx_nifty_fut_5m_instrument_ts` on `(instrument_key, ts DESC)` — the latter is what `get_nifty_fut_series()` actually filters on, matching `fetch_candles_utc`'s own per-instrument-key access pattern.
- Written from: `nifty_fut_capture.run_capture()` → `write_nifty_fut_snapshot()`, every 5 minutes from the poller's main loop (forward capture); and `nifty_fut_ref.fetch_fut_series_local_first()` → `write_nifty_fut_snapshot()` for backfilled gap rows (read-time persist).
- Read by: `get_nifty_fut_series()`, called from `fetch_fut_series_local_first()`. No other read path.
- `INSERT OR IGNORE` only, never `OR REPLACE` — same idempotency posture as `option_chain_5m` (a poller restart re-capturing the same 5-min slot, or a backfill re-run over an already-covered range, is a no-op).
- No retention/cleanup job — unbounded, like `option_chain_5m`.
- Uses `get_connection()` (`db/init_db.py:42`) unchanged — already WAL-mode, already concurrency-safe for the poller's writes alongside read-heavy access from analysis scripts / the future admin dashboard (`docs/prd/admin-strategies-dashboard.md`); no change needed there.

## Success criteria

- With `poller.py live` running normally, `nifty_fut_5m` gains a new row roughly every 5 minutes during market hours, tagged with the current front-month contract's `instrument_key`/`trading_symbol`/`expiry_date`.
- Across an observed rollover (current front-month contract's expiry passing), new rows pick up the new contract's `instrument_key`/`trading_symbol`/`expiry_date` automatically, with no manual intervention or deploy.
- `fetch_fut_series_local_first()` called for a date range fully covered locally makes **zero** Upstox calls (verified by mocking/stubbing `fetch_candles_utc`/`fetch_intraday_candles_utc` and confirming they're never invoked) and returns identical values to what `fetch_candles_utc()` would have returned directly for that instrument_key.
- Called for a range with a genuine gap (e.g. before this table started capturing), it returns a complete series (local + backfilled) and persists the backfilled portion — a second call for the *same* range then makes zero Upstox calls.
- The three updated analysis scripts (`nifty_pe_ratio_diagonal_windowed_backtest.py`, `_averaging_backtest.py`, `_merged_windows_artifact.py`) produce identical P&L output before/after the swap, run against the same local data — confirms the swap is a pure data-sourcing change, not a logic change.

## Open questions

- **`symbol = "NIFTY"` vs `"NIFTY50"`** — deliberately chosen to match `resolve_front_month_future`'s own `underlying` parameter (and how Upstox's `search_instrument(f"{underlying} FUT")` names the contract), distinct from `"NIFTY50"` (the index, used by `option_chain_5m`/`candles_*`/`config.SYMBOLS`). Worth the user confirming this naming split is desired rather than assumed, since it's a new, third naming convention alongside `config.SYMBOLS`'s `"NIFTY50"` entry and Upstox's own `NSE_INDEX|Nifty 50` instrument-key strings.
- **Whether `resolve_front_month_future()` should stop hitting Upstox's `search_instrument` every 5 minutes** in favor of the already-loaded `live/fo_instruments.py` index (refreshed at poller startup and EOD, `nifty_fut_ikey()`/`nifty_lot_size()`) — not required for this PRD's stated goal (that call is cheap, metadata-only, and every analysis script already makes it once per run without issue), but flagged as a natural follow-on optimization since the infrastructure to avoid it already exists in the repo.
- **Whether `nifty_fut_capture.py` should be its own file** versus folded directly into `option_chain_capture.py`'s `run_capture()` (both fire on the identical boundary today). Recommended as a separate file/table for the same reason `tick_store.py`/`candle_builder.py`/`option_chain_capture.py` are already separate despite sharing poller infrastructure — one capture mechanism, one table, one file — but this is a reasonable implementer's call either way.
- **Whether an expired NIFTY FUT contract's History API series actually stays fetchable** past its own settlement (unlike the option-chain *resolution* endpoint, which is confirmed broken post-settlement) — asserted as likely true above based on `fetch_candles_utc`'s generic, no-settlement-caveat docstring, but not independently verified against a real expired FUT contract. Worth confirming empirically before leaning on it for backfill correctness near a rollover boundary.
