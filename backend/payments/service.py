"""
Payments business logic — no Flask/HTTP concerns here, routes.py handles
request parsing and response codes. All SQL stays in db/queries.py per the
project's existing convention; this module just orchestrates it.
"""
import time

from db.queries import (
    get_active_plans, create_payment_order, get_pending_order_for_user_plan,
    get_payment_order_by_razorpay_id, activate_subscription_from_payment,
    get_stale_pending_orders, get_active_or_recent_subscription_source,
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


def reconcile_pending_orders(grace_minutes: int = 10) -> dict:
    """
    Pull-based reconciliation instead of a webhook receiver (webhooks can
    themselves fail to deliver): for every order never synced via
    verify-payment and past the grace period, ask Razorpay directly what
    really happened, then either late-activate a genuinely-paid order or
    auto-refund it if the user already has this exact plan covered by a
    different paid order (a genuine duplicate purchase).
    """
    stale  = get_stale_pending_orders(grace_minutes)
    report = {"synced": [], "duplicate_refunded": [], "still_pending": [], "errors": []}

    for order in stale:
        try:
            payments = razorpay_client.fetch_order_payments(order["razorpay_order_id"])
        except Exception as e:
            report["errors"].append({"order_id": order["id"], "error": str(e)})
            continue

        mark_order_reconciled(order["id"])
        captured = next((p for p in payments if p.get("status") == "captured"), None)
        if not captured:
            report["still_pending"].append(order["id"])
            continue

        dup_source = get_active_or_recent_subscription_source(
            order["user_id"], order["plan_id"], exclude_payment_order_id=order["id"],
        )
        if dup_source:
            try:
                refund = razorpay_client.refund_payment(captured["id"], captured["amount"])
                mark_order_duplicate_refunded(
                    order["id"], captured["id"], dup_source["razorpay_order_id"], refund["id"],
                )
                report["duplicate_refunded"].append(order["id"])
            except Exception as e:
                report["errors"].append({"order_id": order["id"], "error": f"refund failed: {e}"})
            continue

        result = activate_subscription_from_payment(
            order["user_id"], order["plan_id"], order["razorpay_order_id"], captured["id"], order["amount"],
        )
        report["synced"].append({"order_id": order["id"], "result": result})

    return report
