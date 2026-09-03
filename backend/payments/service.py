"""
Payments business logic — no Flask/HTTP concerns here, routes.py handles
request parsing and response codes. All SQL stays in db/queries.py per the
project's existing convention; this module just orchestrates it.
"""
import time

from db.queries import (
    get_active_plans, create_payment_order, get_pending_order_for_user_plan,
    get_payment_order_by_razorpay_id, get_payment_order, activate_subscription_from_payment,
    get_stale_pending_orders, get_covering_subscription_order,
    mark_order_reconciled, mark_order_duplicate_refunded,
)
from . import razorpay_client


def get_or_create_order(user_id: int, plan_id: int) -> dict:
    """Reuses a still-pending order for this user+plan instead of always
    minting a fresh Razorpay order — a retry after a stalled checkout
    reopens the same order rather than creating a duplicate outright."""
    plans = {p["id"]: p for p in get_active_plans()}
    plan  = plans.get(plan_id)
    if not plan:
        return {"ok": False, "error": "Invalid or inactive plan"}
    if plan["price"] <= 0:
        return {"ok": False, "error": "This plan has no price to pay"}

    amount_paise = int(plan["price"]) * 100
    if amount_paise < 100:
        return {"ok": False, "error": "Amount too small"}

    existing = get_pending_order_for_user_plan(user_id, plan_id)
    if existing:
        return {
            "ok": True, "order_id": existing["razorpay_order_id"], "amount": amount_paise,
            "currency": existing["currency"], "key_id": razorpay_client.RAZORPAY_KEY_ID,
            "plan_name": plan["name"],
        }

    order = razorpay_client.create_order(
        amount_paise, "INR", f"plan{plan['id']}_user{user_id}_{int(time.time())}",
    )
    create_payment_order(user_id, plan["id"], order["id"], plan["price"], "INR")
    return {
        "ok": True, "order_id": order["id"], "amount": amount_paise, "currency": "INR",
        "key_id": razorpay_client.RAZORPAY_KEY_ID, "plan_name": plan["name"],
    }


def verify_and_activate(razorpay_order_id: str, razorpay_payment_id: str,
                         razorpay_signature: str, user_id: int) -> dict:
    """Raises razorpay.errors.SignatureVerificationError on a bad signature
    — caller (routes.py) catches it and never activates on a mismatch."""
    razorpay_client.verify_signature({
        "razorpay_order_id":   razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature":  razorpay_signature,
    })
    order = get_payment_order_by_razorpay_id(razorpay_order_id)
    if not order or order["user_id"] != user_id:
        return {"ok": False, "error": "Order not found"}
    return activate_subscription_from_payment(
        user_id, order["plan_id"], razorpay_order_id, razorpay_payment_id, order["amount"],
    )


def _reconcile_order(order: dict) -> dict:
    """
    Check one `payment_orders` row directly against Razorpay and either
    late-activate a genuinely-paid order, auto-refund it if the user already
    has an unexpired subscription for this exact plan (a genuine duplicate
    purchase, as opposed to a renewal — which only happens once the prior
    subscription has actually lapsed), or leave it as still pending.

    Shared by both callers so "check + activate/refund" is defined in exactly
    one place: `reconcile_pending_orders` (the unattended cron sweep, scoped
    by grace period) and `reconcile_order_by_id` (an admin manually clicking
    "Refresh" on one payment, no grace period — they've already decided it's
    worth checking now).
    """
    try:
        payments = razorpay_client.fetch_order_payments(order["razorpay_order_id"])
    except Exception as e:
        return {"order_id": order["id"], "outcome": "error", "error": str(e)}

    mark_order_reconciled(order["id"])
    captured = next((p for p in payments if p.get("status") == "captured"), None)
    if not captured:
        return {"order_id": order["id"], "outcome": "still_pending"}

    covering_order = get_covering_subscription_order(
        order["user_id"], order["plan_id"], exclude_payment_order_id=order["id"],
    )
    if covering_order:
        try:
            refund = razorpay_client.refund_payment(captured["id"], captured["amount"])
            mark_order_duplicate_refunded(
                order["id"], captured["id"], covering_order["razorpay_order_id"], refund["id"],
            )
            return {"order_id": order["id"], "outcome": "duplicate_refunded"}
        except Exception as e:
            return {"order_id": order["id"], "outcome": "error", "error": f"refund failed: {e}"}

    result = activate_subscription_from_payment(
        order["user_id"], order["plan_id"], order["razorpay_order_id"], captured["id"], order["amount"],
    )
    return {"order_id": order["id"], "outcome": "synced", "result": result}


def reconcile_pending_orders(grace_minutes: int = 10) -> dict:
    """Pull-based reconciliation instead of a webhook receiver (webhooks can
    themselves fail to deliver): sweep every order never synced via
    verify-payment and past the grace period through `_reconcile_order`."""
    stale  = get_stale_pending_orders(grace_minutes)
    report = {"synced": [], "duplicate_refunded": [], "still_pending": [], "errors": []}

    for order in stale:
        r = _reconcile_order(order)
        if r["outcome"] == "synced":
            report["synced"].append({"order_id": r["order_id"], "result": r["result"]})
        elif r["outcome"] == "duplicate_refunded":
            report["duplicate_refunded"].append(r["order_id"])
        elif r["outcome"] == "still_pending":
            report["still_pending"].append(r["order_id"])
        else:
            report["errors"].append({"order_id": r["order_id"], "error": r["error"]})

    return report


def reconcile_order_by_id(order_id: int) -> dict:
    """Admin-triggered manual check for one payment — same `_reconcile_order`
    logic as the cron sweep, just scoped to a single order and without
    waiting on the grace period (an admin clicking "Refresh" has already
    decided it's worth checking now)."""
    order = get_payment_order(order_id)
    if not order:
        return {"ok": False, "error": "Order not found"}
    if order["status"] != "created":
        return {"ok": False, "error": f"Order already {order['status']} — nothing to reconcile"}

    result = _reconcile_order(order)
    if result["outcome"] == "error":
        return {"ok": False, "error": result["error"]}
    return {"ok": True, "outcome": result["outcome"], **({"result": result["result"]} if "result" in result else {})}
