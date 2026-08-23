# NIFTY Entry-Signal Quality Study — 1-HOUR Timeframe Extension — Report

Script: `backend/analysis/nifty_entry_signal_backtest_1h.py`
Data: `backend/data/drishti.db`, table `candles_1h`, symbol `NIFTY50`
Run date: 2026-07-28
Baseline being extended: `backend/analysis/nifty_entry_signal_backtest.py` / `nifty_entry_signal_backtest_report.md` — the daily-timeframe **Bollinger(20,2) lower-band re-entry + `z_ema200 > -0.5` filter** combo (reused conceptually, not re-derived, per instruction).

```
VERDICT: Not statistically distinguishable from noise as a 90%+ system, and — this is the
important finding — the daily-timeframe combo DOES NOT TRANSFER to the 1-hour timeframe.
Recomputed exactly (BB(20,2) lower-band re-entry + z_ema200 > -0.5, both on hourly closes),
scored against a hard 2-week-max (70-candle) forward window: n=48, hit1=56.2%, 90%
exact-binomial CI [43.4%, 68.5%]. This is a large-enough sample to trust (well above the
~30-trade floor) and its confidence interval sits entirely and comfortably BELOW the daily
study's 84.7-97.5% CI range for A1/A3 -- this is not "inconclusive," it is a real, evidenced
gap between timeframes. Worse: the z_ema200 filter that HELPED on daily (90.4%->94.0%) does
NOT help here -- the unfiltered base signal actually scores higher (n=106, hit1=64.2%, CI
[55.8%, 71.9%]) than the filtered one, and a direct kept-vs-excluded comparison shows the
signals the filter EXCLUDES have a nominally HIGHER hit rate (70.7%) than the ones it KEEPS
(56.2%) -- the opposite direction from daily, though not statistically significant on its own
(Fisher's exact p=0.16). The core reason is structural, not a bug: "200" periods on hourly
bars is only ~28.6 trading days (~5.7 weeks) of trend, a completely different, much
shorter-horizon filter than daily's ~200-trading-day (~9.5-month) trend measure -- it is
measuring something qualitatively different, and there is no evidence it does the same job
here. Neither signal (filtered or unfiltered) comes close to the user's ~90% bar at any
z-threshold, BB parameterization, or forward-window length tested.
```

## Strategy as tested

- **Base signal (H1):** Bollinger Band(20,2) lower-band re-entry on 1-hour NIFTY50 closes —
  close re-enters above the lower band having closed below it on the immediately preceding
  1h candle. Identical logic to daily A3, recomputed on hourly bars.
- **Filtered signal (H2, the direct daily-combo analog):** H1 AND `z_ema200 > -0.5`, where
  `z_ema200 = (close - EMA200) / rolling_200period_stddev(close)`, both EMA200 and the
  rolling stddev computed on **1-hour** closes (not daily).
- **"Works" definition:** entry_price = close[t]; looking forward at 1h-candle HIGHs over the
  next up to 70 one-hour candles (t+1 .. t+70, never t's own high — no same-bar lookahead),
  does price touch entry_price × 1.01 (+1%)? +2%/+3% tracked as stretch tiers, same as the
  daily study. Drawdown before the target hits does NOT disqualify a hit — identical
  methodology to the daily study throughout.
- **Sizing:** none (signal-quality study, not P&L, matching the daily study's scope).
- **Universe / timeframe:** NIFTY 50 index, 1-hour candles, 2024-07-29 → 2026-07-27 (the only
  history the `candles_1h` table has).
- **Assumptions made (stated, not stalled on):**
  1. **Forward window = 70 one-hour candles**, not the user's rough guess of "~60 candles (10
     trading days × ~6/day)". The actual per-day candle count was confirmed directly from the
     data (see Data section below): NSE 1h candles run 09:15/10:15/11:15/12:15/13:15/14:15/
     15:15 IST = **7 candles/trading day**, not 6. "2 weeks" = 10 trading days (same
     day-counting convention the daily study already used: "42 trading days ≈ 2 months" implies
     ~21 trading days/month, so 2 weeks = 10 trading days). 10 × 7 = **70 candles**, computed
     from the data, not assumed.
  2. Entry price = the signal candle's own close (matches the daily study's convention), not
     next-candle open.

## *** Flag: "200" means something very different in calendar time here ***

This is the single most important caveat in this report, stated up front per the task's
explicit instruction:

| | Daily (A3 + z_ema200 filter) | 1-hour (H2) |
|---|---|---|
| EMA200 / rolling-200-stddev window | 200 **trading days** | 200 **hourly candles** |
| Calendar span (using confirmed 7 candles/day) | ~200 trading days ≈ **9.5 months** | 200/7 ≈ **28.6 trading days ≈ 5.7 weeks (~1.3 months)** |
| Fraction of total available history in the dataset | ~4% of ~20y | ~5.8% of ~2y |

The daily filter measures "how far below a ~10-month trend is price, in units of its own
recent volatility." The 1h filter, using the identical "200" parameter, measures the same
thing over a ~6-week trend instead — a qualitatively different, much noisier, much
shorter-horizon regime read. This was not silently treated as an equivalent parameterization
anywhere in this analysis; it is very plausibly *why* the filter's effect flips direction
between timeframes (see Validation below).

## Data

- **Source:** SQLite (`drishti.db`), `candles_1h` table, `NIFTY50` symbol. **No yfinance
  fallback used or needed anywhere in this study** (hard rule per instruction) — the DB
  already has the full ~2 years the poller has bootstrapped.
- **Window:** 3,453 rows, 2024-07-29 03:45 UTC (09:15 IST) → 2026-07-27 09:45 UTC (15:15 IST),
  495 distinct IST trading dates.
- **Per-day candle count — confirmed directly from the data, not assumed:**
  493 of 495 dates have exactly **7** candles (09:15/10:15/11:15/12:15/13:15/14:15/15:15 IST);
  2 dates (**2024-11-01**, **2025-10-21**) have exactly **1** candle each. Both are genuine NSE
  special/Muhurat-trading half-day sessions (a single ~1h evening session is exactly what a
  Diwali Muhurat day looks like), not an ingestion gap — verified by checking those exact
  dates fall on NSE's published special-session calendar, not by assumption.
- **Data-quality checks (all clean, no fixes needed):** zero duplicate `(symbol, ts)` pairs,
  zero NaNs in OHLCV, zero OHLC integrity violations (`high >= max(open,close,low)` and
  `low <= min(open,close,high)` checked on every row). `volume = 0` on all 3,453 rows —
  expected (NIFTY 50 is an index; matches the daily table's documented behavior). No
  volume-based logic is used anywhere in this signal (per explicit instruction) — this is
  purely a price/BB/EMA study.
- **No dedup needed** (unlike the daily `candles_1d` table's documented double-write
  artifact) — `candles_1h` has one row per `(symbol, ts)` throughout.

## Core metrics — H1 (unfiltered) vs H2 (z_ema200-filtered, the direct daily-combo analog)

| Signal | n | Hit +1% | Hit +2% | Hit +3% | Avg max adverse dip | 90% bootstrap CI (hit1) | 90% exact-binomial CI (hit1) |
|---|---|---|---|---|---|---|---|
| **H1 — BB(20,2) reentry, unfiltered** | **106** | **64.2%** | 38.7% | 20.8% | 1.76% | [56.6%, 71.7%] | [55.8%, 71.9%] |
| **H2 — H1 + z_ema200 > -0.5** | **48** | **56.2%** | 31.2% | 20.8% | 1.70% | [43.8%, 68.8%] | [43.4%, 68.5%] |

Both n=106 and n=48 clear the ~30-trade floor for statistical meaningfulness stated in the
brief (unlike the daily study's small-sample D/C families) — **this is a real, trustworthy
result, not a thin sample**, and it says the combo underperforms its daily-timeframe
counterpart by a wide, non-overlapping-CI margin (compare to daily A3's [84.7%, 94.5%] and
A1's [87.2%, 97.5%] 90% exact-binomial CIs).

## Cost assumptions used

None modeled directly — same out-of-scope decision as the daily study (signal-quality study,
not a P&L study). As a substitute stress test (mirroring the daily report's approach), a
stricter **close-based** confirmation (candle **close**, not just intraday high wick, must
clear +1% within the 70-candle window) was checked directly:

| Signal | Hit +1% (high-based) | Hit +1% (close-based, stricter) | Degradation |
|---|---|---|---|
| H1 | 64.2% (68/106) | 61.3% (65/106) | -2.9pp |
| H2 | 56.2% (27/48) | 52.1% (25/48) | -4.1pp |

Mild, not a cliff — the touches that do occur are not razor-thin one-candle wicks. This
doesn't change the verdict either way: the baseline (wick-based) numbers are already well
below the 90% bar before any stricter definition or cost is applied.

## Validation results

### Walk-forward (first year vs. second year — the only split with enough data on each side)

Split at 2025-07-29 (midpoint of the ~2-year history):

| Signal | Train n (Y1: 2024-07-29→2025-07-28) | Train hit1% | Test n (Y2: 2025-07-29→2026-07-27) | Test hit1% | Gap |
|---|---|---|---|---|---|
| H1 unfiltered | 52 | 57.7% | 54 | 70.4% | **+12.7pp** |
| H2 filtered | 24 | 45.8% | 24 | 66.7% | **+20.8pp** |

Both signals do *better* out-of-sample here, which is a mild positive against overfitting (no
sign the first-year number was inflated by curve-fitting) — but note the swing size itself
(especially H2's 45.8%→66.7%) is large relative to n=24 per side, so this should be read as
"no red flag," not "confirmed stability."

### Rolling 4-fold walk-forward (expanding-window train, ~12-28 trades per test fold)

| Fold | H1 test n | H1 test hit1% | H2 test n | H2 test hit1% |
|---|---|---|---|---|
| 1 (no train data yet) | 26 | 61.5% | 12 | 33.3% |
| 2 | 26 | 53.8% | 12 | 58.3% |
| 3 | 26 | 61.5% | 12 | 50.0% |
| 4 | 28 | 78.6% | 12 | 83.3% |

Noisy, bouncing between the mid-30s and low-80s per fold — expected given each fold only has
12-28 trades. No monotonic degradation trend (rules out "decaying over time"), but no fold
ever approaches 90% sustained, either. This is consistent with "genuinely mediocre and noisy,"
not "secretly great but a few bad folds hide it."

### Monte Carlo / bootstrap and exact-binomial CI

Both already reported in the core-metrics table above. Bootstrap and Clopper-Pearson intervals
agree closely (as expected — n is large enough here that the bootstrap isn't degenerate the
way it was for the daily study's tiny all-hit samples). Both intervals for both H1 and H2 sit
entirely below 90%, with real width (H1: ~16pp wide, H2: ~25pp wide) reflecting genuine sample
uncertainty, not false precision.

### Parameter-sensitivity sweep

**z_ema200 threshold** (base BB(20,2), 70-candle window):

| Threshold | n | Hit +1% |
|---|---|---|
| z > -0.3 | 44 | 56.8% |
| z > -0.4 | 47 | 57.4% |
| **z > -0.5 (base)** | **48** | **56.2%** |
| z > -0.6 | 49 | 57.1% |
| z > -0.7 | 51 | 58.8% |

**This is a flat plateau — but a plateau of mediocrity, not of excellence.** Every threshold
from -0.3 to -0.7 lands in a tight 56.2-58.8% band. The signal isn't fragile to the exact
z-threshold (good, low overfitting risk on this specific parameter), but no threshold in this
range rescues it anywhere near 90%.

**Bollinger (length, std) sweep** (z_ema200 > -0.5 held fixed):

| length \\ std | 1.8 | 2.0 | 2.2 |
|---|---|---|---|
| 15 | n=68, 55.9% | n=54, 57.4% | n=36, 52.8% |
| 20 | n=60, 51.7% | n=48, **56.2%** (base) | n=37, 64.9% |
| 25 | n=49, 55.1% | n=42, 57.1% | n=31, 58.1% |

Also a plateau (51.7-64.9%), same read as above — parameter-robust, but robustly mediocre, not
robustly good. This mirrors the daily study's finding that A3's BB(20,2) parameterization
itself is not fragile — but here that robustness applies to a ~55-60% number instead of a
~90% one.

**Forward-window length sweep** (H1 unfiltered / H2 filtered side by side, candles → trading
days using the confirmed 7/day rate):

| Window | H1 n | H1 hit1% | H2 n | H2 hit1% |
|---|---|---|---|---|
| 35 candles (5 trading days) | 106 | 50.9% | 48 | 43.8% |
| 49 candles (7 trading days) | 106 | 55.7% | 48 | 47.9% |
| **70 candles (10 trading days, base = 2-week cap)** | **106** | **64.2%** | **48** | **56.2%** |
| 91 candles (13 trading days) | 105 | 67.6% | 47 | 61.7% |
| 105 candles (15 trading days) | 105 | 68.6% | 47 | 61.7% |

Hit rate climbs steadily as the window widens — expected, more time to reach a small target —
but even at 15 trading days (50% *beyond* the user's mandated 2-week ceiling) it only reaches
~62-69%, nowhere close to 90%. This directly shows the 2-week cap is a real, binding constraint
on this signal's apparent quality (the daily study's window was 42 trading days ≈ 2 months, over
4x longer) — but widening it further than the user's own instruction allows would not have
closed the gap to 90% regardless.

### Bias checks

- **Lookahead bias:** none found. The signal only compares `close[t]` against `close[t-1]` and
  `bb_low[t]` (itself a trailing rolling function of the prior 20 closes); `z_ema200[t]` uses
  only `EMA200` and `rolling(200).std()`, both backward-looking/recursive. The forward-outcome
  evaluator only reads candles `t+1 .. t+window`, never `t`'s own high/low. Unlike the daily
  script's A6/B5 confluence signals, no centered-window or multi-trigger confirmation logic is
  used here, so there was no analogous lookahead bug class to fix — verified by direct code
  inspection, not just assumed clean because the daily version was.
- **Survivorship bias:** N/A — single index, not a basket.
- **Overfitting:** **low risk on the parameters actually swept** (2 free parameters — BB(length,
  std) and the z-threshold — both shown to sit on real plateaus above, not cliffs, and neither
  was tuned on this 1h dataset; both were carried over unchanged from the daily study). The
  real risk here is a **different, more subtle one**: the "200" period count itself was
  transplanted from daily to hourly without adjustment, which — as flagged above — measures a
  ~6-week trend instead of a ~9.5-month one. This isn't a parameter that was swept and found
  fragile; it's an implicit assumption (that "200" is "the same 200" across timeframes) that
  this study's results suggest is simply false for this signal, structurally, not from
  overfitting to noise.
- **Cost-doubled stress test:** N/A directly (no costs modeled, matching the daily study's
  scope) — substituted with the close-based-confirmation stricter test above (mild
  degradation, not a cliff; doesn't change the verdict since the baseline already fails the bar).

## Filter-direction check — does z_ema200 > -0.5 actually help here?

Directly testing whether the filter is doing its intended job (excluding the deeper-below-trend,
"dead cat bounce risk" signals) by comparing the KEPT subset (z_ema200 > -0.5, n=48) against the
EXCLUDED subset (z_ema200 ≤ -0.5, n=58, both drawn from H1's 106 total):

| Subset | n | Hit +1% |
|---|---|---|
| **Kept (z_ema200 > -0.5)** | 48 | **56.2%** |
| **Excluded (z_ema200 ≤ -0.5)** | 58 | **70.7%** |

Fisher's exact test on this 2×2 table: **p = 0.155** — not statistically significant at
conventional thresholds, so this should not be over-read as "the filter actively hurts." But
it is the **opposite direction** from the daily study, where the analogous exclusion
demonstrably helped (90.4%→94.0%). Combined with the "200 means something different" structural
point above, the honest read is: **there is no evidence in this data that the z_ema200 filter
does the same job on 1h bars that it does on daily bars**, and a plausible reason it might even
point the wrong way is that on a ~6-week lookback, "far below trend" partly captures ordinary
short-term mean-reversion setups (which tend to bounce) rather than "deep, dead-cat-bounce-risk"
territory the way a ~9.5-month lookback does.

## Where it fails

There isn't a single dramatic "COVID-style" failure mode the way the daily study found (the
2-year window here doesn't span a crash on the scale of COVID or 2008) — the failure mode is
structural and pervasive, not episodic: the majority of H2's 21 misses are **near-misses**, not
disasters. Looking at the full per-signal table below, most misses have `best_fwd_gain_pct` in
the 0.0-0.99% range (i.e. the price got close to +1% but the 2-week window expired first) and
modest `max_adverse_dip_pct` (1-8%, nothing like daily A1/A3's worst 20-38% drawdowns). This
means the signal is directionally reasonable (price often does drift up somewhat after the
BB-reentry trigger) but the **2-week window is frequently too short** for the move to fully
develop into a full +1% touch — confirmed directly by the window-length sweep above, where hit
rate keeps climbing as the window widens (43.8%→61.7% for H2 across 5→15 trading days) without
ever reaching a ceiling near 90% even 50% past the user's own mandated cap.

## Currently live / most-recent matching setup (as of latest candle, 2026-07-27 15:15 IST)

**No fresh signal fires on the most recent (2026-07-27 15:15 IST) candle** for either H1 or H2 —
the prior candle's close was not below the BB(20,2) lower band, so no re-entry condition is
met.

- **H1 (unfiltered), most recent signal:** fired **2026-07-24 11:15 IST** at close 23,702.85.
  11 of 70 candles elapsed as of the latest data. The +1% target (≥23,939.88) was already
  touched (best forward gain so far +1.30%, on essentially zero drawdown, 0.01%) — **this
  entry is already a resolved HIT** even though its window hasn't formally closed.
- **H2 (filtered), most recent signal:** fired **2026-07-22 12:15 IST** at close 23,978.85
  (z_ema200 = 0.202 at fire time — comfortably clears the -0.5 filter). 24 of 70 candles
  elapsed. Best forward gain so far only +0.19%, current max adverse dip 1.55% — **this entry
  is still open and currently NOT a resolved hit**; 46 candles remain in its window.

## Full per-signal table — H2 (BB(20,2) reentry + z_ema200 > -0.5, n=48 complete windows)

Entry = close on the re-entry candle. "z_ema200" is the filter value at fire time (all > -0.5
by construction). Outcome shows the highest target reached and candle-count to reach it
(candle 1 = the next 1h candle), or, for misses, the best forward gain achieved anywhere in
the 70-candle window. Max adverse dip = worst drawdown from entry before the +1% hit (or
before window expiry if it never hit). One additional signal (2026-07-22 12:15 IST) fired but
is excluded from this table/headline as its 70-candle window is still open (see "Currently
live" above).

| Date/time (IST) | Entry | BB(20,2) lower band | z_ema200 | Outcome (candles to reach) | Max adverse dip |
|---|---|---|---|---|---|
| 2024-09-06 13:15 | 24865.60 | 24841.02 | 0.320 | HIT +3% (c59) | 0.45% |
| 2024-10-03 10:15 | 25491.95 | 25484.11 | 0.231 | MISS (best +0.00%) | 3.13% |
| 2024-10-03 14:15 | 25258.45 | 25246.70 | -0.354 | MISS (best +0.90%) | 2.23% |
| 2024-12-10 14:15 | 24612.00 | 24545.89 | 0.793 | MISS (best +0.73%) | 4.37% |
| 2024-12-13 11:15 | 24560.45 | 24378.09 | 0.514 | MISS (best +0.94%) | 4.17% |
| 2025-02-07 14:15 | 23573.70 | 23478.02 | 0.284 | MISS (best +0.07%) | 3.62% |
| 2025-02-10 10:15 | 23401.30 | 23398.03 | -0.296 | MISS (best +0.04%) | 3.64% |
| 2025-02-10 12:15 | 23353.85 | 23340.94 | -0.451 | MISS (best +0.24%) | 3.45% |
| 2025-03-27 09:15 | 23600.35 | 23487.19 | 1.467 | MISS (best +0.21%) | 7.87% |
| 2025-04-01 14:15 | 23174.50 | 23130.44 | 0.260 | HIT +3% (c69) | 6.17% |
| 2025-04-04 13:15 | 22909.60 | 22900.18 | -0.336 | HIT +3% (c47) | 5.09% |
| 2025-04-25 12:15 | 24047.15 | 23958.54 | 1.142 | HIT +3% (c70) | 0.25% |
| 2025-05-09 13:15 | 24005.05 | 23970.47 | 0.293 | HIT +3% (c3) | 0.18% |
| 2025-05-20 15:15 | 24713.85 | 24706.14 | 0.640 | HIT +1% (c22) | 1.02% |
| 2025-05-22 10:15 | 24594.60 | 24594.34 | 0.478 | HIT +1% (c7) | 0.54% |
| 2025-06-02 10:15 | 24623.25 | 24621.87 | 0.534 | HIT +2% (c34) | 0.49% |
| 2025-06-12 11:15 | 25039.15 | 25036.78 | 1.413 | HIT +1% (c56) | 2.26% |
| 2025-06-13 11:15 | 24688.95 | 24646.22 | 0.061 | HIT +3% (c61) | 0.15% |
| 2025-06-20 09:15 | 24919.05 | 24743.35 | 1.196 | HIT +3% (c42) | 0.38% |
| 2025-07-02 14:15 | 25459.55 | 25433.44 | 1.520 | MISS (best +0.50%) | 1.80% |
| 2025-07-03 15:15 | 25397.40 | 25394.48 | 1.131 | MISS (best +0.60%) | 1.56% |
| 2025-07-04 12:15 | 25370.70 | 25342.89 | 0.987 | MISS (best +0.70%) | 1.78% |
| 2025-07-10 12:15 | 25382.25 | 25362.46 | 0.680 | MISS (best +0.19%) | 1.97% |
| 2025-07-11 12:15 | 25155.70 | 25144.99 | -0.039 | MISS (best +0.40%) | 1.37% |
| 2025-08-22 11:15 | 24925.50 | 24898.96 | 0.284 | MISS (best +0.39%) | 2.09% |
| 2025-09-22 15:15 | 25200.20 | 25199.12 | 0.828 | MISS (best +0.24%) | 2.43% |
| 2025-09-23 11:15 | 25142.60 | 25111.68 | 0.597 | MISS (best +0.47%) | 2.21% |
| 2025-09-25 15:15 | 24904.55 | 24884.20 | -0.387 | HIT +1% (c43) | 1.27% |
| 2025-10-14 13:15 | 25122.75 | 25085.86 | 0.506 | HIT +3% (c24) | 0.09% |
| 2025-10-31 11:15 | 25798.15 | 25771.55 | 0.829 | MISS (best +0.82%) | 1.86% |
| 2025-11-06 10:15 | 25560.50 | 25539.76 | 0.164 | HIT +2% (c67) | 0.95% |
| 2025-11-07 10:15 | 25410.55 | 25371.64 | -0.176 | HIT +3% (c65) | 0.02% |
| 2025-11-25 09:15 | 26018.60 | 25951.81 | 1.030 | HIT +1% (c14) | 0.68% |
| 2025-11-26 09:15 | 26084.25 | 25865.89 | 1.304 | MISS (best +0.93%) | 1.37% |
| 2025-12-02 13:15 | 26045.05 | 26020.32 | 0.821 | MISS (best +0.60%) | 1.35% |
| 2025-12-03 10:15 | 25919.65 | 25917.13 | 0.205 | HIT +1% (c16) | 0.11% |
| 2025-12-08 14:15 | 25971.15 | 25918.06 | 0.262 | MISS (best +0.81%) | 1.07% |
| 2025-12-09 10:15 | 25865.00 | 25820.00 | -0.225 | HIT +1% (c62) | 0.66% |
| 2025-12-26 13:15 | 26044.15 | 26037.66 | 0.620 | HIT +1% (c34) | 0.64% |
| 2026-02-06 10:15 | 25576.40 | 25537.32 | -0.008 | HIT +1% (c6) | 0.19% |
| 2026-02-13 11:15 | 25573.40 | 25570.62 | -0.226 | HIT +1% (c26) | 0.78% |
| 2026-04-13 10:15 | 23743.70 | 23666.48 | 0.026 | HIT +3% (c29) | 0.06% |
| 2026-04-23 11:15 | 24222.50 | 24193.01 | 0.420 | HIT +1% (c64) | 1.76% |
| 2026-04-24 11:15 | 23930.65 | 23894.97 | -0.047 | HIT +2% (c54) | 0.49% |
| 2026-04-30 11:15 | 23899.75 | 23797.83 | -0.131 | HIT +2% (c26) | 0.11% |
| 2026-05-11 11:15 | 23935.55 | 23909.36 | -0.166 | MISS (best +0.26%) | 2.81% |
| 2026-06-24 09:15 | 23917.85 | 23798.65 | 0.525 | HIT +2% (c50) | 0.03% |
| 2026-07-09 09:15 | 24044.25 | 23877.63 | 0.202 | HIT +1% (c43) | 0.49% |

27/48 = 56.2% HIT +1%. Full per-signal CSVs for both H1 and H2 were also generated (see
"Files" note at the end of this report / the parent response).

## Comparison against the daily-timeframe version — side by side

| | Daily A3 (BB reentry, unfiltered, full-history) | Daily A3+filter (z_ema200 > -0.5, full-history) | Daily A3+filter, last 2 years | **1h H1 (unfiltered)** | **1h H2 (filtered, direct analog)** |
|---|---|---|---|---|---|
| n | 115 | 67 | 8 | **106** | **48** |
| Hit +1% | 90.4% | 94.0% | 100% | **64.2%** | **56.2%** |
| 90% CI | [84.7%, 94.5%]\* | ~[87-98%]\* | n/a (too small) | **[55.8%, 71.9%]** | **[43.4%, 68.5%]** |
| Forward window | 42 trading days (~2 months) | 42 trading days | 42 trading days | **10 trading days (2-week cap, ~4.2x shorter)** | **10 trading days (2-week cap)** |
| Filter effect vs. unfiltered | — | **+3.6pp (helps)** | **+7.7pp (helps)** | — | **-8.0pp (hurts, not significant)** |
| "200" lookback in calendar time | ~9.5 months | ~9.5 months | ~9.5 months | — | **~5.7 weeks (~7x shorter)** |
| Total history available | ~20 years | ~20 years | 2 years (mandated) | **~2 years (all that exists)** | **~2 years (all that exists)** |

\*Daily A3+filter's exact CIs are not directly reproduced in the daily report as read (the
report cites its numbers primarily as point estimates plus context from A1/A3's own
unfiltered CIs); treat the "~[87-98%]" here as an approximate bound for comparison purposes,
not a literal re-quote.

The two headline facts: **(1)** the 1h version's hit rate is 30+ percentage points lower than
the daily version's, with confidence intervals that do not overlap at all, and **(2)** the
filter that reliably helped on daily reliably does not help (and directionally slightly hurts)
on hourly. Both are consistent with the same root cause — a 2-week forward window and a
~6-week trend filter are simply testing a very different, much shorter-horizon phenomenon than
a 2-month window and a ~9.5-month filter.

## Recommendation

Do not deploy the 1-hour version of this combo signal, and do not treat it as "the same edge,
just on a faster clock." This is not a small-sample problem (n=48-106 is large enough to trust)
and not a parameter-tuning problem (the z-threshold and BB-parameter sweeps both show genuine
plateaus, ruling out "just needs the right threshold") — it is a genuine, well-evidenced
timeframe-transfer failure. The most likely fixable issue, if the user wants to pursue an
hourly version of this idea further, is the mismatched window scaling: this study's own
window-length sweep shows hit rate climbing steadily (44%→69% for H1) as the forward window
widens even past the user's 2-week cap, and the "200-period" trend filter measuring a ~6-week
regime instead of a ~9.5-month one is very plausibly why the filter's effect direction flipped.
A more honest next step than declaring the idea dead would be to explicitly time-scale both
parameters to match daily's calendar-time horizons (e.g., a ~1,400-period EMA/rolling-stddev
for a ~9.5-month-equivalent lookback, and a forward window closer to 2 months' worth of 1h
candles, ~294 candles) rather than reusing the raw period counts unchanged — but that is a
different, unasked-for experiment, not a fix within the scope of what was requested here (a
strict 2-week window, "200" literally as stated). As instructed and as literally specified,
the verdict stands: this combo does not clear the user's bar on 1-hour bars, and the daily
study's numbers should not be extrapolated to imply it would.

# Part 2 — E-family: Supertrend(10, 2.6) bull flip × EMA20 × RSI(14) buckets (2026-07-28 session)

Run date: 2026-07-28. Same new signal introduced in `nifty_entry_signal_backtest.py` /
`nifty_entry_signal_backtest_report.md`'s Part 4 (Supertrend(10,2.6) bear→bull flip, split by
close vs EMA(20) and RSI(14) vs 50 at the flip candle), recomputed here on 1-hour candles
using this file's confirmed 70-candle (~2-week) forward window / +1%/+2%/+3% tiers /
drawdown-tolerant hit definition — identical methodology to H1/H2 above, not reinvented.

```
VERDICT (1h): Real, statistically usable, but well short of a 90%+ system, and it does NOT
match the daily timeframe's number for the same signal. E1 (the "all three true" headline
combo: ST(10,2.6) bull flip + close>EMA20 + RSI>50), n=68, scores 69.1% hit1, 90%
exact-binomial CI [58.7%, 78.3%] -- comfortably above a coin flip and, notably, ABOVE the
unfiltered base flip (E0, n=79, 65.8%), unlike the daily version where E1 was essentially
identical to E0. But 69.1% sits nowhere near the daily timeframe's 93.9% for the identical
rule, and the two CIs do not overlap at all. E2/E4 (n=7, n=4) are honestly too small to
trust despite non-trivial hit rates; E3 has zero signals in 2 years of history. This is the
third confirmation in this project that a Supertrend/EMA/RSI-family signal's forward-window
calendar span, not just its period count, is the dominant driver of hit-rate differences
across timeframes -- consistent with, not contradicting, the earlier BB+z_ema200 finding.
```

## Strategy as tested

Identical rule to the daily version (see the daily report's Part 4 for the full spec and the
tie-break assumption, reused verbatim): Supertrend(period=10, multiplier=2.6) bear→bull flip
on **1-hour** NIFTY50 closes; at the flip candle, close vs EMA(20) and RSI(14) vs 50 (both
computed on 1h closes) are recorded, using the same strict-`>`-is-"above" tie-break. Forward
window, targets, and drawdown-tolerant hit definition are this file's already-established
70-candle / +1%/+2%/+3% convention (see the file header docstring) — not re-derived.

## Core metrics — base flip + all 4 buckets (2024-07-29 → 2026-07-27, complete 70-candle windows only)

| Signal | n | Hit +1% | Hit +2% | Hit +3% | Avg max adverse dip |
|---|---|---|---|---|---|
| **E0 — ST(10,2.6) flip, no split (reference)** | **79** | **65.8%** | 41.8% | 24.1% | 1.67% |
| **E1 — flip + close>EMA20 + RSI>50 (HEADLINE)** | **68** | **69.1%** | 44.1% | 25.0% | 1.47% |
| E2 — flip + close>EMA20 + RSI<=50 | 7 | 42.9% | 14.3% | 14.3% | 3.23% |
| E3 — flip + close<=EMA20 + RSI>50 | 0 | — | — | — | — |
| E4 — flip + close<=EMA20 + RSI<=50 | 4 | 50.0% | 50.0% | 25.0% | 2.34% |

**Small-sample flag, stated plainly:** E2 (n=7) and E4 (n=4) are well below the ~30-trade
floor — their 42.9%/50.0% point estimates should not be read as "the filter fails when EMA/RSI
disagree," they simply aren't a large enough sample to say anything. E3 has **zero** signals
in the full ~2-year history (a 1h ST(10,2.6) bull flip essentially never happens with close
below/at EMA20 while RSI is simultaneously above 50 — mechanically rare, same direction as
the daily timeframe's E3=0). Only E0 (n=79) and E1 (n=68) clear the floor and are carried
through the validation gauntlet below.

## Cost assumptions used

None modeled directly (same scope as H1/H2 above). Close-based stricter-confirmation stress
test below, mirroring the H1/H2 approach.

## Validation results

### Walk-forward (first year vs. second year, split 2025-07-29)

| Signal | Train n (Y1) | Train hit1% | Test n (Y2) | Test hit1% | Gap |
|---|---|---|---|---|---|
| E0_ST26_flip_base | 36 | 61.1% | 43 | 69.8% | +8.7pp |
| E1_ST26_flip_aboveEMA20_RSIabove50 | 32 | 65.6% | 36 | 72.2% | +6.6pp |

Both do better out-of-sample, mirroring H1/H2's finding above (mild positive against
overfitting, but the swing itself is large relative to n≈32-43 per side — "no red flag," not
"confirmed stability").

### Rolling 4-fold walk-forward, E1 (expanding-window train, ~17 trades per test fold)

| Fold | Test n | Test hit1% |
|---|---|---|
| 1 (no train data yet) | 17 | 70.6% |
| 2 | 17 | 58.8% |
| 3 | 17 | 70.6% |
| 4 | 17 | 76.5% |

Noisy (58.8-76.5%), no monotonic trend — same "genuinely mediocre-to-decent and noisy, not
secretly hiding a 90%+ signal" read as H1/H2.

### Monte Carlo / bootstrap and exact-binomial CI

| Signal | n | Point hit1% | 90% bootstrap CI | 90% exact-binomial CI |
|---|---|---|---|---|
| E0_ST26_flip_base | 79 | 65.8% | [57.0%, 74.7%] | [56.1%, 74.7%] |
| E1_ST26_flip_aboveEMA20_RSIabove50 | 68 | 69.1% | [60.3%, 77.9%] | [58.7%, 78.3%] |

Both n's clear the ~30-trade floor — a trustworthy result, just not a good enough one. Neither
CI comes close to overlapping the daily timeframe's [88.4%, 97.3%] for the identical rule.

### Parameter-sensitivity sweep (period ±20%, multiplier ±~20%, E1 headline combo)

| period \ mult | 2.10 | 2.35 | 2.60 (base) | 2.85 | 3.10 |
|---|---|---|---|---|---|
| 8  | n=71, 69.0% | n=69, 66.7% | n=69, 69.6% | n=61, 72.1% | n=55, 69.1% |
| 10 | n=69, 68.1% | n=69, 66.7% | n=68, **69.1%** | n=60, 71.7% | n=54, 68.5% |
| 12 | n=68, 69.1% | n=65, 66.2% | n=65, 70.8% | n=61, 73.8% | n=55, 69.1% |

A real plateau (66.2-73.8% across all 15 combinations) — not fragile to the exact
parameterization, same as the daily version, but the plateau sits at ~66-74% instead of
~93-96%.

### Forward-window length sweep, E1 (candles → trading days at the confirmed 7/day rate)

| Window | n | Hit +1% |
|---|---|---|
| 35 candles (5 trading days) | 68 | 58.8% |
| 49 candles (7 trading days) | 68 | 67.6% |
| **70 candles (10 trading days, base)** | **68** | **69.1%** |
| 91 candles (13 trading days) | 67 | 73.1% |
| 105 candles (15 trading days) | 67 | 76.1% |

Same climbing-with-window pattern found for H1/H2 earlier in this file — even 50% past the
user's 2-week cap (15 trading days), hit rate only reaches 76.1%, nowhere near daily's 93.9%.
This directly supports the cross-timeframe read below: the 2-week cap is a real, binding
constraint on this signal's apparent 1h quality, not just a filter artifact.

### Bias checks

- **Lookahead bias:** none — identical single-candle-snapshot construction to the daily
  version (Supertrend direction, close, EMA20, RSI14 all backward-looking on 1h closes through
  the flip candle only).
- **Survivorship bias:** N/A — single index.
- **Overfitting:** low risk on the swept parameters (period/multiplier plateau shown above).
  The larger risk, as flagged throughout this file, is the "200 means something different
  across timeframes" issue for indicators that use a 200-period lookback — **not directly
  applicable to E-family**, since E1 uses EMA(20)/RSI(14), both short enough that 20-24
  candles (1h) vs. 20-24 trading days (daily) is a real, if smaller, calendar-time mismatch
  (~3 trading days vs. ~20 trading days) worth naming even though it's not the dominant driver
  here — the forward-window length difference is.
- **Cost-doubled stress test:** substituted with close-based stricter confirmation (below), as
  in H1/H2.

### Close-based stricter-confirmation stress test (substitute for cost-doubling)

| Signal | Hit +1% (high-based) | Hit +1% (close-based) | Degradation |
|---|---|---|---|
| E0 | 65.8% | 63.3% | -2.5pp |
| E1 | 69.1% | 66.2% | -2.9pp |

Mild, not a cliff — consistent with both the daily E-family result and H1/H2's finding.

## Cross-timeframe comparison — does E1 behave consistently between daily and 1h?

| | Daily E1 | 1h E1 |
|---|---|---|
| n | 99 | 68 |
| Hit +1% | 93.9% | 69.1% |
| 90% exact-binomial CI | [88.4%, 97.3%] | [58.7%, 78.3%] |
| E1 vs E0 (base) lift | -0.2pp | **+3.3pp** |
| Bucket split (E1/E2/E3/E4) | 99/1/0/1 (of 101) | 68/7/0/4 (of 79) |

**No overlap in the CIs — a real, evidenced divergence**, the same direction (1h
underperforms daily) found for the H1/H2 BB+z_ema200 combo earlier in this file. Two
differences from that earlier finding are worth naming explicitly:

1. **The EMA20/RSI50 filter itself does NOT flip direction here** the way z_ema200 did for
   H1/H2 — E1 is mildly *positive* relative to E0 on both timeframes (essentially flat on
   daily, +3.3pp on 1h). This signal's cross-timeframe gap is not a "the filter works
   backwards on 1h" story.
2. **The gap is instead almost entirely attributable to the forward-window length mismatch**
   (42 trading days / ~2 months on daily vs. 70 candles / 10 trading days / ~2 weeks on 1h —
   a ~4.2x difference), confirmed directly by the window-length sweep above: even pushed 50%
   past the user's own 2-week cap, 1h hit rate only reaches 76.1%, still well short of 93.9%.
   This is the same lesson already flagged at the top of this file (from the earlier BB+z_ema200
   session) applied again: "N periods"/"N-candle window" means something very different in
   calendar time across timeframes, and this is the dominant driver of the divergence for
   this particular signal — not a broken filter.

## Currently live / most-recent matching setup (as of latest candle, 2026-07-27 15:15 IST)

`st26_dir` has been in **bull** mode for at least the last 5 candles as of the latest data.
The most recent E1 fire is **2026-07-27 09:15 IST** at close 23,933.30 (the first candle of
the latest trading day) — **6 of 70 candles elapsed**, best forward gain so far only +0.33%,
essentially flat, **not yet resolved either way**. This is a genuinely open, currently-live
E1 setup (unlike the daily timeframe, where the most recent E1 fire from 2026-06-16 is
already a resolved historical hit).

## Recommendation

Do not deploy the 1-hour version of E1 expecting anything close to daily's ~94% hit rate —
confirmed here for the third time in this project (after the earlier BB+z_ema200 case) that
window-length/calendar-time mismatches across timeframes materially change a signal's
apparent quality, even when (as here, unlike the BB+z_ema200 case) the filter's *direction*
of effect stays consistent. At 69.1% (CI [58.7%, 78.3%], n=68, a trustworthy sample size),
this is a real, better-than-coin-flip signal on 1h bars in its own right — mildly better than
its own unfiltered base rate (65.8%) — but it should be evaluated and used as its own,
weaker, 1h-specific signal, not as "the same edge as daily, just faster." If the user wants
1h performance closer to daily's, the same fix suggested for H1/H2 applies: time-scale the
forward window to daily's ~2-month calendar span (roughly 294 1h candles) rather than holding
it at a literal 2-week cap — a different, unasked-for experiment, not in scope here.

# Part 3 — F-family: EMA20-gap two-sided mean-reversion, LONG + SHORT (2026-07-28 session)

Run date: 2026-07-28. Same spec as the daily script's F-family (see its report's Part 5 for
the full definition, edge-case reasoning, and no-lookahead argument) — `gap_pct = (close -
EMA20)/EMA20*100` computed on 1h closes/EMA20 instead of daily ones. F1=LONG fires the first
1h candle `gap_pct` crosses below -3%; F2=SHORT fires the first 1h candle it crosses above
+3%. Same forward window as every other 1h signal in this file: 70 candles (10 trading days,
~2 weeks, at the confirmed 7 candles/trading day rate).

```
VERDICT (1h): Neither side is statistically meaningful at the mandated 3% threshold, or at
any threshold in the sweep -- this is a hard small-sample case, not a borderline one, and it
is reported that way rather than dressed up. At the base 3% threshold, F1 (long) fires only
n=2 times and F2 (short) only n=1 time in the full ~2 years of available 1h history. Even
loosening the threshold to 2% (the loosest end of the mandated sweep) only reaches n=8 (long)
and n=7 (short) -- both still far below the ~30-trade floor this project has held to
throughout. Both n=2 long fires happened to hit +1% (100%), and the single short fire also
hit (100%), but per the user's standing instruction this is explicitly NOT presented as a
validated result: a sample this size proves nothing, and a single future miss would swing the
"hit rate" by 33-100 percentage points. The directional pattern visible even in this tiny
sample (long side: 8/8 hits at the 2% threshold; short side: only 3/7 hits at the 2% threshold)
is DIRECTIONALLY CONSISTENT with the daily timeframe's F1>>F2 asymmetry (93.7% vs. 77.0%) --
but "consistent with" is not the same as "confirmed by" at this sample size, and is reported
as a suggestive-only observation, not a finding.
```

## Why the 1h sample is this small (root cause, not just a data-availability complaint)

A 3%+ gap between an hourly close and its own EMA(20) is a genuinely large, comparatively rare
move at the 1h timeframe -- EMA(20) on 1h bars tracks roughly the last ~3 trading days (20
candles / 7 per day), a much shorter and more responsive lookback than daily EMA20's ~1 month.
Price rarely gets 3%+ away from a trend line that reactive within only ~2 years of available
1h history (2024-07-29 -> 2026-07-27, 3,453 candles). This is the same "200 means something
different on 1h" phenomenon flagged for the H1/H2 and E-family sections above, playing out on
a shorter EMA this time: the indicator recipe is identical, but the frequency of a 3% breach
against a 20-candle EMA is structurally much lower on hourly bars than on daily ones, and 2
years of 1h history is simply not enough calendar time to accumulate a usable sample of such
breaches -- more history, not a parameter tweak, is what this signal needs on this timeframe.

## Core metrics — base 3% threshold (complete 70-candle windows only)

| Signal | n | Hit +1% | Hit +2% | Hit +3% | Avg max adverse move |
|---|---|---|---|---|---|
| F1_ema20gap_long (3%) | 2 | 100.0% | 100.0% | 50.0% | 0.41% |
| F2_ema20gap_short (3%) | 1 | 100.0% | 0.0% | 0.0% | 0.81% |

**Small-sample flag, stated plainly per the user's standing rule: n=2 and n=1 are not
statistically meaningful at any hit rate shown, including the 100% figures above.** No
walk-forward split, bootstrap CI, or regime-block analysis is presented for these — there is
not enough data for any of those tools to say anything (a train/test split of 1-2 points each
is meaningless, and a bootstrap resample of n=1-2 just reproduces the single observed outcome
with a degenerate, zero-width or trivial CI). This is flagged rather than computed and
presented as if it meant something.

## Threshold sweep (2%/2.5%/3%/3.5%/4%, both sides) — still too small at every setting

| Threshold | n (long) | Hit1% (long) | n (short) | Hit1% (short) |
|---|---|---|---|---|
| 2.0% | 8 | 100.0% | 7 | 42.9% |
| 2.5% | 4 | 100.0% | 3 | 66.7% |
| **3.0% (base)** | **2** | **100.0%** | **1** | **100.0%** |
| 3.5% | 1 | 100.0% | 1 | 100.0% |
| 4.0% | 1 | 100.0% | 1 | 100.0% |

Even at the loosest end of the mandated sweep (2%), n tops out at 8 (long) / 7 (short) — both
still less than a third of the ~30-trade floor used throughout this project. There is no
threshold in this sweep at which the 1h version of this signal reaches a statistically usable
sample size. This is exactly the kind of result the user's standing instruction anticipates:
report it honestly as unusable, not as "100% hit rate, promising."

## Full per-signal detail — all fires at 2% threshold (most populated cut available, n=8/7)

Shown at the 2% threshold (not the 3% headline) specifically because it is the most populated
cut in the sweep — even so, still far too small to validate. All times IST.

**F1 (LONG, n=8):**

| Time (IST) | Entry | EMA20 | gap_pct | Outcome | Max adverse move |
|---|---|---|---|---|---|
| 2024-08-05 09:15 | 24292.15 | 24801.96 | -2.06% | HIT (d61) | 1.64% |
| 2025-04-07 09:15 | 21918.15 | 23002.62 | -4.71% | HIT (d5) | 0.55% |
| 2026-03-04 09:15 | 24413.65 | 25033.39 | -2.48% | HIT (d8) | 0.24% |
| 2026-03-09 09:15 | 23806.20 | 24554.86 | -3.05% | HIT (d5) | 0.26% |
| 2026-03-13 09:15 | 23329.80 | 23838.63 | -2.13% | HIT (d15) | 1.61% |
| 2026-03-13 12:15 | 23175.70 | 23691.89 | -2.18% | HIT (d9) | 0.95% |
| 2026-03-23 09:15 | 22572.30 | 23219.36 | -2.79% | HIT (d7) | 0.45% |
| 2026-04-02 09:15 | 22234.35 | 22704.20 | -2.07% | HIT (d4) | 0.20% |

8/8 = 100% hit +1% at the 2% threshold — every single 1h long fire in ~2 years of data
recovered +1% within the 70-candle window. Encouraging on its face, structurally consistent
with the daily-timeframe long side being the stronger of the two, but n=8 cannot be presented
as validated under the user's standing small-sample rule.

**F2 (SHORT, n=7):**

| Time (IST) | Entry | EMA20 | gap_pct | Outcome | Max adverse move (UP) |
|---|---|---|---|---|---|
| 2024-11-25 09:15 | 24261.75 | 23676.90 | +2.47% | HIT (d24) | 0.38% |
| 2025-04-15 09:15 | 23312.10 | 22726.81 | +2.58% | MISS (best +0.17%) | 4.91% |
| 2025-04-17 12:15 | 23788.65 | 23319.31 | +2.01% | MISS (best +0.11%) | 3.37% |
| 2025-04-21 09:15 | 24033.45 | 23509.24 | +2.23% | MISS (best +0.77%) | 2.31% |
| 2026-02-03 09:15 | 25671.00 | 25121.88 | +2.19% | HIT (d63) | 1.32% |
| 2026-04-08 09:15 | 23880.45 | 22963.66 | +3.99% | HIT (d21) | 0.81% |
| 2026-06-15 09:15 | 23945.05 | 23415.69 | +2.26% | MISS (best +0.67%) | 0.67% |

3/7 = 42.9% hit +1% at the 2% threshold — notably weaker than the long side even at this tiny
sample size, directionally consistent with the daily timeframe's F1>>F2 asymmetry, but again
n=7 is not a validated result.

## Bias checks

- **Lookahead bias:** none — identical no-lookahead argument as the daily F-family (same-bar
  `gap_pct` computed from `close[t]` and `EMA20[t]`, crossing test only compares `gap_pct[t]`
  vs. `gap_pct[t-1]`). Trivially safe by construction.
- **Survivorship bias:** N/A — single index.
- **Overfitting / small-sample risk:** this is the dominant risk here, not overfitting in the
  traditional sense. With only 1-8 trades at any tested threshold, ANY reported hit rate
  (including the 100% figures above) reflects a handful of historical instances, not a
  statistically estimable rate. This is exactly the small-sample flag the task brief asked to
  be reported honestly rather than dressed up.

## Currently live / most-recent matching setup (as of latest candle, 2026-07-27 15:15 IST)

**No fresh F1 or F2 signal on the latest candle.** `gap_pct` as of the last 1h candle
(2026-07-27 15:15 IST) is **+0.35%** (close 24,003.65 vs. EMA20 23,919.10) — well inside the
±3% band.

- **F1 (long, 3% threshold):** last fired **2026-03-09 09:15 IST** at close 23,806.20
  (gap_pct -3.05%). 657 candles have elapsed since (window is 70 candles) — long since
  resolved (**HIT**, +1% touched at candle 5). Nothing actionable as a fresh entry today.
- **F2 (short, 3% threshold):** last fired **2026-04-08 09:15 IST** at close 23,880.45
  (gap_pct +3.99%). 524 candles have elapsed since — long since resolved (**HIT**, +1% touched
  at candle 21). Nothing actionable as a fresh entry today.

## Cross-timeframe comparison — does F1/F2 behave consistently between daily and 1h?

| | Daily F1 (long) | 1h F1 (long, 3%) | Daily F2 (short) | 1h F2 (short, 3%) |
|---|---|---|---|---|
| n | 111 | 2 | 148 | 1 |
| Hit +1% | 93.7% | 100.0% | 77.0% | 100.0% |
| Statistically usable? | Yes (n>>30) | **No (n=2)** | Yes (n>>30) | **No (n=1)** |
| Forward window | 42 trading days (~2 months) | 70 1h candles (~2 weeks) | 42 trading days | 70 1h candles |

Unlike the earlier BB+z_ema200 and E-family signals in this project (which both had large
enough 1h samples to compute a real, if divergent, CI), **the F-family cannot be compared
across timeframes on statistical terms at all** — the 1h sample is too small at every
threshold tested for its point estimate to mean anything, so there is no real 1h number to
set against the daily one. The one thing that CAN be said: the direction of the long/short
asymmetry is the same on both timeframes even at the loosest 1h threshold (2%: 100% long vs.
42.9% short on 1h; 93.7% long vs. 77.0% short on daily) — suggestive that the long-side
mean-reversion bet is mechanically the stronger one on this instrument regardless of
timeframe, and that fading an overbought market is the weaker bet on both timeframes too. This
is an observation, not a validated cross-timeframe finding, given the 1h sample size.

## Recommendation

Do not use the 1h version of F1/F2 for anything requiring statistical confidence — there is
not enough 1h history (only ~2 years) for a 3%-vs-a-20-candle-EMA breach to accumulate a usable
sample size, and loosening the threshold within the mandated sweep range does not fix this (n
tops out at 8/7 even at 2%). If the user wants a validated 1h version of this idea, the
practical options are: (a) wait for more 1h history to accumulate, (b) lower the threshold well
below 2% (outside the sweep tested here, and at that point arguably a different, more
frequently-firing signal rather than "the same 3% idea on a faster clock"), or (c) accept the
daily-timeframe F1 result (a real, validated, and by some distance the strongest long-side
signal candidate produced by this project so far) as the deployable version of this idea and
treat 1h as out of scope for it.
