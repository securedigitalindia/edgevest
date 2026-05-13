"""
Alert dispatcher.
Uses Telegram HTML parse mode (more reliable than Markdown for special chars).
Sends two types of messages:
  1. Signal alert  — what happened (always)
  2. Trade idea    — one message per trade suggestion
"""

import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

IST      = ZoneInfo("Asia/Kolkata")
_DIV     = "─" * 30
_DIV_MSG = "\n" + _DIV + "\n"

_EVENT_META = {
    "CROSS UP":        ("↑",  "Price crossed ABOVE"),
    "CROSS DOWN":      ("↓",  "Price crossed BELOW"),
    "RSI OVERSOLD":    ("⚠️", "RSI dropped into oversold zone"),
    "RSI OVERBOUGHT":  ("⚠️", "RSI rose into overbought zone"),
    "500-MULTI ENTRY":    ("📉", "Nifty crossed 500-level — short entry"),
    "500-MULTI EXIT":     ("🔺", "Short exit — Nifty fell 500 pts from entry"),
    "500-MULTI ROLLOVER": ("🔄", "Monthly expiry rollover — rolling short to next month"),
    "MANUAL ENTRY":       ("✍️", "Manual trade entry"),
}


def _h(text: str) -> str:
    """Escape HTML special characters."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _row(label: str, value: str, bold_value: bool = True) -> str:
    v = f"<b>{_h(value)}</b>" if bold_value else _h(value)
    return f"{_h(label):<12}{v}"


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def _fmt_candle_ts(candle_ts, timeframe: str) -> str:
    """Convert candle timestamp to IST. Intraday → HH:MM IST (DD Mon), daily+ → DD Mon YYYY."""
    if candle_ts is None:
        return "—"
    import pandas as pd
    ts = pd.Timestamp(candle_ts).tz_convert("Asia/Kolkata")
    if timeframe in ("5m", "15m", "1h"):
        return ts.strftime("%H:%M IST  (%d %b)")
    return ts.strftime("%d %b %Y  IST")


def _format_signal(signal: dict, alert_str: str) -> str:
    event     = signal["event"]
    icon, description = _EVENT_META.get(event, ("•", event))
    tf        = signal["timeframe"].upper()

    ind_label = {
        "supertrend_cross":   "Supertrend",
        "ema_cross":          f"EMA{_ema_period(signal)}",
        "rsi_threshold":      "RSI",
        "confluence_cross":   signal.get("cross_label", "Indicator"),
        "nifty_500_multiple": "500 Level",
    }.get(signal.get("trigger_type", ""), "Indicator")

    ltp        = signal["ltp"]
    ind        = signal["indicator_val"]
    diff       = ltp - ind
    prev_close = signal.get("prev_close")
    is_manual  = signal.get("trigger_type") == "manual"

    lines = [
        f'🔔 <b>{_h(signal["symbol"])}</b>  •  {_h(tf)}  •  {icon} <b>{_h(event)}</b>',
        _DIV,
        f"<i>{_h(description)}</i>",
        "",
    ]
    if not is_manual:
        lines.append(_row("CMP", f"{ltp:,.2f}"))
        if prev_close is not None:
            lines.append(_row("Prev Close", f"{prev_close:,.2f}", bold_value=False))
        lines += [
            _row(ind_label,  f"{ind:,.2f}"),
            _row("Diff",     f"{diff:+,.2f}", bold_value=False),
        ]
    else:
        lines.append(_row("Spot", f"{ltp:,.2f}", bold_value=False))

    if "st_dir" in signal:
        bias = "Bullish 🟢" if signal["st_dir"] == 1 else "Bearish 🔴"
        lines.append(_row("ST Bias", bias, bold_value=False))

    if "rsi_level" in signal:
        lines.append(_row("Threshold", str(signal["rsi_level"]), bold_value=False))

    if "entry_level" in signal:
        lines.append(_row("Entry @", f"{signal['entry_level']:,}", bold_value=False))
    if "exit_level" in signal:
        lines.append(_row("Exit @", f"{signal['exit_level']:,}", bold_value=False))

    confirmed_by = signal.get("confirmed_by", [])
    if confirmed_by:
        labels = {
            "supertrend_direction": "ST direction",
            "price_below_day_high": "below day high",
            "price_above_day_low":  "above day low",
        }
        confirmed_str = "  +  ".join(labels.get(c, c) for c in confirmed_by)
        lines.append(_row("Confirmed", confirmed_str, bold_value=False))

    lines += [
        "",
        _row("Trigger",   signal["trigger_name"],                                  bold_value=False),
        _row("Candle",    _fmt_candle_ts(signal.get("candle_ts"), signal["timeframe"]), bold_value=False),
        _row("Alert at",  alert_str,                                                bold_value=False),
    ]

    trade_count = len(signal.get("trades", []))
    if trade_count:
        noun = "trade ideas" if trade_count > 1 else "trade idea"
        lines += ["", f"<i>{trade_count} {noun} follow below 👇</i>"]

    return "\n".join(lines)


def _format_trade(trade: dict, idx: int, total: int, symbol: str, alert_str: str) -> str:
    header = (
        f'📋 <b>TRADE IDEA {idx}/{total}</b>  •  <b>{_h(symbol)}</b>'
        if total > 1 else
        f'📋 <b>TRADE IDEA</b>  •  <b>{_h(symbol)}</b>'
    )

    lines = [
        header,
        _DIV,
        f'<b>{_h(trade["title"])}</b>',
        "",
    ]

    for leg in trade["legs"]:
        icon = "🔴 SELL" if leg["action"] == "SELL" else "🟢 BUY "
        lines.append(f'{icon}  <b>{_h(leg["instrument"])}</b>')
        if leg.get("note"):
            lines.append(f'       <i>{_h(leg["note"])}</i>')
        lines.append("")

    lines += [
        _DIV,
        f'💡 <i>{_h(trade["rationale"])}</i>',
        "",
        _row("Alert at", alert_str, bold_value=False),
    ]

    return "\n".join(lines)


def _ema_period(signal: dict) -> str:
    for part in signal.get("trigger_name", "").split("_"):
        if part.startswith("EMA") and part[3:].isdigit():
            return part[3:]
    return ""


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def send_alert(signal: dict):
    trades     = signal.get("trades", [])
    alert_str  = datetime.now(timezone.utc).astimezone(IST).strftime("%d %b  %H:%M IST")
    sig_text   = _format_signal(signal, alert_str)
    trade_texts = [_format_trade(t, i, len(trades), signal["symbol"], alert_str)
                   for i, t in enumerate(trades, 1)]

    # Console
    print(f"\n{'='*54}")
    print(sig_text)
    for text in trade_texts:
        print(f"\n{_DIV}")
        print(text)
    print(f"\n{'='*54}\n", flush=True)

    # Telegram — signal first, then one message per trade
    send_telegram(sig_text)
    for text in trade_texts:
        send_telegram(text)


def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       text,
            "parse_mode": "HTML",
        }, timeout=8)
        if not resp.ok:
            print(f"  [Telegram error]  {resp.status_code}: {resp.text}", flush=True)
    except Exception as e:
        print(f"  [Telegram failed]  {e}", flush=True)
