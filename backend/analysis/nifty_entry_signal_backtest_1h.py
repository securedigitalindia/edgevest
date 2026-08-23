"""
Drishti — NIFTY Entry-Signal Quality Backtest (1-HOUR timeframe)
=================================================================
Extends the already-validated daily-timeframe combo signal from
`analysis/nifty_entry_signal_backtest.py` (see its report,
`nifty_entry_signal_backtest_report.md`) to 1-hour candles. Concept is
reused verbatim, recomputed on hourly data:

    Base signal:  Bollinger Band(20,2) lower-band re-entry -- close
                  re-enters above the lower band having closed below it
                  on the immediately preceding candle.
    Filter:       z_ema200 = (close - EMA200) / rolling_200period_stddev(close)
                  keep only signals where z_ema200 > -0.5. This is a
                  continuous "how many std-devs of recent volatility below
                  the 200-period trend" measure, NOT a binary above/below
                  trend gate.

On daily data this combo took the signal from n=115/90.4% (unfiltered) to
n=67/94.0% (full-history) and, on the last 2 years specifically, from
n=13/92.3% to n=8/100%. This script does NOT re-derive those numbers --
it recomputes the identical rule on 1h bars and reports how it holds up.

*** CRITICAL CAVEAT: "200" means something very different in calendar
time on 1h bars than on daily bars. *** With the ACTUAL per-day candle
count confirmed directly from the data (see load_clean_nifty_1h()'s
docstring -- 7 candles/trading day: 09:15/10:15/11:15/12:15/13:15/14:15/
15:15 IST), EMA200/rolling-200-stddev on 1h bars spans ~200/7 = ~28.6
trading days (~5.7 weeks, ~1.3 months) of *trend*, vs. ~200 trading days
(~9.5 months) on daily bars. This is a materially shorter-horizon trend
filter, not an equivalent parameterization -- flagged throughout the
report, not silently treated as "the same 200."

Data: SQLite candles_1h via db.queries.get_candles("NIFTY50", "1h", ...).
Only ~2 years of history exist in this table (bootstrapped 730 days back
from an Upstox migration) -- no yfinance fallback is used or permitted for
this study (hard rule, see report). Sanity-checked before use: zero OHLC
integrity violations, zero duplicate timestamps, zero NaNs, all-zero
volume (expected -- NIFTY is an index, exactly as documented for the
daily table). Two calendar dates (2024-11-01, 2025-10-21) have only 1
candle instead of 7 -- these are genuine NSE special/Muhurat-trading
half-sessions, not a data-quality defect (verified against the actual
per-day distribution, not assumed).

Forward window: user specified a MAX of 2 weeks. 2 weeks == 10 trading
days (same convention already used for "42 trading days ~= 2 months" in
the daily study, i.e. ~21 trading days/month => 2 weeks = 10 trading
days). At the CONFIRMED 7 candles/trading day, this is
10 * 7 = 70 one-hour candles -- computed from the data, not assumed from
the user's rough "~60 candles (10 days x ~6/day)" guess, which undercounts
the actual per-day candle rate.

No-lookahead discipline: identical to the daily script. Every indicator
(BB, EMA200, rolling std, z-score) is a backward-looking rolling/EMA
function of candles up to and including candle t. The BB reentry signal
itself only compares candle t's close against candle t and t-1's own
values -- no lookahead. entry_price = close[t]; forward window is
candles t+1 .. t+70 (never t's own high/low).

Usage:
    python analysis/nifty_entry_signal_backtest_1h.py
    python analysis/nifty_entry_signal_backtest_1h.py --export-csv /path/to/dir
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
Z_EMA200_THRESHOLD = -0.5           # base filter threshold, reused from daily study
FORWARD_WEEKS = 2
TRADING_DAYS_PER_WEEK = 5
FORWARD_TRADING_DAYS = FORWARD_WEEKS * TRADING_DAYS_PER_WEEK   # 10 -- matches daily-study's day convention
TARGETS = (0.01, 0.02, 0.03)        # +1% / +2% / +3%, same tiers as daily study

# F-family (2026-07-28 session): EMA20-gap mean-reversion, the first TWO-SIDED (long+short)
# signal family tested on 1h bars -- H/E families above are long-only. See
# detect_ema20gap_signals()'s docstring (shared logic/spec with the daily script's F-family)
# for the exact threshold-crossing definition, recomputed here on 1h closes/EMA20.
EMA20GAP_THRESHOLD = 3.0


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_clean_nifty_1h(limit: int = 20000) -> pd.DataFrame:
    """
    Pull all available NIFTY50 1h candles and sanity-check.

    Data-quality findings (checked directly, not assumed):
      - 3,453 rows total, 2024-07-29 03:45 UTC (09:15 IST) through
        2026-07-27 09:45 UTC (15:15 IST) -- 495 distinct IST trading dates.
      - Per-day candle count: 493 of 495 dates have exactly 7 candles
        (09:15/10:15/11:15/12:15/13:15/14:15/15:15 IST); 2 dates
        (2024-11-01, 2025-10-21) have exactly 1 candle -- both are genuine
        NSE special/Muhurat-trading half-day sessions, not a gap or
        ingestion bug (single-candle "day" is exactly what a ~1hr special
        session should look like).
      - Zero duplicate (symbol, ts) pairs, zero NaNs in OHLCV, zero OHLC
        integrity violations (checked high >= max(open,close,low) and
        low <= min(open,close,high) for every row).
      - volume is 0 on all 3,453 rows -- expected (NIFTY 50 is an index,
        same as the daily table; no volume-based logic is used anywhere
        in this script, per explicit user instruction).
    """
    df = get_candles("NIFTY50", "1h", limit=limit)
    if df.empty:
        raise RuntimeError("No NIFTY50 1h candles found in drishti.db")

    df["ts_ist"] = df["ts"].dt.tz_convert(IST)
    df["date"] = df["ts_ist"].dt.date

    bad_high = df[df["high"] < df[["open", "close", "low"]].max(axis=1)]
    bad_low = df[df["low"] > df[["open", "close", "high"]].min(axis=1)]
    if len(bad_high) or len(bad_low):
        raise RuntimeError(
            f"OHLC integrity violation: {len(bad_high)} bad-high rows, "
            f"{len(bad_low)} bad-low rows"
        )
    if df["ts"].duplicated().any():
        raise RuntimeError("Duplicate (symbol, ts) rows found in candles_1h")
    if df[["open", "high", "low", "close"]].isnull().any().any():
        raise RuntimeError("NaNs found in OHLC columns")

    df = df.sort_values("ts").reset_index(drop=True)
    return df[["ts", "ts_ist", "date", "open", "high", "low", "close", "volume"]].copy()


def confirm_candles_per_day(df: pd.DataFrame) -> dict:
    """Return {per_day_count: n_dates_with_that_count} -- used to derive
    FORWARD_WINDOW_CANDLES from the data rather than assuming it."""
    counts = df.groupby("date").size()
    return counts.value_counts().to_dict()


# ---------------------------------------------------------------------------
# Indicators (all backward-looking -- no centered windows)
# ---------------------------------------------------------------------------

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c, h, l = df["close"], df["high"], df["low"]

    bb = pta.bbands(c, length=20, lower_std=2.0, upper_std=2.0)
    df["bb_low"] = bb[next(x for x in bb.columns if x.startswith("BBL"))]
    df["bb_mid"] = bb[next(x for x in bb.columns if x.startswith("BBM"))]
    df["bb_up"] = bb[next(x for x in bb.columns if x.startswith("BBU"))]

    df["ema200"] = pta.ema(c, length=200)
    df["std200"] = c.rolling(200).std()
    df["z_ema200"] = (c - df["ema200"]) / df["std200"]

    # E-family (2026-07-28 session): Supertrend(10, 2.6) bear->bull flip + EMA(20)/RSI(14)
    # snapshot at the flip candle, on 1h closes. Same indicator recipe as the daily study's
    # E-family, recomputed on hourly bars -- period/multiplier/EMA-length/RSI-length are all
    # literal candle counts here (10, 20, 14 CANDLES, not trading days), per the user's
    # instruction to run the identically-specified signal on this timeframe.
    df["ema20"] = pta.ema(c, length=20)
    df["rsi14"] = pta.rsi(c, length=14)
    st26 = pta.supertrend(h, l, c, length=10, multiplier=2.6)
    df["st26_val"] = st26[next(x for x in st26.columns
                               if x.startswith("SUPERT_10") and not x.startswith("SUPERTd"))]
    df["st26_dir"] = st26[next(x for x in st26.columns if x.startswith("SUPERTd_10"))]

    return df


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------

def detect_bb_reentry(df: pd.DataFrame) -> pd.Series:
    """A3-equivalent base signal, recomputed on 1h closes: close re-enters
    above the BB(20,2) lower band having closed below it on the immediately
    preceding 1h candle. No lookahead: only uses close[t] and close[t-1]
    plus bb_low[t] (itself a backward-looking rolling function)."""
    c = df["close"]
    below_lower = c < df["bb_low"]
    reentry = (~below_lower) & (below_lower.shift(1))
    return reentry.fillna(False)


def make_masks(df: pd.DataFrame, z_threshold: float = Z_EMA200_THRESHOLD) -> dict:
    base = detect_bb_reentry(df)
    filtered = (base & (df["z_ema200"] > z_threshold)).fillna(False)
    return {
        "H1_BB_reentry_unfiltered": base,
        "H2_BB_reentry_z_ema200_filtered": filtered,
    }


def detect_st26_ema_rsi_buckets(df: pd.DataFrame, st_dir_col: str = "st26_dir",
                                 st_val_col: str = "st26_val") -> tuple:
    """E-family, 1h version -- identical logic to the daily script's function of the same
    name (see its docstring for the full spec and the tie-break rule, reused verbatim here):
    Supertrend(10, 2.6) bear->bull flip on 1h candles; at the flip candle, record close vs
    EMA(20) (strict > = above, <= = below/at) and RSI(14) vs 50 (strict > = above, <= =
    below/at), both computed on 1h closes. Single-candle snapshot, trivially lookahead-safe.
    Returns (base_mask, bucket_masks, meta) -- same shape as the daily version."""
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
        f"Supertrend(10,2.6) flips bear->bull, ST={m['st_val']:.2f}; "
        f"close {m['close']:.2f} {ema_side} EMA20={m['ema20_val']:.2f}; "
        f"RSI(14)={m['rsi_val']:.1f} {rsi_side} 50"
    )


def detect_ema20gap_signals(df: pd.DataFrame, threshold: float = EMA20GAP_THRESHOLD) -> tuple:
    """
    F-family, 1h version -- identical spec to the daily script's function of the same name
    (see its docstring for the full definition, edge-case reasoning, and no-lookahead
    argument, reused verbatim here on 1h closes/EMA20 instead of daily ones):

    gap_pct = (close - EMA20) / EMA20 * 100, computed on 1h candles.
    LONG fires the first 1h candle gap_pct crosses BELOW -threshold (bet: mean-reversion UP).
    SHORT fires the first 1h candle gap_pct crosses ABOVE +threshold (bet: mean-reversion
    DOWN). Both are threshold-CROSSING signals (fire once on first breach), same convention
    as the daily F-family and as H1/H2's BB-reentry-style triggers elsewhere in this script.
    entry_price = that candle's own close.

    Returns (long_mask, short_mask, meta: dict[idx -> dict]).
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
        f"(close={m['close']:.2f}, EMA20={m['ema20']:.2f})"
    )


def compute_forward_outcomes_directional(df: pd.DataFrame, sig_idxs, direction: str, window: int,
                                         targets=TARGETS, reason_overrides: dict = None) -> list:
    """
    Two-sided generalization of compute_forward_outcomes() above (which is long-only, used by
    H1/H2/E-family), needed for the F-family long+short EMA20-gap signal on 1h candles.

    direction="long": entry_price=close[i]; target_px=entry*(1+t); a HIT requires the window
    HIGH to reach target_px; max_adverse_dip_pct = worst DOWN move (entry vs. window LOW)
    before the hit (or before window expiry). Identical semantics to compute_forward_outcomes().

    direction="short": entry_price=close[i]; target_px=entry*(1-t); a HIT requires the window
    LOW to reach target_px; max_adverse_dip_pct here means the worst UP move (entry vs.
    window HIGH) before the hit (or before window expiry) -- deliberately INVERTED from the
    long convention, since "adverse" for a short means price rising against it, not falling.

    window is a CANDLE count (i+1 .. i+window, never candle i's own high/low).
    """
    n = len(df)
    close, high, low = df["close"].values, df["high"].values, df["low"].values
    ts_ist_col = df["ts_ist"]
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

        hit_candle = {}
        for tpx, t in zip(targets_px, targets):
            hit_candle[t] = None
            for d in range(len(w_high)):
                touched = (w_high[d] >= tpx) if direction == "long" else (w_low[d] <= tpx)
                if touched:
                    hit_candle[t] = d + 1
                    break

        day_of_1pct = hit_candle[targets[0]]
        if direction == "long":
            adverse_extreme = w_low[:day_of_1pct].min() if day_of_1pct else (w_low.min() if len(w_low) else entry_price)
            max_adverse_dip_pct = max(0.0, (entry_price - adverse_extreme) / entry_price * 100)
            best_fwd_move_pct = (w_high.max() / entry_price - 1) * 100 if len(w_high) else 0.0
        else:
            adverse_extreme = w_high[:day_of_1pct].max() if day_of_1pct else (w_high.max() if len(w_high) else entry_price)
            max_adverse_dip_pct = max(0.0, (adverse_extreme - entry_price) / entry_price * 100)
            best_fwd_move_pct = (1 - w_low.min() / entry_price) * 100 if len(w_low) else 0.0

        reason = reason_overrides[i] if reason_overrides and i in reason_overrides else direction
        out.append({
            "ts_ist": ts_ist_col.iloc[i], "direction": direction,
            "entry_price": round(float(entry_price), 2), "reason": reason,
            "hit_1pct": hit_candle[targets[0]] is not None, "candles_to_1pct": hit_candle[targets[0]],
            "hit_2pct": hit_candle[targets[1]] is not None, "candles_to_2pct": hit_candle[targets[1]],
            "hit_3pct": hit_candle[targets[2]] is not None, "candles_to_3pct": hit_candle[targets[2]],
            "max_adverse_dip_pct": round(float(max_adverse_dip_pct), 2),
            "best_fwd_gain_pct": round(float(best_fwd_move_pct), 2),
            "window_truncated": truncated, "fwd_candles_available": int(fwd_avail), "idx": int(i),
        })
    return out


def ema20gap_param_sweep(df: pd.DataFrame, window: int,
                        thresholds=(2.0, 2.5, 3.0, 3.5, 4.0)) -> list:
    """1h analog of the daily script's ema20gap_param_sweep -- sweep the breach threshold at
    2%/2.5%/3%/3.5%/4% for both LONG and SHORT."""
    n = len(df)
    out = []
    for th in thresholds:
        long_mask, short_mask, meta = detect_ema20gap_signals(df, threshold=th)
        long_idxs = [i for i in np.where(long_mask.values)[0] if i + window <= n - 1]
        short_idxs = [i for i in np.where(short_mask.values)[0] if i + window <= n - 1]
        long_rows = compute_forward_outcomes_directional(df, long_idxs, "long", window)
        short_rows = compute_forward_outcomes_directional(df, short_idxs, "short", window)
        h1_long = sum(r["hit_1pct"] for r in long_rows) / len(long_rows) * 100 if long_rows else None
        h1_short = sum(r["hit_1pct"] for r in short_rows) / len(short_rows) * 100 if short_rows else None
        out.append((th, len(long_rows), h1_long, len(short_rows), h1_short))
    return out


def reason_string(df: pd.DataFrame, i: int) -> str:
    row = df.iloc[i]
    return (
        f"close {row['close']:.2f} re-enters above BB(20,2) lower band "
        f"{row['bb_low']:.2f}; z_ema200={row['z_ema200']:.2f} "
        f"(EMA200={row['ema200']:.2f}, std200={row['std200']:.2f})"
    )


# ---------------------------------------------------------------------------
# Forward-outcome evaluation
# ---------------------------------------------------------------------------

def compute_forward_outcomes(df: pd.DataFrame, sig_idxs, window: int,
                             targets=TARGETS, reason_overrides: dict = None) -> list:
    """
    entry_price = close[i] (signal candle's own close). Forward window =
    candles i+1 .. i+window (never includes candle i's own high/low --
    avoids same-bar lookahead). window is a CANDLE count, not a calendar
    span, so it naturally absorbs the two single-candle special-session
    days without special-casing them.
    """
    n = len(df)
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    # NOTE: deliberately NOT using df["ts_ist"].values here -- .values on a
    # tz-aware Series silently drops the tz label while keeping the
    # UNDERLYING UTC instant (a well-known pandas gotcha), which would mean
    # displaying UTC times mislabeled as IST. Using .iloc[i] on the Series
    # itself preserves the tz-aware Asia/Kolkata Timestamp correctly.
    ts_ist_col = df["ts_ist"]
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

        hit_candle = {}
        for tpx, t in zip(targets_px, targets):
            hit_candle[t] = None
            for d in range(len(w_high)):
                if w_high[d] >= tpx:
                    hit_candle[t] = d + 1
                    break

        best_fwd_gain_pct = (w_high.max() / entry_price - 1) * 100 if len(w_high) else 0.0

        out.append({
            "ts_ist": ts_ist_col.iloc[i], "entry_price": round(float(entry_price), 2),
            "bb_low": round(float(df["bb_low"].values[i]), 2),
            "z_ema200": round(float(df["z_ema200"].values[i]), 3),
            "reason": reason_overrides[i] if reason_overrides and i in reason_overrides else reason_string(df, i),
            "hit_1pct": hit_candle[0.01] is not None, "candles_to_1pct": hit_candle[0.01],
            "hit_2pct": hit_candle[0.02] is not None, "candles_to_2pct": hit_candle[0.02],
            "hit_3pct": hit_candle[0.03] is not None, "candles_to_3pct": hit_candle[0.03],
            "max_adverse_dip_pct": round(float(max_adverse_dip_pct), 2),
            "best_fwd_gain_pct": round(float(best_fwd_gain_pct), 2),
            "window_truncated": truncated, "fwd_candles_available": int(fwd_avail), "idx": int(i),
        })
    return out


# ---------------------------------------------------------------------------
# Validation gauntlet
# ---------------------------------------------------------------------------

def stats(rows: list) -> dict:
    if not rows:
        return {"n": 0}
    n = len(rows)
    return {
        "n": n,
        "hit1": sum(r["hit_1pct"] for r in rows) / n * 100,
        "hit2": sum(r["hit_2pct"] for r in rows) / n * 100,
        "hit3": sum(r["hit_3pct"] for r in rows) / n * 100,
        "avg_dip": float(np.mean([r["max_adverse_dip_pct"] for r in rows])),
    }


def walk_forward_split(rows: list, split_ts: pd.Timestamp) -> tuple:
    train = [r for r in rows if r["ts_ist"] < split_ts]
    test = [r for r in rows if r["ts_ist"] >= split_ts]
    return stats(train), stats(test)


def rolling_walk_forward(rows: list, n_folds: int = 4) -> list:
    """Chronological k-fold walk-forward: fold k trains on folds 1..k-1 pooled
    (expanding window) and tests on fold k alone. First fold has no prior
    train data so is skipped as a train set (still reported as a test-only
    baseline fold)."""
    if len(rows) < n_folds * 5:
        return []
    rows_sorted = sorted(rows, key=lambda r: r["ts_ist"])
    n = len(rows_sorted)
    fold_size = n // n_folds
    folds = [rows_sorted[i * fold_size: (i + 1) * fold_size if i < n_folds - 1 else n]
             for i in range(n_folds)]
    out = []
    for k in range(n_folds):
        test = folds[k]
        train = [r for j in range(k) for r in folds[j]]
        out.append((k + 1, stats(train), stats(test)))
    return out


def bootstrap_ci(rows: list, n_boot: int = 5000, seed: int = 42) -> tuple:
    """Non-parametric bootstrap CI on the hit-rate. Same i.i.d.-resampling
    caveat as the daily study: understates true uncertainty when signals
    cluster in time."""
    rng = np.random.default_rng(seed)
    hits = np.array([r["hit_1pct"] for r in rows], dtype=float)
    n = len(hits)
    if n == 0:
        return None
    boot = rng.choice(hits, size=(n_boot, n), replace=True).mean(axis=1) * 100
    lo, hi = np.percentile(boot, [5, 95])
    return hits.mean() * 100, lo, hi


def clopper_pearson_ci(hits: int, n: int, alpha: float = 0.10) -> tuple:
    """Exact-binomial CI -- correct tool when the bootstrap goes degenerate
    on small or all-hit samples (same tool used for the daily study's D/C
    families)."""
    from scipy import stats as sstats
    if n == 0:
        return (None, None)
    lo = 0.0 if hits == 0 else sstats.beta.ppf(alpha / 2, hits, n - hits + 1)
    hi = 1.0 if hits == n else sstats.beta.ppf(1 - alpha / 2, hits + 1, n - hits)
    return lo * 100, hi * 100


def z_threshold_sweep(df: pd.DataFrame, window: int, thresholds=(-0.3, -0.4, -0.5, -0.6, -0.7)) -> list:
    base = detect_bb_reentry(df)
    n = len(df)
    out = []
    for th in thresholds:
        mask = (base & (df["z_ema200"] > th)).fillna(False)
        idxs = [i for i in np.where(mask.values)[0] if i + window <= n - 1]
        rows = compute_forward_outcomes(df, idxs, window)
        s = stats(rows)
        out.append((th, s.get("n", 0), s.get("hit1")))
    return out


def bb_param_sweep(df: pd.DataFrame, window: int, z_threshold: float = Z_EMA200_THRESHOLD) -> list:
    out = []
    for length in (15, 20, 25):
        for bstd in (1.8, 2.0, 2.2):
            bb = pta.bbands(df["close"], length=length, lower_std=bstd, upper_std=bstd)
            low = bb[next(x for x in bb.columns if x.startswith("BBL"))]
            below = df["close"] < low
            reentry = (~below) & (below.shift(1))
            mask = (reentry.fillna(False) & (df["z_ema200"] > z_threshold)).fillna(False)
            idxs = [i for i in np.where(mask.values)[0] if i + window <= len(df) - 1]
            rows = compute_forward_outcomes(df, idxs, window)
            s = stats(rows)
            out.append((length, bstd, s.get("n", 0), s.get("hit1")))
    return out


def window_sweep(df: pd.DataFrame, mask: pd.Series, windows=(35, 49, 70, 91, 105)) -> list:
    """Sensitivity of the forward-window candle count itself (0.5wk/1wk/2wk(base)/2.6wk/3wk)."""
    n = len(df)
    out = []
    for w in windows:
        idxs = [i for i in np.where(mask.values)[0] if i + w <= n - 1]
        rows = compute_forward_outcomes(df, idxs, w)
        s = stats(rows)
        out.append((w, s.get("n", 0), s.get("hit1")))
    return out


def st26_param_sweep(df: pd.DataFrame, window: int) -> list:
    """1h analog of the daily script's st26_param_sweep -- perturb Supertrend(10, 2.6)'s
    period (+-20%) and multiplier (+-~15-20%), re-score the E1 headline combo (flip +
    close>EMA20 + RSI>50) on 1h bars."""
    n = len(df)
    out = []
    for period in (8, 10, 12):
        for mult in (2.1, 2.35, 2.6, 2.85, 3.1):
            st = pta.supertrend(df["high"], df["low"], df["close"], length=period, multiplier=mult)
            d = st[next(x for x in st.columns if x.startswith("SUPERTd"))]
            flip = ((d == 1) & (d.shift(1) == -1)).fillna(False)
            c_v, ema20_v, rsi_v = df["close"].values, df["ema20"].values, df["rsi14"].values
            above_ema = c_v > ema20_v
            above_rsi = rsi_v > 50.0
            e1_mask = flip.values & above_ema & above_rsi
            idxs = [i for i in np.where(e1_mask)[0] if i + window <= n - 1]
            rows = compute_forward_outcomes(df, idxs, window)
            s = stats(rows)
            out.append((period, mult, s.get("n", 0), s.get("hit1")))
    return out


def cost_stress_test(rows: list, one_way_bps: float = 5.0) -> dict:
    """Not a P&L study (no sizing/costs per the daily study's scope either),
    but as a substitute 'cost sensitivity' proxy: require the +1% target to
    clear entry by an extra round-trip friction margin (slippage + a token
    brokerage/STT/stamp-duty/GST bps estimate for an index trade wrapper,
    doubled per the mandated stress test) before counting as a hit. This
    reuses the existing high-touch data rather than re-running a fresh
    backtest, since no sizing/exit rule exists to attach real P&L to."""
    # Indian cash-equiv index costs are a few bps one-way; double it as the stress case.
    margin = 2 * one_way_bps / 10000.0
    hits = [r for r in rows if r["hit_1pct"]]
    n = len(rows)
    if n == 0:
        return {"n": 0}
    # Recompute at threshold (1% + margin) using stored entry/target proximity is not directly
    # possible without raw arrays; approximate conservatively by shifting target to 1%+margin
    # and reusing max_fwd_gain (best_fwd_gain_pct) as the ceiling check.
    stressed_hits = sum(1 for r in rows if r["best_fwd_gain_pct"] >= (1.0 + margin * 100))
    return {"n": n, "hit1_stressed_pct": stressed_hits / n * 100, "margin_bps_roundtrip": margin * 10000}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="NIFTY 1h entry-signal quality backtest")
    parser.add_argument("--export-csv", default=None, help="Directory to write per-signal CSVs into")
    args = parser.parse_args()

    df = load_clean_nifty_1h()
    per_day = confirm_candles_per_day(df)
    df = add_indicators(df)
    n = len(df)

    print(f"NIFTY50 1h candles: {n} rows, {df['date'].min()} .. {df['date'].max()} "
          f"({df['date'].nunique()} distinct IST trading dates)")
    print(f"Per-day candle count distribution: {per_day}")

    window = FORWARD_TRADING_DAYS * 7  # 7 = confirmed candles/day from the data
    print(f"Forward window: {FORWARD_TRADING_DAYS} trading days x 7 candles/day = {window} candles "
          f"(2-week max per instruction)\n")

    masks = make_masks(df)
    reason_overrides_by_name = {}

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

    all_results = {}
    for name, mask in masks.items():
        idxs = [i for i in np.where(mask.values)[0] if i + window <= n - 1]
        rows = compute_forward_outcomes(df, idxs, window,
                                         reason_overrides=reason_overrides_by_name.get(name))
        all_results[name] = rows
        s = stats(rows)
        if s.get("n"):
            print(f"{name:35s} n={s['n']:4d}  hit1={s['hit1']:.1f}%  hit2={s['hit2']:.1f}%  "
                  f"hit3={s['hit3']:.1f}%  avg_dip={s['avg_dip']:.2f}%")
        else:
            print(f"{name:35s} n=0")

    # F-family (2026-07-28 session): two-sided EMA20-gap mean-reversion, handled separately
    # since it needs compute_forward_outcomes_directional (long AND short semantics), not the
    # long-only compute_forward_outcomes every other signal here uses.
    f_long_mask, f_short_mask, f_meta = detect_ema20gap_signals(df)
    f_long_idxs = [i for i in np.where(f_long_mask.values)[0] if i + window <= n - 1]
    f_short_idxs = [i for i in np.where(f_short_mask.values)[0] if i + window <= n - 1]
    f_long_rows = compute_forward_outcomes_directional(
        df, f_long_idxs, "long", window,
        reason_overrides={i: ema20gap_reason_string("long", f_meta[i]) for i in f_long_idxs})
    f_short_rows = compute_forward_outcomes_directional(
        df, f_short_idxs, "short", window,
        reason_overrides={i: ema20gap_reason_string("short", f_meta[i]) for i in f_short_idxs})
    all_results["F1_ema20gap_long"] = f_long_rows
    all_results["F2_ema20gap_short"] = f_short_rows
    for fname, frows in (("F1_ema20gap_long", f_long_rows), ("F2_ema20gap_short", f_short_rows)):
        s = stats(frows)
        if s.get("n"):
            print(f"{fname:35s} n={s['n']:4d}  hit1={s['hit1']:.1f}%  hit2={s['hit2']:.1f}%  "
                  f"hit3={s['hit3']:.1f}%  avg_dip={s['avg_dip']:.2f}%")
        else:
            print(f"{fname:35s} n=0")

    if args.export_csv:
        os.makedirs(args.export_csv, exist_ok=True)
        for name, rows in all_results.items():
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(args.export_csv, f"{name}.csv"), index=False)
        print(f"\nPer-signal CSVs written to {args.export_csv}")


if __name__ == "__main__":
    main()
