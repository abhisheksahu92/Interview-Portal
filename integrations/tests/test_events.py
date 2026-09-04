"""Fan-out, subscription filtering, entitlement gating, and headers."""

import json

import pytest

from integrations import verify_signature
from integrations.events import APPLICATION_HIRED, OFFER_ACCEPTED, emit
from integrations.models import OutboundWebhook, WebhookDelivery
from integrations.signing import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
)

pytestmark = pytest.mark.django_db


def test_emit_delivers_to_a_subscribed_webhook(company, webhook, responder):
    deliveries = emit(company, APPLICATION_HIRED, {"id": 7})

    assert len(deliveries) == 1
    delivery = deliveries[0]
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.SENT
    assert delivery.response_code == 200
    assert delivery.attempts == 1
    assert delivery.sent_at is not None
    assert responder.last["url"] == webhook.url
    assert responder.last["timeout"] == 5


def test_delivery_headers_are_signed_and_verifiable(company, webhook, responder):
    emit(company, APPLICATION_HIRED, {"id": 7})

    call = responder.last
    headers = call["headers"]
    assert headers[EVENT_HEADER] == APPLICATION_HIRED
    assert headers[DELIVERY_HEADER].isdigit()
    assert verify_signature(
        webhook.secret,
        headers[TIMESTAMP_HEADER],
        call["body"],
        headers[SIGNATURE_HEADER],
    )
    # a receiver must reject a body that was altered in transit
    assert not verify_signature(
        webhook.secret,
        headers[TIMESTAMP_HEADER],
        call["body"] + b" ",
        headers[SIGNATURE_HEADER],
    )


def test_payload_envelope_shape(company, webhook, responder):
    emit(company, APPLICATION_HIRED, {"id": 7})

    body = json.loads(responder.last["body"])
    assert body["event"] == APPLICATION_HIRED
    assert body["company"] == company.slug
    assert body["data"] == {"id": 7}
    assert body["occurred_at"]


def test_only_subscribed_webhooks_receive_an_event(company, responder):
    hired = OutboundWebhook.objects.create(
        company=company, name="hires", url="https://a.test/h", events=[APPLICATION_HIRED]
    )
    offers = OutboundWebhook.objects.create(
        company=company, name="offers", url="https://b.test/o", events=[OFFER_ACCEPTED]
    )

    deliveries = emit(company, APPLICATION_HIRED, {})

    assert [d.webhook_id for d in deliveries] == [hired.pk]
    assert offers.deliveries.count() == 0


def test_empty_event_list_means_all_events(company, webhook, responder):
    assert webhook.events == []
    assert len(emit(company, APPLICATION_HIRED, {})) == 1
    assert len(emit(company, OFFER_ACCEPTED, {})) == 1


def test_inactive_webhook_is_skipped(company, webhook, responder):
    webhook.active = False
    webhook.save(update_fields=["active"])
    assert emit(company, APPLICATION_HIRED, {}) == []


def test_other_companies_never_receive_our_events(company, other_company, responder):
    theirs = OutboundWebhook.objects.create(
        company=other_company, name="theirs", url="https://theirs.test/h"
    )
    emit(company, APPLICATION_HIRED, {})
    assert theirs.deliveries.count() == 0


def test_emit_is_gated_on_the_integrations_feature(free_company, responder):
    OutboundWebhook.objects.create(
        company=free_company, name="hook", url="https://x.test/h"
    )
    assert emit(free_company, APPLICATION_HIRED, {}) == []
    assert responder.calls == []


def test_unknown_event_is_refused(company, webhook, responder):
    assert emit(company, "not.an.event", {}) == []
    assert responder.calls == []


def test_emit_without_a_company_is_a_no_op(responder):
    assert emit(None, APPLICATION_HIRED, {}) == []


def test_secret_is_generated_and_masked(company):
    hook = OutboundWebhook.objects.create(
        company=company, name="auto", url="https://x.test/h"
    )
    assert len(hook.secret) == 48
    assert hook.masked_secret.endswith(hook.secret[-4:])
    assert hook.secret[:8] not in hook.masked_secret


def test_unknown_events_are_dropped_on_save(company):
    hook = OutboundWebhook.objects.create(
        company=company,
        name="filtered",
        url="https://x.test/h",
        events=[APPLICATION_HIRED, "bogus.event"],
    )
    assert hook.events == [APPLICATION_HIRED]
