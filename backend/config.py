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
    _calendar_ratio_trigger("NIFTY_CE_ITM400_RATIO_DIAG_1X2", itm_points=400, max_debit_pts=25),
    _calendar_ratio_trigger("NIFTY_CE_ITM300_RATIO_DIAG_1X2", itm_points=300, max_debit_pts=25),
    _calendar_ratio_trigger("NIFTY_CE_ITM200_RATIO_DIAG_1X2", itm_points=200, max_debit_pts=25),
    _calendar_ratio_trigger("NIFTY_CE_ITM100_RATIO_DIAG_1X2", itm_points=100, max_debit_pts=25),
    _calendar_ratio_trigger("NIFTY_CE_ITM0_RATIO_DIAG_1X2", itm_points=0, max_debit_pts=25),
    # OTM100 uses its own credit > 5 rule (confirmed 2026-09-22), unlike the other five which
    # fire on debit < 25 — on real data OTM100 has priced as a debit too (14.1 on the reference
    # snapshot), so this rule is expected to rarely fire, same caveat as the PE ratio diagonal.
    _calendar_ratio_trigger("NIFTY_CE_OTM100_RATIO_DIAG_1X2", itm_points=-100, min_credit_pts=5),
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


CHAIN_TRIGGERS.append(_pe_ratio_diagonal_trigger("NIFTY_PE_RATIO_DIAG_4LEG_400", min_credit_pts=5))


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
