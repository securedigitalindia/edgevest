"""
Payments HTTP routes. Built as a factory (create_payments_blueprint) rather
than a module-level Blueprint instance because require_login/require_role/
current_user are defined in server.py itself — importing them at module load
time here would create a circular import. server.py passes its own already-
defined decorators/helper in at registration time instead.
"""
import hmac
import os

from flask import Blueprint, request, jsonify
import razorpay as razorpay_sdk

from . import service, razorpay_client

PAYMENTS_CRON_SECRET = os.environ.get("PAYMENTS_CRON_SECRET", "")


def create_payments_blueprint(require_login, require_role, current_user):
    bp = Blueprint("payments", __name__)

    @bp.route("/api/billing/create-order", methods=["POST"])
    @require_login
    def api_billing_create_order():
        if not razorpay_client.is_configured():
            return jsonify(ok=False, error="Payments not configured"), 500
        data    = request.json or {}
        plan_id = data.get("plan_id")
        if not plan_id:
            return jsonify(ok=False, error="plan_id required"), 400
        try:
            result = service.get_or_create_order(current_user()["id"], int(plan_id))
        except razorpay_sdk.errors.BadRequestError as e:
            return jsonify(ok=False, error=str(e)), 400
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500
        return jsonify(result), (200 if result["ok"] else 400)

    @bp.route("/api/billing/verify-payment", methods=["POST"])
    @require_login
    def api_billing_verify_payment():
        if not razorpay_client.is_configured():
            return jsonify(ok=False, error="Payments not configured"), 500
        data     = request.json or {}
        required = ("razorpay_order_id", "razorpay_payment_id", "razorpay_signature")
        if not all(data.get(k) for k in required):
            return jsonify(ok=False, error="Missing payment fields"), 400
        try:
            result = service.verify_and_activate(
                data["razorpay_order_id"], data["razorpay_payment_id"], data["razorpay_signature"],
                current_user()["id"],
            )
        except razorpay_sdk.errors.SignatureVerificationError:
            return jsonify(ok=False, error="Signature verification failed"), 400
        return jsonify(result), (200 if result["ok"] else 400)

    @bp.route("/api/payments/reconcile", methods=["POST"])
    def api_payments_reconcile():
        # Cron-only — no browser session exists for a cron job, so this uses
        # a shared-secret header instead of require_login.
        if not razorpay_client.is_configured():
            return jsonify(ok=False, error="Payments not configured"), 500
        secret = request.headers.get("X-Cron-Secret", "")
        if not PAYMENTS_CRON_SECRET or not hmac.compare_digest(secret, PAYMENTS_CRON_SECRET):
            return jsonify(ok=False, error="Unauthorized"), 401
        report = service.reconcile_pending_orders()
        return jsonify(ok=True, **report)

    @bp.route("/api/payments", methods=["GET"])
    @require_role("super_admin", "admin")
    def api_payments_list():
        from db.queries import get_all_payments
        return jsonify(ok=True, payments=get_all_payments())

    @bp.route("/api/payments/<int:order_id>/reconcile", methods=["POST"])
    @require_role("super_admin", "admin")
    def api_payment_reconcile_one(order_id):
        if not razorpay_client.is_configured():
            return jsonify(ok=False, error="Payments not configured"), 500
        result = service.reconcile_order_by_id(order_id)
        return jsonify(result), (200 if result["ok"] else 400)

    @bp.route("/api/payments/flagged", methods=["GET"])
    @require_role("super_admin", "admin")
    def api_payments_flagged():
        from db.queries import get_flagged_duplicate_orders
        return jsonify(ok=True, orders=get_flagged_duplicate_orders())

    return bp
