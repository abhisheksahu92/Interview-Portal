"""Retry scheduling, exhaustion, redelivery and the periodic command."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from integrations.delivery import attempt_delivery, deliver_due, send_test_event
from integrations.events import APPLICATION_HIRED, emit
from integrations.models import WebhookDelivery

pytestmark = pytest.mark.django_db


def _pending(company, webhook, responder, status=500):
    responder.status_code = status
    delivery = emit(company, APPLICATION_HIRED, {"id": 1})[0]
    delivery.refresh_from_db()
    return delivery


def test_a_failing_endpoint_leaves_the_delivery_pending(company, webhook, responder):
    delivery = _pending(company, webhook, responder)

    assert delivery.status == WebhookDelivery.PENDING
    assert delivery.attempts == 1
    assert delivery.response_code == 500
    assert delivery.last_error == "HTTP 500"
    assert delivery.next_attempt_at is not None


def test_transport_errors_are_captured_not_raised(company, webhook, responder):
    responder.raises = ConnectionError("connection refused")
    delivery = emit(company, APPLICATION_HIRED, {})[0]
    delivery.refresh_from_db()

    assert delivery.status == WebhookDelivery.PENDING
    assert "ConnectionError" in delivery.last_error
    assert delivery.response_code is None


def test_backoff_schedule_is_1m_5m_30m_2h_12h(company, webhook, responder):
    delivery = _pending(company, webhook, responder)
    expected = [60, 300, 1800, 7200, 43200]

    assert [delivery.backoff_for(n) for n in range(1, 6)] == expected
    # an attempt count beyond the table stays on the last (longest) step
    assert delivery.backoff_for(9) == 43200


def test_next_attempt_uses_the_backoff_for_the_attempt_just_made(
    company, webhook, responder
):
    delivery = _pending(company, webhook, responder)
    first = delivery.next_attempt_at
    assert first - delivery.created_at >= timedelta(seconds=55)

    attempt_delivery(delivery, now=timezone.now())
    delivery.refresh_from_db()
    assert delivery.attempts == 2
    assert delivery.next_attempt_at - timezone.now() > timedelta(seconds=240)


def test_five_failed_attempts_exhaust_the_delivery(company, webhook, responder):
    delivery = _pending(company, webhook, responder)
    for _ in range(4):
        attempt_delivery(delivery)
    delivery.refresh_from_db()

    assert delivery.attempts == WebhookDelivery.MAX_ATTEMPTS == 5
    assert delivery.status == WebhookDelivery.FAILED
    assert delivery.next_attempt_at is None
    assert delivery.attempts_remaining == 0


def test_a_later_attempt_can_still_succeed(company, webhook, responder):
    delivery = _pending(company, webhook, responder)
    responder.status_code = 202

    assert attempt_delivery(delivery) is True
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.SENT
    assert delivery.response_code == 202
    assert delivery.last_error == ""
    assert delivery.next_attempt_at is None


def test_deliver_due_only_picks_up_deliveries_whose_time_has_come(
    company, webhook, responder
):
    delivery = _pending(company, webhook, responder)
    responder.status_code = 200

    assert deliver_due() == (0, 0, 0)  # still inside the 1m backoff

    delivery.next_attempt_at = timezone.now() - timedelta(seconds=1)
    delivery.save(update_fields=["next_attempt_at"])
    assert deliver_due() == (1, 0, 0)
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.SENT


def test_deliver_due_reports_reschedules_and_exhaustion(company, webhook, responder):
    delivery = _pending(company, webhook, responder)
    delivery.next_attempt_at = timezone.now() - timedelta(seconds=1)
    delivery.save(update_fields=["next_attempt_at"])

    assert deliver_due() == (0, 1, 0)

    delivery.refresh_from_db()
    delivery.attempts = 4
    delivery.next_attempt_at = timezone.now() - timedelta(seconds=1)
    delivery.save(update_fields=["attempts", "next_attempt_at"])
    assert deliver_due() == (0, 0, 1)


def test_deliver_webhooks_command_runs_the_queue(company, webhook, responder, capsys):
    delivery = _pending(company, webhook, responder)
    delivery.next_attempt_at = timezone.now() - timedelta(seconds=1)
    delivery.save(update_fields=["next_attempt_at"])
    responder.status_code = 200

    call_command("deliver_webhooks")

    assert "1 sent" in capsys.readouterr().out
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.SENT


def test_deliver_webhooks_is_registered_with_run_periodic():
    from core.management.commands.run_periodic import available_commands

    assert "deliver_webhooks" in available_commands()


def test_send_test_event_bypasses_subscriptions(company, webhook, responder):
    webhook.events = ["offer.accepted"]
    webhook.save(update_fields=["events"])

    delivery = send_test_event(webhook)

    assert delivery.status == WebhookDelivery.SENT
    assert delivery.payload["data"]["test"] is True
    assert delivery.event == "offer.accepted"


def test_redelivery_resets_the_attempt_counter(company, webhook, responder):
    delivery = _pending(company, webhook, responder)
    delivery.attempts = 5
    delivery.status = WebhookDelivery.FAILED
    delivery.save(update_fields=["attempts", "status"])

    delivery.reset_for_redelivery()

    assert delivery.attempts == 0
    assert delivery.status == WebhookDelivery.PENDING
    assert delivery.last_error == ""
    assert delivery.next_attempt_at is not None
