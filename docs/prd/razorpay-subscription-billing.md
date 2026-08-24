# Razorpay Subscription Billing + "My Plan" Client Tab

**Status: Shipped** (`dev` branch, commits `f98b890`, `cf69014`, `b5d3510`)

## Problem

EdgeVest already had a full subscription model — `subscription_plans` (admin-managed catalogue), `subscriptions` (one row per client subscription), and a gem-credit redemption flow (`subscribe_with_credits`) — but real-money payment was an explicit, unimplemented placeholder. `POST /api/subscribe` (`backend/server.py`) returned `{"ok": false, "error": "Payment not yet supported"}, 402` any time `plan.price > 0`, so no plan with a nonzero price could actually be purchased.

Separately, once a client *did* have a subscription (free plan, or gem-redeemed), there was nowhere in the product for them to check its status. The only subscription UI that existed was admin-facing (`SubsTab` in `SettingsDrawer.jsx`, lists every user's subscriptions) or the purchase flow itself (`NoSubscriptionGate`, only rendered when the client has no active subscription at all).

## Goal

A client on `NoSubscriptionGate` can pay for a priced plan with a real card/UPI/etc. via Razorpay Standard Checkout and have their subscription activate automatically on successful payment. An admin can set or change a plan's rupee price from the same inline-editor UI they already use for gem cost. A client with an active or past subscription can see its status, dates, and payment history from Settings, regardless of whether it came from Razorpay, gem redemption, or a free plan.

"Done," concretely: a genuine Razorpay test-mode payment against a priced plan lands as `payment_orders.status='paid'` with a real `razorpay_payment_id`, a matching new row in `subscriptions` with the correct `amount_paid`, and the payer immediately sees that plan reflected in the new "My Plan" tab — without a page reload being required to fetch it (reload is used today for the dashboard gate itself, but the tab's own query is invalidated).

## Non-goals

- Recurring/auto-debit subscriptions (Razorpay Subscriptions API, mandates, UPI Autopay) — this is one-time Standard Checkout per purchase; renewal is still a manual re-purchase.
- Refunds, cancellations, or partial-period proration — not built; a `subscriptions` row, once activated, has no cancellation path other than a new subscription superseding it (`status='expired'` set on the prior active row, see Mechanics).
- Webhooks — verification is entirely client-round-trip (`verify-payment` called from the browser after `handler` fires); no server-to-server Razorpay webhook listener exists, so a payment that completes but whose browser tab is killed before `verify-payment` fires will show as `payment_orders.status='created'` forever with no automatic reconciliation.
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

## Architecture impact

**Backend — additive only, nothing pre-existing changed except imports:**
- `backend/server.py` — `import razorpay`; `razorpay_client` singleton (`None` if `RAZORPAY_KEY_ID` unset, so a misconfigured env degrades billing routes to a clean 500 instead of crashing the whole app at import time — same defensive pattern used elsewhere in this codebase for optional integrations). Three new routes: `POST /api/billing/create-order`, `POST /api/billing/verify-payment`, `GET /api/my-subscription`. Pre-existing `POST /api/subscribe` (free-only) and `POST /api/subscribe-with-credits` (gem redemption) are untouched — this feature adds a third, parallel activation path rather than modifying either.
- `backend/db/queries.py` — three new functions: `create_payment_order`, `get_payment_order_by_razorpay_id`, `activate_subscription_from_payment`, plus `get_subscription_history`. All additive; no existing query function's signature or behavior changed.
- `backend/db/init_db.py` — new `payment_orders` table + `idx_payment_orders_user` index, additive `CREATE TABLE IF NOT EXISTS` block. `subscription_plans` and `subscriptions` schemas are unchanged (both already had the columns this feature needed: `price` on the former, `amount_paid` on the latter).
- `backend/requirements.txt` — `razorpay>=1.4.0` added.
- `backend/.env.dev` — `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` test keys added (gitignored, not part of any commit).

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
    updated_at          TEXT
)
```
Index: `idx_payment_orders_user (user_id)`.

- `amount` is **rupees, not paise** — same unit as `subscription_plans.price` and `subscriptions.amount_paid`. Both those pre-existing columns are unitless `INTEGER`s with no currency field; this feature treats them as rupees throughout (matching how an admin already types "999" into `PlansTab`'s price field) and only multiplies by 100 to get paise at the single point where the Razorpay API requires it (`amount_paise = int(plan["price"]) * 100` in `create-order`). `payment_orders.amount` is written as `plan["price"]` (rupees) in `create_payment_order()`, and that same rupee value flows straight into `subscriptions.amount_paid` in `activate_subscription_from_payment()` — no unit is ever silently mixed across the two tables.
- `status` values used: `'created'` (order made, not yet paid or abandoned) → `'paid'` (verified and activated). No `'failed'`/`'cancelled'` status is ever written — a failed or dismissed checkout just leaves the row at `'created'` forever (see Non-goals re: no webhook reconciliation).
- `razorpay_order_id` is `UNIQUE` — this, plus the `status='created'` re-check inside `activate_subscription_from_payment`, is what makes verification idempotent against replays.
- No changes to `subscription_plans` or `subscriptions` schemas — both already had every column this feature needed (`price`, `amount_paid`).
- No retention/cleanup job for `payment_orders` — kept indefinitely, same posture as `subscriptions` itself (financial/audit records, not a rolling buffer).
- Written from: `create_payment_order()` (order creation), `activate_subscription_from_payment()` (marks `paid`). Read by: `get_payment_order_by_razorpay_id()` (verify-payment's ownership check).

## Success criteria

- `POST /api/billing/create-order` for a plan with `price > 0` returns `200` with a `key_id`/`order_id`/`amount` triple, and a corresponding `payment_orders` row appears with `status='created'`.
- A completed Razorpay test-mode payment (confirmed during implementation with real ₹99 test-mode transactions across multiple accounts) results in: `payment_orders.status='paid'` with a real `razorpay_payment_id`, and a new `subscriptions` row with `status='active'`, `amount_paid` equal to the plan's rupee price, and any prior active row for that user flipped to `status='expired'`.
- An abandoned/incomplete checkout (modal dismissed, or `payment.failed`) leaves its `payment_orders` row at `status='created'` with `razorpay_payment_id IS NULL` and creates **no** `subscriptions` row — confirmed during implementation testing, verifying the "never activate on anything less than a verified completed payment" invariant holds structurally.
- `GET /api/my-subscription` returns the caller's own `current`/`history` only — never another user's data (enforced by `current_user()["id"]` scoping, same as every other `require_login` route).
- Admin can set a price on a plan that was created before this feature shipped (`price=0` originally) via `PlansTab`'s new inline editor, and the client-facing `Pay ₹{price}` button appears for that plan immediately after.
- A replayed `POST /api/billing/verify-payment` (same `razorpay_order_id`, called twice) activates a subscription at most once — second call returns `{"ok": false, "error": "Order not found or already processed"}`.

## Open questions

- No webhook listener exists, so a payment that completes on Razorpay's side but never reaches `verify-payment` (browser closed mid-flow, network drop after `handler` fires) has no automatic reconciliation path — that `payment_orders` row stays `status='created'` forever and the user's money is taken with no subscription activated. Whether to add a Razorpay webhook (`payment.captured` event → server-side activation, independent of the client round-trip) is undecided.
- The `payment.failed` / `ondismiss` failure paths were not reliably exercisable during testing — the commonly-documented `failure@razorpay` UPI VPA convention did not reliably trigger a failure in practice, and generic test cards (e.g. `4111 1111 1111 1111`) are rejected outright as "International cards are not supported" on Razorpay test accounts with international cards disabled by default. Whoever next needs to test the failure path should use a domestic test card from the Razorpay Dashboard's own Test Mode page and check current Razorpay docs directly for the correct failure-simulation method, rather than relying on the VPA convention.
- `SubscriptionTab`'s `paymentLabel()` cannot always distinguish "this historical subscription was a free plan" from "it was redeemed with gems" after the fact — it infers this from the plan's *current* `gem_cost`, which may have changed since that historical `subscriptions` row was created (e.g. a plan that cost gems at purchase time but has since been set to `gem_cost=0`). Accepted as a known, minor labelling imprecision rather than a reason to add a `payment_method` column to `subscriptions` retroactively — undecided whether that column should be added going forward for new rows.
- No decision on recurring billing, refunds/cancellations, or multi-currency — all explicitly out of scope for this shipped version (see Non-goals).
