# Refer & Earn

## Problem

EdgeVest is invite-only with no signup form — Google OAuth (`/auth/google` → `/auth/callback`, `backend/server.py:200-231`) is the only entry point, and today there's no mechanism for an existing user to bring in a new one. Growth currently depends entirely on whoever administers invites manually. Every new user already gets a flat `SIGNUP_CREDITS` (99 gems, `backend/config.py:23`) welcome bonus regardless of how they heard about EdgeVest — there's no incentive for an existing user to actively recruit, and no way to reward one for doing so.

## Goal

An existing user can share a personal referral link. A new user who signs up through that link gets a (separately configurable) signup bonus instead of the standard one. Once that new user actually completes onboarding (`user.setup_done` flips true — the same flag `App.jsx` gates `SetupWizard` on), the referrer is credited a configurable amount of gems through the existing credits ledger (`user_credits` / `credit_transactions`, `backend/db/queries.py`). A user can see their own referral code/link and a running history of who they've referred and what they've earned from it, in a new screen under `/profile`.

## Non-goals

- **No cap** on total referrals or total gems earned by one referrer — explicitly declined by the founder.
- No referral leaderboard.
- No multi-tier / pyramid referrals (referrer of a referrer earning anything).
- No vanity/custom referral codes — system-generated only.
- No email/SMS invite sending — the codebase has no transactional email or SMS integration today; sharing is copy-link/native-share only, client-side.
- No admin UI for managing/auditing all referrals in v1 (e.g. no referral column added to `profile/Users.jsx`) — `credit_transactions` (reason `referral_signup_bonus` / `referral_reward`) already gives an auditable trail if this is needed later.
- No clawback logic for a referred user who is later deactivated/banned — see Open questions; the capability to deactivate a user doesn't currently exist in the API surface anyway.
- No retroactive referral crediting for users who already signed up before this feature ships.

## Mechanics / behavior

### Referral code

- Every user gets a system-generated `referral_code` (short, uppercase, unambiguous alphabet — e.g. excluding `0/O/1/I` — 7 chars), stored on `users.referral_code`.
- **Lazily generated, not backfilled**: rather than a bulk migration backfilling all existing rows (no precedent for that in this codebase — see Architecture impact), the code is generated on first read (first call to the new `GET /api/my-referrals` endpoint) and persisted, following the same "generate on demand" precedent as `display_code` on `recommended_trades` (`backend/db/queries.py:365-375`, only computed at insert time, never backfilled for pre-existing rows) and the same lazy-upsert pattern `_award_credits_tx` already uses for `user_credits` (`INSERT ... ON CONFLICT DO UPDATE`, `backend/db/queries.py:2188-2201`).
- Referral link format: `<frontend origin>/?ref=<CODE>` — e.g. `https://edgevest.in/?ref=AB23XYZ`. The frontend builds this client-side from `window.location.origin` (never hardcoded server-side), the same way `authUrl()` already builds `?next=` from `window.location.origin` (`frontend/src/api/client.js:9`) — necessary because one backend serves multiple frontend origins per env (dev's Vite proxy vs its CloudFront bundle, per root `CLAUDE.md`'s Environments table).
- An unauthenticated visit to `/?ref=CODE` renders `Landing` regardless of path (`App.jsx`'s `AppShell`: `!user` → `<Route path="*" element={<Landing />} />`), so no new route is needed for the link to land somewhere sensible.

### Signup flow — carrying `ref` through OAuth

Mirrors the existing `?next=` mechanism exactly (`docs/apis.md` §"Dynamic post-auth redirect", `server.py:193-206`):

1. `Landing.jsx` reads `?ref=` from its own URL (`useSearchParams`) and appends it to the Google sign-in link, alongside the existing `?next=`. `authUrl()` (`client.js:9`) currently only supports `next` — it needs to accept extra query params (e.g. `authUrl(path, { ref })`) to carry both.
2. `GET /auth/google` reads `?ref=`, looks up the owning user by `referral_code` (case-insensitive), and — only if found — stashes the **resolved `referrer_user_id`** (not the raw code) in `session["referral_referrer_id"]`, the same way it already stashes `post_login_redirect` (`server.py:204-206`). An unknown/garbage code is silently ignored (falls through to standard signup, per requirement 2).
3. `GET /auth/callback` pops `session["referral_referrer_id"]` and passes it into `upsert_user(..., referrer_user_id=...)`.
4. `upsert_user()` (`db/queries.py:593-628`) already branches on whether the google_id row is new (`existing` check, line 599) — this is exactly the hook point requirement 2 asks for ("only applies to a brand-new user, never retroactively"). Inside the `else` (new-row) branch, where it currently unconditionally awards `SIGNUP_CREDITS`:
   - If a valid `referrer_user_id` was passed **and** it isn't equal to the new user's own id (defensive self-referral guard — see below): award `REFERRAL_SIGNUP_BONUS_GEMS` instead of `SIGNUP_CREDITS`, reason `"referral_signup_bonus"`, `ref_id=str(referrer_user_id)`; and insert one row into a new `referrals` table (`status='pending'`).
   - Otherwise: unchanged — `SIGNUP_CREDITS`, reason `"signup_bonus"`.
   - Both paths still only fire for `role == "client"` (i.e. never for the very first user, who becomes `super_admin` — that branch already skips crediting entirely today, `db/queries.py:617-621`).

### Referrer payout — triggered by `setup_done`

`user.setup_done` is not a one-time event in this codebase — it's re-sent as `true` on **every** save from two different screens:
- `SetupWizard.jsx`'s `finish()` (`frontend/src/screens/SetupWizard.jsx:75`) — the actual first-time onboarding completion.
- `ProfileDetails.jsx`'s `saveProfile()` (`frontend/src/screens/profile/ProfileDetails.jsx:75`) — a user re-editing their trading preferences **after** onboarding, which also sends `setup_done: true` every time.

Both hit the same `POST /api/profile` → `upsert_user_trading_profile()` (`server.py:1311-1331` → `db/queries.py:883-907`), which upserts unconditionally (`ON CONFLICT ... DO UPDATE`, no "only if not already done" guard). So the payout **cannot** be implemented as "fire once when setup_done first becomes true" at the application layer — it has to be idempotent against being invoked arbitrarily many times for the same user, which this PRD's data model (below) makes true by construction rather than by convention.

Trigger point: inside `upsert_user_trading_profile()`, immediately after the profile upsert, when `setup_done` is truthy:
```
UPDATE referrals SET status='rewarded', rewarded_at=?
WHERE referee_user_id=? AND status='pending'
```
If (and only if) this `UPDATE` actually affects a row (rowcount == 1), look up that row's `referrer_user_id` and call `_award_credits_tx(conn, referrer_user_id, REFERRAL_REWARD_GEMS, "referral_reward", ref_id=str(referee_user_id), ...)` — same connection/transaction as the profile upsert. Every subsequent call (re-saving the profile, a duplicate `setup_done=true` POST, etc.) finds zero rows in `status='pending'` and is a guaranteed no-op. This is the idempotency requirement from the brief, satisfied at the DB layer, not by a flag check in Python.

### Self-referral guard

Given Google OAuth is the only identity mechanism, walk through how self-referral could actually occur:

- **Same Google account, reused link**: `/auth/google` does `session.clear()` before anything else (`server.py:202`), so a returning user clicking their own (or anyone's) referral link just re-authenticates normally; `upsert_user()`'s `existing` check finds their `google_id` already present and takes the `UPDATE` branch — referral logic never runs (it's fully inside the `else`/new-row branch). **Structurally impossible**, no extra guard code needed for this case.
- **Resolved-referrer-equals-new-user defensive check**: at the moment `upsert_user()` decides whether to award the referral bonus, the new user's id is freshly `INSERT`-ed and cannot equal any pre-existing `referrer_user_id` looked up from an existing `referral_code` row — so `referrer_user_id == new_uid` can't actually happen either. Still worth a one-line defensive `if referrer_user_id and referrer_user_id != new_uid:` guard (cheap, and protects against any future refactor that reorders id assignment).
- **Separate Google accounts, same person** (e.g. two different Gmail addresses): indistinguishable from a legitimate two-person referral given Google OAuth is the only identity signal — this codebase has no phone/KYC verification to correlate accounts. Treated as an accepted risk, consistent with the founder's explicit "no cap" decision (there was never an intent to fully lock down abuse here). Not solved by this PRD; flagged as a known limitation, not a bug.

### Idempotency / replay safety summary

| Guarantee | Mechanism |
|---|---|
| Each referee triggers at most one referrer payout, ever | `referrals.referee_user_id` is `UNIQUE` — a referee can appear in at most one row, period. Payout `UPDATE ... WHERE status='pending'` additionally only ever transitions once. |
| Repeated `setup_done=true` POSTs don't double-pay | Second+ call finds `status != 'pending'`, `UPDATE` affects 0 rows, no credit awarded. |
| Referral signup bonus only applies to genuinely new users | Lives inside `upsert_user()`'s new-row `else` branch, which only runs once per `google_id`, ever. |
| Invalid/unknown `ref` code | Silently ignored at `/auth/google` — falls back to standard `SIGNUP_CREDITS` flow, same as no `ref` param at all. |

## Architecture impact

**Backend (all flat-file, no new module — matches existing convention where only `payments/` is a package; this feature is small enough to stay in `server.py` + `db/queries.py`, same as everything else):**

- `backend/config.py` — two new constants near `SIGNUP_CREDITS` (line 23):
  - `REFERRAL_SIGNUP_BONUS_GEMS` — gems awarded to a user who signs up via a referral link, replacing `SIGNUP_CREDITS` for that signup only.
  - `REFERRAL_REWARD_GEMS` — gems awarded to the referrer once the referee's `setup_done` flips true.
  - (Exact values not specified by the founder — see Open questions.)
- `backend/db/init_db.py` — one new table (`CREATE TABLE IF NOT EXISTS referrals`, matching the idempotent-migration convention documented at the top of the file and in `docs/schema.md`'s header) plus one new nullable column on the existing `users` table, added via the same "check `pragma_table_info`, `ALTER TABLE ADD COLUMN` if missing" pattern already used for `users.mobile`/`users.note` (`db/init_db.py:536-542`):
  ```sql
  ALTER TABLE users ADD COLUMN referral_code TEXT UNIQUE
  ```
  No backfill loop for existing rows — see Mechanics' "lazily generated" note above.
- `backend/db/queries.py`:
  - `upsert_user()` (line 593) — new optional `referrer_user_id` param, branches the new-row credit award and inserts the `referrals` row as described above.
  - `upsert_user_trading_profile()` (line 883) — the referrer-payout trigger, as described above.
  - New functions: `get_user_by_referral_code(code)`, `get_or_create_referral_code(user_id)` (lazy-generate + persist, retry-on-collision loop against the `UNIQUE` constraint), `get_referral_stats(user_id)` (counts + `SUM(amount) FROM credit_transactions WHERE user_id=? AND reason='referral_reward'` for `gems_earned` — reusing the existing ledger as the source of truth rather than storing a redundant running total, same posture `docs/schema.md` already documents for `user_credits.balance` vs. `credit_transactions`), `get_referral_history(user_id)` (join `referrals` → `users` for referee name/status/dates).
- `backend/server.py`:
  - `/auth/google` (line 200) — read `?ref=`, resolve via `get_user_by_referral_code`, stash `session["referral_referrer_id"]`.
  - `/auth/callback` (line 210) — pop the stashed id, pass to `upsert_user()`.
  - New route: `GET /api/my-referrals` (`require_login`, naming mirrors the existing `GET /api/my-subscription` pattern at line 1217) → `{ code, referred_count, rewarded_count, gems_earned, referrals: [...] }`.
  - `/auth/dev-login` (line 233, `FLASK_ENV=dev` only) is unaffected — it only ever resolves an *existing* user by email (`get_user_by_email`), so the new-user referral path can never fire through it. Flagged as an open question below re: how to manually test the new-user path in dev.

**Frontend:**

- `frontend/src/api/client.js` — `authUrl()` (line 9) extended to accept extra query params beyond `next` (needed to also carry `ref`).
- `frontend/src/screens/Landing.jsx` — read `?ref=` via `useSearchParams`, pass through to both `authUrl('/auth/google', ...)` calls (there are two — the nav button and the hero CTA, lines 43 and 63) and to `DevLogin`'s link if present (no-op there per above, but keep the param present for URL consistency).
- New screen `frontend/src/screens/profile/Referrals.jsx` (own file rather than folding into `Gems.jsx` — `Gems.jsx` is already a complete, self-contained concern (balance + tx history) mirroring how `MyPlan`/`MyAccounts`/`Gems` are already kept as three separate single-purpose screens despite all being "client value" screens; a referral code/share-link/referral-list UI is a distinct enough concern to warrant its own screen and route, consistent with that existing pattern — but this is a judgment call, not something the founder specified; flagged as an open question). Fetches `GET /api/my-referrals` via a new `useQuery(['my-referrals'], ...)`, shows the code, a copy-to-clipboard/share button for `${window.location.origin}/?ref=${code}`, and the referral history list (styled similarly to `Gems.jsx`'s transaction list).
- `frontend/src/App.jsx` — new lazy import + route `/profile/referrals`, alongside the existing `/profile/gems` line (79).
- `frontend/src/screens/profile/ProfileHub.jsx` — new `MenuRow` in the `!isAdmin` client section (alongside `My Plan`/`My Accounts`/`Gems`, lines 48-52).
- New API module function in `frontend/src/api/` (either added to `games.js` where `getCredits` currently lives, or a new file — `games.js` housing credits code is itself a pre-existing naming mismatch in this codebase, not something to compound further; recommend a small addition to `games.js` for now to match precedent, or raise a separate cleanup if a dedicated `credits.js`/`referrals.js` module is preferred).

## Data / storage

### `referrals` (new table)

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `referrer_user_id` | INTEGER NOT NULL REFERENCES `users(id)` | |
| `referee_user_id` | INTEGER NOT NULL UNIQUE REFERENCES `users(id)` | `UNIQUE` is the DB-level enforcement of "one payout per referee, ever" |
| `status` | TEXT NOT NULL DEFAULT `'pending'` | `pending` → `rewarded` (one-way transition) |
| `created_at` | TEXT NOT NULL | ISO-8601 UTC, set at signup (inside `upsert_user()`) |
| `rewarded_at` | TEXT | Nullable until the referrer payout fires |

Index: `idx_referrals_referrer` on `(referrer_user_id, status)` — for the referrer's own history/stats query.

### `users.referral_code` (new column)

`TEXT UNIQUE`, nullable. Lazily populated on first `GET /api/my-referrals` call per user (see Mechanics). Existing users are unaffected until they first visit the new Referrals screen.

### Gems ledger — no new storage, reuses existing tables

Referral gem awards post through the exact existing mechanism (`user_credits.balance` + `credit_transactions`, `backend/db/queries.py:2188-2342`, `docs/schema.md`'s Credits section) via `_award_credits_tx()`, with two new `credit_transactions.reason` values: `"referral_signup_bonus"` and `"referral_reward"`. No parallel gems store — this directly satisfies the constraint in the task brief. `Gems.jsx`'s existing transaction history (`frontend/src/screens/profile/Gems.jsx`) will show these rows automatically once they exist; its `REASON_META` map (lines 8-14) should get two new entries for icon/label, otherwise it falls back to the raw reason string (`meta?.label ?? tx.reason`, line 48) — functional but unstyled without that addition.

Not touched: `subscriptions`, `payment_orders`, `account_trades`, or any market-data tables.

## Success criteria

- A brand-new user who signs up via a referral link has a `credit_transactions` row with `reason='referral_signup_bonus'` and amount `= REFERRAL_SIGNUP_BONUS_GEMS`, and **no** `signup_bonus` row.
- A brand-new user who signs up without a `ref` param still gets exactly the current behavior — one `signup_bonus` row for `SIGNUP_CREDITS`, unchanged.
- After that referred user completes `SetupWizard` (or otherwise POSTs `setup_done: true` for the first time), the referrer's `user_credits.balance` increases by `REFERRAL_REWARD_GEMS` and a `credit_transactions` row with `reason='referral_reward'` appears, exactly once — verifiable by re-triggering `POST /api/profile` with `setup_done: true` again (e.g. via `ProfileDetails`) and confirming no second `referral_reward` row is created.
- `SELECT referee_user_id, COUNT(*) FROM referrals GROUP BY referee_user_id HAVING COUNT(*) > 1` returns zero rows, always (enforced by the `UNIQUE` constraint, but worth a spot-check).
- `GET /api/my-referrals` for a user with zero referrals returns a valid `code` (lazily generated) and empty stats, not an error.
- Manual two-browser-profile check: user A copies their link from the new Referrals screen, user B signs up through it in a separate/incognito session, A's Referrals screen shows B listed with status `pending` before B finishes onboarding and `rewarded` after.

## Open questions

- **Exact gem amounts** for `REFERRAL_SIGNUP_BONUS_GEMS` and `REFERRAL_REWARD_GEMS` — not specified in the brief; this PRD deliberately doesn't guess a number to lock in, needs the founder's input before implementation.
- **Screen ownership**: this PRD recommends a new `profile/Referrals.jsx` over extending `Gems.jsx`, based on the existing one-screen-per-concern pattern (`MyPlan`/`MyAccounts`/`Gems` already separate) — but the task brief explicitly asked to confirm this rather than assume it; flagging for sign-off rather than treating it as decided.
- **How much of the referee's identity to surface** to the referrer in the referral history list (full name + email vs. first name only / masked email) — a privacy consideration not discussed with the founder; `get_all_users()`-style admin views already expose full identity, but this is a peer-facing view, which is a different trust boundary.
- **Referral availability by role** — should `admin`/`super_admin` users also get a referral code and see this screen, or is it client-only like `Gems`/`MyPlan`/`MyAccounts` today (`ProfileHub.jsx`'s `!isAdmin` gate)? Recommend client-only for v1 to match precedent, but not explicitly settled.
- **Referred-user deactivation/clawback**: the brief asks what happens if a referred user's account is "later deleted/banned" — as of this reading, `server.py` has no route that ever sets `users.active = 0` (it's only ever read, at `server.py:225`, never written anywhere in the current codebase). So this scenario isn't reachable today; if/when a deactivation feature is added, whether an already-paid `referral_reward` should be clawed back is undecided and out of scope for this PRD.
- **Testing the new-user path in `dev`**: `/auth/dev-login` only logs in as an *existing* user, so it can't exercise the brand-new-user referral-signup flow locally. Real Google OAuth against `dev-api.edgevest.in` would be needed (creating genuinely new test Google accounts), or a dev-only "delete test user" utility — neither currently exists. Worth deciding before implementation, not blocking the PRD itself.
