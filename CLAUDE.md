# CLAUDE.md — EdgeVest (Root)

This is the EdgeVest monorepo. It contains two sub-projects:

```
edgevest/
├── backend/   — Python Flask API + live NSE market signal agent (Drishti)
├── frontend/  — React 18 SPA (Vite + PWA)
```

Each sub-folder has its own `CLAUDE.md` with detailed context. Read the relevant one before making changes.

## Docs

Whole-system reference docs, kept up to date with the actual codebase (not aspirational):

- `docs/PRD.md` — product summary, user roles, core features, non-goals.
- `docs/apis.md` — every Flask route: method, path, auth requirement, request/response shape.
- `docs/architecture.md` — system design, backend/frontend split, environments & deployment, auth flow.
- `docs/schema.md` — every SQLite table: columns, indexes, relationships.
- `docs/release-checklist.md` — versioning convention, backend/frontend release steps, current outstanding release items.

`docs/prd/*.md` is a separate folder for **feature-specific** PRDs (design docs written before/alongside one nontrivial feature) — check there for design context (schema decisions, non-goals, open questions) before building analysis or extensions on top of an existing feature. Don't confuse it with `docs/PRD.md` above, which is the whole-product doc.

## High-Level Architecture

- **Backend** (`backend/server.py`) — Flask REST API on port 5555. Google OAuth login, session cookies. Serves `/api/*`, `/auth/*`, `/logout`.
- **Frontend** (`frontend/`) — Vite dev server on port 5173. Proxies `/api`, `/auth`, `/logout` → `localhost:5555` in dev.
- **Poller** (`backend/poller.py live`) — separate long-running process, independent of the Flask server. Polls Upstox every 5s, sends Telegram alerts.

## Dev Setup

```bash
# Backend (terminal 1)
cd backend && source venv/bin/activate && FLASK_ENV=dev ./edgevest-web
# (or: FLASK_ENV=dev python server.py — same bind, 127.0.0.1:5555)

# Frontend (terminal 2)
cd frontend && npm run dev   # http://localhost:5173

# Poller (terminal 3, optional)
cd backend && source venv/bin/activate && python poller.py live --force
```

`FLASK_ENV` must be set explicitly — it has no smart default, and defaults to `production` if unset (loads real prod secrets locally). See **Environments** below for full detail.

## Environments

Three environments, each with its own dotenv file — `backend/.env.<FLASK_ENV>` (loaded via `load_dotenv(f".env.{FLASK_ENV}")`, `server.py:12-13`) and `frontend/.env.<vite-mode>` (Vite's built-in per-mode env loading).

| | production | staging | dev |
|---|---|---|---|
| `FLASK_ENV` | `production` | `staging` | `dev` |
| Backend env file | `backend/.env.production` | `backend/.env.staging` | `backend/.env.dev` |
| Frontend Vite mode | *(default)* | `staging` | `dev` |
| npm build script | `npm run build` | `npm run build:staging` | `npm run build:dev` |
| Frontend hosting | S3 `edgevest-frontend` + CloudFront `EN3ECQGE4B933` → `edgevest.in` / `www.edgevest.in` | S3 `edgevest-frontend-staging` + CloudFront `E3P4LNBWP838MK` → `staging.edgevest.in` | S3 `edgevest-frontend-dev` + CloudFront `E1JHFOPTMLOMJT` → `dev.edgevest.in` |
| Backend hosting | EC2 behind nginx (`api.edgevest.in`), systemd `edgevest-web.service` | reserved — **not deployed yet** | the user's own laptop, exposed as `dev-api.edgevest.in` (DNS A record → `127.0.0.1` — only resolves on whichever machine looks it up, i.e. only works for the person running it) |
| Cookie security | strict: `Secure=True`, `SameSite=None`, `Domain=.edgevest.in` | strict (same) | relaxed: `Secure=False`, `SameSite=Lax`, `Domain=None` — `server.py:34`, `_PROD = FLASK_ENV != "dev"` |

AWS account `604048703942`, via local CLI profile `default` (a separate `Chalo-ReadOnlyAccess-*` SSO profile is also configured on dev machines for an unrelated project — don't confuse the two). ACM certs for CloudFront are always requested in `us-east-1` regardless of bucket region (`ap-south-2`). No Route53 zone for `edgevest.in` exists in this AWS account — DNS is managed externally; changes go through whoever administers that.

### `dev` details

Replaced the old Vite/Flask `development` mode entirely (2026-08-23) — that mode's `.env.development` files were deleted on both sides. Don't reuse the string `"development"` for anything; `"dev"` is now what `server.py:34` checks.

- **`npm run dev` goes through Vite's own dev-server proxy** (`vite.config.js`'s `server.proxy`, unconditionally forwarding `/api`, `/auth`, `/logout` → `http://localhost:5555`), same-origin from the browser's perspective. `vite.config.js` overrides `VITE_API_URL` to relative `/api` specifically when `command === 'serve'` (i.e. only `npm run dev`), regardless of `.env.dev`'s value — this sidesteps CORS/SameSite/Private-Network-Access entirely, and is the **only fully-working local login path**.
- **`npm run build:dev`** (deployed to `dev.edgevest.in`) uses the absolute `VITE_API_URL=http://dev-api.edgevest.in:5555/api` from `.env.dev` instead, calling the local backend by its public DNS name directly. Always use the **`http://`** URL — the CloudFront `ViewerProtocolPolicy` is `allow-all` specifically so this works without TLS on the backend; `https://dev.edgevest.in` will fail every API call (mixed content — HTTPS page, plain-HTTP backend). Chrome (incl. Incognito) silently auto-upgrades the bare `http://dev.edgevest.in/` URL to HTTPS on its own — use the explicit-port form `http://dev.edgevest.in:80/` to avoid that.
- That direct `dev.edgevest.in → dev-api.edgevest.in` path **cannot fully authenticate**: Private Network Access blocks any `fetch`/`XHR` from a public-address page into a loopback target unless the page itself is HTTPS (doesn't block top-level navigations, so the OAuth handshake completes, but every API call after that is blocked).
- Google OAuth: dedicated dev client (`367386931124-rn06t20eeg05jqgp1hgnlepce5epghng.apps.googleusercontent.com`, secret in `.env.dev`) has **three** authorized redirect URIs registered on it (Google allows multiple per client) — `https://dev-api.edgevest.in/auth/callback`, `http://dev-api.edgevest.in:5555/auth/callback`, `http://localhost:5555/auth/callback` — which one Flask builds depends on how the request actually reached it (`url_for(..., _external=True)` reflects the real incoming scheme/host/port).
- Post-login/logout redirect is **dynamic**, not a single static `FRONTEND_URL`: frontend's `authUrl(path)` helper (`frontend/src/api/client.js`) appends `?next=<current origin>` to every login/logout link; `server.py`'s `/auth/google` validates it against `CORS_ORIGINS` and stashes it in session for `/auth/callback` to redirect back to (`_post_auth_redirect()`). Falls back to `FRONTEND_URL` if `next` is missing/untrusted. Works the same way for every env, not dev-specific.
- **Future plan (confirmed 2026-08-23, not started):** deploy `dev` and `staging` to two separate real servers "when the application grows more." Once off loopback, PNA/mixed-content/cross-site-cookie issues all disappear on their own — worth revisiting whether `dev`'s relaxed cookie settings are still wanted at that point.

## Key Conventions

- Backend is **never** run inside Claude sessions — user runs it separately.
- All timestamps displayed to the user must be in **IST**, never UTC.
- Auth is Google OAuth via Authlib, server-side redirect flow (`server.py` — no client-side Google JS SDK involved, so Google's "Authorized JavaScript origins" field is irrelevant; only "Authorized redirect URIs" matters). Sessions in signed Flask cookies — see the cookie-security row in **Environments** above for how strictness varies by env.
- `CORS_ORIGINS` (env var, comma-separated exact origins) must **never** be `"*"` — Flask-CORS echoes a literal `*` back when configured that way, which browsers reject outright for any credentialed (`withCredentials: true`) request, which this app always sends.
- Frontend API base: `VITE_API_URL` env var, defaults to `/api`.
- Prod: frontend is a static build (Vite), backend behind nginx with `ProxyFix`.
