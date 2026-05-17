"""
Drishti — Daily Pre-Market Analysis for NIFTY
==============================================
Generates a next-day outlook by combining:
  • 1d candles  — primary trend (Supertrend, EMA 20/50/200, RSI 14, ATR 14)
  • 15m candles — end-of-day momentum (Supertrend, EMA 9/21, RSI 14)
  • Options chain — PCR, Max Pain, OI walls (via Upstox OptionsApi)
  • India VIX — via yfinance

Entry point:  run_daily_analysis()
Called from   live/poller.py at 08:30 IST each trading day.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_ta as ta
import yfinance as yf

from db.queries import get_candles
from live.alert import send_telegram, _h
from live.expiry import expiry_cache

IST   = ZoneInfo("Asia/Kolkata")
_DIVL = "━" * 36
_DIV  = "─" * 36

NIFTY_SYMBOL    = "NIFTY50"
NIFTY_IKEY      = "NSE_INDEX|Nifty 50"
NIFTY_YF_TICKER = "^NSEI"
VIX_YF_TICKER   = "^INDIAVIX"


# ─────────────────────────────────────────────────────────
# Indicator helpers
# ─────────────────────────────────────────────────────────

def _supertrend(df: pd.DataFrame, period: int = 7, multiplier: float = 3.0) -> dict:
    st = ta.supertrend(df["high"], df["low"], df["close"],
                       length=period, multiplier=multiplier)
    st_col  = next(c for c in st.columns
                   if c.startswith("SUPERT_") and "_d" not in c and "_s" not in c and "_l" not in c)
    std_col = next(c for c in st.columns if c.startswith("SUPERTd_"))
    val = float(st[st_col].iloc[-1])
    direction = int(st[std_col].iloc[-1])   # 1 = bullish, -1 = bearish
    return {"value": round(val, 1), "bullish": direction == 1}


def _ema(df: pd.DataFrame, period: int) -> float:
    return round(float(ta.ema(df["close"], length=period).iloc[-1]), 1)


def _rsi(df: pd.DataFrame, period: int = 14) -> float:
    return round(float(ta.rsi(df["close"], length=period).iloc[-1]), 1)


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    atr = ta.atr(df["high"], df["low"], df["close"], length=period)
    return round(float(atr.iloc[-1]), 1)


def _swing_levels(df: pd.DataFrame, lookback: int = 20) -> dict:
    recent = df.tail(lookback)
    return {
        "high": round(float(recent["high"].max()), 1),
        "low":  round(float(recent["low"].min()),  1),
    }


# ─────────────────────────────────────────────────────────
# India VIX via yfinance
# ─────────────────────────────────────────────────────────

def _fetch_vix() -> float | None:
    try:
        df = yf.download(VIX_YF_TICKER, period="5d", interval="1d",
                         progress=False, auto_adjust=True)
        if df.empty:
            return None
        close = df["Close"]
        # yfinance may return MultiIndex columns — flatten to Series
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        return round(float(close.dropna().iloc[-1]), 2)
    except Exception as e:
        print(f"  [daily_analysis]  VIX fetch failed: {e}", flush=True)
        return None


# ─────────────────────────────────────────────────────────
# Options chain — PCR, Max Pain, OI walls
# ─────────────────────────────────────────────────────────

def _fetch_options_data(expiry: date) -> dict | None:
    """
    Fetch option chain for NIFTY via Upstox OptionsApi.
    Returns PCR, max pain strike, top call OI strike, top put OI strike.
    """
    try:
        import upstox_client
        from config import UPSTOX_ACCESS_TOKEN
        if not UPSTOX_ACCESS_TOKEN:
            return None

        cfg = upstox_client.Configuration()
        cfg.access_token = UPSTOX_ACCESS_TOKEN
        api = upstox_client.OptionsApi(upstox_client.ApiClient(cfg))

        expiry_str = expiry.strftime("%Y-%m-%d")
        resp = api.get_put_call_option_chain(NIFTY_IKEY, expiry_str)

        if not resp or not resp.data:
            return None

        rows = resp.data   # list of PutCallOptionChainData

        total_call_oi = 0
        total_put_oi  = 0
        oi_by_strike: dict[float, dict] = {}

        for row in rows:
            strike = row.strike_price
            if strike is None:
                continue

            call_oi = 0
            put_oi  = 0

            if row.call_options and row.call_options.market_data:
                call_oi = int(row.call_options.market_data.oi or 0)
            if row.put_options and row.put_options.market_data:
                put_oi  = int(row.put_options.market_data.oi or 0)

            total_call_oi += call_oi
            total_put_oi  += put_oi
            oi_by_strike[strike] = {"call": call_oi, "put": put_oi}

        if total_call_oi == 0 and total_put_oi == 0:
            return None

        pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi else None

        # Max Pain — strike where total options loss (for buyers) is maximum
        # = minimize total premium paid out by sellers = minimize total loss for option writers
        # Standard: for each strike K, sum losses of all calls (if spot > K, call loses K-spot)
        # and puts (if spot < K, put loses spot-K). Max pain = strike with minimum total loss.
        strikes = sorted(oi_by_strike.keys())
        pain: dict[float, float] = {}
        for k in strikes:
            loss = 0.0
            for s, oi in oi_by_strike.items():
                # Call writers lose if settlement > strike
                if k > s:
                    loss += oi["call"] * (k - s)
                # Put writers lose if settlement < strike
                if k < s:
                    loss += oi["put"] * (s - k)
            pain[k] = loss
        max_pain_strike = min(pain, key=pain.__getitem__) if pain else None

        # Top OI walls
        top_call = max(oi_by_strike, key=lambda s: oi_by_strike[s]["call"]) if oi_by_strike else None
        top_put  = max(oi_by_strike, key=lambda s: oi_by_strike[s]["put"])  if oi_by_strike else None

        return {
            "pcr":           pcr,
            "max_pain":      int(max_pain_strike) if max_pain_strike else None,
            "call_oi_wall":  int(top_call) if top_call else None,
            "put_oi_wall":   int(top_put)  if top_put  else None,
            "total_call_oi": total_call_oi,
            "total_put_oi":  total_put_oi,
        }
    except Exception as e:
        print(f"  [daily_analysis]  options chain fetch failed: {e}", flush=True)
        return None


# ─────────────────────────────────────────────────────────
# Bias logic
# ─────────────────────────────────────────────────────────

def _bias(d1: dict, m15: dict, opts: dict | None, vix: float | None) -> str:
    """
    Rule-based bias paragraph combining 1d and 15m signals.
    Returns a plain string (HTML escaped by caller).
    """
    d1_bull  = d1["supertrend"]["bullish"]
    m15_bull = m15["supertrend"]["bullish"]
    close    = d1["close"]

    above_ema20  = close > d1["ema20"]
    above_ema50  = close > d1["ema50"]
    above_ema200 = close > d1["ema200"]
    rsi_1d       = d1["rsi"]
    rsi_15m      = m15["rsi"]

    # Count bullish signals
    bull_signals = sum([
        d1_bull, m15_bull,
        above_ema20, above_ema50, above_ema200,
        rsi_1d > 50, rsi_15m > 50,
    ])

    if d1_bull and m15_bull:
        if rsi_1d > 70:
            bias = "Both timeframes bullish but RSI overbought — upside limited; watch for profit-booking near resistance."
        else:
            bias = "Both timeframes aligned bullish. Dips likely to be bought; focus on support holds for long entries."
    elif d1_bull and not m15_bull:
        bias = (f"Daily trend bullish but 15m closed bearish (RSI {rsi_15m:.0f}). "
                f"Wait for 15m to turn up or watch {_fmt_lvl(m15['support1'])} support on open.")
    elif not d1_bull and m15_bull:
        bias = (f"Daily trend bearish — 15m recovery looks counter-trend. "
                f"Rallies may face resistance near {_fmt_lvl(d1['ema20'])} (EMA20). Sell-on-rise bias.")
    else:
        bias = "Both timeframes bearish. Bounces likely to fade; sell-on-rise or wait for trend reversal confirmation."

    # VIX addendum
    if vix is not None:
        if vix > 20:
            bias += f" VIX at {vix} — elevated; expect volatile swings, wider stops."
        elif vix < 13:
            bias += f" VIX at {vix} — low/complacent; sharp moves possible if sentiment shifts."

    # PCR addendum
    if opts and opts.get("pcr"):
        pcr = opts["pcr"]
        if pcr > 1.3:
            bias += f" PCR {pcr} — heavy put writing suggests strong support below."
        elif pcr < 0.8:
            bias += f" PCR {pcr} — call-heavy; bears in control, use rallies to sell."

    return bias


def _fmt_lvl(v: float) -> str:
    return f"{int(v):,}"


def _pcr_sentiment(pcr: float | None) -> str:
    if pcr is None:
        return "—"
    if pcr >= 1.3:
        return f"{pcr}  (strongly bullish)"
    if pcr >= 1.0:
        return f"{pcr}  (mildly bullish)"
    if pcr >= 0.8:
        return f"{pcr}  (neutral)"
    return f"{pcr}  (bearish)"


def _vix_label(vix: float | None) -> str:
    if vix is None:
        return "—"
    if vix < 13:
        label = "low — complacent"
    elif vix < 18:
        label = "normal — calm"
    elif vix < 25:
        label = "elevated — volatile"
    else:
        label = "high — fearful"
    return f"{vix}  ({label})"


def _st_label(st: dict) -> str:
    arrow = "▲" if st["bullish"] else "▼"
    trend = "BULLISH" if st["bullish"] else "BEARISH"
    return f"{arrow} {trend}  (line @ {_fmt_lvl(st['value'])})"


def _ema_line(label: str, ema_val: float, close: float) -> str:
    tick = "✅" if close > ema_val else "❌"
    return f"{label:<10}: {_fmt_lvl(ema_val)}   {tick} {'above' if close > ema_val else 'below'}"


def _rsi_label(rsi: float) -> str:
    if rsi >= 70:
        zone = "overbought"
    elif rsi >= 55:
        zone = "bullish"
    elif rsi >= 45:
        zone = "neutral"
    elif rsi >= 30:
        zone = "bearish"
    else:
        zone = "oversold"
    return f"{rsi}  — {zone}"


# ─────────────────────────────────────────────────────────
# Main analysis builder
# ─────────────────────────────────────────────────────────

def build_analysis() -> dict:
    """
    Compute all data points. Returns a structured dict.
    Raises on fatal errors (not enough candles, etc.).
    """
    # ── 1D candles ──────────────────────────────────────
    df1d = get_candles(NIFTY_SYMBOL, "1d", limit=300)
    if df1d.empty or len(df1d) < 50:
        raise ValueError("Not enough 1d candles for NIFTY50. Run: python main.py bootstrap")

    close_1d = float(df1d["close"].iloc[-1])
    prev_open = float(df1d["open"].iloc[-1])
    high_1d   = float(df1d["high"].iloc[-1])
    low_1d    = float(df1d["low"].iloc[-1])
    prev_close_2d = float(df1d["close"].iloc[-2])   # day before last close
    day_chg_pct = round((close_1d - prev_close_2d) / prev_close_2d * 100, 2)

    week_close  = float(df1d["close"].iloc[-6]) if len(df1d) >= 6 else None
    week_chg    = round((close_1d - week_close) / week_close * 100, 2) if week_close else None

    st_1d   = _supertrend(df1d)
    ema20   = _ema(df1d, 20)
    ema50   = _ema(df1d, 50)
    ema200  = _ema(df1d, 200)
    rsi_1d  = _rsi(df1d, 14)
    atr_1d  = _atr(df1d, 14)
    swing   = _swing_levels(df1d, 20)

    # Key resistance/support from EMAs and swings
    res_levels = sorted({swing["high"], round(ema20 + 50, -2), round(ema50 + 50, -2)})
    sup_levels = sorted({swing["low"],  round(ema20 - 50, -2), round(ema50 - 50, -2)})

    d1_data = {
        "close":      close_1d,
        "open":       prev_open,
        "high":       high_1d,
        "low":        low_1d,
        "day_chg":    day_chg_pct,
        "week_chg":   week_chg,
        "supertrend": st_1d,
        "ema20":      ema20,
        "ema50":      ema50,
        "ema200":     ema200,
        "rsi":        rsi_1d,
        "atr":        atr_1d,
        "swing":      swing,
        "resistance1": res_levels[-1] if res_levels else swing["high"],
        "resistance2": res_levels[-2] if len(res_levels) >= 2 else None,
        "support1":    sup_levels[0]  if sup_levels else swing["low"],
        "support2":    sup_levels[1]  if len(sup_levels) >= 2 else None,
    }

    # ── 15M candles ─────────────────────────────────────
    df15 = get_candles(NIFTY_SYMBOL, "15m", limit=200)
    if df15.empty or len(df15) < 30:
        raise ValueError("Not enough 15m candles for NIFTY50.")

    last_15m = df15.iloc[-1]
    st_15m   = _supertrend(df15)
    ema9     = _ema(df15, 9)
    ema21    = _ema(df15, 21)
    rsi_15m  = _rsi(df15, 14)
    swing15  = _swing_levels(df15, 26)   # ~6.5h of 15m candles = last session

    m15_data = {
        "close":      float(last_15m["close"]),
        "open":       float(last_15m["open"]),
        "high":       float(last_15m["high"]),
        "low":        float(last_15m["low"]),
        "candle_ts":  str(last_15m["ts"]),
        "supertrend": st_15m,
        "ema9":       ema9,
        "ema21":      ema21,
        "rsi":        rsi_15m,
        "support1":   swing15["low"],
        "support2":   round(swing15["low"] - atr_1d * 0.5, 1),
        "resistance1": swing15["high"],
    }

    # ── Options chain ────────────────────────────────────
    try:
        expiry_cache.refresh()
        weekly_expiry = expiry_cache.pick("NIFTY50", "weekly", 0)
    except Exception:
        weekly_expiry = None

    opts_data = None
    if weekly_expiry:
        opts_data = _fetch_options_data(weekly_expiry)

    # ── India VIX ────────────────────────────────────────
    vix = _fetch_vix()

    return {
        "d1":           d1_data,
        "m15":          m15_data,
        "opts":         opts_data,
        "vix":          vix,
        "weekly_expiry": weekly_expiry,
        "generated_at": datetime.now(timezone.utc).astimezone(IST),
    }


# ─────────────────────────────────────────────────────────
# Telegram message formatter
# ─────────────────────────────────────────────────────────

def format_report(a: dict) -> str:
    d1   = a["d1"]
    m15  = a["m15"]
    opts = a["opts"]
    vix  = a["vix"]
    exp  = a["weekly_expiry"]
    ts   = a["generated_at"]

    close    = d1["close"]
    day_chg  = d1["day_chg"]
    chg_icon = "🟢" if day_chg >= 0 else "🔴"
    week_str = (f"  |  Week: {'+' if d1['week_chg'] >= 0 else ''}{d1['week_chg']}%"
                if d1["week_chg"] is not None else "")
    exp_str  = exp.strftime("%-d %b %Y") if exp else "—"
    days_to_exp = (exp - date.today()).days if exp else None
    exp_days = f"  ({days_to_exp}d)" if days_to_exp is not None else ""

    bias_text = _bias(d1, m15, opts, vix)

    # ── Last 15m candle timestamp ─────────────────────────
    try:
        raw_ts = m15["candle_ts"]
        if hasattr(raw_ts, "astimezone"):          # already a tz-aware Timestamp
            candle_ts = raw_ts.astimezone(IST).strftime("%H:%M IST")
        else:
            candle_ts = datetime.strptime(
                str(raw_ts).replace("Z", "+00:00"), "%Y-%m-%dT%H:%M:%S%z"
            ).astimezone(IST).strftime("%H:%M IST")
    except Exception:
        candle_ts = "—"

    lines = [
        _DIVL,
        f"📊  <b>NIFTY  —  {ts.strftime('%-d %b %Y')} Pre-Market</b>",
        _DIVL,
        "",
        f"Close  : <b>₹{_fmt_lvl(close)}</b>   {chg_icon} {'+' if day_chg >= 0 else ''}{day_chg}%{week_str}",
        f"Range  : {_fmt_lvl(d1['low'])}  –  {_fmt_lvl(d1['high'])}",
        "",
        f"<b>── Daily (1D) Trend {'─'*14}</b>",
        f"Supertrend : {_st_label(d1['supertrend'])}",
        _ema_line("EMA 20", d1["ema20"], close),
        _ema_line("EMA 50", d1["ema50"], close),
        _ema_line("EMA 200", d1["ema200"], close),
        f"RSI 14     : {_rsi_label(d1['rsi'])}",
        f"ATR 14     : {d1['atr']} pts  (±{int(d1['atr'])} expected range)",
        "",
        f"<b>── Daily Key Levels {'─'*13}</b>",
        f"Resistance : {_fmt_lvl(d1['resistance1'])}"
        + (f"  |  {_fmt_lvl(d1['resistance2'])}" if d1["resistance2"] else ""),
        f"Support    : {_fmt_lvl(d1['support1'])}"
        + (f"  |  {_fmt_lvl(d1['support2'])}" if d1["support2"] else ""),
        f"20d High   : {_fmt_lvl(d1['swing']['high'])}  |  20d Low : {_fmt_lvl(d1['swing']['low'])}",
        "",
        f"<b>── 15-Min  ({candle_ts} close) {'─'*8}</b>",
        f"Supertrend : {_st_label(m15['supertrend'])}",
        f"EMA 9      : {_fmt_lvl(m15['ema9'])}   "
        + ("✅ above" if m15["close"] > m15["ema9"]  else "❌ below"),
        f"EMA 21     : {_fmt_lvl(m15['ema21'])}   "
        + ("✅ above" if m15["close"] > m15["ema21"] else "❌ below"),
        f"RSI 14     : {_rsi_label(m15['rsi'])}",
        f"Session Hi : {_fmt_lvl(m15['resistance1'])}  |  Session Lo : {_fmt_lvl(m15['support1'])}",
    ]

    # Options block
    if opts:
        lines += [
            "",
            f"<b>── Options  (Expiry: {exp_str}{exp_days}) {'─'*4}</b>",
            f"PCR        : {_pcr_sentiment(opts.get('pcr'))}",
            f"Max Pain   : {_fmt_lvl(opts['max_pain'])}" if opts.get("max_pain") else "Max Pain   : —",
            f"Call OI wall: {_fmt_lvl(opts['call_oi_wall'])} CE" if opts.get("call_oi_wall") else "Call OI wall: —",
            f"Put OI wall : {_fmt_lvl(opts['put_oi_wall'])} PE"  if opts.get("put_oi_wall")  else "Put OI wall : —",
        ]
    else:
        lines += ["", f"Expiry: {exp_str}{exp_days}  |  Options data unavailable"]

    # VIX + Bias
    lines += [
        "",
        f"<b>── Volatility {'─'*20}</b>",
        f"India VIX  : {_vix_label(vix)}",
        "",
        f"<b>── Bias {'─'*26}</b>",
        f"<i>{_h(bias_text)}</i>",
        "",
        _DIVL,
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────

def run_daily_analysis():
    """
    Build and send the pre-market analysis to Telegram.
    Called from the poller at 08:30 IST each trading day.
    """
    print("  Running daily NIFTY analysis...", flush=True)
    try:
        analysis = build_analysis()
        msg      = format_report(analysis)
        send_telegram(msg)
        print("  Daily analysis sent.", flush=True)
    except Exception as e:
        print(f"  [daily_analysis]  failed: {e}", flush=True)
