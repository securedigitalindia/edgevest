# Financial Education / Knowledge Content

## Problem

EdgeVest pushes clients into F&O structures — PE calendar spreads, the NIFTY 500-multiple short-with-auto-roll strategy, ladder-style call structures under research — via Telegram alerts and the Recommended Positions screen, but there is nowhere in the product that explains *what those structures are, why they're built that way, or how to read the numbers the app already shows* (margin, P&L, "AUTO ROLL," a trade chain). A client who doesn't already know what a calendar spread is has to take the recommendation on faith or go read about it elsewhere. This is a trust and comprehension gap for an advisory product whose entire pitch is "we tell you what to do" — it doesn't build conviction if the client doesn't understand the "why."

Separately, the founder is exploring how to grow interest/demand without expanding into a new regulated advisory category (mutual funds, bonds-as-advice would push further into SEBI Investment Adviser/RA territory than the existing F&O recommendation product already sits in). Generic, publicly-known financial education about EdgeVest's own strategy mechanics — not personalized advice, not new instrument recommendations — is a low-regulatory-risk way to add value and give people a reason to open the app between recommendations.

## Goal

A "Learn" section inside the app where any authenticated user (any role, subscribed or not) can read short, static articles that explain EdgeVest's own recommended strategies and the mechanics behind the numbers already shown elsewhere in the product (Trades, Positions, Monthly Report). "Done" looks like: a client sees a NIFTY 500-Multiple entry alert on Telegram, opens the app, and can go to Profile → Learn and read a plain-language explanation of what that trade is, why it has a fut leg and a PE leg, what "AUTO ROLL" means when it later shows up on their position, and what the margin/P&L figures on their Recommended Positions card actually represent — all without contacting the advisor.

## Non-goals

- **No personalized advice.** Every article is static and identical for every reader regardless of role, portfolio, open positions, or trade history — no "based on your position in X" dynamic content. This boundary is what keeps this feature out of SEBI IA/RA scope; it must not be blurred.
- **No new instrument/fund recommendations.** Mutual funds, bonds, or any instrument outside options/futures mechanics are explicitly out of scope. Module 2 (Strategies) content only explains structures EdgeVest already recommends via its own trigger/trade-suggestion pipeline (`backend/live/triggers.py`, `backend/live/trade_suggestions.py`) — it does not suggest new trades or symbols. Module 1 (Fundamentals, added in the 2026-09-01 revision below) is the one deliberate, narrow exception to "platform-grounded only" — generic option-mechanics education (intrinsic/time value, Greeks, margin/leverage) not tied to a specific EdgeVest trade — but it still never suggests what to trade, which is the boundary that actually matters here.
- **No admin content editor / CMS in v1.** No new database table, no in-app authoring UI. Content ships as part of the frontend build; adding or editing an article is a code change + deploy, same as any other copy change in this codebase today. See "Content authoring model" below for the tradeoff.
- **No public, unauthenticated / SEO-crawlable version in v1.** Content lives behind the existing Google OAuth gate like every other screen in the app (`App.jsx`'s `!user → Landing` gate). It is not reachable without login, so it earns no organic-search/SEO benefit in this version — see Open Questions.
- **No progress tracking, read receipts, or completion badges** — no new per-user state, no new table.
- **No comments, ratings, or user-generated content.**
- **No video/multimedia** — text, headings, lists, and simple tables only, matching the rest of this codebase's plain-CSS, text-first UI.
- **No versioning/changelog UI** for articles — a manually-maintained "last updated" date per article is fine as a courtesy; automated history tracking is not built.
- **Not a substitute for compliance review** — see Open Questions: the actual copy needs a compliance-minded pass before shipping (staying descriptive/explanatory, never "you should...").

## Where this lives in the nav / IA

**Not a 6th top-level tab.** `MainNav` (`frontend/src/components/nav/MainNav.jsx`) deliberately has 5 peer tabs — Dashboard | Trades | Positions | Games | Profile (`frontend/CLAUDE.md`) — and education content is not a primary, frequently-revisited destination the way those five are; it doesn't warrant permanent nav real estate on mobile's bottom bar.

It fits the existing `/profile/*` pattern instead — the established home for secondary, non-transactional screens (`Reports.jsx`/Monthly Report, `Referrals.jsx`, `MyPlan.jsx`, etc.), reached via a `MenuRow` in `ProfileHub.jsx`. Specifically: a new **"Learn"** row in `ProfileHub.jsx`'s common (non-admin-gated) section, next to "Monthly Report" and "Details" — visible to every role, not just clients. This mirrors Monthly Report's own placement precedent: it started admin-only, then the founder explicitly moved it into the common section once its content was confirmed non-sensitive for any role (`docs/prd/monthly-recommendation-report.md`'s revision note) — education content has the same "useful to everyone, sensitive to no one" shape from day one, so it goes straight into the common section rather than needing a later move.

No subscription gate either. `NoSubscriptionGate` blocks Trades/Games for `subscription_valid === false`, but Learn content isn't a paid deliverable — it's exactly the kind of thing worth showing a lapsed or not-yet-subscribed user to build trust and pull them back toward subscribing, so `/profile/learn` renders for every authenticated user regardless of `subscription_valid`.

## Content authoring model

**Decision: static content, shipped as part of the frontend build — plain JS data files, not a backend-driven content table with an admin editor.**

This codebase has no CMS and no precedent for admin-authored rich content. The one existing "admin editor" pattern — `Plans.jsx`'s inline price/gem-cost editor (`frontend/src/screens/profile/Plans.jsx`) — edits single scalar numeric fields on an existing row via a text input + Save button; it is not a model for authoring multi-paragraph article content, and building a real content editor (rich text or markdown input, article CRUD routes, a new `education_articles` table, draft/publish states) is a materially larger scope than this feature's actual v1 need of ~7 articles that change rarely.

Tradeoff, stated explicitly: static-first means every content edit requires a code change + build + deploy (frontend `npm run build` → S3/CloudFront, per `docs/architecture.md`'s deployment flow) rather than an in-app save button — acceptable because (a) this content is evergreen/mechanical (how a strategy works, not time-sensitive market commentary), (b) the founder already ships copy changes this way everywhere else in the app (landing page copy, plan descriptions typed by hand, etc.), and (c) it avoids inventing a whole new subsystem (schema, routes, an editor screen, access control for who can publish) for a low-frequency editing need. If the founder later wants non-engineers editing content directly, or wants content to change often enough that a deploy-per-edit becomes a real bottleneck, that's the trigger to revisit and build a real backend-driven CMS — not decided here, flagged in Open Questions.

**Shape, concretely:**

- `frontend/src/content/education/` — one file per article, e.g. `nifty-500-multiple.js`, `pe-calendar-spread.js`, exporting a plain object: `{ slug, title, category, summary, lastUpdated, body }`.
- `body` is an array of simple content blocks — `{type:'p', text}`, `{type:'heading', text}`, `{type:'list', items:[...]}`, `{type:'callout', text}`, `{type:'table', headers, rows}` — rather than raw JSX or a new Markdown/MDX toolchain. Considered and rejected: pulling in an MDX pipeline (new build-time dependency, new Vite plugin) for ~7 static articles is disproportionate; this repo already favors "no new dependency" when the need is this bounded (see `docs/prd/monthly-recommendation-report.md`'s hand-rolled-SVG-over-charting-library decision for the same pattern). A shared `ArticleBody.jsx` renderer maps block types to plain HTML/CSS elements, matching this codebase's "no CSS framework, colocated `.css`" convention (`frontend/CLAUDE.md`).
- `frontend/src/content/education/index.js` — aggregates all article objects into one list + category groupings, imported by the hub screen. Adding a new article is: create the file, add one import + array entry here, PR, deploy.

## v1 topics

Grounded in the platform's own actual strategies/mechanics — the differentiator is "understand what *this platform* is recommending you," not generic finance-101 content lifted from elsewhere. Two groupings on the hub screen: **Platform Strategies** (specific to what EdgeVest actually sends) and **Reading Your Numbers** (how to interpret the app's own UI).

| Slug | Title | Grounded in |
|---|---|---|
| `fo-glossary` | F&O terms used on EdgeVest (lot, strike, expiry, CE/PE, ITM/OTM, leg, roll) | Foundational glossary for every other article — terms appear throughout `Positions.jsx`, `Trades.jsx`, `trade_legs` schema fields (`instrument_type`, `strike`, `expiry_str`, `lots`, `lot_size`) |
| `pe-calendar-spread` | What is a PE Calendar Spread (and why EdgeVest recommends one) | `nifty_pe_cal_qtrly` / `nifty_pe_cal_monthly` / `nifty_pe_cal_weekly_to_monthly` in `backend/live/trade_suggestions.py` — sell near-expiry ITM PE, buy far-expiry ITM PE, same strike; these are the actual trade cards a client sees |
| `nifty-500-multiple` | The NIFTY 500-Multiple Short strategy, explained | `Nifty500MultipleTrigger` (`backend/live/triggers.py`) + `nifty_500_short_entry`/`nifty_500_short_exit` templates — entry on an upward 500-point-level cross (short fut + sell PE), exit on a configured point drop from entry |
| `auto-roll-explained` | What "AUTO ROLL" means when it shows up on your position | `Nifty500MultipleTrigger._do_auto_roll()` / `roll_recommended_trade()` — a monthly-expiry roll fully exits the old trade and opens a new, linked one (`parent_trade_id`); explains why a client's position "changes ID" at expiry without them doing anything |
| `reading-margin-and-pnl` | Reading the Margin and P&L on your Recommended Positions | `margin_at_entry`/`margin_final` distinction and the instrument-key-matched P&L computation used by `Dashboard.jsx`'s `RecItem` (see `docs/prd/monthly-recommendation-report.md`'s Data model section for the underlying mechanics) — explained in plain language, not the technical migration detail |
| `reading-monthly-report` | How to read the Monthly Report | `Reports.jsx` / `GET /api/reports/monthly` — why peak margin isn't a sum, why the margin chart fluctuates, what "New vs Carried" positions means |
| `call-ladder-averaging` | Call ladder averaging: how it works and its risk shape | `backend/analysis/nifty_ce_ladder_avg_backtest.py`'s 1:1:1 call ladder + debit-drop averaging pattern — **must explicitly state this is a strategy pattern EdgeVest studies/backtests, not a live trigger currently sent to clients** (it has no entry in `config.py`'s `TRIGGERS` or `trade_suggestions.py`'s registry today); the article should describe the general mechanics and flag the unlimited-risk-above-the-far-strike characteristic honestly, without implying it's an active recommendation |

Exact copy for each article is a writing task, not specified here — the table above fixes what each article must accurately describe and which real code path it must not contradict.

**Revision, 2026-09-01 — module structure + a foundations module added, inspired by Zerodha Varsity's IA.** The founder asked for the content plan to draw on Varsity's structure (zerodha.com/varsity) — numbered, progressive modules rather than a flat list, and a foundations layer before the platform-specific content. Varsity itself runs ~17 modules and hundreds of chapters (Introduction to Stock Markets, Technical Analysis, Options Theory for Professional Trading, etc.) — replicating that scale is explicitly out of scope here; this revision borrows the *structural pattern* (numbered modules, each with a clear theme, ordered simple-to-advanced), not the content volume. Three modules, ten articles total:

| # | Module | Articles |
|---|---|---|
| 1 | **F&O Fundamentals** | `fo-glossary`, `intrinsic-vs-time-value` *(new)*, `understanding-options-greeks` *(new)*, `margin-and-leverage` *(new)* |
| 2 | **EdgeVest Strategies Explained** | `pe-calendar-spread`, `nifty-500-multiple`, `auto-roll-explained`, `call-ladder-averaging` |
| 3 | **Reading Your Numbers** | `reading-margin-and-pnl`, `reading-monthly-report` |

The three new Module 1 articles are generic option-mechanics education (why an option has intrinsic vs. time value, what Delta/Theta/Vega mean in plain terms, how margin/leverage work) — not tied to any one EdgeVest strategy, unlike everything in Module 2. This is a deliberate, narrow exception to the original "no generic finance-101 content" framing (see Non-goals): the founder's call was that a *small* foundations layer earns its place because Module 2's articles (calendar spreads, the 500-Multiple strategy) already lean on these concepts (decay, ITM/OTM, Greeks-adjacent reasoning) without ever defining them from scratch, and Varsity's own structure puts exactly this kind of foundations module first for the same reason. It remains bounded — 4 short articles, not a Varsity-scale options-theory module — and still holds the line on the harder non-goal: no personalized advice, no instrument recommendations, nothing that tells a reader what to trade.

`index.js`'s aggregator groups articles by `module` (1/2/3) with a module title + description, not just the flat `category` used in the original two-grouping design — the hub screen renders one section per module, numbered, in order, mirroring Varsity's own module-list page rather than a flat two-column category split.

## Mechanics / behavior

### Hub screen (`/profile/learn`)

A list of articles grouped into the three numbered modules above (see the 2026-09-01 revision), each row showing title + one-line summary, tapping through to the article. Same `PageHeader` convention as every other `/profile/*` screen (`title="Learn"`, `fallback="/profile"`).

### Article screen (`/profile/learn/:slug`)

Renders one article's `body` via the shared `ArticleBody` block renderer. `PageHeader` with `fallback="/profile/learn"` (back goes to the hub, not all the way to Profile). A slug that doesn't match any article in the index renders a simple "not found" state and a link back to the hub — no 404 route needed at the App.jsx level since this is a single nested path segment, not a new top-level route.

### No role or subscription gating

Both routes render for any authenticated user (`super_admin`, `admin`, `client`) regardless of `subscription_valid` — consistent with the "useful to everyone, sensitive to no one" framing above. No `if (!isAdmin) return <Navigate .../>` guard (unlike `Plans.jsx`/`Brokers.jsx`/`Users.jsx`/`Subscriptions.jsx`, which are admin-only) and no `NoSubscriptionGate` wrapping (unlike `Trades`/`Games`).

## Architecture impact

**Frontend only — nothing on the backend changes.** No new Flask route, no new DB table/column, no change to `docs/apis.md` or `docs/schema.md`.

- **New content directory**: `frontend/src/content/education/*.js` (one file per article) + `frontend/src/content/education/index.js` (aggregator). New, additive.
- **New screens**: `frontend/src/screens/profile/Learn.jsx` (hub) and `frontend/src/screens/profile/LearnArticle.jsx` (article view, reads `:slug` param via `useParams()`), plus a shared `frontend/src/components/common/ArticleBody.jsx` block renderer used only by `LearnArticle.jsx`. Both screens colocate their own `.css` (or extend `Profile.css`) per the "no CSS framework" convention.
- **Routing** (`frontend/src/App.jsx`): two new lazy-loaded routes alongside the other `/profile/*` entries —
  ```
  <Route path="/profile/learn"       element={<Learn />} />
  <Route path="/profile/learn/:slug" element={<LearnArticle />} />
  ```
- **Nav entry** (`frontend/src/screens/profile/ProfileHub.jsx`): a new `MenuRow` in the common (non-admin) section, e.g. `<MenuRow icon={BookIcon} label="Learn" onClick={() => navigate('/profile/learn')} />`, placed alongside "Monthly Report" and "Details."
- **New icon**: `BookIcon` doesn't currently exist in `frontend/src/components/common/Icons.jsx` (existing icons: Bank/Game/Chevron/Plus/Dashboard/Positions/Profile/Gem/Gear/Undo/Lock/Close/Refresh/Bell/Warning/Trophy/People/Card/Building/Clipboard/Receipt/Chart/Trend) — add one inline SVG icon following that file's existing size-prop convention.
- **Dashboard entry point** (`frontend/src/screens/Dashboard.jsx`, `Dashboard.css`) — a 5th `FeaturedTile` linking to `/profile/learn`, added 2026-09-01; see the resolved Open Questions entry below for why it's a wide/spanning tile rather than a 5th square in the 2-column grid, and a new `teal` tile color variant.
- No changes to `authStore.js`, `useMe.js`, `client.js`, or any existing hook — this feature introduces no server state, so no new TanStack Query hook is needed either (content is imported directly, not fetched).

## Data / storage

None. No new table, no new column, no new API surface, nothing persisted server-side or client-side (no localStorage read/completion state in v1). Content lives entirely as static JS modules bundled into the frontend build, versioned in git like the rest of the codebase.

## Success criteria

- The "Learn" row appears in `ProfileHub.jsx`'s common section (visible and clickable) for a `client`, `admin`, and `super_admin` test account alike, including a `client` account with `subscription_valid === false`.
- All v1 articles (table above) render correctly at their `/profile/learn/:slug` route with no console errors, for every role.
- Each article's technical claims are spot-checked against the real code path it references (e.g. the `nifty-500-multiple` article's description of entry/exit logic matches `Nifty500MultipleTrigger.check()` in `backend/live/triggers.py`; the `auto-roll-explained` article's description matches `_do_auto_roll()`) — a mismatch here is a bug, since the entire premise of this content is "explains what this platform actually does."
- The `call-ladder-averaging` article explicitly and unambiguously states that this pattern is not currently a live, active EdgeVest recommendation — verified by reading the shipped copy, not just this table.
- `docs/apis.md` and `docs/schema.md` remain unchanged by this feature (confirms it stayed frontend-only, as scoped).
- No backend deploy is required to ship this feature — a `frontend`-only build/deploy (`npm run build` → S3/CloudFront, per `docs/architecture.md`) is sufficient.

## Open questions

- **Public/SEO-facing exposure was part of the founder's original framing** ("retention/trust/SEO") but this PRD scopes v1 as in-app, behind-login only — App.jsx's routing renders everything inside the authenticated shell, and making content reachable without login would mean new unauthenticated routes (parallel to how `Landing` renders for `!user` today), meta tags, and a sitemap — a materially bigger scope than a Profile menu row. Whether that public/crawlable version is worth building as a fast-follow, and whether the same static content could simply be reused at a public route, is undecided here and needs the founder's call.
- ~~Discoverability beyond the Profile menu~~ — **resolved 2026-09-01**: yes. A 5th `FeaturedTile` ("Learn Trading & Investing") was added to `Dashboard.jsx`'s Featured grid, linking to `/profile/learn`. Since the grid is a fixed 2-column layout and a lone 5th tile on its own row would leave an awkward empty gap, it spans both columns as a shorter banner instead (`.ov-tile-wide` in `Dashboard.css`) rather than a square tile like the other four. Its ribbon shows a live article count (`${ARTICLES.length} guides`, from `content/education/index.js`) rather than a static label, so it never needs a manual update as articles are added.
- **When does static-first stop being the right call?** If the founder wants to edit content without a developer, or content needs to change frequently (e.g. weekly market commentary rather than evergreen mechanics), that's the trigger to build a real `education_articles` table + admin editor (following `Plans.jsx`'s inline-editor pattern, extended to rich text). Not needed for v1's ~7 articles; explicitly deferred, not designed here.
- **Compliance review of the actual copy** — the whole reason this feature is framed as low-regulatory-risk is that it stays descriptive ("here is what this structure is and how it behaves") rather than advisory ("you should do X"). Whoever writes the final article text should get that phrasing checked against this boundary before shipping, especially for `pe-calendar-spread` and `nifty-500-multiple`, which describe strategies EdgeVest is actively recommending in real time elsewhere in the product.
