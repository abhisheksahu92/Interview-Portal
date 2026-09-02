"""Apply Stripe webhook events to local Subscription rows."""

import logging
from datetime import UTC, datetime

from django.conf import settings

from billing.models import Plan, Subscription
from billing.services import free_plan, get_subscription, pro_plan
from core.models import Company

logger = logging.getLogger(__name__)

HANDLED_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
}

_STRIPE_STATUS_MAP = {
    "active": Subscription.ACTIVE,
    "trialing": Subscription.TRIALING,
    "past_due": Subscription.PAST_DUE,
    "unpaid": Subscription.PAST_DUE,
    "incomplete": Subscription.PAST_DUE,
    "canceled": Subscription.CANCELED,
    "incomplete_expired": Subscription.CANCELED,
}


def _as_dict(value):
    """Stripe objects behave like dicts; keep plain dicts working too."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return dict(value)


def _period_end(value):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _subscription_for(obj):
    """Locate the local subscription referenced by a Stripe object."""
    company_id = obj.get("client_reference_id") or _as_dict(obj.get("metadata")).get(
        "company_id"
    )
    if company_id:
        company = Company.objects.filter(pk=company_id).first()
        if company is not None:
            return get_subscription(company)

    customer = obj.get("customer")
    if customer:
        found = (
            Subscription.objects.filter(stripe_customer_id=customer)
            .select_related("plan", "company")
            .first()
        )
        if found is not None:
            return found

    sub_id = obj.get("subscription") or (obj.get("id") if obj.get("object") == "subscription" else None)
    if sub_id:
        return (
            Subscription.objects.filter(stripe_subscription_id=sub_id)
            .select_related("plan", "company")
            .first()
        )
    return None


def _plan_for_price(price_id):
    if price_id:
        plan = Plan.objects.filter(stripe_price_id=price_id).first()
        if plan is not None:
            return plan
    return pro_plan()


def _price_from_subscription_object(obj):
    items = _as_dict(obj.get("items")).get("data") or []
    if items:
        return _as_dict(_as_dict(items[0]).get("price")).get("id")
    return None


def handle_event(event):
    """Dispatch one verified Stripe event. Returns the touched Subscription."""
    event = _as_dict(event)
    event_type = event.get("type")
    obj = _as_dict(_as_dict(event.get("data")).get("object"))

    if event_type not in HANDLED_EVENTS:
        logger.info("billing: ignoring stripe event %s", event_type)
        return None

    subscription = _subscription_for(obj)
    if subscription is None:
        logger.warning("billing: no subscription matched stripe event %s", event_type)
        return None

    if event_type == "checkout.session.completed":
        subscription.plan = _plan_for_price(
            _as_dict(obj.get("metadata")).get("price_id") or settings.STRIPE_PRICE_ID_PRO
        )
        subscription.stripe_customer_id = obj.get("customer") or subscription.stripe_customer_id
        subscription.stripe_subscription_id = (
            obj.get("subscription") or subscription.stripe_subscription_id
        )
        subscription.status = Subscription.ACTIVE
        subscription.save()

    elif event_type == "customer.subscription.updated":
        stripe_status = obj.get("status")
        subscription.status = _STRIPE_STATUS_MAP.get(stripe_status, subscription.status)
        subscription.stripe_subscription_id = obj.get("id") or subscription.stripe_subscription_id
        if obj.get("customer"):
            subscription.stripe_customer_id = obj["customer"]
        subscription.current_period_end = (
            _period_end(obj.get("current_period_end")) or subscription.current_period_end
        )
        if subscription.status == Subscription.CANCELED:
            subscription.plan = free_plan()
        else:
            subscription.plan = _plan_for_price(_price_from_subscription_object(obj))
        subscription.save()

    elif event_type == "customer.subscription.deleted":
        subscription.plan = free_plan()
        subscription.status = Subscription.CANCELED
        subscription.stripe_subscription_id = ""
        subscription.current_period_end = None
        subscription.save()

    elif event_type == "invoice.payment_failed":
        subscription.status = Subscription.PAST_DUE
        subscription.save()

    return subscription
