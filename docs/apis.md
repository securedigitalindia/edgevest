# EdgeVest — API Reference

Source of truth: `backend/server.py` (single file, ~1280 lines). Base URL in prod is `https://api.edgevest.in` (frontend calls it via `/api/*`, proxied/absolute per env — see `frontend/src/api/client.js` and root `CLAUDE.md`'s Environments section). Auth is **session-cookie based**, not tokens — every `/api/*` route is protected by one of the decorators below, which check `session["user"]` (a Flask signed cookie), not an `Authorization` header.

Frontend API client modules live in `frontend/src/api/*.js` (one per resource: `auth`, `games`, `prices`, `settings`, `trades`), all going through the shared axios instance in `frontend/src/api/client.js` (`withCredentials: true`, base URL from `VITE_API_URL`).

## Auth model

Three decorators gate access, all defined at the top of `server.py`:

- **`@require_login`** — 401 JSON (`/api/*` paths) or redirect to login otherwise, if no `session["user"]`.
- **`@require_role(*roles)`** — like `require_login`, plus 403 if `user["role"]` isn't in the allowed set. Roles seen in the code: `super_admin`, `admin`, `client`.
- **`@require_subscription`** — defined but not applied to any route in the current file; would 402 client-role users without an active subscription.

A fourth, unrelated auth mechanism exists for exactly one route: `POST /api/payments/reconcile` (see Payments section below) checks a static shared-secret header (`X-Cron-Secret`) instead of a session, since it's called by a cron job with no browser/session to authenticate with. It does not use any of the three decorators above.

`is_admin()` = role in `{super_admin, admin}`. `is_super_admin()` = role `== super_admin`.

`@app.before_request` (`refresh_session`) re-fetches the user's DB row at most once every 60 seconds per session, so role/active-flag changes propagate without forcing re-login — skipped for `login`, `auth_google`, `auth_callback`, `logout`, `static`, `api_prices`, `api_spot`.

**CORS**: `CORS_ORIGINS` env var (comma-separated exact origins) — must never be `"*"` (see root `CLAUDE.md`). **Cookie security** varies by env (`_PROD` flag) — see root `CLAUDE.md`'s Environments table for the full prod/staging/dev cookie matrix.

## Dynamic post-auth redirect (`?next=`)

Added 2026-08-23. One backend can be reached by multiple frontend origins (e.g. dev's Vite server *and* its CloudFront bundle). Instead of a single static `FRONTEND_URL`, the frontend appends `?next=<its own origin>` to login/logout links (`frontend/src/api/client.js`'s `authUrl()` helper); the backend validates that origin against `_CORS_ORIGINS` and, if trusted, redirects back there after auth completes instead of the static fallback. `/auth/google` stashes the validated `next` in `session["post_login_redirect"]` (survives the external round-trip to Google); `/auth/callback` consumes it via `_post_auth_redirect()`. `/logout` checks `?next=` directly (no round-trip needed). Untrusted or missing `next` falls back to `FRONTEND_URL` env var, or `"/"`.

---

## Auth routes

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/login` | — | Redirects to `FRONTEND_URL` (or `/`). Not used by the frontend's own login link (that goes straight to `/auth/google`) — closest thing to a legacy/manual entry point. |
| GET | `/auth/google` | — | Clears session, sets `session.permanent = True`, stores validated `?next=` origin, builds `redirect_uri` dynamically via `url_for("auth_callback", _external=True)` (reflects whatever scheme/host/port the request actually arrived on — see root `CLAUDE.md` for why this means multiple redirect URIs must be registered per OAuth client in non-uniform envs), redirects to Google's consent screen (Authlib, `prompt="consent"`). |
| GET | `/auth/callback` | — | Exchanges the OAuth code (`google.authorize_access_token()`); on failure (state mismatch/expired) bounces back to `/auth/google`. On success, `upsert_user(google_id, email, name, picture)` (creates or updates the user row), sets `session["user"]`. If the user is inactive (`user["active"]` false), skips setting the session and just redirects. For `client`-role users, also runs `expire_stale_subscriptions()`. Redirects via `_post_auth_redirect()`. |
| GET | `/logout` | — | Clears session, redirects to validated `?next=` or `FRONTEND_URL`/`/`. |

No client-side Google JS SDK involved anywhere — this is a pure server-side Authlib redirect flow. Google's "Authorized JavaScript origins" field is irrelevant; only "Authorized redirect URIs" matters.

## `/api/me` — current user

| Method | Path | Auth |
|---|---|---|
| GET | `/api/me` | `require_login` |

Re-verifies the session's user still exists in the DB (handles a deleted account with a stale cookie — clears session and 401s if not found). Response: `{ user: {..., setup_done: bool, subscription_valid: bool} }`. `subscription_valid` is only computed for `client` role (always `true` for admin roles).

## Users (`/api/users*`) — admin management

| Method | Path | Auth | Body / Params | Response |
|---|---|---|---|---|
| GET | `/api/users` | `require_role(super_admin, admin)` | — | `{ users: [...] }` |
| POST | `/api/users/<uid>/role` | `require_role(super_admin)` | `{ role }` — must be `super_admin`\|`admin`\|`client` | `{ ok }` or 400 |
| POST | `/api/users/<uid>/profile` | `require_login` (self or admin only, else 403) | `{ mobile, note, role? }` — `role` only applied if caller is admin | `{ ok }` |

## Subscription plans (`/api/plans*`, `/api/subscriptions`) — admin

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/api/plans` | `require_login` | — | Admins see `get_all_plans()`, others `get_active_plans()` |
| POST | `/api/plans` | `require_role(super_admin, admin)` | `{ name, description, price, duration_days, gem_cost }` | `{ ok, id }` |
| PUT | `/api/plans/<plan_id>` | `require_role(super_admin, admin)` | any of `name, description, price, gem_cost, duration_days` | `{ ok }` |
| POST | `/api/plans/<plan_id>/toggle` | `require_role(super_admin, admin)` | `{ active }` | `{ ok }` |
| GET | `/api/subscriptions` | `require_role(super_admin, admin)` | — | `{ subscriptions: [...] }` |

## Instrument search

| Method | Path | Auth | Params | Response |
|---|---|---|---|---|
| GET | `/api/search` | `require_login` | `?q=` (min 2 chars, else empty result) | `{ results: [{ label, symbol, instrument_type, instrument_key, strike, expiry_str, weekly, lot_size }] }`, top 12 from `live.fo_instruments.search_instruments()` |

## Brokers / accounts

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/api/brokers` | `require_login` | — | `{ brokers: [...] }` |
| POST | `/api/brokers` | `require_login` + admin-only (403 else) | `{ name }` | `{ ok, id }` |
| GET | `/api/accounts` | `require_login` | — | Clients see own accounts, others see all |
| POST | `/api/accounts` | `require_login`, client-role only | `{ broker_id, account_no, label, capital }` (`user_id` forced to caller for clients; capital must be > 0) | `{ ok, id }` |
| POST | `/api/accounts/<aid>/capital` | `require_login`, must own the account | `{ action: "set"\|"add", amount }` | `{ ok, capital }` |
| GET | `/api/accounts/<aid>/portfolio` | `require_login`, own account or admin | — | `{ portfolio }`, priced from `price_cache` table |

## Recommendations (admin-authored trade calls)

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| GET | `/api/recommendations` | `require_login` | — | Returns every recommendation with computed `segment` (F&O/ETF/Commodities/Equity, derived from leg instrument types), `legs`, `current_legs`, `exit_legs`, `realized_pnl` (computed from entry/exit leg price pairs), `adjustments`. |
| POST | `/api/recommendations/create` | `require_role(super_admin, admin)` | `{ symbol, legs: [...], note }` | Delegates to `live.manual_trade.add_manual_trade()`. |
| POST | `/api/recommendations/<id>/exit` | `require_role(super_admin, admin)` | `{ prices: [...] }` — one price per open entry leg, in order | Closes the trade, sends a Telegram exit alert (`live.alert.send_rec_exit_alert`) on a best-effort basis. |
| POST | `/api/recommendations/<id>/adjust` | `require_role(super_admin, admin)` | `{ note, legs: [...] }` | Adds an adjustment row, sends Telegram alert, recalculates margin (both best-effort/non-fatal on failure). |
| POST | `/api/recommendations/<id>/delete` | `require_role(super_admin, admin)` | — | Only allowed while `status == "open"`. |

`legs` bodies are normalized by `_normalize_legs()` to accept either `type`/`instrument_type` and `expiry`/`expiry_str` naming — both work.

## Account trades (client-side pushes of a recommendation to their own broker account)

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| GET | `/api/account-trades` | `require_login` | `?account_id=` optional | Clients see only their own (non-game) accounts' open trades; admins see all. Each row includes pending adjustments/exit awaiting the client's action. |
| POST | `/api/account-trades/create` | `require_login`, non-admin only, must own `account_id` | `{ recommended_trade_id?, account_id, symbol, legs, note }` | Delegates to `live.manual_trade.push_to_account()`. |
| POST | `/api/account-trades/<id>/adjust` | `require_login`, client must own the underlying account | `{ adjustment_id, adj_type, legs }` | Recalculates margin best-effort. |
| POST | `/api/account-trades/<id>/exit` | `require_login`, non-admin, must own | `{ prices: [...], note }` | Delegates to `live.manual_trade.close_account_trade()`. |
| POST | `/api/account-trades/<id>/delete` | `require_login`, non-admin, must own | — | |
| GET | `/api/account-trades/history` | `require_login` | `?account_id=` optional | Closed trades, same ownership scoping as the open-trades list. |

## Games (paper-trading contests — price prediction / MCQ / leaderboard types)

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| GET | `/api/games` | `require_login` | — | Non-admins only see `active`/`closed`/`resolved` games (not `draft`); each gets `participant_count` and, for non-admins, `my_entry`. |
| POST | `/api/games` | `require_role(super_admin, admin)` | `{ title, game_type, start_time, end_time, description?, symbol?, reward_pool?, winner_count?, initial_cash?, questions? }` | `game_type in {price_prediction, mcq, leaderboard}`. MCQ games also save `questions` via `save_game_questions()`. |
| GET | `/api/games/<id>` | `require_login` | — | Questions include the answer only for admins or a resolved game. Non-admins get partial entry visibility depending on game type/status (predictions become visible once the caller has entered; MCQ answers stay hidden). For a `closed` leaderboard game, injects live P&L as `score` from `price_cache` so the leaderboard is meaningful pre-resolution. |
| PUT | `/api/games/<id>` | `require_role(super_admin, admin)` | any of `title, description, symbol, start_time, end_time, reward_pool, winner_count, initial_cash, questions` | Only while `draft`/`active`. |
| POST | `/api/games/<id>/activate` | `require_role(super_admin, admin)` | — | `draft → active` only. |
| POST | `/api/games/<id>/close` | `require_role(super_admin, admin)` | — | `active → closed`; deactivates that game's virtual accounts and auto-exits all their open trades at current LTP (best-effort per trade, failures collected and returned). Response: `{ ok, exited: [...], failed: [...] }`. |
| POST | `/api/games/<id>/reopen` | `require_role(super_admin, admin)` | — | `closed → active`. |
| POST | `/api/games/<id>/resolve` | `require_role(super_admin, admin)` | `{ result_value? }` | Only from `closed`. Delegates to `resolve_game()`, response `{ ok, winners }`. |
| POST | `/api/games/<id>/delete` | `require_role(super_admin, admin)` | — | |
| POST | `/api/games/<id>/enter` | `require_login`, non-admin | `{ entry_data }` | Only while `active`. Leaderboard-type games also create a virtual trading account (`create_game_virtual_account`) seeded with `initial_cash`. |
| GET | `/api/games/<id>/leaderboard` | `require_login` | — | Only visible once `closed`/`resolved`, or to admins. |
| POST | `/api/games/<id>/trade` | `require_login`, non-admin, leaderboard games only | `{ symbol, action, price, quantity }` | Auto-creates an entry on first trade if the user hasn't entered yet. |
| GET | `/api/games/<id>/portfolio` | `require_login`, leaderboard games only | — | Priced from `price_cache`, scoped to the caller. |

## Credits

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/api/credits` | `require_login` | `{ balance, history }` |

## Prices / spot

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/api/prices` | `require_login` | `{ keys: [instrument_key, ...] }` | `{ ...instrumentPrices, _spot: {...}, _ts?: "..." }`. `_spot` (from `_spot_data()`, driven by `config.SPOT_IKEYS`/`SPOT_DISPLAY`) is **always included regardless of `keys`**; `_ts` only present when `keys` was non-empty. Frontend consolidated onto one shared poll of this endpoint as of 2026-08-23 — see `frontend/src/hooks/usePrices.js` and root `CLAUDE.md`. |
| GET | `/api/spot` | `require_login` | — | Same shape as `/api/prices`'s `_spot` field alone. |

## Subscriptions (client self-serve)

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| POST | `/api/subscribe` | `require_login` | `{ plan_id }` | Only free plans (`price == 0`) — paid plans return `402 Payment not yet supported` here specifically; use `/api/billing/create-order` + `/api/billing/verify-payment` (below) for paid plans instead. |
| POST | `/api/subscribe-with-credits` | `require_login` | `{ plan_id }` | Delegates to `subscribe_with_credits()`; response status is 200 if `result["ok"]` else 400. |
| GET | `/api/my-subscription` | `require_login` | — | `{ current: {...}|null, history: [...] }`. `current` = `get_user_subscription(uid)`; `history` = `get_subscription_history(uid, limit=20)`, newest first, joined to the plan's *current* name/gem_cost. Scoped to the caller only. |

## Payments (Razorpay Standard Checkout)

Lives in its own package, `backend/payments/` (Flask Blueprint, registered via a factory in `server.py` — see `docs/architecture.md` §2). Handles real-money payment for priced subscription plans; free/gem-redeemed plans go through the routes above instead, untouched by this feature.

| Method | Path | Auth | Body | Response / Notes |
|---|---|---|---|---|
| POST | `/api/billing/create-order` | `require_login` | `{ plan_id }` | 500 if Razorpay keys unset for this env. 400 if `plan_id` invalid/inactive, plan has no price, or resulting paise amount `< 100` (Razorpay's minimum). Reuses a still-`created`, non-stale (<30 min) pending order for this user+plan instead of always minting a new Razorpay order, so a retry after a stalled checkout doesn't create a duplicate. On success: `{ ok, order_id, amount, currency, key_id, plan_name }` — `key_id` is Razorpay's *public* key, safe to return to the client; `amount` is paise. **Known minor issue**: when reusing a pending order, `amount` is recomputed from the plan's *current* price rather than the order's original amount — could briefly mismatch if the price changed mid-retry-window (cosmetic; the real charge is bound server-side to the Razorpay order, unaffected). |
| POST | `/api/billing/verify-payment` | `require_login` | `{ razorpay_order_id, razorpay_payment_id, razorpay_signature }` | 500 if Razorpay keys unset. 400 if any field missing, if `razorpay_client.utility.verify_payment_signature` raises (bad/forged signature — never proceeds past this), or if the order doesn't belong to the caller (`order["user_id"] != current_user()["id"]`, anti-hijack check, returned as generic "Order not found" so as not to leak whether the order exists for someone else). On success, activates the subscription atomically and idempotently (`activate_subscription_from_payment` — a replayed call with the same `razorpay_order_id` returns `{"ok": false, "error": "Order not found or already processed"}` rather than double-activating). |
| POST | `/api/payments/reconcile` | **`X-Cron-Secret` header** (shared secret via `hmac.compare_digest` against `PAYMENTS_CRON_SECRET` env var) — **not** `require_login`/`require_role` | — | Cron-only pull-based reconciliation for orders never synced via `verify-payment` (browser closed before the callback fired, network drop, etc.). For every `payment_orders` row still `status='created'` and older than a 10-minute grace period: asks Razorpay directly whether it was actually paid, then either late-activates it (if this plan isn't already covered by an unexpired subscription for this user) or auto-refunds it as a duplicate (if it is) — no human-in-the-loop step on the refund. See `docs/prd/razorpay-subscription-billing.md` for the full dedup-logic writeup and known risks (concurrent-invocation race; no scheduler currently configured to call this endpoint). Response: `{ ok, synced: [...], duplicate_refunded: [...], still_pending: [...], errors: [...] }`. |
| GET | `/api/payments/flagged` | `require_role(super_admin, admin)` | — | `{ ok, orders: [...] }` — every `payment_orders` row with `status='duplicate_refunded'`, joined to user email and plan name, for admin audit. |

## Profile (trading-preferences onboarding)

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| GET | `/api/profile` | `require_login` | — | `{ profile }` |
| POST | `/api/profile` | `require_login` | `{ segment, risk_type, trader_type, focus, setup_done? }` | Upserts the caller's trading profile (drives `user.setup_done` used by the frontend's setup-wizard gate). |

---

## Dead / stub code found while documenting

- A comment banner `# edgevest-fe — serve React build for all non-API routes` (server.py, before `/api/subscribe`) has no route beneath it — Flask does **not** actually serve the frontend build; that's handled entirely by S3/CloudFront in every env. Looks like a leftover comment from an earlier deployment approach.
- `require_login`'s non-`/api/` branch does `redirect(url_for("index"))`, but no route is registered under the endpoint name `index` anywhere in this file — that code path would 500 (`BuildError`) if ever actually hit on a non-API GET while logged out. In practice this likely never fires since the frontend is a separate SPA and no non-API Flask routes exist for a logged-out user to hit.
- `@require_subscription` is defined but not applied to any route currently.
