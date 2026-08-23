# EdgeVest — System Architecture

## 1. System overview

EdgeVest is a two-project monorepo: a React SPA frontend and a Python Flask backend, plus a fully independent long-running poller process. All three share one SQLite database file (`backend/data/drishti.db`) as the only integration point between the request-serving API and the live market-data agent.

```
Browser
  │
  ├─ static assets ──────► S3 + CloudFront (per-env bucket/distribution)
  │
  └─ /api/*, /auth/*, /logout ──► Flask API (server.py, gunicorn in prod)
                                        │
                                        ▼
                                  SQLite (drishti.db)
                                        ▲
                                        │
                            Drishti live poller (poller.py live)
                              — independent process, 5s loop —
                                        │
                          ┌─────────────┴─────────────┐
                          ▼                             ▼
                    Upstox API                    Telegram Bot API
              (LTP, candles, option chain)         (alerts, briefs)
```

The Flask API and the poller are **never the same process** and are deployed as two separate systemd units in prod. The API only reads/writes SQLite in response to HTTP requests; it never talks to Upstox or Telegram directly. The poller only talks to Upstox/Telegram and SQLite; it never serves HTTP. Neither knows the other exists beyond the shared DB file.

## 2. Backend architecture

### Two independent processes, one DB

- **`backend/server.py`** — Flask REST API, run via `gunicorn server:app` in prod (see `backend/gunicorn.conf.py`, `bind = "127.0.0.1:5555"`, 2 workers) or `python server.py` (Werkzeug dev server, also binds `127.0.0.1:5555`) locally. Both paths go through the `backend/edgevest-web` wrapper script, which picks Flask-dev-server vs gunicorn based on `FLASK_ENV`. Serves `/api/*`, `/auth/*`, `/login`, `/logout`. Google OAuth login, session-cookie auth (see §5).
- **`backend/poller.py live`** — the Drishti live NSE market signal agent. Polls Upstox every 5s during market hours (09:15–15:30 IST), detects Supertrend/EMA/RSI crossings, dispatches Telegram alerts with optional trade suggestions, and maintains OHLCV history via Upstox's History V3 API. Also `poller.py` doubles as a CLI dispatcher for one-off commands: `bootstrap` (seed history), `sync` (gap-fill), `verify` (row-count/gap check), `init` (create tables).

### Config

`backend/config.py` is the single source of truth: `SYMBOLS` (currently `NIFTY50`, `BANKNIFTY`, `RELIANCE`), `TIMEFRAMES` (`1m`/`5m`/`15m`/`1h`/`1d`/`1wk`/`1mo`, each with its own bootstrap lookback), `TRIGGERS` (the list of active signal conditions — Supertrend crosses on 1d/1wk/1h, RSI14 1h oversold, EMA20 15m confluence alerts, a "Nifty 500-multiple" short-entry/exit strategy, an EMA20 1d down-cross → PE-calendar-spread trade suggestion), `UPSTOX_INSTRUMENT_KEYS`, `SPOT_IKEYS`/`SPOT_DISPLAY` (header-bar indices), Telegram credentials, poll intervals. Adding a trigger is purely a `TRIGGERS` list edit — no code change.

### Data pipeline

- **`backend/bootstrap/upstox_loader.py`** — `fetch_historical()`, shared by bootstrap and sync, via Upstox's History V3 API. Chunks per-timeframe lookback caps, normalizes to UTC, drops in-progress last candles.
- **`backend/sync/daily_sync.py`** — true gap-fill from `get_latest_ts()` through today; runs once daily at 16:00, triggered by the poller's EOD task, not at startup.
- Historical data loading was migrated from yfinance to Upstox (this session's commit `0f9a56b`) — `backend/bootstrap/yfinance_loader.py` deleted, `upstox_loader.py` added. Motivation per `backend/CLAUDE.md`: yfinance silently missed at least one ad-hoc NSE special session (2026-02-01 Union Budget Sunday trading), which diff-based gap detection couldn't catch after the fact; Upstox is a direct exchange feed.

### Signal/trigger engine (`backend/live/`)

- **`triggers.py`** — trigger classes (`SupertrendCrossTrigger`, `EmaCrossTrigger`, `RsiThresholdTrigger`, `ConfluenceCrossTrigger`, `Nifty500MultipleTrigger`), all built from `config.TRIGGERS` via `build_trigger()`. `BaseTrigger` handles cooldown + trade-suggestion dispatch.
- **`signal_engine.py`** — pure indicator compute functions (`compute_supertrend`, `compute_ema`, `compute_rsi`).
- **`candle_builder.py`** — builds 1h candles from ticks at each `:15` IST boundary.
- **`trade_suggestions.py`** — trade-suggestion template functions (PE calendar spreads, the 500-multiple short entry/exit) attached to triggers via config.
- **`expiry.py`** — `ExpiryCache`, NSE option expiry dates from Upstox `OptionsApi`.
- **`alert.py` / `briefing.py`** — Telegram dispatch (per-signal alerts, morning/EOD briefs).
- **`holidays.py`** — BSE/NSE trading-day calendar via `exchange-calendars`.

## 3. Frontend architecture

React 18 SPA, Vite + `vite-plugin-pwa` (auto service worker, `NetworkFirst` for `/api/*` with a 5s timeout fallback to cache). No CSS framework — colocated `.css` files.

- **State**: TanStack Query v5 for all server state (no manual fetch/`useEffect`); Zustand for auth (`store/authStore.js` — `{user, ready}`) and, as of this session, for cross-component price-key coordination (`store/priceKeysStore.js`, see §6).
- **API layer**: `src/api/client.js` — single axios instance, `baseURL = VITE_API_URL || '/api'`, `withCredentials: true`, error interceptor normalizes failures to `{ok: false, error}` instead of throwing. Per-domain modules (`auth.js`, `games.js`, `prices.js`, `trades.js`, `settings.js`) wrap individual endpoints.
- **Routing**: React Router v7 — `/` → `/dashboard`, `/dashboard`, `/games`, `/games/:id`, catch-all → `/dashboard`.
- **Auth gate** (`App.jsx` via `useMe`): `Landing` if not logged in → `SetupWizard` if `!user.setup_done` → full shell (nav + routes) otherwise. Subscription gate via `user.subscription_valid`.
- **Screens**: `Dashboard` (positions, recommendations, P&L, instrument search), `Games` (paper-trading games list) + `GameDetail`, `Landing`, `SetupWizard`.
- **Key components**: `TickerStrip` (live index prices in the header, polls the shared price query), `MainNav` (top nav + `SettingsDrawer` trigger), `SettingsDrawer` (profile/broker/account tabs).

## 4. Environments & deployment

Three environments, each with its own dotenv file (`backend/.env.<FLASK_ENV>`, loaded via `load_dotenv(f".env.{FLASK_ENV}")`, `server.py:12-13`) and its own Vite mode (`frontend/.env.<mode>`). Full day-to-day detail is in root `CLAUDE.md`'s Environments section; this is the architectural summary.

| | production | staging | dev |
|---|---|---|---|
| `FLASK_ENV` | `production` | `staging` | `dev` |
| Frontend hosting | S3 `edgevest-frontend` + CloudFront `EN3ECQGE4B933` → `edgevest.in`/`www.edgevest.in` | S3 `edgevest-frontend-staging` + CloudFront `E3P4LNBWP838MK` → `staging.edgevest.in` | S3 `edgevest-frontend-dev` + CloudFront `E1JHFOPTMLOMJT` → `dev.edgevest.in` |
| Backend hosting | EC2 behind nginx (`api.edgevest.in`), systemd `edgevest-web.service` (gunicorn) + `edgevest-poller.service` | reserved, **not deployed** — intended as a true prod-replica once given a real backend server | the developer's own laptop, exposed as `dev-api.edgevest.in` (DNS A record → `127.0.0.1`) |
| Cookie security | strict — `Secure=True`, `SameSite=None`, `Domain=.edgevest.in` | strict (same) | relaxed — `Secure=False`, `SameSite=Lax`, `Domain=None` (`server.py:34`, `_PROD = FLASK_ENV != "dev"`) |

All AWS resources live in account `604048703942`, CLI profile `default` (a separate `Chalo-ReadOnlyAccess-*` SSO profile also exists on dev machines for an unrelated project). ACM certs for CloudFront are requested in `us-east-1` regardless of S3 bucket region (`ap-south-2`). No Route53 zone for `edgevest.in` exists in this AWS account — DNS is managed externally.

Prod deployment topology (`backend/deploy/nginx.conf`): nginx reverse-proxies `api.edgevest.in` → `127.0.0.1:5555` (gunicorn), passing `X-Forwarded-Proto`/`X-Real-IP`, consumed by Flask's `ProxyFix` middleware so `url_for(_external=True)` generates correct `https://` URLs. `edgevest-web.service` and `edgevest-poller.service` both run as systemd units under user `ubuntu`, `WorkingDirectory=/home/ubuntu/edgevest/backend`, each loading `.env.production` via `EnvironmentFile=/home/ubuntu/edgevest/backend/.env.production` (fixed 2026-08-23 — `edgevest-web.service` previously pointed one directory too shallow, at `/home/ubuntu/edgevest/.env.production`; if the prod server's actual installed unit file still has the old path, it needs to be redeployed there too, not just fixed in this repo).

### `dev`-specific architecture notes

- `npm run dev` (Vite dev server, `localhost:5173`) routes API calls through Vite's own dev-server proxy (`vite.config.js`, `/api`,`/auth`,`/logout` → `http://localhost:5555`), same-origin from the browser's perspective — `vite.config.js` overrides `VITE_API_URL` to relative `/api` specifically when Vite's `command === 'serve'`. This is the only fully-working local login path.
- `npm run build:dev` (deployed to `dev.edgevest.in`) instead uses the absolute `VITE_API_URL=http://dev-api.edgevest.in:5555/api` from `.env.dev`, calling the laptop backend directly by its public DNS name. Must be accessed via `http://`, not `https://` — CloudFront's `ViewerProtocolPolicy` is `allow-all` specifically to permit this, since the backend has no TLS.
- That direct `dev.edgevest.in → dev-api.edgevest.in` path **cannot fully authenticate**: Chrome's Private Network Access (PNA) policy blocks any `fetch`/`XHR` from a public-address-space page into a loopback target unless the page itself is a secure context (HTTPS). It does not block top-level navigations, so the OAuth handshake itself completes, but every subsequent API call is blocked.
- Future plan (not started): deploy `dev` and `staging` to two separate real servers once the app grows further — off loopback, PNA/mixed-content/cross-site-cookie issues all disappear, and dev's relaxed cookie settings may no longer be needed.

## 5. Auth architecture

Google OAuth 2.0, **server-side authorization-code flow via Authlib** (`authlib.integrations.flask_client.OAuth`) — not Google's client-side JS SDK. The frontend's "Sign in with Google" control is a plain `<a href>` link to `/auth/google`; no JS ever talks to Google directly, so Google Cloud Console's "Authorized JavaScript origins" field is irrelevant here — only "Authorized redirect URIs" matters.

Flow: `/auth/google` → `google.authorize_redirect(redirect_uri, ...)` (redirect_uri built dynamically via `url_for("auth_callback", _external=True)`, reflecting whatever scheme/host/port the incoming request actually used) → Google consent → `/auth/callback` → `google.authorize_access_token()` → `upsert_user()` → `session["user"] = user`.

**Dynamic post-login/logout redirect** (added this session, `server.py`): rather than a single static `FRONTEND_URL`, the frontend's `authUrl(path)` helper (`client.js`) appends `?next=<current origin>` to every login/logout link. `/auth/google` validates `next` against `_CORS_ORIGINS` and stashes it in session; `/auth/callback` consumes it via `_post_auth_redirect()`. Falls back to the static `FRONTEND_URL` if `next` is missing/untrusted. This lets one backend process correctly serve multiple frontend origins (e.g. dev's Vite server and its CloudFront bundle) without hardcoding one.

Session cookie config (`server.py:34-38`) varies by `_PROD` flag (see §4's table) but always: `HTTPONLY=True`, 30-day `PERMANENT_SESSION_LIFETIME`.

## 6. Known architectural quirks / tradeoffs

- **`dev`'s relaxed cookies are a loopback-only workaround**, not a general pattern — `SameSite=Lax`/`Secure=False` only works because `npm run dev`'s proxy keeps everything on the same "site" (`localhost`, cookie matching ignores port). It would not be safe or sufficient once the backend moves to a real server.
- **`staging` is fully provisioned but unused** — S3, CloudFront, and an issued ACM cert all exist for `staging.edgevest.in`, deliberately idle until a real backend server is stood up for it.
- **PNA blocks `dev.edgevest.in`'s direct backend calls** — see §4; this is a browser platform restriction, not fixable via CORS/backend config, only by adding real TLS to the loopback-exposed backend.
- **Price polling was consolidated this session** — `TickerStrip`, `Dashboard` (twice), and `GameDetail` (twice) each used to run independent `/api/prices` polls. Now all funnel through one shared TanStack Query in `hooks/usePrices.js`, keyed by the *union* of every mounted consumer's needed instrument keys (tracked in the new `store/priceKeysStore.js` Zustand store, updated via `useEffect` per consumer). `useRecPrices` in `hooks/useTrades.js` is now just an alias for `useTrackedPrices`, kept for call-site compatibility. Backend's `POST /api/prices` always returns `_spot` regardless of the `keys` payload, which is what makes the union-based single-query approach work — one request satisfies both the global ticker and any screen-specific instrument prices.
- **Prod backend has a hardcoded fallback secret in `config.py`** (`UPSTOX_ACCESS_TOKEN` default value, `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are always hardcoded, not env-driven) — pre-existing, not touched this session, worth flagging for anyone doing a security pass.
