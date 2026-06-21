# CLAUDE.md — EdgeVest Frontend

React 18 SPA built with Vite. Advisory-first market intelligence UI for the EdgeVest platform.

## Stack

- **React 18** + React Router v7
- **TanStack Query v5** — all server state, no manual fetch/useEffect for data
- **Zustand** — auth state only (`authStore.js`)
- **Axios** — HTTP client (`src/api/client.js`)
- **Vite** + `vite-plugin-pwa` — PWA, auto service worker
- No CSS framework — plain CSS files per component/screen

## Commands

```bash
npm run dev      # dev server on :5173 (proxies /api → :5555)
npm run build    # production build
npm run preview  # preview prod build
npm run lint     # eslint
```

## Project Structure

```
src/
├── api/           — API modules (one per domain)
│   ├── client.js  — axios instance, base URL, error interceptor
│   ├── auth.js
│   ├── games.js
│   ├── prices.js
│   ├── settings.js
│   └── trades.js
├── components/
│   ├── common/    — Toast.jsx, ErrorBoundary.jsx
│   ├── drawer/    — SettingsDrawer.jsx (profile, brokers, accounts tabs)
│   ├── games/     — GameDetail.jsx
│   └── nav/       — MainNav.jsx, TickerStrip.jsx
├── hooks/         — useMe, useTrades, useGames, usePrices, useSettings (TanStack Query)
├── screens/
│   ├── Dashboard.jsx  — main trading UI (positions, recommendations, P&L)
│   ├── Games.jsx      — paper trading games
│   ├── Landing.jsx    — unauthenticated landing / login
│   └── SetupWizard.jsx — first-time user onboarding
├── store/
│   └── authStore.js   — Zustand: { user, ready } + setUser()
├── App.jsx        — routing shell, auth gate, setup gate
└── main.jsx       — React root
```

## Auth Flow

`useMe` hook (`hooks/useMe.js`) calls `GET /api/me` on mount → sets Zustand `authStore`. App renders:
- `Landing` if `!user`
- `SetupWizard` if `!user.setup_done`
- Full shell (nav + routes) otherwise

Subscription gate: `user.subscription_valid !== false` — passed as `subscribed` prop into Dashboard/Games.

## Routing

| Path | Screen |
|---|---|
| `/` | redirect → `/dashboard` |
| `/dashboard` | Dashboard |
| `/games` | Games list |
| `/games/:id` | Game detail |
| `*` | redirect → `/dashboard` |

## API Conventions

- All API calls go through `src/api/client.js` (axios instance, `baseURL=/api`, `withCredentials:true`)
- Error interceptor returns `{ ok: false, error: msg }` instead of throwing — callers check `data.ok`
- `VITE_API_URL` env var overrides base in prod (e.g. `https://api.edgevest.in/api`)

## Key Components

- **TickerStrip** — live price ticker at top, polls `/api/spot`
- **MainNav** — top nav, hamburger → opens `SettingsDrawer`
- **SettingsDrawer** — profile/broker/account settings in a slide-over
- **Dashboard** — positions table, recommendations, P&L summary, instrument search typeahead
- **Games** — paper trading games list + GameDetail

## PWA

Configured in `vite.config.js`. Service worker caches static assets; `/api/*` uses `NetworkFirst` with 5s timeout fallback to cache.

## Conventions

- No CSS framework — colocated `.css` files per component
- TanStack Query keys: `['me']`, `['recs']`, `['trades']`, `['games']`, etc.
- `fmtRs(v)` / `fmtPnl(v)` helper functions for INR formatting in Dashboard
- App version from `package.json` via `__APP_VERSION__` Vite define — shown in profile menu
