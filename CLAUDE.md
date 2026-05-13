# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Drishti is a live NSE market signal agent. It polls Upstox every 5 seconds during market hours, detects technical indicator crossings (Supertrend, EMA, RSI), sends Telegram alerts with optional trade suggestions, and maintains a full OHLCV history via yfinance.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py init        # create DB tables (includes ticks table)
python main.py bootstrap   # seed full OHLCV history (~5–10 min)
```

## Commands

```bash
python main.py live               # start live poller (market hours only, runs EOD tasks at 16:00)
python main.py live --force       # skip holiday/hours check — for testing outside market hours
python main.py bootstrap          # seed all symbols, all timeframes
python main.py bootstrap RELIANCE # seed one symbol
python main.py sync               # manual EOD sync (normally auto-triggered by poller at 16:00)
python main.py verify             # check row counts and detect gaps
python main.py init               # (re-)create all tables, idempotent
```

## Daily Lifecycle (live poller)

```
Startup      holiday check → expiry cache refresh → load triggers → morning Telegram brief
09:15–15:30  poll every 5s: store LTP ticks → run triggers → alert on crossing → build 1h candles at :15 boundary
15:30        stop polling
16:00        full yfinance sync + tick cleanup + expiry cache refresh + EOD Telegram brief → exit
```

## Architecture

### Config
**`config.py`** — single source of truth. `SYMBOLS`, `TIMEFRAMES`, `TRIGGERS`, `UPSTOX_INSTRUMENT_KEYS`, Telegram credentials, poll intervals, cooldown settings. To add a trigger: append to `TRIGGERS` list — no code change needed.

### Database (`db/`)
**`db/init_db.py`** — `get_connection()`, table creation, `TF_TABLE` mapping. Tables: `candles_1h/1d/1wk/1mo`, `sync_log`, `ticks`, `recommended_trades`.

**`db/queries.py`** — only file with SQL. Key functions:
- `upsert_candles(symbol, tf_key, df)` — write OHLCV, uses INSERT OR REPLACE
- `get_candles(symbol, tf_key, limit)` — returns ascending DataFrame with tz-aware timestamps
- `write_ticks(symbol_ltps: dict)` — write {symbol: ltp} at current UTC second to `ticks` table
- `get_ticks(symbol, start_utc, end_utc)` — read ticks in a time window
- `cleanup_ticks(days_to_keep=7)` — delete old ticks
- `open_recommended_trade(trigger_name, symbol, entry_level, entry_ltp, entry_time, exit_level, pe_strike, expiry_str, fut_lots, pe_lots, entry_fut_price, entry_pe_price, parent_trade_id)` — record a new open trade; lot sizes and leg prices snapshotted at entry
- `get_open_recommended_trade(symbol, entry_level)` — return the open trade at a given level, or None
- `get_all_open_recommended_trades(symbol)` — all open trades for a symbol (status='open')
- `get_trade_chain(trade_id)` — all trades in the rollover chain (root → latest), ordered by entry_time; walk parent_trade_id links
- `close_recommended_trade(trade_id, exit_ltp, exit_time, exit_fut_price, exit_pe_price)` — mark as exited; leg prices optional (NULL until fut/options polling added)
- `roll_recommended_trade(trade_id, exit_ltp, exit_time, new_expiry_str, new_pe_strike, ...)` — mark current as 'rolled', open replacement row with parent_trade_id linking back; use at monthly expiry

### Data Pipeline (`bootstrap/`, `sync/`)
**`bootstrap/yfinance_loader.py`** — `fetch_historical()` shared by bootstrap and sync. Normalises to UTC, drops in-progress candles for intraday intervals.

**`sync/daily_sync.py`** — incremental upsert for all timeframes. Called at startup and again at 16:00 by the poller.

### Live Polling (`live/`)
**`live/poller.py`** — main loop. Orchestrates all startup/EOD tasks and the 5s poll cycle. Entry point via `python main.py live`.

**`live/upstox_client.py`** — `get_ltp(instrument_keys)` via Upstox Python SDK. Singleton API client. Returns `{instrument_key: float}`. Instrument keys use pipe format (`NSE_INDEX|Nifty 50`); equities use ISIN not trading symbol.

**`live/tick_store.py`** — writes LTP ticks to DB on every poll. Call `init(ikey_to_name)` once at startup, then `record(prices)` each cycle.

**`live/candle_builder.py`** — at each 1h candle close (:15 IST boundary), aggregates ticks in the window → OHLCV → upserts to `candles_1h`. Skips if fewer than 3 ticks or tick coverage < 50% of window (keeps existing yfinance data in that case).

**`live/intraday_sync.py`** — `HourlyCandleWatcher`: fires `should_sync()` once per hour at :15 IST. Still used for the watcher timing logic; yfinance startup sync has moved to `daily_sync`.

**`live/triggers.py`** — trigger classes. `build_trigger(cfg, symbol)` instantiates from config. All triggers inherit `BaseTrigger` which handles cooldown (`cooldown_minutes` in config) and trade suggestion dispatch. Types:
- `SupertrendCrossTrigger` — LTP crosses Supertrend line
- `EmaCrossTrigger` — LTP crosses EMA line (optional `direction: UP/DOWN` filter)
- `RsiThresholdTrigger` — RSI crosses below `below` or above `above`
- `ConfluenceCrossTrigger` — cross + multiple confirm conditions (AND-gated)
- `Nifty500MultipleTrigger` — LTP crosses UP through 500-multiple → entry signal; LTP drops `exit_distance` pts from entry → exit signal. Uses `recommended_trades` DB for dedup and exit tracking. `check()` can return a list of signals (entry + exit can fire same tick). Does NOT use `BaseTrigger._signal()` — builds signal dicts directly in `_make_signal()`.

**`live/signal_engine.py`** — pure indicator compute functions (`compute_supertrend`, `compute_ema`, `compute_rsi`). Each returns the indicator value plus last candle close (used to initialise crossing baseline so gap-down/up scenarios fire immediately on first tick).

**`live/alert.py`** — Telegram dispatcher. `send_alert(signal)` sends one signal message then one message per trade suggestion. Uses HTML parse mode.

**`live/expiry.py`** — `ExpiryCache` fetches NSE option expiry dates from Upstox `OptionsApi`. `expiry_cache.pick(symbol, type, index)` returns a `date`. Types: `"weekly"`, `"monthly"`, `"quarterly"`.

**`live/trade_suggestions.py`** — trade suggestion templates. Each template function takes `(ltp, symbol, params)` and returns a trade dict with `title`, `legs`, `rationale`. Templates:
- `nifty_pe_cal_qtrly` / `nifty_pe_cal_monthly` / `nifty_pe_cal_weekly_to_monthly` — PE calendar spreads
- `nifty_500_short_entry` — entry trade for 500-multiple strategy: SELL fut + SELL PE. Returns private keys `_pe_strike`, `_expiry_str`, `_exit_level` that `Nifty500MultipleTrigger` extracts for DB storage before sending the signal.
- `nifty_500_short_exit` — exit trade: BUY fut + BUY PE back. Params come from the `recommended_trades` DB row merged with config params (so fut_lots/pe_lots are still config-driven).

**`live/holidays.py`** — `is_trading_day(date)` and `check_or_exit()` using BSE (XBOM) calendar from `exchange-calendars`. BSE and NSE share the same holiday schedule.

**`live/briefing.py`** — `send_morning_brief(trigger_count)` and `send_eod_brief(alerts)` Telegram messages. Morning brief includes a rotating market quote and tomorrow's trading status. EOD brief summarises alerts fired that day.

## Key Conventions

- Symbols stored as `name` field (e.g. `"RELIANCE"`), not yfinance ticker.
- All DB timestamps are ISO-8601 UTC strings; `get_candles()` returns tz-aware `pd.Timestamp`. Ticks stored as `"YYYY-MM-DDTHH:MM:SSZ"` — use this exact format for comparisons.
- `upsert_candles` uses INSERT OR REPLACE — safe to run multiple times.
- NSE 1h candles start/end at `:15` past each hour (09:15, 10:15, ... 15:15). The 15:15–15:30 partial window is not built into a candle.
- Instrument keys use pipe format (`NSE_INDEX|Nifty 50`) in config and code; Upstox SDK responses use colon format (`NSE_INDEX:Nifty 50`) — `upstox_client.py` normalises back to pipe.
- Trigger cooldown: `_signal()` in `BaseTrigger` returns `None` if within cooldown window — subclass `check()` methods already propagate this correctly.
- 1d indicators (EMA20, ST) use yesterday's closed candles during the trading day — this is correct behaviour. The EMA line is fixed intraday; live LTP is compared against it every 5s.
- Tick-built 1h candles have `volume=NULL`. The 16:00 yfinance sync overwrites them with official OHLCV including volume.
