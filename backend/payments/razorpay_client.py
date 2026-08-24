"""
Thin wrapper around the razorpay SDK — every direct call to Razorpay lives
here, isolated from routes.py/service.py. None if keys aren't set for this
env, so callers degrade to a clean error instead of crashing on import.
"""
import os
import razorpay

RAZORPAY_KEY_ID     = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) if RAZORPAY_KEY_ID else None


def is_configured() -> bool:
    return _client is not None


def create_order(amount_paise: int, currency: str, receipt: str) -> dict:
    return _client.order.create({"amount": amount_paise, "currency": currency, "receipt": receipt})


def verify_signature(data: dict) -> None:
    """Raises razorpay.errors.SignatureVerificationError on mismatch."""
    _client.utility.verify_payment_signature(data)


def fetch_order_payments(razorpay_order_id: str) -> list[dict]:
    return _client.order.payments(razorpay_order_id)["items"]


def refund_payment(razorpay_payment_id: str, amount_paise: int) -> dict:
    return _client.payment.refund(razorpay_payment_id, {"amount": amount_paise})
