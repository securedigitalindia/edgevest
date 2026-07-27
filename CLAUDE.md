# CLAUDE.md — EdgeVest (Root)

This is the EdgeVest monorepo. It contains two sub-projects:

```
edgevest/
├── backend/   — Python Flask API + live NSE market signal agent (Drishti)
├── frontend/  — React 18 SPA (Vite + PWA)
```

Each sub-folder has its own `CLAUDE.md` with detailed context. Read the relevant one before making changes.

## High-Level Architecture

- **Backend** (`backend/server.py`) — Flask REST API on port 5555. Google OAuth login, session cookies. Serves `/api/*`, `/auth/*`, `/logout`.
- **Frontend** (`frontend/`) — Vite dev server on port 5173. Proxies `/api`, `/auth`, `/logout` → `localhost:5555` in dev.
- **Poller** (`backend/poller.py live`) — separate long-running process, independent of the Flask server. Polls Upstox every 5s, sends Telegram alerts.

## Dev Setup

```bash
# Backend (terminal 1)
cd backend && source venv/bin/activate && python server.py

# Frontend (terminal 2)
cd frontend && npm run dev

# Poller (terminal 3, optional)
cd backend && source venv/bin/activate && python poller.py live --force
```

## Key Conventions

- Backend is **never** run inside Claude sessions — user runs it separately.
- All timestamps displayed to the user must be in **IST**, never UTC.
- Auth is Google OAuth; sessions stored in signed Flask cookies (`SESSION_COOKIE_DOMAIN=.edgevest.in` in prod).
- Frontend API base: `VITE_API_URL` env var, defaults to `/api`.
- Prod: frontend is a static build (Vite), backend behind nginx with `ProxyFix`.
