# ============================================================
#  Drishti — config.py
#  Single source of truth for all settings
# ============================================================

import os

# -----------------------------------------------------------
# Symbols
# -----------------------------------------------------------
# Each entry: (yfinance_ticker, display_name, type)
# type: "equity" | "index"
SYMBOLS = [
    {"ticker": "^NSEI",        "name": "NIFTY50",    "type": "index"},
    {"ticker": "^NSEBANK",     "name": "BANKNIFTY",  "type": "index"},
    {"ticker": "RELIANCE.NS",  "name": "RELIANCE",   "type": "equity"},
]

# -----------------------------------------------------------
# Database
# -----------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "drishti.db")

# -----------------------------------------------------------
# Timeframes
# -----------------------------------------------------------
# key        : internal name used for table suffix and yfinance interval
# interval   : yfinance interval string
# period     : max history to bootstrap (yfinance period string)
# yf_limit   : max days yfinance reliably provides for this interval
# description: human label

TIMEFRAMES = [
    {
        "key":         "5m",
        "interval":    "5m",
        "period":      "60d",       # yfinance max for 5m
        "description": "5 Minute",
    },
    {
        "key":         "15m",
        "interval":    "15m",
        "period":      "60d",       # yfinance max for 15m
        "description": "15 Minute",
    },
    {
        "key":         "1h",
        "interval":    "1h",
        "period":      "730d",      # yfinance max for 1h
        "description": "1 Hour",
    },
    {
        "key":         "1d",
        "interval":    "1d",
        "period":      "20y",
        "description": "1 Day",
    },
    {
        "key":         "1wk",
        "interval":    "1wk",
        "period":      "20y",
        "description": "1 Week",
    },
    {
        "key":         "1mo",
        "interval":    "1mo",
        "period":      "20y",
        "description": "1 Month",
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
# yfinance request delay (seconds) between symbol fetches
# to avoid rate limiting
FETCH_DELAY_SECONDS = 1.5

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

TRIGGERS = [
    # --- Basic alerts (no trade suggestion) ---
    {
        "name":             "ST_1D_CROSS",
        "type":             "supertrend_cross",
        "timeframe":        "1d",
        "period":           7,
        "multiplier":       3.0,
        "symbols":          ["NIFTY50", "BANKNIFTY"],
        "cooldown_minutes": 480,   # 8h — daily flip won't reverse intraday
    },
    {
        "name":             "ST_1WK_CROSS",
        "type":             "supertrend_cross",
        "timeframe":        "1wk",
        "period":           7,
        "multiplier":       3.0,
        "symbols":          ["NIFTY50", "BANKNIFTY"],
        "cooldown_minutes": 2880,  # 2 days — weekly flip is a rare, durable signal
    },
    {
        "name":             "ST_1H_CROSS",
        "type":             "supertrend_cross",
        "timeframe":        "1h",
        "period":           10,
        "multiplier":       1.8,
        "symbols":          "all",
        "cooldown_minutes": 15,   # don't re-alert same cross within 15 min
    },
    {
        "name":             "RSI14_1H_OVERSOLD",
        "type":             "rsi_threshold",
        "timeframe":        "1h",
        "period":           14,
        "below":            35,
        "symbols":          "all",
        "cooldown_minutes": 60,   # RSI can linger in zone; one alert per hour max
    },

    # --- Trade suggestion alerts ---
    {
        "name":             "EMA20_1D_DOWN_CROSS",
        "type":             "ema_cross",
        "timeframe":        "1d",
        "period":           20,
        "direction":        "DOWN",
        "symbols":          ["NIFTY50"],
        "cooldown_minutes": 30,
        # trades: list — 0, 1, or more suggestions per alert
        # All trade logic is driven by params here — no code change needed
        "trades": [
            {
                "type":  "nifty_pe_cal_qtrly",
                "params": {
                    "itm_points":  2000,  # strike = CMP + 2000 (ITM put)
                    "strike_step": 1000,  # round to nearest 1000
                    "far_index":   1,     # quarterly[1] = 2nd quarterly out
                },
            },
        ],
    },
]

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
