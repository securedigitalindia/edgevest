# EdgeVest — Product Overview

This is a whole-product PRD describing EdgeVest as it exists today, reverse-engineered from the current codebase. It is not a proposal or a roadmap — it documents what is actually built. For feature-specific PRDs written before/alongside a new capability, see `docs/prd/`. For environment and infrastructure detail, see `docs/architecture.md`.

## Product summary

EdgeVest is an invite-only, advisory-first market intelligence platform for NSE/BSE traders. It combines a live technical-signal engine ("Drishti") that watches a small set of instruments and pushes Telegram alerts, with a web app for tracking trade recommendations, managing brokerage accounts and positions, and running paper-trading games. Access is gated behind Google OAuth — there is no public sign-up flow; the landing page explicitly states "Invite-only access."

The product frames itself around an advisor/client relationship rather than a self-serve retail trading app: the tagline is "Stock market intelligence built for serious traders," and the four features called out on the landing page are Live Signals, F&O Trade Tracking, Telegram Alerts, and Advisor Tools ("push trades to client accounts, track adjustments, manage multi-leg strategies"). The landing page lists four supported market segments — Equity, Derivatives (F&O), Commodities, Indices — though the SetupWizard onboarding flow also offers Currency and Mutual Funds as segment choices, so segment coverage in onboarding is broader than what's marketed on the landing page.

## Target users

The codebase implements three user roles (`backend/server.py`'s `require_role` checks and `/api/users/<id>/role`): `super_admin`, `admin`, and `client`. This is inferred directly from the role-gating code, not from separate documentation, but the pattern is unambiguous:

- **Admins / super-admins** — the advisor side. They can manage the user list and roles, define subscription plans (`/api/plans`), create recommendations, and (per the landing page's "Advisor Tools" pitch) push trades into client accounts and manage adjustments across multi-leg strategies. `is_admin()`/`is_super_admin()` helper functions gate this throughout `server.py`.
- **Clients** — the advisee/subscriber side. Their access to certain API calls is gated by `is_subscription_valid()` (a 402 response if no active subscription), and their session includes a computed `subscription_valid` flag. Clients receive recommendations, track their own account trades, and consume credits for game entries.

There is no evidence of a third "self-directed retail" tier — the product model looks like a boutique advisory service with a software layer on top, not an open trading platform.

## Core features

**Live signals & alerts.** A separate always-running process (`backend/poller.py live`, the "Drishti" agent) polls Upstox every 5 seconds during NSE market hours and evaluates a configured set of triggers — Supertrend crossings, EMA crossings, RSI thresholds, and confluence conditions combining several of these — against a small watchlist (`config.py`'s `SYMBOLS`: NIFTY50, BANKNIFTY, RELIANCE as of this writing). When a trigger fires, it sends a Telegram alert, optionally with an attached trade suggestion (e.g. a specific PE calendar-spread structure). This is the "Live Signals" and "Telegram Alerts" features on the landing page. The instrument coverage is deliberately narrow, not a general scanner across the whole market.

**Trade recommendations & tracking.** Admins create recommendations (`/api/recommendations/create`) with one or more legs; clients see them and can act on them. Separately, `account-trades` let a client/advisor record actual positions taken in a real brokerage account, track entries, exits, and adjustments, and see live P&L computed against polled prices. This is the "F&O Trade Tracking" and "Advisor Tools" pitch — multi-leg strategies, adjustment history, and per-account portfolio views (`/api/accounts/<id>/portfolio`).

**Paper-trading games.** A separate, lighter-weight feature (`Games.jsx`, `GameDetail.jsx`) lets admins run three types of games — `price_prediction` (🔮), `mcq` (📝 quiz), and `leaderboard` (📈) — against a slightly broader index list (NIFTY50, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX). Clients enter using credits, and results feed a leaderboard. Games have a lifecycle (`draft → active → closed → resolved`) that admins move through explicitly.

**Broker & account management.** Users can register brokers and brokerage accounts (`/api/brokers`, `/api/accounts`), set account capital, and have their portfolio computed per account. This underpins the account-trades P&L tracking above.

**Subscriptions & credits.** There's a plan system (`/api/plans`, admin-managed, with a toggle for active/inactive) and a credits system (`/api/credits`, `/api/subscribe`, `/api/subscribe-with-credits`) — new users are granted a signup credit balance (`SIGNUP_CREDITS = 99` in `config.py`) that can apparently be spent toward a subscription or toward game entries. The exact business rules of how credits convert to subscription value aren't fully clear from a surface read of the code and would need a closer look at `db/queries.py` to state precisely — flagged here as something to verify rather than asserted as fact.

**Onboarding.** First-time users go through a `SetupWizard` before reaching the main app (gated by `user.setup_done` per `frontend/CLAUDE.md`'s App.jsx auth-gate description) that collects: trading segments of interest, risk profile (conservative/moderate/aggressive), trader-vs-investor self-classification, and whether they want a self-directed, advisory/managed, or mutual-fund-focused experience. This profile data likely feeds how recommendations/content get tailored, though the consuming logic wasn't examined here.

## Non-goals / current limitations

These are observed gaps, not stated product decisions — worth treating as "not yet built" rather than "deliberately excluded," except where noted:

- Instrument coverage for live signals is narrow (3 symbols as configured today) — this is not a general-purpose market scanner.
- No public self-signup — invite-only, which is a deliberate product stance per the landing page copy, not a limitation to fix.
- The credits-to-subscription conversion mechanics aren't fully verified here (see above) — worth a closer read of `db/queries.py` before treating this section as authoritative.
- Environments: production is live; a `staging` environment is fully provisioned (S3/CloudFront/DNS/cert) but has no backend deployed yet; a `dev` environment exists for local development with a laptop-hosted backend. See `docs/architecture.md` for full detail — none of this environment work changes what the product does, only how it's built and tested.

## Environments

Production, staging, and dev environment topology, AWS resources, and the auth/deployment mechanics behind them are documented separately in `docs/architecture.md` rather than duplicated here — this PRD is scoped to product behavior, not infrastructure.
