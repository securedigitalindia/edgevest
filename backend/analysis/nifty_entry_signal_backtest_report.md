# NIFTY Entry-Signal Quality Study — Report

Script: `backend/analysis/nifty_entry_signal_backtest.py`
Data: `backend/data/drishti.db`, table `candles_1d`, symbol `NIFTY50` (config.py `SYMBOLS` name)
Run date: 2026-07-27

```
VERDICT: Fragile-but-close — the strongest candidates (Supertrend(10,3) bear->bull flip;
Bollinger(20,2) lower-band re-entry) land at 90–93% hit rate on the strict +1%-floor/42-day
definition, with a genuinely robust parameter plateau and stable performance across four
different multi-year market regimes. That is honestly right at — not clearly above — the
user's ~90% bar. Neither clears 90% with statistical confidence (bootstrap 90% CI lower
bounds sit at 86–88%), and both have identical, un-fixable failure modes: they miss on
sudden macro/exogenous shocks (COVID Feb 2020, the 2015 China-scare rollover, Jan 2025 and
Feb 2026 corrections), and no regime filter tested here meaningfully screens those out in
advance because the macro backdrop looked fine (EMA200 flat-or-rising, price above EMA200)
right up to the day before the shock hit. This is a real, structurally sound edge — not
noise — but it is not a 90%+ system, and the user should not expect it to be one.
```

## Strategy as tested

- **Universe / timeframe:** NIFTY 50 index (spot level), daily (1d) candles only. No
  options/futures overlay, no leverage, no transaction costs (per scope — this is a
  signal-quality study).
- **Entry:** a signal fires on day *t* using only data available up to and including day
  *t*'s close. `entry_price = close[t]`.
- **"Works" definition (the target):** looking forward at daily HIGHs over the next 42
  trading days (*t+1* .. *t+42*, never including day *t*'s own high — that would be
  same-bar lookahead), does price ever touch `entry_price × 1.01` (+1%)? That is the pass
  bar. +2%/+3% are tracked separately as "how far did it stretch."
- **Drawdown tolerance:** a signal that first drops and later recovers to hit +1% within
  the window still counts as a HIT. For every signal, `max_adverse_dip_pct` = the worst
  intraday-high-relative drawdown observed from day *t+1* through either (a) the day the
  +1% target was hit, or (b) window expiry if it never hit.
- **Sizing:** none (signal-quality study, not a P&L study).
- **Assumption made (ambiguity in the brief):** entry price = the signal day's own close
  (the value that confirms the setup), not next-day's open. This is standard for a
  signal-quality study; a real trader using next-day-open execution would see materially
  the same numbers since NIFTY's typical overnight gap is a small fraction of the +1%
  target — this doesn't change the verdict, just flagged per the brief's request to state
  assumptions rather than stall.

## Data

- **Source:** SQLite (`drishti.db`), no yfinance fallback needed — DB already covers
  2007-09-17 through 2026-07-27 (4,625 unique trading days after dedup), comparable in
  depth to the prior ad hoc study's 2007–2026 window and spanning the 2008 GFC, 2011
  correction, 2013 taper tantrum, 2015–16 China scare, 2018 NBFC crisis, 2020 COVID crash,
  2022 correction, and 2024–26 volatility.
- **Data-quality finding (fixed before use):** `candles_1d` stores almost every trading day
  from 2007 through early 2026 **twice**, under two different UTC timestamp encodings
  (`<prev-day> 18:30:00` and `<same-day> 00:00:00`, both of which map to the same IST
  calendar date). Checked: 9,174 of 9,212 raw rows for NIFTY50 belong to such a pair, and
  in every single pair the OHLCV values are byte-identical — this looks like a historical
  double-bootstrap artifact, not real duplicate market data, and the last ~38 trading days
  (roughly since the ingestion path was fixed) only have one row each. Deduped by keeping
  one row per IST calendar date before computing anything; final dataset has zero duplicate
  dates, zero OHLC integrity violations (checked high ≥ max(open,close,low) and low ≤
  min(open,close,high) for every row), zero NaNs in raw OHLCV. ~2,668 rows have `volume=0`
  (index data — NIFTY 50 has no traded volume of its own, expected and harmless).
- **Window:** 2007-09-17 → 2026-07-27, 4,625 trading days, 15 candidate signal families
  tested, producing between 4 and 312 signals each (see table below).

## Core metrics — all 15 signals tested (full-history, complete 42-day windows only)

| Signal | n | Hit +1% | Hit +2% | Hit +3% | Avg max adverse dip | Median days to +1% |
|---|---|---|---|---|---|---|
| **A1 — Supertrend(10,3) bear→bull flip** | **75** | **93.3%** | 90.7% | 76.0% | 2.59% | 2 |
| B1 — A1 + EMA200-flat-or-rising regime filter | 46 | 93.5% | 89.1% | 69.6% | 2.65% | 3 |
| A2 — RSI(14) crosses below 25 | 16 | 93.8% | 93.8% | 81.2% | 4.09% | 1 |
| B2 — A2 + regime filter | 5 | 100.0% | 100.0% | 80.0% | 0.98% | 1 |
| **A3 — Bollinger(20,2) lower-band re-entry** | **109** | **90.8%** | 81.7% | 72.5% | 2.76% | 2 |
| A4 — EMA50 pullback in uptrend, RSI<45 | 312 | 86.5% | 73.1% | 60.3% | 2.44% | 3 |
| A5 — MACD bull cross + RSI<40 | 4 | 100.0% | 100.0% | 75.0% | 3.00% | 4 |
| A6 — Supertrend flip + RSI recross >30 (±3d, no-lookahead fixed) | 4 | 100.0% | 100.0% | 50.0% | 4.27% | 6 |
| B3 — Bollinger-bandwidth squeeze → basis breakout | 104 | 87.5% | 76.0% | 68.3% | 2.20% | 3 |
| B4 — ≥4 consecutive down days + reversal candle | 17 | 88.2% | 82.4% | 70.6% | 4.04% | 1 |
| B5 — Price/RSI bullish divergence (no-lookahead fixed) | 22 | 100.0% | 90.9% | 77.3% | 1.86% | 4 |
| B6 — Z-score(close vs EMA50) ≤ -2 | 57 | 87.7% | 84.2% | 82.5% | 4.86% | 2 |
| B7 — B6 + regime filter | 30 | 86.7% | 83.3% | 83.3% | 4.07% | 1 |
| B8 — B4 + regime filter | 6 | 66.7% | 50.0% | 33.3% | 8.20% | 2 |
| B9 — B5 + regime filter | 7 | 100.0% | 100.0% | 85.7% | 2.54% | 4 |

**Small-sample flag (n<30):** A2, B2, A5, A6, B4, B5, B8, B9 all have fewer than 30 signals
over 19 years. Several show 100% hit rates — **this is statistically meaningless at this
sample size**, not a headline result. B2 (n=5), A5 (n=4), A6 (n=4) in particular should not
be trusted or acted on; a single future miss would swing their "hit rate" by 20–25
percentage points. B5/B9 (divergence, n=22/7) are the most interesting of the small-sample
group — a real, mechanistically sensible signal (price/RSI divergence with a genuine
no-lookahead confirmation lag) that never disqualified an entry outright in the tested
history, but 22 trades is not enough to certify a 100% hit rate; treat as "promising,
unproven," not investable on its own.

**n≥25 cutoff used for statistical meaningfulness** in everything downstream (walk-forward,
bootstrap, parameter sweep): only A1, A3, A4, B1, B3, B6, B7 clear this bar. Of those, A1
and A3 have the best combination of hit rate and honest sample size and were carried
through the full validation gauntlet as the top two candidates. B3 (squeeze breakout, the
volatility-contraction idea from the brief) is included as a third data point because it's
the most interesting of the "new/inventive" family, even though it comes in below the 90%
bar and degrades out-of-sample (see below).

## Cost assumptions used

None — explicitly out of scope per the brief (signal-quality study, not a P&L study). No
brokerage/STT/GST/slippage/execution-lag modeling was applied; there is therefore no
"cost-doubled" stress test in this report. As a substitute stress test (see Validation
below), the definition itself was stress-tested: requiring the daily **close** (not just an
intraday high wick) to clear +1% is a stricter, more execution-realistic proxy, and is
reported as a sensitivity check.

## Validation results

### Walk-forward (train = pre-2018, test = 2018 onward — includes COVID crash, 2022 correction)

| Signal | Train n | Train hit1% | Test n | Test hit1% | Gap |
|---|---|---|---|---|---|
| A1_ST_flip | 41 | 95.1% | 34 | 91.2% | -3.9pp |
| A3_BB_reentry | 61 | 90.2% | 48 | 91.7% | **+1.5pp** |
| B3_BBsqueeze_breakout | 57 | 91.2% | 47 | 83.0% | **-8.2pp** |

A1 and A3 both hold up out-of-sample — A3 actually does slightly *better* out-of-sample,
which is a good sign against overfitting (no evidence the in-sample number was inflated by
fitting to the earlier, calmer regime). B3 degrades meaningfully out-of-sample (91.2% →
83.0%), which combined with its below-90% full-sample number is why it's reported as the
weaker of the three rather than promoted alongside A1/A3.

### Regime-block consistency (non-overlapping ~5-year blocks, a second cut at walk-forward)

| Signal | 2007–11 | 2012–16 | 2017–21 | 2022–26 |
|---|---|---|---|---|
| A1_ST_flip | n=15, 93.3% | n=23, 95.7% | n=16, 93.8% | n=21, 90.5% |
| A3_BB_reentry | n=30, 90.0% | n=28, 89.3% | n=26, 88.5% | n=25, 96.0% |

Both signals stay in a tight 88–96% band across every 5-year block, each of which contains
at least one genuine bear/correction episode (2008 GFC aftermath + 2011 correction; 2013
taper tantrum + 2015–16 China scare; 2018 NBFC crisis + 2020 COVID; 2022 correction). This
is a real cross-regime plateau, not a result driven by one lucky bull-market slice.

### Monte Carlo / bootstrap (5,000 resamples, hit-rate CI)

| Signal | n | Point hit1% | 90% bootstrap CI |
|---|---|---|---|
| A1_ST_flip | 75 | 93.3% | **[88.0%, 97.3%]** |
| A3_BB_reentry | 109 | 90.8% | **[86.2%, 95.4%]** |
| B3_BBsqueeze_breakout | 104 | 87.5% | [81.7%, 92.3%] |

Caveat stated plainly: bootstrap resampling with replacement treats each signal as
independent, which understates true uncertainty because these signals cluster in time
(several ST flips or BB re-entries can fire within the same choppy month, driven by the
same underlying price action) — so read these CIs as a **lower bound** on the real
uncertainty, not an exact interval. Even so: neither A1 nor A3's CI lower bound clears 90%,
which is the honest reason the verdict above is "close to, not confidently above" the
user's bar.

### Parameter-sensitivity sweep

**Supertrend (period, multiplier) — is A1 sitting on a plateau or a cliff edge?**

| period \ mult | 2.5 | 3.0 | 3.5 |
|---|---|---|---|
| 8  | n=101, 95.0% | n=75, 93.3% | n=62, 95.2% |
| 10 | n=103, 94.2% | n=75, **93.3%** (base) | n=62, 91.9% |
| 12 | n=102, 94.1% | n=76, 93.4% | n=61, 91.8% |

Every one of the 9 combinations (period ±20%, multiplier ±17%) lands between 91.8% and
95.2% hit rate. This is a genuine robustness **plateau** — the signal isn't fragile to the
exact Supertrend parameterization, which is a strong mark in its favor against the
overfitting concern.

**Bollinger (length, std) — same check for A3:**

| length \ std | 1.8 | 2.0 | 2.2 |
|---|---|---|---|
| 15 | n=174, 90.2% | n=123, 91.1% | n=75, 88.0% |
| 20 | n=147, 92.5% | n=109, **90.8%** (base) | n=77, 89.6% |
| 25 | n=154, 92.2% | n=107, 92.5% | n=76, 92.1% |

Also a plateau (88.0–92.5% across the full grid) rather than a cliff — A3 isn't a
one-exact-parameter curve-fit either.

### Bias checks

- **Lookahead bias:** actively found and fixed during development, not just checked
  off — two of the 15 signal families (A6 confluence, B5/B9 divergence) originally defined
  their "signal day" using information not yet knowable on that day (a ±3-day-forward RSI
  recross for A6; a centered rolling-window local minimum for B5/B9, which needs the next 5
  days of closes to confirm). Both were corrected to fire on the first day the pattern is
  actually confirmable, using that later day's close as the entry price. All other 12
  signals use only backward-looking rolling/recursive indicators (EMA, RSI, ATR,
  Supertrend, Bollinger, z-scores, candle patterns) computed strictly through day *t* — no
  further lookahead found on inspection.
- **Survivorship bias:** not applicable — single index (NIFTY 50), not a basket or
  membership-list backtest.
- **Overfitting:** low risk for A1/A3. Both use single, standard, widely-used
  parameterizations (Supertrend(10,3), Bollinger(20,2)) that were not tuned on this
  dataset, sit on a demonstrated ±20% parameter plateau (not a cliff), and have a
  reasonable trades-per-free-parameter ratio (1–2 free parameters, 75–109 trades). The
  small-sample signals (n<30) carry real overfitting/false-positive risk simply from
  sample size, independent of parameter count — flagged above.
- **Definition-sensitivity stress test** (substitute for cost-doubling, since costs are
  out of scope): re-running A1 and A3 requiring the daily **close** (not the high) to clear
  +1% within the window is meaningfully stricter, since it requires the market to hold the
  gain into a close rather than just wick through it intraday. This was checked directly by
  inspecting the per-signal table's `days_to_1pct` and the miss list — the vast majority of
  hits arrive with `max_adverse_dip_pct` at or near 0% and close within 1–4 median trading
  days of entry, meaning the touches are not razor-thin one-day wicks; the signal is not
  fragile to this stricter proxy. (This is a qualitative read of the existing table, not a
  separately re-run backtest — noted as a scope limitation of this stress test.)

## Where it fails

Both A1 and A3 fail in exactly the pattern the prior ad hoc study flagged, and a
regime filter (EMA200 flat-or-rising over the last 20 trading days) does **not** reliably
fix it — this was tested explicitly (B1) and only removed 2 of A1's 5 misses while cutting
the total sample by 39% and *lowering* the +3% hit rate from 76.0% to 69.6%. Checking the
actual EMA200 slope/price-vs-EMA200 readings on each of A1's 5 misses:

| Miss date | Close vs EMA200 | EMA200 20d-slope | Reading |
|---|---|---|---|
| 2011-01-03 | above | +1.45% (rising) | regime looked fine — filter would NOT catch this |
| 2015-12-28 | below | -0.77% (falling) | regime filter *would* catch this one |
| 2020-02-06 (pre-COVID) | above | +0.91% (rising) | regime looked fine — exogenous shock, unforecastable by trend metrics |
| 2025-02-04 | above | -0.33% (near-flat) | borderline — filter marginally catches this |
| 2026-02-04 | above | +0.31% (rising) | regime looked fine — filter would NOT catch this |

3 of 5 misses occurred in a macro backdrop that looked completely healthy by trend metrics
right up until the day before the drawdown — most notably the pre-COVID Feb 2020 miss
(38.12% max adverse dip, by far the worst in either table), where price was above a rising
EMA200 the day the signal fired. No amount of trend-based regime filtering can be expected
to catch a signal that fires the session before an exogenous shock. This is the honest
structural ceiling on both signals: they are good at "bounce from an oversold/technical
low," not at "predict whether a bounce will hold," and roughly 1-in-14 (A1) or 1-in-11 (A3)
times it won't.

## Currently live / actionable setup (as of latest candle, 2026-07-27)

No new entry fired on the most recent candle for any of the 15 tested signal families.
The most recent A1 and A3 signals are still inside their open 42-day forward windows:

- **A1 (Supertrend flip):** last fired 2026-06-17 at close 24,085.70. 27 trading days
  elapsed so far; the +1% target (≥24,326.56) was already touched (max high +1.85% on the
  way), so this entry is already a resolved HIT within the historical stats even though its
  window hasn't formally closed. Latest close (23,995.95) is back to -0.37% from entry.
- **A3 (BB re-entry):** last fired 2026-06-09 at close 23,242.10. 33 trading days elapsed;
  target hit long ago (max high +5.55%). Latest close is +3.24% from entry.
- **B3 (squeeze breakout, for reference):** last fired 2026-07-17 at close 24,334.30, only
  6 trading days ago, currently unresolved and **underwater** at -1.39% from entry (max
  adverse dip so far -2.99%), 36 trading days still remaining in its window.

Nothing is actionable as a *fresh* entry today under either A1 or A3's exact trigger rule
(neither an ST bear→bull flip nor a BB lower-band re-entry occurred on 2026-07-27; RSI is
49.5 and Supertrend has been in bull mode since well before this candle).

## Full per-signal table — Candidate 1: A1 — Supertrend(10,3) bear→bull flip (n=75)

Entry = close on the flip day. Reason column shows the actual Supertrend line value that
day. Outcome shows the highest target level reached and the day count to reach it (day 1 =
next trading day), or, for misses, the best forward gain achieved anywhere in the 42-day
window. Max adverse dip = worst drawdown from entry observed before the +1% hit (or before
window expiry if it never hit).

| Date | Entry | Reason (indicator values on signal day) | Outcome (days to reach) | Max adverse dip before hit/expiry |
|---|---|---|---|---|
| 2007-10-29 | 5905.9 | Supertrend(10,3) flips bear->bull, ST=5180.6 | HIT +3% (d30) | 1.22% |
| 2008-04-25 | 5111.7 | Supertrend(10,3) flips bear->bull, ST=4703.3 | HIT +3% (d4) | 0.64% |
| 2008-07-23 | 4476.8 | Supertrend(10,3) flips bear->bull, ST=3897.9 | HIT +3% (d10) | 2.03% |
| 2008-11-04 | 3142.1 | Supertrend(10,3) flips bear->bull, ST=2413.0 | HIT +3% (d1) | 5.45% |
| 2009-03-23 | 2939.9 | Supertrend(10,3) flips bear->bull, ST=2638.7 | HIT +3% (d3) | 0.86% |
| 2009-07-17 | 4374.9 | Supertrend(10,3) flips bear->bull, ST=3908.8 | HIT +3% (d1) | 0.00% |
| 2009-11-11 | 5003.9 | Supertrend(10,3) flips bear->bull, ST=4607.5 | HIT +3% (d15) | 1.58% |
| 2010-03-03 | 5088.1 | Supertrend(10,3) flips bear->bull, ST=4805.8 | HIT +3% (d10) | 0.77% |
| 2010-06-14 | 5197.7 | Supertrend(10,3) flips bear->bull, ST=4890.1 | HIT +3% (d5) | 0.51% |
| 2011-01-03 | 6157.6 | Supertrend(10,3) flips bear->bull, ST=5952.7 | MISS (best +0.38%) | 15.91% |
| 2011-03-25 | 5654.2 | Supertrend(10,3) flips bear->bull, ST=5322.3 | HIT +3% (d4) | 0.20% |
| 2011-06-27 | 5526.6 | Supertrend(10,3) flips bear->bull, ST=5236.9 | HIT +3% (d4) | 0.55% |
| 2011-09-08 | 5153.2 | Supertrend(10,3) flips bear->bull, ST=4805.5 | HIT +3% (d33) | 8.25% |
| 2011-10-14 | 5132.3 | Supertrend(10,3) flips bear->bull, ST=4769.8 | HIT +3% (d8) | 2.36% |
| 2011-12-02 | 5050.1 | Supertrend(10,3) flips bear->bull, ST=4647.6 | HIT +3% (d36) | 10.28% |
| 2012-01-17 | 4967.3 | Supertrend(10,3) flips bear->bull, ST=4689.3 | HIT +3% (d5) | 0.73% |
| 2012-06-07 | 5049.6 | Supertrend(10,3) flips bear->bull, ST=4795.5 | HIT +3% (d16) | 1.09% |
| 2012-08-06 | 5282.6 | Supertrend(10,3) flips bear->bull, ST=5081.0 | HIT +3% (d11) | 0.02% |
| 2012-09-12 | 5431.0 | Supertrend(10,3) flips bear->bull, ST=5241.6 | HIT +3% (d3) | 0.17% |
| 2012-11-29 | 5825.0 | Supertrend(10,3) flips bear->bull, ST=5587.9 | HIT +3% (d22) | 0.00% |
| 2013-03-08 | 5945.7 | Supertrend(10,3) flips bear->bull, ST=5705.5 | HIT +2% (d38) | 7.88% |
| 2013-04-18 | 5783.1 | Supertrend(10,3) flips bear->bull, ST=5477.2 | HIT +3% (d6) | 0.00% |
| 2013-07-01 | 5898.9 | Supertrend(10,3) flips bear->bull, ST=5577.2 | HIT +3% (d16) | 2.35% |
| 2013-09-06 | 5680.4 | Supertrend(10,3) flips bear->bull, ST=5193.8 | HIT +3% (d1) | 0.00% |
| 2013-12-06 | 6259.9 | Supertrend(10,3) flips bear->bull, ST=6021.0 | HIT +2% (d1) | 0.00% |
| 2014-02-25 | 6200.1 | Supertrend(10,3) flips bear->bull, ST=6007.9 | HIT +3% (d6) | 0.00% |
| 2014-07-23 | 7795.8 | Supertrend(10,3) flips bear->bull, ST=7504.7 | HIT +3% (d25) | 3.28% |
| 2014-10-29 | 8090.4 | Supertrend(10,3) flips bear->bull, ST=7808.1 | HIT +3% (d3) | 0.06% |
| 2014-12-22 | 8324.0 | Supertrend(10,3) flips bear->bull, ST=7977.8 | HIT +3% (d19) | 2.11% |
| 2015-01-15 | 8494.1 | Supertrend(10,3) flips bear->bull, ST=8095.0 | HIT +3% (d5) | 0.49% |
| 2015-03-02 | 8956.8 | Supertrend(10,3) flips bear->bull, ST=8584.2 | HIT +1% (d2) | 0.70% |
| 2015-04-08 | 8714.4 | Supertrend(10,3) flips bear->bull, ST=8368.3 | HIT +1% (d3) | 0.37% |
| 2015-05-22 | 8459.0 | Supertrend(10,3) flips bear->bull, ST=8117.6 | HIT +2% (d40) | 6.13% |
| 2015-06-22 | 8353.1 | Supertrend(10,3) flips bear->bull, ST=7988.5 | HIT +3% (d18) | 1.88% |
| 2015-10-05 | 8119.3 | Supertrend(10,3) flips bear->bull, ST=7644.4 | HIT +2% (d10) | 0.28% |
| 2015-12-28 | 7925.1 | Supertrend(10,3) flips bear->bull, ST=7647.3 | MISS (best +0.38%) | 13.33% |
| 2016-03-02 | 7368.9 | Supertrend(10,3) flips bear->bull, ST=6909.1 | HIT +3% (d11) | 0.00% |
| 2016-12-30 | 8185.8 | Supertrend(10,3) flips bear->bull, ST=7889.4 | HIT +3% (d10) | 0.64% |
| 2017-09-11 | 10006.0 | Supertrend(10,3) flips bear->bull, ST=9751.3 | HIT +3% (d30) | 0.00% |
| 2017-10-12 | 10096.4 | Supertrend(10,3) flips bear->bull, ST=9759.9 | HIT +3% (d13) | 0.00% |
| 2017-12-15 | 10333.2 | Supertrend(10,3) flips bear->bull, ST=10043.5 | HIT +3% (d15) | 2.50% |
| 2018-04-09 | 10379.4 | Supertrend(10,3) flips bear->bull, ST=10010.0 | HIT +3% (d14) | 0.23% |
| 2018-06-07 | 10768.4 | Supertrend(10,3) flips bear->bull, ST=10446.5 | HIT +3% (d32) | 0.55% |
| 2018-11-15 | 10616.7 | Supertrend(10,3) flips bear->bull, ST=10167.2 | HIT +3% (d11) | 0.00% |
| 2018-12-17 | 10888.4 | Supertrend(10,3) flips bear->bull, ST=10480.9 | HIT +2% (d36) | 3.25% |
| 2019-03-06 | 11053.0 | Supertrend(10,3) flips bear->bull, ST=10678.6 | HIT +3% (d7) | 0.40% |
| 2019-05-20 | 11828.2 | Supertrend(10,3) flips bear->bull, ST=11217.9 | HIT +2% (d10) | 1.81% |
| 2019-09-20 | 11274.2 | Supertrend(10,3) flips bear->bull, ST=10447.4 | HIT +3% (d1) | 0.00% |
| 2020-02-06 | 12138.0 | Supertrend(10,3) flips bear->bull, ST=11676.3 | **MISS (best +0.90%)** | **38.12%** |
| 2020-04-30 | 9859.9 | Supertrend(10,3) flips bear->bull, ST=8879.8 | HIT +3% (d22) | 10.68% |
| 2020-06-01 | 9826.1 | Supertrend(10,3) flips bear->bull, ST=9072.0 | HIT +3% (d2) | 0.02% |
| 2020-10-05 | 11503.4 | Supertrend(10,3) flips bear->bull, ST=10982.5 | HIT +3% (d3) | 0.00% |
| 2021-02-02 | 14647.9 | Supertrend(10,3) flips bear->bull, ST=13702.2 | HIT +3% (d4) | 0.50% |
| 2021-05-21 | 15175.3 | Supertrend(10,3) flips bear->bull, ST=14460.7 | HIT +3% (d7) | 0.20% |
| 2022-01-03 | 17625.7 | Supertrend(10,3) flips bear->bull, ST=16816.3 | HIT +3% (d7) | 0.18% |
| 2022-03-16 | 16975.3 | Supertrend(10,3) flips bear->bull, ST=15839.9 | HIT +3% (d9) | 0.00% |
| 2022-07-07 | 16132.9 | Supertrend(10,3) flips bear->bull, ST=15417.8 | HIT +3% (d10) | 1.70% |
| 2022-09-12 | 17936.3 | Supertrend(10,3) flips bear->bull, ST=17331.5 | HIT +2% (d39) | 6.63% |
| 2022-10-24 | 17730.8 | Supertrend(10,3) flips bear->bull, ST=17090.8 | HIT +3% (d10) | 0.53% |
| 2023-04-06 | 17599.2 | Supertrend(10,3) flips bear->bull, ST=17010.5 | HIT +3% (d15) | 0.01% |
| 2023-09-07 | 19727.0 | Supertrend(10,3) flips bear->bull, ST=19220.6 | HIT +2% (d5) | 0.00% |
| 2023-11-15 | 19675.5 | Supertrend(10,3) flips bear->bull, ST=19174.8 | HIT +3% (d11) | 0.25% |
| 2024-02-19 | 22122.2 | Supertrend(10,3) flips bear->bull, ST=21386.6 | HIT +2% (d30) | 1.18% |
| 2024-04-08 | 22666.3 | Supertrend(10,3) flips bear->bull, ST=21972.0 | HIT +3% (d41) | 3.92% |
| 2024-05-23 | 22967.7 | Supertrend(10,3) flips bear->bull, ST=22055.8 | HIT +3% (d18) | 2.40% |
| 2024-06-25 | 23721.3 | Supertrend(10,3) flips bear->bull, ST=22799.7 | HIT +3% (d10) | 0.21% |
| 2024-08-26 | 25010.6 | Supertrend(10,3) flips bear->bull, ST=24299.8 | HIT +3% (d19) | 0.18% |
| 2024-11-27 | 24274.9 | Supertrend(10,3) flips bear->bull, ST=23308.3 | HIT +2% (d6) | 1.65% |
| 2025-02-04 | 23739.2 | Supertrend(10,3) flips bear->bull, ST=22759.0 | MISS (best +0.55%) | 8.41% |
| 2025-03-18 | 22834.3 | Supertrend(10,3) flips bear->bull, ST=21991.0 | HIT +3% (d4) | 0.12% |
| 2025-04-15 | 23328.5 | Supertrend(10,3) flips bear->bull, ST=22119.4 | HIT +3% (d3) | 0.24% |
| 2025-09-12 | 25114.0 | Supertrend(10,3) flips bear->bull, ST=24552.5 | HIT +3% (d25) | 0.26% |
| 2025-10-09 | 25181.8 | Supertrend(10,3) flips bear->bull, ST=24573.8 | HIT +3% (d9) | 0.48% |
| 2026-02-04 | 25776.0 | Supertrend(10,3) flips bear->bull, ST=24564.5 | MISS (best +0.91%) | 13.94% |
| 2026-04-08 | 23997.3 | Supertrend(10,3) flips bear->bull, ST=22336.2 | HIT +2% (d7) | 1.84% |

70/75 = 93.3% HIT +1%. 5 misses: 2011-01-03, 2015-12-28, 2020-02-06 (worst, pre-COVID),
2025-02-04, 2026-02-04.

## Full per-signal table — Candidate 2: A3 — Bollinger(20,2) lower-band re-entry (n=109)

Entry = close on the re-entry day (the day close moves back above the BB(20,2) lower band
after having closed below it). Reason column shows the actual lower-band value that day.

| Date | Entry | Reason (indicator values on signal day) | Outcome (days to reach) | Max adverse dip before hit/expiry |
|---|---|---|---|---|
| 2008-01-23 | 5203.4 | close 5203.4 re-enters above BB(20,2) lower band 5163.9 | HIT +3% (d2) | 3.99% |
| 2008-03-14 | 4745.8 | close 4745.8 re-enters above BB(20,2) lower band 4602.5 | HIT +3% (d5) | 5.84% |
| 2008-03-18 | 4533.0 | close 4533.0 re-enters above BB(20,2) lower band 4453.5 | HIT +3% (d1) | 0.00% |
| 2008-05-27 | 4859.8 | close 4859.8 re-enters above BB(20,2) lower band 4857.3 | HIT +2% (d2) | 0.50% |
| 2008-06-03 | 4715.9 | close 4715.9 re-enters above BB(20,2) lower band 4712.2 | MISS (best +0.64%) | 19.63% |
| 2008-06-05 | 4676.9 | close 4677.0 re-enters above BB(20,2) lower band 4609.4 | HIT +1% (d1) | 1.34% |
| 2008-06-10 | 4449.8 | close 4449.8 re-enters above BB(20,2) lower band 4432.5 | HIT +3% (d4) | 0.00% |
| 2008-06-25 | 4252.6 | close 4252.6 re-enters above BB(20,2) lower band 4181.1 | HIT +3% (d20) | 0.53% |
| 2008-07-02 | 4093.3 | close 4093.4 re-enters above BB(20,2) lower band 3934.5 | HIT +3% (d14) | 5.34% |
| 2008-09-18 | 4038.2 | close 4038.1 re-enters above BB(20,2) lower band 3997.7 | HIT +3% (d1) | 0.00% |
| 2008-10-07 | 3606.6 | close 3606.6 re-enters above BB(20,2) lower band 3600.3 | HIT +1% (d4) | 11.30% |
| 2008-10-13 | 3490.7 | close 3490.7 re-enters above BB(20,2) lower band 3357.7 | HIT +3% (d1) | 0.00% |
| 2008-10-29 | 2697.1 | close 2697.1 re-enters above BB(20,2) lower band 2469.6 | HIT +3% (d1) | 0.03% |
| 2009-01-14 | 2835.3 | close 2835.3 re-enters above BB(20,2) lower band 2746.8 | HIT +3% (d17) | 4.71% |
| 2009-03-04 | 2645.2 | close 2645.2 re-enters above BB(20,2) lower band 2610.0 | HIT +3% (d5) | 4.00% |
| 2009-07-14 | 4111.4 | close 4111.4 re-enters above BB(20,2) lower band 3975.7 | HIT +3% (d1) | 0.00% |
| 2009-11-04 | 4710.8 | close 4710.8 re-enters above BB(20,2) lower band 4626.4 | HIT +3% (d3) | 2.13% |
| 2010-01-29 | 4882.1 | close 4882.0 re-enters above BB(20,2) lower band 4865.0 | HIT +3% (d20) | 1.39% |
| 2010-05-10 | 5193.6 | close 5193.6 re-enters above BB(20,2) lower band 5064.3 | HIT +3% (d30) | 7.84% |
| 2010-05-20 | 4947.6 | close 4947.6 re-enters above BB(20,2) lower band 4921.6 | HIT +3% (d7) | 2.13% |
| 2010-05-26 | 4917.4 | close 4917.4 re-enters above BB(20,2) lower band 4815.9 | HIT +3% (d2) | 0.40% |
| 2011-01-12 | 5863.2 | close 5863.2 re-enters above BB(20,2) lower band 5760.7 | MISS (best -0.09%) | 11.69% |
| 2011-01-17 | 5654.8 | close 5654.8 re-enters above BB(20,2) lower band 5632.1 | HIT +2% (d6) | 0.00% |
| 2011-05-06 | 5551.4 | close 5551.5 re-enters above BB(20,2) lower band 5492.9 | HIT +2% (d39) | 6.40% |
| 2011-06-21 | 5275.9 | close 5275.9 re-enters above BB(20,2) lower band 5271.7 | HIT +3% (d3) | 0.45% |
| 2011-07-29 | 5482.0 | close 5482.0 re-enters above BB(20,2) lower band 5471.1 | HIT +1% (d1) | 0.00% |
| 2011-08-10 | 5161.0 | close 5161.0 re-enters above BB(20,2) lower band 5094.1 | MISS (best +0.65%) | 8.54% |
| 2011-11-18 | 4905.8 | close 4905.8 re-enters above BB(20,2) lower band 4900.2 | HIT +3% (d9) | 5.40% |
| 2011-11-22 | 4812.4 | close 4812.4 re-enters above BB(20,2) lower band 4789.5 | HIT +3% (d6) | 3.56% |
| 2011-11-25 | 4710.1 | close 4710.0 re-enters above BB(20,2) lower band 4665.6 | HIT +3% (d1) | 0.00% |
| 2012-05-07 | 5114.1 | close 5114.1 re-enters above BB(20,2) lower band 5107.5 | HIT +3% (d38) | 6.72% |
| 2012-05-14 | 4907.8 | close 4907.8 re-enters above BB(20,2) lower band 4890.0 | HIT +3% (d17) | 2.42% |
| 2012-07-27 | 5099.9 | close 5099.9 re-enters above BB(20,2) lower band 5050.5 | HIT +3% (d6) | 0.00% |
| 2012-10-31 | 5619.7 | close 5619.7 re-enters above BB(20,2) lower band 5602.6 | HIT +3% (d18) | 0.32% |
| 2012-11-19 | 5571.4 | close 5571.4 re-enters above BB(20,2) lower band 5567.9 | HIT +3% (d7) | 0.41% |
| 2013-02-12 | 5922.5 | close 5922.5 re-enters above BB(20,2) lower band 5888.6 | MISS (best +0.82%) | 7.52% |
| 2013-02-27 | 5796.9 | close 5796.9 re-enters above BB(20,2) lower band 5778.2 | HIT +3% (d8) | 2.30% |
| 2013-03-01 | 5719.7 | close 5719.7 re-enters above BB(20,2) lower band 5717.6 | HIT +3% (d5) | 0.98% |
| 2013-06-14 | 5808.4 | close 5808.4 re-enters above BB(20,2) lower band 5692.4 | HIT +3% (d20) | 4.17% |
| 2013-08-08 | 5565.6 | close 5565.6 re-enters above BB(20,2) lower band 5482.1 | HIT +3% (d3) | 0.15% |
| 2014-02-04 | 6000.9 | close 6000.9 re-enters above BB(20,2) lower band 5980.6 | HIT +3% (d13) | 0.65% |
| 2014-10-17 | 7779.7 | close 7779.7 re-enters above BB(20,2) lower band 7729.8 | HIT +3% (d4) | 0.00% |
| 2014-12-18 | 8159.3 | close 8159.3 re-enters above BB(20,2) lower band 8047.9 | HIT +3% (d9) | 0.00% |
| 2015-03-27 | 8341.4 | close 8341.4 re-enters above BB(20,2) lower band 8320.7 | HIT +3% (d3) | 0.00% |
| 2015-08-27 | 7948.9 | close 7949.0 re-enters above BB(20,2) lower band 7818.3 | HIT +3% (d26) | 0.00% |
| 2015-11-06 | 7954.3 | close 7954.3 re-enters above BB(20,2) lower band 7940.6 | MISS (best +0.31%) | 5.86% |
| 2015-11-16 | 7806.6 | close 7806.6 re-enters above BB(20,2) lower band 7736.6 | HIT +2% (d9) | 1.04% |
| 2015-12-10 | 7683.3 | close 7683.3 re-enters above BB(20,2) lower band 7633.9 | HIT +3% (d11) | 1.72% |
| 2016-01-19 | 7435.1 | close 7435.1 re-enters above BB(20,2) lower band 7316.4 | HIT +3% (d42) | 2.60% |
| 2016-02-15 | 7162.9 | close 7163.0 re-enters above BB(20,2) lower band 7024.6 | HIT +3% (d12) | 2.82% |
| 2016-09-30 | 8611.1 | close 8611.2 re-enters above BB(20,2) lower band 8590.2 | HIT +2% (d2) | 0.00% |
| 2016-10-14 | 8583.4 | close 8583.4 re-enters above BB(20,2) lower band 8561.6 | HIT +1% (d2) | 0.90% |
| 2016-10-18 | 8677.9 | close 8677.9 re-enters above BB(20,2) lower band 8524.1 | MISS (best +0.68%) | 8.78% |
| 2016-11-07 | 8497.0 | close 8497.0 re-enters above BB(20,2) lower band 8443.0 | HIT +1% (d3) | 5.82% |
| 2016-11-18 | 8074.1 | close 8074.1 re-enters above BB(20,2) lower band 8030.4 | HIT +3% (d38) | 1.95% |
| 2016-11-22 | 8002.3 | close 8002.3 re-enters above BB(20,2) lower band 7890.4 | HIT +3% (d7) | 0.62% |
| 2016-12-23 | 7985.8 | close 7985.8 re-enters above BB(20,2) lower band 7984.2 | HIT +3% (d9) | 1.15% |
| 2016-12-27 | 8032.9 | close 8032.9 re-enters above BB(20,2) lower band 7932.3 | HIT +3% (d7) | 0.15% |
| 2017-06-29 | 9504.1 | close 9504.1 re-enters above BB(20,2) lower band 9501.2 | HIT +3% (d8) | 0.58% |
| 2017-08-14 | 9794.1 | close 9794.2 re-enters above BB(20,2) lower band 9736.6 | HIT +3% (d19) | 0.21% |
| 2017-09-28 | 9769.0 | close 9769.0 re-enters above BB(20,2) lower band 9740.1 | HIT +3% (d8) | 0.00% |
| 2018-03-08 | 10242.6 | close 10242.7 re-enters above BB(20,2) lower band 10197.6 | HIT +3% (d26) | 0.30% |
| 2018-03-20 | 10124.4 | close 10124.3 re-enters above BB(20,2) lower band 10065.8 | HIT +3% (d14) | 0.00% |
| 2018-05-22 | 10536.7 | close 10536.7 re-enters above BB(20,2) lower band 10508.8 | HIT +3% (d15) | 1.13% |
| 2018-05-24 | 10513.9 | close 10513.8 re-enters above BB(20,2) lower band 10457.6 | HIT +3% (d12) | 0.00% |
| 2018-09-12 | 11369.9 | close 11369.9 re-enters above BB(20,2) lower band 11299.5 | HIT +1% (d1) | 0.00% |
| 2018-09-25 | 11067.5 | close 11067.5 re-enters above BB(20,2) lower band 10997.0 | MISS (best +0.71%) | 9.60% |
| 2018-10-09 | 10301.0 | close 10301.0 re-enters above BB(20,2) lower band 10255.3 | HIT +3% (d6) | 0.00% |
| 2019-05-14 | 11222.0 | close 11222.0 re-enters above BB(20,2) lower band 11171.1 | HIT +3% (d4) | 0.76% |
| 2019-07-11 | 11582.9 | close 11582.9 re-enters above BB(20,2) lower band 11491.5 | HIT +1% (d4) | 0.44% |
| 2019-08-23 | 10829.4 | close 10829.3 re-enters above BB(20,2) lower band 10735.6 | HIT +3% (d18) | 0.67% |
| 2020-02-04 | 11979.6 | close 11979.7 re-enters above BB(20,2) lower band 11824.2 | HIT +2% (d6) | 0.22% |
| 2020-03-03 | 11303.3 | close 11303.3 re-enters above BB(20,2) lower band 11224.7 | MISS (best +0.76%) | 33.55% |
| 2020-03-13 | 9955.2 | close 9955.2 re-enters above BB(20,2) lower band 9847.5 | MISS (best -0.66%) | 24.55% |
| 2020-03-19 | 8263.5 | close 8263.5 re-enters above BB(20,2) lower band 8261.3 | HIT +3% (d1) | 1.03% |
| 2020-03-24 | 7801.1 | close 7801.0 re-enters above BB(20,2) lower band 7300.4 | HIT +3% (d1) | 1.11% |
| 2020-05-19 | 8879.1 | close 8879.1 re-enters above BB(20,2) lower band 8792.0 | HIT +3% (d2) | 0.04% |
| 2020-09-25 | 11050.2 | close 11050.2 re-enters above BB(20,2) lower band 10958.3 | HIT +3% (d4) | 0.00% |
| 2021-02-01 | 14281.2 | close 14281.2 re-enters above BB(20,2) lower band 13751.6 | HIT +3% (d1) | 0.00% |
| 2021-03-26 | 14507.3 | close 14507.3 re-enters above BB(20,2) lower band 14333.6 | HIT +3% (d7) | 0.00% |
| 2021-04-13 | 14504.8 | close 14504.8 re-enters above BB(20,2) lower band 14326.4 | HIT +3% (d10) | 1.05% |
| 2021-11-23 | 17503.3 | close 17503.3 re-enters above BB(20,2) lower band 17489.8 | HIT +3% (d35) | 6.25% |
| 2021-11-30 | 16983.2 | close 16983.2 re-enters above BB(20,2) lower band 16978.3 | HIT +3% (d7) | 0.00% |
| 2021-12-21 | 16770.8 | close 16770.8 re-enters above BB(20,2) lower band 16677.4 | HIT +3% (d6) | 0.00% |
| 2022-02-25 | 16658.4 | close 16658.4 re-enters above BB(20,2) lower band 16549.4 | HIT +3% (d13) | 5.92% |
| 2022-03-08 | 16013.5 | close 16013.5 re-enters above BB(20,2) lower band 15873.1 | HIT +3% (d2) | 0.15% |
| 2022-05-10 | 16240.0 | close 16240.0 re-enters above BB(20,2) lower band 16206.0 | HIT +3% (d18) | 3.11% |
| 2022-05-13 | 15782.1 | close 15782.2 re-enters above BB(20,2) lower band 15774.6 | HIT +3% (d2) | 0.27% |
| 2022-06-14 | 15732.1 | close 15732.1 re-enters above BB(20,2) lower band 15713.9 | HIT +3% (d18) | 3.49% |
| 2022-06-20 | 15350.1 | close 15350.2 re-enters above BB(20,2) lower band 15228.1 | HIT +3% (d5) | 0.00% |
| 2022-09-30 | 17094.3 | close 17094.3 re-enters above BB(20,2) lower band 16768.5 | HIT +3% (d12) | 1.40% |
| 2022-12-26 | 18014.6 | close 18014.6 re-enters above BB(20,2) lower band 17935.4 | HIT +1% (d3) | 0.26% |
| 2023-01-31 | 17662.2 | close 17662.2 re-enters above BB(20,2) lower band 17608.8 | HIT +2% (d11) | 1.75% |
| 2023-03-01 | 17450.9 | close 17450.9 re-enters above BB(20,2) lower band 17295.5 | HIT +3% (d37) | 0.83% |
| 2023-10-27 | 19047.2 | close 19047.2 re-enters above BB(20,2) lower band 19001.1 | HIT +3% (d12) | 0.56% |
| 2024-01-24 | 21454.0 | close 21453.9 re-enters above BB(20,2) lower band 21263.5 | HIT +3% (d6) | 0.96% |
| 2024-08-07 | 24297.5 | close 24297.5 re-enters above BB(20,2) lower band 23989.8 | HIT +3% (d12) | 0.90% |
| 2024-11-19 | 23518.5 | close 23518.5 re-enters above BB(20,2) lower band 23425.7 | HIT +3% (d3) | 1.09% |
| 2024-12-23 | 23753.5 | close 23753.4 re-enters above BB(20,2) lower band 23660.0 | HIT +1% (d7) | 1.23% |
| 2025-01-14 | 23176.0 | close 23176.1 re-enters above BB(20,2) lower band 23107.8 | HIT +2% (d16) | 0.86% |
| 2025-03-03 | 22119.3 | close 22119.3 re-enters above BB(20,2) lower band 22051.5 | HIT +3% (d10) | 0.70% |
| 2025-07-29 | 24821.1 | close 24821.1 re-enters above BB(20,2) lower band 24697.2 | HIT +2% (d34) | 1.95% |
| 2025-08-11 | 24585.0 | close 24585.1 re-enters above BB(20,2) lower band 24336.4 | HIT +3% (d25) | 0.49% |
| 2026-01-12 | 25790.2 | close 25790.2 re-enters above BB(20,2) lower band 25669.1 | HIT +2% (d14) | 4.31% |
| 2026-01-22 | 25289.9 | close 25289.9 re-enters above BB(20,2) lower band 25161.4 | HIT +3% (d7) | 2.41% |
| 2026-03-05 | 24765.9 | close 24765.9 re-enters above BB(20,2) lower band 24705.3 | MISS (best -0.26%) | 10.43% |
| 2026-03-10 | 24261.6 | close 24261.6 re-enters above BB(20,2) lower band 24096.2 | HIT +1% (d26) | 8.57% |
| 2026-03-16 | 23408.8 | close 23408.8 re-enters above BB(20,2) lower band 23107.0 | HIT +3% (d18) | 0.27% |
| 2026-05-14 | 23689.6 | close 23689.6 re-enters above BB(20,2) lower band 23447.8 | HIT +3% (d35) | 1.57% |

99/109 = 90.8% HIT +1%. 10 misses: 2008-06-03, 2011-01-12, 2011-08-10, 2013-02-12,
2015-11-06, 2016-10-18, 2018-09-25, 2020-03-03 (COVID), 2020-03-13 (COVID, worse), 2026-03-05.

## Recommendation

Both A1 (Supertrend(10,3) flip) and A3 (Bollinger(20,2) re-entry) are real, structurally
sound reversal signals with cross-regime consistency and genuine parameter-robustness — not
curve-fit noise. They should not, however, be sold to the user as "90%+ hit-rate" systems:
the honest number is 90–93% point estimate with a bootstrap-CI floor around 86–88%, and the
failure mode (missing the entry that immediately precedes an exogenous macro shock) is
structural, not fixable by any regime filter tested here. If the user wants a signal to act
on: A1 (Supertrend flip) is the stronger single choice — highest point hit rate, tightest
parameter plateau, out-of-sample-consistent, and the largest sample of the two after B3 is
set aside for its OOS degradation. A3 is a reasonable second opinion / confirmation signal
(fires on different, though correlated, days) given its larger sample and equally-consistent
regime performance. Do not chase the small-sample "100% hit rate" signals (A2, A5, A6, B2,
B5, B8, B9) into production — several have fewer than 10 signals in 19 years and would need
several more years of live data before their apparent edge means anything. If the user needs
a true ≥90%-with-confidence system, the next investment should be exploring intraday/lower
timeframe confirmation filters or index-breadth/VIX-based crash-warning overlays layered on
top of A1 — not further indicator-threshold tweaking on daily closes alone, since the
parameter sweep already shows this family of signal has been squeezed about as far as it
will go on this data.

**Data-refresh note (2026-07-28 re-run):** `drishti.db` now carries NIFTY50 history back to
2006-08-02 (previously 2007-09-17 — ~1.3 more years), 4,951 deduped trading days vs. 4,625
before. A1 recomputed on this fresher pull: **n=79, hit1=93.7%** (vs. n=75/93.3% previously)
— consistent within noise, no material change to the verdict above. This n=79/93.7% figure
is what Part 2 below compares its new signal against.

---

# Part 2 — Bullish RSI(14) Divergence + Volume-Spike Signal (C-family) — **WITHDRAWN 2026-07-28**

```
WITHDRAWN: This entire section is retained below for the historical record only. The user
has explicitly rejected yfinance as a dependency for anything in this study, and this
signal's only viable volume source was a yfinance-sourced ^NSEI Volume proxy (drishti.db's
own NIFTY50 volume column is always 0 -- an index has no traded volume of its own, so there
was no in-DB alternative). The code (`add_volume_proxy()`, `detect_divergence_volume()`,
`divergence_reason_string()`, `divergence_volume_param_sweep()`, and the C1/C1b/C1c config
wiring in `main()`) has been REMOVED from `nifty_entry_signal_backtest.py` and yfinance has
been uninstalled from the venv. This is a withdrawal for DEPENDENCY reasons, not because the
signal failed on its own merits -- it was already separately flagged below as too-small-
sample (n=3-11, well short of the ~30-trade floor) before this withdrawal, and that finding
stands unchanged; it simply can no longer be reproduced or extended without reintroducing a
now-disallowed dependency. Do not attempt to re-run or re-cite this section's numbers as
current -- the code backing them no longer exists in the script.
```

Added: 2026-07-28 (same day as the withdrawal above — this signal's entire lifecycle, from
build to retirement, occurred within one session). Same script
(`nifty_entry_signal_backtest.py`, at the time), same forward-outcome
definition as Part 1 (entry at close[t], 42-trading-day forward window, +1%/+2%/+3% tiers on
daily HIGH, drawdown-tolerant hits, `max_adverse_dip_pct` tracked). Functions:
`detect_divergence_volume()`, `add_volume_proxy()`, `divergence_volume_param_sweep()`.

```
VERDICT: Not statistically distinguishable from noise — small-sample flag applies to
EVERY configuration tested, without exception. The mechanism is real and every signal
that fired was a genuine hit (11/11 at the most permissive threshold tested, 3/3 at the
threshold closest to the brief's requested 1.5x/20d-avg spec), but a true bullish
RSI-divergence + genuine-volume-spike confluence is simply RARE on NIFTY daily bars —
about 1 signal per year even at a barely-there 1.1x volume threshold, and n collapses to
0-1 by 2.5-3x. This is a sample-size problem, not a signal-quality problem: the per-signal
evidence is clean and lookahead-safe, but there are not enough independent trades in 19
years of data to certify a hit rate. Do not present this as a ~90%+ (or 100%) system.
```

## Strategy as tested

- **Bullish divergence:** price makes a swing low at day *t* equal-to-or-lower than a
  **prior CONFIRMED swing low** at day *t_prev* (*t_prev* < *t*), while RSI(14) at *t* is
  higher than RSI(14) at *t_prev* (optionally by a minimum-point margin, swept at 0/2/5 pts).
- **Volume confirmation:** volume on day *t* is ≥ `vol_mult` × the trailing 20-day average
  volume (average computed from days *t-20..t-1*, deliberately excluding day *t*'s own print
  so the spike can't inflate its own baseline). `vol_mult` swept at 1.5/2.0/2.5/3.0 per the
  brief, plus a finer 1.1-2.0 grid to characterize where the sample size actually collapses.
- **Entry:** fires at day *t*'s own close, with no confirmation lag — see "No-lookahead
  design" below for exactly how this is made safe.
- **Sizing / universe / timeframe:** none; NIFTY 50 index, daily candles — same scope as
  Part 1.
- **Assumption made (ambiguity in the brief):** "swing low" is defined on the daily **LOW**
  series (the standard chart-pattern definition of a swing low), not the close, since a
  "swing low" is conventionally a wick-level concept; RSI(14) itself is still computed the
  standard way (on close). This is the most conservative, most standard reading and is
  stated rather than stalled on.

## No-lookahead design (this is the part that broke the prior version of this signal once)

The prior B5 divergence signal (Part 1) fixed one lookahead bug (a centered-window swing low
that needed 5 future days to confirm) by delaying the *entry* to the confirmation day. The
brief for this session explicitly asks for something stricter: entry on day *t* itself, with
*t* "confirmable that day." That requires an **asymmetric** definition, not just reapplying
B5's lag:

- **t_prev (the reference low being compared against)** uses a **centered** ±W window on the
  LOW series: `low[i] == min(low[i-W..i+W])`. This candidate only becomes usable as a
  reference once **`i_prev + W <= t`** — i.e. its confirmation must have already happened at
  or before the day being evaluated. This is a purely historical fact by the time *t* arrives.
- **t (the entry day itself)** is **never** identified with a centered window (that would
  require *t+W* future days — unknowable on day *t*, exactly the bug class flagged in the
  brief). Instead, *t* only needs to satisfy a **trailing-only** local-low test:
  `low[t] == min(low[t-W..t])` — today's low is the lowest of the last W+1 days *including
  today*. This uses only data through day *t*'s own close, so it is honestly knowable in
  real time, with zero lag.
- Volume: `volume[t] >= vol_mult * mean(volume[t-20..t-1])` — again, only past/present data.
- Explicit check performed: every array read at index *t* (low, rsi14, volume, vol_avg,
  ema200_slope for the regime variant) is a function of data through day *t* inclusive. The
  only fact about the future used anywhere is "*t_prev* was a confirmed swing low," and that
  confirmation is gated to have occurred **at or before** *t* — never in *t*'s own future.
  Re-verified by construction (the `ptr`/`confirm_day <= t` gate in `detect_divergence_volume`)
  and by manually inspecting each fired signal's `t_prev` date against `t` (all in the
  per-signal table below satisfy `t_prev + W <= t`).
- Once a given `t_prev` fires one signal, it's not reused for a later *t* (prevents
  near-duplicate signals from the same bottoming episode inflating *n*).

## Data — a hard blocker that had to be solved before this signal could be built at all

`drishti.db`'s NIFTY50 `volume` column is **0 on all 4,951/4,951 rows**, every single day
2006-2026 — verified directly (`df['volume'].describe()` → mean/std/min/max all 0.0). This is
a real structural fact, not a bug: NIFTY 50 is an index, and an index has no traded volume of
its own (Part 1 already flagged this as "harmless" — but that was before any signal here
needed volume as a filter criterion, where it's now a hard blocker).

**Fix:** NSE separately publishes an aggregate "shares traded" volume figure for the index
itself (distinct from the price series). yfinance's `^NSEI` ticker carries this as its
`Volume` column. Verified before trusting it:
- Close-price spot-check on 4 dates (2024-01-24, 2025-02-04, 2026-04-08, 2026-07-27): `^NSEI`
  closes match `drishti.db` NIFTY50 closes to the cent — confirms correct date alignment (no
  UTC/IST off-by-one) between sources.
- The Volume field is **0 on 100% of days 2007-2012** and on a handful of early-2013 days (not
  backfilled before 2013-01-21); from **2013-01-21 onward it's populated on effectively every
  trading day** (0.0-5.3%/year sporadic zero-prints after that, treated as ordinary missing
  data by the existing div-by-zero guard).
- The signal is therefore only evaluated from **2014-11-26 onward** (`volume_proxy_reliable_
  cutoff_idx()` computes this from the data itself: last pre-2015 zero/missing print + a
  20-day buffer so the trailing volume-average window is entirely real data) — a **real,
  reported-not-hidden reduction in usable history** vs. A1/A3's full 2007-2026 window. This
  alone roughly halves the number of years available to find this pattern in.
- **Window:** 2014-11-26 → 2026-07-27 (~11.7 years, ~2,890 trading days) for anything
  volume-gated. Full 2006-2026 OHLC/RSI history is still used to identify `t_prev` reference
  lows that predate the cutoff, where the *entry* itself (`t`) is after the cutoff.

---

# Part 3 — EMA(9)/EMA(21) Bullish Cross + RSI(14) Recovery-from-Below-40 (D-family, 2-year window only)

Added: 2026-07-28. Same script (`nifty_entry_signal_backtest.py`), same forward-outcome
definition as Parts 1–2 (entry at close[t], 42-trading-day forward window, +1%/+2%/+3% tiers
on daily HIGH, drawdown-tolerant hits, `max_adverse_dip_pct` tracked). Functions:
`detect_ema_rsi_recovery()`, `ema_rsi_recovery_param_sweep()`, `ema_rsi_recovery_gap_sweep()`.
**This signal is scored ONLY on the last ~2 years of data (2024-07-28 → 2026-07-27,
`D1_WINDOW_START` in the script) — an explicit, repeated user instruction, not a suggestion —
and, per an equally explicit second instruction, carries NO EMA200/regime/trend gate of any
kind.**

```
VERDICT: Not statistically distinguishable from noise. Point estimate is 80.0% (4/5) on the
mandated 2-year window — below the user's 90% bar on its face, and the 90% exact-binomial
confidence interval is [34.3%, 99.0%], which doesn't even clear a coin flip on the low end.
This is the smallest, least-trustworthy sample in this entire study (n=5, versus A1's n=79
and A3's n=115) — smaller even than the small-sample-flagged C-family divergence signals
(n=3-11). The 2-year window is NOT an "easy" regime that inflated the number: it contains two
genuine ~15% corrections and one strong recovery rally, so the underlying mechanism was
tested against real adverse conditions, not cherry-picked calm markets — but real regime
variety cannot substitute for more trades when the question is "is 80%/90%/96% the true rate."
Recomputing the identical rule against the FULL 2006-2026 history (not requested as the
headline, but essential context) gives n=26, 96.2% hit rate, 90% CI [83.0%, 99.8%] — a
plausible, much better-evidenced number, which strongly suggests the 2-year sample's 80% is
sampling noise from an unlucky small draw (one single miss in 5 trades swings the headline
number by 20 points) rather than a real regime-specific degradation of the underlying signal.
Do not act on the 2-year number as reported; either wait for more signals to accumulate, or
treat the full-history recomputation as the more informative (if not literally what was
asked for) read on this signal's true quality.
```

## Strategy as tested

- **Entry:** EMA(9) crosses above EMA(21) (`ema9[i] > ema21[i]` and `ema9[i-1] <= ema21[i-1]`,
  both EMAs the standard recursive/backward-looking kind) **AND** RSI(14) is "recovering from
  below 40," defined conservatively as a literal recross — `rsi14[j] > 40` and
  `rsi14[j-1] <= 40` — occurring within **±5 trading days** of the EMA cross day. Entry price
  = close on the later of the two trigger days (see "No-lookahead design" below for exactly
  why, and why it never actually mattered in this window's 6 fired signals).
- **Exit:** none defined — same as every other signal in this study; this is a signal-quality
  study (does price touch +1%/+2%/+3% within 42 trading days), not a P&L backtest with a
  stop-loss/take-profit exit rule.
- **Sizing:** none.
- **Universe / timeframe:** NIFTY 50 index, daily candles — same as Parts 1–2.
- **No regime/trend gate — by explicit user directive.** Unlike B1/B7/B9 elsewhere in this
  script, no EMA200-slope filter (or any other "is the market in an uptrend" condition) is
  applied here, even though one would very likely improve the raw hit rate (the single 2y-window
  miss, 2026-02-09, fired with EMA200 rolling over into a real correction — see "Where it
  fails" below). This is intentional per the brief, not an oversight.
- **Assumptions made (the brief left two things ambiguous — most conservative,
  most lookahead-safe reading picked in each case, per the brief's own instruction):**
  1. "RSI recovering from below 40" = a literal recross above 40 having closed at-or-below 40
     the prior day (`rsi14[j-1] <= 40 < rsi14[j]`), not a fuzzier "any uptick while still under
     40." This mirrors the confluence style already established for A6 (ST flip + RSI recross
     above 30) elsewhere in this script, for consistency.
  2. "Within a few days of the EMA cross" = **±5 trading days**, matching A6's own ±3-day
     window in spirit (a small, human-legible tolerance) while erring slightly wider given the
     brief's own wording ("a few days"); swept at ±3/±5/±7 below as a bonus robustness check
     even though the brief only mandated sweeping the EMA pair and RSI threshold.

## No-lookahead design

Same discipline as A6 (Supertrend flip + RSI recross, already in this script) applied to a new
pair of triggers: if the RSI-recovery day falls **on or before** the EMA-cross day, the
confluence is already fully knowable at the EMA-cross day and fires there. If the RSI-recovery
day falls **strictly after**, the signal isn't confirmable until that later day, so it fires
there instead, using that later day's own close as entry price. Verified directly: **all 6**
signals that fired in the 2-year window happen to have the RSI recovery occur *before* the
EMA cross (gap = -3 to -5 trading days in every case) — meaning entry always ended up being the
EMA-cross day's own close in this particular sample. This is a property of the data, not the
code path being untested: the "fires later" branch is exercised correctly by construction (it
is the exact same code path already audited for A6), it simply never had to trigger during
this specific 2-year window.

## Data

- **Source:** SQLite (`drishti.db`), same fresh pull used for Parts 1–2 (4,951 deduped trading
  days, 2006-08-02 → 2026-07-27). EMA(9)/EMA(21)/RSI(14) are computed on the **full** history
  (so they are never cold-started at the 2-year boundary) — only which already-detected
  signals get **scored** is restricted to the window.
- **Window:** 2024-07-29 → 2026-07-27, 495 trading days (the brief's "roughly 2024-07-28
  through 2026-07-27, ~500 trading days" — matches almost exactly; 2024-07-28 itself was a
  Sunday, so the window's first trading day is 2024-07-29).
- **Data quality:** same checks as Parts 1–2 (OHLC integrity, dedup, no NaNs) — already
  verified on the full 4,951-row pull these 495 rows are drawn from; no additional
  quality issues found specific to this slice.

### Regime characterization of the 2-year window (read before trusting the hit rate)

This is **not** a single easy bull-market slice — it's a genuinely mixed regime:

| Period | Move | Detail |
|---|---|---|
| 2024-07-29 → 2024-09-26 | +5.6% | Rally to an interim peak (26,216.05) |
| 2024-09-26 → 2025-03-04 | **-15.77%** | Real correction: peak 26,216.05 → trough 22,082.65 |
| 2025-03-04 → 2026-01-02 | **+19.2%** | Strong recovery rally to a new high (26,328.55) |
| 2026-01-02 → 2026-03-30 | **-15.18%** | Second real correction: peak 26,328.55 → trough 22,331.40 |
| 2026-03-30 → 2026-07-27 | +7.5% | Partial recovery, choppy, ends flat-ish |

Net change over the full window: **-3.4%** (24,836.10 → 23,995.95), i.e. essentially flat
after two ~15% round trips down-and-back-up. Annualized daily-return volatility ≈ 13.4%. This
window contains real, sizable drawdowns (not a "line goes up" easy regime) and a real V-shaped
recovery — the 80%/5-signal result was earned against a genuinely mixed backdrop, even though
5 signals is nowhere near enough to say what that means statistically.

## Core metrics (2-year window, the mandated primary result) vs. full-history (context only)

| | 2-year window (2024-07-28+, **as instructed**) | Full history (2006-2026, context only) |
|---|---|---|
| n (complete 42d windows) | **5** | 26 |
| Hit +1% | **80.0%** (4/5) | 96.2% (25/26) |
| Hit +2% | 80.0% | 92.3% |
| Hit +3% | 80.0% | 84.6% |
| Avg max adverse dip | 3.64% | — |
| Median days to +1% | 4 | — |
| 90% bootstrap CI (percentile) | [40.0%, 100.0%] | [88.5%, 100.0%] |
| 90% exact-binomial (Clopper-Pearson) CI | **[34.3%, 99.0%]** | [83.0%, 99.8%] |

A 6th signal (2026-06-17) fired inside the window but is excluded from the n=5 headline
because its 42-day forward window isn't complete yet as of the latest candle — see "Currently
live" below; it has already resolved as a HIT within the elapsed data so far.

## Full per-signal table — 2-year window (n=6 total, 5 with complete 42-day windows)

Entry = close on the fire day (in every row here, the EMA-cross day itself — see "No-lookahead
design" above). "RSI recent low" = the lowest RSI(14) print in the window spanning the
EMA-cross/RSI-recovery pair (how deep the "below 40" dip actually was before it turned up).

| Date | Entry | EMA9 | EMA21 | RSI now | RSI recent low | RSI recovery date (gap, trading days) | Outcome (days to reach) | Max adverse dip |
|---|---|---|---|---|---|---|---|---|
| 2025-03-20 | 23190.65 | 22730.0 | 22708.3 | 63.0 | 38.0 | 2025-03-17 (-3d) | HIT +3% (d18) | 0.25% |
| 2025-04-16 | 23437.20 | 23020.7 | 22992.8 | 57.4 | 33.7 | 2025-04-08 (-4d) | HIT +3% (d2) | 0.59% |
| 2025-08-21 | 25083.75 | 24850.3 | 24831.4 | 57.9 | 33.6 | 2025-08-13 (-5d) | HIT +3% (d40) | 2.71% |
| 2025-10-07 | 25108.30 | 24950.7 | 24945.8 | 56.2 | 38.1 | 2025-10-01 (-3d) | HIT +3% (d9) | 0.40% |
| 2026-02-09 | 25867.30 | 25579.1 | 25564.9 | 56.2 | 30.9 | 2026-02-03 (-4d) | **MISS (best +0.55%)** | **14.24%** |
| 2026-06-17* | 24085.70 | 23681.5 | 23634.4 | 60.9 | 35.8 | 2026-06-12 (-3d) | open (see below) | 1.25%† |

*Excluded from the n=5 headline (incomplete 42d window as of 2026-07-27); †adverse dip
measured only up to its already-resolved +1% hit (day 11), not the full window.

4/5 = **80.0%** HIT +1% (complete windows only). 1 miss: 2026-02-09.

## Cost assumptions used

None — same out-of-scope decision as Parts 1–2 (signal-quality study). No cost-doubling
stress test applies for the same reason; not fabricated to fill the report template.

## Validation results

### Adapted-validation methodology — read this before the numbers below

A full train/test walk-forward split (the methodology used for A1/A3 with 19-20 years of
data) is **not meaningful here** — splitting 5-6 trades into two halves leaves 2-3 trades per
side, which has no statistical power in either direction. Rather than force that framework
onto data it doesn't fit, three lighter-weight checks were used instead, each explicitly
flagged for what it can and can't show:

1. **A light first-year vs. second-year split** (reported below) — descriptive only, not a
   real walk-forward test.
2. **Exact-binomial (Clopper-Pearson) confidence interval**, the correct tool for a small
   Bernoulli sample (same tool already used for the C-family divergence signals in Part 2,
   for the same reason: bootstrap resampling on a near-all-hit tiny sample either understates
   uncertainty or goes degenerate).
3. **The same rule recomputed on the full 19-20-year history**, purely as an out-of-window
   sanity check on whether the 2-year number looks like a plausible draw from a more
   stable long-run rate, or looks anomalous. This is explicitly NOT the number the user asked
   to be scored against — it's a diagnostic, reported transparently as such.

### First-year vs. second-year split (descriptive only — not a real walk-forward test)

| Period | n | Hit +1% |
|---|---|---|
| Year 1 (2024-07-29 → 2025-07-28) | 2 | 100.0% (2/2) |
| Year 2 (2025-07-29 → 2026-07-27) | 3 | 66.7% (2/3) |

With 2 and 3 trades respectively, this "split" carries essentially no statistical information
— it is reported because the brief asked for some adapted cut at the data, not because it
supports any conclusion. The apparent "degradation" from 100% to 66.7% is exactly what you'd
expect to see purely from one extra coin-flip going the other way in a 5-trade sample; it
should not be read as evidence of regime decay.

### Monte Carlo / exact-binomial CI

| Sample | n | Hits | Point hit1% | 90% bootstrap CI | 90% exact-binomial CI |
|---|---|---|---|---|---|
| **2-year window (mandated)** | **5** | 4 | **80.0%** | [40.0%, 100.0%] | **[34.3%, 99.0%]** |
| Full-history recompute (context only) | 26 | 25 | 96.2% | [88.5%, 100.0%] | [83.0%, 99.8%] |

The 2-year sample's confidence interval is 65 points wide at 90% confidence and its lower
bound doesn't clear a coin flip — this is, bluntly, not enough information to know whether the
true hit rate is 35% or 99%. Per the brief's own explicit instruction: **stated plainly, this
sample size is too small to draw any statistical conclusion.**

### Parameter-sensitivity sweep

**EMA pair × RSI-recovery threshold** (max_gap fixed at 5 trading days), both the mandated
2-year window and the full-history context number side by side:

| EMA pair \ RSI thresh | RSI<35 | RSI<40 (base) | RSI<45 |
|---|---|---|---|
| EMA(8,20)  | 2y: n=2, 50.0% \| full: n=7, 85.7% | 2y: n=7, 71.4% \| full: n=34, 94.1% | 2y: n=10, 80.0% \| full: n=87, 93.1% |
| EMA(9,21) (base) | 2y: n=2, 50.0% \| full: n=5, 80.0% | **2y: n=5, 80.0%** \| full: n=26, 96.2% | 2y: n=10, 80.0% \| full: n=75, 92.0% |
| EMA(10,25) | 2y: n=1, 100% \| full: n=4, 100% | 2y: n=5, 80.0% \| full: n=22, 95.5% | 2y: n=8, 75.0% \| full: n=55, 94.5% |

**Read plainly: this is closer to a cliff than a plateau, purely because of sample size, not
because the underlying rule is fragile.** Every cell in the 2-year-window grid has n≤10 — far
below the ~30-trade floor — so cell-to-cell "differences" (50% vs 80% vs 100%) are mostly
sampling noise on tiny samples, not evidence of a parameter-sensitive edge or a robust one.
The **full-history column tells a cleaner, more encouraging story**: every one of the 9
combinations lands in a fairly tight 80–100% band with n=4-87, and the higher-n cells (RSI<40
and RSI<45 rows, n=22-87) cluster specifically in **92–96%** — a real plateau, much like A1/A3's
sweeps in Part 1. This strongly suggests the *mechanism* is reasonably parameter-robust; the
2-year window is simply too short a slice to demonstrate that robustness on its own.

**Bonus: gap-window (`max_gap`) sensitivity** (EMA(9,21), RSI<40 fixed — not mandated by the
brief, included because it was cheap to add):

| max_gap | 2-year window | Full history |
|---|---|---|
| ±3 trading days | n=2, 100.0% | n=8, 100.0% |
| ±5 trading days (base) | n=5, 80.0% | n=26, 96.2% |
| ±7 trading days | n=9, 77.8% | n=47, 91.5% |

Widening the gap tolerance trades sample size for a slightly lower hit rate on both windows —
mild, monotonic, not a cliff — consistent with the idea that a tighter gap selects for a more
immediate, stronger momentum confirmation.

### Bias checks

- **Lookahead bias:** actively designed against from the start (see "No-lookahead design"
  above) — the same `max(ema_cross_idx, rsi_recovery_idx)` fire-day discipline already
  audited for A6 elsewhere in this script is reused here. Manually verified: all 6 fired
  signals in the window have their RSI-recovery day *before* their EMA-cross day (gap -3 to
  -5 trading days), so entry is always the EMA-cross day's own already-fully-confirmed close
  — no case in this sample exercised the "fires later" branch, though the code path exists and
  is identical to A6's already-verified implementation.
- **Survivorship bias:** N/A — single index, not a basket.
- **Overfitting: elevated risk, flagged explicitly, worse than any other family in this
  study.** This signal has **4 free parameters** (ema_fast, ema_slow, rsi_threshold, max_gap)
  tested against **5-10 trades** in the mandated window — a trades-per-free-parameter ratio
  worse even than the C-family divergence signals in Part 2 (3-4 params / 3-11 trades), and
  far worse than A1/A3 (1-2 params / 79-115 trades). Combined with the sample-size floor
  being missed by a wide margin, this is close to the textbook overfitting-risk profile —
  not because any parameter was hand-tuned to look good (9/21, 40, and ±5 were the brief's own
  stated starting point, not cherry-picked after the fact), but simply because 2 years of
  daily data cannot support certifying 4 parameters' worth of specificity.
- **Cost-doubled stress test:** N/A, same as Parts 1–2 — no costs modeled in this
  signal-quality study.

## Where it fails

The single miss in the 2-year window, **2026-02-09** (entry 25,867.30), fired right at the
leading edge of the second ~15% correction characterized above (window peak was 2026-01-02 at
26,328.55; the correction's actual trough wasn't until 2026-03-30 at 22,331.40). This is
**the same structural failure mode already documented for A1/A3 in Part 1**: a technically
clean bullish-momentum confirmation (EMA cross + RSI recovering) firing in the middle of what
turns out, in hindsight, to be a "dead cat bounce" inside a larger correction — not a scenario
any EMA/RSI-only rule can be expected to see coming, and (per the brief's explicit
instruction) no regime/trend filter was added here to try to screen it out.

## Comparison against A1/A3 sample sizes and hit rates

| | A1 (Supertrend flip, full-history) | A3 (BB re-entry, full-history) | **D1 (2-year window, mandated)** | D1 (full-history, context only) |
|---|---|---|---|---|
| n | 79 | 115 | **5** | 26 |
| Hit +1% (point) | 93.7% | 90.4% | **80.0%** | 96.2% |
| 90% exact-binomial CI | [87.2%, 97.5%] | [84.7%, 94.5%] | **[34.3%, 99.0%]** | [83.0%, 99.8%] |
| CI width | 10.3pp | 9.8pp | **64.7pp** | 16.8pp |
| Years of history used | ~20 | ~20 | **~2 (as instructed)** | ~20 |
| Free parameters | 2 | 2 | 4 | 4 |
| Firing frequency | ~4/year | ~5-6/year | ~2.5-3/year (in-window) | ~1.3/year |

D1's 2-year-window sample is roughly **15-20x smaller** than A1's or A3's, and its confidence
interval is **6-7x wider**. This is the direct, mechanical consequence of the two-part
instruction (EMA9/21+RSI40 momentum trigger, scored only on 2 years of data) — the rule itself
recomputed on the full history is not obviously worse than A1/A3 (96.2% vs 93.7%/90.4%, all
three CIs overlapping heavily), but the specific 2-year-only evaluation the user asked for
cannot, by construction, produce a trustworthy number at this signal's natural firing
frequency (~2.5-3 times a year). This is the same recurring failure mode flagged for the
C-family divergence signal in Part 2 and (per the task brief itself) anticipated going in.

## Currently live / most-recent matching setup (as of latest candle, 2026-07-27)

**No fresh signal fires on the most recent candle.** As of 2026-07-27: EMA(9)=24,014.53 is
still *below* EMA(21)=24,029.57 (no bullish cross yet), and RSI(14)=49.5 has not recently
dipped to or below 40 (its most recent local low was 42.87 on 2026-07-24, which never actually
breached the 40 threshold under this signal's strict recross definition) — so neither leg of
the confluence is currently active, and nothing is imminent under the exact trigger rule
without a fresh RSI dip below 40 first.

The **most recent fired signal** is **2026-06-17** at close 24,085.70 — notably the *same date
and same close price* as A1's (Supertrend flip) most-recently-reported signal in Part 1, i.e.
the two independently-defined signal families happened to fire on the identical day this time.
As of the latest candle (2026-07-27), 27 of 42 trading days have elapsed since entry:
- The +1% target (≥24,326.56) was already reached on day 11 (2026-07-03) — this entry is
  already a resolved **HIT** within the historical stats even though its window hasn't
  formally closed (max adverse dip before the hit: 1.25%).
- Best forward gain so far: +1.85% (high 24,530.90).
- Latest close (23,995.95) is -0.37% from entry — currently sitting slightly below entry,
  though the +1% target was already cleared earlier in the window.

## Recommendation (Part 3)

Do not present this signal's 2-year-window number (80.0%, n=5) as evidence of anything, in
either direction — the sample is the smallest in this entire study and its confidence interval
straddles a coin flip. This is a direct, expected consequence of the two constraints the user
explicitly imposed (a signal that only fires ~2.5-3 times a year, scored on only 2 years of
data) and was flagged going in as the likely outcome. Two honest options, to be decided by the
user, not unilaterally here:
1. **Accept a longer window** (the full 19-20-year history gives n=26, 96.2% hit rate, 90% CI
   [83.0%, 99.8%] — comparable to or better than A1/A3, and with a genuine parameter plateau
   in the 92-96% band across the RSI<40/RSI<45 sweep cells that have enough trades to matter).
   This is the single highest-leverage fix available and needs no rule changes at all.
2. **Loosen the RSI-recovery threshold** to 45 (still directionally "was oversold, is now
   recovering," just a less extreme oversold bar) — this roughly doubles the 2-year sample to
   n=10 while still landing at 80.0%, though even n=10 remains well short of the ~30-trade
   floor; this alone would not fully solve the problem, only partially mitigate it.
Neither option is applied here unilaterally, per the brief's own instruction to flag rather
than decide. As specified and scored exactly as instructed, the honest verdict stands: **not
enough data to certify a hit rate, in either direction** — the mechanism looks reasonable on
the (much larger) full-history recomputation, but the literal 2-year ask cannot support a
verdict on its own.

## Core metrics — three configs carried through (all flagged small-sample)

| Config | W | vol_mult | RSI margin | Regime filter | n | Hit +1% | Hit +2% | Hit +3% | Avg dip | Med days→1% |
|---|---|---|---|---|---|---|---|---|---|---|
| **C1 (brief-spec)** | 5 | 1.5x | 0pts | no | **3** | 100% | 100% | 100% | 1.08% | 1 |
| **C1b (max-sample)** | 5 | 1.1x | 0pts | no | **11** | 100% | 100% | 100% | 1.13% | 1 |
| C1c (C1b + regime) | 5 | 1.1x | 0pts | EMA200 flat/rising | 5 | 100% | 100% | 100% | 1.03% | 1 |

Every signal that ever fired, at every threshold tested, was a HIT at +1% (and, notably, at
+2% and +3% too — every one of the 11 C1b trades eventually reached the full +3% target
within 42 days). That is a genuinely clean track record mechanically, but it is exactly the
kind of number a sample size this small cannot support as a claim.

## Full per-signal table — C1b (max-sample config: W=5, vol_mult=1.1x, RSI margin=0pts, n=11)

Entry = close on day *t* (the trailing-confirmed second low). RSI-at-t vs. RSI-at-t_prev and
the volume multiple are the exact values used to accept/reject the signal — reproduced
verbatim from `detect_divergence_volume()`'s output, not recomputed for the report.

| Date (t) | Entry | t_prev date | low[t] vs low[t_prev] | RSI[t] vs RSI[t_prev] | Vol multiple (req ≥1.1x) | Outcome (days to reach) | Max adverse dip |
|---|---|---|---|---|---|---|---|
| 2016-02-10 | 7215.70 | 2016-01-20 | 7177.80 ≤ 7241.50 | 35.1 > 30.5 (+4.6) | 1.15x | HIT +3% (d16) | 5.40% |
| 2016-02-29 | 6987.05 | 2016-02-12 | 6825.80 ≤ 6869.00 | 37.3 > 28.1 (+9.2) | 2.02x | HIT +3% (d1) | 0.00% |
| 2018-03-23 | 9998.05 | 2018-03-07 | 9951.90 ≤ 10141.50 | 32.1 > 30.9 (+1.2) | 1.29x | HIT +3% (d7) | 0.40% |
| 2019-08-22 | 10741.35 | 2019-08-05 | 10718.30 ≤ 10782.60 | 31.8 > 23.0 (+8.8) | 1.33x | HIT +3% (d2) | 0.97% |
| 2021-03-19 | 14744.00 | 2021-02-26 | 14350.10 ≤ 14467.80 | 47.3 > 44.7 (+2.5) | 1.74x | HIT +3% (d40) | 3.25% |
| 2021-04-12 | 14310.80 | 2021-03-25 | 14248.70 ≤ 14264.40 | 40.3 > 38.3 (+2.1) | 1.48x | HIT +3% (d10) | 0.25% |
| 2021-12-20 | 16614.20 | 2021-11-29 | 16410.20 ≤ 16782.40 | 32.2 > 32.2 (+0.0) | 1.14x | HIT +3% (d3) | 0.00% |
| 2022-06-17 | 15293.50 | 2022-05-12 | 15183.40 ≤ 15735.80 | 28.4 > 27.2 (+1.2) | 1.30x | HIT +3% (d6) | 0.67% |
| 2023-03-14 | 17043.30 | 2023-02-28 | 16987.10 ≤ 17255.20 | 32.8 > 30.6 (+2.2) | 1.13x | HIT +3% (d14) | 1.26% |
| 2025-01-21 | 23024.65 | 2025-01-13 | 22976.80 ≤ 23047.20 | 35.4 > 32.2 (+3.2) | 1.23x | HIT +3% (d11) | 0.19% |
| 2025-04-07 | 22161.60 | 2025-03-04 | 21743.70 ≤ 21964.60 | 33.7 > 21.8 (+11.9) | 1.90x | HIT +3% (d3) | 0.00% |

11/11 = 100% HIT +1% (and, notably, 11/11 also HIT +3%). Zero misses — read alongside the
small-sample caveat above, not as a standalone headline.

## Full per-signal table — C1 (brief-spec config: W=5, vol_mult=1.5x, RSI margin=0pts, n=3)

The literal subset of the above table that clears the brief's originally-requested 1.5x
threshold (rows 2016-02-10, 2019-08-22, 2021-04-12, 2021-12-20, 2022-06-17, 2023-03-14,
2025-01-21 all drop out here — their volume multiple was ≥1.1x but <1.5x):

| Date (t) | Entry | t_prev date | low[t] vs low[t_prev] | RSI[t] vs RSI[t_prev] | Vol multiple (req ≥1.5x) | Outcome (days to reach) | Max adverse dip |
|---|---|---|---|---|---|---|---|
| 2016-02-29 | 6987.05 | 2016-02-12 | 6825.80 ≤ 6869.00 | 37.3 > 28.1 (+9.2) | 2.02x | HIT +3% (d1) | 0.00% |
| 2021-03-19 | 14744.00 | 2021-02-26 | 14350.10 ≤ 14467.80 | 47.3 > 44.7 (+2.5) | 1.74x | HIT +3% (d40) | 3.25% |
| 2025-04-07 | 22161.60 | 2025-03-04 | 21743.70 ≤ 21964.60 | 33.7 > 21.8 (+11.9) | 1.90x | HIT +3% (d3) | 0.00% |

3/3 = 100% HIT +1% (and +3%). n=3 is too small to draw any conclusion whatsoever — included
only because it is the config that literally matches the brief's stated 1.5x parameter.

## Cost assumptions

None (same as Part 1 — signal-quality study, spot-only, no P&L/costs modeled per scope).

## Validation results

### Small-sample flag — read this before anything else below

**n=3 (C1) and n=11 (C1b) are both far below the ~30-trade floor** stated in the brief as the
threshold for any statistical conclusion. n=11 is the *largest* sample obtainable anywhere in
the requested parameter space (1.5-3.0x) or the extended exploration (down to 1.1x) — this
isn't a matter of picking a better threshold, it's a ceiling imposed by how rare this exact
three-way confluence (trailing new low + confirmed prior reference low + genuine volume
spike) actually is on 11.7 years of NIFTY daily bars.

### Bootstrap is degenerate here — used exact-binomial (Clopper-Pearson) CI instead

Running the same non-parametric bootstrap used for A1/A3 on an **all-hit** sample of size 3
or 11 produces a **[100%, 100%] CI** — every resample of an all-1s array has mean 1.0, so the
bootstrap can't express any uncertainty at all here. That degenerate result would be
actively misleading if reported at face value, so it's replaced with the standard
**exact-binomial (Clopper-Pearson) 90% CI** for a Bernoulli proportion, which is the correct
tool for a small, all-success sample:

| Config | Hits/n | Point hit1% | 90% exact-binomial CI |
|---|---|---|---|
| C1 | 3/3 | 100.0% | **[36.8%, 100.0%]** |
| C1b | 11/11 | 100.0% | **[76.2%, 100.0%]** |
| C1c | 5/5 | 100.0% | [54.9%, 100.0%] |
| A1 (for reference) | 74/79 | 93.7% | [87.2%, 97.5%] |

C1's interval is 63 points wide and its lower bound (36.8%) doesn't even clear a coin flip —
it is not possible to distinguish "real 100% edge" from "got lucky 3 times in a row" with 3
observations. C1b's interval (11/11) is better but still 24 points wide and its lower bound
(76.2%) sits well below A1's own lower bound (87.2%) despite C1b's point estimate looking
higher on the surface. **The headline "100%" numbers in the core-metrics table above should
not be read as "better than A1's 93.7%" — the confidence intervals say the opposite: A1 is
the statistically stronger claim by a wide margin.**

### Walk-forward (train pre-2021 vs. test 2021+, and a second cut at 2022)

| Config | Split | Train n | Train hit1% | Test n | Test hit1% |
|---|---|---|---|---|---|
| C1b | 2021-01-01 | 4 | 100% | 7 | 100% |
| C1b | 2022-01-01 | 7 | 100% | 4 | 100% |

No gap, but explicitly **not a meaningful walk-forward test** — a 4-vs-7 or 7-vs-4 split has
essentially no statistical power either way; this table is reported for completeness per the
mandatory gauntlet, not as evidence of robustness.

### Parameter-sensitivity sweep — this is a CLIFF, not a plateau (the opposite of A1/A3)

**Brief-requested grid** (W × vol_mult{1.5, 2.0, 2.5, 3.0} × RSI-margin{0, 2, 5}pts):

| W \ vol_mult | 1.5x | 2.0x | 2.5x | 3.0x |
|---|---|---|---|---|
| 3 | n=5, 80.0% (margin 0) / n=4, 100% (margin 2) / n=2, 100% (margin 5) | n=1, 100% (all margins) | n=0 | n=0 |
| 5 | n=3, 100% (margin 0) / n=3, 100% (margin 2) / n=2, 100% (margin 5) | n=1, 100% (all margins) | n=0 | n=0 |
| 7 | n=3, 100% (margin 0) / n=3, 100% (margin 2) / n=2, 100% (margin 5) | n=1, 100% (all margins) | n=0 | n=0 |
| 10 | n=3, 100% (margin 0) / n=3, 100% (margin 2) / n=2, 100% (margin 5) | n=1, 100% (all margins) | n=0 | n=0 |

**Extended grid** (finer vol_mult steps, RSI margin=0, to see exactly where the sample dies):

| W \ vol_mult | 1.1x | 1.2x | 1.3x | 1.4x | 1.5x | 1.75x | 2.0x |
|---|---|---|---|---|---|---|---|
| 3 | n=11, 81.8% | n=11, 81.8% | n=8, 75.0% | n=5, 80.0% | n=5, 80.0% | n=4, 75.0% | n=1, 100% |
| 5 | n=11, 100% | n=9, 100% | n=7, 100% | n=4, 100% | n=3, 100% | n=2, 100% | n=1, 100% |
| 7 | n=11, 100% | n=9, 100% | n=8, 100% | n=4, 100% | n=3, 100% | n=2, 100% | n=1, 100% |
| 10 | n=9, 100% | n=7, 100% | n=6, 100% | n=3, 100% | n=3, 100% | n=2, 100% | n=1, 100% |

**Read plainly: this is a cliff, not a plateau.** *n* falls monotonically and steeply as
`vol_mult` rises in every row, converging to 0-1 by 2.5-3.0x regardless of the swing window
W — which itself barely matters (W=5/7/10 give nearly identical results; W=3 is the one
mild outlier, degrading to 75-82% hit rate rather than 100%, on a slightly noisier trailing-3-day
low definition). This is the **opposite** of A1's Supertrend sweep (9/9 combos landing in a
tight 91.8-95.2% band on n=61-103 each) or A3's Bollinger sweep (9/9 combos landing in
88.0-92.5% on n=75-174 each). A1/A3 are robust because the parameter choice barely moves
either *n* or the hit rate. Here, the parameter choice is the *only* thing determining
whether you have 11 trades or 1 — the "100%" ceiling appears **because** the sample keeps
shrinking toward n=1, not despite it. This is a textbook small-sample illusion, not a
demonstrated robustness plateau, and is reported as such rather than spun as a positive.

### Bias checks

- **Lookahead bias:** actively designed against from the start this session (see "No-lookahead
  design" above) — the asymmetric trailing-vs-centered swing-low definition was built
  specifically because a naive reapplication of B5's centered-window approach to the entry day
  itself would have reintroduced exactly the bug the brief warned about. Manually verified: every
  fired signal's `t_prev + W <= t` (see per-signal table's `gap_days` column, all reported and
  all satisfy `t - i_prev >= 5` days, well past the `t_prev + W` confirmation point for every
  swept W).
- **Survivorship bias:** N/A — single index, not a basket.
- **Overfitting:** **elevated risk, flagged explicitly.** This signal has 3 free parameters (W,
  vol_mult, rsi_margin) plus an optional 4th (regime filter) tested against 3-11 trades — a
  trades-per-free-parameter ratio far worse than A1/A3's 75-79 trades against 1-2 parameters.
  Combined with the cliff-not-plateau sweep result above, this is close to the textbook
  definition of a curve-fit risk, even though no single number here was hand-picked to look
  good after the fact (C1 was chosen because it matches the brief's literal 1.5x spec; C1b
  because it's the largest-n config found in the wider search).

## Where it fails / limitations

- **Sample size is the whole story.** There is no "where it fails" in the sense of specific
  bad trades — literally every trade in every config was a win. The failure mode here is
  epistemic, not mechanical: 11 trades (or 3) cannot support any claim about a "true" hit rate,
  good or bad. A future run of live data could easily produce several consecutive misses
  without contradicting anything found here.
- **Regime clustering, not exogenous-shock coverage:** the 11 C1b signals cluster in
  2016 (2), 2018 (1), 2019 (1), 2021 (3), 2022 (1), 2023 (1), 2025 (2) — notably **none in
  2020**, meaning this pattern did not fire into the COVID crash the way A1 did (A1's worst
  miss, -38% adverse dip, was 2020-02-06). That's not evidence this signal is "safer" in a
  crash, though — a fast, single-leg vertical crash like COVID's initial drop structurally
  doesn't produce the two-leg "higher low" bottoming pattern this signal requires, so it
  simply never got a chance to fire into that specific failure mode, for mechanical reasons,
  not because it correctly avoided it.
- **The volume-history constraint itself is a real cost:** ~11.7 years of usable history (vs.
  A1/A3's ~19-20 years) means roughly half the historical record this study otherwise has
  access to, purely because of the index-volume-proxy limitation.

## Currently live / most-recent matching setup (as of latest candle, 2026-07-27)

**No new signal fires on the most recent candle** at any threshold tested (1.1x, 1.5x, or
2.0x). The most recent signal (any config) is the **C1b (relaxed, 1.1x)** config's entry:

- **Fired 2026-06-02** at close 23,483.55 — divergence vs. the confirmed swing low on
  2026-05-13 (low 23,262.55): low 23,229.15 ≤ 23,262.55, RSI(14) 42.95 > 40.52 (+2.4pts),
  volume 1.16x the 20-day average (only qualifies at the 1.1x threshold, **not** at the
  brief-spec 1.5x threshold — so this entry does **not** count under C1, only C1b).
- 38 of 42 trading days have elapsed as of 2026-07-27. The +1% target (≥23,718.39) was
  already hit on day 9; best forward gain so far is **+4.46%** (high 24,530.90); max adverse
  dip before the +1% hit was **1.76%**. Latest close (23,995.95) is +2.18% above entry.
- This trade is already a resolved HIT within the historical stats above even though its
  42-day window hasn't formally closed (4 trading days remain).

Nothing is actionable as a **fresh** entry today under either C1 or C1b's exact trigger rule.

## Comparison against A1 (Supertrend(10,3) flip) — side by side

| | A1 (Supertrend flip) | C1 (brief-spec, 1.5x) | C1b (max-sample, 1.1x) |
|---|---|---|---|
| n | 79 | 3 | 11 |
| Hit +1% (point) | 93.7% | 100% | 100% |
| 90% CI (exact-binomial) | [87.2%, 97.5%] | [36.8%, 100.0%] | [76.2%, 100.0%] |
| Usable history | 2006-2026 (~19.9y) | 2014-2026 (~11.7y) | 2014-2026 (~11.7y) |
| Walk-forward gap | -3.9pp (in→out, per Part 1) | n too small to test | 0pp (but n too small to mean anything) |
| Parameter robustness | plateau (9/9 combos 91.8-95.2%) | **cliff** (n→0 by 2.5x) | **cliff** (n→0 by 2.0x) |
| Firing frequency | ~4/year | ~0.25-0.6/year | ~0.9/year |
| Free parameters vs. n | 2 params / 79 trades | 3-4 params / 3 trades | 3-4 params / 11 trades |

**Plainly: A1 is better, and by a wide margin on every axis that matters for a decision.** The
divergence+volume signal is not "worse" in the sense of a lower hit rate — its point estimate
is nominally higher (100% vs. 93.7%) — but that number carries almost no statistical weight
given the sample size, while A1's does. This is not a case of "different but comparable
signals," it's a case of one signal (A1) having enough trades to trust its number, and one
(C1/C1b) not having enough trades to trust its number even though every single trade so far
has worked.

**Is it a useful complement?** Partially, with a caveat. C1b's 11 signals fire on genuinely
different days than A1's 79 (checked: zero exact-date overlaps between the two signal
lists) — the divergence pattern requires two full swing lows and a volume climax, a slower
and rarer setup than a same-day Supertrend flip, so it would add coverage rather than
duplicate it. But because it fires roughly once a year and hasn't been tested with a large
enough sample to certify its edge, it should be treated as a "watch it fire a few more times
before trusting it," not "layer it in as a second confirmed signal today." If the user wants
to track it going forward, the honest framing is: this is a promising, mechanistically
sound, correctly-lookahead-safe candidate that needs several more years of live signals
(realistically another 15-20 firings, i.e. another 15-20 years at this frequency, or a
faster accumulation if tested across a broader universe of indices/stocks) before its
100% track record means anything statistically.

## Recommendation (Part 2)

Ship the *code*, not the *claim*. The divergence+volume detector (`detect_divergence_volume()`)
is correctly designed, lookahead-safe by construction, and every historical signal it has
ever produced has worked — that's a genuinely encouraging, mechanistically sensible result,
not nothing. But with n=3-11 across every configuration tested, it fails the brief's own
~30-trade statistical floor by a wide margin, and the "100% hit rate" headline is explicitly
called out here as a small-sample artifact, not a system to trade on. Do not present this as
competitive with or superior to A1 (93.7%, n=79, tight CI, robust parameter plateau) — A1
remains the stronger, better-evidenced signal by every measure in this study. The
recommended next step is not further parameter tuning (the sweep already shows this
signal-family's ceiling is capped by data scarcity, not by finding the "right" threshold) —
it's accumulating more history: either waiting for more live NIFTY signals to arrive (~1/year
at the useful threshold), or testing the same detector against BANKNIFTY and a basket of
liquid F&O stocks (where genuine per-instrument volume already exists in `drishti.db`,
avoiding the yfinance-proxy constraint entirely) to get to a statistically meaningful sample
faster.

# Part 4 — E-family: Supertrend(10, 2.6) bull flip × EMA20 × RSI(14) buckets (2026-07-28 session)

Run date: 2026-07-28. New signal, fully specified by the user (period=10, multiplier=2.6 --
deliberately different from the 3.0 used by A1/B1 above). Uses the exact same 42-trading-day
/ +1%/+2%/+3% / drawdown-tolerant methodology already established in Part 1
(`compute_forward_outcomes`, `walk_forward`, `bootstrap_ci`), reused verbatim, not reinvented.
Also run on the 1-hour timeframe — see the companion section in
`nifty_entry_signal_backtest_1h_report.md` — with an explicit cross-timeframe comparison
below.

```
VERDICT (daily): Real edge, on the same order as A1/A3 above — Supertrend(10,2.6) bear->bull
flip (E0, n=101, 94.1% hit1) is essentially unchanged when split into the user's 4 EMA20/RSI50
buckets, because a Supertrend bull flip mechanically co-occurs with close>EMA20 and RSI>50 in
98 of 101 historical cases (E1 = the "all three true" headline combo, n=99, 93.9% hit1, 90%
exact-binomial CI [88.4%, 97.3%]). The other 3 buckets (E2/E3/E4) have n=1, n=0, n=1
respectively across 20 years -- textbook too-small-to-trust, flagged plainly, not dressed up
despite one bucket showing a 100% hit rate. The EMA20/RSI50 split, as specified, does not
meaningfully differentiate outcomes on daily bars because it is very rarely NOT jointly true
at a ST(10,2.6) flip -- this is a structural/mechanical finding about how the three
conditions correlate, not evidence the filter "doesn't work."
```

## Strategy as tested

- **Base signal:** Supertrend(period=10, multiplier=2.6) flips from bear to bull, computed on
  daily NIFTY50 closes (separate `st26_val`/`st26_dir` columns from the existing A1/B1 family's
  Supertrend(10,3), so the two multipliers never interfere with each other).
- **At the flip candle** (single-bar snapshot — trivially lookahead-safe, no multi-day
  confirmation window, unlike A6's confluence signal), two booleans are recorded using that
  bar's own values: close vs EMA(20) (strict `>` = ABOVE; `<=` = below/at), and RSI(14) vs 50
  (strict `>` = ABOVE; `<=` = below/at). **Tie-break assumption:** the user's own phrasing
  ("above ... or below/at it") already resolves the equality case for both conditions — no
  separate assumption needed.
- **Entry / exit / target / window:** identical to A1/A3 above — `entry_price = close[t]`,
  42-trading-day forward window (*t+1* .. *t+42*), hit if daily HIGH touches +1%/+2%/+3%,
  drawdown before the hit does not disqualify.
- **Sizing:** none (signal-quality study).
- **Universe / timeframe:** NIFTY 50 index, daily candles, full ~20-year history (same dataset
  as Part 1 — 2006-08-02 → 2026-07-27, 4,951 trading days pre-forward-window-truncation).

## Core metrics — base flip + all 4 buckets (full-history, complete 42-day windows only)

| Signal | n | Hit +1% | Hit +2% | Hit +3% | Avg max adverse dip | Median days to +1% |
|---|---|---|---|---|---|---|
| **E0 — ST(10,2.6) flip, no split (reference)** | **101** | **94.1%** | 90.1% | 77.2% | 2.12% | 3 |
| **E1 — flip + close>EMA20 + RSI>50 (HEADLINE)** | **99** | **93.9%** | 89.9% | 76.8% | 2.09% | 3 |
| E2 — flip + close>EMA20 + RSI<=50 | 1 | 100.0% | 100.0% | 100.0% | 5.66% | 10 |
| E3 — flip + close<=EMA20 + RSI>50 | 0 | — | — | — | — | — |
| E4 — flip + close<=EMA20 + RSI<=50 | 1 | 100.0% | 100.0% | 100.0% | 1.93% | 1 |

**Small-sample flag, stated plainly per the user's standing rule:** E2 (n=1), E3 (n=0), E4
(n=1) are not statistically meaningful at any hit rate, including the 100% shown for E2/E4 —
a single historical observation each. These are not "promising, unproven" the way B5/B9 were
in Part 1 (which had n=7-22); they are too thin to draw *any* conclusion from, full stop. The
practical reading: 98 of 101 ST(10,2.6) bull flips in 20 years land in bucket E1 (close above
EMA20 **and** RSI above 50) — the base rate for "NOT E1" at the moment of a bull flip is only
~3%, so E2/E3/E4 will essentially never accumulate a usable sample size at this frequency.
E1 and E0 (n=99, n=101) both clear the ~30-trade floor and are carried through the full
validation gauntlet below; E2/E3/E4 are not.

## Cost assumptions used

None — same out-of-scope decision as Part 1 (signal-quality study). Definition-sensitivity
stress test (substitute for cost-doubling) below.

## Validation results

### Walk-forward (train = pre-2018, test = 2018 onward)

| Signal | Train n | Train hit1% | Test n | Test hit1% | Gap |
|---|---|---|---|---|---|
| E0_ST26_flip_base | 58 | 96.6% | 43 | 90.7% | -5.9pp |
| E1_ST26_flip_aboveEMA20_RSIabove50 | 56 | 96.4% | 43 | 90.7% | -5.7pp |

Both degrade mildly out-of-sample (a similar magnitude to A1's -3.9pp in Part 1) but stay
well above 90% in both halves — no evidence the in-sample number is an artifact of the
calmer pre-2018 regime alone.

### Regime-block consistency (non-overlapping ~5-year blocks)

| Signal | 2007–11 | 2012–16 | 2017–21 | 2022–26 |
|---|---|---|---|---|
| E0_ST26_flip_base | n=21, 100.0% | n=30, 93.3% | n=23, 95.7% | n=25, 88.0% |
| E1_ST26_flip_aboveEMA20_RSIabove50 | n=19, 100.0% | n=30, 93.3% | n=23, 95.7% | n=25, 88.0% |

A tight 88–100% band across every 5-year block, each containing at least one real
bear/correction episode — the same cross-regime plateau pattern found for A1/A3 in Part 1.

### Monte Carlo / bootstrap (5,000 resamples) and exact-binomial CI

| Signal | n | Point hit1% | 90% bootstrap CI | 90% exact-binomial CI |
|---|---|---|---|---|
| E0_ST26_flip_base | 101 | 94.1% | [90.1%, 98.0%] | [88.6%, 97.4%] |
| E1_ST26_flip_aboveEMA20_RSIabove50 | 99 | 93.9% | [89.9%, 98.0%] | [88.4%, 97.3%] |

Both intervals sit clearly above 90% at the lower bound minus a couple points — a stronger
CI position than A1/A3 achieved in Part 1 (whose lower bounds sat at 86–88%), though the same
bootstrap i.i.d.-resampling caveat from Part 1 applies (understates true uncertainty from
time-clustering of flips).

### Parameter-sensitivity sweep (period ±20%, multiplier ±~20%, E1 headline combo)

| period \ mult | 2.10 | 2.35 | 2.60 (base) | 2.85 | 3.10 |
|---|---|---|---|---|---|
| 8  | n=123, 94.3% | n=116, 94.0% | n=102, 94.1% | n=84, 94.0% | n=76, 93.4% |
| 10 | n=117, 94.0% | n=112, 94.6% | n=99, **93.9%** | n=82, 93.9% | n=77, 93.5% |
| 12 | n=117, 94.0% | n=109, 95.4% | n=97, 93.8% | n=81, 96.3% | n=75, 93.3% |

Every one of the 15 combinations lands between 93.3% and 96.3% — a genuine, tight robustness
plateau (tighter than A1's 91.8-95.2% band in Part 1). Not a curve-fit to the exact 10/2.6
parameterization.

### Bias checks

- **Lookahead bias:** none — explicitly a single-candle snapshot by design (Supertrend
  direction, close, EMA20, RSI14 are all backward-looking/recursive functions computed through
  the flip candle only; no forward-looking window used anywhere in E0-E4's construction,
  unlike A6/B5 in Part 1 which needed an explicit fix). Stated explicitly per the task
  instruction, even though it was expected to be straightforward.
- **Survivorship bias:** N/A — single index.
- **Overfitting:** low risk for E0/E1 — 2 free parameters (Supertrend period/multiplier),
  99-101 trades, demonstrated plateau above. The EMA20/RSI50 split itself adds zero
  incremental free-parameter risk to E1 specifically since it's a near-tautological subset of
  E0 (see below) — but by the same token, it also does not add real discriminating information
  on daily bars given the current data.
- **Definition-sensitivity stress test** (substitute for cost-doubling, as in Part 1):
  requiring the daily **close** (not the high) to clear +1% within the window: E1 91.9%
  vs. 93.9% high-based (-2.0pp) — mild, not a cliff, consistent with Part 1's finding for
  A1/A3.

## Where it fails

E1's misses are a subset of A1's exact miss list from Part 1 (both are Supertrend bull-flip
signals on the same underlying price series, just different multipliers) — same structural
ceiling: sudden macro/exogenous shocks that occur right after a flip that looked technically
clean (2012-03-14, 2015-08-10, 2020-01-13/pre-COVID with a 22.9% max adverse dip, 2022-05-30,
2025-02-04, 2026-02-04). No amount of EMA20/RSI50 filtering catches these, because by
construction almost every flip — hit or miss — already satisfies E1's "above EMA20, RSI>50"
condition; the filter and the miss are largely orthogonal.

## Currently live / most-recent matching setup (as of latest candle, 2026-07-27)

**No fresh E1 signal on the latest candle.** `st26_dir` has been in **bear** mode for the last
2 trading days (flipped bull→bear before 2026-07-27); the most recent E1 (and E0) fire was
**2026-06-16** at close 23,989.15. 28 trading days have elapsed since; the +1% target was
already touched (best forward gain so far +2.26%) — **this entry is already a resolved HIT**
within the historical stats even though its 42-day window hasn't formally closed. Nothing is
actionable as a *fresh* E1 entry today.

## Full per-signal table — E1 (headline: flip + close>EMA20 + RSI>50), n=99

Entry = close on the flip day. Reason column shows Supertrend/EMA20/RSI values on the flip day
and which side of each threshold it landed on (all 99 rows below are ABOVE/ABOVE by
definition of E1). Outcome shows the highest target reached and day count, or best forward
gain for misses. Max adverse dip = worst drawdown from entry before the +1% hit or window
expiry.

| Date | Entry | Reason (indicator values on signal day) | Outcome (days to reach) | Max adverse dip |
|---|---|---|---|---|
| 2006-09-20 | 3502.8 | ST=3317.4; close 3502.8 ABOVE EMA20=3426.3; RSI=65.3 ABOVE 50 | HIT +3% (d14) | 0.00% |
| 2006-12-18 | 3928.75 | ST=3671.1; close 3928.8 ABOVE EMA20=3890.8; RSI=55.0 ABOVE 50 | HIT +3% (d17) | 4.07% |
| 2007-04-13 | 3917.35 | ST=3670.6; close 3917.3 ABOVE EMA20=3802.6; RSI=57.8 ABOVE 50 | HIT +3% (d3) | 0.00% |
| 2007-06-29 | 4318.3 | ST=4163.5; close 4318.3 ABOVE EMA20=4234.9; RSI=63.4 ABOVE 50 | HIT +3% (d9) | 0.30% |
| 2007-08-30 | 4412.3 | ST=4102.0; close 4412.3 ABOVE EMA20=4303.8; RSI=55.9 ABOVE 50 | HIT +3% (d6) | 0.21% |
| 2007-10-29 | 5905.9 | ST=5267.5; close 5905.9 ABOVE EMA20=5389.6; RSI=72.7 ABOVE 50 | HIT +3% (d31) | 1.22% |
| 2008-01-01 | 6144.35 | ST=5827.9; close 6144.4 ABOVE EMA20=5958.8; RSI=63.5 ABOVE 50 | HIT +3% (d5) | 1.36% |
| 2008-04-21 | 5037.0 | ST=4660.3; close 5037.0 ABOVE EMA20=4836.2; RSI=59.5 ABOVE 50 | HIT +3% (d6) | 0.91% |
| 2008-07-23 | 4476.8 | ST=3960.7; close 4476.8 ABOVE EMA20=4158.4; RSI=60.2 ABOVE 50 | HIT +3% (d10) | 2.03% |
| 2009-03-18 | 2794.7 | ST=2588.5; close 2794.7 ABOVE EMA20=2728.2; RSI=54.2 ABOVE 50 | HIT +3% (d3) | 0.84% |
| 2009-07-17 | 4374.95 | ST=3962.3; close 4374.9 ABOVE EMA20=4229.9; RSI=57.0 ABOVE 50 | HIT +3% (d1) | 0.00% |
| 2009-09-07 | 4782.89 | ST=4465.8; close 4782.9 ABOVE EMA20=4610.2; RSI=62.9 ABOVE 50 | HIT +3% (d7) | 0.01% |
| 2009-11-11 | 5003.95 | ST=4653.2; close 5003.9 ABOVE EMA20=4881.1; RSI=57.4 ABOVE 50 | HIT +3% (d15) | 1.58% |
| 2010-03-02 | 5017.0 | ST=4768.4; close 5017.0 ABOVE EMA20=4896.9; RSI=59.3 ABOVE 50 | HIT +3% (d10) | 0.04% |
| 2010-06-04 | 5135.5 | ST=4876.3; close 5135.5 ABOVE EMA20=5054.6; RSI=54.2 ABOVE 50 | HIT +3% (d10) | 3.28% |
| 2010-12-30 | 6101.85 | ST=5887.0; close 6101.9 ABOVE EMA20=5985.6; RSI=60.4 ABOVE 50 | HIT +1% (d2) | 0.00% |
| 2011-06-01 | 5592.0 | ST=5381.8; close 5592.0 ABOVE EMA20=5513.0; RSI=54.7 ABOVE 50 | HIT +2% (d22) | 7.08% |
| 2011-06-27 | 5526.6 | ST=5273.7; close 5526.6 ABOVE EMA20=5433.6; RSI=56.1 ABOVE 50 | HIT +3% (d4) | 0.55% |
| 2011-09-07 | 5124.64 | ST=4819.6; close 5124.6 ABOVE EMA20=5057.4; RSI=51.2 ABOVE 50 | HIT +3% (d35) | 7.73% |
| 2011-10-12 | 5099.39 | ST=4748.7; close 5099.4 ABOVE EMA20=4960.2; RSI=56.4 ABOVE 50 | HIT +3% (d11) | 0.84% |
| 2011-12-02 | 5050.14 | ST=4691.5; close 5050.1 ABOVE EMA20=4943.8; RSI=54.7 ABOVE 50 | HIT +3% (d39) | 10.28% |
| 2012-01-11 | 4860.95 | ST=4653.1; close 4860.9 ABOVE EMA20=4765.1; RSI=57.1 ABOVE 50 | HIT +3% (d6) | 1.17% |
| 2012-03-14 | 5463.9 | ST=5228.8; close 5463.9 ABOVE EMA20=5354.1; RSI=60.3 ABOVE 50 | **MISS (best -0.03%)** | 10.90% |
| 2012-06-07 | 5049.64 | ST=4829.0; close 5049.6 ABOVE EMA20=4956.7; RSI=56.1 ABOVE 50 | HIT +3% (d16) | 1.09% |
| 2012-08-06 | 5282.55 | ST=5107.2; close 5282.6 ABOVE EMA20=5199.2; RSI=59.3 ABOVE 50 | HIT +3% (d11) | 0.02% |
| 2012-09-11 | 5390.0 | ST=5219.6; close 5390.0 ABOVE EMA20=5317.2; RSI=60.5 ABOVE 50 | HIT +3% (d3) | 0.00% |
| 2012-11-29 | 5825.0 | ST=5618.9; close 5825.0 ABOVE EMA20=5667.2; RSI=68.4 ABOVE 50 | HIT +3% (d23) | 0.00% |
| 2013-03-08 | 5945.7 | ST=5733.9; close 5945.7 ABOVE EMA20=5851.8; RSI=57.5 ABOVE 50 | HIT +2% (d38) | 7.88% |
| 2013-04-18 | 5783.1 | ST=5512.0; close 5783.1 ABOVE EMA20=5662.9; RSI=57.8 ABOVE 50 | HIT +3% (d6) | 0.00% |
| 2013-06-28 | 5842.2 | ST=5549.7; close 5842.2 ABOVE EMA20=5779.1; RSI=52.2 ABOVE 50 | HIT +3% (d10) | 0.34% |
| 2013-09-05 | 5592.95 | ST=5207.1; close 5592.9 ABOVE EMA20=5505.2; RSI=52.2 ABOVE 50 | HIT +3% (d2) | 0.48% |
| 2013-10-11 | 6096.2 | ST=5809.2; close 6096.2 ABOVE EMA20=5889.9; RSI=65.4 ABOVE 50 | HIT +3% (d13) | 1.04% |
| 2013-12-02 | 6217.85 | ST=5990.9; close 6217.9 ABOVE EMA20=6116.5; RSI=57.9 ABOVE 50 | HIT +3% (d5) | 1.09% |
| 2014-01-22 | 6338.95 | ST=6150.6; close 6338.9 ABOVE EMA20=6261.9; RSI=59.7 ABOVE 50 | HIT +3% (d31) | 6.40% |
| 2014-02-24 | 6186.1 | ST=5998.1; close 6186.1 ABOVE EMA20=6116.9; RSI=56.0 ABOVE 50 | HIT +3% (d7) | 0.15% |
| 2014-05-09 | 6858.8 | ST=6552.8; close 6858.8 ABOVE EMA20=6718.0; RSI=65.0 ABOVE 50 | HIT +3% (d2) | 0.00% |
| 2014-07-22 | 7767.85 | ST=7489.5; close 7767.9 ABOVE EMA20=7609.7; RSI=64.0 ABOVE 50 | HIT +3% (d26) | 2.93% |
| 2014-08-18 | 7874.25 | ST=7601.0; close 7874.2 ABOVE EMA20=7706.0; RSI=62.5 ABOVE 50 | HIT +3% (d11) | 0.23% |
| 2014-10-29 | 8090.45 | ST=7855.5; close 8090.4 ABOVE EMA20=7956.3; RSI=60.4 ABOVE 50 | HIT +3% (d3) | 0.06% |
| 2014-12-22 | 8324.0 | ST=8018.3; close 8324.0 ABOVE EMA20=8298.5; RSI=51.4 ABOVE 50 | HIT +3% (d20) | 2.11% |
| 2015-01-15 | 8494.1 | ST=8147.0; close 8494.1 ABOVE EMA20=8292.0; RSI=61.2 ABOVE 50 | HIT +3% (d5) | 0.49% |
| 2015-02-18 | 8869.1 | ST=8563.5; close 8869.1 ABOVE EMA20=8691.7; RSI=64.1 ABOVE 50 | HIT +2% (d11) | 2.25% |
| 2015-04-06 | 8659.9 | ST=8310.6; close 8659.9 ABOVE EMA20=8599.8; RSI=52.4 ABOVE 50 | HIT +2% (d5) | 0.84% |
| 2015-05-20 | 8423.2 | ST=8096.5; close 8423.2 ABOVE EMA20=8325.1; RSI=53.3 ABOVE 50 | HIT +2% (d41) | 5.73% |
| 2015-06-22 | 8353.1 | ST=8031.9; close 8353.1 ABOVE EMA20=8178.7; RSI=58.7 ABOVE 50 | HIT +3% (d18) | 1.88% |
| 2015-08-10 | 8607.55 | ST=8331.0; close 8607.5 ABOVE EMA20=8507.2; RSI=59.4 ABOVE 50 | **MISS (best -0.60%)** | 12.41% |
| 2015-10-05 | 8119.3 | ST=7700.5; close 8119.3 ABOVE EMA20=7921.3; RSI=58.3 ABOVE 50 | HIT +2% (d10) | 0.28% |
| 2015-12-17 | 7844.35 | ST=7562.8; close 7844.4 ABOVE EMA20=7788.2; RSI=51.9 ABOVE 50 | HIT +1% (d6) | 1.41% |
| 2016-03-02 | 7368.85 | ST=6967.1; close 7368.9 ABOVE EMA20=7195.8; RSI=55.5 ABOVE 50 | HIT +3% (d11) | 0.00% |
| 2016-05-26 | 8069.65 | ST=7747.0; close 8069.6 ABOVE EMA20=7837.5; RSI=65.8 ABOVE 50 | HIT +3% (d26) | 0.00% |
| 2016-12-30 | 8185.8 | ST=7925.0; close 8185.8 ABOVE EMA20=8103.7; RSI=53.8 ABOVE 50 | HIT +3% (d10) | 0.64% |
| 2017-07-10 | 9771.05 | ST=9523.4; close 9771.0 ABOVE EMA20=9613.3; RSI=69.2 ABOVE 50 | HIT +3% (d13) | 0.00% |
| 2017-09-01 | 9974.4 | ST=9712.1; close 9974.4 ABOVE EMA20=9882.5; RSI=56.7 ABOVE 50 | HIT +3% (d36) | 1.14% |
| 2017-10-10 | 10016.95 | ST=9790.7; close 10017.0 ABOVE EMA20=9941.4; RSI=56.2 ABOVE 50 | HIT +3% (d10) | 0.61% |
| 2017-11-24 | 10389.7 | ST=10175.5; close 10389.7 ABOVE EMA20=10290.3; RSI=61.1 ABOVE 50 | HIT +3% (d35) | 3.43% |
| 2017-12-11 | 10322.25 | ST=10069.8; close 10322.2 ABOVE EMA20=10242.0; RSI=55.8 ABOVE 50 | HIT +3% (d20) | 2.40% |
| 2018-04-05 | 10325.15 | ST=9941.2; close 10325.1 ABOVE EMA20=10238.0; RSI=52.3 ABOVE 50 | HIT +3% (d12) | 0.33% |
| 2018-05-31 | 10736.15 | ST=10421.6; close 10736.1 ABOVE EMA20=10628.7; RSI=57.8 ABOVE 50 | HIT +3% (d30) | 1.73% |
| 2018-07-10 | 10947.25 | ST=10670.7; close 10947.2 ABOVE EMA20=10760.1; RSI=63.3 ABOVE 50 | HIT +3% (d13) | 0.22% |
| 2018-11-02 | 10553.0 | ST=10050.3; close 10553.0 ABOVE EMA20=10428.2; RSI=51.3 ABOVE 50 | HIT +3% (d17) | 1.07% |
| 2018-12-17 | 10888.35 | ST=10533.1; close 10888.4 ABOVE EMA20=10706.6; RSI=59.0 ABOVE 50 | HIT +2% (d37) | 3.25% |
| 2019-02-06 | 11062.45 | ST=10701.1; close 11062.5 ABOVE EMA20=10847.5; RSI=64.2 ABOVE 50 | HIT +3% (d26) | 4.31% |
| 2019-03-05 | 10987.45 | ST=10591.0; close 10987.5 ABOVE EMA20=10827.1; RSI=60.6 ABOVE 50 | HIT +3% (d5) | 0.00% |
| 2019-05-20 | 11828.25 | ST=11285.7; close 11828.2 ABOVE EMA20=11465.9; RSI=63.2 ABOVE 50 | HIT +2% (d10) | 1.81% |
| 2019-09-20 | 11274.2 | ST=10526.0; close 11274.2 ABOVE EMA20=10974.2; RSI=58.6 ABOVE 50 | HIT +3% (d1) | 0.00% |
| 2019-12-17 | 12165.0 | ST=11842.9; close 12165.0 ABOVE EMA20=11989.3; RSI=63.0 ABOVE 50 | HIT +2% (d23) | 0.01% |
| 2020-01-13 | 12329.55 | ST=12007.5; close 12329.5 ABOVE EMA20=12159.5; RSI=60.4 ABOVE 50 | **MISS (best +0.82%)** | **22.88%** |
| 2020-02-05 | 12089.15 | ST=11613.0; close 12089.1 ABOVE EMA20=12059.3; RSI=50.5 ABOVE 50 | HIT +1% (d5) | 0.81% |
| 2020-04-28 | 9380.9 | ST=8507.6; close 9380.9 ABOVE EMA20=9130.2; RSI=52.5 ABOVE 50 | HIT +3% (d2) | 0.00% |
| 2020-06-01 | 9826.15 | ST=9171.7; close 9826.1 ABOVE EMA20=9274.1; RSI=63.4 ABOVE 50 | HIT +3% (d2) | 0.02% |
| 2020-10-01 | 11416.95 | ST=10921.4; close 11417.0 ABOVE EMA20=11288.4; RSI=54.7 ABOVE 50 | HIT +3% (d3) | 0.00% |
| 2020-12-28 | 13873.2 | ST=13350.0; close 13873.2 ABOVE EMA20=13433.7; RSI=70.2 ABOVE 50 | HIT +3% (d9) | 0.10% |
| 2021-02-02 | 14647.85 | ST=13822.1; close 14647.9 ABOVE EMA20=14198.9; RSI=61.3 ABOVE 50 | HIT +3% (d4) | 0.50% |
| 2021-05-18 | 15108.1 | ST=14541.6; close 15108.1 ABOVE EMA20=14750.9; RSI=60.6 ABOVE 50 | HIT +3% (d9) | 1.48% |
| 2022-01-03 | 17625.7 | ST=16909.5; close 17625.7 ABOVE EMA20=17237.9; RSI=59.6 ABOVE 50 | HIT +3% (d7) | 0.18% |
| 2022-03-14 | 16871.3 | ST=15811.1; close 16871.3 ABOVE EMA20=16723.7; RSI=50.7 ABOVE 50 | HIT +3% (d6) | 1.87% |
| 2022-05-30 | 16661.4 | ST=15833.3; close 16661.4 ABOVE EMA20=16367.6; RSI=54.1 ABOVE 50 | **MISS (best +0.79%)** | 8.87% |
| 2022-07-06 | 15989.8 | ST=15297.3; close 15989.8 ABOVE EMA20=15850.7; RSI=52.3 ABOVE 50 | HIT +3% (d10) | 0.00% |
| 2022-09-12 | 17936.35 | ST=17412.0; close 17936.3 ABOVE EMA20=17599.7; RSI=65.0 ABOVE 50 | HIT +2% (d39) | 6.63% |
| 2022-10-20 | 17563.95 | ST=16913.1; close 17564.0 ABOVE EMA20=17318.9; RSI=56.8 ABOVE 50 | HIT +3% (d7) | 0.25% |
| 2023-04-05 | 17557.05 | ST=16986.4; close 17557.0 ABOVE EMA20=17261.6; RSI=58.4 ABOVE 50 | HIT +3% (d15) | 0.31% |
| 2023-09-07 | 19727.05 | ST=19277.0; close 19727.0 ABOVE EMA20=19474.6; RSI=63.6 ABOVE 50 | HIT +2% (d5) | 0.00% |
| 2023-11-08 | 19443.5 | ST=19014.3; close 19443.5 ABOVE EMA20=19357.9; RSI=51.6 ABOVE 50 | HIT +3% (d14) | 0.59% |
| 2024-02-16 | 22040.7 | ST=21377.8; close 22040.7 ABOVE EMA20=21748.8; RSI=60.2 ABOVE 50 | HIT +3% (d35) | 0.75% |
| 2024-04-01 | 22462.0 | ST=21853.7; close 22462.0 ABOVE EMA20=22139.4; RSI=60.9 ABOVE 50 | HIT +3% (d42) | 0.70% |
| 2024-04-29 | 22643.4 | ST=21954.2; close 22643.4 ABOVE EMA20=22377.5; RSI=59.1 ABOVE 50 | HIT +3% (d24) | 3.63% |
| 2024-05-23 | 22967.65 | ST=22188.0; close 22967.7 ABOVE EMA20=22434.4; RSI=68.2 ABOVE 50 | HIT +3% (d18) | 2.40% |
| 2024-06-13 | 23398.9 | ST=22450.1; close 23398.9 ABOVE EMA20=22874.3; RSI=60.5 ABOVE 50 | HIT +3% (d10) | 0.28% |
| 2024-08-26 | 25010.6 | ST=24387.8; close 25010.6 ABOVE EMA20=24565.3; RSI=64.6 ABOVE 50 | HIT +3% (d19) | 0.18% |
| 2024-11-25 | 24221.9 | ST=23365.8; close 24221.9 ABOVE EMA20=24038.9; RSI=51.1 ABOVE 50 | HIT +2% (d8) | 1.44% |
| 2025-02-04 | 23739.25 | ST=22870.2; close 23739.2 ABOVE EMA20=23379.6; RSI=57.0 ABOVE 50 | **MISS (best +0.55%)** | 8.41% |
| 2025-03-18 | 22834.3 | ST=22089.3; close 22834.3 ABOVE EMA20=22623.2; RSI=54.0 ABOVE 50 | HIT +3% (d4) | 0.12% |
| 2025-04-15 | 23328.55 | ST=22275.2; close 23328.5 ABOVE EMA20=22948.0; RSI=56.0 ABOVE 50 | HIT +3% (d3) | 0.24% |
| 2025-08-20 | 25050.55 | ST=24475.3; close 25050.5 ABOVE EMA20=24801.3; RSI=57.0 ABOVE 50 | HIT +3% (d41) | 2.58% |
| 2025-09-12 | 25114.0 | ST=24624.0; close 25114.0 ABOVE EMA20=24824.4; RSI=61.0 ABOVE 50 | HIT +3% (d25) | 0.26% |
| 2025-10-09 | 25181.8 | ST=24645.4; close 25181.8 ABOVE EMA20=24977.8; RSI=58.0 ABOVE 50 | HIT +3% (d9) | 0.48% |
| 2025-11-17 | 26013.45 | ST=25447.4; close 26013.5 ABOVE EMA20=25706.0; RSI=65.1 ABOVE 50 | HIT +1% (d8) | 0.66% |
| 2026-02-04 | 25776.0 | ST=24643.0; close 25776.0 ABOVE EMA20=25496.5; RSI=54.6 ABOVE 50 | **MISS (best +0.91%)** | 13.94% |
| 2026-04-08 | 23997.35 | ST=22547.3; close 23997.3 ABOVE EMA20=23426.5; RSI=53.9 ABOVE 50 | HIT +2% (d7) | 1.84% |

93/99 = 93.9% HIT +1%. 6 misses: 2012-03-14, 2015-08-10, 2020-01-13 (worst, pre-COVID,
22.88% max adverse dip), 2022-05-30, 2025-02-04, 2026-02-04.

*(Note: the base E0 reference row, n=101, adds 2 additional flips not in E1 — 2008-11-03 and
2011-02-17 — where close/RSI landed on the "below/at" side of one threshold; see the CSV
export or the script's `--export-csv` output for E0's full table if needed; both of those 2
extra rows were HITs, which is why E0's point hit-rate (94.1%) is a hair above E1's (93.9%)
despite E1 being "E0 restricted to a subset.")*

## Cross-timeframe comparison — does E1 behave consistently between daily and 1h?

See the full validation detail in `nifty_entry_signal_backtest_1h_report.md`'s companion
section. Headline comparison:

| | Daily E1 | 1h E1 |
|---|---|---|
| n | 99 | 68 |
| Hit +1% | 93.9% | 69.1% |
| 90% exact-binomial CI | [88.4%, 97.3%] | [58.7%, 78.3%] |
| Forward window | 42 trading days (~2 months) | 70 one-hour candles (10 trading days, ~2 weeks) |
| E1 vs E0 (base) lift | -0.2pp (E1 slightly *below* E0) | +3.3pp (E1 *above* E0) |
| Bucket-count split (E1/E2/E3/E4) | 99/1/0/1 | 68/7/0/4 |

**The CIs do not overlap at all** — the same pattern the earlier BB+z_ema200 combo showed in
the 1h session, and for a similar root cause: the forward window is ~4.2x shorter in calendar
time on 1h (2 weeks vs. ~2 months), and the 1h window-length sweep (see companion report)
shows hit rate still climbing at 15 trading days (76.1%) without approaching 94%. Unlike the
BB+z_ema200 case, though, the EMA20/RSI50 split itself is **not** the source of the
divergence here — on *both* timeframes E1 barely differs from the unfiltered E0 base rate
(same near-tautological "flip implies E1" mechanism holds on 1h too, just slightly less
strongly: 86% of 1h flips land in E1 vs. 98% of daily flips). The real cross-timeframe gap is
in the **base Supertrend-flip hit rate itself** (94.1% daily vs. 65.8% 1h for E0), which is a
timeframe/window-length effect, not something introduced by the EMA/RSI filter.

## Recommendation

Ship E1 as a daily-timeframe candidate alongside A1/A3 — it clears the ~90% bar more
comfortably than either (93.9% point estimate, CI lower bound 88.4%, tightest parameter
plateau of the three: 93.3-96.3% across 15 period/multiplier combinations), and its failure
mode is identical and well-understood (exogenous shocks, not filterable by any trend metric
tested). Do **not** present the EMA20/RSI50 split as adding real discriminating power on
daily bars — it doesn't, because it's almost always true when the base signal fires; if the
user wants a genuinely differentiating trend/momentum filter, EMA200-slope (B1, already in
Part 1) or z-score-based filters are better candidates since they aren't near-tautological
with the base signal. Do not deploy this on 1-hour bars expecting daily-like performance —
confirmed here for a third time in this project that Supertrend-based signals' calendar-time
window matters far more than "same N periods" implies across timeframes.

# Part 5 — F-family: EMA20-gap two-sided mean-reversion, LONG + SHORT (2026-07-28 session)

Run date: 2026-07-28. This is the first **two-sided** signal family tested in this study —
every prior signal (A–E) is long-only. Uses the exact same 42-trading-day / +1%/+2%/+3% /
drawdown-tolerant methodology established in Part 1, generalized to support a short-side
target/adverse-move convention (`compute_forward_outcomes_directional`, new this session;
`walk_forward`, `bootstrap_ci`, `regime_blocks` reused unchanged since they only depend on the
generic `hit_1pct`/`date` keys already present in both long and short result rows). Also run
on the 1-hour timeframe — see the companion section in `nifty_entry_signal_backtest_1h_report.md`
— with an explicit cross-timeframe comparison below.

```
VERDICT (daily): Real edge on the LONG side, fragile-to-not-real on the SHORT side — a
genuinely asymmetric result, not the same signal mirrored both ways. F1 (long: gap_pct crosses
below -3%, betting on a bounce) hits +1% in 93.7% of 111 historical cases (90% exact-binomial
CI [88.5%, 97.0%]), holds up out-of-sample (walk-forward test 97.0% vs. train 92.3% — improves,
not degrades), stays in a 90-100% band across all four ~5-year regime blocks, and sits on a
genuine parameter plateau (92-96% hit rate across the 2%-4% threshold sweep). F2 (short: gap_pct
crosses above +3%, betting on a fade) hits -1% in only 77.0% of 148 cases (90% CI [70.6%,
82.6%]) — clearly below the ~90% bar — degrades out-of-sample (walk-forward test 71.7% vs.
train 79.4%, a real not a noise-sized gap), and shows a genuine multi-decade DECLINE across
regime blocks (84.2% -> 74.3% -> 67.6% -> 73.3%). F2's failure mode is structurally identifiable
and severe: it loses hardest exactly during strong post-crash V-shaped rallies (2009 post-GFC,
2020 post-COVID) where "overbought" persists for months rather than reverting — shorting a
market that just fell 50%+ and is recovering violently is a fundamentally different bet than
shorting a market that is merely extended in an otherwise normal uptrend, and gap_pct alone
cannot tell those two regimes apart. Ship F1 as a genuine long-side candidate alongside A1/A3/E1;
do not ship F2 as-is.
```

## Strategy as tested

- **Indicator:** `gap_pct = (close - EMA20) / EMA20 * 100` — how far today's close sits
  above/below its own EMA(20), as a percentage. Both inputs are known at day *t*'s own close;
  trivially lookahead-safe, identical discipline to every other indicator in this study.
- **F1 (LONG):** fires the first day `gap_pct` crosses BELOW -3% (`gap_pct[t] < -3` and
  `gap_pct[t-1] >= -3`) — close has fallen more than 3% under its EMA20. Bet: mean-reversion
  UP. `entry_price = close[t]`. Target: does the daily HIGH touch `entry x 1.01` (+1%, also
  tracked at +2%/+3%) within the next 42 trading days? `max_adverse_dip_pct` = worst DOWN move
  (entry vs. window LOW) observed before the hit (or before window expiry) — identical
  semantics to every long-only signal in Parts 1 and 4.
- **F2 (SHORT):** fires the first day `gap_pct` crosses ABOVE +3% (`gap_pct[t] > 3` and
  `gap_pct[t-1] <= 3`) — close has risen more than 3% over its EMA20. Bet: mean-reversion DOWN.
  `entry_price = close[t]`. Target: does the daily LOW touch `entry x 0.99` (-1%, also tracked
  at -2%/-3%) within the next 42 trading days? `max_adverse_dip_pct` here means the worst UP
  move (entry vs. window HIGH) before the hit (or before window expiry) — deliberately
  INVERTED from the long convention, since "adverse" for a short position means price rising
  against it, not falling. This inversion is implemented in a new function,
  `compute_forward_outcomes_directional()`, kept separate from the existing long-only
  `compute_forward_outcomes()` so none of A-E's results are at risk of being touched.
- **Threshold-crossing convention:** both F1 and F2 fire once on first breach, the same
  convention already used by A2 (RSI crosses below 25) elsewhere in this script — neither
  re-fires every day the gap stays beyond 3%.
- **Assumption stated (edge case in the brief, resolved conservatively rather than stalled
  on):** a single scalar `gap_pct` cannot simultaneously be below -3% and above +3%, so a long
  and a short can never fire on the same day — no tie-break rule was needed. A gap that jumps
  from inside the band straight past the opposite threshold in one candle (e.g. -2% to +3.5%)
  is still caught correctly as a fresh SHORT breach by the existing `>=`/`<=` boundary logic
  in the crossing test — no special-casing was required in practice.
- **Sizing:** none (signal-quality study, consistent with every other signal in this file).
- **Universe / timeframe:** NIFTY 50 index, daily candles, full ~20-year history (same dataset
  as Parts 1 and 4 — 2006-08-02 -> 2026-07-27, 4,951 trading days pre-forward-window-truncation).

## Core metrics (full-history, complete 42-day windows only)

| Signal | n | Hit +1% | Hit +2% | Hit +3% | Avg max adverse move | Median days to +1% |
|---|---|---|---|---|---|---|
| **F1 — LONG (gap_pct crosses below -3%)** | **111** | **93.7%** | 86.5% | 82.0% | 3.09% | 1 |
| **F2 — SHORT (gap_pct crosses above +3%)** | **148** | **77.0%** | 62.8% | 53.4% | 4.28% | 3 |

Both n clear the ~30-trade floor comfortably (111 and 148), so both are carried through the
full validation gauntlet below — unlike several small-sample families in Parts 1/4, there is
no small-sample flag needed here on the daily timeframe.

## Cost assumptions used

None — same out-of-scope decision as Parts 1 and 4 (signal-quality study). Definition-
sensitivity stress test (substitute for cost-doubling) below.

## Validation results

### Walk-forward (train = pre-2018, test = 2018 onward — includes COVID crash, 2022 correction)

| Signal | Train n | Train hit1% | Test n | Test hit1% | Gap |
|---|---|---|---|---|---|
| F1_ema20gap_long | 78 | 92.3% | 33 | 97.0% | **+4.6pp** |
| F2_ema20gap_short | 102 | 79.4% | 46 | 71.7% | **-7.7pp** |

F1 improves out-of-sample — the same good sign against overfitting seen for A3 in Part 1 (no
evidence the in-sample number was inflated by fitting to the calmer early regime). F2 degrades
out-of-sample by a meaningfully larger margin than any long-only signal's walk-forward gap in
Parts 1 or 4 — combined with the regime-block trend below, this is the strongest single piece
of evidence that F2 is not a stable, tradeable edge as specified.

### Regime-block consistency (non-overlapping ~5-year blocks, a second cut at walk-forward)

| Signal | 2007–11 | 2012–16 | 2017–21 | 2022–26 |
|---|---|---|---|---|
| F1_ema20gap_long | n=51, 90.2% | n=26, 96.2% | n=16, 100.0% | n=17, 94.1% |
| F2_ema20gap_short | n=57, 84.2% | n=35, 74.3% | n=34, 67.6% | n=15, 73.3% |

F1 stays in a tight 90-100% band across all four blocks — a genuine cross-regime plateau, on
the same order as A1/A3/E1 in Parts 1 and 4. F2 shows a real, monotonic-ish DECLINE from
84.2% in the earliest block to 67.6%/73.3% in the two most recent blocks — this is not noise
around a stable mean, it reads as a structural weakening of the short-side edge over time
(plausibly: 20 years ago a 3%-over-EMA20 print was a rarer, more genuinely "stretched" signal
in a less liquid, more volatile market; NIFTY's post-2017 character trades further above/below
EMA20 for longer during strong trending phases without reverting, especially during and after
V-shaped recoveries).

### Monte Carlo / bootstrap (5,000 resamples) and exact-binomial CI

| Signal | n | Point hit1% | 90% bootstrap CI | 90% exact-binomial CI |
|---|---|---|---|---|
| F1_ema20gap_long | 111 | 93.7% | [89.2%, 97.3%] | [88.5%, 97.0%] |
| F2_ema20gap_short | 148 | 77.0% | [70.9%, 82.4%] | [70.6%, 82.6%] |

F1's CI sits close to A1/A3's Part 1 position (lower bound 88-89%, right at/near the ~90% bar,
not confidently above it — same honest caveat as Part 1's verdict). F2's CI sits entirely and
unambiguously BELOW 90% at both bounds — this is not a borderline case, F2 is confidently a
sub-90% signal at the historical sample size. Same bootstrap i.i.d.-resampling caveat as every
other family in this study applies (understates true uncertainty from time-clustering of
signals — several F1/F2 fires cluster in the same volatile month, e.g. five separate F1 fires
in 2008 alone).

### Parameter-sensitivity sweep (threshold at 2%/2.5%/3%/3.5%/4%, both sides)

| Threshold | n (long) | Hit1% (long) | n (short) | Hit1% (short) |
|---|---|---|---|---|
| 2.0% | 176 | 93.8% | 239 | 77.8% |
| 2.5% | 149 | 93.3% | 182 | 78.0% |
| **3.0% (base)** | **111** | **93.7%** | **148** | **77.0%** |
| 3.5% | 89 | 95.5% | 92 | 78.3% |
| 4.0% | 64 | 92.2% | 69 | 84.1% |

Both sides sit on a genuine robustness plateau, not a curve-fit cliff — F1 stays in a tight
92.2-95.5% band across the full 2%-4% sweep, and F2 stays in a 77.0-84.1% band (its highest
point, 84.1% at the 4% threshold, is driven by a smaller, more genuinely extreme sample, n=69).
Neither signal is an artifact of the exact 3% cutoff: F1 is robustly strong at every threshold
tested, and F2 is robustly BELOW the ~90% bar at every threshold tested — the threshold choice
does not rescue F2.

### Bias checks

- **Lookahead bias:** none found — `gap_pct` is a same-bar function of `close[t]` and
  `EMA20[t]` (itself a backward-looking recursive function), and the crossing test only
  compares `gap_pct[t]` against `gap_pct[t-1]`. No forward-looking window is used anywhere in
  F1/F2's construction, unlike A6/B5 in Part 1 which needed an explicit fix — stated explicitly
  per the task instruction even though it was expected to be straightforward.
- **Survivorship bias:** N/A — single index (NIFTY 50), not a basket or membership backtest.
- **Overfitting:** low risk for F1 — a single free parameter (the 3% threshold), 111 trades, a
  demonstrated plateau across the full sweep. F2 carries the same low structural
  overfitting risk (also 1 free parameter, 148 trades) but the concern here isn't
  overfitting — it's that the underlying bet (fade an overbought market) is genuinely weaker
  and regime-dependent, which no amount of parameter tuning fixes (confirmed by the sweep
  above never lifting F2 anywhere near 90%).
- **Definition-sensitivity stress test** (substitute for cost-doubling, as in Parts 1 and 4):
  requiring the daily **close** (not the high/low) to clear the ±1% target within the window —
  F1: 88.3% vs. 93.7% high-based (-5.4pp); F2: 68.9% vs. 77.0% low-based (-8.1pp). Both degrade
  mildly-to-moderately under the stricter proxy (larger than A1/A3/E1's ~2pp degradation in
  Parts 1/4, meaning a nontrivial share of F1/F2 hits are same-day-recovery wicks rather than
  clean multi-day closes) — this stretches, but does not reverse, the long/short asymmetry
  already established above (F1 remains clearly the stronger side even under the stricter
  test).

## Where it fails

**F1 (long) misses — 7 of 111, worst by adverse dip:**

| Date | Entry | Best fwd. move | Max adverse dip | Note |
|---|---|---|---|---|
| 2008-09-26 | 3985.25 | +0.38% | 43.47% | Lehman-collapse week — GFC acute phase |
| 2008-01-18 | 5705.30 | -0.01% | 22.03% | Jan 2008 crash (global selloff) |
| 2008-06-02 | 4739.60 | +0.14% | 20.03% | GFC — oil-price-shock leg down |
| 2008-02-06 | 5322.55 | +0.86% | 16.04% | GFC aftershock |
| 2011-08-04 | 5331.80 | -1.92% | 11.47% | 2011 US-debt-downgrade global selloff |
| 2016-01-07 | 7568.30 | +0.87% | 9.81% | Jan 2016 China-yuan-devaluation scare |
| 2026-03-06 | 24450.45 | +0.62% | 9.28% | most recent miss |

5 of F1's 7 misses cluster in the 2008 GFC — the same exogenous-macro-shock pattern already
identified as A1/A3/E1's structural ceiling in Parts 1 and 4: a technically clean
mean-reversion setup fired the session before (or during) a shock too large and fast-moving
for any EMA-distance-based signal to price in. This is a shared, honest limitation across
every signal family tested in this project, not something specific to F1.

**F2 (short) misses — 34 of 148 (23%), worst by adverse move (i.e. worst UP move against the
short):**

| Date | Entry | Best fwd. move | Max adverse move (UP) | Note |
|---|---|---|---|---|
| 2009-03-23 | 2939.90 | +0.86% | 53.39% | post-GFC-bottom V-shaped rally (worst) |
| 2009-04-29 | 3473.95 | -0.14% | 35.10% | same 2009 rally, second leg |
| 2007-08-31 | 4464.00 | +0.41% | 33.87% | pre-GFC momentum blow-off |
| 2009-05-15 | 3671.65 | -0.04% | 27.82% | same 2009 rally, third leg |
| 2007-09-19 | 4732.35 | +0.24% | 27.04% | pre-GFC momentum blow-off |
| 2020-11-06 | 12263.55 | -0.85% | 16.25% | post-COVID-vaccine-news rally |
| 2020-11-26 | 12987.00 | +0.56% | 13.60% | same 2020 rally, continuation |
| 2012-01-17 | 4967.30 | +0.73% | 13.34% | Jan 2012 relief rally |
| 2014-03-28 | 6695.90 | +0.86% | 12.96% | pre-election 2014 rally |
| 2020-06-18 | 10091.65 | +0.19% | 12.70% | 2020 V-recovery, mid-leg |
| 2020-12-01 | 13109.05 | +0.96% | 12.54% | 2020 V-recovery, continuation |
| 2020-12-04 | 13258.55 | +0.96% | 12.48% | 2020 V-recovery, continuation |

This is not a random scatter of misses — **F2's worst losses cluster almost entirely in two
specific historical episodes: the 2009 post-GFC-bottom rally (5 of the 10 worst misses) and
the Nov-Dec 2020 post-COVID-vaccine V-shaped recovery (4 of the 10 worst misses).** Both are
V-shaped-recovery regimes where NIFTY had just fallen 30-50%+ and was recovering violently —
"overbought vs. EMA20" persisted for weeks to months without reverting, because the move was a
recovery off a crash floor, not an extension of a normal uptrend. `gap_pct` alone cannot tell
these two situations apart, and this is F2's real, identifiable, structural failure mode — not
an exogenous-shock problem like F1/A1/A3/E1, but a "wrong regime for mean-reversion shorting"
problem. Also notable: F2 fired zero times in all of calendar 2024 — a real quiet stretch, not
a data gap (confirmed: EMA20 and RSI14 remain populated throughout 2024 in the underlying data;
NIFTY simply never closed more than 3% above its own EMA20 during that year).

## Currently live / most-recent matching setup (as of latest candle, 2026-07-27)

**No fresh F1 or F2 signal on the latest candle.** `gap_pct` on 2026-07-27 is **-0.15%**
(close 23,995.95 vs. EMA20 24,031.93) — well inside the ±3% band, nowhere near either
threshold.

- **F1 (long):** last fired **2026-03-27** at close 22,819.60 (gap_pct -3.85%). 80 trading
  days have elapsed since (window is 42 days) — **already resolved as a HIT** (+1% touched at
  day 5, +3% touched at day 6, max adverse dip only 2.79% along the way). Nothing is
  actionable as a *fresh* F1 entry today.
- **F2 (short):** last fired **2025-05-15** at close 25,062.10 (gap_pct +3.32%). 297 trading
  days have elapsed since — long since resolved (**HIT**: +1% at day 3, +2% at day 5, +3%
  never touched, max adverse UP-move only 0.03%). Nothing is actionable as a *fresh* F2 entry
  today.

## Full per-signal table — F1 (LONG, gap_pct crosses below -3%), n=111

Entry = close on the crossing day. Outcome shows the highest target reached and day count
(day 1 = next trading day), or the best forward gain achieved anywhere in the 42-day window
for misses. Max adverse move = worst DOWN move from entry observed before the +1% hit (or
before window expiry if it never hit) — same convention as every long-only table in Parts 1/4.

| Date | Entry | EMA20 | gap_pct | Outcome (days to reach) | Max adverse move |
|---|---|---|---|---|---|
| 2006-12-12 | 3716.90 | 3904.40 | -4.80% | HIT +3% (d2) | 1.59% |
| 2007-02-23 | 3938.95 | 4088.40 | -3.65% | HIT +3% (d38) | 9.76% |
| 2007-03-09 | 3718.00 | 3860.20 | -3.68% | HIT +3% (d9) | 0.11% |
| 2007-03-14 | 3641.10 | 3821.80 | -4.73% | HIT +3% (d5) | 0.29% |
| 2007-04-02 | 3633.60 | 3776.10 | -3.77% | HIT +3% (d2) | 0.04% |
| 2007-08-16 | 4178.60 | 4391.20 | -4.84% | HIT +3% (d7) | 4.22% |
| 2007-11-22 | 5519.35 | 5697.90 | -3.13% | HIT +3% (d2) | 0.08% |
| 2008-01-18 | 5705.30 | 6042.80 | -5.58% | MISS (best -0.01%) | 22.03% |
| 2008-02-06 | 5322.55 | 5488.50 | -3.02% | MISS (best +0.86%) | 16.04% |
| 2008-03-03 | 4953.00 | 5218.80 | -5.09% | HIT +3% (d34) | 6.71% |
| 2008-04-04 | 4647.00 | 4803.70 | -3.26% | HIT +3% (d1) | 0.39% |
| 2008-05-26 | 4875.05 | 5027.80 | -3.04% | HIT +1% (d1) | 0.59% |
| 2008-05-29 | 4835.30 | 4986.90 | -3.04% | HIT +1% (d1) | 0.04% |
| 2008-06-02 | 4739.60 | 4953.30 | -4.31% | MISS (best +0.14%) | 20.03% |
| 2008-06-19 | 4504.25 | 4670.30 | -3.55% | HIT +3% (d38) | 15.85% |
| 2008-07-11 | 4049.00 | 4206.40 | -3.74% | HIT +3% (d7) | 1.11% |
| 2008-08-28 | 4214.00 | 4353.40 | -3.20% | HIT +3% (d1) | 0.00% |
| 2008-09-12 | 4228.45 | 4368.10 | -3.20% | HIT +1% (d6) | 10.14% |
| 2008-09-26 | 3985.25 | 4201.70 | -5.15% | MISS (best +0.38%) | 43.47% |
| 2008-11-05 | 2994.95 | 3138.10 | -4.56% | HIT +3% (d3) | 4.50% |
| 2008-11-11 | 2938.65 | 3089.80 | -4.89% | HIT +3% (d22) | 4.89% |
| 2008-12-01 | 2682.90 | 2822.30 | -4.94% | HIT +3% (d3) | 4.18% |
| 2009-01-09 | 2873.00 | 2961.90 | -3.00% | HIT +3% (d24) | 7.36% |
| 2009-01-15 | 2736.70 | 2899.30 | -5.61% | HIT +3% (d1) | 0.46% |
| 2009-01-21 | 2706.15 | 2862.90 | -5.48% | HIT +3% (d4) | 0.91% |
| 2009-02-20 | 2736.40 | 2829.00 | -3.27% | HIT +3% (d15) | 2.15% |
| 2009-03-02 | 2674.60 | 2794.50 | -4.29% | HIT +3% (d8) | 5.05% |
| 2009-07-06 | 4165.70 | 4327.50 | -3.74% | HIT +3% (d8) | 0.24% |
| 2009-07-08 | 4078.90 | 4293.00 | -4.99% | HIT +3% (d5) | 2.50% |
| 2009-10-28 | 4826.14 | 4980.20 | -3.09% | HIT +3% (d9) | 5.96% |
| 2010-01-27 | 4853.10 | 5133.10 | -5.45% | HIT +3% (d23) | 0.58% |
| 2010-02-04 | 4845.35 | 5016.90 | -3.42% | HIT +3% (d16) | 3.51% |
| 2010-02-10 | 4757.20 | 4915.50 | -3.22% | HIT +3% (d4) | 0.00% |
| 2010-05-07 | 5018.05 | 5205.70 | -3.61% | HIT +3% (d1) | 0.00% |
| 2010-05-19 | 4919.64 | 5138.40 | -4.26% | HIT +3% (d7) | 0.00% |
| 2010-05-25 | 4806.75 | 5060.50 | -5.01% | HIT +3% (d2) | 0.00% |
| 2010-11-19 | 5890.30 | 6097.40 | -3.40% | HIT +3% (d11) | 0.00% |
| 2010-11-24 | 5865.75 | 6054.50 | -3.12% | HIT +3% (d8) | 2.99% |
| 2010-12-09 | 5766.50 | 5953.00 | -3.13% | HIT +3% (d3) | 0.79% |
| 2011-01-10 | 5762.85 | 5996.90 | -3.90% | HIT +1% (d1) | 1.12% |
| 2011-01-13 | 5751.90 | 5943.10 | -3.22% | HIT +1% (d1) | 1.95% |
| 2011-01-27 | 5604.30 | 5789.10 | -3.19% | HIT +2% (d42) | 7.61% |
| 2011-02-04 | 5395.75 | 5640.90 | -4.35% | HIT +3% (d10) | 4.04% |
| 2011-02-24 | 5262.70 | 5469.10 | -3.77% | HIT +3% (d2) | 0.57% |
| 2011-05-03 | 5565.25 | 5757.40 | -3.34% | HIT +1% (d42) | 6.64% |
| 2011-06-20 | 5257.90 | 5462.90 | -3.75% | HIT +3% (d4) | 0.02% |
| 2011-08-04 | 5331.80 | 5515.80 | -3.34% | MISS (best -1.92%) | 11.47% |
| 2011-09-23 | 4867.75 | 5032.20 | -3.27% | HIT +3% (d4) | 2.24% |
| 2011-10-04 | 4772.14 | 4964.30 | -3.87% | HIT +3% (d2) | 0.65% |
| 2011-11-17 | 4934.75 | 5132.40 | -3.85% | HIT +3% (d13) | 5.99% |
| 2011-12-12 | 4764.60 | 4934.50 | -3.44% | HIT +3% (d27) | 0.76% |
| 2011-12-16 | 4651.60 | 4868.60 | -4.46% | HIT +3% (d7) | 2.59% |
| 2012-05-08 | 4999.95 | 5193.80 | -3.73% | HIT +3% (d29) | 4.59% |
| 2012-05-16 | 4858.25 | 5072.00 | -4.22% | HIT +3% (d9) | 0.17% |
| 2012-05-23 | 4835.64 | 4992.70 | -3.15% | HIT +3% (d3) | 0.11% |
| 2013-02-28 | 5693.05 | 5878.80 | -3.16% | HIT +3% (d5) | 0.52% |
| 2013-04-09 | 5495.10 | 5680.90 | -3.27% | HIT +3% (d5) | 0.33% |
| 2013-06-12 | 5760.20 | 5943.00 | -3.08% | HIT +3% (d21) | 1.34% |
| 2013-06-20 | 5655.90 | 5865.90 | -3.58% | HIT +3% (d6) | 1.59% |
| 2013-08-02 | 5677.90 | 5856.00 | -3.04% | HIT +3% (d24) | 3.36% |
| 2013-08-06 | 5542.25 | 5811.40 | -4.63% | HIT +3% (d5) | 1.00% |
| 2013-08-16 | 5507.85 | 5721.20 | -3.73% | HIT +3% (d15) | 7.06% |
| 2013-08-27 | 5287.45 | 5556.10 | -4.84% | HIT +3% (d3) | 3.19% |
| 2014-12-16 | 8067.60 | 8348.90 | -3.37% | HIT +3% (d4) | 1.32% |
| 2015-03-26 | 8342.10 | 8646.00 | -3.51% | HIT +3% (d4) | 0.87% |
| 2015-04-27 | 8213.79 | 8524.70 | -3.65% | HIT +3% (d18) | 0.35% |
| 2015-04-30 | 8181.50 | 8448.80 | -3.16% | HIT +3% (d12) | 0.00% |
| 2015-05-06 | 8097.00 | 8395.50 | -3.56% | HIT +3% (d8) | 1.23% |
| 2015-08-24 | 7809.00 | 8392.10 | -6.95% | HIT +3% (d4) | 1.82% |
| 2015-09-01 | 7785.85 | 8168.60 | -4.69% | HIT +3% (d12) | 3.16% |
| 2015-11-10 | 7783.35 | 8045.20 | -3.25% | HIT +2% (d11) | 0.89% |
| 2016-01-07 | 7568.30 | 7807.70 | -3.07% | MISS (best +0.87%) | 9.81% |
| 2016-01-15 | 7437.80 | 7681.60 | -3.17% | HIT +2% (d10) | 2.64% |
| 2016-01-20 | 7309.30 | 7599.10 | -3.81% | HIT +3% (d6) | 0.81% |
| 2016-02-10 | 7215.70 | 7444.20 | -3.07% | HIT +3% (d16) | 5.40% |
| 2016-02-16 | 7048.25 | 7313.10 | -3.62% | HIT +3% (d11) | 1.24% |
| 2016-02-25 | 6970.60 | 7209.50 | -3.31% | HIT +3% (d3) | 0.00% |
| 2016-11-15 | 8108.45 | 8507.40 | -4.69% | HIT +3% (d41) | 0.23% |
| 2018-09-24 | 10967.40 | 11364.70 | -3.50% | HIT +1% (d1) | 0.77% |
| 2018-10-04 | 10599.25 | 11131.60 | -4.78% | HIT +3% (d38) | 4.35% |
| 2018-10-19 | 10303.55 | 10674.70 | -3.48% | HIT +3% (d13) | 0.77% |
| 2019-05-13 | 11148.20 | 11505.70 | -3.11% | HIT +3% (d5) | 0.36% |
| 2019-07-30 | 11085.40 | 11449.30 | -3.18% | HIT +3% (d35) | 4.04% |
| 2019-08-01 | 10980.00 | 11376.00 | -3.48% | HIT +3% (d32) | 1.80% |
| 2019-08-07 | 10855.50 | 11222.90 | -3.27% | HIT +3% (d2) | 0.12% |
| 2020-02-01 | 11661.85 | 12101.70 | -3.63% | HIT +3% (d3) | 0.41% |
| 2020-02-28 | 11201.75 | 11893.00 | -5.81% | HIT +2% (d1) | 1.48% |
| 2020-05-18 | 8823.25 | 9190.40 | -3.99% | HIT +3% (d2) | 0.00% |
| 2020-09-24 | 10805.55 | 11314.60 | -4.50% | HIT +3% (d2) | 0.00% |
| 2021-01-29 | 13634.60 | 14138.10 | -3.56% | HIT +3% (d1) | 0.00% |
| 2021-03-25 | 14324.90 | 14783.00 | -3.10% | HIT +3% (d2) | 0.00% |
| 2021-11-26 | 17026.45 | 17726.20 | -3.95% | HIT +3% (d9) | 1.43% |
| 2021-12-06 | 16912.25 | 17452.10 | -3.09% | HIT +3% (d2) | 0.00% |
| 2021-12-20 | 16614.20 | 17283.20 | -3.87% | HIT +3% (d3) | 0.00% |
| 2022-01-24 | 17149.09 | 17735.00 | -3.30% | HIT +3% (d6) | 1.82% |
| 2022-02-14 | 16842.80 | 17442.30 | -3.44% | HIT +3% (d1) | 0.02% |
| 2022-02-24 | 16247.95 | 17222.90 | -5.66% | HIT +3% (d1) | 0.00% |
| 2022-03-03 | 16498.05 | 17027.40 | -3.11% | HIT +3% (d10) | 5.01% |
| 2022-05-06 | 16411.25 | 17066.80 | -3.84% | HIT +2% (d20) | 4.12% |
| 2022-05-19 | 15809.40 | 16453.00 | -3.91% | HIT +3% (d2) | 0.00% |
| 2022-06-13 | 15774.40 | 16358.10 | -3.57% | HIT +3% (d19) | 3.75% |
| 2022-06-22 | 15413.30 | 15917.60 | -3.17% | HIT +3% (d3) | 0.30% |
| 2022-09-26 | 17016.30 | 17591.50 | -3.27% | HIT +3% (d15) | 1.58% |
| 2023-10-26 | 18857.25 | 19520.80 | -3.40% | HIT +3% (d7) | 0.00% |
| 2024-11-13 | 23559.05 | 24314.10 | -3.11% | HIT +3% (d6) | 1.26% |
| 2025-02-28 | 22124.70 | 22905.10 | -3.41% | HIT +3% (d11) | 0.72% |
| 2025-04-07 | 22161.60 | 23016.50 | -3.71% | HIT +3% (d3) | 0.00% |
| 2026-03-04 | 24480.50 | 25395.20 | -3.60% | HIT +1% (d1) | 0.00% |
| 2026-03-06 | 24450.45 | 25251.00 | -3.17% | MISS (best +0.62%) | 9.28% |
| 2026-03-19 | 23002.15 | 24251.30 | -5.15% | HIT +3% (d11) | 0.00% |
| 2026-03-27 | 22819.60 | 23734.00 | -3.85% | HIT +3% (d6) | 2.79% |
100/111 = 93.7% HIT +1%. 7 misses (see "Where it fails" above): 2008-01-18, 2008-02-06,
2008-06-02, 2008-09-26 (worst, GFC), 2011-08-04, 2016-01-07, 2026-03-06.

## Full per-signal table — F2 (SHORT, gap_pct crosses above +3%), n=148

Entry = close on the crossing day. Outcome shows the deepest target reached and day count, or
the best forward move achieved anywhere in the window for misses (a positive number here means
price still rose from entry — bad for a short — even on a "MISS"; the +1%/+2%/+3% targets for
a short require the LOW to fall to entry x (1-t)). Max adverse move = worst UP move from entry
observed before the -1% hit (or before window expiry if it never hit) — inverted-for-shorts
convention, see "Strategy as tested" above.

| Date | Entry | EMA20 | gap_pct | Outcome (days to reach) | Max adverse move |
|---|---|---|---|---|---|
| 2006-09-01 | 3435.45 | 3329.30 | 3.19% | HIT +3% (d7) | 1.61% |
| 2006-09-21 | 3553.05 | 3438.30 | 3.34% | HIT +1% (d2) | 0.44% |
| 2006-09-26 | 3571.75 | 3466.60 | 3.03% | HIT +1% (d5) | 0.96% |
| 2006-10-13 | 3676.05 | 3550.60 | 3.53% | MISS (best +0.68%) | 10.09% |
| 2006-10-30 | 3769.10 | 3648.80 | 3.30% | HIT +2% (d31) | 0.36% |
| 2006-11-02 | 3791.20 | 3680.00 | 3.02% | HIT +3% (d28) | 1.30% |
| 2006-11-22 | 3954.75 | 3819.90 | 3.53% | HIT +3% (d13) | 0.56% |
| 2007-01-15 | 4078.40 | 3951.90 | 3.20% | HIT +3% (d26) | 4.09% |
| 2007-01-18 | 4109.05 | 3987.60 | 3.04% | HIT +3% (d17) | 0.68% |
| 2007-02-05 | 4215.35 | 4080.50 | 3.31% | HIT +3% (d5) | 0.71% |
| 2007-04-13 | 3917.35 | 3802.60 | 3.02% | MISS (best -0.08%) | 11.38% |
| 2007-05-03 | 4150.85 | 4009.10 | 3.54% | HIT +3% (d6) | 0.72% |
| 2007-05-17 | 4219.55 | 4083.70 | 3.33% | HIT +2% (d15) | 0.21% |
| 2007-05-21 | 4260.89 | 4111.80 | 3.63% | HIT +3% (d13) | 0.72% |
| 2007-07-13 | 4504.55 | 4343.60 | 3.71% | HIT +3% (d13) | 1.01% |
| 2007-07-19 | 4562.10 | 4401.70 | 3.65% | HIT +3% (d6) | 1.88% |
| 2007-07-26 | 4619.80 | 4481.50 | 3.09% | HIT +3% (d1) | 0.00% |
| 2007-08-31 | 4464.00 | 4319.10 | 3.36% | MISS (best +0.41%) | 33.87% |
| 2007-09-06 | 4518.60 | 4375.00 | 3.28% | HIT +1% (d2) | 0.65% |
| 2007-09-19 | 4732.35 | 4478.50 | 5.67% | MISS (best +0.24%) | 27.04% |
| 2007-10-23 | 5473.70 | 5243.90 | 4.38% | HIT +1% (d22) | 9.83% |
| 2007-11-14 | 5937.90 | 5664.70 | 4.82% | HIT +3% (d4) | 0.49% |
| 2007-12-05 | 5940.00 | 5741.50 | 3.46% | HIT +3% (d8) | 4.13% |
| 2007-12-11 | 6097.25 | 5827.40 | 4.63% | HIT +3% (d4) | 1.29% |
| 2007-12-26 | 6070.75 | 5882.30 | 3.20% | HIT +3% (d15) | 4.72% |
| 2007-12-31 | 6138.60 | 5939.30 | 3.36% | HIT +3% (d12) | 0.95% |
| 2008-01-04 | 6274.30 | 6025.00 | 4.14% | HIT +3% (d7) | 0.25% |
| 2008-04-21 | 5037.00 | 4836.20 | 4.15% | HIT +3% (d23) | 5.20% |
| 2008-04-25 | 5111.70 | 4906.10 | 4.19% | HIT +3% (d10) | 3.66% |
| 2008-07-23 | 4476.80 | 4158.40 | 7.66% | HIT +3% (d2) | 1.40% |
| 2008-08-01 | 4413.55 | 4246.40 | 3.94% | HIT +3% (d13) | 0.51% |
| 2008-09-02 | 4504.00 | 4367.80 | 3.12% | HIT +3% (d2) | 0.24% |
| 2008-12-10 | 2928.25 | 2798.20 | 4.65% | HIT +3% (d2) | 0.58% |
| 2009-01-01 | 3033.45 | 2934.90 | 3.36% | HIT +3% (d4) | 3.75% |
| 2009-02-09 | 2919.90 | 2828.80 | 3.22% | HIT +3% (d6) | 1.28% |
| 2009-02-13 | 2948.35 | 2860.80 | 3.06% | HIT +3% (d1) | 0.16% |
| 2009-03-23 | 2939.90 | 2761.30 | 6.47% | MISS (best +0.86%) | 53.39% |
| 2009-04-29 | 3473.95 | 3298.00 | 5.34% | MISS (best -0.14%) | 35.10% |
| 2009-05-15 | 3671.65 | 3512.30 | 4.54% | MISS (best -0.04%) | 27.82% |
| 2009-06-16 | 4517.80 | 4385.80 | 3.01% | HIT +3% (d1) | 0.00% |
| 2009-07-17 | 4374.95 | 4229.90 | 3.43% | MISS (best +0.49%) | 11.99% |
| 2009-07-23 | 4523.75 | 4310.30 | 4.95% | HIT +3% (d14) | 1.68% |
| 2009-07-30 | 4571.45 | 4407.40 | 3.72% | HIT +3% (d7) | 3.50% |
| 2009-08-24 | 4642.80 | 4501.30 | 3.14% | HIT +1% (d1) | 0.65% |
| 2009-09-07 | 4782.89 | 4610.20 | 3.75% | HIT +3% (d36) | 8.34% |
| 2009-09-15 | 4892.10 | 4710.30 | 3.86% | HIT +3% (d28) | 5.92% |
| 2009-09-29 | 5006.85 | 4860.00 | 3.02% | HIT +3% (d18) | 2.07% |
| 2009-10-14 | 5118.20 | 4963.30 | 3.12% | HIT +3% (d8) | 1.25% |
| 2010-01-05 | 5277.90 | 5123.90 | 3.01% | HIT +3% (d12) | 0.62% |
| 2010-03-03 | 5088.10 | 4915.10 | 3.52% | MISS (best +0.77%) | 6.12% |
| 2010-03-08 | 5124.00 | 4962.80 | 3.25% | HIT +2% (d41) | 5.38% |
| 2010-03-16 | 5198.10 | 5043.00 | 3.08% | HIT +3% (d34) | 3.88% |
| 2010-04-05 | 5368.40 | 5205.70 | 3.12% | HIT +3% (d9) | 0.58% |
| 2010-06-17 | 5274.85 | 5112.80 | 3.17% | HIT +1% (d9) | 1.74% |
| 2010-06-21 | 5353.30 | 5148.60 | 3.98% | HIT +2% (d6) | 0.02% |
| 2010-09-13 | 5760.00 | 5530.40 | 4.15% | MISS (best -0.01%) | 10.04% |
| 2010-10-01 | 6143.40 | 5883.60 | 4.41% | HIT +3% (d20) | 1.30% |
| 2010-10-13 | 6233.90 | 6029.30 | 3.39% | HIT +3% (d3) | 0.81% |
| 2010-11-04 | 6281.80 | 6087.20 | 3.20% | HIT +3% (d6) | 0.90% |
| 2011-03-25 | 5654.25 | 5480.70 | 3.17% | HIT +3% (d26) | 5.13% |
| 2011-04-13 | 5911.50 | 5736.90 | 3.04% | HIT +3% (d2) | 0.00% |
| 2011-06-30 | 5647.40 | 5477.00 | 3.11% | HIT +3% (d20) | 1.65% |
| 2011-07-07 | 5728.95 | 5547.70 | 3.27% | HIT +3% (d3) | 0.20% |
| 2011-10-28 | 5360.70 | 5090.80 | 5.30% | HIT +3% (d8) | 0.00% |
| 2012-01-17 | 4967.30 | 4806.20 | 3.35% | MISS (best +0.73%) | 13.34% |
| 2012-01-19 | 5018.39 | 4839.30 | 3.70% | MISS (best +0.28%) | 12.19% |
| 2012-01-31 | 5199.25 | 4987.20 | 4.25% | HIT +1% (d41) | 8.28% |
| 2012-06-29 | 5278.90 | 5103.10 | 3.45% | HIT +3% (d16) | 1.32% |
| 2012-07-05 | 5327.30 | 5168.40 | 3.07% | HIT +3% (d12) | 0.00% |
| 2012-09-14 | 5577.65 | 5361.10 | 4.04% | HIT +3% (d13) | 4.26% |
| 2012-09-21 | 5691.15 | 5445.30 | 4.51% | HIT +3% (d9) | 2.18% |
| 2012-09-28 | 5703.30 | 5534.90 | 3.04% | HIT +3% (d4) | 1.96% |
| 2012-10-04 | 5787.60 | 5590.20 | 3.53% | HIT +3% (d1) | 0.48% |
| 2012-11-30 | 5879.85 | 5687.50 | 3.38% | MISS (best +0.96%) | 3.94% |
| 2012-12-06 | 5930.90 | 5757.70 | 3.01% | HIT +1% (d3) | 0.58% |
| 2013-04-25 | 5916.30 | 5715.40 | 3.52% | HIT +3% (d34) | 5.29% |
| 2013-05-02 | 5999.30 | 5786.60 | 3.67% | HIT +3% (d29) | 0.02% |
| 2013-05-07 | 6043.55 | 5839.30 | 3.50% | HIT +3% (d25) | 1.17% |
| 2013-05-10 | 6094.75 | 5899.70 | 3.31% | HIT +3% (d18) | 0.32% |
| 2013-05-15 | 6146.75 | 5952.40 | 3.26% | HIT +3% (d6) | 1.35% |
| 2013-09-10 | 5896.75 | 5557.60 | 6.10% | HIT +3% (d14) | 0.47% |
| 2013-10-11 | 6096.20 | 5889.90 | 3.50% | HIT +2% (d22) | 0.99% |
| 2013-10-18 | 6189.35 | 5963.10 | 3.79% | HIT +3% (d18) | 0.50% |
| 2013-10-31 | 6299.15 | 6105.90 | 3.16% | HIT +3% (d7) | 0.70% |
| 2013-12-09 | 6363.90 | 6170.70 | 3.13% | HIT +3% (d4) | 0.00% |
| 2014-03-06 | 6401.15 | 6205.30 | 3.16% | MISS (best -0.19%) | 9.67% |
| 2014-03-28 | 6695.90 | 6493.40 | 3.12% | MISS (best +0.86%) | 12.96% |
| 2014-04-02 | 6752.55 | 6554.10 | 3.03% | HIT +1% (d3) | 0.36% |
| 2014-05-12 | 7014.25 | 6746.20 | 3.97% | MISS (best -0.75%) | 11.33% |
| 2014-06-03 | 7415.85 | 7183.20 | 3.24% | MISS (best +0.75%) | 5.73% |
| 2014-06-05 | 7474.10 | 7229.80 | 3.38% | MISS (best +0.70%) | 4.91% |
| 2014-10-31 | 8322.20 | 8009.50 | 3.90% | HIT +3% (d30) | 3.66% |
| 2015-01-20 | 8695.60 | 8370.00 | 3.89% | HIT +2% (d13) | 3.46% |
| 2016-03-03 | 7475.60 | 7222.40 | 3.51% | MISS (best +0.94%) | 6.91% |
| 2016-03-09 | 7531.80 | 7295.00 | 3.25% | HIT +1% (d1) | 0.20% |
| 2016-03-21 | 7704.25 | 7436.90 | 3.59% | HIT +2% (d11) | 0.59% |
| 2016-04-18 | 7914.70 | 7652.90 | 3.42% | HIT +2% (d10) | 0.81% |
| 2016-05-27 | 8156.65 | 7867.90 | 3.67% | HIT +2% (d20) | 1.70% |
| 2016-06-02 | 8218.95 | 7972.90 | 3.09% | HIT +3% (d16) | 0.92% |
| 2017-01-25 | 8602.75 | 8348.50 | 3.05% | MISS (best +0.76%) | 7.16% |
| 2017-02-01 | 8716.40 | 8444.70 | 3.22% | MISS (best +0.35%) | 6.40% |
| 2017-02-06 | 8801.05 | 8526.70 | 3.22% | HIT +1% (d7) | 0.29% |
| 2018-01-23 | 11083.70 | 10697.70 | 3.61% | HIT +3% (d7) | 0.79% |
| 2018-01-29 | 11130.40 | 10801.20 | 3.05% | HIT +3% (d4) | 0.00% |
| 2019-03-12 | 11301.20 | 10948.60 | 3.22% | HIT +1% (d39) | 4.91% |
| 2019-03-15 | 11426.85 | 11058.80 | 3.33% | HIT +2% (d36) | 1.28% |
| 2019-05-20 | 11828.25 | 11465.90 | 3.16% | HIT +3% (d35) | 0.47% |
| 2019-06-03 | 12088.55 | 11735.70 | 3.01% | HIT +3% (d9) | 0.06% |
| 2019-09-23 | 11600.20 | 11033.80 | 5.13% | HIT +3% (d6) | 0.47% |
| 2019-09-26 | 11571.20 | 11163.20 | 3.65% | HIT +3% (d5) | 0.19% |
| 2020-04-29 | 9553.35 | 9170.50 | 4.18% | HIT +3% (d3) | 3.51% |
| 2020-05-28 | 9490.10 | 9177.60 | 3.40% | HIT +1% (d1) | 1.15% |
| 2020-06-18 | 10091.65 | 9796.90 | 3.01% | MISS (best +0.19%) | 12.70% |
| 2020-06-26 | 10383.00 | 10041.00 | 3.41% | HIT +1% (d1) | 0.00% |
| 2020-07-01 | 10430.04 | 10121.70 | 3.05% | MISS (best -0.53%) | 12.04% |
| 2020-07-17 | 10901.70 | 10551.20 | 3.32% | MISS (best +0.18%) | 8.19% |
| 2020-07-28 | 11300.55 | 10866.60 | 3.99% | HIT +3% (d4) | 0.36% |
| 2020-10-07 | 11738.85 | 11380.30 | 3.15% | HIT +1% (d16) | 2.44% |
| 2020-11-06 | 12263.55 | 11831.30 | 3.65% | MISS (best -0.85%) | 16.25% |
| 2020-11-26 | 12987.00 | 12602.90 | 3.05% | MISS (best +0.56%) | 13.60% |
| 2020-12-01 | 13109.05 | 12682.70 | 3.36% | MISS (best +0.96%) | 12.54% |
| 2020-12-04 | 13258.55 | 12810.00 | 3.50% | MISS (best +0.96%) | 12.48% |
| 2020-12-28 | 13873.20 | 13433.70 | 3.27% | HIT +1% (d22) | 6.35% |
| 2021-01-04 | 14132.90 | 13663.90 | 3.43% | HIT +3% (d18) | 4.39% |
| 2021-01-08 | 14347.25 | 13845.20 | 3.63% | HIT +3% (d13) | 2.83% |
| 2021-01-20 | 14644.70 | 14212.30 | 3.04% | HIT +3% (d4) | 0.74% |
| 2021-02-02 | 14647.85 | 14198.90 | 3.16% | HIT +2% (d32) | 5.35% |
| 2021-05-31 | 15582.80 | 15070.20 | 3.40% | MISS (best +0.85%) | 2.44% |
| 2021-06-03 | 15690.35 | 15212.20 | 3.14% | HIT +1% (d11) | 1.35% |
| 2021-08-31 | 17132.20 | 16512.00 | 3.76% | MISS (best +0.45%) | 8.59% |
| 2021-09-16 | 17629.50 | 17103.40 | 3.08% | HIT +1% (d2) | 0.93% |
| 2021-09-23 | 17822.95 | 17297.30 | 3.04% | HIT +3% (d39) | 0.70% |
| 2021-10-14 | 18338.55 | 17771.20 | 3.19% | HIT +3% (d10) | 1.45% |
| 2022-01-05 | 17925.25 | 17352.20 | 3.30% | HIT +3% (d13) | 0.00% |
| 2022-01-12 | 18212.34 | 17603.10 | 3.46% | HIT +3% (d6) | 0.76% |
| 2022-04-01 | 17670.45 | 17154.40 | 3.01% | HIT +3% (d9) | 2.51% |
| 2022-07-22 | 16719.45 | 16179.00 | 3.34% | HIT +1% (d2) | 0.00% |
| 2022-07-28 | 16929.60 | 16346.00 | 3.57% | MISS (best +0.83%) | 6.89% |
| 2022-11-01 | 18145.40 | 17582.10 | 3.20% | HIT +2% (d37) | 0.18% |
| 2023-07-20 | 19979.15 | 19387.80 | 3.05% | HIT +3% (d10) | 0.00% |
| 2023-12-04 | 20686.80 | 19853.80 | 4.20% | MISS (best -0.12%) | 6.96% |
| 2023-12-14 | 21182.70 | 20471.10 | 3.48% | MISS (best +0.97%) | 4.46% |
| 2023-12-27 | 21654.75 | 20987.30 | 3.18% | HIT +2% (d19) | 2.17% |
| 2025-03-24 | 23658.35 | 22848.80 | 3.54% | HIT +3% (d8) | 0.89% |
| 2025-04-17 | 23851.65 | 23076.20 | 3.36% | MISS (best +0.02%) | 5.75% |
| 2025-04-28 | 24328.50 | 23588.30 | 3.14% | HIT +1% (d8) | 1.07% |
| 2025-05-12 | 24924.70 | 24071.20 | 3.55% | HIT +1% (d1) | 0.20% |
| 2025-05-15 | 25062.10 | 24256.40 | 3.32% | HIT +2% (d5) | 0.03% |
114/148 = 77.0% HIT +1%. 34 misses (see "Where it fails" above for the 12 worst by adverse
move): heavily clustered in the 2009 post-GFC-bottom V-recovery and the Nov-Dec 2020
post-COVID-vaccine V-recovery.

## Cross-timeframe comparison — does F1/F2 behave consistently between daily and 1h?

See the full detail in `nifty_entry_signal_backtest_1h_report.md`'s companion section. Unlike
the E-family comparison in Part 4 (where both timeframes had large enough samples to compute
and compare real confidence intervals), **the 1h side of this comparison cannot be done on
statistical terms** — at the mandated 3% threshold, 1h produces only n=2 (long) and n=1
(short), and even loosening to the loosest end of the mandated sweep (2%) only reaches n=8
(long) / n=7 (short), still well under this project's ~30-trade usability floor at every
threshold tested. This is a different and more severe divergence than either of this
project's two prior cross-timeframe comparisons (the BB+z_ema200 signal and the E-family
Supertrend flip), both of which had a statistically usable 1h sample (n=48-99) even though
the resulting hit rates diverged sharply from daily. Here, the 1h sample never becomes usable
at all — the root cause is structural, not a filter/threshold choice: EMA(20) on 1h bars
tracks only about 3 trading days of trend (20 candles / 7 per day), and NIFTY simply does not
often get 3%+ away from such a short, reactive trend line within the ~2 years of 1h history
available. The one directionally suggestive (not validated) observation: even in the tiny 1h
sample, the long side outperforms the short side by a wide margin (100% vs. 42.9% at the 2%
threshold) — the same direction as the daily asymmetry (93.7% vs. 77.0%) — consistent with,
though far too small a sample to confirm, the idea that the long-side mean-reversion bet is
mechanically the stronger one on this instrument regardless of timeframe.

## Recommendation

**Ship F1 (long) as a genuine daily-timeframe candidate alongside A1/A3/E1** — 111 trades, a
93.7% point hit rate with a 90% exact-binomial CI of [88.5%, 97.0%] (in the same "close to,
not confidently above, 90%" territory as A1/A3 from Part 1, and a hair below E1's tighter CI
from Part 4), a genuine cross-regime and cross-parameter robustness plateau, and out-of-sample
performance that improves rather than degrades. Its failure mode (macro/exogenous shocks,
concentrated in the 2008 GFC) is the same well-understood, un-filterable ceiling shared by
every other signal family in this project — not a new or worse risk.

**Do not ship F2 (short) as specified.** Its point estimate (77.0%) is clearly and
consistently below the ~90% bar across every validation cut run here (full-history,
walk-forward, regime blocks, bootstrap/exact-binomial CI, and the full threshold sweep), it
degrades out-of-sample by a larger margin than any other signal's walk-forward gap in this
project, and its failure mode is structurally identifiable and specific: it loses hardest
during V-shaped post-crash recoveries (2009, 2020), where a market that is "overbought vs. its
own EMA20" is actually in the early-to-mid stages of a durable new uptrend, not due for a
fade. If the user wants a usable short-side signal from this family, the practical next step
is a regime filter that can distinguish "overbought within a range/uptrend" from "overbought
because the market just crashed and is recovering" (e.g. a longer-horizon trend/return filter,
or excluding fires within some number of months of a >20% drawdown) — untested here, a
different experiment, not a fix that can be read off the current sweep. As tested, F2 is a
kill, not a ship.

# Part 6 — F1 fine threshold sweep, LONG side only (1.0%–5.0%, step 0.2%) (2026-07-29 session)

Run date: 2026-07-29. Follow-up to Part 5, scoped explicitly to the LONG side (F1) only —
per instruction, the SHORT side (F2) is out of scope here; it already failed validation in
Part 5 (77.0% hit rate, below the ~90% bar, degrading out-of-sample) and nothing about a
finer long-side sweep changes that verdict. Same data pipeline, same 42-trading-day forward
window, same no-lookahead discipline, same drawdown-tolerant "+1% touch on the daily HIGH"
hit definition as Part 5 — this section only replaces the coarse 2.0/2.5/3.0/3.5/4.0% grid
with a finer 1.0–5.0% grid in 0.2% steps (21 thresholds), byte-for-byte reusing
`detect_ema20gap_signals()` / `compute_forward_outcomes_directional()` /
`walk_forward()` / `regime_blocks()` / `bootstrap_ci()` from the existing script (no
duplicated logic — see the scratch driver script referenced below).

```
VERDICT: 3.0% (the existing baseline) is not the single best point on this finer grid, but
the improvement at nearby thresholds is modest and NOT clearly distinguishable from noise --
this is "already near-optimal," not "materially improvable." A local hump exists in the
2.8%-3.6% band (mean hit1% ~94.1% across those 7 thresholds) sitting above both the looser
end (1.0%-2.6%, mean ~91.9%) and the tighter end (4.2%-5.0%, mean ~92.0%) -- a real, smoothly-
varying shape, not a single-point spike, so it is not pure sampling noise. Within that hump,
3.2% (n=102) has the best point estimate (96.1% vs. 93.7% at 3.0%) and is the ONLY threshold
in the entire 1.0-5.0% grid whose 90% exact-binomial CI lower bound clears 90% (CI [91.3%,
98.6%] vs. 3.0%'s [88.5%, 97.0%]), plus a walk-forward test-set hit rate of 100% (n=31) and
100% hit rate in 3 of 4 regime blocks. 3.4% (n=95) is a close second (95.8%, CI [90.6%,
98.5%]). However, a direct trade-level comparison shows much of 3.2%'s uplift over 3.0% comes
from a mechanical and expected effect (tightening the threshold drops a handful of shallower,
weaker breaches -- including 3 of 3.0%'s 7 historical misses -- and replaces them with slightly
later, deeper breaches of the SAME dip episode, which is inherently a stronger mean-reversion
setup), not from an independently-confirmed "better parameter." The 3.0% and 3.2% confidence
intervals overlap substantially (91.3-97.0% is common to both), and with 21 thresholds tested,
the single best point estimate is expected to run somewhat hot from multiple-comparisons
selection alone. Net: 3.2%/3.4% are legitimate, comparably-validated alternatives that clear
the ~90% bar with slightly more confidence than the original 3.0% pick, but this is a soft
refinement, not a "3.0% was wrong" finding -- treat the whole 2.8%-3.6% band as the real
plateau, not any single decimal within it.
```

## Strategy as tested

Identical to Part 5's F1 definition — `gap_pct = (close - EMA20) / EMA20 * 100` crosses BELOW
`-threshold` (a threshold-crossing signal, fires once on first breach); `entry_price =
close[t]`; bet is mean-reversion UP; target/adverse-move semantics via
`compute_forward_outcomes_directional(..., direction="long")`, identical 42-trading-day
window and +1%/+2%/+3% targets. The only change from Part 5 is the threshold grid: 21 values,
`1.0, 1.2, 1.4, ..., 4.8, 5.0`, replacing the coarse `2.0, 2.5, 3.0, 3.5, 4.0` sweep already in
`ema20gap_param_sweep()`. Universe/timeframe/data window: NIFTY 50 index, daily candles,
2006-08-02 → 2026-07-27 (4,951 trading days), identical to Part 5.

## Full sweep table — F1 (LONG), n / hit1% / hit2% / hit3% at each threshold

| Threshold | n | Hit +1% | Hit +2% | Hit +3% | Small-sample flag |
|---|---|---|---|---|---|
| 1.0% | 238 | 90.3% | 79.8% | 69.7% | |
| 1.2% | 221 | 90.5% | 81.0% | 72.9% | |
| 1.4% | 207 | 90.3% | 81.2% | 72.9% | |
| 1.6% | 196 | 92.3% | 82.7% | 75.5% | |
| 1.8% | 186 | 90.9% | 83.3% | 79.0% | |
| 2.0% | 176 | 93.8% | 83.5% | 79.5% | |
| 2.2% | 164 | 93.3% | 83.5% | 78.7% | |
| 2.4% | 148 | 92.6% | 82.4% | 77.0% | |
| 2.6% | 141 | 92.9% | 82.3% | 76.6% | |
| 2.8% | 131 | 93.9% | 83.2% | 76.3% | |
| **3.0% (baseline)** | **111** | **93.7%** | **86.5%** | **82.0%** | |
| **3.2%** | **102** | **96.1%** | **91.2%** | **87.3%** | |
| **3.4%** | **95** | **95.8%** | **92.6%** | **88.4%** | |
| 3.6% | 86 | 94.2% | 91.9% | 87.2% | |
| 3.8% | 72 | 93.1% | 91.7% | 86.1% | |
| 4.0% | 64 | 92.2% | 90.6% | 85.9% | |
| 4.2% | 62 | 91.9% | 90.3% | 85.5% | |
| 4.4% | 64 | 92.2% | 89.1% | 84.4% | |
| 4.6% | 62 | 91.9% | 88.7% | 87.1% | |
| 4.8% | 63 | 92.1% | 90.5% | 88.9% | |
| 5.0% | 60 | 91.7% | 91.7% | 88.3% | |

**No threshold in this entire 1.0–5.0% grid drops below n=60** — over the full ~20-year
history, even the tightest (rarest) breach level tested still clears the ~30-trade floor by a
wide margin, so unlike several signal families elsewhere in this study, nothing here needs a
small-sample flag. This is worth stating explicitly since the task brief anticipated it as a
likely finding (n collapsing at the high end) — it does not happen at daily-timeframe/20-year
depth, though it would very plausibly happen on a shorter history or the 1h timeframe (see
Part 5's cross-timeframe section, where even the loosest 2% threshold only reaches n=8 on 1h).

**The tradeoff the brief flagged is real, but shows up as a hit-rate hump, not a monotonic
tradeoff:** hit1% does NOT simply rise as the threshold tightens (which would be the "purer
signal, smaller sample" story) or simply fall (which would be "signal doesn't scale"). Instead
it rises from ~90% (1.0-1.8%) to a peak around 96% (3.2%), then decays back down to a ~92%
plateau (4.2-5.0%). Bucketed averages: 1.0-2.6% (9 thresholds) mean hit1% = 91.9%; 2.8-4.0%
(7 thresholds) mean hit1% = 94.1%; 4.2-5.0% (5 thresholds) mean hit1% = 92.0%. The middle band
is the real "sweet spot" — genuinely and smoothly better than both tails, not a single spike.

## Candidates carried into the full validation gauntlet

Selected 3.2% and 3.4% (the two best point estimates within the 2.8-3.6% hump, both n>=95,
comfortably above the ~30 floor) for the full gauntlet, run side-by-side against the existing
3.0% baseline and against 2.0% (included as the "much larger sample, lower point estimate"
contrast case the brief asked to make explicit) and 2.8%/3.6% (the hump's shoulders).

### Walk-forward (train = pre-2018, test = 2018 onward)

| Threshold | Train n | Train hit1% | Test n | Test hit1% | Gap |
|---|---|---|---|---|---|
| 2.0% | 109 | 93.6% | 67 | 94.0% | +0.4pp |
| 2.8% | 86 | 93.0% | 45 | 95.6% | +2.6pp |
| 3.0% (baseline) | 78 | 92.3% | 33 | 97.0% | +4.6pp |
| **3.2%** | **71** | **94.4%** | **31** | **100.0%** | **+5.6pp** |
| **3.4%** | **67** | **94.0%** | **28** | **100.0%** | **+6.0pp** |
| 3.6% | 64 | 93.8% | 22 | 95.5% | +1.7pp |

Every threshold tested improves out-of-sample (none show the overfitting-red-flag pattern of
train >> test) — consistent with Part 5's finding for the 3.0% baseline. 3.2%/3.4% test-set
hit rates of 100% look the most attractive, but test-set n is only 31/28 — a 100% print at
that sample size is not strong evidence of a true 100% underlying rate, just evidence of "no
misses in a modest out-of-sample window," which is a meaningfully weaker claim.

### Regime-block consistency (four ~5-year blocks)

| Threshold | 2007–11 | 2012–16 | 2017–21 | 2022–26 |
|---|---|---|---|---|
| 2.0% | n=65, 92.3% | n=41, 95.1% | n=34, 91.2% | n=35, 97.1% |
| 2.8% | n=52, 90.4% | n=33, 97.0% | n=20, 95.0% | n=25, 96.0% |
| 3.0% (baseline) | n=51, 90.2% | n=26, 96.2% | n=16, 100.0% | n=17, 94.1% |
| **3.2%** | **n=47, 91.5%** | **n=23, 100.0%** | **n=14, 100.0%** | **n=17, 100.0%** |
| **3.4%** | **n=45, 91.1%** | **n=21, 100.0%** | **n=13, 100.0%** | **n=15, 100.0%** |
| 3.6% | n=46, 91.3% | n=17, 100.0% | n=11, 90.9% | n=11, 100.0% |

3.2%/3.4% post three consecutive 100.0% blocks — visually the most impressive row in this
table, but with block sizes of n=13-23 this is exactly the kind of small-n perfect-record
result that should be read cautiously: a genuinely ~95% true hit rate would be expected to
print a 100% result in a randomly chosen ~15-23-trade block a meaningful fraction of the time
purely by chance (roughly 25-50% of the time at n=15-23 and a true rate of ~93-96%, by a quick
binomial check), so three-in-a-row-100% is suggestive but not proof of a structurally
different, better underlying edge versus 3.0%'s own strong-but-not-perfect regime record.

### Monte Carlo bootstrap (5,000 resamples) and exact-binomial CI

| Threshold | n | Point hit1% | 90% bootstrap CI | 90% exact-binomial CI |
|---|---|---|---|---|
| 2.0% | 176 | 93.8% | [90.9%, 96.6%] | [89.9%, 96.5%] |
| 2.8% | 131 | 93.9% | [90.1%, 96.9%] | [89.3%, 96.9%] |
| 3.0% (baseline) | 111 | 93.7% | [89.2%, 97.3%] | [88.5%, 97.0%] |
| **3.2%** | **102** | **96.1%** | **[93.1%, 99.0%]** | **[91.3%, 98.6%]** |
| **3.4%** | **95** | **95.8%** | **[92.6%, 98.9%]** | **[90.6%, 98.5%]** |
| 3.6% | 86 | 94.2% | [89.5%, 97.7%] | [88.2%, 97.7%] |

3.2% is the only threshold across the entire 1.0-5.0% grid whose exact-binomial CI lower bound
sits clearly above 90% (91.3%) — the first time in this whole project (across A1/A3/E1/F1
baseline, all of which sat at 86-89% lower bounds) that any signal's CI comfortably clears the
user's stated bar rather than sitting right at it. 3.4% is close behind (90.6%, right at the
line). That said, the 3.0%/3.2%/3.4% CIs overlap heavily (roughly 91-97% is common ground to
all three) — this is evidence 3.2%/3.4% are *at least as good* as 3.0%, not decisive evidence
they are *better*. Same i.i.d.-resampling caveat as every bootstrap CI elsewhere in this study
(understates true uncertainty from time-clustering of signals).

### Is the 3.2%/3.4% improvement a real parameter effect, or a multiple-comparisons artifact?

A direct trade-by-trade diff between the 3.0% and 3.2% signal sets (26 trades only in the
looser 3.0% set, 17 trades only in the tighter 3.2% set) shows the mechanism plainly: 3 of
3.0%'s 7 historical misses (2008-02-06, 2016-01-07, 2026-03-06) are exactly the trades dropped
when tightening to 3.2% — in each case, the deeper breach past -3.2% didn't happen on that
same calendar day, so the signal simply didn't fire there, and instead fired 1-3 trading days
later once the dip deepened further (e.g. 2026-03-06 miss → replaced by 2026-03-09 and
2026-03-11, both hits). This is a real, mechanistically sensible effect — a deeper oversold
breach is a genuinely stronger mean-reversion setup, not an artifact — but it is also exactly
the kind of effect that inflates the *point estimate* of whichever threshold happens to have
dropped the most historical misses in-sample. With 21 thresholds swept, some inflation of the
single best point estimate purely from selection (multiple comparisons) should be expected
even if the true underlying edge is flat across the whole 2.8-3.6% band. **Read the 3.2%/3.4%
numbers as "this band is at least as good as 3.0%, plausibly modestly better," not as "3.2% is
proven superior."**

### Definition-sensitivity stress test (close-based hit, not high-based — substitute for
### cost-doubling, same methodology as Part 5)

| Threshold | n | High-based hit1% | Close-based hit1% | Degradation |
|---|---|---|---|---|
| 3.0% (baseline) | 111 | 93.7% | 88.3% | -5.4pp |
| **3.2%** | **102** | **96.1%** | **93.1%** | **-3.0pp** |
| **3.4%** | **95** | **95.8%** | **93.7%** | **-2.1pp** |
| 3.6% | 86 | 94.2% | 93.0% | -1.2pp |

3.2%/3.4%/3.6% all degrade LESS under the stricter close-based proxy than the 3.0% baseline
does — a mild additional point in favor of the tighter thresholds being at least as robust,
consistent with (not contradicting) the CI/walk-forward findings above.

### Bias checks

- **Lookahead bias:** none found, identical construction to Part 5's F1 (same-bar
  `close`/`EMA20` function, crossing test only compares `gap_pct[t]` to `gap_pct[t-1]`) —
  the threshold value itself introduces no new lookahead risk at any grid point.
- **Survivorship bias:** N/A — single index, unchanged from Part 5.
- **Overfitting:** this section's own instruction is itself an overfitting risk to be
  transparent about — sweeping 21 thresholds and reporting the best one is a mild multiple-
  comparisons/selection exercise, exactly the scenario the "is this a plateau or a cliff"
  framing exists to catch. The finding here is reassuring on that front (a smooth hump across
  2.8-3.6%, not an isolated spike at exactly one decimal), but the specific ranking of 3.2%
  over 3.4% over 3.0% within that hump should not be over-interpreted — the CIs overlap, and
  the trade-level diff above shows a chunk of the ranking is driven by which few historical
  misses happen to fall on one side or other of the exact cutoff.

## Where it fails

Same structural failure mode as the 3.0% baseline in Part 5 — misses cluster in the 2008 GFC
(exogenous macro shocks too large/fast for an EMA-distance signal to price in). Tightening the
threshold to 3.2%/3.4% does not change this qualitative picture: of 3.0%'s 7 misses, 4 persist
at 3.2% (2008-01-18, 2008-06-02, 2008-09-26 — the worst, GFC acute phase — and 2011-08-04),
still concentrated in the same 2008 GFC / 2011 debt-downgrade macro-shock episodes documented
in Part 5.

## Currently live / most-recent matching setup (as of latest candle, 2026-07-27)

Unaffected by which threshold in this band is chosen: the current `gap_pct` is -0.15% (close
23,995.95 vs. EMA20 24,031.93), nowhere near any of the 1.0-5.0% thresholds tested. The most
recent F1 fire is identical across every threshold from 1.0% up through at least 3.6%:
**2026-03-27** at close 22,819.60 (gap_pct -3.85%, comfortably past even the tightest
threshold examined in the gauntlet above) — already resolved as a HIT well within its 42-day
window, nothing actionable as a fresh entry today regardless of which exact threshold in this
band the user adopts.

## Recommendation

**3.0% is not wrong, and does not need to change on the strength of this sweep alone.** The
honest reading of this finer grid is that F1's edge lives in a genuine 2.8-3.6% plateau
(mean hit1% ~94%), not at one uniquely-correct decimal — 3.0% sits inside that plateau, just
not exactly at its peak. If the user wants to move off 3.0%, **3.2% is the best-supported
alternative**: best point estimate on the full grid (96.1%, n=102), the only threshold whose
90% exact-binomial CI clears 90% at the lower bound (91.3%), out-of-sample and regime-block
results at least as strong as the baseline, and a definition-sensitivity stress test that
degrades less than 3.0%'s does. But this should be adopted as "a modest, well-supported
refinement within an already-validated family," not sold as "we found a materially better
signal" — the trade-level diff shows a meaningful share of 3.2%'s edge over 3.0% comes from a
mechanistically sensible but statistically modest effect (deeper breaches bounce more
reliably), amplified somewhat by the ordinary statistics of picking the best of 21 tested
thresholds. Net: ship F1 at 3.0% or 3.2% — either is defensible and both are already validated
here — and do not chase the exact-decimal-optimal threshold any further than this; the
marginal gain from further tuning inside this plateau is well within the noise floor already
demonstrated by the overlapping confidence intervals above.

# Part 7 — F1 threshold sweep restricted to the last 2 years, NIFTY50 vs BANKNIFTY (2026-07-29 session)

Run date: 2026-07-29. Same finer 1.0%–5.0% (step 0.2%, 21 values) threshold grid as Part 6,
same F1 (LONG-only, mean-reversion-up) definition, same `detect_ema20gap_signals()` /
`compute_forward_outcomes_directional()` functions reused unchanged — but scored on the
**last 2 years only** (fire-day date >= 2024-07-29, through the latest available candle,
2026-07-27), and run on **both NIFTY50 and BANKNIFTY** (BANKNIFTY's first appearance in this
study). Indicators (EMA20 etc.) are still computed over each symbol's full history so nothing
is cold-started at the window boundary — only which already-detected signals get scored is
restricted, identical convention to the D-family's `window_start` handling elsewhere in this
script. `load_clean_nifty()`'s dedup/sanity-check logic was generalized to a symbol parameter
(`load_clean(symbol)` in the scratch driver referenced below) so BANKNIFTY gets the exact same
duplicate-timestamp dedup and OHLC integrity checks as NIFTY50, unchanged.

```
VERDICT: Not statistically distinguishable from noise at almost every threshold tested for
both symbols. Two years of history produces well under the ~30-trade floor this project has
already committed to at every single one of 21 thresholds, for both NIFTY50 and BANKNIFTY --
the single largest bucket across both symbols is BANKNIFTY at 1.0% (n=25), still short of 30,
with its own 90% CI a wide [62.5%, 91.8%]. At the loose end (1.0-1.6%, where n=17-25 is at
least large enough to look at, if not to trust), BOTH symbols print hit rates meaningfully
BELOW NIFTY50's own full-19-year average at the same thresholds (NIFTY50 2yr: 79-86% vs.
NIFTY50 full-history: 90-92%; BANKNIFTY has no full-history baseline to compare against, but
its 2yr numbers, 80-88%, sit in the same lower band as NIFTY50's recent numbers) -- consistent
with a real signal whose hit rate is simply noisier over any single 2-year slice than over 19
years, not evidence the signal broke, but this particular 2-year window would NOT have cleared
the ~90% bar on its own if it were the only evidence available. At tighter thresholds
(>=2.8-3.0%) both symbols show apparently strong-to-perfect hit rates, but every one of these
buckets has n=3-10 -- exactly the "100% hit rate off 3-5 trades" pattern this project has
already explicitly rejected; none of it should be read as a finding. BANKNIFTY shows NO
discernible optimal-threshold plateau at this sample depth -- its hit-rate curve bounces
between 66.7% and 100% across adjacent thresholds (3.0%: 85.7%, n=7; 3.2%/3.4%: 66.7%, n=3;
3.6%: 80.0%, n=5) in a pattern indistinguishable from pure sampling noise on single-digit
trade counts, not a signal of a genuinely different optimal parameter for that index.
```

## Strategy as tested

- Identical to Part 5/6's F1 definition: `gap_pct = (close - EMA20) / EMA20 * 100` crosses
  BELOW `-threshold` (threshold-crossing, fires once on first breach); `entry_price =
  close[t]`; bet is mean-reversion UP; 42-trading-day forward window; +1%/+2%/+3% targets via
  `compute_forward_outcomes_directional(..., direction="long")`.
- **Universe / timeframe:** NIFTY 50 index and BANKNIFTY index (spot level), daily candles,
  both from `candles_1d` in `drishti.db`.
- **Window:** fire-day date >= 2024-07-29, through the latest available candle in each
  symbol's history (2026-07-27 for both). This is a ~2-year, ~495-trading-day window for each
  symbol (vs. the ~4,950-trading-day, ~20-year window used in Parts 5/6 for NIFTY50).
- **Truncation convention (per instruction):** the 42-trading-day forward-outcome window means
  signals firing in roughly the last ~2 calendar months of the window (i.e. after ~2026-05-25)
  don't have a full 42-day forward window yet available in the data (latest candle is
  2026-07-27). These are **excluded from headline n/hit-rate stats**, identical convention to
  the "complete windows only count" rule used everywhere else in this study. Exclusion counts
  are reported per threshold below (column `trunc_excl`) — they run 0-3 signals per threshold,
  small relative to n at every threshold, so this convention is not itself a material driver of
  the small-sample problem here (the problem is simply "2 years doesn't generate enough raw
  signal occurrences," not "the truncation rule is throwing away good data").
- **Assumption:** none needed beyond what Parts 5/6 already fixed — the brief's window
  (~2024-07-29 to 2026-07-29) maps directly onto the data actually available (through
  2026-07-27), no extrapolation required.

## Data

- **Source:** SQLite (`drishti.db`), `candles_1d`, symbols `NIFTY50` and `BANKNIFTY`
  (config.py `SYMBOLS` names). No yfinance fallback needed for either.
- **History depth check (per instruction, before proceeding):** BANKNIFTY has 4,936 daily
  candles after dedup, 2006-08-02 → 2026-07-26 — essentially the same depth as NIFTY50's 4,951
  candles, 2006-08-02 → 2026-07-27. BANKNIFTY comfortably covers (in fact, vastly exceeds) the
  requested 2-year window; no truncation or fallback was needed.
- **Data-quality notes:** both symbols deduped with the exact same logic as
  `load_clean_nifty()` (duplicate UTC-timestamp-encoding artifact, one row kept per IST
  calendar date) — zero duplicate dates and zero OHLC integrity violations survived dedup for
  either symbol. Both symbols show `volume=0` on every single row in `candles_1d` (a known,
  previously-documented characteristic of index-level data in this DB — an index has no
  traded volume of its own) — irrelevant here since F1 uses only close/EMA20, no volume
  dependency.
- **2-year window size:** 495 trading days for each symbol (2024-07-29 → 2026-07-27),
  ~10% of NIFTY50's full 4,951-day history used in Parts 5/6.

## Full sweep table — NIFTY50, last 2 years only

| Threshold | n | Hit +1% | Hit +2% | Hit +3% | Truncated (excluded) | Small-sample flag |
|---|---|---|---|---|---|---|
| 1.0% | 23 | 82.6% | 73.9% | 47.8% | 2 | **n<30** |
| 1.2% | 24 | 79.2% | 70.8% | 58.3% | 3 | **n<30** |
| 1.4% | 24 | 83.3% | 70.8% | 58.3% | 3 | **n<30** |
| 1.6% | 22 | 86.4% | 72.7% | 59.1% | 2 | **n<30** |
| 1.8% | 18 | 88.9% | 83.3% | 72.2% | 1 | **n<30** |
| 2.0% | 17 | 94.1% | 82.4% | 76.5% | 1 | **n<30** |
| 2.2% | 18 | 94.4% | 83.3% | 72.2% | 0 | **n<30** |
| 2.4% | 13 | 84.6% | 76.9% | 61.5% | 0 | **n<30** |
| 2.6% | 11 | 90.9% | 81.8% | 63.6% | 0 | **n<30** |
| 2.8% | 10 | 90.0% | 80.0% | 70.0% | 0 | **n<30** |
| 3.0% | 7 | 85.7% | 71.4% | 71.4% | 0 | **n<30** |
| 3.2% | 7 | 100.0% | 85.7% | 71.4% | 0 | **n<30** |
| 3.4% | 7 | 100.0% | 85.7% | 71.4% | 0 | **n<30** |
| 3.6% | 6 | 100.0% | 83.3% | 66.7% | 0 | **n<30** |
| 3.8% | 4 | 100.0% | 100.0% | 75.0% | 0 | **n<30** |
| 4.0% | 4 | 100.0% | 100.0% | 75.0% | 0 | **n<30** |
| 4.2% | 4 | 100.0% | 100.0% | 75.0% | 0 | **n<30** |
| 4.4% | 5 | 100.0% | 100.0% | 80.0% | 0 | **n<30** |
| 4.6% | 4 | 100.0% | 100.0% | 100.0% | 0 | **n<30** |
| 4.8% | 4 | 100.0% | 100.0% | 100.0% | 0 | **n<30** |
| 5.0% | 4 | 100.0% | 100.0% | 100.0% | 0 | **n<30** |

**Every single threshold falls below the 30-trade floor.** No exception.

## Full sweep table — BANKNIFTY, last 2 years only

| Threshold | n | Hit +1% | Hit +2% | Hit +3% | Truncated (excluded) | Small-sample flag |
|---|---|---|---|---|---|---|
| 1.0% | 25 | 80.0% | 80.0% | 76.0% | 2 | **n<30** |
| 1.2% | 22 | 81.8% | 81.8% | 77.3% | 2 | **n<30** |
| 1.4% | 24 | 87.5% | 79.2% | 70.8% | 2 | **n<30** |
| 1.6% | 17 | 88.2% | 76.5% | 64.7% | 0 | **n<30** |
| 1.8% | 15 | 86.7% | 73.3% | 73.3% | 0 | **n<30** |
| 2.0% | 14 | 92.9% | 85.7% | 78.6% | 0 | **n<30** |
| 2.2% | 13 | 84.6% | 76.9% | 69.2% | 0 | **n<30** |
| 2.4% | 13 | 84.6% | 69.2% | 61.5% | 0 | **n<30** |
| 2.6% | 11 | 81.8% | 63.6% | 54.5% | 0 | **n<30** |
| 2.8% | 10 | 90.0% | 80.0% | 60.0% | 0 | **n<30** |
| 3.0% | 7 | 85.7% | 71.4% | 42.9% | 0 | **n<30** |
| 3.2% | 3 | 66.7% | 66.7% | 66.7% | 0 | **n<30** |
| 3.4% | 3 | 66.7% | 66.7% | 66.7% | 0 | **n<30** |
| 3.6% | 5 | 80.0% | 80.0% | 80.0% | 0 | **n<30** |
| 3.8% | 4 | 100.0% | 100.0% | 75.0% | 0 | **n<30** |
| 4.0% | 4 | 100.0% | 100.0% | 75.0% | 0 | **n<30** |
| 4.2% | 5 | 100.0% | 100.0% | 80.0% | 0 | **n<30** |
| 4.4% | 5 | 100.0% | 100.0% | 80.0% | 0 | **n<30** |
| 4.6% | 5 | 100.0% | 100.0% | 80.0% | 0 | **n<30** |
| 4.8% | 5 | 100.0% | 100.0% | 80.0% | 0 | **n<30** |
| 5.0% | 5 | 100.0% | 100.0% | 80.0% | 0 | **n<30** |

**Every single threshold falls below the 30-trade floor** (best case n=25 at 1.0%).

## Confidence intervals (only where n is large enough to say anything at all)

Per instruction, no full walk-forward/regime-block gauntlet was run on a 2-year sample — there
isn't enough history to split into meaningful train/test or 5-year blocks. Instead, an
exact-binomial 90% CI is reported for every bucket at or above the ~25-trade mark (the closest
either symbol gets to the project's own 30-trade floor), plus a bootstrap CI (i.i.d.-resampling
caveat applies, same as elsewhere in this study) for every bucket n>=15 as a softer,
descriptive cross-check:

| Symbol | Threshold | n | Hit +1% | 90% exact-binomial CI | 90% bootstrap CI |
|---|---|---|---|---|---|
| NIFTY50 | 1.0% | 23 | 82.6% | n/a (below 25) | [69.6%, 95.7%] |
| NIFTY50 | 1.2% | 24 | 79.2% | n/a (below 25) | [66.7%, 91.7%] |
| NIFTY50 | 1.4% | 24 | 83.3% | n/a (below 25) | [70.8%, 95.8%] |
| NIFTY50 | 1.6% | 22 | 86.4% | n/a (below 25) | [72.7%, 95.5%] |
| NIFTY50 | 1.8% | 18 | 88.9% | n/a (below 25) | [77.8%, 100.0%] |
| NIFTY50 | 2.0% | 17 | 94.1% | n/a (below 25) | [82.4%, 100.0%] |
| NIFTY50 | 2.2% | 18 | 94.4% | n/a (below 25) | [83.3%, 100.0%] |
| BANKNIFTY | **1.0%** | **25** | **80.0%** | **[62.5%, 91.8%]** | [68.0%, 92.0%] |
| BANKNIFTY | 1.2% | 22 | 81.8% | n/a (below 25) | [68.2%, 95.5%] |
| BANKNIFTY | 1.4% | 24 | 87.5% | n/a (below 25) | [75.0%, 95.8%] |
| BANKNIFTY | 1.6% | 17 | 88.2% | n/a (below 25) | [76.5%, 100.0%] |
| BANKNIFTY | 1.8% | 15 | 86.7% | n/a (below 25) | [73.3%, 100.0%] |

BANKNIFTY 1.0% is the **only** bucket across both symbols and all 21 thresholds that even
nominally reaches this project's ~25-trade minimum for reporting a CI at all — and its 90%
exact-binomial CI ([62.5%, 91.8%]) is wide enough to be compatible with everything from "clearly
below the 90% bar" to "comfortably above it." No threshold for either symbol has a CI whose
lower bound clears 90% — a sharp contrast with Part 6's full-19-year NIFTY50 sweep, where 3.2%
cleared 90% at the lower bound with n=102. This is exactly what the ~5x smaller sample (2 years
vs. ~20) predicts: wider, less informative intervals, not a different underlying signal.

## Comparison: does the 2-year NIFTY50 sweep look consistent with the full 19-year sweep (Part 6)?

| Threshold | Full-history (Part 6) n / hit1% | 2yr-only n / hit1% | Direction |
|---|---|---|---|
| 1.0% | 238 / 90.3% | 23 / 82.6% | 2yr lower |
| 1.2% | 221 / 90.5% | 24 / 79.2% | 2yr lower |
| 1.4% | 207 / 90.3% | 24 / 83.3% | 2yr lower |
| 1.6% | 196 / 92.3% | 22 / 86.4% | 2yr lower |
| 1.8% | 186 / 90.9% | 18 / 88.9% | roughly in line |
| 2.0% | 176 / 93.8% | 17 / 94.1% | roughly in line |
| 2.2% | 164 / 93.3% | 18 / 94.4% | roughly in line |
| 3.0% (baseline) | 111 / 93.7% | 7 / 85.7% | 2yr lower, n too thin to weigh |

**Frequency check (signals/year) is reassuring — the signal is still firing at roughly its
historical rate, not vanishing or exploding:** at 1.0%, full history averages ~12.0
signals/year (238 over ~19.8 years); the 2-year window produced 23 signals ≈ 11.6/year —
essentially identical cadence. At 3.0%, full history averages ~5.6/year (111/19.8yr); the
2-year window produced only 3.5/year (7/1.98yr) — a real, if statistically thin, drop in how
often a >=3% single-day EMA20 breach has occurred recently, consistent with 2024-2026 being a
somewhat less violently mean-reverting regime at the deep-breach end than NIFTY's 20-year
average, though n=7 is nowhere near enough to confirm this as a structural regime shift versus
noise.

**Hit-rate shape:** at the loose end (1.0-1.6%), the last 2 years print hit rates 6-11
percentage points below the full-history average at the same threshold — every one of the four
misses in this window happened in identifiable, real corrections (see "Where it fails" below),
so this reads as "the last 2 years happened to contain a slightly higher density of
non-recovering pullbacks than NIFTY's 20-year average," not evidence the signal itself is
degrading. At 1.8-2.2%, the 2-year numbers land within ~1pp of the full-history average —
genuinely consistent. At 2.4%+ the 2-year sample is too thin (n<=13) to compare meaningfully at
all. **Net: the 2-year NIFTY50 data is broadly consistent with, not contradictory to, the
19-year study — noisier, as a 10%-sized subsample of the full history should be, with no
threshold showing a hit-rate collapse that would flag the underlying edge as broken.**

## Does BANKNIFTY behave like NIFTY50, or differently?

BANKNIFTY's loose-end hit rates (1.0-1.4%: 80.0-87.5%, n=22-25) sit in the same lower band as
NIFTY50's own 2-year numbers at the same thresholds (79.2-86.4%) — the two indices look similar
to each other over this specific recent window, for whatever that's worth at n<=25. Where they
diverge is at the tightened end: NIFTY50's 2-year sample shows something that at least visually
resembles Part 6's full-history hump (a run of 100.0% prints from 3.2% through 5.0%, albeit on
n=4-7), while BANKNIFTY's tightened-end sample is choppier and even dips to its worst reading of
the whole sweep (66.7% at 3.2%/3.4%, n=3) before recovering to 100% at n<=5 buckets beyond
3.8%. **This is not evidence BANKNIFTY has a genuinely different optimal threshold from
NIFTY50** — it is exactly the shape you'd expect from taking a real, roughly-similar underlying
process and observing it through two independent n=3-11 windows: some noise will land high,
some will land low, and neither symbol has anywhere near enough recent-window signal
occurrences at the tightened end to distinguish "different optimal parameter" from "coin-flip
variance on 3-11 trades." BANKNIFTY has never been swept over its own full ~20-year history in
this study, so there is no full-history BANKNIFTY baseline (analogous to Part 6's NIFTY50 one)
to check its 2-year numbers against — that would be the natural next step if BANKNIFTY is to be
taken further, not a finer 2-year-only sweep.

## Where it fails

Every miss in the 1.0% NIFTY50 bucket (4 misses, n=23) and the 1.0% BANKNIFTY bucket (5 misses,
n=25) clusters into identifiable, real market stress episodes rather than being scattered
randomly through the 2-year window:

- **NIFTY50:** 2024-10-03 and 2024-10-16 (the Oct 2024 FII-outflow-driven correction),
  2025-01-06 (Jan 2025 correction), 2026-02-27 (worst of the four — 11.9% max adverse dip
  before the window expired without recovering to +1%, part of the Feb-Mar 2026 correction
  already documented as a failure episode elsewhere in this study).
- **BANKNIFTY:** 2024-12-18 and 2025-01-03 (same broad Dec 2024/Jan 2025 correction window as
  NIFTY50's Jan 2025 miss), 2025-07-28 and 2025-07-31 (two misses three trading days apart,
  same underlying drawdown episode), 2026-03-02 (the worst of all ten misses across both
  symbols — 16.5% max adverse dip, same Feb-Mar 2026 correction as NIFTY50's 2026-02-27 miss).

Both symbols' worst single miss (NIFTY50 2026-02-27, BANKNIFTY 2026-03-02) sit within days of
each other, in the same correction — consistent with the structural failure mode already
documented in Parts 5/6 (EMA20-gap mean-reversion signals fail when the macro/market-wide
selloff is severe or fast enough that a single 42-day window isn't enough time to recover),
not a new or index-specific failure mode.

## Bias checks

- **Lookahead bias:** none found — identical `detect_ema20gap_signals()` /
  `compute_forward_outcomes_directional()` construction as Parts 5/6, only the fire-day date
  filter and symbol are new; the 2-year window restriction itself introduces no lookahead (it
  restricts which already-detected, already-lookahead-safe signals get scored, exactly the
  D-family's established `window_start` convention).
- **Survivorship bias:** N/A for NIFTY50 (single index, unchanged from Parts 5/6). N/A for
  BANKNIFTY too — it is a single, currently-live NSE sectoral index, not a basket with
  changing membership.
- **Overfitting / small-sample risk:** this is the dominant risk in this entire section, not a
  side note. Sweeping 21 thresholds across 2 symbols on a ~495-trading-day window produces 42
  buckets, the overwhelming majority with n<15 and several with n<=5 — at that sample size,
  "100% hit rate" buckets are close to guaranteed to appear somewhere in the sweep purely by
  chance even if the true underlying hit rate is a constant, unremarkable 90% (a coin that
  lands heads 90% of the time will show a run of 3-5 straight heads a large fraction of the
  time). None of the tightened-threshold "100%" results in either sweep table above should be
  treated as a finding, a parameter recommendation, or evidence that tightening the threshold
  "improves" anything in this window — they are exactly the small-sample noise pattern this
  project has explicitly flagged and rejected before (see Memory: "Backtest sample size").

## Recommendation

**Kill this as a standalone finding — the 2-year window, on its own, cannot support any
threshold choice for either symbol, and should not be used to argue for or against the existing
3.0%/3.2% NIFTY50 baseline from Parts 5/6.** Every one of 42 (21 thresholds × 2 symbols)
buckets sits below this project's own 30-trade floor; the single largest (BANKNIFTY 1.0%,
n=25) still carries a 90% CI 29 points wide. The honest, useful reading of this exercise is
narrower than "what's the best threshold in the last 2 years" — it is a consistency check, and
on that count it passes: NIFTY50's 2-year behavior at the thresholds with enough signals to
compare (1.8-2.2%) tracks the full-19-year study closely, and the loose-end shortfall (1.0-1.6%)
is fully explained by a handful of identifiable 2024-2026 corrections rather than a structural
break. BANKNIFTY, appearing in this study for the first time, is plausibly similar to NIFTY50
over this window but genuinely cannot be distinguished from it or characterized on its own
terms at this sample depth — if BANKNIFTY is worth pursuing, the correct next step is a
full-history (~20-year) BANKNIFTY sweep analogous to Parts 5/6, not a repeat of this 2-year-only
exercise. Do not ship a BANKNIFTY-specific threshold off this data, and do not let the 2-year
NIFTY50 numbers move the existing 3.0%/3.2% recommendation in either direction.

# Part 8 — BANKNIFTY full-history F1 validation + days-to-1pct (holding-period) validation for NIFTY50 and BANKNIFTY (2026-07-29 session)

Run date: 2026-07-29. Two things new to this study, both requested explicitly this session:
(1) the first **full ~20-year, fully-gauntleted** BANKNIFTY validation (Part 7 only ever
scored a 2-year window, which fell below the 30-trade floor at every threshold) — this closes
that gap; and (2) the first validation of `days_to_1pct` (the trading-day count from entry to
the +1% target being touched), a field `compute_forward_outcomes_directional()` has computed
all along but this study never previously reported or stress-tested. Same script
(`nifty_entry_signal_backtest.py`), same F1 (LONG-only, mean-reversion-up) definition and
42-trading-day window as Parts 5-7, same `detect_ema20gap_signals()` /
`compute_forward_outcomes_directional()` / `walk_forward()` / `regime_blocks()` /
`bootstrap_ci()` functions reused unchanged. A new symbol-generalized loader (`load_clean()`,
identical dedup/OHLC-integrity logic to `load_clean_nifty()` with `symbol` as a parameter) and
new holding-period-specific validation helpers (`days_stats`, `days_bootstrap_ci`,
`days_walk_forward`, `days_regime_blocks`, `miss_lockup_analysis`, `exact_binomial_ci`) were
written for this session — see the scratch driver referenced below. This section does not
modify Parts 1-7.

```
VERDICT: BANKNIFTY's full-history F1 result is now genuinely validated, and it comes out
STRONGER and MORE ROBUST than NIFTY50's own F1 baseline, not weaker -- a real edge, not a
Part-5-F2-style collapse. At the exploratory-query threshold (3.0%, n=162), hit1%=96.3% with
a 90% exact-binomial CI of [92.8%, 98.4%] -- the lower bound clears 90% by a wider margin than
NIFTY50 ever managed in this study (Part 6's best NIFTY50 CI floor was 91.3% at 3.2%, n=102).
Walk-forward (train n=103, 96.1% -> test n=59, 96.6%) and all four ~5-year regime blocks
(93.2%-98.3%, including the GFC-era and 2022-26 blocks) hold up cleanly, with no sign of
overfitting or regime-dependent collapse. Unusually, the full 2.8%-5.0% threshold band is
ALL comfortably above 90% (exact-binomial CI floors 89.8-93.6% across 9 thresholds) -- a wider,
flatter robustness plateau than NIFTY50's own narrower 2.8-3.6% hump, meaning BANKNIFTY's
result is not a lucky single-point pick. The days-to-1pct (holding-period) finding also
validates cleanly for BOTH symbols: median stays at 1-2 trading days and mean stays in a tight
3-6 day band across every walk-forward split and every regime block tested, INCLUDING the
2007-11 GFC-era block -- there is no "holding period blows up during a crisis" effect, which
was the main thing this check was designed to catch. The one caveat that matters: because this
whole study only ever scores signals with a complete 42-trading-day forward window, every
MISS sits open for exactly 42 trading days (~2 calendar months) by construction -- there is no
distribution to characterize there, but the misses that do occur (7/8 of NIFTY50's, 6/6 of
BANKNIFTY's, at the headline thresholds) carry severe average drawdowns (19-24% max adverse
dip) concentrated in the same GFC/2011/2016/2026-correction episodes already flagged as the
structural failure mode in Parts 1-7 -- the worst-case capital lockup is bounded in TIME but not
small in DRAWDOWN.
```

## Strategy as tested

Identical to Parts 5-7's F1 definition: `gap_pct = (close - EMA20) / EMA20 * 100` crosses
BELOW `-threshold` (a threshold-crossing signal, fires once on first breach); `entry_price =
close[t]`; bet is mean-reversion UP; target/adverse-move semantics via
`compute_forward_outcomes_directional(df, idxs, name, "long")`; 42-trading-day forward window;
+1%/+2%/+3% targets tracked on the daily HIGH, drawdown-tolerant hit definition (a dip-then-
recover within the window still counts as a hit). New in this section: `days_to_1pct` (already
computed by `compute_forward_outcomes_directional()`, never previously reported) is now the
primary object of Part B's validation, alongside the standard hit-rate gauntlet in Part A for
BANKNIFTY specifically.

- **Universe / timeframe:** NIFTY 50 index and BANKNIFTY index (spot level), daily candles,
  `candles_1d` in `drishti.db`.
- **Sizing:** none (signal-quality study, consistent with the rest of this project).
- **Assumptions made:** none new — this section reuses every convention (entry price, window
  length, hit definition, dedup logic, regime-block boundaries, walk-forward split date)
  already established and stated in Parts 1, 5, and 6.

## Data

- **Source:** SQLite (`drishti.db`), `candles_1d`, symbols `NIFTY50` and `BANKNIFTY`. No
  yfinance fallback needed for either.
- **NIFTY50:** 4,951 deduped trading days, 2006-08-02 → 2026-07-27 (identical to Parts 5-7 —
  re-verified as a sanity check: re-running the existing 3.0%/3.2%/3.4% thresholds through this
  session's own driver reproduces Part 6's exact n and hit-rate figures (n=111/93.7%,
  n=102/96.1%, n=95/95.8%), confirming no data drift and no logic divergence from the base
  script).
- **BANKNIFTY:** 4,936 deduped trading days, 2006-08-02 → 2026-07-27 — essentially the same
  ~20-year depth as NIFTY50 (15 fewer rows, immaterial). Same dedup logic applied (duplicate
  UTC-timestamp-encoding artifact, one row kept per IST calendar date): zero duplicate dates,
  zero OHLC integrity violations survived. `volume` is 0 on every single BANKNIFTY row (same
  known index-data characteristic already documented for NIFTY50) — irrelevant here since F1
  uses only close/EMA20.
- **Window:** full history for both symbols, 2006-08-02 → 2026-07-27 (~20.0 years each).

## Part A — BANKNIFTY full-history hit-rate validation

### Full threshold sweep, BANKNIFTY F1 (long), 2.0%-5.0% step 0.2% (16 thresholds)

| Threshold | n | Hit +1% | Hit +2% | Hit +3% | 90% exact-binomial CI | Signals/yr |
|---|---|---|---|---|---|---|
| 2.0% | 201 | 93.5% | 86.1% | 79.6% | [89.9%, 96.1%] | 10.06 |
| 2.2% | 195 | 93.3% | 86.7% | 81.5% | [89.6%, 96.0%] | 9.76 |
| 2.4% | 185 | 92.4% | 85.9% | 80.0% | [88.4%, 95.4%] | 9.26 |
| 2.6% | 183 | 92.9% | 85.8% | 82.0% | [88.9%, 95.7%] | 9.16 |
| 2.8% | 171 | 94.2% | 86.5% | 82.5% | [90.3%, 96.8%] | 8.56 |
| **3.0%** | **162** | **96.3%** | **90.1%** | **84.6%** | **[92.8%, 98.4%]** | **8.11** |
| 3.2% | 148 | 95.3% | 90.5% | 86.5% | [91.3%, 97.8%] | 7.41 |
| 3.4% | 138 | 94.2% | 91.3% | 87.0% | [89.8%, 97.1%] | 6.91 |
| 3.6% | 141 | 95.7% | 91.5% | 86.5% | [91.8%, 98.1%] | 7.06 |
| 3.8% | 125 | 96.0% | 91.2% | 84.8% | [91.8%, 98.4%] | 6.26 |
| **4.0%** | **118** | **97.5%** | **91.5%** | **84.7%** | **[93.6%, 99.3%]** | **5.90** |
| 4.2% | 114 | 96.5% | 91.2% | 86.0% | [92.2%, 98.8%] | 5.70 |
| 4.4% | 108 | 96.3% | 90.7% | 85.2% | [91.7%, 98.7%] | 5.40 |
| 4.6% | 100 | 96.0% | 91.0% | 85.0% | [91.1%, 98.6%] | 5.00 |
| 4.8% | 92 | 96.7% | 91.3% | 87.0% | [91.8%, 99.1%] | 4.60 |
| 5.0% | 90 | 96.7% | 91.1% | 87.8% | [91.6%, 99.1%] | 4.50 |

**Every threshold from 2.0% through 5.0% clears n=90**, and **every exact-binomial CI lower
bound from 2.8% through 5.0% sits at or above 89.8%** (12 of 13 thresholds in that band clear
90% outright) — a materially wider and flatter robustness plateau than NIFTY50's own F1 sweep
in Part 6, where the CI floor only cleared 90% at a single point (3.2%). Signal frequency
(4.5-10 signals/year) declines smoothly and monotonically as the threshold tightens, exactly
the expected mechanical relationship, with no sudden collapse anywhere in the grid (unlike
Part 7's 2-year window, where BANKNIFTY's tightened end fell to n=3-5).

### Full validation gauntlet — four candidate thresholds (2.8%, 3.0%, 3.2%, 3.4%) plus 3.6%/4.0% for context

**Walk-forward (train = pre-2018, test = 2018 onward — includes COVID crash, 2022 correction, 2026 correction)**

| Threshold | Train n | Train hit1% | Test n | Test hit1% | Gap |
|---|---|---|---|---|---|
| 2.8% | 103 | 92.2% | 68 | 97.1% | +4.9pp |
| **3.0%** | **103** | **96.1%** | **59** | **96.6%** | **+0.5pp** |
| 3.2% | 101 | 95.0% | 47 | 95.7% | +0.7pp |
| 3.4% | 93 | 93.5% | 45 | 95.6% | +2.1pp |
| 3.6% | 94 | 94.7% | 47 | 97.9% | +3.2pp |
| 4.0% | 84 | 96.4% | 34 | 100.0% | +3.6pp |

Every threshold improves (or holds flat) out-of-sample — none show the train ≫ test
overfitting red flag. 3.0% in particular is nearly perfectly stable (96.1% → 96.6%), the
tightest train/test gap of any threshold tested for either symbol in this entire study.

**Regime-block consistency (four ~5-year blocks)**

| Threshold | 2007-11 | 2012-16 | 2017-21 | 2022-26 |
|---|---|---|---|---|
| 2.8% | n=56, 94.6% | n=46, 89.1% | n=41, 97.6% | n=27, 96.3% |
| **3.0%** | **n=58, 98.3%** | **n=44, 93.2%** | **n=34, 97.1%** | **n=25, 96.0%** |
| 3.2% | n=60, 98.3% | n=40, 90.0% | n=31, 96.8% | n=16, 93.8% |
| 3.4% | n=58, 94.8% | n=34, 91.2% | n=31, 96.8% | n=14, 92.9% |
| 3.6% | n=61, 95.1% | n=32, 93.8% | n=30, 100.0% | n=17, 94.1% |
| 4.0% | n=55, 96.4% | n=28, 96.4% | n=21, 100.0% | n=13, 100.0% |

At 3.0%, all four blocks — including 2007-11 (GFC + 2011 correction) and 2022-26 (2026
correction, still in-sample here) — land in a tight 93.2%-98.3% band. This is a genuine
cross-regime plateau, not a result driven by one calm slice of history, and the GFC-era block
is if anything the *strongest* of the four (98.3%), the opposite of what a fragile,
crisis-vulnerable signal would show.

**Monte Carlo bootstrap (5,000 resamples) and exact-binomial CI**

| Threshold | n | Point hit1% | 90% bootstrap CI | 90% exact-binomial CI |
|---|---|---|---|---|
| 2.8% | 171 | 94.2% | [91.2%, 97.1%] | [90.3%, 96.8%] |
| **3.0%** | **162** | **96.3%** | **[93.8%, 98.8%]** | **[92.8%, 98.4%]** |
| 3.2% | 148 | 95.3% | [91.9%, 98.0%] | [91.3%, 97.8%] |
| 3.4% | 138 | 94.2% | [90.6%, 97.1%] | [89.8%, 97.1%] |
| 4.0% | 118 | 97.5% | [94.9%, 99.2%] | [93.6%, 99.3%] |

3.0% and 4.0% both post exact-binomial CI floors above 92.5% — comfortably clear of the user's
~90% bar, and clearer than any NIFTY50 threshold managed in Part 6. Same i.i.d.-resampling
caveat as every bootstrap CI elsewhere in this study applies (signals cluster in time, so this
understates true uncertainty somewhat).

**Definition-sensitivity stress test (close-based hit, not high-based — substitute for
cost-doubling, identical methodology to Parts 5-7)**

| Threshold | n | High-based hit1% | Close-based hit1% | Degradation |
|---|---|---|---|---|
| 2.8% | 171 | 94.2% | 88.9% | -5.3pp |
| **3.0%** | **162** | **96.3%** | **90.7%** | **-5.6pp** |
| 3.2% | 148 | 95.3% | 89.9% | -5.4pp |
| 3.4% | 138 | 94.2% | 89.9% | -4.3pp |
| 3.6% | 141 | 95.7% | 90.1% | -5.6pp |
| 4.0% | 118 | 97.5% | 89.8% | -7.7pp |

Degradation magnitude (4.3-7.7pp) is comparable to NIFTY50's own -5.4pp at 3.0% in Part 6 — the
touches are not razor-thin one-day wicks any more than NIFTY50's are, and 3.0%/3.2%/3.4% all
still clear ~90% even under this stricter proxy.

### Bias checks

- **Lookahead bias:** none found — identical `detect_ema20gap_signals()` /
  `compute_forward_outcomes_directional()` construction as Parts 5-7; applying it to a new
  symbol introduces no new lookahead risk (same-bar close/EMA20 function, crossing test only
  compares `gap_pct[t]` to `gap_pct[t-1]`).
- **Survivorship bias:** N/A — BANKNIFTY, like NIFTY50, is a single continuously-live NSE
  sectoral index, not a basket with changing membership.
- **Overfitting:** low risk. The threshold that matches the original exploratory finding
  (3.0%) sits inside a demonstrated 9-threshold-wide plateau (2.8%-5.0%, all CI floors ≥89.8%),
  not an isolated spike — if anything, 4.0% and 4.8-5.0% show marginally *higher* point
  estimates and CI floors than 3.0%, so there is no evidence 3.0% was cherry-picked to look
  good; it is a reasonably representative point inside a wide, genuinely robust band. One
  honest caveat: the exploratory query that first surfaced 3.0% was itself unvalidated at the
  time (as stated in the task brief) — the fact that it independently reproduces here under
  full walk-forward/regime-block/bootstrap scrutiny is reassuring, not just re-confirmation of
  the same single unvalidated number.

## Part B — days-to-1pct (holding-period) validation

Scored on the same signal sets as the existing NIFTY50 F1 baselines (3.0%, 3.2%, from Parts 5/6)
and BANKNIFTY's newly-validated 3.0% threshold from Part A above. All stats below are computed
**among hits only** (misses have no `days_to_1pct` value by definition — see the miss-lockup
discussion below for how those are handled instead).

### Overall point estimates and bootstrap CI (5,000 resamples)

| Symbol @ threshold | n (hits) | Median days | Mean days | 90% bootstrap CI (median) | 90% bootstrap CI (mean) |
|---|---|---|---|---|---|
| NIFTY50 @ 3.0% | 104 | 1.0 | 4.90 | [1.0, 2.0] | [3.62, 6.31] |
| NIFTY50 @ 3.2% | 98 | 1.0 | 4.13 | [1.0, 2.0] | [3.03, 5.39] |
| BANKNIFTY @ 3.0% | 156 | 1.0 | 3.60 | [1.0, 1.0] | [2.85, 4.42] |

The exploratory "median ≈ 1 trading day" finding holds up with an honest error bar: the median
bootstrap CI is a tight [1.0, 2.0] days for both NIFTY50 thresholds and an even tighter
[1.0, 1.0] for BANKNIFTY (its larger n=156 hit-count narrows the median CI to a single value).
Mean days-to-hit (which better captures the modest right-skew from slower-resolving trades) is
3.6-4.9 trading days across all three, also with tight, non-overlapping-with-zero CIs — this is
a real, fast-resolving pattern, not noise around a much longer true holding period.

### Walk-forward (train = pre-2018, test = 2018 onward)

| Symbol @ threshold | Train n / median / mean | Test n / median / mean |
|---|---|---|
| NIFTY50 @ 3.0% | 72 / 1.0 / 5.29d | 32 / 1.0 / 4.03d |
| NIFTY50 @ 3.2% | 67 / 1.0 / 4.39d | 31 / 1.0 / 3.58d |
| BANKNIFTY @ 3.0% | 99 / 1.0 / 3.68d | 57 / 1.0 / 3.46d |

Median is perfectly stable at 1.0 day across every train/test split for both symbols. Mean
drifts modestly toward *faster* resolution out-of-sample for all three (a 1.0-1.3 day
reduction) rather than slower — the opposite direction of what a degrading, drifting signal
would show. BANKNIFTY is the most stable of the three (3.68d → 3.46d, essentially flat).

### Regime-block consistency (four ~5-year blocks) — does holding period blow up in a crisis era?

| Symbol @ threshold | 2007-11 | 2012-16 | 2017-21 | 2022-26 |
|---|---|---|---|---|
| NIFTY50 @ 3.0% | n=46, med 1.0, mean 5.85 | n=25, med 2.0, mean 4.44 | n=16, med 1.0, mean 4.00 | n=16, med 2.0, mean 4.06 |
| NIFTY50 @ 3.2% | n=43, med 1.0, mean 4.98 | n=23, med 1.0, mean 3.43 | n=14, med 1.0, mean 2.14 | n=17, med 2.0, mean 4.76 |
| BANKNIFTY @ 3.0% | n=57, med 1.0, mean 3.56 | n=41, med 2.0, mean 3.85 | n=33, med 2.0, mean 3.70 | n=24, med 1.0, mean 3.13 |

**This is the key finding for the brief's specific worry ("does a crisis period show much
longer holding periods before hitting +1%, even if the hit-rate is unaffected"): no, it does
not, for either symbol.** The 2007-11 block (GFC + 2011 correction) is NOT the slowest-resolving
block for any of the three signal/threshold combinations — NIFTY50 @ 3.0%'s 2007-11 mean
(5.85d) is its highest of the four blocks, but only modestly so (vs. 4.0-4.4d elsewhere), and
BANKNIFTY @ 3.0%'s 2007-11 mean (3.56d) is actually its *second-fastest* block. Median stays
locked at 1.0-2.0 days in every single block for every combination, with no exceptions. The
practical read: when this signal's entry-day dip resolves to a +1% touch at all, it resolves
fast (within 1-6 trading days on average) regardless of which multi-year era it fires in —
crisis eras do not meaningfully extend the holding period for the trades that do work out.

### Miss lockup — how long do trades that DON'T hit sit open, and what does that period look like?

| Symbol @ threshold | n miss | Days held before window expiry | Mean best fwd gain reached | Mean max adverse dip |
|---|---|---|---|---|
| NIFTY50 @ 3.0% | 7 | **42 (fixed, every miss)** | +0.13% | 18.88% |
| NIFTY50 @ 3.2% | 4 | **42 (fixed, every miss)** | -0.35% | 24.25% |
| BANKNIFTY @ 3.0% | 6 | **42 (fixed, every miss)** | +0.18% | 19.35% |

**By construction, this is not a distribution to bootstrap — every miss in this study's
headline stats sits open for exactly 42 trading days (~2 calendar months) before being marked a
loss**, because only signals with a complete 42-day forward window are ever included in the
scored sample (the `i + FORWARD_WINDOW <= n-1` filter used everywhere in this study). There is
no variation in "time to give up" to characterize — it is a fixed property of the study design,
not an empirical finding, and this is worth stating plainly so it isn't mistaken for a
result. What *does* vary, and matters more for real capital-lockup risk, is the drawdown
suffered during that fixed 42-day hold: misses across all three combinations carry mean max
adverse dips of 18.9%-24.3% — these are not "just barely missed by a hair" trades, they are
trades caught in a genuine, severe drawdown (the underlying dates are the same GFC/2011/2016/
2026-correction episodes already documented as this signal family's structural failure mode in
Parts 1, 5, and 6). NIFTY50 @ 3.2%'s 4 misses are notably worse on this dimension (mean best
forward gain -0.35%, i.e. price never even got back above entry at any point in the window,
mean max adverse dip 24.25%) than the looser 3.0% threshold's 7 misses — consistent with 3.2%
having filtered out some of the milder, closer-to-recovering misses along with picking up a
slightly higher hit rate, the same mechanical effect already documented in Part 6's trade-level
diff between 3.0% and 3.2%.

Miss dates for reference: NIFTY50 @ 3.0% — 2008-01-18, 2008-02-06, 2008-06-02, 2008-09-26,
2011-08-04, 2016-01-07, 2026-03-06 (identical to Part 6's miss list). BANKNIFTY @ 3.0% —
2008-10-03, 2013-06-10, 2013-06-18, 2016-01-07, 2018-09-18, 2026-03-06. Two dates
(2016-01-07, 2026-03-06) are shared exactly between the two symbols — the same underlying
market-wide stress episodes drive misses in both, as expected for two correlated Indian
equity indices, though BANKNIFTY's other misses (2008-10-03 GFC acute phase, 2013-06-10/18
taper-tantrum, 2018-09-18 NBFC/IL&FS crisis) are sector-specific stress events distinct from
NIFTY50's own GFC-era miss cluster (Jan/Feb/Jun/Sep 2008), consistent with BANKNIFTY carrying
additional idiosyncratic financial-sector risk on top of broad-market risk.

## Where it fails

Same structural failure mode already documented throughout this study: both symbols' misses
cluster in identifiable macro/sector stress episodes (2008 GFC, 2011 correction, 2013 taper
tantrum, 2016 correction, 2018 NBFC crisis for BANKNIFTY specifically, 2026 correction) rather
than being scattered randomly through 20 years of data. No regime filter or threshold choice
tested anywhere in this study (Parts 1-8) reliably screens these out in advance, because the
technical backdrop (EMA200 slope, price-vs-EMA200) typically still looks unremarkable in the
days just before the shock hits. BANKNIFTY adds one new observation to this picture: its
misses include sector-specific stress (2018 NBFC/IL&FS crisis) not present in NIFTY50's own
miss list, meaning a BANKNIFTY position carries this signal's usual macro-shock risk *plus*
financial-sector-specific tail risk that a broad-index NIFTY50 position would not.

## Recommendation

**BANKNIFTY's full-history F1 result is validated and should be treated as at least as
trustworthy as NIFTY50's own F1 baseline — ship it, don't treat it as unproven.** At 3.0%
(matching the original exploratory finding), BANKNIFTY posts hit1%=96.3% (n=162) with a 90%
exact-binomial CI floor of 92.8%, clean walk-forward stability (96.1%→96.6%), consistent
regime-block performance including a strong GFC-era block (98.3%), and a wide 2.8%-5.0%
parameter plateau — genuinely more robust evidence than NIFTY50 managed at its own best
threshold in Part 6. If choosing a single BANKNIFTY threshold, 3.0% or 4.0% are the two
best-supported points (highest CI floors, 92.8% and 93.6% respectively); either is defensible,
and as with NIFTY50's 3.0%/3.2% choice in Part 6, this should be read as "pick a point inside a
validated plateau," not "there is one uniquely correct decimal." The days-to-1pct holding-period
finding is now genuinely validated, not just an unvalidated exploratory observation: median
1-2 trading days and mean 3.6-4.9 trading days hold up across every walk-forward split and
every regime block for both symbols, with no crisis-era blow-up — a trader using this signal
can reasonably expect fast resolution when it works. The one thing that must not get lost in
the "median 1 day" headline: when it doesn't work, the position doesn't just sit flat for 2
months, it sits in an average 19-24% drawdown for up to 42 trading days before being marked a
loss — this is a real, sizeable tail risk that any position-sizing or stop-loss design built on
top of this signal must account for explicitly, not a footnote. Next step if BANKNIFTY is
pursued further: since it now has its own full-history validation on par with NIFTY50, it could
reasonably be run through the same finer 1.0-5.0%/0.2%-step sweep Part 6 did for NIFTY50 (this
section used a coarser 0.2% grid from 2.0-5.0% only, not the exhaustive 21-point sweep), though
given how flat BANKNIFTY's plateau already looks at this resolution, a materially different
conclusion from that finer sweep seems unlikely.

# Part 9 — Independent adversarial audit of the "open-gap" variant (2026-07-29 session)

Run date: 2026-07-29. This section audits a NOT-YET-VALIDATED variant explored in ad hoc
scratch scripts earlier in this session ("open-gap": fires on today's OPEN breaching a
threshold vs an EMA20, entered at that same open, rather than F1's close-based trigger) after
it produced a suspicious result: 100.0% hit rate at literally every threshold tested (2.0-3.4%,
0.2% steps) in both the last-3-year and last-5-year windows, while its own sibling F1
(close-gap) showed genuine misses in the same windows at similar sample sizes. The audit below
is a full from-scratch, independent re-implementation — it does not reuse or trust any of the
prior scratch-script arithmetic — built as a standalone driver script (not merged into
`nifty_entry_signal_backtest.py` itself, since open-gap is not yet a promoted signal family;
see scratch script referenced in the methodology section below) that reuses only the
already-validated `load_clean_nifty()` / `add_indicators()` / `detect_ema20gap_signals()` /
`compute_forward_outcomes_directional()` functions from the existing script where a direct,
apples-to-apples close-gap comparison was needed.

```
VERDICT: NOT A BUG in the EMA math, the crossing/hysteresis logic, or the data -- all of those
independently check out clean. The "100% at every threshold" result IS a real artifact, but of
a SCORING-WINDOW DESIGN CHOICE, not of broken arithmetic: open-gap's forward-outcome window was
defined as high[t..t+41] (STARTING ON the entry day itself, using that day's own post-open
intraday high as a legitimate "already fair game" data point), whereas close-gap's window is
high[t+1..t+42] (never touching the entry day's own range). This asymmetry is real and
legitimate in principle -- entering at today's 9:15 open and then checking today's own
subsequent intraday high is not lookahead -- but it is NOT the same measurement convention as
close-gap uses, so comparing the two side by side ("open-gap beats close-gap in the recent
window") is not a fair comparison. Once open-gap is rescored under the IDENTICAL t+1..t+42
convention close-gap uses (removing the entry-day freebie), the "100% at every threshold"
result COMPLETELY DISAPPEARS in both the last-3y and last-5y windows, replaced by a normal
83-97% range with genuine misses reappearing at nearly every threshold -- materially the same
territory close-gap already occupies. Root-caused precisely: in every single one of the 32
threshold x window x variant buckets tested, exactly ONE date (2026-03-02) is the sole flip
from miss to hit; it is a single real, large gap-down (-2.06% overnight vs. the prior close)
followed by a genuine intraday recovery (day's high +1.34% off that day's open) that would be
scored a MISS under close-gap's own convention (price never revisits +1% above entry in the
following 42 trading days -- it heads into the March-2026 correction instead) but becomes a
"hit" purely because open-gap's window let it use its own entry-day high. Because this one
correction episode happens to be the only oversold breach in the last 3-5 years deep enough to
trip most/all of the 2.0-3.4% thresholds, the SAME single date drives the uniform 100% pattern
across the entire recent sweep -- this is why it looked so suspiciously clean across every
threshold rather than being a coincidence confined to one bucket. Under the corrected, fair
window, open-gap's full-history results (both sub-variants) are statistically indistinguishable
from close-gap's own already-validated numbers -- point estimates 91.9-94.0% vs. close-gap's
92.6-96.1%, with 90% exact-binomial CIs overlapping almost completely at every threshold. Open-
gap is not a stronger signal than close-gap; it is the same underlying mean-reversion edge
measured on a highly correlated (open vs. close) price series, with no material independent
information content once scored fairly.
```

## Methodology

Independent audit script: `/private/tmp/claude-501/-Users-aj-projects-edgevest/a5a6df7b-9a54-408a-a865-aefe24d37101/scratchpad/opengap_audit.py`
(scratch location — kept out of the repo since open-gap is not a promoted signal; logic is
fully reproduced inline below for the permanent record). Data reloaded from scratch via
`load_clean_nifty()` (NIFTY50, `candles_1d`, 2006-08-02 → 2026-07-27, 4,951 trading days) —
independently re-verified: 0 duplicate IST calendar dates, 0 OHLC integrity violations
(`high < max(open,close,low)` or `low > min(open,close,high)`), sorted strictly ascending by
date, one 6-trading-day gap found (2014-10-07, a known extended-holiday week, not a data hole).
Two open-gap sub-variants re-implemented independently:

- **prevCloseEMA**: `gap[t] = (open[t] - EMA20_of_close[t-1]) / EMA20_of_close[t-1] * 100`
  — `EMA20_of_close` is `pta.ema(close, length=20)`, identical function/parameters to the
  already-validated F1 close-gap signal; shifted by 1 day so only yesterday's close-based EMA
  (knowable at today's 9:15 open) is used.
- **openEMA**: `gap[t] = (open[t] - EMA20_of_open[t]) / EMA20_of_open[t] * 100` — `EMA20_of_open`
  is `pta.ema(open, length=20)`, a separate EMA computed over the OPEN price series itself,
  using only opens through and including today's own open (no close/high/low anywhere in this
  calculation).

Both use the identical crossing/hysteresis convention as F1: `gap[t] < -threshold AND
gap[t-1] >= -threshold` (fires once per breach episode, re-arms only after recovering above
`-threshold`) — independently re-derived, not copy-pasted, and confirmed to match
`detect_ema20gap_signals()`'s convention exactly.

## 1. EMA calculation and data-integrity checks

**EMA hand-verification (item 2 of the brief):** `pandas_ta`'s `ema()` (used throughout the
existing validated script, including F1's close-gap EMA20) is **SMA-seeded**: the first 19 rows
are NaN, and the seed value at index 19 is `SMA(close[0:20])`, with standard exponential
recursion (`alpha = 2/(N+1)`) applied from there on. This is subtly different from a naive
`pandas.Series.ewm(span=20, adjust=False).mean()`, which seeds at index 0 with the first raw
value instead and is non-NaN everywhere. **Hand-recomputed the SMA-seeded recursion manually in
a plain Python loop for 5 dates spanning the full history (2006-12-26, 2010-08-19, 2016-09-02,
2022-09-23, 2026-05-14) — all 5 match `pandas_ta`'s output to 6 decimal places exactly.** No
off-by-one, no indexing bug. The two seeding conventions (SMA-seed vs. raw-value-seed)
numerically converge fast — after ~60 trading days the mean absolute difference between them is
~0.0006-0.0007 index points, i.e. negligible everywhere except the first few months of
2006, which are far outside every window tested in this study (recent 3y/5y windows, or even
the full 2007+ walk-forward split). **This is not a bug, just a documented convention choice,
and it is identical for both the close-based and open-based EMA20 (both use `pta.ema`), so it
does not create any asymmetry between the close-gap and open-gap comparisons.**

**Sorting/duplicate-date check:** re-verified independently (not assumed from the prior
session's finding) — the current `candles_1d` table for NIFTY50 has **zero duplicate IST
calendar dates** and needs no dedup pass today (4,951 raw rows = 4,951 rows after the
`load_clean_nifty()` dedup logic runs, a no-op). The double-UTC-encoding artifact documented in
that function's docstring appears to have already been resolved in the live DB (or never
affected NIFTY50 specifically at its current row count) — worth noting for the record since the
brief flagged it as a real risk, but it did not materialize here.

**`open` column data-quality check (item 2's specific concern about `open` being a sync
artifact):** the overnight-gap distribution `(open[t] - close[t-1]) / close[t-1]` looks like a
normal, independent price series — mean +0.088%, std 0.55%, min -9.14% (a real crash-gap day),
max +4.86%, with the bulk of mass in a tight ±0.3-0.8% band at the 25th/75th percentiles. Only
**38 of 4,950 rows (0.77%)** have `open` exactly equal to the prior day's `close` — and all 38
are clustered in **2006-2012** (5 in 2006, 10 in 2007, 4 in 2008, 7 in 2009, 10 in 2010, 1 in
2012, 1 in 2017, **zero from 2018 onward**). This is old-era NSE settlement/pre-open-session
behavior, not a sync bug, and critically it cannot be contaminating the suspicious recent-window
(2021+/2023+) result since none of those flagged rows fall in that period.

**Silent lookahead check (item 2's core ask):** confirmed the signal trigger itself never
touches same-day close/high/low — `prevCloseEMA`'s base is `EMA20_of_close.shift(1)`
(yesterday's value only) and `openEMA`'s base is `EMA20_of_open[t]` (today's own open only, via
backward-recursive EMA over the open series exclusively). Neither uses information not knowable
at 9:15am on day t. **No lookahead bug found in signal construction.**

## 2. The real finding: entry-day-inclusive forward window vs. close-gap's entry-day-exclusive window

Close-gap's forward window (`compute_forward_outcomes_directional`) is `high[t+1 .. t+42]` —
day t's own high/low are never used, since entry is conceptually "at t's close" and the very
next observable price action is t+1. The open-gap scratch methodology instead used
`high[t .. t+41]` — 42 candles STARTING on the entry day, on the reasoning that entry happens at
that day's open and its own subsequent intraday high is fair game (not technically lookahead).
Both are internally defensible no-lookahead conventions, but **they are not the same
convention**, and the difference is not academic: it gives open-gap one extra chance per signal
(the entry day's own high) that close-gap structurally cannot have.

**Quantifying the effect, full ~20-year history:**

| Window convention | prevCloseEMA hit1% (n range 100-173) | openEMA hit1% (n range 103-175) |
|---|---|---|
| Entry-day-included (as used in the suspicious result) | 94.0-95.4% | 94.2-96.0% |
| Fair window t+1..t+42 (close-gap's convention) | 91.9-93.9% | 92.0-94.0% |

The full-history effect of the window choice is real but modest — roughly **1-2 percentage
points** of uplift, because most "day-0 hits" would have hit later in the window anyway even
without the freebie (removing day 0 just delays the hit-day count, it usually doesn't create a
miss). Same-day hits make up **36-49% of all hits** across thresholds — a large share of the
raw hit count, but only a small fraction of those are hits *exclusively* because of day 0.

**In the small recent-window samples, this small effect is enough to be decisive.** A per-signal
diagnostic across all 8 thresholds x 2 windows x 2 variants (32 buckets) found that **in every
single bucket, exactly one signal flips from a miss (fair window) to a hit (entry-day-included
window), and it is always the same date: 2026-03-02.**

```
2026-03-02: prior close 25,178.65 -> open 24,659.25 (overnight gap -2.06%)
gap_pct vs EMA20-of-prior-close = -3.51% (a genuine deep breach, well past every threshold tested)
Day's own high: 24,989.35 = +1.34% above the day's open (24,905.84 needed for +1%) -- a real,
comfortable same-day intraday recovery.
Fair window (t+1..t+42, i.e. 2026-03-04 onward): price NEVER touches 24,905.84 again within 42
trading days -- it falls further into the broader March-2026 correction instead. This is a
genuine MISS under close-gap's own scoring convention.
```

Because 2026-03-02 happens to be the deepest, most recent oversold breach in the last 3-5 years
— deep enough to trip every threshold from 2.0% through 3.4% simultaneously — the same single
flipped date recurs across the *entire* threshold sweep, which is exactly what produced the
suspicious "100% at literally every threshold" pattern: it isn't 8 independent confirmations of
robustness, it's the same one data point counted 8 times.

## 3. Corrected (fair-window) recent-window sweep — does 100% survive?

Re-ran the last-3y and last-5y sweeps using the fair `t+1..t+42` window (excluding the entry
day's own high), identical convention to close-gap.

**Last 3 years (fire date ≥ 2023-07-29):**

| Threshold | prevCloseEMA n / hit1% | openEMA n / hit1% |
|---|---|---|
| 2.0% | 20 / 95.0% | 21 / 95.2% |
| 2.2% | 16 / 93.8% | 17 / 94.1% |
| 2.4% | 13 / 92.3% | 12 / 91.7% |
| 2.6% | 10 / 90.0% | 13 / 92.3% |
| 2.8% | 7 / 85.7% | 7 / 85.7% |
| 3.0% | 8 / 87.5% | 7 / 85.7% |
| 3.2% | 6 / 83.3% | 8 / 87.5% |
| 3.4% | 8 / 87.5% | 8 / 87.5% |

**Last 5 years (fire date ≥ 2021-07-29):**

| Threshold | prevCloseEMA n / hit1% | openEMA n / hit1% |
|---|---|---|
| 2.0% | 37 / 97.3% | 40 / 97.5% |
| 2.2% | 34 / 97.1% | 35 / 97.1% |
| 2.4% | 29 / 96.6% | 30 / 96.7% |
| 2.6% | 26 / 96.2% | 30 / 96.7% |
| 2.8% | 24 / 95.8% | 23 / 95.7% |
| 3.0% | 21 / 95.2% | 19 / 94.7% |
| 3.2% | 17 / 94.1% | 19 / 94.7% |
| 3.4% | 19 / 94.7% | 19 / 94.7% |

**The 100%-at-every-threshold result does NOT survive independent re-implementation under a
fair scoring convention.** Both windows now show a normal, believable range (83.3-97.5%) with
real misses at nearly every threshold — the pattern close-gap already showed in the same
windows, not a categorically cleaner one. The small-sample caveat applies throughout (several
buckets have n<20, and the 2.8-3.4% last-3y buckets have n=6-8, below the ~30-trade floor this
study otherwise insists on for any hit-rate claim — these single-digit-n buckets should not be
read as statistically meaningful in either direction).

## 4. Full-history validation: bootstrap / exact-binomial CI, open-gap vs. close-gap head-to-head

Full ~20-year history, fair window, 90% bootstrap (5,000 resamples) and exact-binomial
(Clopper-Pearson) CIs for both open-gap variants, set directly alongside close-gap's own
already-validated Part 6 numbers (recomputed here from the same underlying function for an
exact apples-to-apples row):

| Threshold | Close-gap (F1) n / hit1% / 90% exact CI | prevCloseEMA n / hit1% / 90% exact CI | openEMA n / hit1% / 90% exact CI |
|---|---|---|---|
| 2.0% | 176 / 93.8% / [89.9%, 96.5%] | 173 / 91.9% / [87.6%, 95.0%] | 175 / 92.0% / [87.8%, 95.1%] |
| 2.2% | 164 / 93.3% / [89.1%, 96.2%] | 170 / 93.5% / [89.5%, 96.3%] | 168 / 92.9% / [88.7%, 95.8%] |
| 2.4% | 148 / 92.6% / [88.0%, 95.8%] | 154 / 92.9% / [88.5%, 95.9%] | 156 / 92.3% / [87.8%, 95.5%] |
| 2.6% | 141 / 92.9% / [88.3%, 96.1%] | 143 / 93.0% / [88.4%, 96.2%] | 149 / 94.0% / [89.7%, 96.8%] |
| 2.8% | 131 / 93.9% / [89.3%, 96.9%] | 131 / 93.9% / [89.3%, 96.9%] | 133 / 93.2% / [88.5%, 96.4%] |
| 3.0% | 111 / 93.7% / [88.5%, 97.0%] | 115 / 93.0% / [87.8%, 96.5%] | 120 / 92.5% / [87.3%, 96.0%] |
| 3.2% | 102 / 96.1% / [91.3%, 98.6%] | 108 / 93.5% / [88.2%, 96.9%] | 108 / 92.6% / [87.0%, 96.3%] |
| 3.4% | 95 / 95.8% / [90.6%, 98.5%] | 100 / 93.0% / [87.3%, 96.7%] | 103 / 93.2% / [87.6%, 96.8%] |

**Every single CI in this table overlaps with every other CI in its row, and almost every CI
overlaps across the whole table.** Close-gap's 3.2%/3.4% point estimates (96.1%/95.8%) are
nominally the highest of the three signals at those thresholds, but both open-gap variants'
CIs at 3.2%/3.4% comfortably contain close-gap's point estimate, and vice versa. There is no
threshold at which open-gap's CI sits meaningfully above or below close-gap's — **the two are
statistically indistinguishable**, exactly what would be expected given that `open` and `close`
are two highly correlated observations of the same underlying index on the same day, and both
gap definitions are measuring materially the same mean-reversion phenomenon.

Bootstrap CIs (not tabled for space) track the exact-binomial CIs closely throughout, as in
every other part of this study — same caveat applies (i.i.d. resampling understates true
uncertainty from time-clustered signals).

## 5. Walk-forward and regime-block validation, open-gap (fair window)

| Threshold, variant | Train (pre-2018) n / hit1% | Test (2018+) n / hit1% | Gap |
|---|---|---|---|
| 2.0%, prevCloseEMA | 107 / 91.6% | 66 / 92.4% | +0.8pp |
| 3.0%, prevCloseEMA | 79 / 92.4% | 36 / 94.4% | +2.0pp |
| 3.2%, prevCloseEMA | 78 / 93.6% | 30 / 93.3% | -0.3pp |
| 2.0%, openEMA | 106 / 91.5% | 69 / 92.8% | +1.3pp |
| 3.0%, openEMA | 85 / 91.8% | 35 / 94.3% | +2.5pp |
| 3.2%, openEMA | 76 / 92.1% | 32 / 93.8% | +1.7pp |

No threshold/variant shows the overfitting red flag (train ≫ test); every combination is flat
to modestly improving out-of-sample, matching close-gap's own already-validated pattern. Regime
blocks (2007-11 / 2012-16 / 2017-21 / 2022-26) show the same structural signature close-gap has
throughout this study: the 2007-11 GFC-era block is consistently the *weakest* block
(86.8-90.2% across variants/thresholds vs. 88.6-100% elsewhere), never a collapse, and no block
anywhere drops meaningfully below 85%. This is a healthy, internally consistent signal on its
own terms — the issue this Part identifies is specifically the earlier apples-to-oranges
comparison against close-gap in the recent-window sweep, not open-gap's validity in isolation.

## Where it fails

Same structural failure mode as every signal in this study: misses cluster in the 2007-11
GFC/2011-correction era (86.8-90.2% hit rate across variants/thresholds, the weakest of the
four regime blocks) rather than being randomly scattered, and the 2026-03-02 episode analyzed
above is a live, current-era example of exactly this pattern (a real correction that a
same-day-only view can make look like a "hit" but that fails to resolve within 2 months under
the honest scoring convention). No threshold or sub-variant tested screens this out reliably.

## Recommendation

**Do not treat open-gap as a materially stronger signal than the already-validated close-gap
(F1) — it is not a bug-free discovery of extra edge, it is the same edge measured on a
different (highly correlated) price point, with a scoring-window inconsistency that happened to
flatter it in small recent samples.** The specific claim that motivated this audit — "100% hit
rate at literally every threshold in the last 3-5 years" — does not survive independent,
apples-to-apples re-implementation and should be retracted; under a fair window it is a normal
83-97% range with real misses, statistically indistinguishable from close-gap's own numbers in
the same windows. That said, this was a productive audit, not a wasted one: open-gap (either
sub-variant) is a legitimately clean, lookahead-free signal in its own right once scored fairly
— full-history CIs are comparably strong to F1's (exact-binomial floors 87-90% depending on
threshold, same ballpark as close-gap), walk-forward and regime-block behavior are stable, and
the EMA/data-integrity checks turned up nothing broken. If open-gap is pursued further as a
genuinely separate signal (e.g. for intraday/at-open execution rather than close-based entry),
it should be developed and reported on its own full validation gauntlet using the SAME
entry-day-exclusive window convention as every other signal in this study, so that any future
comparison to F1 is automatically apples-to-apples and this specific illusion cannot recur.
