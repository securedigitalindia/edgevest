"""
Drishti — NIFTY Entry-Signal Quality Backtest
==============================================
Tests candidate daily-candle entry signals for NIFTY 50 (spot/index level)
against a fixed forward-looking definition of "works":

    An entry fires on day t (entry_price = close[t]). Looking forward at
    daily HIGHs over the next ~42 trading days (t+1 .. t+42), does price
    ever touch entry_price * 1.01 (+1%)? That's the pass/fail bar. +2%/+3%
    are also tracked (how far the move typically stretches), and every
    signal reports the max adverse dip (%) suffered before the target hit
    (or before window expiry, if it never hit) -- a drawdown-before-recovery
    is explicitly allowed and does NOT disqualify a "hit".

This is a signal-quality study, not a P&L study: no position sizing,
costs, or slippage are modeled (see docs/prd -- N/A here, ad hoc study).

Data: SQLite candles_1d via db.queries.get_candles("NIFTY50", "1d", ...).
The table stores each historical trading day TWICE under two different UTC
ts encodings with byte-identical OHLCV (an ingestion artifact, most visible
pre-2026) -- this script dedupes to one row per IST calendar date before
computing anything. See docstring in load_clean_nifty() for details.

No-lookahead discipline:
  - Every indicator (EMA/RSI/ATR/Supertrend/Bollinger/z-score) is a
    backward-looking rolling/recursive function of data up to and
    including day t -- never centered, never using t+1 onward.
  - Two signal families needed an explicit lookahead fix during
    development (see inline comments in make_signal_masks): the ST+RSI
    confluence signal and the price/RSI divergence signal both originally
    defined "day of signal" using information not yet knowable on that
    day. Both are corrected to fire on the first day the pattern is
    actually confirmable.

Usage:
    python analysis/nifty_entry_signal_backtest.py                  # full run, all signals
    python analysis/nifty_entry_signal_backtest.py --signal A1_ST_flip A3_BB_reentry
    python analysis/nifty_entry_signal_backtest.py --export-csv /path/to/dir

This is a read-only analysis tool. It never writes to drishti.db and is
never invoked by the live poller.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import pandas_ta as pta

from db.queries import get_candles

IST = "Asia/Kolkata"
FORWARD_WINDOW = 42          # trading days (~2 months)
TARGETS = (0.01, 0.02, 0.03)  # +1% / +2% / +3%

# D-family (2026-07-28 session): EMA9/21 cross + RSI-recovery signal is explicitly scoped
# by the user to the LAST ~2 YEARS ONLY (not the 19-20y history used by A1/A3/C-family) --
# see detect_ema_rsi_recovery()'s docstring. This start date is a stated user instruction
# ("roughly 2024-07-28 through 2026-07-27"), not derived from the data.
D1_WINDOW_START = pd.Timestamp("2024-07-28").date()

# F-family (2026-07-28 session): EMA20-gap mean-reversion, the first TWO-SIDED (long+short)
# signal family in this study -- every other signal (A-E) is long-only. See
# detect_ema20gap_signals()'s docstring for the exact threshold-crossing definition.
EMA20GAP_THRESHOLD = 3.0


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_clean_nifty(limit: int = 20000) -> pd.DataFrame:
    """
    Pull all available NIFTY50 1d candles and dedupe.

    Data-quality finding: candles_1d stores almost every pre-2026 trading
    day twice, once at ts = <prev-UTC-day> 18:30 and once at ts =
    <same-UTC-day> 00:00 -- both map to the same IST calendar date, and
    every field (O/H/L/C/V) is byte-identical between the pair (verified:
    9174 of 9212 rows pre-dedupe belong to a same-date pair, and zero of
    those pairs disagree on OHLCV). This looks like a historical
    double-bootstrap artifact, not real duplicate market data. The last
    ~38 trading days only have a single row (bootstrap/sync since fixed
    the double-write). We dedupe by keeping one row per IST calendar date.
    """
    df = get_candles("NIFTY50", "1d", limit=limit)
    if df.empty:
        raise RuntimeError("No NIFTY50 1d candles found in drishti.db")

    df["ts_ist"] = df["ts"].dt.tz_convert(IST)
    df["date"] = df["ts_ist"].dt.date
    df = df.sort_values("ts").drop_duplicates(subset=["date"], keep="first")
    df = df.sort_values("date").reset_index(drop=True)

    # Sanity checks
    bad_high = df[df["high"] < df[["open", "close", "low"]].max(axis=1)]
    bad_low = df[df["low"] > df[["open", "close", "high"]].min(axis=1)]
    if len(bad_high) or len(bad_low):
        raise RuntimeError(
            f"OHLC integrity violation: {len(bad_high)} bad-high rows, "
            f"{len(bad_low)} bad-low rows"
        )
    if df["date"].duplicated().any():
        raise RuntimeError("Duplicate trading dates survived dedupe")

    return df[["date", "open", "high", "low", "close", "volume"]].copy()


# ---------------------------------------------------------------------------
# Indicators (all backward-looking / recursive -- no centered windows here)
# ---------------------------------------------------------------------------

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c, h, l = df["close"], df["high"], df["low"]

    df["ema20"] = pta.ema(c, length=20)
    df["ema21"] = pta.ema(c, length=21)
    df["ema50"] = pta.ema(c, length=50)
    df["ema200"] = pta.ema(c, length=200)
    df["rsi14"] = pta.rsi(c, length=14)
    df["atr14"] = pta.atr(h, l, c, length=14)

    bb = pta.bbands(c, length=20, lower_std=2.0, upper_std=2.0)
    df["bb_low"] = bb[next(x for x in bb.columns if x.startswith("BBL"))]
    df["bb_mid"] = bb[next(x for x in bb.columns if x.startswith("BBM"))]
    df["bb_up"] = bb[next(x for x in bb.columns if x.startswith("BBU"))]
    df["bb_bw"] = bb[next(x for x in bb.columns if x.startswith("BBB"))]

    st = pta.supertrend(h, l, c, length=10, multiplier=3.0)
    df["st_val"] = st[next(x for x in st.columns
                           if x.startswith("SUPERT_10") and not x.startswith("SUPERTd"))]
    df["st_dir"] = st[next(x for x in st.columns if x.startswith("SUPERTd_10"))]

    # E-family (2026-07-28 session): Supertrend(10, 2.6) -- deliberately a DIFFERENT
    # multiplier from the 3.0 used by A1/B1 above, per explicit user spec. Computed as its
    # own separate column pair (st26_val/st26_dir) rather than overwriting st_val/st_dir so
    # A1/B1/A6 (all built on the 10,3 flip) are completely unaffected.
    st26 = pta.supertrend(h, l, c, length=10, multiplier=2.6)
    df["st26_val"] = st26[next(x for x in st26.columns
                               if x.startswith("SUPERT_10") and not x.startswith("SUPERTd"))]
    df["st26_dir"] = st26[next(x for x in st26.columns if x.startswith("SUPERTd_10"))]

    macd = pta.macd(c, fast=12, slow=26, signal=9)
    df["macd"] = macd[next(x for x in macd.columns if x.startswith("MACD_12"))]
    df["macd_signal"] = macd[next(x for x in macd.columns if x.startswith("MACDs_12"))]
    df["macd_hist"] = macd[next(x for x in macd.columns if x.startswith("MACDh_12"))]

    # EMA200 20-day slope (% change) -- regime filter candidate
    df["ema200_slope20"] = (df["ema200"] - df["ema200"].shift(20)) / df["ema200"].shift(20) * 100

    # z-score of close vs EMA50/EMA200 using trailing rolling std of close
    df["z_ema50"] = (c - df["ema50"]) / c.rolling(50).std()
    df["z_ema200"] = (c - df["ema200"]) / c.rolling(200).std()

    # consecutive down-day streak (0 on an up day)
    down = (c < c.shift(1)).astype(int)
    grp = (down != down.shift(1)).cumsum()
    df["consec_down"] = down.groupby(grp).cumsum() * down

    # Bollinger-bandwidth trailing 252d percentile rank (own history only, no lookahead)
    df["bb_bw_pct252"] = _rolling_pct_rank(df["bb_bw"], 252)

    # candlestick patterns (same-day + prior-day OHLC only)
    body = (df["close"] - df["open"]).abs()
    rng = df["high"] - df["low"]
    upper_wick = df["high"] - df[["close", "open"]].max(axis=1)
    lower_wick = df[["close", "open"]].min(axis=1) - df["low"]
    prev_open, prev_close = df["open"].shift(1), df["close"].shift(1)
    prev_bearish = prev_close < prev_open
    today_bullish = df["close"] > df["open"]
    df["bullish_engulfing"] = (
        today_bullish & prev_bearish & (df["close"] >= prev_open) & (df["open"] <= prev_close)
    )
    df["hammer"] = (
        (lower_wick >= 2 * body) & (upper_wick <= 0.3 * body.clip(lower=1e-9)) & (rng > 0)
    )

    return df


def _rolling_pct_rank(s: pd.Series, window: int) -> np.ndarray:
    """Trailing (backward-only) percentile rank of the latest value within its own
    past `window` days -- used for the Bollinger-bandwidth squeeze percentile."""
    arr = s.values
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        win = arr[i - window + 1:i + 1]
        if np.isnan(win).any():
            continue
        out[i] = (win < win[-1]).sum() / (window - 1) * 100
    return out


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------

def make_signal_masks(df: pd.DataFrame) -> dict:
    """Return {signal_name: boolean pd.Series aligned to df.index}, one entry
    per candidate entry-signal family. Names prefixed A_ reproduce the prior
    ad hoc study's 6 signal types (re-derived against the strict %-floor / 42d
    definition here, not the old flat-point/63d one). Names prefixed B_ are
    the new/inventive candidates requested: regime filters, vol squeeze,
    momentum exhaustion + reversal candle, price/RSI divergence, and
    z-score-based adaptive thresholds, plus 2-way confluences of these
    (kept only where n stays statistically usable)."""
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    masks = {}

    st_dir = df["st_dir"]
    st_flip_bull = (st_dir == 1) & (st_dir.shift(1) == -1)
    regime_ok = df["ema200_slope20"] >= 0  # EMA200 flat-or-rising over the last 20 trading days

    rsi_cross_below25 = (df["rsi14"] < 25) & (df["rsi14"].shift(1) >= 25)

    # A1 -- Supertrend(10,3) bear->bull flip, no filter (prior study's best-sample signal)
    masks["A1_ST_flip"] = st_flip_bull.fillna(False)

    # B1 -- A1 + EMA200 regime filter (only take the flip if the 200d trend isn't rolling over)
    masks["B1_ST_flip_regime"] = (st_flip_bull & regime_ok).fillna(False)

    # A2 -- RSI(14) crosses below 25 (extreme oversold entry trigger)
    masks["A2_RSI25"] = rsi_cross_below25.fillna(False)

    # B2 -- A2 + regime filter
    masks["B2_RSI25_regime"] = (rsi_cross_below25 & regime_ok).fillna(False)

    # A3 -- Bollinger(20,2) lower-band re-entry (close drops below lower band, then re-enters)
    below_lower = c < df["bb_low"]
    reentry = (~below_lower) & (below_lower.shift(1))
    masks["A3_BB_reentry"] = reentry.fillna(False)

    # A4 -- EMA50 pullback in an uptrend (price near EMA50, RSI<45, close>EMA200)
    near_ema50 = (c <= df["ema50"] * 1.005) & (c >= df["ema50"] * 0.98)
    masks["A4_EMA50_pullback"] = (near_ema50 & (df["rsi14"] < 45) & (c > df["ema200"])).fillna(False)

    # A5 -- MACD bull cross + RSI<40
    macd_cross_up = (df["macd"] > df["macd_signal"]) & (df["macd"].shift(1) <= df["macd_signal"].shift(1))
    masks["A5_MACD_RSI40"] = (macd_cross_up & (df["rsi14"] < 40)).fillna(False)

    # A6 -- Confluence: ST flip + RSI recross above 30 within +-3 days.
    # LOOKAHEAD FIX: if the RSI recross happens AFTER the flip day, the confluence
    # isn't knowable until that later day. Signal fires (and entry_price is taken)
    # on max(flip_day, recross_day), never on the flip day alone if recross is
    # still in the future relative to it.
    st_flip_idx = np.where(st_flip_bull.fillna(False).values)[0]
    rsi_recross30 = ((df["rsi14"] > 30) & (df["rsi14"].shift(1) <= 30)).fillna(False)
    rsi_recross_idx = set(np.where(rsi_recross30.values)[0].tolist())
    confluence_mask = np.zeros(len(df), dtype=bool)
    for i in st_flip_idx:
        best_j = None
        for j in range(max(0, i - 3), min(len(df), i + 4)):
            if j in rsi_recross_idx:
                best_j = j
                break
        if best_j is not None:
            confluence_mask[max(i, best_j)] = True
    masks["A6_ST_RSI_confluence"] = pd.Series(confluence_mask, index=df.index)

    # B3 -- Bollinger-bandwidth squeeze (percentile <20 over trailing 252d within the last
    # 5 days) followed by close crossing back above the 20d basis -- vol contraction -> expansion
    squeeze = df["bb_bw_pct252"] < 20
    cross_up_mid = (c > df["bb_mid"]) & (c.shift(1) <= df["bb_mid"].shift(1))
    squeeze_set = set(np.where(squeeze.fillna(False).values)[0].tolist())
    b3_mask = np.zeros(len(df), dtype=bool)
    for j in np.where(cross_up_mid.fillna(False).values)[0]:
        if any((j - k) in squeeze_set for k in range(0, 6)):
            b3_mask[j] = True
    masks["B3_BBsqueeze_breakout"] = pd.Series(b3_mask, index=df.index)

    # B4 -- Momentum exhaustion: >=4 consecutive down days, then a reversal candle
    # (bullish engulfing or hammer) as the actual trigger day
    consec_down_prior = df["consec_down"].shift(1)
    reversal_candle = df["bullish_engulfing"] | df["hammer"]
    masks["B4_4down_reversal"] = ((consec_down_prior >= 4) & reversal_candle).fillna(False)

    # B5 -- Price/RSI bullish divergence: price makes a lower low vs the prior swing low,
    # RSI makes a higher low. Swing lows defined via a +-5-day centered window.
    # LOOKAHEAD FIX: a centered-window "local min" at day i isn't confirmable until day
    # i+5 (once the next 5 days of closes are known). The signal fires on day i+5 (first
    # day the pattern becomes knowable) using that day's own close as entry_price -- not
    # on the low day itself.
    W = 5
    is_local_min = (c == c.rolling(2 * W + 1, center=True).min())
    local_min_idx = np.where(is_local_min.fillna(False).values)[0]
    confirmed = sorted((i + W, i) for i in local_min_idx if i + W < len(df))
    close_v, rsi_v = c.values, df["rsi14"].values
    b5_mask = np.zeros(len(df), dtype=bool)
    for k in range(1, len(confirmed)):
        confirm_prev, i_prev = confirmed[k - 1]
        confirm_cur, i_cur = confirmed[k]
        if not (3 <= i_cur - i_prev <= 60) or confirm_prev > i_cur:
            continue
        if close_v[i_cur] < close_v[i_prev] and rsi_v[i_cur] > rsi_v[i_prev]:
            b5_mask[confirm_cur] = True
    masks["B5_price_rsi_divergence"] = pd.Series(b5_mask, index=df.index)

    # B6 -- Z-score of price vs EMA50 crosses below -2 (adaptive oversold threshold,
    # scales with NIFTY's volatility regime instead of a fixed RSI/BB cutoff)
    z = df["z_ema50"]
    b6_mask = (z <= -2) & (z.shift(1) > -2)
    masks["B6_zscore_ema50"] = b6_mask.fillna(False)

    # B7/B8/B9 -- regime-filtered variants of B6/B4/B5
    masks["B7_zscore_regime"] = (b6_mask & regime_ok).fillna(False)
    masks["B8_4down_reversal_regime"] = ((consec_down_prior >= 4) & reversal_candle & regime_ok).fillna(False)
    masks["B9_divergence_regime"] = (masks["B5_price_rsi_divergence"] & regime_ok).fillna(False)

    return masks


def detect_st26_ema_rsi_buckets(df: pd.DataFrame, st_dir_col: str = "st26_dir",
                                 st_val_col: str = "st26_val") -> tuple:
    """
    E-family (2026-07-28 session): Supertrend(10, 2.6) bear->bull flip, fully specified by
    the user -- implemented literally, no reinterpretation.

    At the exact flip candle (single-bar snapshot, no multi-day confirmation window --
    trivially lookahead-safe since every value used is that same bar's own close/EMA/RSI,
    never a future bar), two booleans are recorded using the flip day's OWN close/RSI:
      - close ABOVE EMA(20)      (strict >)   vs. close BELOW-OR-AT EMA(20) (<=)
      - RSI(14) ABOVE 50         (strict >)   vs. RSI(14) BELOW-OR-AT 50   (<=)
    Tie-breaking at exact equality: the user's own phrasing ("above ... or below/at it")
    already resolves this -- equality is grouped into the "below/at" bucket for both EMA20
    and RSI50, so no separate assumption is needed here.

    Returns (base_mask, bucket_masks: dict[str->np.ndarray], meta: dict[int->dict]) where
    bucket_masks has keys "E1_above_above" (close>EMA20 & RSI>50, the user's headline/primary
    combo), "E2_above_below" (close>EMA20 & RSI<=50), "E3_below_above" (close<=EMA20 &
    RSI>50), "E4_below_below" (close<=EMA20 & RSI<=50). base_mask is the unfiltered ST flip
    on its own (E0 reference row).
    """
    n = len(df)
    st_dir = df[st_dir_col]
    flip = ((st_dir == 1) & (st_dir.shift(1) == -1)).fillna(False)
    flip_idx = np.where(flip.values)[0]

    c_v, ema20_v, rsi_v, st_v = (df["close"].values, df["ema20"].values,
                                 df["rsi14"].values, df[st_val_col].values)

    above_ema = np.zeros(n, dtype=bool)
    above_rsi = np.zeros(n, dtype=bool)
    above_ema[flip_idx] = c_v[flip_idx] > ema20_v[flip_idx]
    above_rsi[flip_idx] = rsi_v[flip_idx] > 50.0

    bucket_masks = {
        "E1_ST26_flip_aboveEMA20_RSIabove50": flip.values & above_ema & above_rsi,
        "E2_ST26_flip_aboveEMA20_RSIbelow50": flip.values & above_ema & ~above_rsi,
        "E3_ST26_flip_belowEMA20_RSIabove50": flip.values & ~above_ema & above_rsi,
        "E4_ST26_flip_belowEMA20_RSIbelow50": flip.values & ~above_ema & ~above_rsi,
    }
    bucket_masks = {k: pd.Series(v, index=df.index) for k, v in bucket_masks.items()}

    meta = {}
    for i in flip_idx:
        meta[i] = {
            "st_val": float(st_v[i]), "ema20_val": float(ema20_v[i]),
            "rsi_val": float(rsi_v[i]), "close": float(c_v[i]),
            "above_ema20": bool(above_ema[i]), "above_rsi50": bool(above_rsi[i]),
        }
    return pd.Series(flip.values, index=df.index), bucket_masks, meta


def st26_bucket_reason_string(m: dict) -> str:
    ema_side = "ABOVE" if m["above_ema20"] else "below/at"
    rsi_side = "ABOVE" if m["above_rsi50"] else "below/at"
    return (
        f"Supertrend(10,2.6) flips bear->bull, ST={m['st_val']:.1f}; "
        f"close {m['close']:.1f} {ema_side} EMA20={m['ema20_val']:.1f}; "
        f"RSI(14)={m['rsi_val']:.1f} {rsi_side} 50"
    )


def st26_param_sweep(df0: pd.DataFrame, n_total: int) -> list:
    """Perturb Supertrend(10, 2.6)'s period (+-20%) and multiplier (+-~15-20%) and
    re-score the E1 headline combo (flip + close>EMA20 + RSI>50) -- is E1 sitting on a
    plateau or a cliff edge?"""
    out = []
    for period in (8, 10, 12):
        for mult in (2.1, 2.35, 2.6, 2.85, 3.1):
            st = pta.supertrend(df0["high"], df0["low"], df0["close"], length=period, multiplier=mult)
            d = st[next(x for x in st.columns if x.startswith("SUPERTd"))]
            flip = ((d == 1) & (d.shift(1) == -1)).fillna(False)
            c_v, ema20_v, rsi_v = df0["close"].values, df0["ema20"].values, df0["rsi14"].values
            above_ema = c_v > ema20_v
            above_rsi = rsi_v > 50.0
            e1_mask = flip.values & above_ema & above_rsi
            idxs = [i for i in np.where(e1_mask)[0] if i + FORWARD_WINDOW <= n_total - 1]
            rows = compute_forward_outcomes(df0, idxs, f"E1_ST_{period}_{mult}")
            h1 = sum(r["hit_1pct"] for r in rows) / len(rows) * 100 if rows else None
            out.append((period, mult, len(rows), h1))
    return out


def detect_ema20gap_signals(df: pd.DataFrame, threshold: float = EMA20GAP_THRESHOLD) -> tuple:
    """
    F-family (2026-07-28 session): two-sided mean-reversion signal, the first LONG-AND-SHORT
    family in this study (A-E are all long-only).

    gap_pct = (close - EMA20) / EMA20 * 100 -- how far today's close sits above/below its
    own EMA(20), as a percentage. Both indicators (close, EMA20) are known at day t's own
    close; trivially lookahead-safe, same as every other backward-looking indicator here.

    LONG fires the first day gap_pct crosses BELOW -threshold (gap_pct[t] < -threshold and
    gap_pct[t-1] >= -threshold) -- close has fallen more than `threshold`% under its EMA20.
    Bet: mean-reversion UP. entry_price = that day's own close.

    SHORT fires the first day gap_pct crosses ABOVE +threshold (gap_pct[t] > threshold and
    gap_pct[t-1] <= threshold) -- close has risen more than `threshold`% over its EMA20.
    Bet: mean-reversion DOWN. entry_price = that day's own close.

    This is a threshold-CROSSING signal (fires once on first breach), identical convention
    to A2 (RSI crosses below 25) elsewhere in this script -- it does NOT re-fire every day
    the gap stays beyond the threshold.

    Edge case (conservative assumption, stated per the brief rather than stalled on): if
    gap_pct jumps from inside the band straight past the opposite side in one candle (e.g.
    -2% one day to +3.5% the next), the crossing tests above still correctly catch it as a
    fresh SHORT breach (gap_pct[t-1]=-2 <= +threshold, gap_pct[t]=+3.5 > +threshold) -- no
    special-casing needed, the >=/<= boundary conditions already handle it. A long and a
    short cannot both fire on the same day (gap_pct is a single scalar -- it cannot be both
    below -3% and above +3% simultaneously), so no tie-breaking rule is needed there either.

    Returns (long_mask, short_mask, meta: dict[idx -> dict]) where meta holds close/EMA20/
    gap_pct for every day either mask fires on.
    """
    gap_pct = (df["close"] - df["ema20"]) / df["ema20"] * 100
    long_mask = ((gap_pct < -threshold) & (gap_pct.shift(1) >= -threshold)).fillna(False)
    short_mask = ((gap_pct > threshold) & (gap_pct.shift(1) <= threshold)).fillna(False)

    meta = {}
    c_v, ema20_v, gap_v = df["close"].values, df["ema20"].values, gap_pct.values
    for i in np.where((long_mask | short_mask).values)[0]:
        meta[i] = {"close": float(c_v[i]), "ema20": float(ema20_v[i]), "gap_pct": float(gap_v[i]),
                   "threshold": threshold}
    return long_mask, short_mask, meta


def ema20gap_reason_string(direction: str, m: dict) -> str:
    th = m["threshold"]
    return (
        f"gap_pct=(close-EMA20)/EMA20={m['gap_pct']:.2f}% crosses "
        f"{'below -' if direction == 'long' else 'above +'}{th:.1f}% "
        f"(close={m['close']:.1f}, EMA20={m['ema20']:.1f})"
    )


def compute_forward_outcomes_directional(df: pd.DataFrame, sig_idxs, name: str, direction: str,
                                         window: int = FORWARD_WINDOW, targets=TARGETS,
                                         reason_overrides: dict = None) -> list:
    """
    Two-sided generalization of compute_forward_outcomes() above, needed for the F-family
    long+short EMA20-gap signal (every prior signal A-E is long-only and uses the original
    function unchanged).

    direction="long": entry_price=close[i]; target_px=entry*(1+t); a HIT requires the window
    HIGH to reach target_px; max_adverse_dip_pct = worst DOWN move (entry vs. window LOW)
    observed before the hit (or before window expiry if it never hits). Identical semantics
    to compute_forward_outcomes().

    direction="short": entry_price=close[i]; target_px=entry*(1-t); a HIT requires the window
    LOW to reach target_px; max_adverse_dip_pct here means the worst UP move (entry vs.
    window HIGH) observed before the hit (or before window expiry) -- deliberately INVERTED
    from the long convention, since "adverse" for a short position means price rising against
    it, not falling. Getting this inversion right (rather than reusing the long-only low/high
    roles as-is) is the whole point of this separate function.

    Forward window = i+1 .. i+window (never day i's own high/low) -- same no-lookahead
    discipline as compute_forward_outcomes().
    """
    n = len(df)
    close, high, low, dates = df["close"].values, df["high"].values, df["low"].values, df["date"].values
    out = []
    sign = 1 if direction == "long" else -1

    for i in sig_idxs:
        entry_price = close[i]
        end = min(i + window, n - 1)
        fwd_avail = end - i
        if fwd_avail <= 0:
            continue
        truncated = fwd_avail < window

        w_high, w_low = high[i + 1:end + 1], low[i + 1:end + 1]
        targets_px = [entry_price * (1 + sign * t) for t in targets]

        hit_day = {}
        for tpx, t in zip(targets_px, targets):
            hit_day[t] = None
            for d in range(len(w_high)):
                touched = (w_high[d] >= tpx) if direction == "long" else (w_low[d] <= tpx)
                if touched:
                    hit_day[t] = d + 1
                    break

        day_of_1pct = hit_day[targets[0]]
        if direction == "long":
            adverse_extreme = w_low[:day_of_1pct].min() if day_of_1pct else (w_low.min() if len(w_low) else entry_price)
            max_adverse_dip_pct = max(0.0, (entry_price - adverse_extreme) / entry_price * 100)
            best_fwd_move_pct = (w_high.max() / entry_price - 1) * 100 if len(w_high) else 0.0
        else:
            adverse_extreme = w_high[:day_of_1pct].max() if day_of_1pct else (w_high.max() if len(w_high) else entry_price)
            max_adverse_dip_pct = max(0.0, (adverse_extreme - entry_price) / entry_price * 100)
            best_fwd_move_pct = (1 - w_low.min() / entry_price) * 100 if len(w_low) else 0.0

        reason = reason_overrides[i] if reason_overrides and i in reason_overrides else name
        out.append({
            "signal": name, "direction": direction, "date": dates[i],
            "entry_price": round(float(entry_price), 2), "reason": reason,
            "hit_1pct": hit_day[targets[0]] is not None, "days_to_1pct": hit_day[targets[0]],
            "hit_2pct": hit_day[targets[1]] is not None, "days_to_2pct": hit_day[targets[1]],
            "hit_3pct": hit_day[targets[2]] is not None, "days_to_3pct": hit_day[targets[2]],
            "max_adverse_dip_pct": round(float(max_adverse_dip_pct), 2),
            "best_fwd_gain_pct": round(float(best_fwd_move_pct), 2),
            "window_truncated": truncated, "fwd_days_available": int(fwd_avail), "idx": int(i),
        })
    return out


def ema20gap_param_sweep(df: pd.DataFrame, n_total: int,
                        thresholds=(2.0, 2.5, 3.0, 3.5, 4.0)) -> list:
    """Sweep the 3% breach threshold at +-33% (2%/2.5%/3%/3.5%/4%) for both LONG and SHORT --
    is F1/F2 sitting on a robustness plateau or a curve-fit cliff at exactly 3%?"""
    out = []
    for th in thresholds:
        long_mask, short_mask, meta = detect_ema20gap_signals(df, threshold=th)
        long_idxs = [i for i in np.where(long_mask.values)[0] if i + FORWARD_WINDOW <= n_total - 1]
        short_idxs = [i for i in np.where(short_mask.values)[0] if i + FORWARD_WINDOW <= n_total - 1]
        long_rows = compute_forward_outcomes_directional(df, long_idxs, "x", "long")
        short_rows = compute_forward_outcomes_directional(df, short_idxs, "x", "short")
        h1_long = sum(r["hit_1pct"] for r in long_rows) / len(long_rows) * 100 if long_rows else None
        h1_short = sum(r["hit_1pct"] for r in short_rows) / len(short_rows) * 100 if short_rows else None
        out.append((th, len(long_rows), h1_long, len(short_rows), h1_short))
    return out


def detect_ema_rsi_recovery(df: pd.DataFrame, ema_fast: int = 9, ema_slow: int = 21,
                            rsi_threshold: float = 40.0, max_gap: int = 5,
                            window_start=None) -> tuple:
    """
    D-family: EMA(ema_fast)/EMA(ema_slow) bullish cross + RSI(14) "recovering from below
    rsi_threshold" as momentum confirmation. Requested this session, explicitly WITHOUT any
    EMA200/regime gate (user directive -- do not add one even if it would look like it
    "improves" the number).

    Definition:
      - EMA cross day i: ema_fast[i] > ema_slow[i] and ema_fast[i-1] <= ema_slow[i-1]
        (both EMAs computed the standard recursive/backward-looking way -- no lookahead).
      - RSI recovery day j: rsi14[j] > rsi_threshold and rsi14[j-1] <= rsi_threshold, i.e.
        RSI(14) recrosses back ABOVE rsi_threshold having been AT OR BELOW it the previous
        day. This is the most conservative, most lookahead-safe reading of the brief's
        "RSI recovering from below 40" (a literal recross), not a fuzzier "any uptick while
        still under 40" test -- and it matches the confluence style already used elsewhere
        in this script for A6 (Supertrend flip + RSI recross above 30 within +-3 days).
      - Confluence: day j must fall within +-max_gap trading days of day i ("within a few
        days of the EMA cross" per the brief -- max_gap=5 is the stated conservative
        assumption; swept at 3/5/7 as a robustness check in the report, though the brief
        only mandated sweeping the EMA pair and RSI threshold).
      - LOOKAHEAD-SAFE FIRE DAY (identical discipline to A6's fix elsewhere in this file):
        if the RSI recovery happens ON OR BEFORE the EMA cross day, the confluence is fully
        knowable at the EMA cross day itself -- fires there. If the RSI recovery happens
        STRICTLY AFTER the EMA cross day, the confluence isn't confirmable until that later
        day, so the signal fires on max(i, j) using THAT day's own close as entry_price,
        never on the EMA-cross day's close if RSI hadn't recovered yet as of that day.

    `window_start` (a date, optional): if given, only signals whose FIRE DAY's date is
    `>= window_start` are returned. Indicators themselves are always computed over the
    full history passed in `df` (so EMA9/21/RSI14 are never cold-started at the window
    boundary) -- only which already-detected signals get reported/scored is restricted.
    This is how the user's "last 2 years only" data-window instruction is implemented
    without corrupting indicator warm-up.

    Returns (mask: np.ndarray[bool], meta: dict[int -> dict]) where meta holds the exact
    EMA9/EMA21 values, RSI value, RSI recent low (the lowest RSI14 print in the window
    spanning the EMA-cross/RSI-recovery pair, i.e. how deep the "below 40" dip actually
    was), and the gap in trading days between the two triggers -- everything the report's
    per-signal table needs.
    """
    n = len(df)
    ema_f = pta.ema(df["close"], length=ema_fast)
    ema_s = pta.ema(df["close"], length=ema_slow)
    rsi = df["rsi14"]
    dates_v = df["date"].values

    ema_cross = (ema_f > ema_s) & (ema_f.shift(1) <= ema_s.shift(1))
    rsi_recovery = (rsi > rsi_threshold) & (rsi.shift(1) <= rsi_threshold)
    ema_cross_idx = np.where(ema_cross.fillna(False).values)[0]
    rsi_recovery_set = set(np.where(rsi_recovery.fillna(False).values)[0].tolist())

    mask = np.zeros(n, dtype=bool)
    meta = {}
    for i in ema_cross_idx:
        best_j = None
        for j in range(max(0, i - max_gap), min(n, i + max_gap + 1)):
            if j in rsi_recovery_set:
                best_j = j
                break
        if best_j is None:
            continue
        fire_idx = max(i, best_j)
        if window_start is not None and dates_v[fire_idx] < window_start:
            continue
        lo = max(0, min(i, best_j) - max_gap)
        rsi_recent_low = float(np.nanmin(rsi.values[lo:fire_idx + 1]))
        mask[fire_idx] = True
        meta[fire_idx] = {
            "ema_cross_idx": int(i), "rsi_recovery_idx": int(best_j),
            "ema_cross_date": dates_v[i], "rsi_recovery_date": dates_v[best_j],
            "ema_fast_val": float(ema_f.values[fire_idx]), "ema_slow_val": float(ema_s.values[fire_idx]),
            "rsi_val": float(rsi.values[fire_idx]), "rsi_recent_low": rsi_recent_low,
            "gap_days": int(best_j - i), "ema_fast": ema_fast, "ema_slow": ema_slow,
            "rsi_threshold": rsi_threshold, "max_gap": max_gap,
        }
    return mask, meta


def ema_rsi_recovery_reason_string(row_close: float, m: dict) -> str:
    return (
        f"EMA({m['ema_fast']})={m['ema_fast_val']:.1f} crosses above "
        f"EMA({m['ema_slow']})={m['ema_slow_val']:.1f} on {m['ema_cross_date']}; "
        f"RSI(14) recovers above {m['rsi_threshold']:.0f} on {m['rsi_recovery_date']} "
        f"(recent low {m['rsi_recent_low']:.1f}, now {m['rsi_val']:.1f}), gap {m['gap_days']}d; "
        f"entry close {row_close:.1f}"
    )


def ema_rsi_recovery_param_sweep(df: pd.DataFrame, n_total: int, window_start=None) -> list:
    """Sweep EMA(fast,slow) pairs and RSI-recovery thresholds (max_gap fixed at 5), each
    scored BOTH on the user-mandated 2-year window and on the full history (for context --
    the full-history number is never the headline, only a robustness/sanity cross-check)."""
    out = []
    for ema_fast, ema_slow in ((9, 21), (8, 20), (10, 25)):
        for rsi_threshold in (35.0, 40.0, 45.0):
            mask, meta = detect_ema_rsi_recovery(df, ema_fast=ema_fast, ema_slow=ema_slow,
                                                  rsi_threshold=rsi_threshold, max_gap=5)
            idxs_all = [i for i in np.where(mask)[0] if i + FORWARD_WINDOW <= n_total - 1]
            idxs_win = [i for i in idxs_all if window_start is None or df["date"].values[i] >= window_start]
            rows_full = compute_forward_outcomes(
                df, idxs_all, "x", reason_overrides={i: ema_rsi_recovery_reason_string(df["close"].values[i], meta[i]) for i in idxs_all})
            rows_win = compute_forward_outcomes(
                df, idxs_win, "x", reason_overrides={i: ema_rsi_recovery_reason_string(df["close"].values[i], meta[i]) for i in idxs_win})
            h1_full = sum(r["hit_1pct"] for r in rows_full) / len(rows_full) * 100 if rows_full else None
            h1_win = sum(r["hit_1pct"] for r in rows_win) / len(rows_win) * 100 if rows_win else None
            out.append((ema_fast, ema_slow, rsi_threshold, len(rows_win), h1_win, len(rows_full), h1_full))
    return out


def ema_rsi_recovery_gap_sweep(df: pd.DataFrame, n_total: int, window_start=None) -> list:
    """Bonus robustness check (not mandated by the brief, cheap to add): sensitivity of the
    +-max_gap 'within a few days' parameter itself, holding EMA(9,21)/RSI<40 fixed."""
    out = []
    for max_gap in (3, 5, 7):
        mask, meta = detect_ema_rsi_recovery(df, ema_fast=9, ema_slow=21, rsi_threshold=40.0, max_gap=max_gap)
        idxs_all = [i for i in np.where(mask)[0] if i + FORWARD_WINDOW <= n_total - 1]
        idxs_win = [i for i in idxs_all if window_start is None or df["date"].values[i] >= window_start]
        rows_full = compute_forward_outcomes(df, idxs_all, "x")
        rows_win = compute_forward_outcomes(df, idxs_win, "x")
        h1_full = sum(r["hit_1pct"] for r in rows_full) / len(rows_full) * 100 if rows_full else None
        h1_win = sum(r["hit_1pct"] for r in rows_win) / len(rows_win) * 100 if rows_win else None
        out.append((max_gap, len(rows_win), h1_win, len(rows_full), h1_full))
    return out


def reason_string(df: pd.DataFrame, i: int, name: str) -> str:
    row = df.iloc[i]
    parts = []
    if "ST_flip" in name:
        parts.append(f"Supertrend(10,3) flips bear->bull, ST={row['st_val']:.1f}")
    if "RSI25" in name:
        parts.append(f"RSI(14)={row['rsi14']:.1f} crosses below 25")
    if "BB_reentry" in name:
        parts.append(f"close {row['close']:.1f} re-enters above BB(20,2) lower band {row['bb_low']:.1f}")
    if "EMA50_pullback" in name:
        parts.append(
            f"close {row['close']:.1f} near EMA50 {row['ema50']:.1f}, RSI={row['rsi14']:.1f}<45, "
            f"uptrend (close>EMA200 {row['ema200']:.1f})"
        )
    if "MACD_RSI40" in name:
        parts.append(f"MACD {row['macd']:.1f} crosses above signal {row['macd_signal']:.1f}, RSI={row['rsi14']:.1f}<40")
    if "confluence" in name:
        parts.append(f"ST flip + RSI(14)={row['rsi14']:.1f} recrossed above 30 within +-3d")
    if "BBsqueeze" in name:
        parts.append(
            f"BB bandwidth pctile={row['bb_bw_pct252']:.0f} (squeeze<20 within last 5d), "
            f"close {row['close']:.1f} crosses above BB basis {row['bb_mid']:.1f}"
        )
    if "4down_reversal" in name:
        cand = "bullish engulfing" if row["bullish_engulfing"] else "hammer"
        parts.append(f">=4 consecutive down days then {cand} on trigger day (close {row['close']:.1f})")
    if "divergence" in name:
        parts.append(
            f"price/RSI bullish divergence confirmed 5d after swing low (no-lookahead lag); "
            f"entry close {row['close']:.1f}, RSI={row['rsi14']:.1f}"
        )
    if "zscore_ema50" in name:
        parts.append(f"z-score(close vs EMA50)={row['z_ema50']:.2f} crosses below -2 (EMA50={row['ema50']:.1f})")
    if "regime" in name:
        parts.append(f"EMA200 20d-slope={row['ema200_slope20']:.2f}%>=0 (flat/rising regime)")
    return "; ".join(parts) if parts else name


# ---------------------------------------------------------------------------
# Forward-outcome evaluation
# ---------------------------------------------------------------------------

def compute_forward_outcomes(df: pd.DataFrame, sig_idxs, name: str,
                             window: int = FORWARD_WINDOW, targets=TARGETS,
                             reason_overrides: dict = None) -> list:
    """
    entry_price = close[i] (the signal day's own close -- the value that
    confirms the setup; see report for the next-open-execution caveat).
    Forward window = i+1 .. i+window (never includes day i's own high/low,
    avoiding same-bar lookahead).
    """
    n = len(df)
    close, high, low, dates = df["close"].values, df["high"].values, df["low"].values, df["date"].values
    out = []

    for i in sig_idxs:
        entry_price = close[i]
        end = min(i + window, n - 1)
        fwd_avail = end - i
        if fwd_avail <= 0:
            continue
        truncated = fwd_avail < window

        w_high, w_low = high[i + 1:end + 1], low[i + 1:end + 1]
        targets_px = [entry_price * (1 + t) for t in targets]

        day_of_1pct = None
        for d in range(len(w_high)):
            if w_high[d] >= targets_px[0]:
                day_of_1pct = d + 1
                break
        adverse_low = w_low[:day_of_1pct].min() if day_of_1pct else (w_low.min() if len(w_low) else entry_price)
        max_adverse_dip_pct = max(0.0, (entry_price - adverse_low) / entry_price * 100)

        hit_day = {}
        for tpx, t in zip(targets_px, targets):
            hit_day[t] = None
            for d in range(len(w_high)):
                if w_high[d] >= tpx:
                    hit_day[t] = d + 1
                    break

        best_fwd_gain_pct = (w_high.max() / entry_price - 1) * 100 if len(w_high) else 0.0

        reason = reason_overrides[i] if reason_overrides and i in reason_overrides else reason_string(df, i, name)
        out.append({
            "signal": name, "date": dates[i], "entry_price": round(float(entry_price), 2),
            "reason": reason,
            "hit_1pct": hit_day[0.01] is not None, "days_to_1pct": hit_day[0.01],
            "hit_2pct": hit_day[0.02] is not None, "days_to_2pct": hit_day[0.02],
            "hit_3pct": hit_day[0.03] is not None, "days_to_3pct": hit_day[0.03],
            "max_adverse_dip_pct": round(float(max_adverse_dip_pct), 2),
            "best_fwd_gain_pct": round(float(best_fwd_gain_pct), 2),
            "window_truncated": truncated, "fwd_days_available": int(fwd_avail), "idx": int(i),
        })
    return out


# ---------------------------------------------------------------------------
# Validation gauntlet
# ---------------------------------------------------------------------------

def walk_forward(rows: list, split_date: str = "2018-01-01") -> tuple:
    split = pd.to_datetime(split_date).date()
    train = [r for r in rows if r["date"] < split]
    test = [r for r in rows if r["date"] >= split]

    def stats(rs):
        if not rs:
            return None
        n = len(rs)
        return {
            "n": n,
            "hit1": sum(r["hit_1pct"] for r in rs) / n * 100,
            "hit2": sum(r["hit_2pct"] for r in rs) / n * 100,
            "hit3": sum(r["hit_3pct"] for r in rs) / n * 100,
        }
    return stats(train), stats(test)


def regime_blocks(rows: list, blocks=None) -> list:
    blocks = blocks or [
        ("2007-01-01", "2011-12-31"), ("2012-01-01", "2016-12-31"),
        ("2017-01-01", "2021-12-31"), ("2022-01-01", "2026-12-31"),
    ]
    out = []
    for s, e in blocks:
        sd, ed = pd.to_datetime(s).date(), pd.to_datetime(e).date()
        sub = [r for r in rows if sd <= r["date"] <= ed]
        if sub:
            n = len(sub)
            out.append((s, e, n, sum(r["hit_1pct"] for r in sub) / n * 100))
        else:
            out.append((s, e, 0, None))
    return out


def bootstrap_ci(rows: list, n_boot: int = 5000, seed: int = 42) -> tuple:
    """Non-parametric bootstrap CI on the hit-rate. Caveat: resampling with
    replacement treats signals as i.i.d., which understates uncertainty when
    signals cluster in time (e.g. several ST flips during one choppy month) --
    the CI here should be read as a lower bound on true uncertainty, not exact."""
    rng = np.random.default_rng(seed)
    hits = np.array([r["hit_1pct"] for r in rows], dtype=float)
    n = len(hits)
    boot = rng.choice(hits, size=(n_boot, n), replace=True).mean(axis=1) * 100
    lo, hi = np.percentile(boot, [5, 95])
    return hits.mean() * 100, lo, hi


def supertrend_param_sweep(df0: pd.DataFrame, n_total: int) -> list:
    out = []
    for period in (8, 10, 12):
        for mult in (2.5, 3.0, 3.5):
            st = pta.supertrend(df0["high"], df0["low"], df0["close"], length=period, multiplier=mult)
            d = st[next(x for x in st.columns if x.startswith("SUPERTd"))]
            flip = (d == 1) & (d.shift(1) == -1)
            idxs = [i for i in np.where(flip.fillna(False).values)[0] if i + FORWARD_WINDOW <= n_total - 1]
            rows = compute_forward_outcomes(df0, idxs, f"ST_{period}_{mult}")
            h1 = sum(r["hit_1pct"] for r in rows) / len(rows) * 100 if rows else None
            out.append((period, mult, len(rows), h1))
    return out


def bbands_param_sweep(df0: pd.DataFrame, n_total: int) -> list:
    out = []
    for length in (15, 20, 25):
        for std in (1.8, 2.0, 2.2):
            bb = pta.bbands(df0["close"], length=length, lower_std=std, upper_std=std)
            low = bb[next(x for x in bb.columns if x.startswith("BBL"))]
            below = df0["close"] < low
            reentry = (~below) & (below.shift(1))
            idxs = [i for i in np.where(reentry.fillna(False).values)[0] if i + FORWARD_WINDOW <= n_total - 1]
            rows = compute_forward_outcomes(df0, idxs, f"BB_{length}_{std}")
            h1 = sum(r["hit_1pct"] for r in rows) / len(rows) * 100 if rows else None
            out.append((length, std, len(rows), h1))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# NOTE: a C-family (bullish RSI/price divergence + volume-spike) signal was previously
# developed here but has been REMOVED (2026-07-28) along with its supporting
# add_volume_proxy() / detect_divergence_volume() / divergence_reason_string() /
# divergence_volume_param_sweep() functions. It required a yfinance-sourced ^NSEI Volume
# proxy (drishti.db's own NIFTY50 volume column is always 0 -- an index has no traded
# volume of its own), and the user has explicitly rejected yfinance as a dependency for
# anything in this study. This is a withdrawal for dependency reasons, not because the
# signal failed on its own merits (it was already separately flagged as too-small-sample,
# n=3-11, in the report before this removal). See nifty_entry_signal_backtest_report.md's
# Part 2 for the historical record of what was found, marked withdrawn.

# D-family (2026-07-28 session): EMA9/21 cross + RSI(14) recovery-from-below-40, explicitly
# NO regime/trend gate (user directive), explicitly scored ONLY on the last ~2 years
# (D1_WINDOW_START) even though the underlying EMA/RSI indicators are computed on full
# history so they aren't cold-started at the window boundary. See
# detect_ema_rsi_recovery()'s docstring for the exact no-lookahead confluence logic.
D1_CONFIG = dict(ema_fast=9, ema_slow=21, rsi_threshold=40.0, max_gap=5)


def main():
    parser = argparse.ArgumentParser(description="NIFTY entry-signal quality backtest")
    parser.add_argument("--signal", nargs="*", default=None,
                       help="Restrict to specific signal name(s) (default: all)")
    parser.add_argument("--export-csv", default=None,
                       help="Directory to write full per-signal CSVs into")
    args = parser.parse_args()

    df = load_clean_nifty()
    df = add_indicators(df)
    masks = make_signal_masks(df)
    n = len(df)

    reason_overrides_by_name = {}
    d1_mask, d1_meta = detect_ema_rsi_recovery(df, window_start=D1_WINDOW_START, **D1_CONFIG)
    masks["D1_EMA9_21_RSI40_recovery"] = pd.Series(d1_mask, index=df.index)
    reason_overrides_by_name["D1_EMA9_21_RSI40_recovery"] = {
        i: ema_rsi_recovery_reason_string(df["close"].values[i], d1_meta[i]) for i in np.where(d1_mask)[0]
    }

    e0_mask, e_bucket_masks, e_meta = detect_st26_ema_rsi_buckets(df)
    masks["E0_ST26_flip_base"] = e0_mask
    reason_overrides_by_name["E0_ST26_flip_base"] = {
        i: st26_bucket_reason_string(e_meta[i]) for i in np.where(e0_mask.values)[0]
    }
    for bname, bmask in e_bucket_masks.items():
        masks[bname] = bmask
        reason_overrides_by_name[bname] = {
            i: st26_bucket_reason_string(e_meta[i]) for i in np.where(bmask.values)[0]
        }

    # F-family (2026-07-28 session): two-sided EMA20-gap mean-reversion. Handled SEPARATELY
    # from the generic `masks` loop below because F1/F2 need compute_forward_outcomes_directional
    # (long AND short target/adverse-dip semantics), not the long-only compute_forward_outcomes
    # every other signal here uses.
    f_long_mask, f_short_mask, f_meta = detect_ema20gap_signals(df)
    f_long_idxs = [i for i in np.where(f_long_mask.values)[0] if i + FORWARD_WINDOW <= n - 1]
    f_short_idxs = [i for i in np.where(f_short_mask.values)[0] if i + FORWARD_WINDOW <= n - 1]
    f_long_rows = compute_forward_outcomes_directional(
        df, f_long_idxs, "F1_ema20gap_long", "long",
        reason_overrides={i: ema20gap_reason_string("long", f_meta[i]) for i in f_long_idxs})
    f_short_rows = compute_forward_outcomes_directional(
        df, f_short_idxs, "F2_ema20gap_short", "short",
        reason_overrides={i: ema20gap_reason_string("short", f_meta[i]) for i in f_short_idxs})

    f_names = ["F1_ema20gap_long", "F2_ema20gap_short"]
    names = [x for x in (args.signal or list(masks.keys())) if x in masks]
    f_names_selected = [x for x in (args.signal or f_names) if x in f_names]

    print(f"NIFTY50 1d candles: {len(df)} trading days, {df['date'].min()} .. {df['date'].max()}")
    print(f"D-family (EMA/RSI recovery) scored only from {D1_WINDOW_START} onward "
          f"(user-mandated 2-year window -- see D1_WINDOW_START)\n")
    print(f"{'signal':30s} {'n':>5s} {'hit1%':>7s} {'hit2%':>7s} {'hit3%':>7s} {'avg_dip%':>9s} {'med_days1':>10s}")

    all_results = {}
    for name in names:
        mask = masks[name]
        idxs_all = np.where(mask.values)[0]
        idxs_complete = [i for i in idxs_all if i + FORWARD_WINDOW <= n - 1]
        rows = compute_forward_outcomes(df, idxs_complete, name,
                                         reason_overrides=reason_overrides_by_name.get(name))
        all_results[name] = rows
        if rows:
            h1 = sum(r["hit_1pct"] for r in rows) / len(rows) * 100
            h2 = sum(r["hit_2pct"] for r in rows) / len(rows) * 100
            h3 = sum(r["hit_3pct"] for r in rows) / len(rows) * 100
            dip = np.mean([r["max_adverse_dip_pct"] for r in rows])
            d1s = [r["days_to_1pct"] for r in rows if r["days_to_1pct"] is not None]
            med1 = np.median(d1s) if d1s else float("nan")
            print(f"{name:30s} {len(rows):5d} {h1:7.1f} {h2:7.1f} {h3:7.1f} {dip:9.2f} {med1:10.0f}")
        else:
            print(f"{name:30s} {0:5d} {'--':>7s}")

    f_rows_by_name = {"F1_ema20gap_long": f_long_rows, "F2_ema20gap_short": f_short_rows}
    for fname in f_names_selected:
        frows = f_rows_by_name[fname]
        all_results[fname] = frows
        if frows:
            h1 = sum(r["hit_1pct"] for r in frows) / len(frows) * 100
            h2 = sum(r["hit_2pct"] for r in frows) / len(frows) * 100
            h3 = sum(r["hit_3pct"] for r in frows) / len(frows) * 100
            dip = np.mean([r["max_adverse_dip_pct"] for r in frows])
            d1s = [r["days_to_1pct"] for r in frows if r["days_to_1pct"] is not None]
            med1 = np.median(d1s) if d1s else float("nan")
            print(f"{fname:30s} {len(frows):5d} {h1:7.1f} {h2:7.1f} {h3:7.1f} {dip:9.2f} {med1:10.0f}")
        else:
            print(f"{fname:30s} {0:5d} {'--':>7s}")

    if args.export_csv:
        os.makedirs(args.export_csv, exist_ok=True)
        for name, rows in all_results.items():
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(args.export_csv, f"{name}.csv"), index=False)
        print(f"\nPer-signal CSVs written to {args.export_csv}")


if __name__ == "__main__":
    main()
