# 5-Minute Option-Chain Snapshot Capture

## Problem

We want to build a NIFTY calendar-spread strategy: for a given OTM strike, compare the option premium of a near expiry vs. a farther expiry (e.g. "next" weekly/monthly vs. "next-to-next") and find strikes where that premium diff stays flat/stable as spot moves and as the near leg decays toward its own expiry. A flat diff means the near leg decays toward zero while the far leg holds more value, giving the calendar spread a bounded, predictable risk profile regardless of spot direction — concretely: with NIFTY at 24230, strike 24600 CE showed a next-vs-next-to-next premium diff of 40 points; three days later, with NIFTY down to 23800, the diff was still ~40.

Today there is no historical option-chain data to test this hypothesis against. Nothing in the codebase captures option premiums, OI, or IV over time at intraday resolution — `ticks` only stores spot LTP, and the option-chain endpoint is only ever called live/on-demand elsewhere (`live/expiry.py`, `live/trade_suggestions.py`). Without a time series of option premiums per strike/expiry, the diff-stability question can't be answered at all.

## Goal

Continuously and unattended, capture a full NIFTY option-chain snapshot (both weekly and monthly expiry triads, all strikes, both CE and PE) every 5 minutes during market hours, durably enough that a strike's premium history can be reconstructed and plotted intraday and across days — without any manual intervention or separate process to babysit. "Done" means: the poller runs normally and `option_chain_5m` fills up automatically every 5 minutes with no impact on existing trigger/alert behavior, and the data is queryable by fixed strike and fixed expiry_date across an arbitrary time range.

## Non-goals

- The actual diff-stability analysis/scoring (identifying which strike has the flattest diff) — not built.
- Any plotting or visualization of the captured data — not built.
- Any query helpers beyond the raw table and the batch writer — not built.
- Any integration with the existing `nifty_pe_cal_qtrly` / `nifty_pe_cal_monthly` / `nifty_pe_cal_weekly_to_monthly` trade-suggestion templates in `live/trade_suggestions.py` — not connected.
- Extending capture to symbols other than NIFTY50, or building a PE-specific strategy — undecided (PE rows are captured today only because they're free in the same API response, not because anything consumes them).
- Retention/pruning of `option_chain_5m` — deliberately not built (see Data / storage).

## Mechanics / behavior

- Runs inside the existing `live/poller.py` process, on its own 5-minute timer inside the main poll loop — not a fourth standalone process.
- Timer is a dedicated `CandleWatcher(5)` instance (`option_chain_watcher` in `poller.py`), separate from the pre-existing 5-minute candle-building watcher. `CandleWatcher.should_build()` is stateful (consumes the boundary fire once); sharing the existing 5m watcher would starve one of the two callers, so a second instance is used.
- Each poll-loop iteration: `option_chain_watcher.should_build()` is checked; when true, `option_chain_capture.run_capture()` is called, wrapped in `try/except` so a slow or failing option-chain fetch delays only that one loop iteration and never crashes the poller or blocks trigger/alert signal checking beyond that single cycle.
- `run_capture()` sweeps `SYMBOLS = ["NIFTY50"]` (the only symbol with an active options strategy today) across both `expiry_type` values (`"weekly"`, `"monthly"`) and `expiry_rank` 0/1/2 (six fetches per snapshot, when all six expiries exist).
- Each `(expiry_type, rank)` fetch is independently wrapped in `try/except` inside `capture_symbol()` — one bad rank or one failed API call drops only that expiry's rows, not the whole snapshot.
- For each fetch: `expiry_cache.pick(symbol, expiry_type, rank)` resolves the rank to a concrete `expiry_date`; if fewer than `rank+1` expiries of that type exist (e.g. only 2 monthly expiries loaded), `pick()` returns `None` and that rank is skipped — this is expected, not an error (confirmed in testing: monthly rank 2 was correctly skipped when only 2 monthly expiries existed).
- The resolved expiry_date is passed to Upstox's `OptionsApi.get_put_call_option_chain(instrument_key, expiry_date)`, which returns the full strike ladder for that expiry in one call — both CE and PE, plus `underlying_spot_price` (spot at capture time, so no separate LTP call is needed).
- Every strike in the returned ladder is captured, unfiltered — no pre-filtering to a strike band near spot. Filtering by moneyness/distance-from-spot is a query-time concern against the `spot_ltp` column, not a capture-time one, because pre-filtering would break tracking a *fixed* strike across days as spot drifts away from it (per the example: strike 24600 must stay trackable even after spot moves 430 points away).
- Capture timestamp (`ts`) is floored to the nearest clock-aligned 5-minute UTC boundary via `_boundary_ts()` — not wall-clock time of the fetch. Since IST offset (330 min) is a multiple of 5, UTC-aligned and NSE-market-aligned 5-min boundaries coincide exactly. This makes the same 5-min slot produce the same `ts` even if the poller restarts and re-captures — `INSERT OR IGNORE` against the row's unique key then makes the re-capture a no-op rather than a duplicate.
- `expiry_rank` (0/1/2) is relative to *capture time*, recomputed every snapshot — rank 0 is always "whichever expiry is nearest and unexpired right now." After a near expiry passes, what was rank 1 becomes the new rank 0. **Any analysis that needs to follow one specific expiry pair's diff across a full lifecycle spanning a rollover must filter by `expiry_date` (the fixed contract identity), never by `expiry_rank`** — filtering by rank would silently splice together two different contract pairs as if they were one continuous series. `expiry_rank` is only safe for "what's currently near/next/next2" queries.

### Fields captured per row

| Field | Source | Notes |
|---|---|---|
| `ts` | `_boundary_ts()` | 5-min-floored UTC, `YYYY-MM-DDTHH:MM:SSZ` |
| `symbol` | `SYMBOLS` loop | `"NIFTY50"` today |
| `spot_ltp` | `OptionStrikeData.underlying_spot_price` | per strike row in the API response, not a separate fetch |
| `expiry_type` | loop var | `"weekly"` \| `"monthly"` |
| `expiry_rank` | loop var | 0/1/2, relative to capture time — see caveat above |
| `expiry_date` | `expiry_cache.pick()` | fixed contract identity, `YYYY-MM-DD` |
| `strike` | `OptionStrikeData.strike_price` | |
| `opt_type` | loop | `"CE"` \| `"PE"` |
| `ltp` | `market_data.ltp` | nullable |
| `oi` | `market_data.oi` | nullable |
| `iv` | `option_greeks.iv` (`AnalyticsData`) | nullable |

## Architecture impact

- **New module**: `backend/live/option_chain_capture.py` — `_get_api()` (singleton `upstox_client.OptionsApi`, same construction pattern as `live/expiry.py`), `_boundary_ts()`, `_capture_expiry()`, `capture_symbol()`, `run_capture()`.
- **`backend/live/poller.py`** — additive only. Imports `option_chain_capture`; adds `option_chain_watcher = CandleWatcher(5)` alongside the existing `watchers` dict (built from `_INTRADAY_TF`); in the main `while` loop, checks `option_chain_watcher.should_build()` and calls `run_capture()` in its own `try/except` block, positioned after the existing candle-close handling and before `_all_ikeys` is built. Explicitly does **not** add anything to `_all_ikeys` (the list fed to the existing 5s `get_ltp()` call) — this is a fully separate fetch mechanism using the option-chain endpoint, not the LTP endpoint.
- **`backend/db/init_db.py`** — additive only. New `CREATE TABLE IF NOT EXISTS option_chain_5m` block plus two new indexes.
- **`backend/db/queries.py`** — additive only. New `write_option_chain_snapshot(rows: list[dict]) -> int` function, batch `INSERT OR IGNORE`.
- Reuses the existing `UPSTOX_ACCESS_TOKEN` config value and the already-loaded `expiry_cache` singleton (`live/expiry.py`) rather than bootstrapping a second token/cache in a standalone process.
- Does not touch `ticks`, `price_cache`, `candles_*`, `recommended_trades`, `trade_legs`, `TRIGGERS`, or any part of the trigger/alert pipeline (`live/triggers.py`, `live/alert.py`).

## Data / storage

**Table**: `option_chain_5m` (in `backend/db/init_db.py`)

```sql
CREATE TABLE option_chain_5m (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,
    symbol        TEXT    NOT NULL,
    spot_ltp      REAL    NOT NULL,
    expiry_type   TEXT    NOT NULL,
    expiry_rank   INTEGER NOT NULL,
    expiry_date   TEXT    NOT NULL,
    strike        REAL    NOT NULL,
    opt_type      TEXT    NOT NULL,
    ltp           REAL,
    oi            REAL,
    iv            REAL,
    UNIQUE (ts, symbol, expiry_date, strike, opt_type)
)
```

- Indexes: `idx_option_chain_5m_sym_ts (symbol, ts DESC)`, `idx_option_chain_5m_strike_expiry (symbol, expiry_date, strike, opt_type)`.
- Written from: `option_chain_capture.run_capture()` → `db.queries.write_option_chain_snapshot()`, every 5 minutes from the poller's main loop.
- Read by: nothing yet — no query helpers beyond the raw insert path exist. Future analysis code will query directly against this table.
- **No retention/cleanup job**, unlike `ticks` (7-day prune via `cleanup_ticks()`, since `ticks` is just a candle-building buffer). `option_chain_5m` *is* the analysis dataset itself, so rows are kept indefinitely by design.
- `INSERT OR IGNORE`, never `INSERT OR REPLACE` — the unique constraint exists purely to make poller-restart re-capture of the same 5-min slot a no-op, not to support upsert/overwrite semantics.
- Test data: during implementation, capture was verified against the live Upstox API (972 real rows across weekly ranks 0-2 and monthly ranks 0-1; monthly rank 2 correctly skipped since only 2 monthly expiries existed at test time), idempotency was confirmed (re-run wrote 0 new rows), and all test rows were deleted afterward — the table is clean as of this PRD.

## Success criteria

- With the poller running normally (`python poller.py live`), `option_chain_5m` gains new rows roughly every 5 minutes during market hours, with no observed impact on trigger firing, alert latency, or existing candle-building behavior.
- `SELECT COUNT(*) FROM option_chain_5m WHERE symbol='NIFTY50' AND ts >= '<today 09:15 IST in UTC>'` grows monotonically through the trading day at the expected rate (~6 expiry-fetches × strikes-per-chain × 2 opt_types, every 5 min, allowing for skipped ranks).
- Restarting the poller mid-session does not produce duplicate rows for a slot already captured (`INSERT OR IGNORE` verified during implementation testing).
- A query filtered by a single fixed `strike` + `expiry_date` (not `expiry_rank`) returns a clean, continuous time series across multiple days, including across an expiry rollover, without contract-identity splicing.
- A row for a strike far from current spot (e.g. 400+ points OTM) is still present days later, confirming the "don't pre-filter by moneyness at capture time" decision holds in practice.

## Open questions

- No decision has been made on whether to extend capture beyond `NIFTY50` to other symbols, or to build a PE-specific strategy on top of the PE rows already being captured (PE data is stored today only because it's free in the same API response — nothing consumes it yet).
- The diff-stability analysis itself (scoring which strikes have the flattest near/far premium diff) is undesigned — this PRD covers only the data-capture prerequisite.
- No query helpers or plotting exist; whoever builds the analysis will need to design the query layer (e.g. pivoting strike × ts × expiry_rank into a diff series) from scratch against the raw table.
- No decision on whether/when a retention policy might eventually be needed for `option_chain_5m` as it grows — currently intentionally unbounded.
