"""Candidate notification emails for pipeline transitions."""

import pytest
from django.core import mail

from jobs.models import Application
from jobs.services import advance_application, apply_to_job, reject_application


@pytest.fixture(autouse=True)
def _empty_outbox(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox.clear()
    yield
    mail.outbox.clear()


@pytest.mark.django_db
def test_application_received_email(job, candidate):
    application = apply_to_job(job, candidate)
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == [candidate.user.email]
    assert job.title in message.subject
    assert "received" in message.subject.lower()
    assert application.job.company.name in message.body


@pytest.mark.django_db
def test_stage_advanced_email(job, candidate):
    application = apply_to_job(job, candidate)
    mail.outbox.clear()

    advance_application(application)

    assert len(mail.outbox) == 1
    assert application.current_stage.name in mail.outbox[0].subject


@pytest.mark.django_db
def test_rejection_email(job, candidate):
    application = apply_to_job(job, candidate)
    mail.outbox.clear()

    reject_application(application)

    assert len(mail.outbox) == 1
    assert job.title in mail.outbox[0].subject


@pytest.mark.django_db
def test_hired_email_at_end_of_pipeline(job, candidate):
    application = apply_to_job(job, candidate)
    last_stage = job.stages.order_by("-order").first()
    application.current_stage = last_stage
    application.save(update_fields=["current_stage"])
    mail.outbox.clear()

    advance_application(application)

    application.refresh_from_db()
    assert application.status == Application.HIRED
    assert len(mail.outbox) == 1
    assert "Great news" in mail.outbox[0].subject


@pytest.mark.django_db
def test_unrelated_save_sends_nothing(job, candidate):
    application = apply_to_job(job, candidate)
    mail.outbox.clear()
    application.ai_summary = "Strong Python background."
    application.save(update_fields=["ai_summary"])
    assert mail.outbox == []


@pytest.mark.django_db
def test_broken_mail_backend_does_not_break_applying(job, candidate, settings):
    settings.EMAIL_BACKEND = "jobs.tests.test_notifications.ExplodingBackend"
    application = apply_to_job(job, candidate)
    assert application.pk is not None


class ExplodingBackend:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("SMTP is down")
