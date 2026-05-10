"""
Day-start and end-of-day briefing messages sent via Telegram.
"""

from datetime import date, timedelta, datetime, timezone
from zoneinfo import ZoneInfo

from live.alert import send_telegram
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


def _tomorrow_line() -> str:
    tomorrow = date.today() + timedelta(days=1)
    label    = tomorrow.strftime("%A, %d %b %Y")
    if is_trading_day(tomorrow):
        return f"✅ <b>{label}</b> — Trading Day"
    else:
        # Keep looking ahead to find the next trading day
        nxt = tomorrow + timedelta(days=1)
        while not is_trading_day(nxt) and (nxt - tomorrow).days < 10:
            nxt += timedelta(days=1)
        nxt_label = nxt.strftime("%d %b")
        return (f"⚠️ <b>{label}</b> — NSE Market Holiday\n"
                f"         Next trading day: <b>{nxt_label}</b>")


def send_morning_brief(trigger_count: int):
    """Send day-start brief — called after startup tasks complete."""
    now  = datetime.now(timezone.utc).astimezone(IST)
    q, a = _pick_quote(MORNING_QUOTES)

    lines = [
        f"🌅 <b>Good Morning — Market Brief</b>",
        _DIV,
        f"📅 <b>{now.strftime('%A, %d %b %Y')}</b>",
        "",
        f'💡 <i>"{q}"</i>',
        f"   — <i>{a}</i>",
        "",
        _DIV,
        f"📆 Tomorrow:  {_tomorrow_line()}",
        "",
        f"🎯 <b>{trigger_count}</b> trigger(s) active — watching from 09:15 IST",
        _DIV,
        "Have a great trading session! 📈",
    ]
    send_telegram("\n".join(lines))


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

    lines = [
        f"🌆 <b>Market Closed — {now.strftime('%d %b %Y')}</b>",
        _DIV,
        alert_block,
        "",
        _DIV,
        f'💡 <i>"{q}"</i>',
        f"   — <i>{a}</i>",
        "",
        _DIV,
        f"📆 Tomorrow:  {_tomorrow_line()}",
        "",
        "Good night! Rest well. 🌙",
    ]
    send_telegram("\n".join(lines))
