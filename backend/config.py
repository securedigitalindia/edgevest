# ============================================================
#  Drishti — config.py
#  Single source of truth for all settings
# ============================================================

import os

# -----------------------------------------------------------
# Symbols
# -----------------------------------------------------------
# Each entry: (display_name, type). Upstox instrument key is resolved via
# UPSTOX_INSTRUMENT_KEYS[name] — see below.
# type: "equity" | "index"
SYMBOLS = [
    {"name": "NIFTY50",    "type": "index"},
    {"name": "BANKNIFTY",  "type": "index"},
    {"name": "RELIANCE",   "type": "equity"},
]

# -----------------------------------------------------------
# Credits
# -----------------------------------------------------------
SIGNUP_CREDITS = 99          # gems awarded to every new user on first login

# Refer & Earn — see docs/prd/refer-and-earn.md
REFERRAL_SIGNUP_BONUS_GEMS = 149  # gems awarded to a new user who signs up via a referral link (replaces SIGNUP_CREDITS for that signup)
REFERRAL_REWARD_GEMS       = 99   # gems awarded to the referrer once the referee's setup_done flips true

# -----------------------------------------------------------
# Daily NIFTY prediction games (auto-scheduled — live/poller.py)
# -----------------------------------------------------------
# Two price_prediction games run every trading day. Daily schedule (all IST,
# see live/poller.py's module docstring for the exact hook points):
#   GAME_NIFTY_OPEN_ENTRY_CUTOFF_IST (09:00) — close entries on last
#                             evening's open-game, create today's close-game
#   GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST (15:00) — close entries on today's
#                             close-game
#   16:00 (EOD sync)      — resolve BOTH games from that day's official
#                             candles_1d open/close, create tomorrow's
#                             open-game
# Both entry cutoffs are deliberately ~15min BEFORE the actual event they're
# predicting (market opens 09:15, NIFTY's real/effective close is 15:15 —
# not MARKET_CLOSE_IST's 15:30, confirmed by the user) — a safety margin so
# nobody can snipe a near-certain last-moment entry once the answer is
# effectively already known. Both are only resolved at 16:00 because
# candles_1d's official open/close columns don't exist in this system
# before that sync runs — resolving the open-game any earlier would mean
# grading it against an approximate live LTP snapshot instead of the same
# authoritative source used for close. See docs/prd/nifty-daily-prediction-games.md.
GAME_NIFTY_OPEN_REWARD_POOL   = 50   # credits — paid only if someone qualifies (see threshold)
GAME_NIFTY_OPEN_WIN_THRESHOLD = 10   # points — closest guess only wins if within this of the actual open
GAME_NIFTY_CLOSE_REWARD_POOL   = 50
GAME_NIFTY_CLOSE_WIN_THRESHOLD = 10
GAME_NIFTY_OPEN_ENTRY_CUTOFF_IST  = (9, 0)     # ~15min safety margin before MARKET_OPEN_IST (09:15)
CHAIN_DRAFT_CLEANUP_IST            = (9, 5)     # each trading day from this time: delete yesterday-and-older UNREVIEWED chain-trigger drafts (before the first 09:20 chain snapshot can fire)
GAME_NIFTY_CLOSE_ENTRY_CUTOFF_IST = (15, 0)    # ~15min safety margin before NIFTY's real close (15:15)

# -----------------------------------------------------------
# Database
# -----------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "drishti.db")

# -----------------------------------------------------------
# Timeframes
# -----------------------------------------------------------
# key            : internal name used for table suffix, also the Upstox
#                  unit/interval lookup key in bootstrap/upstox_loader.UPSTOX_TF_MAP
# bootstrap_days : how many days of history to seed on a full bootstrap
#                  (clamped to Upstox's own data floor per unit — see
#                  UPSTOX_TF_MAP's DATA_FLOOR — so 1d/1wk/1mo's 7300 days
#                  just means "as far back as Upstox has", currently Jan 2000)
# description    : human label

TIMEFRAMES = [
    {
        "key":            "1m",
        "bootstrap_days": 7,
        "description":    "1 Minute",
    },
    {
        "key":            "5m",
        "bootstrap_days": 60,
        "description":    "5 Minute",
    },
    {
        "key":            "15m",
        "bootstrap_days": 60,
        "description":    "15 Minute",
    },
    {
        "key":            "1h",
        "bootstrap_days": 730,
        "description":    "1 Hour",
    },
    {
        "key":            "1d",
        "bootstrap_days": 7300,
        "description":    "1 Day",
    },
    {
        "key":            "1wk",
        "bootstrap_days": 7300,
        "description":    "1 Week",
    },
    {
        "key":            "1mo",
        "bootstrap_days": 7300,
        "description":    "1 Month",
    },
]

# -----------------------------------------------------------
# Indicator parameters (not used yet — reserved for Phase 2)
# -----------------------------------------------------------
INDICATORS = {
    "ema_fast":          21,
    "ema_slow":          50,
    "rsi_period":        14,
    "supertrend_period": 10,
    "supertrend_mult":   3.0,
}

# -----------------------------------------------------------
# Sync settings
# -----------------------------------------------------------
# Delay (seconds) between Upstox chunk fetches during bootstrap/sync —
# Upstox's rate limits (50/sec, 500/min) are far higher than this needs,
# so this is just gentle pacing, not load-bearing throttling.
FETCH_DELAY_SECONDS = 0.25

# -----------------------------------------------------------
# Live polling
# -----------------------------------------------------------
# Set via:  export UPSTOX_ACCESS_TOKEN="your_daily_token"
# Tokens expire daily — regenerate from Upstox developer console each morning
UPSTOX_ACCESS_TOKEN = os.environ.get("UPSTOX_ACCESS_TOKEN", "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiJBVTMyNDciLCJqdGkiOiI2OWZmYzUyMGMxNmQyYzUwMmRlZGNjMWIiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlzRXh0ZW5kZWQiOnRydWUsImlhdCI6MTc3ODM2OTgyNCwiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxODA5OTg2NDAwfQ.5XUBrH0r87j7A5IDIYCVElwfxvKZ0zlhZNiz8eIuSVM")

# -----------------------------------------------------------
# Telegram alerts
# -----------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8663646998:AAHO7RO_1VmAxLhNEG-Dbj6fkqyN_Ge4dNI"
TELEGRAM_CHAT_ID   = "1080341401"

# Seconds between each LTP poll during market hours
POLL_INTERVAL_SECONDS = 5

# Time (IST) to auto-roll expiring legs on expiry day — before 15:30 settlement
AUTO_ROLL_TIME_IST = (14, 0)

# NSE market hours in IST
MARKET_OPEN_IST  = (9, 15)
MARKET_CLOSE_IST = (15, 30)

# -----------------------------------------------------------
# Trigger definitions
# -----------------------------------------------------------
# Each entry defines one signal condition.
# "symbols": "all"  → applies to every symbol in SYMBOLS above
# "symbols": ["NIFTY50"]  → specific symbols only
#
# Supported types:
#   supertrend_cross  — fires when LTP crosses the Supertrend line (up or down)
#   ema_cross         — fires when LTP crosses the EMA line (up or down)
#   rsi_threshold     — fires when RSI crosses below "below" or above "above"
#
# Optional fields:
#   "direction": "UP" or "DOWN"  → only fire on that crossing direction (cross triggers)
#   "trade": {"type": "<template>", "params": {...}}  → attach a trade suggestion to the alert

# All alert triggers removed 2026-09-22 — the previous definitions (EMA20 15m
# confluence, Supertrend 1d/1wk/1h, RSI14 1h oversold, NIFTY500_MULTI, EMA20 1d
# down-cross) are in git history at commit 0912c0c. The trigger machinery in
# live/triggers.py is untouched, so re-adding an entry here re-enables it.
# The poller still polls every symbol in SYMBOLS (ticks, candles, price cache,
# option-chain capture, EOD sync) with an empty list — see
# _build_all_triggers() in live/poller.py.
TRIGGERS = []

# -----------------------------------------------------------
# Option-chain triggers (live/chain_triggers.py)
# -----------------------------------------------------------
# Evaluated once per 5-min option_chain_5m snapshot; on fire they create a DRAFT
# trade (never an open one — publish it from the Dashboard's Draft Strategies panel).
def _calendar_ratio_trigger(name: str, itm_points: float, *, far_strike_offset: float = 400,
                             max_debit_pts: float | None = None, min_credit_pts: float | None = None,
                             near_lots: int = 1, far_lots: int = 2,
                             strike_step: float = 100, min_dte: int = 1, sides=("CE",),
                             symbol: str = "NIFTY50", risk_level: str = "high") -> dict:
    """
    One entry in the 1:2 calendar/diagonal family (live/chain_triggers.py, type
    "calendar_ratio_credit"): BUY near_lots @ K1 = base - itm_points on the nearest expiry
    with DTE > min_dte, SELL far_lots @ K2 = K1 + far_strike_offset on the next expiry after
    that. base = next strike_step above (CE) / below (PE) the futures price — itm_points=0
    is "no shift, nearest OTM strike"; itm_points > 0 pushes K1 that far into the money.
    Every variant tested on real data prices as a net DEBIT (near_lots*near_ltp -
    far_lots*far_ltp), never a credit, once far_strike_offset is a real gap. Caller must pass
    exactly one of max_debit_pts / min_credit_pts explicitly (no default here) — 2026-09-22:
    a silent default (previously max_debit_pts=25) meant 5 of 6 CHAIN_TRIGGERS entries never
    stated their own rule, which became confusing the moment one entry (OTM100) needed a
    genuinely different threshold shape (credit > 5, not debit < 25) — the rule for every
    trigger must be readable at its own CHAIN_TRIGGERS call site.
    """
    if (max_debit_pts is None) == (min_credit_pts is None):
        raise ValueError(f"{name}: pass exactly one of max_debit_pts or min_credit_pts")
    threshold = {"min_credit_pts": min_credit_pts} if min_credit_pts is not None else {"max_debit_pts": max_debit_pts}
    return {
        "name": name, "type": "calendar_ratio_credit", "symbol": symbol, "sides": list(sides),
        "strike_step": strike_step, "min_dte": min_dte, "near_lots": near_lots, "far_lots": far_lots,
        "itm_points": itm_points, "far_strike_offset": far_strike_offset,
        "risk_level": risk_level, **threshold,
    }


# Evaluated once per 5-min option_chain_5m snapshot; on fire they create a DRAFT trade
# (never an open one — publish it from the Dashboard's Draft Strategies panel). All three
# below are the same 1:2 calendar/diagonal shape (_calendar_ratio_trigger) at different
# itm_points — add a fourth by adding one more call, no other config duplication needed.
CHAIN_TRIGGERS = [
    # _calendar_ratio_trigger("NIFTY_CE_ITM400_RATIO_DIAG_1X2", itm_points=400, max_debit_pts=10),
    # _calendar_ratio_trigger("NIFTY_CE_ITM300_RATIO_DIAG_1X2", itm_points=300, max_debit_pts=25),
    # _calendar_ratio_trigger("NIFTY_CE_ITM200_RATIO_DIAG_1X2", itm_points=200, max_debit_pts=20),
    # _calendar_ratio_trigger("NIFTY_CE_ITM100_RATIO_DIAG_1X2", itm_points=100, max_debit_pts=15),
    # _calendar_ratio_trigger("NIFTY_CE_ITM0_RATIO_DIAG_1X2", itm_points=0, max_debit_pts=10),
    # OTM100 uses its own credit > 5 rule (confirmed 2026-09-22), unlike the other five which
    # fire on debit < 25 — on real data OTM100 has priced as a debit too (14.1 on the reference
    # snapshot), so this rule is expected to rarely fire, same caveat as the PE ratio diagonal.
    # _calendar_ratio_trigger("NIFTY_CE_OTM100_RATIO_DIAG_1X2", itm_points=-100, min_credit_pts=5),
    # _calendar_ratio_trigger("NIFTY_CE_OTM200_RATIO_DIAG_1X2", itm_points=-200, min_credit_pts=10),
]


def _pe_ratio_diagonal_trigger(name: str, *, leg_gap: float = 400, min_credit_pts: float,
                                l1_lots: int = 1, l2_lots: int = 2, l3_lots: int = 1, l4_lots: int = 2,
                                strike_step: float = 100, min_dte: int = 1, sides=("PE",),
                                symbol: str = "NIFTY50", risk_level: str = "high") -> dict:
    """
    One entry of the 4-leg 1:2:1:2 ratio diagonal (live/chain_triggers.py, type
    "pe_ratio_diagonal_credit") — the same shape as the already-backtested strategy
    (docs/prd/pe-ratio-diagonal-strategy.md): BUY l1_lots @ K expiry1 (nearest, DTE >
    min_dte) / SELL l2_lots @ K2 expiry2 / SELL l3_lots @ K expiry2 / BUY l4_lots @ K2
    expiry3. K = base strike next to the futures price (PE floors, CE ceils); K2 = K -
    leg_gap (PE) / K + leg_gap (CE). Fires when credit (l1_lots*l1 - l2_lots*l2 -
    l3_lots*l3 + l4_lots*l4, negated) > min_credit_pts — on real data this 1:2:1:2 ratio
    prices as a DEBIT under normal conditions (verified 2026-09-22: -19.25 on the
    reference snapshot), so this is expected to fire rarely, not every day.
    """
    return {
        "name": name, "type": "pe_ratio_diagonal_credit", "symbol": symbol, "sides": list(sides),
        "strike_step": strike_step, "min_dte": min_dte, "leg_gap": leg_gap,
        "l1_lots": l1_lots, "l2_lots": l2_lots, "l3_lots": l3_lots, "l4_lots": l4_lots,
        "min_credit_pts": min_credit_pts, "risk_level": risk_level,
    }


# CHAIN_TRIGGERS.append(_pe_ratio_diagonal_trigger("NIFTY_PE_RATIO_DIAG_4LEG_400", min_credit_pts=5))


def _vertical_ratio_trigger(name: str, buy_points: float, *, min_credit_pts: float, medium_credit_pts: float,
                            high_credit_pts: float, min_oi: float, sell_gap: float = 500,
                            buy_lots: int = 1, sell_lots: int = 2, strike_step: float = 100,
                            sides=("PE", "CE"), symbol: str = "NIFTY50", risk_level: str = "high") -> dict:
    """
    One same-expiry 1:2 vertical ratio spread (live/chain_triggers.py, type "vertical_ratio_credit"):
    E = the strike_step multiple nearest NIFTY *spot* (the chain snapshot's own spot, not the future);
    BUY buy_lots @ E -/+ buy_points and SELL sell_lots @ E -/+ (buy_points + sell_gap), both in NEXT
    CALENDAR MONTH's expiry (PE goes below E, CE above). Fires when credit = sell_lots*sell_ltp -
    buy_lots*buy_ltp >= min_credit_pts and both legs' open interest >= min_oi. Conviction by credit:
    LOW [min_credit_pts, medium_credit_pts), MEDIUM [medium, high), HIGH >= high_credit_pts.
    Backtest / design: docs/prd/vertical-ratio-credit-trigger.md. Every number is explicit at the call
    site (same rule as _calendar_ratio_trigger).
    """
    if not (min_credit_pts < medium_credit_pts < high_credit_pts):
        raise ValueError(f"{name}: need min_credit_pts < medium_credit_pts < high_credit_pts")
    return {
        "name": name, "type": "vertical_ratio_credit", "symbol": symbol, "sides": list(sides),
        "strike_step": strike_step, "buy_points": buy_points, "sell_points": buy_points + sell_gap,
        "buy_lots": buy_lots, "sell_lots": sell_lots, "min_credit_pts": min_credit_pts,
        "medium_credit_pts": medium_credit_pts, "high_credit_pts": high_credit_pts, "min_oi": min_oi,
        "risk_level": risk_level,
    }


for _buy_points in (800, 900, 1000):
    CHAIN_TRIGGERS.append(_vertical_ratio_trigger(
        f"NIFTY_VERT_1X2_{_buy_points}_{_buy_points + 500}", _buy_points,
        min_credit_pts=15, medium_credit_pts=20, high_credit_pts=25, min_oi=50000))


def _diagonal_debit_trigger(name: str, *, near_qty: int, far_qty: int, far_offset: float, itm_points: float,
                            otm_points: float, high_below: float, medium_below: float, max_debit_pts: float,
                            near_min_oi: float, far_min_oi: float, strike_step: float = 100, sides=("PE", "CE"),
                            symbol: str = "NIFTY50", risk_level: str = "high") -> dict:
    """
    Month diagonal scanned over a strike range, with conviction by net DEBIT (live/chain_triggers.py, type
    "diagonal_debit_conviction"). For every strike S from itm_points in the money to otm_points out of the money
    around the NIFTY spot (PE: E+itm .. E-otm, CE: E-itm .. E+otm), trade near_qty @ S in NEXT calendar month's
    expiry and far_qty @ S -/+ far_offset in the month AFTER (PE below S, CE above). Quantities are SIGNED:
    +n = buy n lots, -n = sell n (same convention as strategies/day_strategies.py).
    debit = near_qty*near_ltp + far_qty*far_ltp (points; negative = a net CREDIT). The strike with the LOWEST
    liquid debit wins; it fires when that debit is below max_debit_pts, once per side per IST day. Conviction:
    HIGH if debit < high_below, MEDIUM if debit < medium_below, else LOW — so a credit rule is written with
    negative numbers (e.g. max_debit_pts=-25, medium_below=-50, high_below=-75 = credit 25+/50+/75+).
    Designs: docs/prd/diagonal-debit-conviction-trigger.md. Every number explicit at the call site.
    """
    if not (high_below < medium_below < max_debit_pts):
        raise ValueError(f"{name}: need high_below < medium_below < max_debit_pts")
    if near_qty == 0 or far_qty == 0:
        raise ValueError(f"{name}: near_qty and far_qty must be non-zero signed lots")
    return {
        "name": name, "type": "diagonal_debit_conviction", "symbol": symbol, "sides": list(sides),
        "strike_step": strike_step, "far_offset": far_offset, "itm_points": itm_points, "otm_points": otm_points,
        "near_qty": near_qty, "far_qty": far_qty, "high_below": high_below, "medium_below": medium_below,
        "max_debit_pts": max_debit_pts, "near_min_oi": near_min_oi, "far_min_oi": far_min_oi, "risk_level": risk_level,
    }


# Month Diagonal 1:3 — SELL 1 @ S next month, BUY 3 @ S -/+ 1000 month after. Fires on debit < 200 (HIGH < 120, MEDIUM < 180).
CHAIN_TRIGGERS.append(_diagonal_debit_trigger(
    "NIFTY_DIAG_1X3_1000", near_qty=-1, far_qty=3, far_offset=1000, itm_points=200, otm_points=500,
    high_below=120, medium_below=180, max_debit_pts=200, near_min_oi=50000, far_min_oi=100000))


# Buy 1 / Sell 4 Far — BUY 1 @ S next month, SELL 4 @ S -/+ 2000 month after. A net CREDIT rule:
# fires on credit > 25 (LOW 25-50, MEDIUM 50-75, HIGH 75+), written as debit thresholds (credit = -debit).
CHAIN_TRIGGERS.append(_diagonal_debit_trigger(
    "NIFTY_B1S4_FAR_2000", near_qty=1, far_qty=-4, far_offset=2000, itm_points=200, otm_points=500,
    high_below=-75, medium_below=-50, max_debit_pts=-25, near_min_oi=50000, far_min_oi=100000))


# Upstox instrument key per symbol name.
# Indices use display name; equities use ISIN (not trading symbol).
# To find any instrument key: download NSE instrument list from
#   https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz
# and look up the "instrument_key" column for your symbol.
UPSTOX_INSTRUMENT_KEYS = {
    "NIFTY50":   "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "RELIANCE":  "NSE_EQ|INE002A01018",   # equities use ISIN; resp key uses symbol but instrument_token matches
}

# Spot index instrument keys shown in the header bar and included in every
# price-cache fetch by the live poller. Add/remove indices here.
SPOT_IKEYS = {
    "NIFTY50":    "NSE_INDEX|Nifty 50",
    "BANKNIFTY":  "NSE_INDEX|Nifty Bank",
    "FINNIFTY":   "NSE_INDEX|Nifty Fin Services",
    "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
    "SENSEX":     "BSE_INDEX|SENSEX",
}

# Symbols shown in the web header bar, in display order.
# Must be keys in SPOT_IKEYS. Day-change shown where candles_1d data exists.
SPOT_DISPLAY = ["NIFTY50", "BANKNIFTY", "SENSEX"]
