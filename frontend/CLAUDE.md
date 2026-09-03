# CLAUDE.md — EdgeVest Frontend

React 18 SPA built with Vite. Advisory-first market intelligence UI for the EdgeVest platform.

## Stack

- **React 18** + React Router v7
- **TanStack Query v5** — all server state, no manual fetch/useEffect for data
- **Zustand** — auth state only (`authStore.js`)
- **Axios** — HTTP client (`src/api/client.js`)
- **Vite** + `vite-plugin-pwa` — PWA, auto service worker
- No CSS framework for existing pages — plain CSS files per component/screen. **New pages only** may opt into Tailwind + shadcn/ui (`src/components/ui/*`, `src/styles/shadcn.css`) by wrapping their root in `<div className="sc-scope">` — see that file's header comment for why it's scoped this way and never migrate an existing page's plain-CSS styling to it without being asked.

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
│   ├── billing.js
│   ├── games.js
│   ├── prices.js
│   ├── settings.js
│   └── trades.js
├── components/
│   ├── common/    — Toast.jsx, ErrorBoundary.jsx, PageHeader.jsx (back-button + title bar, used by Positions + all /profile/* pages), Icons.jsx (Bank/Game/Chevron/Plus/Trend — shared by Positions' AccountPicker and profile/MyAccounts)
│   ├── games/     — GameDetail.jsx
│   ├── nav/       — MainNav.jsx (top + bottom nav, 4 peer tabs), TickerStrip.jsx
│   ├── trades/    — InstrumentSearch.jsx, LegBuilder.jsx, legHelpers.js (newLeg/collectLegs) — shared by Trades' rec forms and Positions' New Trade form
│   └── ui/        — shadcn/ui primitives (button/card/dialog/dropdown-menu/tabs/input/label) — new pages only, see Stack above; no current callers until a new page adopts them
├── hooks/         — useMe, useTrades, useGames, usePrices, useSettings, useBilling (TanStack Query)
├── screens/
│   ├── Dashboard.jsx    — overview/home: active-trades count, monthly report summary, refer-and-earn promo, live games teaser
│   ├── Trades.jsx       — Recommended Positions (admin-authored recs, push-to-account, adjust/exit)
│   ├── Positions.jsx    — "My Positions" / "All Positions" (admin): open/history tabs, account switcher, new-trade form
│   ├── Games.jsx        — paper trading games
│   ├── Landing.jsx      — unauthenticated landing / login
│   ├── SetupWizard.jsx  — first-time user onboarding
│   └── profile/         — account settings, one screen per route (replaces the old SettingsDrawer)
│       ├── ProfileHub.jsx       — /profile menu: identity header + role-branched links
│       ├── ProfileDetails.jsx   — identity, mobile, trading-preference chips
│       ├── MyPlan.jsx           — client: current subscription + history
│       ├── MyAccounts.jsx       — client: brokerage accounts + capital
│       ├── Gems.jsx             — client: gem balance + transaction history
│       ├── Referrals.jsx        — all roles: referral code/link, share, referral history
│       ├── Reports.jsx          — all roles: monthly recommendation report (margin/P&L)
│       ├── Brokers.jsx          — admin: broker list
│       ├── Users.jsx            — admin: user management
│       ├── Plans.jsx            — admin: subscription plan editor
│       ├── Subscriptions.jsx    — admin: all users' subscriptions
│       └── Payments.jsx         — admin: all Razorpay payment orders (paid/pending/refunded), filterable, cross-linked from Users/Subscriptions by email
├── store/
│   └── authStore.js   — Zustand: { user, ready } + setUser()
├── styles/
│   └── shadcn.css     — Tailwind + shadcn tokens, .sc-scope-gated (see Stack above)
├── lib/
│   └── utils.js       — shadcn's cn() class-merge helper (new pages only)
├── utils/
│   └── format.js      — fmtRs/fmtPnl/fmtQty/fmtIstShort, shared by Dashboard, Trades, Positions, profile screens
├── App.jsx        — routing shell, auth gate, setup gate
└── main.jsx       — React root
```

## Auth Flow

`useMe` hook (`hooks/useMe.js`) calls `GET /api/me` on mount → sets Zustand `authStore`. App renders:
- `Landing` if `!user`
- `SetupWizard` if `!user.setup_done`
- Full shell (nav + routes) otherwise

Subscription gate: `user.subscription_valid !== false` — passed as `subscribed` prop into Trades/Games.

## Routing

Bottom nav (mobile, ≤768px) / top nav (desktop) has 5 peer tabs: `Dashboard | Trades | Positions | Games | Profile`. Admin-only `/profile/*` routes self-guard with `if (!isAdmin) return <Navigate to="/profile" replace />`.

| Path | Screen | Notes |
|---|---|---|
| `/` | redirect → `/dashboard` | |
| `/dashboard` | Dashboard | Overview: active-trades count, monthly summary, refer-and-earn promo, games teaser |
| `/trades` | Trades | Recommended Positions (or `NoSubscriptionGate`) |
| `/positions` | Positions | "My Positions" (client) / "All Positions" (admin) |
| `/games` | Games list | |
| `/games/:id` | Game detail | |
| `/profile` | ProfileHub | menu, role-branched |
| `/profile/details` | ProfileDetails | all roles |
| `/profile/plan` | MyPlan | client only |
| `/profile/accounts` | MyAccounts | client only |
| `/profile/gems` | Gems | client only |
| `/profile/referrals` | Referrals | all roles |
| `/profile/reports` | Reports | all roles |
| `/profile/brokers` | Brokers | admin only |
| `/profile/users` | Users | admin only |
| `/profile/plans` | Plans | admin only |
| `/profile/subscriptions` | Subscriptions | admin only |
| `/profile/payments` | Payments | admin only; accepts `?u=<email>` to pre-filter |
| `*` | redirect → `/dashboard` | |

## API Conventions

- All API calls go through `src/api/client.js` (axios instance, `baseURL=/api`, `withCredentials:true`)
- Error interceptor returns `{ ok: false, error: msg }` instead of throwing — callers check `data.ok`
- `VITE_API_URL` env var overrides base in prod (e.g. `https://api.edgevest.in/api`)

## Key Components

- **TickerStrip** — live price ticker at top, polls `/api/spot`
- **MainNav** — top nav + mobile bottom nav, 5 peer tabs (Dashboard/Trades/Positions/Games/Profile), avatar dropdown (Profile link + Sign out)
- **Dashboard** — overview/home: active-trades count card (→ Trades), monthly report summary, refer-and-earn promo card, live games teaser
- **Trades** — Recommended Positions (admin-authored, with instrument search typeahead for building recs)
- **Positions** — the user's own open/closed positions, account switcher, new-trade ticket
- **profile/*** — account settings screens (identity, plan, accounts, gems for clients; brokers/users/plans/subscriptions for admins), replacing the old `SettingsDrawer`
- **Games** — paper trading games list + GameDetail

## PWA

Configured in `vite.config.js`. Service worker caches static assets; `/api/*` uses `NetworkFirst` with 5s timeout fallback to cache.

## Conventions

- No CSS framework — colocated `.css` files per component (Tailwind/shadcn is the one exception, `.sc-scope`-gated, new pages only — see Stack above)
- TanStack Query keys: `['me']`, `['recs']`, `['trades']`, `['games']`, etc.
- `fmtRs(v)` / `fmtPnl(v)` / `fmtQty(...)` / `fmtIstShort(ts)` helpers in `src/utils/format.js`, shared across screens
- App version from `package.json` via `__APP_VERSION__` Vite define — shown in the avatar dropdown and on `/profile`
