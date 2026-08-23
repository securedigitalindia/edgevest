# Database Schema

Single SQLite file at `backend/data/drishti.db` (`config.DB_PATH`), shared by the Flask API (`server.py`) and the Drishti live poller (`poller.py`/`live/`). `WAL` journal mode. Created/migrated idempotently by `backend/db/init_db.py` — every `CREATE TABLE` there uses `IF NOT EXISTS`, and the file contains several inline `ALTER TABLE`/data-migration blocks that run on every startup to bring older DB files up to the current shape (e.g. `_migrate_traders_to_users`, `_migrate_trades_to_legs`). All DB access goes through `backend/db/queries.py` — the only file with SQL — via `get_connection()`.

**Timestamp convention**: every `TEXT` timestamp column is ISO-8601 UTC, formatted `YYYY-MM-DDTHH:MM:SSZ` (see `ticks`, `upsert_user`, etc. in `queries.py`). `get_candles()` returns these as tz-aware `pandas.Timestamp`. Never local/IST in storage — IST conversion happens only at display time.

---

## Market data — candles, ticks, prices

### `candles_1m` / `candles_5m` / `candles_15m` / `candles_1h` / `candles_1d` / `candles_1wk` / `candles_1mo`

One table per timeframe (`db.init_db.TF_TABLE` maps `TIMEFRAMES` keys from `config.py` to table names), identical shape. Populated by `bootstrap/upstox_loader.py` (full history), `sync/daily_sync.py` (daily gap-fill), and `live/candle_builder.py` (tick-built 1h candles at each `:15` boundary).

| Column | Type | Notes |
|---|---|---|
| `symbol` | TEXT NOT NULL | e.g. `"NIFTY50"`, `"RELIANCE"` — part of PK |
| `ts` | TEXT NOT NULL | ISO-8601 UTC, part of PK |
| `open` / `high` / `low` / `close` | REAL | |
| `volume` | REAL | Tick-built 1h candles have `volume=NULL` until overwritten by the 16:00 Upstox sync |
| `oi` | REAL | Added via `ALTER TABLE` migration (Upstox switch — yfinance never provided open interest); nullable |

- **PK**: `(symbol, ts)` — `upsert_candles()` uses `INSERT OR REPLACE`, safe to re-run.
- **Index**: `idx_{table}_sym_ts` on `(symbol, ts DESC)`.
- NSE 1h candles are aligned to `:15` past each hour (09:15…15:15); the 15:15–15:30 partial window is never built into a candle.

### `sync_log`

Tracks the last successful sync per symbol/timeframe (`update_sync_log()` / `get_sync_log()`), used by `sync/daily_sync.py` to know where to resume.

| Column | Type | Notes |
|---|---|---|
| `symbol` | TEXT NOT NULL | part of PK |
| `tf_key` | TEXT NOT NULL | part of PK — `"1m"`, `"1h"`, etc. |
| `last_sync` | TEXT NOT NULL | ISO-8601 UTC |
| `rows_added` | INTEGER DEFAULT 0 | |

- **PK**: `(symbol, tf_key)`.

### `ticks`

Raw LTP ticks written every poll cycle (5s) by `live/tick_store.py` via `write_ticks()`; source data for tick-built 1h candles (`candle_builder.py`). Pruned by `cleanup_ticks(days_to_keep=7)`, called from the poller's EOD tasks — this is the one table with a retention job.

| Column | Type | Notes |
|---|---|---|
| `symbol` | TEXT NOT NULL | part of PK |
| `ts` | TEXT NOT NULL | ISO-8601 UTC, `"YYYY-MM-DDTHH:MM:SSZ"` — exact-second granularity, part of PK |
| `ltp` | REAL NOT NULL | |

- **PK**: `(symbol, ts)`.
- **Index**: `idx_ticks_sym_ts` on `(symbol, ts DESC)`.

### `price_cache`

Latest known LTP per Upstox instrument key, upserted every poll cycle by `update_price_cache()`; read by `get_cached_prices()` to serve `/api/prices` and by the games/portfolio P&L calculators.

| Column | Type | Notes |
|---|---|---|
| `instrument_key` | TEXT PRIMARY KEY | Upstox pipe-format key, e.g. `NSE_INDEX\|Nifty 50` |
| `ltp` | REAL NOT NULL | |
| `ts` | TEXT NOT NULL | ISO-8601 UTC |
| `prev_close` | REAL | Added via migration; nullable |

### `option_chain_5m`

Standalone analysis dataset (calendar-spread research) — a 5-minute-resolution snapshot of the full NIFTY option chain (both weekly/monthly expiry triads, all strikes, CE+PE), captured by `live/option_chain_capture.py` inside the poller's main loop. **Not** a candle-building buffer like `ticks` — no retention/cleanup job exists for it.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `ts` | TEXT NOT NULL | Floored to the nearest 5-min UTC boundary (`_boundary_ts()`), not fetch wall-clock time |
| `symbol` | TEXT NOT NULL | `"NIFTY50"` today |
| `spot_ltp` | REAL NOT NULL | Spot at capture time, from the same API response (no separate LTP call) |
| `expiry_type` | TEXT NOT NULL | `"weekly"` \| `"monthly"` |
| `expiry_rank` | INTEGER NOT NULL | 0/1/2, relative to *capture time* — recomputed every snapshot. Not stable across a rollover; filter by `expiry_date` for a continuous series, never by `expiry_rank` |
| `expiry_date` | TEXT NOT NULL | Fixed contract identity, `YYYY-MM-DD` |
| `strike` | REAL NOT NULL | Unfiltered — every strike in the returned ladder is captured, no moneyness pre-filter |
| `opt_type` | TEXT NOT NULL | `"CE"` \| `"PE"` |
| `ltp` / `oi` / `iv` | REAL | All nullable |

- **UNIQUE**: `(ts, symbol, expiry_date, strike, opt_type)` — the writer uses `INSERT OR IGNORE` (never `OR REPLACE`) against this key, making a poller-restart re-capture of the same 5-min slot a no-op rather than a duplicate.
- **Indexes**: `idx_option_chain_5m_sym_ts` on `(symbol, ts DESC)`; `idx_option_chain_5m_strike_expiry` on `(symbol, expiry_date, strike, opt_type)`.

---

## Trading — recommendations, legs, adjustments

### `recommended_trades`

One row per trade *header* — all leg detail lives in `trade_legs`. Created by triggers (`live/triggers.py` → `open_recommended_trade()`); one open row per `(symbol, entry_level)` at a time.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `trigger_name` | TEXT NOT NULL | e.g. `"NIFTY500_MULTI"` |
| `symbol` | TEXT NOT NULL | |
| `parent_trade_id` | INTEGER REFERENCES `recommended_trades(id)` | Self-referencing — chains a trade to its predecessor across a monthly-expiry roll |
| `entry_level` / `entry_ltp` / `entry_time` | REAL/REAL/TEXT NOT NULL | |
| `exit_level` | REAL NOT NULL | |
| `status` | TEXT NOT NULL DEFAULT `'open'` | `open` \| `exited` (legacy `'rolled'` values are migrated to `'exited'` on startup) |
| `exit_ltp` / `exit_time` | REAL/TEXT | Nullable until exit |
| `margin_required` / `margin_final` | REAL | Added via migration; nullable |

- **Indexes**: `idx_recommended_trades_sym_level_status` on `(symbol, entry_level, status)`; `idx_recommended_trades_parent` on `(parent_trade_id)`.
- Walk a full rollover chain root→latest via `get_trade_chain()` (follows `parent_trade_id`).
- Schema history: this table used to be flat (columns like `pe_strike`, `fut_lots` directly on the row); `_migrate_trades_to_legs()` detects the old shape (`pe_strike` column present) and rewrites it into this header + `trade_legs` on startup.

### `trade_legs`

One row per leg per event (entry, exit, or adjustment) on a `recommended_trades` row.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `trade_id` | INTEGER NOT NULL REFERENCES `recommended_trades(id)` | |
| `action` | TEXT NOT NULL | `entry` \| `exit` (legacy `rollover_in`/`rollover_out` migrated to `entry`/`exit`) |
| `side` | TEXT NOT NULL | `BUY` \| `SELL` |
| `instrument_type` | TEXT NOT NULL | `FUT` \| `PE` \| `CE` \| `EQ` (extensible) |
| `instrument_key` | TEXT | Upstox instrument key; nullable |
| `strike` / `expiry_str` | REAL/TEXT | Nullable (not applicable to `FUT`/`EQ`) |
| `lots` | INTEGER NOT NULL DEFAULT 1 | |
| `lot_size` | INTEGER NOT NULL DEFAULT 0 | |
| `price` | REAL | Leg price at `ts`; nullable |
| `ts` | TEXT NOT NULL | |
| `adjustment_id` | INTEGER REFERENCES `trade_adjustments(id)` | `NULL` = original entry leg; non-`NULL` = belongs to a specific adjustment event |
| `auto_adjust` | INTEGER NOT NULL DEFAULT 0 | `1` = auto-roll this leg when its expiry arrives |

- **Index**: `idx_trade_legs_trade_id` on `(trade_id)`.
- `get_original_entry_legs()` filters `adjustment_id IS NULL` to get just the original entry; `get_current_legs()` computes the net-current leg set after all adjustments.

### `trade_adjustments`

One row per adjustment *event* on a trade (groups the `trade_legs` rows that belong to it).

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `trade_id` | INTEGER NOT NULL REFERENCES `recommended_trades(id)` | |
| `adj_type` | TEXT NOT NULL | `auto_roll` \| `replace_legs` \| `add_legs` \| `partial_exit` \| `exit` |
| `note` | TEXT | Nullable |
| `ts` | TEXT NOT NULL | |

- **Index**: `idx_trade_adjustments_trade_id` on `(trade_id)`.

---

## Users, accounts, brokers, subscriptions

### `users`

Google OAuth identity + role. Created/updated by `upsert_user()` on every login — **the first-ever user to sign up automatically becomes `super_admin`**, everyone after is `client`.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `google_id` | TEXT NOT NULL UNIQUE | |
| `email` | TEXT NOT NULL UNIQUE | |
| `name` | TEXT NOT NULL | |
| `picture` | TEXT | Nullable |
| `role` | TEXT NOT NULL DEFAULT `'client'` | `super_admin` \| `admin`(?) \| `client` — see `update_user_role()` for the full set used by the API |
| `mobile` / `note` | TEXT | Added via migration; nullable |
| `active` | INTEGER NOT NULL DEFAULT 1 | |
| `created_at` | TEXT NOT NULL | |

- Schema history: this table replaces an older `traders` table — `_migrate_traders_to_users()` runs once (detects a leftover `traders` table), copying `mobile`/`note` across, rebuilding `accounts`/`account_trades`/`account_trade_legs` to fix their foreign keys after the rename, then drops `traders`.

### `user_profiles`

Trading-preference answers from the first-run onboarding wizard (frontend `SetupWizard.jsx`).

| Column | Type | Notes |
|---|---|---|
| `user_id` | INTEGER PRIMARY KEY REFERENCES `users(id)` | 1:1 with `users` |
| `segment` / `risk_type` / `trader_type` / `focus` | TEXT | Nullable, free-form wizard answers |
| `setup_done` | INTEGER NOT NULL DEFAULT 0 | Gates whether the frontend shows the wizard again |
| `updated_at` | TEXT NOT NULL | |

### `brokers`

Static-ish lookup of broker names (e.g. Zerodha, Upstox) users can add accounts under.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `name` | TEXT NOT NULL UNIQUE | |

### `accounts`

A user's real (or game-virtual) brokerage account.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `user_id` | INTEGER REFERENCES `users(id)` | |
| `broker_id` | INTEGER REFERENCES `brokers(id)` | |
| `account_no` / `label` | TEXT | Nullable |
| `active` | INTEGER NOT NULL DEFAULT 1 | |
| `game_id` | INTEGER REFERENCES `games(id)` | Added via migration — non-`NULL` marks this as a virtual account for a leaderboard game, not a real brokerage account |
| `capital` | REAL NOT NULL DEFAULT 0 | Added via migration — virtual cash balance for game accounts |

- **Unique index**: `idx_accounts_user_broker` on `(user_id, broker_id)` — one account per user per broker.

### `subscription_plans`

Admin-managed plan catalogue. Seeded with a default free `"Free"` plan (`price=0`, `duration_days=30`) if the table is empty on init.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `name` | TEXT NOT NULL | |
| `description` | TEXT | Nullable |
| `price` | INTEGER NOT NULL DEFAULT 0 | |
| `duration_days` | INTEGER NOT NULL DEFAULT 30 | |
| `active` | INTEGER NOT NULL DEFAULT 1 | |
| `created_at` | TEXT NOT NULL | |
| `gem_cost` | INTEGER NOT NULL DEFAULT 0 | Added via migration — cost in credits if purchasable with gems instead of money |

### `subscriptions`

One row per subscription period a user has held (historical — not just the current one).

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `user_id` | INTEGER NOT NULL REFERENCES `users(id)` | |
| `plan_id` | INTEGER NOT NULL REFERENCES `subscription_plans(id)` | |
| `status` | TEXT NOT NULL DEFAULT `'active'` | `active` \| `expired` (see `expire_stale_subscriptions()`) |
| `start_date` / `end_date` | TEXT NOT NULL | |
| `amount_paid` | INTEGER NOT NULL DEFAULT 0 | |
| `created_at` | TEXT NOT NULL | |

- **Index**: `idx_subscriptions_user` on `(user_id, status)`.
- `activate_subscription()` expires any existing active subscription for the user before inserting the new one — only one `status='active'` row per user by convention (not DB-enforced).

---

## Account trades (real positions pushed from recommendations)

### `account_trades`

One row per account per recommendation pushed to it — the per-client instantiation of a `recommended_trades` header.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `recommended_trade_id` | INTEGER REFERENCES `recommended_trades(id)` | Nullable — an account trade can exist without a source recommendation |
| `account_id` | INTEGER NOT NULL REFERENCES `accounts(id)` | |
| `status` | TEXT NOT NULL DEFAULT `'open'` | `open` \| `exited` |
| `entry_time` | TEXT NOT NULL | |
| `exit_time` | TEXT | Nullable |
| `note` | TEXT | Nullable |
| `margin` | REAL | Added via migration; nullable |

- **Indexes**: `idx_account_trades_account` on `(account_id, status)`; `idx_account_trades_rec` on `(recommended_trade_id)`.

### `account_trade_legs`

Same shape/role as `trade_legs`, but for `account_trades` instead of `recommended_trades`.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `account_trade_id` | INTEGER NOT NULL REFERENCES `account_trades(id)` | |
| `action` / `side` / `instrument_type` / `instrument_key` / `strike` / `expiry_str` / `lots` / `lot_size` / `price` / `ts` | same as `trade_legs` | |
| `adjustment_id` | INTEGER REFERENCES `trade_adjustments(id)` | Added via migration; nullable |
| `margin` | REAL | Added via migration; nullable |

- **Index**: `idx_account_trade_legs_trade` on `(account_trade_id)`.

---

## Games (paper trading)

### `games`

One row per game (price-prediction, MCQ quiz, or leaderboard type).

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `title` / `description` | TEXT | `description` nullable |
| `game_type` | TEXT NOT NULL | `price_prediction` \| `mcq` \| `leaderboard` |
| `symbol` | TEXT | Nullable — relevant for `price_prediction`/`leaderboard` types |
| `status` | TEXT NOT NULL DEFAULT `'draft'` | `draft` \| `active` \| `closed` \| `resolved` (see `useActivateGame`/`useCloseGame`/`useResolveGame` on the frontend) |
| `start_time` / `end_time` | TEXT NOT NULL | |
| `reward_pool` | INTEGER NOT NULL DEFAULT 0 | Credits |
| `winner_count` | INTEGER NOT NULL DEFAULT 1 | |
| `result_value` | TEXT | Nullable until resolved |
| `initial_cash` | INTEGER NOT NULL DEFAULT 1000000 | Starting virtual cash for `leaderboard`-type games |
| `created_by` | INTEGER NOT NULL REFERENCES `users(id)` | |
| `created_at` | TEXT NOT NULL | |
| `resolved_at` | TEXT | Nullable |

### `game_questions`

MCQ-type game questions.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `game_id` | INTEGER NOT NULL REFERENCES `games(id)` | |
| `order_num` | INTEGER NOT NULL DEFAULT 0 | Display order |
| `question` | TEXT NOT NULL | |
| `option_a` / `option_b` / `option_c` / `option_d` | TEXT NOT NULL | |
| `correct_opt` | TEXT NOT NULL | One of `a`/`b`/`c`/`d` |

### `game_entries`

One row per user's entry/submission into a game.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `game_id` | INTEGER NOT NULL REFERENCES `games(id)` | |
| `user_id` | INTEGER NOT NULL REFERENCES `users(id)` | |
| `entry_data` | TEXT NOT NULL DEFAULT `'{}'` | JSON blob — shape depends on `game_type` (prediction value, MCQ answers, etc.) |
| `score` | REAL | Nullable until scored |
| `rank` | INTEGER | Nullable until resolved |
| `credits_won` | INTEGER NOT NULL DEFAULT 0 | |
| `submitted_at` | TEXT NOT NULL | |

- **UNIQUE**: `(game_id, user_id)` — one entry per user per game.
- **Index**: `idx_game_entries_game` on `(game_id)`.

### `virtual_trades`

Individual buy/sell actions a user makes inside a `leaderboard`-type game (paper trading).

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `game_id` | INTEGER NOT NULL REFERENCES `games(id)` | |
| `user_id` | INTEGER NOT NULL REFERENCES `users(id)` | |
| `symbol` | TEXT NOT NULL | |
| `action` | TEXT NOT NULL | `BUY` \| `SELL` |
| `price` | REAL NOT NULL | |
| `quantity` | INTEGER NOT NULL | |
| `traded_at` | TEXT NOT NULL | |

- **Index**: `idx_vtrades_game_user` on `(game_id, user_id)`.
- Portfolio for a game account is computed on the fly from this table by `get_game_portfolio()` (delegates to `get_account_portfolio()`), not stored as a running balance.

---

## Credits

### `user_credits`

Current credit balance per user (gems — used for signup bonuses, game entry, plan purchases).

| Column | Type | Notes |
|---|---|---|
| `user_id` | INTEGER PRIMARY KEY REFERENCES `users(id)` | 1:1 with `users` |
| `balance` | INTEGER NOT NULL DEFAULT 0 | |
| `updated_at` | TEXT NOT NULL | |

### `credit_transactions`

Append-only ledger of every credit change — `user_credits.balance` is derived/maintained alongside this, not solely computed from it, but this table is the audit trail.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `user_id` | INTEGER NOT NULL REFERENCES `users(id)` | |
| `amount` | INTEGER NOT NULL | Signed — positive credit, negative debit |
| `reason` | TEXT NOT NULL | e.g. `"signup_bonus"`, game rewards, plan purchase |
| `ref_id` | TEXT | Nullable — links to the game/plan/etc. that caused this transaction |
| `note` | TEXT | Nullable |
| `created_at` | TEXT NOT NULL | |

- **Index**: `idx_credit_tx_user` on `(user_id)`.
- New users are awarded `config.SIGNUP_CREDITS` (99) via `_award_credits_tx()` at signup (`upsert_user()`), reason `"signup_bonus"`.
