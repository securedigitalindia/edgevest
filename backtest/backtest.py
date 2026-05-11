"""
Drishti Backtester
==================
Replay historical candles against any config-defined trigger.
Simulates a fixed TP / SL per trade and reports all entry-exit results.

Usage:
    # Test specific triggers (default: all confluence_cross in config)
    python backtest/backtest.py --trigger EMA20_15M_BULLISH EMA20_15M_BEARISH

    # Override TP / SL / lookback
    python backtest/backtest.py --days 30 --tp 100 --sl 20

    # More realistic entry (next candle open instead of signal-candle close)
    python backtest/backtest.py --entry next_open

    # Filter to specific symbols
    python backtest/backtest.py --symbol NIFTY50

Supported trigger types:  confluence_cross
                          (ema_cross / supertrend_cross / rsi_threshold — add as needed)
"""

import sys
import os
import argparse
import pandas as pd
import pandas_ta as pta
from datetime import timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import SYMBOLS, TRIGGERS
from db.queries import get_candles

IST = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------------------
# Indicator helpers  (operate on a full DataFrame slice, no DB calls)
# ---------------------------------------------------------------------------

def _add_ema(df: pd.DataFrame, period: int) -> pd.DataFrame:
    df = df.copy()
    df[f"ema_{period}"] = pta.ema(df["close"], length=period)
    return df


def _add_supertrend(df: pd.DataFrame, period: int, multiplier: float) -> pd.DataFrame:
    df = df.copy()
    st = pta.supertrend(df["high"], df["low"], df["close"],
                        length=period, multiplier=multiplier)
    val_col = next(c for c in st.columns
                   if c.startswith("SUPERT_") and not any(x in c for x in ("_d", "_s", "_l")))
    dir_col = next(c for c in st.columns if c.startswith("SUPERTd_"))
    df[f"st_{period}_{multiplier}_val"] = st[val_col]
    df[f"st_{period}_{multiplier}_dir"] = st[dir_col]
    return df


# ---------------------------------------------------------------------------
# Signal detection — one function per trigger type
# ---------------------------------------------------------------------------

def _detect_confluence_cross(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Detect all candles where the confluence_cross trigger would have fired.
    Returns a sub-DataFrame of those candles with extra columns:
        signal_dir  "UP" | "DOWN"
        cross_val   float — value of the crossed indicator at that candle
    """
    cross_cfg = cfg["cross"]
    ind       = cross_cfg["indicator"]
    direction = cfg.get("direction")

    # --- Build cross indicator ---
    if ind == "ema":
        period = cross_cfg["period"]
        df = _add_ema(df, period)
        cross_col = f"ema_{period}"
    elif ind == "supertrend":
        p, m = cross_cfg["period"], cross_cfg["multiplier"]
        df = _add_supertrend(df, p, m)
        cross_col = f"st_{p}_{m}_val"
    else:
        raise ValueError(f"Unknown cross indicator: {ind!r}")

    # --- Pre-compute ST indicators needed by confirm conditions ---
    for cond in cfg.get("confirm", []):
        if cond["type"] == "supertrend_direction":
            p, m = cond["period"], cond["multiplier"]
            if f"st_{p}_{m}_dir" not in df.columns:
                df = _add_supertrend(df, p, m)

    # --- Intraday day-high / day-low (rolling cummax/cummin within each IST day) ---
    if any(c["type"] in ("price_below_day_high", "price_above_day_low")
           for c in cfg.get("confirm", [])):
        df["_ist_date"] = df["ts"].dt.tz_convert(IST).dt.date
        df["day_high"]  = df.groupby("_ist_date")["high"].cummax()
        df["day_low"]   = df.groupby("_ist_date")["low"].cummin()

    # --- Detect raw crosses using high/low, not close ---
    # Previous candle's close sets the prior state (was price above or below indicator?).
    # Current candle uses high/low to check if the indicator level was touched this candle —
    # consistent with entry detection: we can't rely on close since the touch can happen
    # intra-candle and close can bounce back (as the live trigger fires on LTP, not close).
    prev_above = df["close"].shift(1) > df[cross_col].shift(1)
    df["_cross_up"]   = (~prev_above) & (df["high"] >= df[cross_col])
    df["_cross_down"] = prev_above    & (df["low"]  <= df[cross_col])

    if direction == "UP":
        mask = df["_cross_up"]
    elif direction == "DOWN":
        mask = df["_cross_down"]
    else:
        mask = df["_cross_up"] | df["_cross_down"]

    cross_rows = df[mask].copy()

    # --- Evaluate confirm conditions row by row (only on crossed candles) ---
    signal_idxs = []
    for idx, row in cross_rows.iterrows():
        cross_dir = "UP" if row["_cross_up"] else "DOWN"
        ok = True
        for cond in cfg.get("confirm", []):
            ctype = cond["type"]
            if ctype == "supertrend_direction":
                p, m  = cond["period"], cond["multiplier"]
                st_dir = row[f"st_{p}_{m}_dir"]
                exp    = cond.get("expected")
                if exp == "bullish":
                    ok = st_dir == 1
                elif exp == "bearish":
                    ok = st_dir == -1
                else:
                    ok = st_dir == (1 if cross_dir == "UP" else -1)
            elif ctype == "price_below_day_high":
                ok = row["close"] < row["day_high"]
            elif ctype == "price_above_day_low":
                ok = row["close"] > row["day_low"]
            # unknown types pass through
            if not ok:
                break
        if ok:
            signal_idxs.append(idx)

    if not signal_idxs:
        return pd.DataFrame()

    result = df.loc[signal_idxs].copy()
    result["signal_dir"] = result.apply(
        lambda r: "UP" if r["_cross_up"] else "DOWN", axis=1)
    result["cross_val"]  = result[cross_col]
    return result


def detect_signals(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    ttype = cfg["type"]
    if ttype == "confluence_cross":
        return _detect_confluence_cross(df, cfg)
    raise ValueError(f"Backtest not yet implemented for trigger type: {ttype!r}")


# Candle minutes per timeframe key
_TF_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "1d": 1440, "1wk": 10080}


def _get_cross_col(cfg: dict) -> str:
    """Return the cross-indicator column name from a trigger config."""
    c = cfg["cross"]
    if c["indicator"] == "ema":
        return f"ema_{c['period']}"
    if c["indicator"] == "supertrend":
        return f"st_{c['period']}_{c['multiplier']}_val"
    raise ValueError(f"Unknown cross indicator: {c['indicator']!r}")


# ---------------------------------------------------------------------------
# Trade simulation
# ---------------------------------------------------------------------------

def simulate_trades(signal_df: pd.DataFrame, signals: pd.DataFrame,
                    exit_df: pd.DataFrame,
                    tp_pts: float, sl_pts: float | None = None,
                    entry_5m_df: pd.DataFrame | None = None,
                    entry_mode: str = "5m_cross",
                    tf_minutes: int = 15,
                    mode: str = "intraday",
                    max_hold_days: int = 10,
                    exit_mode: str = "fixed",
                    trigger_cfg: dict | None = None) -> list[dict]:
    """
    Entry  : detected on signal_df (trigger timeframe, e.g. 15m)
    Exit   : scanned on exit_df

    entry_mode:
        "5m_cross"  — enter at cross_val using 1m/5m candle touch inside 15m window
        "close"     — 15m signal-candle close
        "next_open" — next 15m candle open

    exit_mode:
        "fixed"     — fixed TP (tp_pts) and fixed SL (sl_pts, required)
        "trail_ema" — trailing stop (tp_pts gap) + EMA20 close condition;
                      sl_pts = optional initial hard SL before trailing activates
        "trail_ind" — trailing stop (tp_pts gap) + trigger's own cross indicator close;
                      sl_pts = optional hard SL (if price never moves your way);
                      indicator and period are taken from trigger_cfg automatically

    mode = "intraday"   exit same-day, force-exit EOD
    mode = "positional" exit across days, force-exit EXPIRED

    Trade direction:
        signal_dir DOWN  ->  LONG   (bullish)
        signal_dir UP    ->  SHORT  (bearish)
    """
    signal_df = signal_df.copy()
    signal_df["_ist_date"] = signal_df["ts"].dt.tz_convert(IST).dt.date

    if exit_mode == "trail_ema":
        signal_df["_ema20"] = pta.ema(signal_df["close"], length=20)

    trail_ind_col = None
    if exit_mode == "trail_ind" and trigger_cfg is not None:
        trail_ind_col = _get_cross_col(trigger_cfg)
        c = trigger_cfg["cross"]
        if trail_ind_col not in signal_df.columns:
            if c["indicator"] == "ema":
                signal_df[trail_ind_col] = pta.ema(signal_df["close"], length=c["period"])
            elif c["indicator"] == "supertrend":
                signal_df = _add_supertrend(signal_df, c["period"], c["multiplier"])

    exit_df = exit_df.copy()
    exit_df["_ist_date"] = exit_df["ts"].dt.tz_convert(IST).dt.date
    exit_df = exit_df.reset_index(drop=True)

    if entry_5m_df is not None:
        entry_5m_df = entry_5m_df.reset_index(drop=True)

    results = []

    for sig_idx, sig_row in signals.iterrows():
        is_long  = sig_row["signal_dir"] == "DOWN"
        sig_date = signal_df.at[sig_idx, "_ist_date"]
        pos      = signal_df.index.get_loc(sig_idx)

        # --- Entry ---
        if entry_mode == "5m_cross" and entry_5m_df is not None:
            # Find the first fine candle inside the 15m window where cross_val was touched
            window_start = sig_row["ts"]
            window_end   = window_start + pd.Timedelta(minutes=tf_minutes)
            window_5m    = entry_5m_df[
                (entry_5m_df["ts"] >= window_start) &
                (entry_5m_df["ts"] <  window_end)
            ]
            # Infer candle interval from entry df (1m or 5m)
            if len(entry_5m_df) >= 2:
                _delta = (entry_5m_df["ts"].iloc[1] - entry_5m_df["ts"].iloc[0]).total_seconds()
                entry_interval_min = max(1, int(round(_delta / 60)))
            else:
                entry_interval_min = 5
            cross_val    = float(sig_row["cross_val"])
            entry_price  = float(sig_row["close"])   # fallback to 15m close
            scan_from_ts = window_end
            for _, frow in window_5m.iterrows():
                touched = (
                    (sig_row["signal_dir"] == "UP"   and frow["high"] >= cross_val) or
                    (sig_row["signal_dir"] == "DOWN" and frow["low"]  <= cross_val)
                )
                if touched:
                    entry_price  = cross_val   # enter at the crossing level, not candle close
                    scan_from_ts = frow["ts"] + pd.Timedelta(minutes=entry_interval_min)
                    break

        elif entry_mode == "next_open":
            if pos + 1 >= len(signal_df):
                continue
            next_row = signal_df.iloc[pos + 1]
            if next_row["_ist_date"] != sig_date:
                continue
            entry_price  = float(next_row["open"])
            scan_from_ts = next_row["ts"]

        else:   # "close"
            entry_price  = float(sig_row["close"])
            scan_from_ts = sig_row["ts"] + pd.Timedelta(minutes=tf_minutes)

        eod_label  = "EOD" if mode == "intraday" else "EXPIRED"
        outcome    = eod_label
        exit_price = entry_price
        exit_ts    = scan_from_ts

        if exit_mode == "fixed":
            tp_price = entry_price + tp_pts if is_long else entry_price - tp_pts
            sl_price = entry_price - sl_pts if is_long else entry_price + sl_pts

            if mode == "intraday":
                scan_rows = exit_df[
                    (exit_df["_ist_date"] == sig_date) &
                    (exit_df["ts"] >= scan_from_ts)
                ]
            else:
                scan_rows = exit_df[exit_df["_ist_date"] > sig_date].head(max_hold_days)

            for _, erow in scan_rows.iterrows():
                exit_price = float(erow["close"])
                exit_ts    = erow["ts"]
                if is_long:
                    if erow["high"] >= tp_price:
                        outcome, exit_price, exit_ts = "TP", tp_price, erow["ts"]; break
                    if erow["low"] <= sl_price:
                        outcome, exit_price, exit_ts = "SL", sl_price, erow["ts"]; break
                else:
                    if erow["low"] <= tp_price:
                        outcome, exit_price, exit_ts = "TP", tp_price, erow["ts"]; break
                    if erow["high"] >= sl_price:
                        outcome, exit_price, exit_ts = "SL", sl_price, erow["ts"]; break

        elif exit_mode in ("trail_ema", "trail_ind"):
            hard_sl = None
            if sl_pts is not None:
                hard_sl = entry_price - sl_pts if is_long else entry_price + sl_pts

            running_ext = entry_price
            trail_sl    = hard_sl   # None until price moves tp_pts (or hard_sl if set)

            fives = exit_df[
                (exit_df["_ist_date"] == sig_date) &
                (exit_df["ts"] >= scan_from_ts)
            ]
            fifteens = signal_df[
                (signal_df["_ist_date"] == sig_date) &
                (signal_df["ts"] >= scan_from_ts)
            ]

            ind_col = "_ema20" if exit_mode == "trail_ema" else trail_ind_col

            fives_ev   = fives[["ts", "high", "low", "close"]].copy()
            fives_ev["_ev"] = "5m"
            fifteen_ev = fifteens[["ts", "close", ind_col]].copy()
            fifteen_ev["_ev"] = "15m"

            events = pd.concat(
                [fives_ev.assign(high=fives_ev["high"], low=fives_ev["low"]),
                 fifteen_ev.assign(high=float("nan"), low=float("nan"))],
                ignore_index=True
            ).sort_values("ts")

            ind_exit_label = "EMA_CLOSE" if exit_mode == "trail_ema" else "IND_EXIT"

            for _, ev in events.iterrows():
                if ev["_ev"] == "5m":
                    exit_price = float(ev["close"])
                    exit_ts    = ev["ts"]
                    h, l       = float(ev["high"]), float(ev["low"])

                    if is_long:
                        if tp_pts is not None and h > running_ext:
                            running_ext = h
                            new_trail   = running_ext - tp_pts
                            trail_sl    = max(trail_sl, new_trail) if trail_sl is not None else new_trail
                        if trail_sl is not None and l <= trail_sl:
                            outcome, exit_price, exit_ts = "TRAIL_SL", trail_sl, ev["ts"]
                            break
                    else:
                        if tp_pts is not None and l < running_ext:
                            running_ext = l
                            new_trail   = running_ext + tp_pts
                            trail_sl    = min(trail_sl, new_trail) if trail_sl is not None else new_trail
                        if trail_sl is not None and h >= trail_sl:
                            outcome, exit_price, exit_ts = "TRAIL_SL", trail_sl, ev["ts"]
                            break

                else:  # 15m close — indicator check
                    c       = float(ev["close"])
                    ind_val = ev.get(ind_col)
                    if pd.isna(ind_val):
                        continue
                    ind_val = float(ind_val)
                    if is_long and c < ind_val:
                        outcome, exit_price, exit_ts = ind_exit_label, c, ev["ts"]
                        break
                    if not is_long and c > ind_val:
                        outcome, exit_price, exit_ts = ind_exit_label, c, ev["ts"]
                        break
                    exit_price = c
                    exit_ts    = ev["ts"]

        pnl = (exit_price - entry_price) if is_long else (entry_price - exit_price)

        results.append({
            "signal_ts":   sig_row["ts"],
            "signal_dir":  sig_row["signal_dir"],
            "side":        "LONG" if is_long else "SHORT",
            "entry_price": round(entry_price, 2),
            "exit_ts":     exit_ts,
            "exit_price":  round(exit_price, 2),
            "outcome":     outcome,
            "pnl":         round(pnl, 2),
            "cross_val":   round(float(sig_row.get("cross_val", 0)), 2),
        })

    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(results: list[dict], trigger_name: str, symbol: str,
                 tp_pts: float, sl_pts: float | None, mode: str = "intraday",
                 exit_mode: str = "fixed"):
    if not results:
        print(f"\n  {symbol}  [{trigger_name}]  — no signals in window")
        return

    forced_label = "EOD" if mode == "intraday" else "EXPIRED"
    fmt = "%d %b  %H:%M" if mode == "intraday" else "%d %b %Y"

    if exit_mode == "fixed":
        params_str = f"TP=+{tp_pts:.0f}  SL=-{sl_pts:.0f}"
    elif exit_mode in ("trail_ema", "trail_ind"):
        parts = []
        if tp_pts is not None:
            parts.append(f"trail={tp_pts:.0f}")
        if sl_pts is not None:
            parts.append(f"SL=-{sl_pts:.0f}")
        params_str = "  ".join(parts) if parts else "pure indicator"

    print(f"\n{'='*76}")
    print(f"  {symbol}  ·  {trigger_name}  [{mode}]  [{exit_mode}]"
          f"   {params_str}"
          f"  ({len(results)} trade{'s' if len(results) != 1 else ''})")
    print(f"{'='*76}")
    print(f"  {'Entry':<17} {'Side':<6} {'Entry Px':>9}  "
          f"{'Exit':<17} {'Exit Px':>9}  {'P&L':>8}  Out")
    print(f"  {'-'*73}")

    for r in results:
        entry_str = pd.Timestamp(r["signal_ts"]).tz_convert(IST).strftime("%d %b  %H:%M")
        exit_str  = pd.Timestamp(r["exit_ts"]).tz_convert(IST).strftime(fmt)
        pnl_str   = f"{r['pnl']:+.1f}"
        print(f"  {entry_str:<17} {r['side']:<6} {r['entry_price']:>9,.1f}  "
              f"{exit_str:<17} {r['exit_price']:>9,.1f}  {pnl_str:>8}  {r['outcome']}")

    total      = len(results)
    tp_cnt     = sum(1 for r in results if r["outcome"] == "TP")
    sl_cnt     = sum(1 for r in results if r["outcome"] in ("SL", "TRAIL_SL"))
    ind_cnt    = sum(1 for r in results if r["outcome"] in ("EMA_CLOSE", "IND_EXIT"))
    forced_cnt = sum(1 for r in results if r["outcome"] == forced_label)
    net_pnl    = sum(r["pnl"] for r in results)
    win_rate   = sum(1 for r in results if r["pnl"] > 0) / total * 100

    summary = f"Trades: {total}   TRAIL_SL: {sl_cnt}   {forced_label}: {forced_cnt}"
    if tp_cnt:
        summary += f"   TP: {tp_cnt}"
    if ind_cnt:
        ind_label = "EMA_CLOSE" if exit_mode == "trail_ema" else "IND_EXIT"
        summary += f"   {ind_label}: {ind_cnt}"
    print(f"\n  {summary}   Win rate: {win_rate:.0f}%   Net P&L: {net_pnl:+.1f} pts")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _expand_symbols(sym_cfg) -> list[str]:
    all_names = [s["name"] for s in SYMBOLS]
    return all_names if sym_cfg == "all" else [n for n in sym_cfg if n in all_names]


def run_backtest(trigger_names: list[str], symbol_filter: list[str],
                 days: int, tp_pts: float, sl_pts: float | None,
                 entry_mode: str, mode: str, max_hold_days: int,
                 exit_mode: str = "fixed"):

    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)

    triggers = [t for t in TRIGGERS if t["name"] in trigger_names]
    if not triggers:
        print(f"No matching triggers found: {trigger_names}")
        print(f"Available: {[t['name'] for t in TRIGGERS]}")
        return

    for cfg in triggers:
        tf_minutes = _TF_MINUTES.get(cfg["timeframe"], 15)
        symbols    = _expand_symbols(cfg.get("symbols", "all"))
        if symbol_filter:
            symbols = [s for s in symbols if s in symbol_filter]

        for symbol in symbols:
            # Signal detection candles (trigger timeframe)
            df = get_candles(symbol, cfg["timeframe"], limit=10000)
            if df.empty:
                print(f"  No candle data for {symbol} [{cfg['timeframe']}]")
                continue
            df = df[df["ts"] >= cutoff].reset_index(drop=True)
            if len(df) < 50:
                print(f"  Insufficient data: {symbol} [{cfg['timeframe']}] — {len(df)} rows")
                continue

            # 1m candles for entry detection (most accurate); fall back to 5m if not built yet
            df_1m = get_candles(symbol, "1m", limit=50000)
            if not df_1m.empty:
                df_1m = df_1m[df_1m["ts"] >= cutoff].reset_index(drop=True)

            df_5m = get_candles(symbol, "5m", limit=10000)
            if not df_5m.empty:
                df_5m = df_5m[df_5m["ts"] >= cutoff].reset_index(drop=True)

            # Entry discovery: 1m preferred (find exact cross within 15m window),
            # fall back to 5m. 1m only has 7 days from yfinance but grows from live ticks.
            entry_df = df_1m if not df_1m.empty else (df_5m if not df_5m.empty else None)
            entry_res = "1m" if not df_1m.empty else ("5m" if not df_5m.empty else "none")

            # Exit scanning: 5m for intraday (60-day history covers full backtest window),
            # 1d for positional. 1m exit scanning deferred until enough history builds up.
            if mode == "intraday":
                exit_df = df_5m
            else:
                exit_df = get_candles(symbol, "1d", limit=10000)
                if not exit_df.empty:
                    exit_df = exit_df[exit_df["ts"] >= cutoff].reset_index(drop=True)

            if exit_df is None or exit_df.empty:
                print(f"  Warning: no exit data for {symbol}, falling back to {cfg['timeframe']}")
                exit_df = df

            print(f"  [{symbol}]  entry: {entry_res}  exit: "
                  f"{'5m' if mode == 'intraday' else '1d'}")

            try:
                signals = detect_signals(df, cfg)
            except Exception as e:
                print(f"  Signal detection failed [{symbol} / {cfg['name']}]: {e}")
                continue

            results  = simulate_trades(df, signals, exit_df, tp_pts, sl_pts,
                                       entry_df, entry_mode, tf_minutes,
                                       mode, max_hold_days, exit_mode,
                                       trigger_cfg=cfg)
            print_report(results, cfg["name"], symbol, tp_pts, sl_pts, mode, exit_mode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drishti backtester")
    parser.add_argument("--trigger", nargs="*", default=[], metavar="NAME",
                        help="Trigger name(s) from config.TRIGGERS "
                             "(default: all confluence_cross)")
    parser.add_argument("--symbol",  nargs="*", default=[], metavar="SYM",
                        help="Symbol name(s) (default: from trigger config)")
    parser.add_argument("--days",    type=int,   required=True,
                        help="Lookback in calendar days  e.g. 30")
    parser.add_argument("--tp",      type=float, default=None,
                        help="fixed: take-profit pts (required)  |  "
                             "trail_ema: trail gap pts (required)  |  "
                             "trail_ind: trail gap pts (optional — omit for pure indicator exit)")
    parser.add_argument("--sl",      type=float, default=None,
                        help="Stop-loss pts (required for fixed; optional hard SL for trail modes)")
    parser.add_argument("--entry",     choices=["5m_cross", "close", "next_open"],
                        default="5m_cross",
                        help="5m_cross: enter at first 5m candle inside 15m window that "
                             "touched the indicator (default, most accurate)  "
                             "close: 15m signal-candle close  "
                             "next_open: next 15m candle open")
    parser.add_argument("--exit-mode", choices=["fixed", "trail_ema", "trail_ind"],
                        default="fixed",
                        help="fixed: fixed TP+SL (--sl required)  "
                             "trail_ema: trail gap + EMA20 close (--sl optional)  "
                             "trail_ind: trail gap + trigger indicator close (--sl optional)")
    parser.add_argument("--mode",      choices=["intraday", "positional"], default="intraday",
                        help="intraday: exit same day on 5m candles  "
                             "positional: hold across days on 1d candles  "
                             "(default: intraday)")
    parser.add_argument("--hold-days", type=int, default=10, metavar="N",
                        help="Positional mode: max days to hold before force-exit "
                             "(default: 10)")
    args = parser.parse_args()

    if args.exit_mode == "fixed" and (args.tp is None or args.sl is None):
        parser.error("--tp and --sl are both required for --exit-mode fixed")
    if args.exit_mode == "trail_ema" and args.tp is None:
        parser.error("--tp (trail gap) is required for --exit-mode trail_ema")

    names = args.trigger or [t["name"] for t in TRIGGERS if t["type"] == "confluence_cross"]
    run_backtest(names, args.symbol, args.days, args.tp, args.sl,
                 args.entry, args.mode, args.hold_days, args.exit_mode)
