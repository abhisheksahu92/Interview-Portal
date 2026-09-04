"""Signed HTTP delivery of webhook payloads, plus the retry schedule.

One attempt is made synchronously by :func:`integrations.events.emit`. If it
does not return 2xx the delivery stays PENDING with ``next_attempt_at`` set by
:data:`WebhookDelivery.BACKOFF_SECONDS` (1m, 5m, 30m, 2h, 12h) and
``manage.py deliver_webhooks`` retries it up to ``MAX_ATTEMPTS`` times before
marking it FAILED.

Everything network-facing goes through :func:`post` so tests can patch
``integrations.delivery.requests``.
"""

import json
import logging
from datetime import timedelta

import requests
from django.utils import timezone

from integrations.models import WebhookDelivery
from integrations.signing import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    build_signature,
)

logger = logging.getLogger(__name__)

#: Seconds we are willing to block a hiring action on a customer endpoint.
TIMEOUT_SECONDS = 5


def build_envelope(company, event, data=None):
    """The JSON body shape every webhook receives."""
    return {
        "event": event,
        "occurred_at": timezone.now().isoformat(),
        "company": getattr(company, "slug", None),
        "data": data or {},
    }


def serialize(envelope) -> bytes:
    """Canonical body bytes — the signature covers exactly these bytes."""
    return json.dumps(envelope, sort_keys=True, default=str).encode()


def headers_for(delivery, body, timestamp=None):
    """Signed headers for ``delivery``'s ``body``."""
    timestamp = str(int(timestamp if timestamp is not None else timezone.now().timestamp()))
    return {
        "Content-Type": "application/json",
        "User-Agent": "InterviewPortal-Webhooks/1.0",
        EVENT_HEADER: delivery.event,
        DELIVERY_HEADER: str(delivery.pk),
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: build_signature(delivery.webhook.secret, timestamp, body),
    }


def post(url, body, headers, timeout=TIMEOUT_SECONDS):
    """The single outbound HTTP call; patched wholesale in tests."""
    return requests.post(url, data=body, headers=headers, timeout=timeout)


def attempt_delivery(delivery, now=None):
    """Try ``delivery`` once, updating its status/attempt bookkeeping.

    Returns True when the endpoint accepted it. Never raises: transport errors
    become ``last_error`` and a scheduled retry.
    """
    now = now or timezone.now()
    delivery.attempts += 1
    body = serialize(delivery.payload)
    fields = ["attempts", "status", "response_code", "last_error", "next_attempt_at", "sent_at"]

    try:
        response = post(
            delivery.webhook.url,
            body,
            headers_for(delivery, body, now.timestamp()),
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as exc:
        delivery.response_code = None
        _fail(delivery, f"{type(exc).__name__}: {exc}", now)
        delivery.save(update_fields=fields)
        return False

    delivery.response_code = _status_code(response)
    if delivery.response_code and 200 <= delivery.response_code < 300:
        delivery.status = WebhookDelivery.SENT
        delivery.sent_at = now
        delivery.last_error = ""
        delivery.next_attempt_at = None
        delivery.save(update_fields=fields)
        return True

    _fail(delivery, f"HTTP {delivery.response_code}", now)
    delivery.save(update_fields=fields)
    return False


def _status_code(response):
    code = getattr(response, "status_code", None)
    try:
        return int(code)
    except (TypeError, ValueError):
        return None


def _fail(delivery, error, now):
    delivery.last_error = error[:2000]
    if delivery.attempts >= delivery.MAX_ATTEMPTS:
        delivery.status = WebhookDelivery.FAILED
        delivery.next_attempt_at = None
    else:
        delivery.status = WebhookDelivery.PENDING
        delivery.next_attempt_at = now + timedelta(
            seconds=delivery.backoff_for(delivery.attempts)
        )


def deliver_due(limit=200, now=None):
    """Retry every PENDING delivery whose ``next_attempt_at`` has passed.

    Returns ``(sent, still_pending, failed)`` counts.
    """
    now = now or timezone.now()
    sent = pending = failed = 0
    queryset = (
        WebhookDelivery.objects.due(now).select_related("webhook", "webhook__company")[:limit]
    )
    for delivery in list(queryset):
        if attempt_delivery(delivery, now=now):
            sent += 1
        elif delivery.status == WebhookDelivery.FAILED:
            failed += 1
        else:
            pending += 1
    return sent, pending, failed


#: Body of the "Send test event" button — recognisable, and clearly not a hire.
TEST_EVENT_DATA = {
    "test": True,
    "message": "Test delivery from Interview Portal.",
    "application": {"id": 0, "status": "ACTIVE"},
}


def send_test_event(webhook, event=None):
    """Deliver a synthetic payload to one webhook, bypassing subscriptions.

    Used by the UI's "Send test event" button so a customer can verify their
    receiver and signature check before any real hiring event exists.
    """
    from integrations.events import APPLICATION_CREATED

    event = event or (webhook.events[0] if webhook.events else APPLICATION_CREATED)
    delivery = WebhookDelivery.objects.create(
        webhook=webhook,
        event=event,
        payload=build_envelope(webhook.company, event, dict(TEST_EVENT_DATA)),
    )
    attempt_delivery(delivery)
    return delivery
