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
    "CROSS UP":      ("↑", "Price crossed ABOVE"),
    "CROSS DOWN":    ("↓", "Price crossed BELOW"),
    "RSI OVERSOLD":  ("⚠️", "RSI dropped into oversold zone"),
    "RSI OVERBOUGHT":("⚠️", "RSI rose into overbought zone"),
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

def _format_signal(signal: dict) -> str:
    now_ist  = datetime.now(timezone.utc).astimezone(IST)
    time_str = now_ist.strftime("%d %b %Y  %H:%M IST")
    event    = signal["event"]
    icon, description = _EVENT_META.get(event, ("•", event))
    tf       = signal["timeframe"].upper()

    ind_label = {
        "supertrend_cross": "Supertrend",
        "ema_cross":        f"EMA{_ema_period(signal)}",
        "rsi_threshold":    "RSI",
    }.get(signal.get("trigger_type", ""), "Indicator")

    lines = [
        f'🔔 <b>{_h(signal["symbol"])}</b>  •  {_h(tf)}  •  {icon} <b>{_h(event)}</b>',
        _DIV,
        f"<i>{_h(description)}</i>",
        "",
        _row("LTP",        f"{signal['ltp']:,.2f}"),
        _row(ind_label,    f"{signal['indicator_val']:,.2f}"),
    ]

    if "st_dir" in signal:
        bias = "Bullish 🟢" if signal["st_dir"] == 1 else "Bearish 🔴"
        lines.append(_row("ST Bias", bias, bold_value=False))

    if "rsi_level" in signal:
        lines.append(_row("Threshold", str(signal["rsi_level"]), bold_value=False))

    lines += [
        "",
        _row("Trigger",  signal["trigger_name"],  bold_value=False),
        _row("Time",     time_str,                 bold_value=False),
    ]

    if signal.get("candle_ts") is not None:
        lines.append(_row("Candle", str(signal["candle_ts"])[:16] + " UTC", bold_value=False))

    trade_count = len(signal.get("trades", []))
    if trade_count:
        noun = "trade ideas" if trade_count > 1 else "trade idea"
        lines += ["", f"<i>{trade_count} {noun} follow below 👇</i>"]

    return "\n".join(lines)


def _format_trade(trade: dict, idx: int, total: int, symbol: str) -> str:
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
    trades = signal.get("trades", [])

    # Console
    print(f"\n{'='*54}")
    print(_format_signal(signal))
    for i, trade in enumerate(trades, 1):
        print(f"\n{_DIV}")
        print(_format_trade(trade, i, len(trades), signal["symbol"]))
    print(f"\n{'='*54}\n", flush=True)

    # Telegram — signal first, then one message per trade
    send_telegram(_format_signal(signal))
    for i, trade in enumerate(trades, 1):
        send_telegram(_format_trade(trade, i, len(trades), signal["symbol"]))


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
