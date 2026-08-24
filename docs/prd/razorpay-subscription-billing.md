# Razorpay Subscription Billing + "My Plan" Client Tab

**Status: Shipped** (`dev` branch, commits `f98b890`, `cf69014`, `b5d3510`, `7c1b695`; reconciliation dup-detection logic refined 2026-08-24, undocumented commit at time of writing)

## Problem

EdgeVest already had a full subscription model — `subscription_plans` (admin-managed catalogue), `subscriptions` (one row per client subscription), and a gem-credit redemption flow (`subscribe_with_credits`) — but real-money payment was an explicit, unimplemented placeholder. `POST /api/subscribe` (`backend/server.py`) returned `{"ok": false, "error": "Payment not yet supported"}, 402` any time `plan.price > 0`, so no plan with a nonzero price could actually be purchased.

Separately, once a client *did* have a subscription (free plan, or gem-redeemed), there was nowhere in the product for them to check its status. The only subscription UI that existed was admin-facing (`SubsTab` in `SettingsDrawer.jsx`, lists every user's subscriptions) or the purchase flow itself (`NoSubscriptionGate`, only rendered when the client has no active subscription at all).

## Goal

A client on `NoSubscriptionGate` can pay for a priced plan with a real card/UPI/etc. via Razorpay Standard Checkout and have their subscription activate automatically on successful payment. An admin can set or change a plan's rupee price from the same inline-editor UI they already use for gem cost. A client with an active or past subscription can see its status, dates, and payment history from Settings, regardless of whether it came from Razorpay, gem redemption, or a free plan.

"Done," concretely: a genuine Razorpay test-mode payment against a priced plan lands as `payment_orders.status='paid'` with a real `razorpay_payment_id`, a matching new row in `subscriptions` with the correct `amount_paid`, and the payer immediately sees that plan reflected in the new "My Plan" tab — without a page reload being required to fetch it (reload is used today for the dashboard gate itself, but the tab's own query is invalidated).

## Non-goals

- Recurring/auto-debit subscriptions (Razorpay Subscriptions API, mandates, UPI Autopay) — this is one-time Standard Checkout per purchase; renewal is still a manual re-purchase.
- Refunds, cancellations, or partial-period proration — not built; a `subscriptions` row, once activated, has no cancellation path other than a new subscription superseding it (`status='expired'` set on the prior active row, see Mechanics).
- Webhooks — no server-to-server Razorpay webhook listener exists. **Partially mitigated as of `7c1b695`**: a pull-based reconciliation cron (`POST /api/payments/reconcile`, see Mechanics) now polls Razorpay directly for any order left at `status='created'` past a grace period, so a payment that completes but whose browser tab dies before `verify-payment` fires is no longer stuck forever — it's just delayed until the next cron run, and only if a cron is actually scheduled to call it (see Open questions — no crontab/systemd timer exists in this repo as of this writing).
- Multi-currency — `currency` is hardcoded `"INR"` in both the `payment_orders` row and the Razorpay order payload.
- Invoicing / GST line items — not built.
- A dedicated frontend `VITE_RAZORPAY_KEY_ID` env var — deliberately not added (see Design decisions).
- Editing `amount_paid` or `payment method` retroactively for old subscription rows to fix the labelling imprecision described below — deliberately not built.

## Mechanics / behavior

### Purchase flow (client-facing)

1. Client without an active subscription sees `NoSubscriptionGate` (`frontend/src/screens/Dashboard.jsx`), which lists active plans (`GET /api/plans` → `get_active_plans`). Each plan card shows the existing gem-redeem button plus, when `plan.price > 0`, a new `Pay ₹{price}` button.
2. Click → `payWithRazorpay(plan)`:
   - `loadRazorpayScript()` (`frontend/src/api/billing.js`) injects `https://checkout.razorpay.com/v1/checkout.js` into `document.body` on demand if `window.Razorpay` isn't already present (memoized via a module-level `_rzpLoading` promise so repeat clicks don't re-inject).
   - `POST /api/billing/create-order { plan_id }` → server validates the plan is active and priced, creates a Razorpay order for `plan.price * 100` paise, records a `payment_orders` row (`status='created'`), and returns `{order_id, amount, currency, key_id, plan_name}`.
   - Razorpay Checkout modal opens client-side using that response (`key: order.key_id`, `order_id`, `amount`, `currency`).
   - On successful payment, Razorpay's `handler` callback fires with `{razorpay_order_id, razorpay_payment_id, razorpay_signature}`, which the frontend immediately forwards to `POST /api/billing/verify-payment`.
   - On `res.ok`, a toast fires and `window.location.reload()` runs after an 800ms delay — a full reload, not a query invalidation, because `NoSubscriptionGate`'s own subscribed/unsubscribed branching lives higher up the component tree than TanStack Query cache invalidation conveniently reaches from this callback.
   - `rzp.on('payment.failed', ...)` and `modal: { ondismiss: ... }` both surface a toast; neither calls `verify-payment` — a failed or abandoned checkout simply leaves the `payment_orders` row at `status='created'` and no subscription is ever created.

### Server-side order creation and verification

| Step | Route | What it does |
|---|---|---|
| Create order | `POST /api/billing/create-order` | Requires login. 500 if `razorpay_client` is `None` (unset keys for this env). Validates `plan_id` against `get_active_plans()`, rejects `price <= 0` (400, "This plan has no price to pay") and any resulting paise amount `< 100` (Razorpay's own minimum). Calls `razorpay_client.order.create(...)` with a `receipt` of `plan{id}_user{id}_{unix_ts}`. On success, calls `create_payment_order()` to persist the order, then returns `key_id` (Razorpay's *public* key) inline in the response body. |
| Verify payment | `POST /api/billing/verify-payment` | Requires login. 500 if `razorpay_client` is `None`. Requires all three of `razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature`. Calls the SDK's `razorpay_client.utility.verify_payment_signature(data)` (raises `SignatureVerificationError` on mismatch → 400, never proceeds past this point on a bad signature). Looks up the order by `razorpay_order_id`, checks `order["user_id"] == current_user()["id"]` (400 "Order not found" otherwise — this is the anti-hijack check). Calls `activate_subscription_from_payment(...)`. |

### Activation (atomic)

`activate_subscription_from_payment(user_id, plan_id, razorpay_order_id, razorpay_payment_id, amount)` (`backend/db/queries.py`), modeled on the pre-existing `subscribe_with_credits` pattern:

1. Inside one connection/transaction, re-select the `payment_orders` row filtered by `razorpay_order_id AND user_id = ? AND status = 'created'`. If no row matches — because it was already verified once, or belongs to a different user — return `{"ok": False, "error": "Order not found or already processed"}` without touching `subscriptions`. This is what makes a replayed/duplicate `verify-payment` call a no-op rather than a double-activation.
2. Look up `plan.duration_days`.
3. `UPDATE payment_orders SET status='paid', razorpay_payment_id=?, updated_at=?`.
4. `UPDATE subscriptions SET status='expired' WHERE user_id=? AND status='active'` — any prior active subscription for this user is expired before the new one is inserted (a user can only have one `status='active'` row at a time; this mirrors how the pre-existing `activate_subscription` / `subscribe_with_credits` functions behave for free/gem activations).
5. `INSERT INTO subscriptions (..., status='active', start_date=today, end_date=today+duration_days, amount_paid=amount, ...)`.
6. Commit.

### Admin plan pricing (`cf69014`)

`PUT /api/plans/<id>` already accepted a `price` field server-side before this feature (`server.py:349-359`, unchanged) — the gap was purely that `PlansTab` (`frontend/src/components/drawer/SettingsDrawer.jsx`) only rendered an inline "Set"/edit control for `gem_cost`; `price` was only ever settable at plan-creation time. Since the new `Pay ₹{price}` button on `NoSubscriptionGate` only renders when `plan.price > 0`, every plan that existed before this feature shipped (all of them — the product only had the gem flow until now) had no price and thus no way to accept Razorpay payment without being deleted and recreated. `cf69014` adds a second inline editor (`editPrice` state, `savePrice()`), structurally identical to the existing `editGem`/`saveGem` pair, next to it in the same plan card.

### "My Plan" tab (`b5d3510`)

New `GET /api/my-subscription` (`server.py`), same response shape convention as the pre-existing `GET /api/credits`:

```json
{ "current": { ... } | null, "history": [ { ... }, ... ] }
```

- `current` = `get_user_subscription(uid)` — pre-existing function, unchanged, reused as-is.
- `history` = new `get_subscription_history(user_id, limit=20)` — all `subscriptions` rows for the user, newest `created_at` first, joined to `subscription_plans` for `plan_name` and the plan's *current* `gem_cost`.

New `SubscriptionTab` component in `SettingsDrawer.jsx`, added as a new "My Plan" tab in the client-facing tab set (alongside the pre-existing "My Accounts" and "💎 Gems" tabs — admin users see a different tab set, `Plans`/`Subscriptions`, unaffected). Modeled directly on the neighboring `GemsTab`'s layout: a gradient card up top showing the current plan's name, status badge, `start_date → end_date`, and days-remaining (computed client-side, `Math.ceil((end_date - now) / 86400000)`), followed by a reverse-chronological history list.

Each history row shows a `paymentLabel(s)`:

```js
function paymentLabel(s) {
  if (s.amount_paid > 0) return `Paid ₹${s.amount_paid}`
  return s.plan_gem_cost > 0 ? 'Redeemed with gems' : 'Free'
}
```

`useVerifyPayment` (in `frontend/src/hooks/useBilling.js`) invalidates both `['me']` and `['my-subscription']` on success, so if this tab is later wired to avoid the full-page reload used by `NoSubscriptionGate` today, it already reflects a fresh payment without one.

### Reconciliation cron (`7c1b695`, dedup logic refined 2026-08-24)

Problem: `verify-payment` only syncs a payment when the browser successfully calls back after checkout completes. If that call never arrives (tab closed right after paying, network drop) but the payment genuinely completed on Razorpay's side, the order sits at `payment_orders.status='created'` forever and the user never gets their subscription despite paying. If they then retry and pay again, nothing reconciles the resulting duplicate.

`POST /api/payments/reconcile` (`backend/payments/routes.py`, `service.reconcile_pending_orders()`) is a pull-based fix, run by an external cron (not a Flask-scheduled job — this repo has no background scheduler, so something outside the app, e.g. system cron or a scheduled task on the EC2 box, must call this endpoint periodically):

1. `get_stale_pending_orders(grace_minutes=10)` — every `payment_orders` row still `status='created'` and older than the grace period.
2. For each, `razorpay_client.fetch_order_payments(razorpay_order_id)` — asks Razorpay directly what actually happened to that order, independent of whether the browser ever called back.
3. `mark_order_reconciled(order_id)` — timestamp the check regardless of outcome (audit trail of "we looked").
4. If no `captured` payment exists → still genuinely unpaid, left alone (`status='created'`), reported as `still_pending`.
5. If a `captured` payment exists → branches on whether this plan is a **genuine duplicate** or a **legitimate purchase/renewal** (see next section). Duplicate → auto-refund via Razorpay's refund API, no human-in-the-loop step (confirmed decision — see Non-goals for what's still manual: partial refunds, cancellations). Not a duplicate → `activate_subscription_from_payment(...)` (the same atomic/idempotent function `verify-payment` uses), late-activating the subscription.

A proactive dedup guard at order-creation time (`get_or_create_order` in `service.py`) also reduces how often duplicates reach this path at all: it reuses an existing non-stale (`created_at` within 30 min) `status='created'` order for the same user+plan instead of always minting a new Razorpay order, so double-clicking "Pay" or retrying a stalled checkout doesn't itself create a second order in the first place.

### Distinguishing "duplicate payment" from "legitimate renewal" (decided 2026-08-24)

EdgeVest's plans are typically annual — a client renews the *same* `plan_id` again once their current subscription lapses. This makes "has this user ever paid for this plan before" a **wrong** test for duplicate detection: it would flag every legitimate renewal as a duplicate and auto-refund it.

The correct test, decided in conversation: **is this plan already covered by a subscription that hasn't expired yet, right now?** If yes, a second captured payment for the same plan is definitionally superfluous — refund it. If no (first purchase, or the prior subscription for this plan has actually lapsed), the payment is legitimate — activate it.

Implemented as `get_covering_subscription_order(user_id, plan_id, exclude_payment_order_id)` (`db/queries.py`): queries `subscriptions WHERE user_id=? AND plan_id=? AND end_date >= today()` directly, rather than checking `subscriptions.status='active'`. This matters because `status` is only flipped from `'active'` to `'expired'` by `expire_stale_subscriptions()`, which is called opportunistically from a few `server.py` routes on the request path (login, etc.) — the reconcile cron is a separate, independent process with no guarantee any of those routes ran recently for this user, so trusting a possibly-stale `status` field could misread a genuinely-lapsed subscription as still covering. Comparing `end_date` directly sidesteps that dependency entirely. It also sidesteps a second subtlety: `activate_subscription_from_payment`'s "expire the prior active row" step has no `plan_id` filter — a user can only ever hold one `status='active'` subscription across *all* plans, not one per plan — so a `plan_id`-scoped `end_date` check is the only unambiguous way to ask "is *this* plan still covered," independent of what the shared `status` field currently says for some other plan the user may have since switched to.

When a covering subscription is found, `get_covering_subscription_order` separately looks up the most recent `payment_orders` row with `status='paid'` for that same user+plan, to populate `duplicate_of_order_id` on the refunded row (admin audit link via `GET /api/payments/flagged`). This can come back `None` if the covering subscription didn't originate from a Razorpay payment at all (e.g. gem redemption, or a free plan) — the refund still proceeds, just without that audit link populated.

### Cron authentication (decided 2026-08-24)

`POST /api/payments/reconcile` has no browser session to authenticate with (it's called by a cron, not a logged-in user), so it can't use `@require_login`/`@require_role` like every other route in this codebase. It instead checks a static shared-secret header (`X-Cron-Secret`, compared via `hmac.compare_digest` against the `PAYMENTS_CRON_SECRET` env var).

Considered and rejected: a "service account" that authenticates through the same session-cookie path as everything else. Rejected because Google OAuth is an interactive browser-redirect flow — a cron job has no browser to complete it with — so a service account would still need *something* bearer-token-shaped underneath (a long-lived session cookie minted for a designated service user, or an API key mapped to a service-account row). That's the same trust model as the shared secret, plus new machinery this codebase has no precedent for (session lifecycle/expiry handling, or a service-account concept alongside the existing `client`/`admin`/`super_admin` roles). Only worth it if multiple cron/service jobs eventually need distinct scoped permissions — for this single endpoint, the shared secret is simpler.

## Architecture impact

**Backend — additive only, nothing pre-existing changed except imports:**
- **`backend/payments/`** (added `7c1b695`) — the first modular package in this codebase; every other feature is flat (`server.py` for routes, `db/queries.py` for all SQL). Holds routes, the Razorpay SDK wrapper, and business-logic orchestration for billing; SQL still stays centralized in `db/queries.py` per the existing project-wide convention — this package never touches SQL directly.
  - `routes.py` — `create_payments_blueprint(require_login, require_role, current_user)`, a **factory**, not a module-level `Blueprint`. Those three are defined in `server.py`; importing them at `payments/routes.py`'s module-load time would be a circular import, so `server.py` passes its own already-defined versions in at registration time instead (`server.py`: `app.register_blueprint(create_payments_blueprint(require_login, require_role, current_user))`). `payments/` never imports from `server.py`.
  - `service.py` — orchestration only, no Flask/HTTP concerns (`get_or_create_order`, `verify_and_activate`, `reconcile_pending_orders`).
  - `razorpay_client.py` — the only file that calls the `razorpay` SDK directly; `is_configured()` guards every route (500 "Payments not configured" if `RAZORPAY_KEY_ID`/`SECRET` unset for the env, matching the defensive optional-integration pattern used elsewhere in this codebase).
  - Four routes registered: `POST /api/billing/create-order`, `POST /api/billing/verify-payment` (both `@require_login`), `POST /api/payments/reconcile` (shared-secret `X-Cron-Secret` auth, no session — see Mechanics), `GET /api/payments/flagged` (`@require_role(super_admin, admin)`).
- `server.py` — `GET /api/my-subscription` (`@require_login`) stays directly in `server.py`, not moved into `payments/`, since it's a read-only query alongside other client-facing endpoints rather than a billing action. Pre-existing `POST /api/subscribe` (free-only) and `POST /api/subscribe-with-credits` (gem redemption) are untouched — this feature adds a third, parallel activation path rather than modifying either.
- `backend/db/queries.py` — additive functions: `create_payment_order`, `get_payment_order_by_razorpay_id`, `activate_subscription_from_payment`, `get_subscription_history`, `get_pending_order_for_user_plan`, `get_stale_pending_orders`, `get_covering_subscription_order` (added `7c1b695` as `get_active_or_recent_subscription_source`, reworked 2026-08-24 — see Mechanics), `mark_order_reconciled`, `mark_order_duplicate_refunded`, `get_flagged_duplicate_orders`. All additive; no existing query function's signature or behavior changed.
- `backend/db/init_db.py` — `payment_orders` table + `idx_payment_orders_user` index (`f98b890`), plus four additive columns via `ALTER TABLE ... ADD COLUMN` migration entries (`7c1b695`): `duplicate_of_order_id`, `refund_id`, `refunded_at`, `reconciled_at`, all nullable `TEXT`. `subscription_plans` and `subscriptions` schemas are otherwise unchanged (both already had the columns this feature needed: `price` on the former, `amount_paid`/`end_date` on the latter).
- `backend/requirements.txt` — `razorpay>=1.4.0` added.
- `backend/.env.dev` — `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / `PAYMENTS_CRON_SECRET` (added `7c1b695`) test values (gitignored, not part of any commit).

**Frontend — additive only:**
- `frontend/src/api/billing.js` (new) — `createOrder`, `verifyPayment`, `getMySubscription`, `loadRazorpayScript`.
- `frontend/src/hooks/useBilling.js` (new) — `useCreateOrder`, `useVerifyPayment`, `useMySubscription` (TanStack Query mutations/query, same conventions as `hooks/useSettings.js` / `hooks/useTrades.js`).
- `frontend/src/screens/Dashboard.jsx` — `NoSubscriptionGate` gets `payWithRazorpay` + a `Pay ₹{price}` button per plan card; pre-existing gem-redeem button (`buy.mutate`) untouched, now sits alongside it in a column layout.
- `frontend/src/components/drawer/SettingsDrawer.jsx` — `PlansTab` (admin) gets the `editPrice` inline editor; new `SubscriptionTab` (client) added as a new "My Plan" tab entry.
- `index.html` — untouched; Razorpay's `checkout.js` is never added to the PWA's static script tags or precache manifest, only injected at runtime on first payment attempt.

## Data / storage

**New table**: `payment_orders` (`backend/db/init_db.py`)

```sql
CREATE TABLE payment_orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    plan_id             INTEGER NOT NULL REFERENCES subscription_plans(id),
    razorpay_order_id   TEXT    NOT NULL UNIQUE,
    razorpay_payment_id TEXT,
    amount              INTEGER NOT NULL,
    currency            TEXT    NOT NULL DEFAULT 'INR',
    status              TEXT    NOT NULL DEFAULT 'created',
    created_at          TEXT    NOT NULL,
    updated_at          TEXT,
    -- added 7c1b695, nullable TEXT via ALTER TABLE, reconciliation-only:
    duplicate_of_order_id TEXT,
    refund_id             TEXT,
    refunded_at           TEXT,
    reconciled_at         TEXT
)
```
Index: `idx_payment_orders_user (user_id)`.

- `amount` is **rupees, not paise** — same unit as `subscription_plans.price` and `subscriptions.amount_paid`. Both those pre-existing columns are unitless `INTEGER`s with no currency field; this feature treats them as rupees throughout (matching how an admin already types "999" into `PlansTab`'s price field) and only multiplies by 100 to get paise at the single point where the Razorpay API requires it (`amount_paise = int(plan["price"]) * 100` in `create-order`). `payment_orders.amount` is written as `plan["price"]` (rupees) in `create_payment_order()`, and that same rupee value flows straight into `subscriptions.amount_paid` in `activate_subscription_from_payment()` — no unit is ever silently mixed across the two tables.
- `status` values used: `'created'` (order made, not yet paid or abandoned) → `'paid'` (verified and activated) or → `'duplicate_refunded'` (reconciled as a genuine duplicate, added `7c1b695`; see Mechanics). No `'failed'`/`'cancelled'` status is ever written — a failed or dismissed checkout just leaves the row at `'created'` until the reconciliation cron next processes it (or forever, if that cron isn't actually scheduled — see Open questions).
- `razorpay_order_id` is `UNIQUE` — this, plus the `status='created'` re-check inside `activate_subscription_from_payment`, is what makes verification idempotent against replays (both from `verify-payment` and from the reconcile cron calling the same function).
- `duplicate_of_order_id` / `refund_id` / `refunded_at` / `reconciled_at` (`7c1b695`) — reconciliation-only bookkeeping. `reconciled_at` is stamped on every order the cron examines, paid-and-covered or not, as an audit trail of "we checked this." `duplicate_of_order_id` holds the *other* order's `razorpay_order_id` (the one that actually activated the still-covering subscription), best-effort — `None` if that subscription didn't originate from a traceable `payment_orders` row (e.g. gem redemption).
- No changes to `subscription_plans` schema. `subscriptions` schema also unchanged — already had every column this feature needed (`amount_paid`, and critically `end_date`, which the reconciliation dedup logic reads directly rather than trusting `status`; see Mechanics).
- No retention/cleanup job for `payment_orders` — kept indefinitely, same posture as `subscriptions` itself (financial/audit records, not a rolling buffer).
- Written from: `create_payment_order()` (order creation), `activate_subscription_from_payment()` (marks `paid`), `mark_order_reconciled()` / `mark_order_duplicate_refunded()` (reconcile cron). Read by: `get_payment_order_by_razorpay_id()` (verify-payment's ownership check), `get_stale_pending_orders()` / `get_pending_order_for_user_plan()` / `get_covering_subscription_order()` / `get_flagged_duplicate_orders()` (reconcile cron + admin audit view).

## Success criteria

- `POST /api/billing/create-order` for a plan with `price > 0` returns `200` with a `key_id`/`order_id`/`amount` triple, and a corresponding `payment_orders` row appears with `status='created'`.
- A completed Razorpay test-mode payment (confirmed during implementation with real ₹99 test-mode transactions across multiple accounts) results in: `payment_orders.status='paid'` with a real `razorpay_payment_id`, and a new `subscriptions` row with `status='active'`, `amount_paid` equal to the plan's rupee price, and any prior active row for that user flipped to `status='expired'`.
- An abandoned/incomplete checkout (modal dismissed, or `payment.failed`) leaves its `payment_orders` row at `status='created'` with `razorpay_payment_id IS NULL` and creates **no** `subscriptions` row — confirmed during implementation testing, verifying the "never activate on anything less than a verified completed payment" invariant holds structurally.
- `GET /api/my-subscription` returns the caller's own `current`/`history` only — never another user's data (enforced by `current_user()["id"]` scoping, same as every other `require_login` route).
- Admin can set a price on a plan that was created before this feature shipped (`price=0` originally) via `PlansTab`'s new inline editor, and the client-facing `Pay ₹{price}` button appears for that plan immediately after.
- A replayed `POST /api/billing/verify-payment` (same `razorpay_order_id`, called twice) activates a subscription at most once — second call returns `{"ok": false, "error": "Order not found or already processed"}`.
- `POST /api/payments/reconcile`, called with a valid `X-Cron-Secret`, correctly late-activates a stale-but-genuinely-paid order that has no covering subscription, and correctly auto-refunds one that does — verified by construction/code-reading during the 2026-08-24 dedup-logic rework (not yet exercised against live Razorpay test-mode data for the reconciliation path specifically; the original `f98b890`/`b5d3510` criteria above *were* confirmed against real test-mode transactions).

## Open questions

- **No webhook listener exists**, though this is now partially mitigated by the pull-based reconciliation cron (`7c1b695`) — see Mechanics. Whether to eventually add a real Razorpay webhook (`payment.captured` event → server-side activation, independent of both the client round-trip and cron polling latency) is still undecided.
- **The reconciliation cron isn't actually scheduled anywhere** — `POST /api/payments/reconcile` exists and works, but no crontab entry, systemd timer, or other scheduler was found in this repo as of 2026-08-24. Confirm whether it's set up directly on the EC2 box outside version control, or still needs to be added.
- **Concurrent reconcile invocations could double-activate a genuine duplicate pair** (found during 2026-08-24 verification pass, not fixed): if the cron overlaps itself — two invocations running at once — two truly-duplicate stale orders for the same user+plan could both pass the `get_covering_subscription_order` check before either commits its activation, since neither would yet see the other's not-yet-committed subscription row as "covering." Both would activate; neither would be refunded. No locking exists against this. Mitigation today is purely operational: don't schedule the cron with an interval shorter than a single run can take, and/or add a lock (e.g. skip-if-already-running) before this ships to an unattended schedule.
- **`get_or_create_order`'s reused-order response can show a stale `amount`** (found during 2026-08-24 verification pass, not fixed): when reusing a still-pending order, the returned `amount` is recomputed from the plan's *current* price rather than read back from the order's own stored `amount`. If an admin edits a plan's price while a user has a pending retry window open (up to 30 min), the Razorpay Checkout modal could briefly display a mismatched amount. Cosmetic only — the actual charge is bound server-side to the Razorpay order object, unaffected by the client-passed `amount` field — but worth a fix (read `existing["amount"]` instead) if it's ever noticed in practice.
- The `payment.failed` / `ondismiss` failure paths were not reliably exercisable during testing — the commonly-documented `failure@razorpay` UPI VPA convention did not reliably trigger a failure in practice, and generic test cards (e.g. `4111 1111 1111 1111`) are rejected outright as "International cards are not supported" on Razorpay test accounts with international cards disabled by default. Whoever next needs to test the failure path should use a domestic test card from the Razorpay Dashboard's own Test Mode page and check current Razorpay docs directly for the correct failure-simulation method, rather than relying on the VPA convention.
- `SubscriptionTab`'s `paymentLabel()` cannot always distinguish "this historical subscription was a free plan" from "it was redeemed with gems" after the fact — it infers this from the plan's *current* `gem_cost`, which may have changed since that historical `subscriptions` row was created (e.g. a plan that cost gems at purchase time but has since been set to `gem_cost=0`). Accepted as a known, minor labelling imprecision rather than a reason to add a `payment_method` column to `subscriptions` retroactively — undecided whether that column should be added going forward for new rows.
- No decision on recurring billing, refunds/cancellations (beyond the narrow auto-refund-a-duplicate case), or multi-currency — all explicitly out of scope for this shipped version (see Non-goals).
