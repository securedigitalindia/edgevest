# NIFTY CE Calendar-Spread Strike Scoring

## Problem

`docs/prd/option-chain-capture.md` built the data prerequisite — `option_chain_5m` — but explicitly left "the actual diff-stability analysis/scoring" and "query helpers beyond the raw table" undone. This PRD is that follow-on: turning the captured option-chain time series into a concrete strike recommendation for a specific strategy — a NIFTY CE **sell-near / buy-far calendar spread** (SELL the nearer weekly-cadence expiry, BUY the next one out, same strike, same `opt_type='CE'`).

Today, choosing a strike for this spread is a manual, eyeballed exercise with no systematic way to reason about downside risk. The trader's own worked example captures the intuition this feature needs to formalize:

> "if i sell 24300 rank1 and buy 24300 rank2 my debit is 70 and suddenly market falls 300 points as per current data it looks like my debit will change as per 24600 if market falls 300 and debit will become 58.1, just as per data speaks. so risk will be 12 rupee but with time that debit will change also and it can again move to 70 if few days goes by and market stays as same point for lets say 3 days, after 3 days 24300 rank1 will become 20 and rank2 lets say 170 so debit will be again 90, so no loss even after 300 point fall and 3 days goes by"

In other words: a spot fall shifts which strike is effectively "at the money," so the debit at strike K after a fall behaves *approximately* like the debit currently observed today at strike K+fall (a spatial proxy for a temporal question) — but that snapshot alone ignores that theta decay on the near leg, acting over the days that pass, also reshapes the debit independently of any spot move. Nobody currently has a way to combine both effects and ask, per strike: "how much spot-fall + how many days can this position absorb before the debit gets worse than entry?"

## Goal

Given the current NIFTY50 option-chain state captured in `option_chain_5m`, produce a concrete recommendation for the sell-near/buy-far CE calendar spread:

1. **Best strike** — among the 8 CE strikes nearest to spot on the upside (ATM and above), the one whose debit is least sensitive to a downside spot move combined with elapsed time.
2. **Safe tolerance window** — a day-range / spot-fall-tolerance estimate within which that strike's debit is expected to stay flat-or-better (i.e. theta decay on the near leg offsets spot-fall-driven repricing risk), based on the same worked-example logic above.

"Done" for this PRD is a runnable analysis module that, given a sufficiently rich `option_chain_5m` history (see Open Questions — this does not exist yet), computes and prints/returns this recommendation for the current NIFTY50 CE chain. It is a read-only analysis/scoring tool, not a live signal, not a trade suggestion template, and not an execution path — per the codebase's existing signal / trade-suggestion / execution distinction (`backend/CLAUDE.md`), this tool sits *before* all three: it informs which strike a human (or a future `trade_suggestions.py` template) might act on, but does not itself fire an alert or open a `recommended_trades` row.

## Non-goals

- **PE calendar spreads** — explicitly out of scope. CE only, per the strategy as specified.
- **Upside risk** — explicitly out of scope. The user was explicit that upside gap risk is "safe" and excluded from this analysis; the scoring model only needs to handle downside spot movement, not both directions.
- **Symbols other than NIFTY50** — matches `option_chain_5m`'s current capture scope (`live/option_chain_capture.py`'s `SYMBOLS = ["NIFTY50"]`).
- **The full option chain** — only the 8 CE strikes nearest to spot on the upside are in scope, not all captured strikes.
- **Any change to capture, schema, or the poller** — `backend/live/poller.py`, `backend/live/option_chain_capture.py`, and the `option_chain_5m` table are untouched. This is a new read-only query/analysis layer on top of existing data.
- **Wiring into `live/trade_suggestions.py` or `recommended_trades`** — matches the parent PRD's non-goal on the existing trade-suggestion templates (`nifty_pe_cal_qtrly` / `nifty_pe_cal_monthly` / `nifty_pe_cal_weekly_to_monthly`, all PE-based and unrelated to this CE strategy). This tool does not open, alert on, or auto-place trades.
- **Live position monitoring** — this is a pre-trade strike-selection tool, not a running check of an already-open position's debit against its "safe" tolerance. Monitoring an open spread is a different, unbuilt feature.
- **Locking in a model architecture** — whether the debit-at-(strike, days-elapsed, spot-fall) estimate is built via empirical/historical regression over many captured days, or a simpler rule-based/interpolation approach, is explicitly left open (see Open Questions). This PRD specifies the *behavior* and *inputs*, not the internal estimation method.
- **Building or validating anything against today's data** — see the blocker below. Non-goal until the prerequisite data exists.

## Mechanics / behavior

### Universe

- Symbol: `NIFTY50` only.
- Option type: `CE` only.
- Candidate strikes: the **8 distinct captured strikes nearest to spot on the upside** — i.e. starting from the ATM strike (the captured strike minimizing `abs(strike - spot_ltp)` at the query timestamp) and going up, take that strike plus the next 7 strikes above it (8 total). Deep-ITM/downside strikes are excluded — not of interest for this strategy per the user's framing.

### Expiry-pair resolution — merged cadence rank (query-layer only, no schema/capture change)

Upstox's own `weekly` flag (`live/expiry.py`'s `_categorise()`) puts the monthly-coinciding date into the `monthly` bucket and *excludes* it from `weekly` — e.g. one real observed split was `weekly = [2026-07-21, 2026-08-04, 2026-08-11]`, `monthly = [2026-07-28, 2026-08-25]`, even though all four/five dates are actually 7 days apart from their neighbors. Using Upstox's `expiry_type`/`expiry_rank` as stored would therefore pick the wrong "next" expiry for this strategy — the buckets are type-relative, not cadence-relative.

This feature instead defines a **merged/continuous 7-day-cadence rank**, computed purely at query time against already-captured data — no new column, no capture-time change:

```
cadence_dates(symbol) =
    sorted(DISTINCT expiry_date
           FROM option_chain_5m
           WHERE symbol = ? AND expiry_type IN ('weekly', 'monthly'))
```

`cadence_dates[N]` is "cadence rank N" (0-indexed, nearest first). Reapplying this to the observed example above: `cadence_dates = [2026-07-21, 2026-07-28, 2026-08-04, 2026-08-11, 2026-08-25]` — a clean weekly-spaced sequence, exactly reproducing the user's own "rank1"/"rank2" pair as `cadence_dates[1] = 2026-07-28` (SELL leg) and `cadence_dates[2] = 2026-08-04` (BUY leg), skipping `cadence_dates[0]` (the imminent/current expiry, not used as a leg in this strategy).

- **The SELL leg = `cadence_dates[1]`**, the **BUY leg = `cadence_dates[2]`** — always 7 calendar days apart by construction of the merged cadence.
- This rank must be resolved by sorting real distinct `expiry_date` values pulled from `option_chain_5m` for the symbol at query time — **never** by trusting the stored `expiry_rank` column, which is bucket-relative (per `docs/prd/option-chain-capture.md`'s own caveat: "`expiry_rank` is only safe for 'what's currently near/next/next2' queries" within a single `expiry_type`, not across the merged weekly+monthly cadence this strategy needs).
- Because `option_chain_5m` only has an `expiry_date` string per row (not a pre-merged rank), this transformation lives entirely in the new query layer — it is not persisted anywhere.

### Debit metric

For a given strike `K`, opt_type `CE`, and timestamp `ts`:

```
debit(K, ts) = ltp(K, cadence_dates[2], ts) - ltp(K, cadence_dates[1], ts)
             = far-leg premium - near-leg premium
```

This is the cost to open (or current value of) the position — SELL near collects `ltp(K, cadence_dates[1])`, BUY far pays `ltp(K, cadence_dates[2])`, net debit is the difference.

### Combining spot-fall and time-decay effects

The core scoring question, per the worked example, is: for a candidate strike `K`, how does `debit(K, ·)` behave under **both** of the following simultaneously (downside only, per Non-goals):

1. **Spot-fall repricing (spatial)** — a spot fall of `F` points makes strike `K`'s post-fall debit resemble the *currently observed* debit at strike `K + F` (since a lower spot makes `K` relatively further OTM, similar to how `K+F` sits relative to today's spot). This is read directly off a single snapshot's cross-strike debit curve — no time series needed for this component alone.
2. **Time decay (temporal)** — holding spot roughly fixed, the near leg (closer to its own expiry) decays faster than the far leg as `D` days pass, which independently pushes the debit — per the example, decay alone can restore or exceed the original debit even after a strike-implied fall reduced it. This requires comparing the *same* strike's debit across snapshots taken `D` days apart — a genuine multi-day time series, not a single-snapshot proxy.

The scoring function needed is `estimated_debit(K, F, D)` — debit at strike `K` after a spot fall of `F` points and `D` days elapsed — combining both effects rather than either alone (the spatial proxy alone ignores decay; decay alone ignores the fall).

### Estimation method — DTE-proxy (validated 2026-07-21, resolves the open architecture question)

Interactive analysis against real market-hours data confirmed a concrete empirical method, superseding the "undecided, needs a model" framing this PRD originally shipped with. Full mechanics documented in the `calendar-spread-debit-proxy` skill (`.claude/skills/calendar-spread-debit-proxy/SKILL.md`) — summary:

- **Key insight**: every weekly-cadence expiry is 7 calendar days apart (`cadence_dates[N+1] - cadence_dates[N] = 7d`, by construction — see Expiry-pair resolution above). This means **`cadence_dates[0]` (the imminent, soon-to-expire contract) vs `cadence_dates[1]` (the current SELL leg)**, observed on any given day, is a live structural proxy for what the *actual* SELL/BUY leg pair (`cadence_dates[1]` / `cadence_dates[2]`) will look like once the SELL leg reaches that same DTE. The right axis is **DTE-of-the-near-leg**, not "days from today" — a captured snapshot where some contract sits at `N` DTE proxies the target date `sell_leg_expiry − N days`, regardless of which actual calendar date that snapshot was taken on.
- **Time-decay component (`D`)**: as more days of capture accumulate, `cadence_dates[0]` traces its own full DTE countdown (e.g. 1, 0) while `cadence_dates[1]` does the same the following week — stitching these across days yields a real multi-point decay curve per strike, not a single 0-vs-7 jump. Validated example (2026-07-20 data, 07-21 contract at 1 DTE / 07-28 at 8 DTE, vs. 2026-07-21 data, same contracts at 0/7 DTE): strike 24250 proxy debit went 112.95 (07-27, near@1DTE) → 116.25 (07-28, near@0DTE) — nearly flat — while strike 24600 went 50.65 → 26.60, a sharp collapse. The two strikes have materially different decay shapes into the near leg's final day, which is exactly the signal this PRD's scoring needs.
- **Spot-fall component (`F`)**: applied on top of the DTE proxy by shifting the strike by the assumed fall amount before the lookup (`estimated_debit(K, F, D) ≈ observed_debit(K + F, N_DTE_snapshot)` where the DTE snapshot corresponds to `D` days out) — combining both effects in one lookup rather than two separate single-effect estimates.
- **Current data ceiling**: as of 2026-07-21, DTE=1 and DTE=0 proxy points exist for the near leg — DTE=2 through DTE=6 will appear automatically as daily captures continue through the week and `cadence_dates[0]`'s successor contract counts down. No historical backfill can produce these; they only arrive via ongoing capture. This is a narrower, now-quantified version of the blocking data gap in Open Questions below, not a replacement for it.
- **One DTE point is real, not proxied**: `cadence_dates[1]` (the SELL leg) sits at a genuine DTE *today* — `(cadence_dates[1] − today).days`, 7 by construction of the cadence as long as the imminent contract hasn't rolled — and today's actual `cadence_dates[1]`/`cadence_dates[2]` prices at that DTE are ground truth, not an estimate. Don't proxy a DTE value that's already directly observable; only strictly lower DTE values need the `cadence_dates[0]`-contract proxy. The implemented tool includes this real point alongside the proxied ones in every DTE-indexed table, labeled to distinguish it.

This resolves "empirical regression vs. rule-based interpolation" in favor of **empirical, built directly from the rank0-decay-curve + strike-shift lookup** — no fitted model/regression needed as a first pass; the estimate is a direct table lookup against accumulated real snapshots. Whether a smoothed/fitted model on top of this raw lookup is later worth it (e.g. to interpolate DTE/strike values that fall between captured grid points) remains open, but the base method is no longer an unknown.

### Ranking — filter before ranking on worst-case loss

Found during implementation: **ranking candidate strikes by worst-case rupee loss alone is unsound.** A cheap, far-OTM strike can show the smallest *absolute* worst-case loss purely because there's little premium in it to begin with — while simultaneously already losing money in the flat-spot, zero-elapsed-time case (thin near/far legs decaying against each other with no edge even absent any adverse move). The implemented tool computes a `no_move_ok` flag per strike (P&L ≥ 0 at every available DTE with spot unchanged from entry) and restricts the worst-case-loss ranking to strikes that pass it — a strike that fails `no_move_ok` is excluded from recommendation regardless of how small its worst-case number looks.

### Output

For the current chain state:
- **Recommended strike** — among the `no_move_ok` candidates (see above), the one whose `estimated_debit(K, F, D)` stays flattest (least negative movement, i.e. least likely to exceed the entry debit) across the downside scenarios evaluated. Rupee-loss and percentage-loss rankings can disagree (cheaper entries show larger % swings for the same rupee move); the implemented tool defaults to ranking by rupee loss and flags when the two disagree.
- **Safe tolerance window** — the `(F, D)` combination(s) — e.g. "up to 300 points down, over up to 3 days" — within which the recommended strike's debit is estimated to stay flat-or-better than entry, mirroring the shape of the user's own worked example. The implemented tool reports this as the first spot level (working down from entry) at which projected P&L turns negative, per available DTE.

## Architecture impact

- **No changes** to `backend/live/poller.py`, `backend/live/option_chain_capture.py`, or the `option_chain_5m` schema in `backend/db/init_db.py` — this is a pure read/analysis layer on top of existing data, matching the parent PRD's framing of the diff-stability analysis as separate follow-on work.
- **New query helpers in `backend/db/queries.py` — implemented** (the codebase's only file with raw SQL — `backend/CLAUDE.md`: "only file with SQL"): `get_merged_cadence_dates(symbol)`, `get_option_chain_ltp(symbol, opt_type, expiry_date, strike, ts)`, `get_latest_option_chain_ts(symbol, date_prefix=None)`, `get_option_chain_capture_days(symbol, expiry_date)`. These are the "query helpers beyond the raw table" the parent PRD explicitly deferred.
- **New standalone module — implemented** at `backend/analysis/calendar_spread_strike_scoring.py` (new top-level directory). Run via `cd backend && source venv/bin/activate && python analysis/calendar_spread_strike_scoring.py --support <spot> --resistance <spot>`. Rationale for a new directory rather than reusing an existing one:
  - `backend/backtest/backtest.py` is a standalone CLI script (argparse, `sys.path.insert` to reach `config`/`db`, invoked directly — not via `poller.py`) but is purpose-built around replaying `TRIGGERS` from `config.py` against candle data; it doesn't fit an option-chain-specific scoring tool.
  - `backend/live/` is reserved for code that runs inside the live poller process (`backend/CLAUDE.md`'s Architecture section) — this tool is explicitly not part of that loop.
  - `backend/utils/verify_db.py` is DB-integrity tooling (invoked via `poller.py verify`), not analysis.
  - The new `backend/analysis/` module follows the same standalone-script conventions as `backtest/backtest.py` (`sys.path.insert` for imports, direct calls into `db/queries.py`, printable/CLI-runnable, no package `__init__.py`, matching `backtest/`'s convention over `live/`'s). Implemented as purely standalone — no `poller.py analysis` subcommand — see Open Questions, now resolved.
- **Reuses `expiry_cache` / `UPSTOX_INSTRUMENT_KEYS` from `live/expiry.py`?** No — this tool only reads already-captured rows from `option_chain_5m`; it does not call the Upstox API directly. `expiry_cache` is a live/poller-time concept and is not needed here.
- **Backend is never run inside a Claude session** (repo convention) — this PRD, like the parent one, is a spec only; validating it requires running the poller through real market sessions, which happens outside any agent session.

## Data / storage

- **No new tables, columns, or indexes.** Purely reads from the existing `option_chain_5m` table (`ts, symbol, spot_ltp, expiry_type, expiry_rank, expiry_date, strike, opt_type, ltp, oi, iv`).
- **No retention/pruning implications** — this feature doesn't write anything, so it has no bearing on `option_chain_5m`'s existing "kept indefinitely" retention decision.
- **If the eventual model needs a fitted/cached artifact** (e.g. regression coefficients from a historical fit), where that would live — a new small table, a serialized file, or recomputed on every invocation — is undecided and explicitly out of scope for this PRD to lock in; it depends on which estimation approach (regression vs. rule-based) is chosen during implementation.
- Nothing in `ticks`, `candles_*`, `recommended_trades`, `trade_legs`, or any other table is read or written by this feature.

## Success criteria

Real data now exists, so some of these are checkable today; the backtest-style item still needs more accumulated history.

- ✅ **Met** — `get_merged_cadence_dates` confirmed to produce `cadence_dates[1]`/`cadence_dates[2]` exactly 7 calendar days apart against real captured data (2026-07-21: `[2026-07-21, 2026-07-28, 2026-08-04, 2026-08-11, 2026-08-25]`).
- ✅ **Met** — `debit(K, ts)` manually cross-checked against the tool's output (`far_ltp - near_ltp`) during implementation; matches.
- ✅ **Met** — the tool degrades gracefully: per-cell `None`/"no-data" when a strike/expiry/ts combination isn't captured, and a top-level "insufficient data" message when fewer than 3 cadence dates or zero DTE snapshots exist, rather than crashing or guessing.
- **Still open** — backtest-style validation (pick a historical date where NIFTY subsequently fell by `F` points over `D` days, check whether the strike the tool would have recommended actually stayed flat-or-better through that realized move) needs more accumulated multi-day history than exists yet; not yet run.

## Open questions

- ~~**Blocking data gap**~~ — **partially resolved.** Real market-hours captures now exist (from 2026-07-21 onward) — the frozen single-snapshot problem this PRD originally flagged is gone. Still limited: only DTE=1/DTE=0 proxy points plus the real DTE=7 point are available so far (captures only started 2026-07-20) — DTE=2 through DTE=6 will fill in automatically as daily captures continue. The tool degrades to "insufficient data" per-strike/per-cell rather than guessing when a DTE isn't yet available, so it's usable today with a narrower DTE range, and gets more complete without further code changes as more days accumulate.
- ~~**Estimation model architecture**~~ — **resolved 2026-07-21**, see "Estimation method — DTE-proxy" above. Empirical direct lookup against the rank0-decay-curve + strike-shift, not a fitted regression, as the first-pass method.
- ~~**Invocation mechanism**~~ — **resolved.** Standalone CLI script, `backtest/backtest.py` pattern (not a `poller.py` subcommand) — implemented at `backend/analysis/calendar_spread_strike_scoring.py`.
- ~~**ATM/strike-interval definition**~~ — **resolved, differently than originally proposed.** The implemented tool uses 100-pt strike multiples (not the raw 50-pt captured grid, and not a single "nearest to spot" pick) — candidates run from the first 100-pt strike above spot up to the user-supplied `--resistance`, capped at 8. `--support`/`--resistance` are CLI inputs, not `config.py` constants.
- **How much historical data is "enough"** to trust the DTE-proxy lookup across the full DTE=0..6 range and multiple down-move episodes — still undecided, narrows to: how many full weekly cycles of captured data before the lookup table has reasonable coverage at every (strike, DTE) cell.
- **Granularity of `D` (days elapsed)** — the implemented tool uses whatever DTE granularity the capture cadence naturally provides (one point per calendar day) rather than a fixed override — whether a coarser/finer granularity would ever be worth engineering remains open, but isn't blocking.
- **Whether/how a fitted model artifact would be persisted** (new table vs. file vs. recompute-on-demand) — still undecided; the implemented tool recomputes on every invocation with no persisted artifact, which is sufficient for the current empirical-lookup approach and only becomes relevant if a fitted/smoothed model is added later.
- **PE symmetry** — the parent PRD already flagged that PE rows are captured but unused; this PRD keeps that open rather than resolving it (CE-only is a deliberate, explicit scope decision here, not an oversight).
