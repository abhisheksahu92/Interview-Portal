"""jobs.emails now delegates to notifications.send but still produces email."""

from unittest import mock

import pytest
from django.core import mail

from jobs import emails
from jobs.services import advance_application, apply_to_job, reject_application
from notifications.models import OutboundMessage

pytestmark = pytest.mark.django_db


def test_apply_still_emails_and_logs_an_outbound_message(job, candidate):
    application = apply_to_job(job, candidate)
    assert len(mail.outbox) == 1
    assert job.title in mail.outbox[0].subject
    assert job.company.name in mail.outbox[0].body
    logged = OutboundMessage.objects.get(event="application_received", channel="email")
    assert logged.company_id == job.company_id
    assert logged.status == OutboundMessage.SENT
    assert logged.recipient_email == candidate.user.email
    assert application.pk


def test_advance_and_reject_still_email(job, candidate):
    application = apply_to_job(job, candidate)
    mail.outbox.clear()
    advance_application(application)
    assert application.current_stage.name in mail.outbox[0].subject
    mail.outbox.clear()
    reject_application(application)
    assert job.title in mail.outbox[0].subject


def test_emails_helpers_return_the_number_of_emails_sent(job, candidate):
    application = apply_to_job(job, candidate)
    mail.outbox.clear()
    assert emails.send_application_hired(application) == 1


def test_a_candidate_without_an_email_is_skipped(job, candidate):
    candidate.user.email = ""
    candidate.user.save(update_fields=["email"])
    mail.outbox.clear()
    application = apply_to_job(job, candidate)
    assert emails.send_application_received(application) == 0
    assert mail.outbox == []


def test_delegation_failure_never_propagates(job, candidate):
    application = apply_to_job(job, candidate)
    with mock.patch("notifications.api.send", side_effect=RuntimeError("boom")):
        assert emails.send_stage_advanced(application) == 0
