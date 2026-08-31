# Bond / FD Yield Screener

## Problem

The founder is looking for ways to grow user interest/demand for EdgeVest without pulling the product further into a regulated-advisory category than the existing F&O recommendation business already sits in — recommending *specific* mutual funds or bonds would edge toward SEBI Investment Adviser/RA territory. One low-regulatory-risk idea from that discussion: give users a place to compare public fixed-income yields (G-Sec, listed corporate bonds, bank FDs) side by side, purely as reference data — not as a recommendation of what to buy. Today EdgeVest has no fixed-income content at all; everything in the product (Trades, Positions, Games) is F&O-specific, and there is no reference/comparison data of any kind, regulated or otherwise.

## Goal

A screen where any user can browse and compare a small, curated set of fixed-income yield data points — G-Sec yields, NSE-listed corporate bond yields, bank FD rates — grouped by instrument type, with issuer, tenure, yield/rate, credit rating (where applicable), and an "as of" date so staleness is visible. Nothing on the screen suggests a specific instrument to buy, links to a purchase flow, or is personalized to the viewing user in any way. "Done" looks like: an admin can add/edit/retire yield entries through an in-app editor, and any user can view the resulting list/comparison — informational only, same spirit as a newspaper's rate-comparison table.

## Non-goals

- **No personalized recommendation of which bond/FD to buy.** This is the entire point of staying regulatory-light — see Problem. No "recommended for you," no ranking algorithm, no user-risk-profile-based filtering that implies advice.
- **No buy/sell facilitation.** No links to purchase a bond/FD, no brokerage integration for fixed income, no "invest now" button. `backend/live/`'s F&O machinery (Upstox order/margin APIs) is not extended to this feature in any way.
- **No portfolio-linking.** This screener never reads from or writes to `accounts`/`account_trades`/`account_trade_legs` — it doesn't know what any user actually holds, and doesn't try to. A separate "portfolio aggregation" idea has apparently already been scoped elsewhere per the founder's framing; this PRD does not touch that ground.
- **No live/real-time yield feed in v1.** See Data source strategy below — this is the central open risk of the whole feature, not a detail to wave through.
- **No scraping of bank/exchange websites.** Flagged explicitly as fragile and likely ToS-violating, not proposed as a real option here even though it's technically possible.
- **No education/explainer content** (what is a G-Sec, how does YTM work, etc.) bundled into this feature — if the separately-scoped education-content idea materializes, it can link to or sit alongside this screener, but this PRD's scope is the data table itself.

## Data source strategy — the central open risk

**There is no existing data source for bond yields or FD rates anywhere in this codebase, and this PRD cannot confirm one exists that EdgeVest could use.** This needs to be treated as the load-bearing constraint on the whole feature, not smoothed over.

### What the codebase actually has today

- `backend/live/upstox_client.py` wraps three Upstox APIs: `MarketQuoteApi` (`get_ltp`), `ChargeApi` (`get_margin`, `get_brokerage`), `HistoryV3Api` (`get_historical_candles`). Every instrument key ever passed through this client, anywhere in the codebase, is `NSE_INDEX|...`, `NSE_EQ|...` (ISIN-based), or an F&O contract key resolved via `live/expiry.py`'s `ExpiryCache` — i.e. equity, index, and derivatives segments only.
- `backend/config.py`'s `UPSTOX_INSTRUMENT_KEYS` and `SPOT_IKEYS` — the two places instrument coverage is declared — contain no G-Sec, corporate-bond, or debt-segment entries. `config.py`'s own comment on how to find an instrument key ("download NSE instrument list from `assets.upstox.com/.../instruments/exchange/NSE.json.gz`, look up `instrument_key`") implies the mechanism *could* extend to other NSE-listed instrument types if Upstox's instrument master includes them — but nothing in this repo has ever exercised that path for debt instruments, so whether Upstox's retail LTP/history APIs actually carry G-Sec or listed-corporate-bond quotes (as opposed to just equity/index/F&O) is **unverified**. This needs a spike — pull the NSE instrument master file and check whether it lists a debt/WDM segment with usable instrument keys, then test whether `get_ltp`/`get_historical_candles` actually return data for one — before any "maybe we can pull this live" plan is taken seriously.
- Bank FD rates have no unified public API in India at all, Upstox or otherwise — each bank publishes its own rate card on its own site, in its own format, updated on its own schedule. There is no realistic path to a live feed for this piece specifically, regardless of what the G-Sec spike above finds.

### v1: admin-curated, not polled

Given the above, v1 must be a small, manually-curated dataset that an admin enters and periodically updates by hand — **not** a `live/poller.py`-style 5-second polling feed, and not a `bootstrap`/`sync`-style scheduled fetch job. There is no data provider integration to build in v1. This mirrors `subscription_plans` in this codebase — an admin-managed reference table with no external sync — far more than it resembles anything in `live/` or `bootstrap/`.

Concretely: an admin manually looks up current G-Sec yields (e.g. from RBI's own published data — not independently verified as machine-readable/API-accessible in this research pass, only asserted as the natural human source), representative NSE-listed corporate bond yields, and published bank FD card rates, and types them into an admin editor (see Mechanics below), the same way an admin today types a plan's price into `Plans.jsx`. Freshness is only as good as how often an admin bothers to update it — the `as_of_date` field exists specifically so users can see how stale a number is rather than assume it's live.

### Future path, if a real source is found

If the spike above finds that Upstox (or some other provider) genuinely exposes machine-readable G-Sec/bond quotes, a v2 could poll that subset on a slow cadence (e.g. daily, not 5s) into the same table this PRD defines, replacing manual entry for that instrument type only — FD rates would still need manual curation regardless, since no such feed exists for them under any provider. This is explicitly a "maybe later, pending a spike that hasn't happened yet" note, not a commitment, and not something to build toward speculatively in v1.

## Mechanics / behavior

### Instrument types

Three types, matching the founder's framing exactly:

| Type | Example | Issuer field means | Credit rating applies? |
|---|---|---|---|
| `g_sec` | 10-Year Government Security | "Government of India" (effectively constant) | No — sovereign, no rating needed |
| `corporate_bond` | NSE-listed NCD | Issuing company (e.g. "HDFC Ltd") | Yes — CRISIL/ICRA/CARE rating, e.g. `AAA` |
| `bank_fd` | Fixed deposit | Bank name | No, or bank's own deposit-insurance-adjacent framing (DICGC covers ₹5L per depositor per bank — informational note, not a "rating" field) |

### Screen layout (client-facing)

- Grouped by instrument type (three sections or a type filter/tab), each a sortable list: issuer, tenure, yield/rate %, credit rating (blank for `g_sec`/`bank_fd`), as-of date.
- Default sort within a group: yield/rate descending (most useful comparison view) — sortable by tenure or issuer too, no strong opinion locked here.
- Every row shows its `as_of_date` inline (e.g. "as of 15 Aug 2026") — this is the anti-staleness signal, not optional/hidden-in-a-tooltip.
- A persistent, non-dismissible disclaimer at the top of the screen: this is publicly available reference information, not a recommendation, not a solicitation to buy, and not personalized to the viewer. Exact copy is a legal/compliance question (see Open questions), but the presence of *some* disclaimer, always visible, is a hard requirement given the whole feature's regulatory-light framing depends on the informational-only boundary being clear to the user, not just true in the backend.
- No per-instrument detail page, no charting, no historical-yield trend in v1 — a flat comparison table is the entire v1 scope.

### Admin editor

Follows `frontend/src/screens/profile/Plans.jsx`'s pattern directly — the existing precedent in this codebase for "admin inline-edits a small reference table": a list of existing entries with click-to-edit fields (Plans does this for `price`/`gem_cost` via `editPrice`/`editGem` state objects and per-row Save/Cancel), plus a "New Entry" form at the bottom for adding a row, plus an active/inactive toggle (`togglePlan`'s pattern) for retiring a stale entry without deleting its history. No bulk import/CSV upload in v1 — entries are few enough (a curated list, not hundreds of instruments) that one-row-at-a-time editing is proportionate, matching how `Plans.jsx` handles what's presumably also a short list.

## Architecture impact

This is additive and does not touch `live/`, `bootstrap/`, `sync/`, or any existing table. Nothing in `backend/live/poller.py`'s daily lifecycle changes.

### Backend

- **New table** — `backend/db/init_db.py`: add a `CREATE TABLE IF NOT EXISTS yield_entries (...)` block (see Data model below) plus its indexes, in the same idempotent style every other table in this file uses. No migration-loop concerns since this is a brand-new table, not an ALTER on an existing one.
- **New routes**, `backend/server.py`, following the exact `GET`/`POST`/`PUT`/toggle shape `subscription_plans` already uses (`/api/plans`, `/api/plans/<id>`, `/api/plans/<id>/toggle`, `server.py:347-389`):
  - `GET /api/yields` — `@require_login` (see Open questions on whether this should be public/unauthenticated instead), returns all `active=1` entries grouped or flat (frontend groups client-side, same as `Trades`/`Positions` do for their own lists).
  - `POST /api/yields` — `@require_role("super_admin", "admin")`, create a new entry.
  - `PUT /api/yields/<id>` — `@require_role("super_admin", "admin")`, edit an existing entry (yield/rate, as_of_date, etc.).
  - `POST /api/yields/<id>/toggle` — `@require_role("super_admin", "admin")`, active/inactive, mirrors `togglePlan`.
- **`backend/db/queries.py`** — new functions `get_yield_entries(active_only=True)`, `create_yield_entry(...)`, `update_yield_entry(id, **fields)`, `toggle_yield_entry(id, active)`. SQL stays here per this file being "the only file with SQL" (`backend/CLAUDE.md`).
- No changes to `backend/config.py`, `backend/live/*`, `backend/bootstrap/*`, or `backend/sync/*` in v1 — there is genuinely nothing for the poller to do here.

### Frontend

- **New admin screen**, e.g. `frontend/src/screens/profile/YieldsAdmin.jsx` (naming TBD) — self-guards `if (!isAdmin) return <Navigate to="/profile" replace />`, `<PageHeader>`, styled per `Plans.jsx`'s inline-edit pattern described above. Route `/profile/yields-admin` (or similar) alongside the other admin `/profile/*` routes in `App.jsx`, entry added to `ProfileHub.jsx`'s Admin section (`Brokers`/`Users`/`Plans`/`Subscriptions`).
- **New client-facing screen** for the comparison view itself — placement is a genuinely open IA question (see Mechanics and Open questions), but the closest existing precedent is `Reports.jsx`: an "all roles, no admin gate" screen living under `/profile` (`ProfileHub.jsx`'s common section, alongside "Monthly Report", not the admin-only section below it). Recommending the same pattern here as a starting point — a `/profile/yields` screen visible to every logged-in role — while flagging in Open questions whether the founder wants this surfaced more prominently (e.g. a Dashboard card/teaser, matching the "games teaser" pattern already on `Dashboard.jsx`) given its explicit purpose is user growth/engagement, not admin bookkeeping like `Reports`.
- **Not** a 6th top-level nav tab — no change to `MainNav.jsx`'s five peer tabs (Dashboard/Trades/Positions/Games/Profile), consistent with how the parallel education-content idea is also being kept out of top-level nav per the same discussion.
- New hook(s) in a new `frontend/src/hooks/useYields.js` (TanStack Query, matching every other data-fetching convention in this codebase — `frontend/CLAUDE.md`'s "no manual fetch/useEffect for data" rule), query key `['yields']`.
- New API module `frontend/src/api/yields.js`, one per domain per existing convention (`api/trades.js`, `api/games.js`, etc.).

## Data / storage

### `yield_entries` (new table)

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `instrument_type` | TEXT NOT NULL | `g_sec` \| `corporate_bond` \| `bank_fd` |
| `issuer_name` | TEXT NOT NULL | e.g. "Government of India", "HDFC Ltd", "State Bank of India" |
| `instrument_label` | TEXT NOT NULL | Free-text display name, e.g. "10-Year G-Sec", "SBI FD 1-2 Year" |
| `tenure_label` | TEXT NOT NULL | Free-text tenure, e.g. "10 years", "1–2 years" — bonds/FDs don't share one tenure convention, so this is deliberately not a rigid enum |
| `tenure_months` | INTEGER | Nullable numeric equivalent, for sorting only — not always cleanly derivable from `tenure_label` (e.g. a range), admin enters best-effort |
| `yield_pct` | REAL NOT NULL | The rate/yield itself, as a percentage (e.g. `7.15`) |
| `credit_rating` | TEXT | Nullable — populated for `corporate_bond`, left null for `g_sec`/`bank_fd` |
| `min_investment` | REAL | Nullable, informational only (e.g. FD minimum deposit) |
| `source_note` | TEXT | Free text — where the admin got this number and when (e.g. "RBI published G-Sec yields, checked 2026-08-30") — audit trail, not shown to end users necessarily (display decision TBD) |
| `as_of_date` | TEXT NOT NULL | ISO date the rate was verified/entered — **this is user-facing**, the anti-staleness signal described in Mechanics |
| `active` | INTEGER NOT NULL DEFAULT 1 | Soft-hide, same pattern as `subscription_plans.active` |
| `created_at` / `updated_at` | TEXT NOT NULL / TEXT | ISO-8601 UTC, same convention as every other table in `docs/schema.md` |

Indexes: `idx_yield_entries_type_active` on `(instrument_type, active)` — the query shape the client screen actually needs (grouped-by-type, active-only).

Nothing else in the schema changes. No new columns on `users`, `accounts`, or any trading table — this table has no foreign key into the rest of the schema at all, by design (it's not user-specific or account-specific data).

## Success criteria

- An admin can create a `g_sec` entry, a `corporate_bond` entry (with a credit rating), and a `bank_fd` entry through the admin screen, and all three appear correctly grouped on the client-facing screen with the exact values entered — no computation/derivation happens between entry and display.
- Deactivating an entry (`toggle`) removes it from `GET /api/yields`'s default response without deleting the row — reactivating brings it back with its original data intact.
- Every visible entry shows a real `as_of_date` — no entry can be created without one (`NOT NULL`, and the admin form should not allow submitting without it).
- `GET /api/yields` returns `403` for whichever auth level Open Questions ultimately settles on being excluded (if kept `@require_login`, a logged-out request gets `401`, matching every other gated route's behavior); `POST`/`PUT`/`toggle` return `403` for a `client`-role session.
- The disclaimer text is present and visible on first paint of the client-facing screen, not behind a click/expand.
- Manual spot-check: none of `backend/live/poller.py`'s startup/EOD task list, `TRIGGERS` config, or `SYMBOLS` config changed as a side effect of building this — confirming the feature genuinely stayed isolated from Drishti.

## Open questions

- **Does Upstox actually expose G-Sec / listed-corporate-bond instrument data at all?** Unverified in this research pass — nothing in the codebase has ever used a debt-segment instrument key. This needs an actual spike (pull the NSE instrument master JSON referenced in `config.py`'s comments, look for a debt/WDM segment, test a real `get_ltp`/`get_historical_candles` call against a bond instrument key) before any "v2: pull this live" plan is more than speculation. Flagging explicitly rather than assuming either a yes or a no.
- **Public/unauthenticated access vs. behind-login.** EdgeVest is invite-only end to end today — `Landing.jsx` is the only screen a logged-out visitor ever sees, and every `/api/*` route in `server.py` requires a session except `/api/me` (which itself just reports "not logged in"). The founder's stated motivation for this feature is growing user interest/demand — which arguably wants this screener to be visible to *non-users* too (SEO/discovery/shareable value before someone even signs up), a genuinely new pattern this codebase has never had. This PRD defaults to keeping it behind login (`/profile/yields`, matching `Reports.jsx`'s access model) as the conservative/consistent-with-precedent choice, but this is the single biggest open product decision here and should be confirmed with the founder before building — going public would also mean adding EdgeVest's first-ever unauthenticated data-serving API route, a real departure from `CORS_ORIGINS`/session-cookie assumptions documented in root `CLAUDE.md`.
- **Where exactly it lives in the nav if kept behind login** — this PRD recommends `/profile/yields` (common section, all roles, `Reports.jsx`'s precedent) as a starting point, but flags that a Dashboard card/teaser (like the existing games teaser) might better serve the stated growth goal than something one tap deeper inside Profile. Not settled.
- **Legal/compliance sign-off on the "informational only" framing.** This PRD documents the founder's stated regulatory position (informational/comparison data, no personalized recommendation, therefore lower regulatory risk) as the design constraint, but a PRD author is not qualified to bless that boundary — recommend an actual compliance/legal review of the disclaimer copy and the feature's mechanics before shipping, given how much regulatory weight the "informational only" line is carrying.
- **Who maintains the curated data, and how often.** No owner or update cadence has been specified — a stale-looking `as_of_date` that never moves is arguably worse for trust than not having the feature at all. Needs a real answer (an admin's standing responsibility, a calendar reminder, whatever) before launch, not just the mechanism to update it.
- **Scope of the initial curated list** — how many G-Secs (which tenures), how many corporate bonds, which banks' FDs, is entirely undecided. This PRD defines the mechanism (the table + editor), not the initial content; the founder needs to decide what the launch list actually contains.
- **Whether `source_note` is shown to end users** (transparency about where a number came from) or kept admin-only (audit trail without cluttering the UI) — left as a display detail for whoever builds this to decide, or for the founder to weigh in on, not treated as decided here.
