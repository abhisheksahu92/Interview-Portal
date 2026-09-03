"""The retry_failed management command."""

from datetime import timedelta
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from notifications.management.commands.retry_failed import backoff_for, is_due
from notifications.models import OutboundMessage

pytestmark = pytest.mark.django_db


def _failed(company, **kwargs):
    defaults = {
        "company": company,
        "event": "application_received",
        "channel": "email",
        "recipient_email": "cand@x.test",
        "subject": "Hi",
        "body": "Body",
        "status": OutboundMessage.FAILED,
        "error": "SMTP down",
        "attempts": 1,
        "last_attempt_at": timezone.now() - timedelta(hours=2),
    }
    defaults.update(kwargs)
    return OutboundMessage.objects.create(**defaults)


def test_backoff_grows_with_attempts():
    assert backoff_for(1) == timedelta(minutes=5)
    assert backoff_for(2) == timedelta(minutes=10)
    assert backoff_for(3) == timedelta(minutes=20)


def test_retry_resends_a_due_failure(company):
    from django.core import mail

    message = _failed(company)
    call_command("retry_failed")
    message.refresh_from_db()
    assert message.status == OutboundMessage.SENT
    assert message.attempts == 2
    assert len(mail.outbox) == 1


def test_retry_respects_the_backoff_window(company):
    message = _failed(company, last_attempt_at=timezone.now())
    assert is_due(message) is False
    call_command("retry_failed")
    message.refresh_from_db()
    assert message.status == OutboundMessage.FAILED
    assert message.attempts == 1


def test_force_ignores_the_backoff_window(company):
    message = _failed(company, last_attempt_at=timezone.now())
    call_command("retry_failed", "--force")
    message.refresh_from_db()
    assert message.status == OutboundMessage.SENT


def test_retry_gives_up_after_three_attempts(company):
    message = _failed(company, attempts=3)
    call_command("retry_failed")
    message.refresh_from_db()
    assert message.attempts == 3
    assert message.status == OutboundMessage.FAILED


def test_retry_records_a_repeat_failure(company, settings):
    settings.EMAIL_BACKEND = "notifications.tests.test_api.ExplodingBackend"
    message = _failed(company)
    call_command("retry_failed")
    message.refresh_from_db()
    assert message.status == OutboundMessage.FAILED
    assert message.attempts == 2


def test_retry_never_touches_the_network(company, whatsapp_company, whatsapp_env):
    _failed(whatsapp_company, channel="whatsapp", recipient_phone="919876543210")
    ok = mock.Mock(status_code=200)
    ok.json.return_value = {"messages": [{"id": "wamid.R"}]}
    with mock.patch("requests.post", return_value=ok) as post:
        call_command("retry_failed")
    assert post.call_count == 1
