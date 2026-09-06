"""Apply Stripe / Razorpay webhook events to local Subscription rows.

Every event is recorded in :class:`billing.models.ProcessedWebhookEvent` before
it is applied, keyed by the gateway's own event id. Gateways retry and replay
deliveries, so without that guard one payment could mint two invoices and two
placement fees.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from billing.models import Plan, ProcessedWebhookEvent, Subscription
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



# --- Idempotency ---------------------------------------------------------


def event_fingerprint(body) -> str:
    """A stable id for an event that carries no id of its own: hash of the body."""
    if body is None:
        body = b""
    if isinstance(body, str):
        body = body.encode("utf-8", "ignore")
    elif not isinstance(body, bytes | bytearray):
        body = json.dumps(body, sort_keys=True, default=str).encode()
    return "sha256:" + hashlib.sha256(bytes(body)).hexdigest()


def mark_processed(provider, event_id, event_type="") -> bool:
    """Claim ``event_id`` for ``provider``.

    Returns ``True`` the first time an event is seen and ``False`` for a replay,
    relying on the unique constraint so two simultaneous deliveries cannot both
    win the claim.
    """
    if not event_id:
        return True
    _row, created = ProcessedWebhookEvent.objects.get_or_create(
        provider=provider,
        event_id=str(event_id)[:200],
        defaults={"event_type": (event_type or "")[:100]},
    )
    if not created:
        logger.info(
            "billing: skipping replayed %s webhook %s (%s)", provider, event_id, event_type
        )
    return created


def already_processed(provider, event_id) -> bool:
    """True when this event has been applied before."""
    if not event_id:
        return False
    return ProcessedWebhookEvent.objects.filter(
        provider=provider, event_id=str(event_id)[:200]
    ).exists()


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


@transaction.atomic
def handle_event(event):
    """Dispatch one verified Stripe event. Returns the touched Subscription."""
    event = _as_dict(event)
    event_type = event.get("type")
    obj = _as_dict(_as_dict(event.get("data")).get("object"))

    if event_type not in HANDLED_EVENTS:
        logger.info("billing: ignoring stripe event %s", event_type)
        return None

    event_id = event.get("id") or event_fingerprint(event)
    if not mark_processed(Subscription.STRIPE, event_id, event_type):
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
        subscription.provider = Subscription.STRIPE
        subscription.status = Subscription.ACTIVE
        subscription.past_due_since = None
        subscription.trial_ends_at = None
        subscription.save()
        from billing.invoicing import invoice_for_payment

        invoice_for_payment(
            subscription,
            provider_ref=obj.get("subscription") or obj.get("id") or "",
            provider=Subscription.STRIPE,
        )

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
        subscription.past_due_since = subscription.past_due_since or timezone.now()
        subscription.save()

    return subscription


# --- Razorpay ------------------------------------------------------------

RAZORPAY_EVENTS = {
    "subscription.activated",
    "subscription.charged",
    "subscription.halted",
    "subscription.cancelled",
    "subscription.completed",
    "payment.captured",
    "payment.failed",
    "order.paid",
}


def _entity(event, name):
    return _as_dict(_as_dict(_as_dict(event.get("payload")).get(name)).get("entity"))


def _razorpay_subscription_for(event):
    """Find the local Subscription referenced by a Razorpay event payload."""
    from billing.services import get_subscription

    sub_entity = _entity(event, "subscription")
    pay_entity = _entity(event, "payment")
    order_entity = _entity(event, "order")

    for entity in (sub_entity, pay_entity, order_entity):
        company_id = _as_dict(entity.get("notes")).get("company_id")
        if company_id:
            company = Company.objects.filter(pk=company_id).first()
            if company is not None:
                return get_subscription(company)

    remote_id = sub_entity.get("id") or pay_entity.get("subscription_id")
    if remote_id:
        found = (
            Subscription.objects.filter(razorpay_subscription_id=remote_id)
            .select_related("plan", "company")
            .first()
        )
        if found is not None:
            return found
    return None


def _razorpay_plan(event, fallback):
    """Plan named by the event's notes, else the subscription's current plan."""
    for name in ("subscription", "payment", "order"):
        code = _as_dict(_entity(event, name).get("notes")).get("plan_code")
        if code:
            plan = Plan.objects.filter(code=code).first()
            if plan is not None:
                return plan
    return fallback


def _razorpay_interval(event, fallback):
    for name in ("subscription", "payment", "order"):
        interval = _as_dict(_entity(event, name).get("notes")).get("interval")
        if interval in {Subscription.MONTHLY, Subscription.YEARLY}:
            return interval
    return fallback


@transaction.atomic
def handle_razorpay_event(event, event_id=None):
    """Apply one verified Razorpay event. Returns the touched Subscription.

    Razorpay puts its delivery id in the ``X-Razorpay-Event-Id`` header rather
    than the body, so the view passes it in; without one we fall back to a hash
    of the payload, which still catches a verbatim replay.
    """
    from billing.invoicing import invoice_for_payment

    event = _as_dict(event)
    name = event.get("event")
    if name not in RAZORPAY_EVENTS:
        logger.info("billing: ignoring razorpay event %s", name)
        return None

    if not mark_processed(
        Subscription.RAZORPAY, event_id or event_fingerprint(event), name
    ):
        return None

    subscription = _razorpay_subscription_for(event)
    if subscription is None:
        logger.warning("billing: no subscription matched razorpay event %s", name)
        return None

    sub_entity = _entity(event, "subscription")
    pay_entity = _entity(event, "payment")
    subscription.provider = Subscription.RAZORPAY

    if name in {"subscription.activated", "subscription.charged", "payment.captured", "order.paid"}:
        subscription.plan = _razorpay_plan(event, subscription.plan)
        subscription.interval = _razorpay_interval(event, subscription.interval)
        subscription.status = Subscription.ACTIVE
        subscription.past_due_since = None
        subscription.trial_ends_at = None
        if sub_entity.get("id"):
            subscription.razorpay_subscription_id = sub_entity["id"]
        if pay_entity.get("customer_id"):
            subscription.razorpay_customer_id = pay_entity["customer_id"]
        subscription.current_period_end = (
            _period_end(sub_entity.get("current_end")) or subscription.current_period_end
        )
        subscription.save()
        if name in {"subscription.charged", "payment.captured", "order.paid"}:
            invoice_for_payment(
                subscription,
                provider_ref=pay_entity.get("id") or sub_entity.get("id") or "",
                provider=Subscription.RAZORPAY,
            )

    elif name in {"subscription.halted", "payment.failed"}:
        subscription.status = Subscription.PAST_DUE
        subscription.past_due_since = subscription.past_due_since or timezone.now()
        subscription.save()

    elif name in {"subscription.cancelled", "subscription.completed"}:
        subscription.plan = free_plan()
        subscription.status = Subscription.CANCELED
        subscription.razorpay_subscription_id = ""
        subscription.current_period_end = None
        subscription.save()

    return subscription
