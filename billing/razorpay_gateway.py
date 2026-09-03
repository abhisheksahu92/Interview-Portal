"""Razorpay adapter: subscriptions, one-time orders and signature verification.

The SDK is imported lazily behind :func:`get_client` so the app boots (and the
test suite runs) without keys or the package, and tests patch a single seam.
"""

import hashlib
import hmac
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

MONTHLY_PERIOD = {"period": "monthly", "interval": 1}
YEARLY_PERIOD = {"period": "yearly", "interval": 1}


class RazorpayUnavailable(Exception):
    """No Razorpay SDK installed, or no API keys configured."""


class SignatureInvalid(Exception):
    """A payment or webhook signature did not verify."""


def is_configured():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def get_client():
    """Return an authenticated razorpay client or raise ``RazorpayUnavailable``."""
    if not is_configured():
        raise RazorpayUnavailable("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not configured.")
    try:
        import razorpay
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RazorpayUnavailable("The razorpay package is not installed.") from exc
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def ensure_plan(plan, interval):
    """Razorpay plan id for a tier, created lazily when not present in env/DB."""
    from billing.models import Subscription

    existing = plan.razorpay_plan_id(interval)
    if existing:
        return existing
    client = get_client()
    amount = int(plan.price_for(interval) * 100)
    period = YEARLY_PERIOD if interval == Subscription.YEARLY else MONTHLY_PERIOD
    created = client.plan.create(
        {
            **period,
            "item": {
                "name": f"{plan.name} ({interval.title()})",
                "amount": amount,
                "currency": "INR",
            },
            "notes": {"plan_code": plan.code, "interval": interval},
        }
    )
    plan_id = created["id"]
    if interval == Subscription.YEARLY:
        plan.razorpay_plan_id_yearly = plan_id
    else:
        plan.razorpay_plan_id_monthly = plan_id
    plan.save(update_fields=["razorpay_plan_id_monthly", "razorpay_plan_id_yearly"])
    return plan_id


def create_subscription(*, company, plan, interval, total_count=12):
    """Create a recurring Razorpay subscription for a monthly plan."""
    client = get_client()
    return client.subscription.create(
        {
            "plan_id": ensure_plan(plan, interval),
            "total_count": total_count,
            "customer_notify": 1,
            "notes": {"company_id": str(company.pk), "plan_code": plan.code},
        }
    )


def create_order(*, company, plan, interval):
    """Create a one-time order (used for yearly up-front payments)."""
    client = get_client()
    amount = int(plan.price_for(interval) * 100)
    return client.order.create(
        {
            "amount": amount,
            "currency": "INR",
            "receipt": f"company-{company.pk}-{plan.code}",
            "notes": {
                "company_id": str(company.pk),
                "plan_code": plan.code,
                "interval": interval,
            },
        }
    )


def _sign(message, secret):
    return hmac.new(
        secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_payment_signature(*, order_id=None, payment_id, signature, subscription_id=None):
    """Verify a Razorpay Checkout callback signature server-side.

    Orders sign ``order_id|payment_id``; subscriptions sign
    ``payment_id|subscription_id``. Raises :class:`SignatureInvalid`.
    """
    secret = settings.RAZORPAY_KEY_SECRET
    if not secret:
        raise RazorpayUnavailable("RAZORPAY_KEY_SECRET is not configured.")
    if subscription_id:
        message = f"{payment_id}|{subscription_id}"
    elif order_id:
        message = f"{order_id}|{payment_id}"
    else:
        raise SignatureInvalid("Neither order_id nor subscription_id was provided.")
    expected = _sign(message, secret)
    if not hmac.compare_digest(expected, str(signature or "")):
        raise SignatureInvalid("Payment signature does not match.")
    return True


def verify_webhook_signature(payload, signature):
    """Verify the ``X-Razorpay-Signature`` header of a webhook POST."""
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret:
        raise RazorpayUnavailable("RAZORPAY_WEBHOOK_SECRET is not configured.")
    body = payload.decode("utf-8") if isinstance(payload, bytes | bytearray) else str(payload)
    expected = _sign(body, secret)
    if not hmac.compare_digest(expected, str(signature or "")):
        raise SignatureInvalid("Webhook signature does not match.")
    return True


def checkout_options(*, company, plan, interval, ref, amount=None, subscription=True):
    """The options dict handed to Razorpay Checkout JS in the template."""
    options = {
        "key": settings.RAZORPAY_KEY_ID,
        "name": "Interview Portal",
        "description": f"{plan.name} plan ({interval.title()})",
        "notes": {"company_id": str(company.pk), "plan_code": plan.code},
        "prefill": {},
        "theme": {"color": "#4f46e5"},
    }
    if subscription:
        options["subscription_id"] = ref
    else:
        options["order_id"] = ref
        options["amount"] = int((amount or plan.price_for(interval)) * 100)
        options["currency"] = "INR"
    return options
