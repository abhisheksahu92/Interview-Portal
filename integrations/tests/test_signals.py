"""Every domain transition that must reach the event bus."""

from datetime import timedelta

import pytest
from django.utils import timezone

from integrations.events import (
    APPLICATION_CREATED,
    APPLICATION_HIRED,
    APPLICATION_REJECTED,
    APPLICATION_STAGE_CHANGED,
    ASSESSMENT_SUBMITTED,
    INTERVIEW_CONFIRMED,
    OFFER_ACCEPTED,
)
from integrations.models import WebhookDelivery
from jobs.models import Application

pytestmark = pytest.mark.django_db


def events_for(webhook):
    return list(
        WebhookDelivery.objects.filter(webhook=webhook)
        .order_by("pk")
        .values_list("event", flat=True)
    )


def test_creating_an_application_emits_application_created(
    job, candidate, webhook, responder
):
    Application.objects.create(job=job, candidate=candidate)
    assert events_for(webhook) == [APPLICATION_CREATED]


def test_created_payload_carries_job_and_candidate(job, candidate, webhook, responder):
    Application.objects.create(job=job, candidate=candidate)
    data = WebhookDelivery.objects.get(webhook=webhook).payload["data"]

    assert data["job"]["title"] == job.title
    assert data["candidate"]["email"] == candidate.user.email
    assert data["status"] == Application.ACTIVE


def test_advancing_emits_stage_changed(application, webhook, responder):
    WebhookDelivery.objects.all().delete()
    application.advance()
    assert events_for(webhook) == [APPLICATION_STAGE_CHANGED]


def test_rejecting_emits_application_rejected(application, webhook, responder):
    WebhookDelivery.objects.all().delete()
    application.reject()
    assert events_for(webhook) == [APPLICATION_REJECTED]


def test_hiring_emits_application_hired(application, webhook, responder):
    WebhookDelivery.objects.all().delete()
    application.status = Application.HIRED
    application.save(update_fields=["status"])
    assert events_for(webhook) == [APPLICATION_HIRED]


def test_a_no_op_save_emits_nothing(application, webhook, responder):
    WebhookDelivery.objects.all().delete()
    application.save()
    assert events_for(webhook) == []


def test_status_is_only_reported_once(application, webhook, responder):
    application.reject()
    WebhookDelivery.objects.all().delete()
    application.save()
    assert events_for(webhook) == []


def test_offer_acceptance_emits_offer_accepted(application, webhook, responder):
    from offers.models import Offer

    offer = Offer.objects.create(application=application, salary=1200000)
    WebhookDelivery.objects.all().delete()

    offer.status = Offer.ACCEPTED
    offer.signed_name = "Asha Rao"
    offer.save(update_fields=["status", "signed_name"])

    assert OFFER_ACCEPTED in events_for(webhook)
    payload = WebhookDelivery.objects.filter(event=OFFER_ACCEPTED).first().payload
    assert payload["data"]["salary"].startswith("1200000")
    assert payload["data"]["signed_name"] == "Asha Rao"


def test_draft_offer_creation_emits_nothing(application, webhook, responder):
    from offers.models import Offer

    WebhookDelivery.objects.all().delete()
    Offer.objects.create(application=application, salary=100)
    assert events_for(webhook) == []


def test_interview_confirmation_emits_interview_confirmed(
    company, application, webhook, responder
):
    from scheduling.models import Interview

    interview = Interview.objects.create(
        company=company,
        application=application,
        scheduled_start=timezone.now() + timedelta(days=1),
        scheduled_end=timezone.now() + timedelta(days=1, hours=1),
        status=Interview.PROPOSED,
    )
    WebhookDelivery.objects.all().delete()

    interview.status = Interview.CONFIRMED
    interview.save(update_fields=["status"])

    assert INTERVIEW_CONFIRMED in events_for(webhook)


def test_assessment_submission_emits_assessment_submitted(
    job, application, webhook, responder
):
    from assessments.models import Assessment, Attempt

    assessment = Assessment.objects.create(job=job, title="Python basics")
    attempt = Attempt.objects.create(assessment=assessment, application=application)
    WebhookDelivery.objects.all().delete()

    attempt.submitted_at = timezone.now()
    attempt.save(update_fields=["submitted_at"])

    assert ASSESSMENT_SUBMITTED in events_for(webhook)


def test_a_resave_after_submission_does_not_re_emit(job, application, webhook, responder):
    from assessments.models import Assessment, Attempt

    assessment = Assessment.objects.create(job=job, title="Python basics")
    attempt = Attempt.objects.create(
        assessment=assessment, application=application, submitted_at=timezone.now()
    )
    WebhookDelivery.objects.all().delete()
    attempt.save()
    assert events_for(webhook) == []


def test_hiring_pushes_to_active_hrms_connectors(application, monkeypatch):
    from integrations.connectors.base import ConnectorResult
    from integrations.models import ConnectorConfig, ConnectorRun

    config = ConnectorConfig.objects.create(
        company=application.company,
        kind=ConnectorConfig.KEKA,
        settings={"api_key": "k", "subdomain": "acme"},
        active=True,
    )
    monkeypatch.setattr(
        "integrations.connectors.keka.KekaConnector.push_hire",
        lambda self, app: ConnectorResult.success(f"created {app.pk}"),
    )

    application.status = application.HIRED
    application.save(update_fields=["status"])

    run = ConnectorRun.objects.get(config=config)
    assert run.status == ConnectorRun.OK
    assert run.context["application_id"] == application.pk


def test_a_broken_connector_does_not_break_the_hire(application, monkeypatch):
    from integrations.models import ConnectorConfig, ConnectorRun

    ConnectorConfig.objects.create(
        company=application.company,
        kind=ConnectorConfig.KEKA,
        settings={"api_key": "k", "subdomain": "acme"},
        active=True,
    )

    def boom(self, app):
        raise RuntimeError("vendor exploded")

    monkeypatch.setattr("integrations.connectors.keka.KekaConnector.push_hire", boom)

    application.status = application.HIRED
    application.save(update_fields=["status"])
    application.refresh_from_db()

    assert application.status == application.HIRED
    run = ConnectorRun.objects.get()
    assert run.status == ConnectorRun.ERROR
    assert "vendor exploded" in run.detail


def test_inactive_connectors_are_not_called(application, monkeypatch):
    from integrations.models import ConnectorConfig, ConnectorRun

    ConnectorConfig.objects.create(
        company=application.company,
        kind=ConnectorConfig.KEKA,
        settings={"api_key": "k", "subdomain": "acme"},
        active=False,
    )
    application.status = application.HIRED
    application.save(update_fields=["status"])
    assert ConnectorRun.objects.count() == 0


def test_a_failing_webhook_never_breaks_a_hiring_action(
    application, webhook, responder
):
    responder.raises = ConnectionError("down")
    application.reject()
    application.refresh_from_db()
    assert application.status == application.REJECTED
