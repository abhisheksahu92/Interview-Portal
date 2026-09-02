"""Thin wrapper around the Stripe SDK.

The SDK is imported lazily so the app boots (and tests run) without it, and so
tests can patch a single seam instead of the network.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class StripeUnavailable(Exception):
    """No Stripe SDK installed, or no secret key configured."""


def get_stripe():
    """Return a configured ``stripe`` module, or raise ``StripeUnavailable``."""
    try:
        import stripe
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise StripeUnavailable("The stripe package is not installed.") from exc
    if not settings.STRIPE_SECRET_KEY:
        raise StripeUnavailable("STRIPE_SECRET_KEY is not configured.")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def is_configured():
    try:
        get_stripe()
    except StripeUnavailable:
        return False
    return True


def create_checkout_session(*, company, subscription, price_id, success_url, cancel_url):
    stripe = get_stripe()
    kwargs = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(company.pk),
        "metadata": {"company_id": str(company.pk)},
    }
    if subscription.stripe_customer_id:
        kwargs["customer"] = subscription.stripe_customer_id
    return stripe.checkout.Session.create(**kwargs)


def create_portal_session(*, subscription, return_url):
    stripe = get_stripe()
    return stripe.billing_portal.Session.create(
        customer=subscription.stripe_customer_id, return_url=return_url
    )


def construct_event(payload, signature):
    """Verify a webhook signature and return the parsed event."""
    stripe = get_stripe()
    return stripe.Webhook.construct_event(
        payload, signature, settings.STRIPE_WEBHOOK_SECRET
    )
