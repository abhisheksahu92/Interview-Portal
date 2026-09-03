"""Recruiter offer flows: gating, creation, sending, PDF, isolation."""

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from jobs.models import Application
from offers.models import Offer, OfferEvent, OfferTemplate
from offers.tests.conftest import grant_offers, make_application


@pytest.fixture
def staff_client(client, recruiter):
    client.force_login(recruiter)
    return client


def test_offer_list_requires_the_offers_feature(client, company, recruiter):
    grant_offers(company, enabled=False)
    client.force_login(recruiter)
    response = client.get(reverse("offers:index"))
    assert response.status_code == 403


def test_offer_list_renders_with_feature(staff_client, draft_offer):
    response = staff_client.get(reverse("offers:index"))
    assert response.status_code == 200
    assert b"Senior Python Engineer" in response.content


def test_expiring_soon_is_highlighted(staff_client, draft_offer):
    draft_offer.status = Offer.SENT
    draft_offer.expires_at = timezone.now() + timezone.timedelta(hours=12)
    draft_offer.save()
    assert draft_offer.expiring_soon is True
    response = staff_client.get(reverse("offers:index"))
    assert b"Expiring soon" in response.content


def test_create_offer_from_application_and_send(staff_client, application, mailoutbox):
    url = reverse("offers:create", args=[application.pk])
    assert staff_client.get(url).status_code == 200
    mail.outbox.clear()  # ignore whatever the application itself triggered
    response = staff_client.post(
        url,
        {
            "salary": "1500000",
            "currency": "INR",
            "joining_date": (timezone.localdate() + timezone.timedelta(days=20)).isoformat(),
            "expires_at": (timezone.localtime() + timezone.timedelta(days=5)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "custom_fields_text": '{"bonus": "10% annual"}',
            "action": "send",
        },
    )
    offer = Offer.objects.get(application=application)
    assert response.status_code == 302
    assert offer.status == Offer.SENT
    assert offer.sent_at is not None
    assert "Asha Rao" in offer.body_rendered
    assert offer.custom_fields == {"bonus": "10% annual"}
    assert offer.pdf.name and offer.pdf.size > 800
    kinds = list(offer.events.values_list("kind", flat=True))
    assert OfferEvent.CREATED in kinds and OfferEvent.SENT in kinds

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["asha@offers.test"]
    assert offer.sign_token in message.body  # signing link is in the email
    assert message.attachments, "the offer PDF must be attached"
    name, content, mimetype = message.attachments[0]
    assert name.endswith(".pdf") and mimetype == "application/pdf"
    assert content[:5] == b"%PDF-"


def test_generated_pdf_is_downloadable(staff_client, draft_offer):
    response = staff_client.get(reverse("offers:pdf", args=[draft_offer.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert b"".join(response.streaming_content)[:5] == b"%PDF-"


def test_live_preview_renders_without_saving(staff_client, application):
    response = staff_client.post(
        reverse("offers:offer_preview", args=[application.pk]),
        {"salary": "900000", "currency": "INR", "custom_fields_text": ""},
    )
    assert response.status_code == 200
    assert b"Asha Rao" in response.content
    assert not Offer.objects.exists()


def test_withdraw_and_resend(staff_client, draft_offer, mailoutbox):
    mail.outbox.clear()
    staff_client.post(reverse("offers:send", args=[draft_offer.pk]))
    staff_client.post(reverse("offers:resend", args=[draft_offer.pk]))
    draft_offer.refresh_from_db()
    assert draft_offer.status == Offer.SENT
    assert len(mail.outbox) == 2
    assert draft_offer.events.filter(kind=OfferEvent.RESENT).exists()

    staff_client.post(reverse("offers:withdraw", args=[draft_offer.pk]))
    draft_offer.refresh_from_db()
    assert draft_offer.status == Offer.WITHDRAWN
    assert draft_offer.events.filter(kind=OfferEvent.WITHDRAWN).exists()


def test_accepted_offer_cannot_be_withdrawn(staff_client, draft_offer):
    draft_offer.status = Offer.ACCEPTED
    draft_offer.save()
    staff_client.post(reverse("offers:withdraw", args=[draft_offer.pk]))
    draft_offer.refresh_from_db()
    assert draft_offer.status == Offer.ACCEPTED


def test_company_isolation_hides_other_tenants_offers(
    staff_client, other_company, candidate, recruiter
):
    foreign_application = make_application(other_company, candidate, title="Rival Role")
    foreign = Offer.objects.create(application=foreign_application, salary=1)
    assert staff_client.get(reverse("offers:detail", args=[foreign.pk])).status_code == 404
    assert staff_client.get(reverse("offers:create", args=[foreign_application.pk])).status_code == 404
    listing = staff_client.get(reverse("offers:index"))
    assert b"Rival Role" not in listing.content


def test_template_crud_and_preview(staff_client, company):
    assert staff_client.get(reverse("offers:template_list")).status_code == 200
    assert OfferTemplate.objects.for_company(company).count() == 1  # seeded lazily

    response = staff_client.post(
        reverse("offers:template_create"),
        {
            "name": "Contractor letter",
            "subject": "Contract with {{company_name}}",
            "body_html": "<p>Hi {{candidate_name}}, {{custom.rate}}/day.</p>",
        },
    )
    assert response.status_code == 302
    template = OfferTemplate.objects.get(name="Contractor letter")

    edit = staff_client.get(reverse("offers:template_edit", args=[template.pk]))
    assert edit.status_code == 200
    assert b"Asha Rao" in edit.content  # sample-data preview

    preview = staff_client.post(
        reverse("offers:template_preview"),
        {"body_html": "Hello {{candidate_name}} {% load static %}"},
    )
    assert b"Asha Rao" in preview.content
    assert b"{% load static %}" in preview.content

    staff_client.post(reverse("offers:template_delete", args=[template.pk]))
    assert not OfferTemplate.objects.filter(pk=template.pk).exists()


def test_template_name_must_be_unique_per_company(staff_client, company):
    OfferTemplate.default_for(company)
    response = staff_client.post(
        reverse("offers:template_create"),
        {"name": "standard offer letter", "subject": "s", "body_html": "b"},
    )
    assert response.status_code == 200
    assert b"already exists" in response.content


def test_candidate_cannot_reach_recruiter_screens(client, draft_offer, candidate):
    client.force_login(candidate.user)
    assert client.get(reverse("offers:index")).status_code == 403


def test_my_offers_lists_only_sent_offers(client, draft_offer, candidate):
    client.force_login(candidate.user)
    empty = client.get(reverse("offers:mine"))
    assert b"no offers yet" in empty.content.lower()

    draft_offer.status = Offer.SENT
    draft_offer.save()
    response = client.get(reverse("offers:mine"))
    assert b"Senior Python Engineer" in response.content


def test_gateway_not_configured_by_default(monkeypatch):
    from offers import gateway

    for key in ("ESIGN_API_BASE", "ESIGN_ACCOUNT_ID", "ESIGN_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert gateway.configured() is False
    result = gateway.create_envelope(offer=None)
    assert result["ok"] is False and result["configured"] is False


def test_gateway_configured_with_env(monkeypatch):
    from offers import gateway

    monkeypatch.setenv("ESIGN_API_BASE", "https://example.test")
    monkeypatch.setenv("ESIGN_ACCOUNT_ID", "acct")
    monkeypatch.setenv("ESIGN_API_KEY", "key")
    assert gateway.configured() is True


def test_application_status_untouched_until_acceptance(draft_offer):
    assert draft_offer.application.status == Application.ACTIVE
