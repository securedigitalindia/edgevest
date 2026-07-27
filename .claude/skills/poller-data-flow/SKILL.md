---
name: poller-data-flow
description: Reference for how backend/live/poller.py pulls data from Upstox every 5s and where each piece of data ends up (ticks, price_cache, candles_*, recommended_trades). Use before adding any new data capture/polling to the live poller, or when tracing where a price/tick/candle value actually comes from.
---

# Drishti live poller — data flow reference

`backend/live/poller.py` is a separate long-running process, invoked via the top-level CLI dispatcher `backend/poller.py live` (independent of the Flask API — note the two files share a base filename but are different files, dispatcher vs. loop logic). Its `while` loop (`poller.py:263-330`) runs every `POLL_INTERVAL_SECONDS` (5s) during market hours.

## What gets polled every 5s

One call, `get_ltp(instrument_keys)` (`live/upstox_client.py:122-153`), against a **merged instrument-key list rebuilt every cycle** (`poller.py:284-288`):

```
_all_ikeys = ikeys (trigger instruments) + _spot_ikeys (header ticker) + _trade_ikeys (open trade legs)
```

- **`ikeys`** — symbols with an active entry in `config.TRIGGERS` *and* a `config.UPSTOX_INSTRUMENT_KEYS` entry. Built once at startup by `_build_all_triggers()` (`poller.py:169-201`). Currently: NIFTY50, BANKNIFTY, RELIANCE.
- **`_spot_ikeys`** — fixed header-ticker set, `config.SPOT_IKEYS` (re-exported via `live/fo_instruments.py:75`): NIFTY50, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX.
- **`_trade_ikeys`** — dynamic, from `get_open_trade_ikeys()` (`db/queries.py:1589-1608`): instrument keys of every option/future leg currently belonging to an **open** `recommended_trades` or `account_trades` row. Recomputed every cycle so it tracks trades as they open/close.

This is the only data-pull mechanism today. Adding a new symbol to be "polled" normally means adding it to one of these three sources — **not** writing a parallel `get_ltp` call.

## Where it lands — two direct write destinations, not three

| destination | table | gets written for | write path |
|---|---|---|---|
| tick history | `ticks` | **only** trigger instruments (`ikey_to_name`) | `tick_store.record()` → filters to `ikey_to_name`, `poller.py:314`, `tick_store.py:17-24` |
| live-quote cache | `price_cache` | **everything** in that cycle's batch (trigger + ticker + open trade legs), no filter | `update_price_cache()`, `poller.py:308-311`, `db/queries.py:1471-1521` |

**`price_cache` is not a history** — one row per `instrument_key`, upserted in place each cycle (`prev_close` snapshotted once per day on first update of the day). It's what `/api/spot` and `/api/prices` read (`server.py:1163-1178`), polled by the frontend's `usePrices` hook every 5s (`frontend/src/hooks/usePrices.js:8`).

**`ticks` is a real history** but pruned to 7 days (`cleanup_ticks`, run at 16:00 EOD, `poller.py:130-133`). It exists only to build intraday candles from.

## Candles are derived, not polled

`candles_1m/5m/15m/1h` are **built from the `ticks` table** at each timeframe boundary by `candle_builder.build_all()` (`poller.py:264-281`, timer via `CandleWatcher` in `live/intraday_sync.py`) — nothing writes them directly during the poll. Since only trigger instruments land in `ticks`, only trigger instruments ever get intraday candles this way; pure ticker symbols (FINNIFTY, SENSEX, MIDCPNIFTY) get live price in `price_cache` but no intraday candle history.

`candles_1d/1wk/1mo` come from a **separate `yfinance` EOD sync** at 16:00 (`sync/daily_sync.py`, triggered in `_run_eod_tasks`, `poller.py:112-155`) — entirely unrelated to Upstox polling.

## `recommended_trades` / `trade_legs` are event-driven, not polled

Written only when a trigger's `check()` fires an entry/exit signal (`poller.py:316-324`) — nothing polls these tables into existence. `/api/recommendations` (`server.py:459-513`) just reads current state on request. The only live-poll connection is one-directional: `get_open_trade_ikeys()` feeds open positions' option/future legs *into* the price-cache poll list so open trades get live LTP for P&L — polling never writes to `recommended_trades` itself.

## Pattern for adding a new capture task

1. Decide: does it fit the existing 5s `get_ltp()` batch (single instrument LTP), or does it need its own API call shape (e.g. an option-chain endpoint returning many rows per call)? Only the former belongs in `_all_ikeys`.
2. If it needs its own cadence/shape: add a timer check inside the `while` loop (`poller.py:263-330`), same pattern as the `CandleWatcher`/timeframe watchers — checked once per 5s cycle, fires on its own schedule.
3. Give it its own table. Don't overload `ticks` or `price_cache` — they have specific, narrow contracts (tick history for trigger symbols only; latest-quote cache for everything).
4. Wrap the new task in `try/except` so a failure is logged and skipped, never crashes the loop or delays the next `get_ltp()` call beyond that one cycle — same defensive pattern used for expiry refresh, F&O instrument refresh, and candle building today.
5. Decide retention explicitly. `ticks` is deliberately short-lived (7 days, it's just a candle-building buffer) — a new table storing data that *is itself* the analysis dataset should not inherit that assumption.
