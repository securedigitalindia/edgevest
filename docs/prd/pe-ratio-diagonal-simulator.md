# NIFTY PE Ratio Diagonal Spread — Spot/Futures & Time Simulator

**Status (2026-09-08):** v1 and v2 rebuilt for a 4-leg/3-expiry strategy shape, replacing the original 2-leg/2-expiry version in place (see git history for that version; it was live for one day). v2's job also changed — see **Strategy shape** and **Views** below. Still not a tracked/traded strategy — this is a research/simulation tool, no `recommended_trades` rows, no Telegram alerts, no `trade_suggestions.py` template.

*(Original 2026-09-07 status, superseded: "v1 and v2 built and working; documented retroactively... Not yet a tracked/traded strategy.")*

## Problem

The user wants to evaluate a new options strategy — a **put ratio diagonal spread** — before trading it: build it, then poke at how it behaves under different spot moves and at different points in time, before committing capital. There was no existing tool in this repo for that: `nifty_pe_ratio_ladder_backtest.py` covers a same-expiry ratio ladder (different structure), `calendar_spread_strike_scoring.py` covers a same-strike CE calendar spread (different legs). Nothing simulates a fixed diagonal ratio spread's P&L against hypothetical spot/futures moves, nor replays it against real historical days.

## Goal

Given three strike variants of the strategy below, let the user:
1. See what it costs to open right now, live.
2. Simulate what it would be worth at other futures price levels, same point in time (no time passing).
3. Replay it against real historical days to see how the entry cost itself decayed as DTE fell.
4. See the *real* (not simulated) intraday P&L for any historical day, tick by tick.
5. Stitch multiple consecutive days into one continuous P&L line, as if held across all of them.

"Done" for v1+v2 is a runnable CLI pair plus a published interactive artifact covering all five views above for the current strategy shape. It is a read-only simulation tool — informs a human, does not itself trade or alert.

## Strategy shape

**Rebuilt 2026-09-08** — 4 legs across 3 expiries (was 2 legs / 2 expiries):

```
LEG 1  BUY  1x   expiry1   strike K        PE
LEG 2  SELL 2x   expiry2   strike K-gap    PE
LEG 3  SELL 1x   expiry2   strike K        PE
LEG 4  BUY  2x   expiry3   strike K-gap    PE
```

(`gap` default 400, e.g. K=24000 -> K-gap=23600.) Legs 1+2 are the original diagonal (buy near/sell far at a -gap strike step); legs 3+4 add its mirror one expiry cycle further out — a same-strike-K reverse calendar (buy expiry1 / sell expiry2) plus a same-strike (K-gap) 2x long calendar (sell expiry2 / buy expiry3).

- **K is not user-chosen.** Live execution rule: at 09:30 IST on entry day, snap the front-month NIFTY future's price down to the next-lower 100-multiple (`floor_strike_100`, e.g. fut=24065 -> K=24000). The old A/24100 · B/24000 · C/23900 parallel-variant exploration is gone — there's one real K per entry, derived from the fut price at that moment, not three hypothetical picks explored side by side. (A `--k-strike` override still exists on both scripts for manual what-if runs.)
- expiry1/2/3 are **dynamic**, resolved by merging Upstox's weekly+monthly expiry buckets, sorting real dates, and taking the first three with **DTE > 1** relative to the reference/entry day (`resolve_expiry_triplet` in `nifty_pe_ratio_diagonal_simulator.py`) — never trust the stored bucket/rank alone (a monthly-coinciding date gets pulled out of the weekly bucket even though it's 7 days after its neighbor; see the `calendar-spread-debit-proxy` skill for the same gotcha in a different strategy).
- **DTE > 1, not just DTE != 0** (tightened from the original 2-leg version's rule) — the 09:30 live-execution rule means an expiry with only 1 day left is already too close to serve as the near leg. Example: entry-date 2026-09-01 resolves expiry1=2026-09-08 (DTE=7 at entry) — 2026-09-01 itself (DTE=0) and any 1-DTE expiry are skipped.
- Reference price is the **front-month NIFTY future's LTP** (currently `NIFTY FUT 29 SEP 26`, `NSE_FO|68407`), not the index spot the option-chain API bundles as `underlying_spot_price`. The two carry a real basis (observed 2026-09-07: index ~23,900s vs futures LTP exactly 24,048) — strike selection and every "if price moved" simulation tracks the future, since that's what a trader actually watches against for this kind of entry.
- Lot size is resolved **live** from the futures contract (currently 65), never hardcoded — this repo's older ladder scripts assumed 65/75 by guess; a corporate action changing it wouldn't be caught by a stale constant.

## Non-goals

- Not a priced/greeks model — no Black-Scholes, no IV surface fitting. Every "if price moved" number is an **empirical strike-shift proxy**: today's (or that historical day's) actual premium at a strike shifted by the simulated move stands in for what the original strike would be worth at that level. Same technique as `calendar_spread_strike_scoring.py`, generalized to signed moves (that PRD's strategy was downside-only; this one needs both directions).
- No time-decay modeling *within* one view's own grid — the "Simulated futures move" grid freezes time; "Entry cost across time" is the only view that shows decay, and only at the single daily-close granularity (whatever "current"/"next" premium existed at each replay day's own end-of-day snapshot or, for intraday, every 5-min tick that day).
- No execution path, no `recommended_trades` row, no Telegram alert. Pure simulation/research.
- No symbols other than NIFTY50 — matches every other options tool in this repo.
- No margin/brokerage modeling — unlike `nifty_pe_ratio_ladder_backtest.py`, this doesn't call `get_margin`/`get_brokerage`. Pure premium P&L.

## Mechanics / behavior

### Data sourcing — Upstox-direct, not the local DB (key decision, arrived at after two false starts)

The DB (`option_chain_5m`, the local 5-min option-chain capture table used by `calendar_spread_strike_scoring.py`) was tried first for v2 and abandoned for price data:

1. **First attempt**: use `option_chain_5m` for both the live tab and historical replay. Rejected — the table was stale (last capture several days behind "today"), and using it for "live" would have silently priced strikes against a spot level from days ago.
2. **v1 (live tab)**: switched to a single live Upstox pull (`live/option_chain_capture.py`'s `capture_symbol()`) — no DB read at all.
3. **v2 first version**: still read `option_chain_5m` for historical replay days, reasoning Upstox has no bulk historical *chain* endpoint. This had a real gap: the poller wasn't running 2026-09-04 onward, so that day (and every day after) had zero rows — no way to replay it, and no way to build an intraday-actual chart for it.
4. **v2 current version**: confirmed Upstox's History API works **per individual instrument**, options included, further back than any local capture window (`HistoryV3Api.get_historical_candle_data1(instrument_key, "minutes", "5", to_date, from_date)` — same call already used for the futures reference price). So v2 now resolves the ~11-13 strikes per expiry the ±400 grid could ever need to their `instrument_key`s (`OptionsApi.get_put_call_option_chain`, 2 calls total, one per expiry) and pulls each one's full historical candle series in one call each. No DB reads for price data.

**One thing still reads the DB**: `db.queries.get_merged_cadence_dates(symbol)`, used only to get the list of expiry dates that have *ever* existed. Upstox's live expiry search (`live/expiry.py`'s `ExpiryCache`) only returns *currently-active* contracts — an already-expired weekly (like 2026-09-01, expired as of 2026-09-07) silently disappears from it, which breaks the "strict backward floor" computation (need to know what "the previous expiry" even was). The DB's capture history still remembers expired contracts even though its own price captures have gaps. If this DB dependency ever needs removing too, the fix is a small hardcoded/computed weekly-cadence assumption or a separate persisted expiry-history log — not attempted here.

### Views

1. **Live** (v1) — one live Upstox pull, K derived from the live fut price (floored to nearest 100), ±400 simulated-futures-move proxy grid across all 4 legs at that snapshot. Reference "day" for DTE purposes is computed via `resolve_reference_trading_day()` (in `nifty_fut_ref.py`): if the market hasn't opened yet today (before 09:15 IST) or today isn't a trading day, this walks back to the most recent real trading session and computes DTE from *that* day, not literal wall-clock "today" — otherwise a pre-market pull would mislabel stale Friday-close data as "today, DTE=1."
2. **Entry-date position tracking** (v2, rebuilt 2026-09-08) — given `--entry-date`, resolves the expiry triplet and K **once, at that day's 09:30 IST fut price**, then tracks the combined 4-leg position's mark-to-market value tick-by-tick from that entry point through the latest available data (historical candles up to yesterday, merged with today's intraday candles once the market has opened). Replaces the old version's job entirely — that version explored an arbitrary `--from-date`/`--as-of` replay *window* against one fixed (current, next) pair with no real anchor to an actual entry; this version has exactly one real entry per run, and answers "what does this position look like now" rather than "how would this shape have looked on various past days." Output: a daily open/close/DTE/P&L table plus the full tick series (for a chart), both via `--export-json`.

The old **strict backward replay limit** (a floor tied to "the expiry immediately preceding the reference current expiry") no longer applies — there's no arbitrary window to bound, since entry-date IS the anchor. The only failure mode now is a contract too old for Upstox to still resolve an `instrument_key` for (see Open Questions).

*(Superseded views from the original 2-leg build, not carried over: a separate "simulated futures move" tab per replay day, a stitched-continuous-replay UI for an arbitrary date range, and an "entry cost across time" x-by-DTE chart. The new v2 output covers the same underlying need — P&L vs. time/DTE — through the entry-anchored daily table instead.)*

## Architecture impact

New files, `backend/analysis/` (matches this repo's existing flat analysis-script convention — no new package):

- **`nifty_fut_ref.py`** — shared Upstox-direct helpers: `resolve_front_month_future`, `get_live_fut_ltp`, `fetch_candles_utc`/`fetch_intraday_candles_utc` (generic candle fetch, any instrument, historical/today respectively), `resolve_pe_instrument_keys`, `resolve_reference_trading_day`, `nearest_price`. No DB access. Unchanged by the 2026-09-08 rebuild.
- **`nifty_pe_ratio_diagonal_simulator.py`** (v1) — live-only CLI. Exports `simulate_strategy`/`print_strategy`/`snap_strike`/`floor_strike_100`/`resolve_expiry_triplet`, reused by v2.
- **`nifty_pe_ratio_diagonal_simulator_v2.py`** — entry-date position tracker (Upstox-direct + one DB read for the expiry-date list, see above). `--export-json` produces a `{entry info, daily table, tick-level points}` payload — a different shape than the pre-2026-09-08 version's replay-window JSON (see Artifact note below).
- **`nifty_pe_ratio_diagonal_backtest.py`** (2026-09-09) — sources every leg's premium primarily from local `option_chain_5m` (works for entry-dates whose expiry1 has already settled, which Upstox itself can no longer serve), falling back to a live Upstox pull — and persisting it — when local capture has a rank-window gap. `--from-date`/`--to-date` sweeps multiple entry-dates.
- **`nifty_pe_ratio_diagonal_averaging_backtest.py`** (2026-09-09) — averaging/laddered-entry variant: every `--up-move` (default 100) fut points from the last triggered set's own entry fires a brand-new 4-leg set with a fresh expiry triplet. Combined P&L sums every active set's own P&L since its own entry.
- **`nifty_pe_ratio_diagonal_windowed_backtest.py`** (2026-09-09) — chains the averaging backtest across every natural expiry-rollover window in a date range automatically; each window is fully independent and exits right when the next window's entry happens (not at its own actual settlement), with the post-exit continuation kept (tagged, not discarded) for a "what if held instead" comparison. Full detail: `docs/prd/pe-ratio-diagonal-strategy.md`'s "Averaging trigger + windowed backtest" section.
- **`nifty_pe_ratio_diagonal_windows_artifact.py`** + **`nifty_pe_ratio_diagonal_windows_template.html`** (2026-09-09) — the one-command builder for the tabbed rolling-windows artifact (runs the windowed backtest, reshapes each window, substitutes into the committed template, writes publishable HTML) and the template itself. Supports `--side PE|CE` (default `PE`) for a focused single-side view. Both committed here specifically so this doesn't have to be manually reconstructed in a future session — see the strategy PRD for the exact refresh command and current artifact URL.
- **`nifty_pe_ratio_diagonal_merged_windows_artifact.py`** + **`nifty_pe_ratio_diagonal_merged_windows_template.html`** (2026-09-09) — runs PE and CE independently within the same windows and renders both together (PE/CE own realized figures as primary tiles, a muted "Combined" reference), additive to the single-side builder above, not a replacement. Full detail, results, and rebuild command: strategy PRD's "CE-side mirror + merged PE+CE artifact" section.
- **`nifty_pe_ratio_diagonal_ema_entry_backtest.py`** (2026-09-09) — separate exploratory entry-rule variant: a systematic EMA20/EMA50-cross signal (mirrors `live/triggers.py`'s `EmaCrossTrigger` logic, evaluated on 5-min NIFTY FUT candle closes) drives entries instead of the averaging up-move trigger, with a simpler 2-leg (not 4-leg) shape. Not yet integrated with the windowed/averaging backtest or the artifact tooling above — standalone script, no published results yet.

No changes to `live/poller.py`, `db/init_db.py`, or any core schema. `option_chain_capture.py` did change (2026-09-09): `EXPIRY_RANKS` widened `[0,1,2]`→`[0,1,2,3,4]` and `EXPIRY_TYPES` gained `"quarterly"` — both were real correctness fixes for the backtest scripts above, not just additive, see the strategy PRD's "Backtest correctness fixes" section. Nothing here depends on the poller running except indirectly for the `get_merged_cadence_dates` DB read (which only needs *some* historical capture of an expiry date to have happened once, not continuous uptime) and for `option_chain_5m` itself being kept current (the user's own `poller.py live`, run separately).

## Artifact

**Rebuilt 2026-09-08 for the 4-leg shape: https://claude.ai/code/artifact/649d1b19-015d-4e14-8a60-61c8ed73002b** — one entry-date run (2026-09-01), embeds v2's full `--export-json` output inline as `DATA`. Shows: net debit/credit at entry, all 4 legs' entry premiums (card grid), a futures-price chart, a 4-line leg-premium chart, a diverging P&L chart, and a daily close table — each chart has a crosshair+tooltip. Verified in both light/dark themes and for console errors before publish.

To refresh with a different `--entry-date`: rerun v2 with `--export-json`, then re-run the same substitution step (read the template's data-embed pattern from this file's history, or regenerate by editing `DATA = {...}` in the published page directly) and republish to the same URL.

*(Old pre-rebuild artifact, no longer linked from here — was built for the 2-leg/replay-window shape: https://claude.ai/code/artifact/c745fb29-caaa-4044-ba1d-5f443bff488f)*

**Rolling-windows artifact, PE-only (2026-09-09): https://claude.ai/code/artifact/a087f925-cb3a-48f0-842e-6d625ff254b5** — one tabbed page, one tab per independent expiry-rollover window (25/31 Aug, 07 Sep so far), each showing its own triggered sets, futures/P&L charts (solid=realized, dashed=if-held-to-settlement reference past a red Exit marker), and two daily tables. Rebuild command and full mechanics: `docs/prd/pe-ratio-diagonal-strategy.md`.

**Merged PE+CE rolling-windows artifact (2026-09-09), the current primary reference for backtest results: https://claude.ai/code/artifact/39795623-8515-475f-8515-afee86658aea** — same windows, both sides run independently and shown together per window (PE/CE own realized figures as the primary stat tiles, a muted "Combined (PE+CE)" tile/line/table-column kept strictly secondary). Rebuild command and full mechanics: `docs/prd/pe-ratio-diagonal-strategy.md`'s "CE-side mirror + merged PE+CE artifact" section.

## Data / storage

None persisted — this tool writes nothing. Every run is a fresh Upstox pull (live + historical); the exported JSON files are scratch artifacts (`/private/tmp/.../scratchpad/`), not committed anywhere.

## Success criteria

- v1: live pull returns a real futures LTP and option premiums across all 4 legs; K resolves correctly via `floor_strike_100`; strike-shift proxy grid computes without missing data across ±400. Verified live 2026-09-08 (fut=23744.1 -> K=23700, all 4 legs priced, full ±400 grid populated).
- v2: given `--entry-date`, resolves the correct 09:30 IST entry fut price and expiry triplet, all 4 leg instrument_keys resolve, and the tick series tracks continuously from entry through the latest available tick with correct day-boundary daily open/close/P&L. Verified live 2026-09-08 with `--entry-date 2026-09-01` (resolved expiry1=2026-09-08 DTE=7 at entry, tracked 6 trading days through DTE=0 today).
- v2's `--export-json` output is directly consumable by the rebuilt artifact with no manual reshaping — confirmed for the 2026-09-01 entry-date run (verified live in-browser, both themes, no console errors).

## Open questions

- The rebuilt artifact covers **one entry-date run at a time** — no UI to pick a different `--entry-date` from inside the page itself, or to compare two entries side by side. Re-running and re-publishing is a manual step (see Artifact section above).
- **Browser verification gap** (noted in earlier PRD versions of this doc as unresolved) is now closed for this page: this session's browser-automation tool successfully interacted with the rebuilt artifact directly (hover tooltip, scroll, dark-mode toggle all confirmed working) — that limitation either never applied here or was specific to the old published page/tooling state.
- Whether to persist live/historical pulls back into a DB table (so reruns don't re-fetch identical historical candles from Upstox every time) is unresolved — currently every run re-fetches everything; the entry-anchored design means the range only ever grows from one fixed entry-date to "now," not an arbitrary rescanned window, so this matters less than it did for the old replay-window design.
- No PRD-stage validation of the 4-leg construction's risk profile (worst-case scenarios, margin at the ratio legs, whether the reverse-calendar/backspread combination has an unbounded-loss direction) — the shape (gap=400, 1:2:1:2 leg ratio, 09:30 floor-100 K rule) was given directly by the user, not derived or stress-tested here. Same kind of "no-move-loss filter before ranking by worst-case" caution documented in `docs/prd/calendar-spread-strike-scoring.md` likely applies before trusting this construction with real capital.
- Not yet decided whether/how this becomes a tracked strategy (a `trade_suggestions.py` template, a `recommended_trades` row, a Telegram alert) if the user decides to actually trade it — out of scope for this PRD, flagged for whoever picks this up next.
