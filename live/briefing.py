"""
Day-start and end-of-day briefing messages sent via Telegram.
"""

from datetime import date, timedelta, datetime, timezone
from math import gcd
from functools import reduce
from zoneinfo import ZoneInfo

from live.alert import send_telegram, _h
from live.holidays import is_trading_day

IST  = ZoneInfo("Asia/Kolkata")
_DIV = "─" * 32

MORNING_QUOTES = [
    ("The stock market is a device for transferring money from the impatient to the patient.", "Warren Buffett"),
    ("In investing, what is comfortable is rarely profitable.", "Robert Arnott"),
    ("The market is a pendulum that forever swings between unsustainable optimism and unjustified pessimism.", "Benjamin Graham"),
    ("Risk comes from not knowing what you are doing.", "Warren Buffett"),
    ("The four most dangerous words in investing are: 'this time it's different.'", "Sir John Templeton"),
    ("Price is what you pay. Value is what you get.", "Warren Buffett"),
    ("Know what you own, and know why you own it.", "Peter Lynch"),
    ("The individual investor should act consistently as an investor and not as a speculator.", "Benjamin Graham"),
    ("Opportunities come infrequently. When it rains gold, put out the bucket, not the thimble.", "Warren Buffett"),
    ("An investment in knowledge pays the best interest.", "Benjamin Franklin"),
    ("Be fearful when others are greedy, and greedy when others are fearful.", "Warren Buffett"),
    ("The best time to plant a tree was 20 years ago. The second best time is now.", "Chinese Proverb"),
]

EVENING_QUOTES = [
    ("The goal of a successful trader is to make the best trades. Money is secondary.", "Alexander Elder"),
    ("Markets are never wrong; opinions often are.", "Jesse Livermore"),
    ("Every day is a new opportunity to improve yourself.", "Unknown"),
    ("Do not be embarrassed by your failures, learn from them and start again.", "Richard Branson"),
    ("I will tell you how to become rich. Close the doors. Be fearful when others are greedy. Be greedy when others are fearful.", "Warren Buffett"),
    ("The most important quality for an investor is temperament, not intellect.", "Warren Buffett"),
    ("The stock market is filled with individuals who know the price of everything, but the value of nothing.", "Philip Fisher"),
    ("In the short run, the market is a voting machine, but in the long run, it is a weighing machine.", "Benjamin Graham"),
    ("It's not whether you're right or wrong, but how much money you make when you're right and how much you lose when you're wrong.", "George Soros"),
    ("Successful investing is about managing risk, not avoiding it.", "Benjamin Graham"),
]


def _pick_quote(quotes: list, offset: int = 0) -> tuple[str, str]:
    idx = (date.today().timetuple().tm_yday + offset) % len(quotes)
    return quotes[idx]


def _tomorrow_holiday_line() -> str | None:
    """Return a holiday warning line if tomorrow is not a trading day, else None."""
    tomorrow = date.today() + timedelta(days=1)
    if is_trading_day(tomorrow):
        return None
    label = tomorrow.strftime("%A, %d %b %Y")
    nxt   = tomorrow + timedelta(days=1)
    while not is_trading_day(nxt) and (nxt - tomorrow).days < 10:
        nxt += timedelta(days=1)
    return (f"⚠️ <b>{label}</b> — NSE Market Holiday\n"
            f"         Next trading day: <b>{nxt.strftime('%d %b')}</b>")


def send_morning_brief():
    """
    Send day-start brief — called after startup tasks complete.
    Only fires if the service started before 09:30 IST (normal morning startup).
    Silently skipped on mid-session restarts.
    """
    now = datetime.now(timezone.utc).astimezone(IST)
    if now.hour > 9 or (now.hour == 9 and now.minute >= 30):
        print(f"  [morning brief]  skipped — started at {now.strftime('%H:%M IST')}, "
              f"not a morning startup", flush=True)
        return

    q, a = _pick_quote(MORNING_QUOTES)
    holiday_line = _tomorrow_holiday_line()

    lines = [
        "🌅 <b>Good Morning — Market Brief</b>",
        _DIV,
        f"📅 <b>{now.strftime('%A, %d %b %Y')}</b>",
        "",
        f'💡 <i>"{q}"</i>',
        f"   — <i>{a}</i>",
        "",
    ]
    if holiday_line:
        lines += [_DIV, f"📆 Tomorrow:  {holiday_line}", ""]
    lines += [_DIV, "Have a great trading session! 📈"]
    send_telegram("\n".join(lines))


def _base_positions(legs: list[dict]) -> int:
    """GCD of all leg lots — the number of positions entered."""
    lots = [l["lots"] for l in legs if l.get("lots", 0) > 0]
    return reduce(gcd, lots) if lots else 1


def _leg_pnl_line(leg: dict, close_price, n_pos: int = 1) -> str:
    side       = leg["side"]
    itype      = leg["instrument_type"]
    strike_str = f"{int(leg['strike']):,} " if leg.get("strike") else ""
    base_lots  = leg["lots"] // n_pos
    lots_str   = f"{base_lots}L"
    entry_p    = leg["price"] or 0
    if close_price is not None:
        return f"   {side}  {strike_str}{itype}  {lots_str}  {entry_p:,.0f} → {close_price:,.0f}"
    return f"   {side}  {strike_str}{itype}  {lots_str}  @ {entry_p:,.0f}"


def _calc_open_pnl(entry_legs: list, current_prices: dict):
    total, has_data = 0.0, False
    for leg in entry_legs:
        cur_price = current_prices.get(leg.get("instrument_key"))
        if cur_price is None or leg["price"] is None:
            continue
        qty = (leg["lots"] * leg["lot_size"]) if leg["lot_size"] else leg["lots"]
        total += (leg["price"] - cur_price) * qty if leg["side"] == "SELL" \
            else (cur_price - leg["price"]) * qty
        has_data = True
    return total if has_data else None


def _calc_realized_pnl(entry_legs: list, close_legs: list):
    total, has_data = 0.0, False
    for leg in entry_legs:
        cl = next((l for l in close_legs
                   if l.get("instrument_key") == leg.get("instrument_key")), None)
        if cl is None or leg["price"] is None or cl["price"] is None:
            continue
        qty = (leg["lots"] * leg["lot_size"]) if leg["lot_size"] else leg["lots"]
        total += (leg["price"] - cl["price"]) * qty if leg["side"] == "SELL" \
            else (cl["price"] - leg["price"]) * qty
        has_data = True
    return total if has_data else None


def _trade_entry_date(t: dict, today_ist: date) -> str:
    try:
        entry_utc = datetime.strptime(t["entry_time"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        entry_ist = entry_utc.astimezone(ZoneInfo("Asia/Kolkata"))
        if entry_ist.date() == today_ist:
            return entry_ist.strftime("%H:%M IST")
        return entry_ist.strftime("%d %b")
    except Exception:
        return "—"


def _trade_summary_block(today_ist: date) -> str:
    """Build HTML trade summary for EOD brief."""
    from db.queries import get_all_open_trades, get_today_closed_trades, get_trade_legs

    open_trades  = get_all_open_trades()
    closed_today = get_today_closed_trades(today_ist)

    if not open_trades and not closed_today:
        return "📂 No active or recently closed trades today."

    # Pre-load entry legs for open trades; collect instrument keys for LTP batch
    all_ikeys: set[str] = set()
    for t in open_trades:
        legs = get_trade_legs(t["id"])
        t["_entry_legs"] = [l for l in legs if l["action"] == "entry"]
        all_ikeys.update(l["instrument_key"] for l in t["_entry_legs"]
                         if l.get("instrument_key"))

    current_prices: dict[str, float] = {}
    if all_ikeys:
        try:
            from live.upstox_client import get_ltp
            current_prices = get_ltp(list(all_ikeys))
        except Exception as e:
            print(f"  [EOD brief]  LTP fetch failed: {e}", flush=True)

    lines = [f"📂 <b>Trade Summary</b>"]

    # --- Open trades ---
    for t in open_trades:
        entry_legs = t["_entry_legs"]
        n_pos      = _base_positions(entry_legs)
        pnl        = _calc_open_pnl(entry_legs, current_prices)
        since      = _trade_entry_date(t, today_ist)
        pos_tag    = f"  ×{n_pos} pos" if n_pos > 1 else ""
        lines.append(
            f"\n🟢 <b>OPEN</b>  ·  id={t['id']}  {_h(t['symbol'])}  "
            f"<i>{_h(t['trigger_name'])}</i>  (since {since}){pos_tag}"
        )
        for leg in entry_legs:
            cur_p = current_prices.get(leg.get("instrument_key"))
            lines.append(_leg_pnl_line(leg, cur_p, n_pos))

        pnl_str    = f"<b>₹{pnl:+,.0f}</b>" if pnl is not None else "<i>P&L unavailable</i>"
        margin_per = (t["margin_required"] / n_pos) if t.get("margin_required") else None
        margin_str = (f"  |  Margin/pos ₹{margin_per:,.0f}" if margin_per else "")
        lines.append(f"   {pnl_str}{margin_str}")

    # --- Today's exited / rolled trades ---
    for t in closed_today:
        all_legs    = get_trade_legs(t["id"])
        entry_legs  = [l for l in all_legs if l["action"] == "entry"]
        close_legs  = [l for l in all_legs if l["action"] in ("exit", "rollover_out")]
        n_pos       = _base_positions(entry_legs)
        pnl         = _calc_realized_pnl(entry_legs, close_legs)
        since       = _trade_entry_date(t, today_ist)
        pos_tag     = f"  ×{n_pos} pos" if n_pos > 1 else ""

        if t["status"] == "rolled":
            icon, word = "🔄", "ROLLED"
        else:
            icon, word = "✅", "EXITED"

        lines.append(
            f"\n{icon} <b>{word}</b>  ·  id={t['id']}  {_h(t['symbol'])}  "
            f"<i>{_h(t['trigger_name'])}</i>  (entered {since}){pos_tag}"
        )
        for leg in entry_legs:
            cl = next((l for l in close_legs
                       if l.get("instrument_key") == leg.get("instrument_key")), None)
            lines.append(_leg_pnl_line(leg, cl["price"] if cl else None, n_pos))

        pnl_str = f"<b>₹{pnl:+,.0f}</b>" if pnl is not None else "<i>P&L unavailable</i>"
        lines.append(f"   {pnl_str}")

    return "\n".join(lines)


def send_eod_brief(alerts: list[dict]):
    """Send end-of-day summary — called at 16:00 IST after EOD tasks."""
    now  = datetime.now(timezone.utc).astimezone(IST)
    q, a = _pick_quote(EVENING_QUOTES, offset=1)

    # Summarise today's alerts
    if alerts:
        fired = {}
        for sig in alerts:
            key = f"{sig['symbol']} — {sig['trigger_name']}"
            fired[key] = fired.get(key, 0) + 1
        alert_lines = [f"   • {k}  ×{v}" if v > 1 else f"   • {k}"
                       for k, v in fired.items()]
        alert_block = (
            f"📊 <b>{len(alerts)} alert(s) fired today:</b>\n"
            + "\n".join(alert_lines)
        )
    else:
        alert_block = "📊 No triggers fired today — quiet session."

    # Trade summary
    try:
        trade_block = _trade_summary_block(now.date())
    except Exception as e:
        print(f"  [EOD brief]  trade summary failed: {e}", flush=True)
        trade_block = None

    holiday_line = _tomorrow_holiday_line()
    lines = [
        f"🌆 <b>Market Closed — {now.strftime('%d %b %Y')}</b>",
        _DIV,
        alert_block,
        "",
    ]
    if trade_block:
        lines += [_DIV, trade_block, ""]
    lines += [
        _DIV,
        f'💡 <i>"{q}"</i>',
        f"   — <i>{a}</i>",
        "",
    ]
    if holiday_line:
        lines += [_DIV, f"📆 Tomorrow:  {holiday_line}", ""]
    lines.append("Good night! Rest well. 🌙")
    send_telegram("\n".join(lines))
