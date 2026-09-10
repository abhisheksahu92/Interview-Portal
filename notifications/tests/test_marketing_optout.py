"""Candidates can silence non-essential email without losing transactional mail."""

import pytest
from django.urls import reverse

from notifications import api, registry
from notifications.models import CandidateChannelOptOut, OutboundMessage


def _opt_out(profile, channel):
    return CandidateChannelOptOut.objects.create(profile=profile, channel=channel)


def test_essential_events_are_the_documented_set():
    assert registry.ESSENTIAL_EVENTS == frozenset(
        {
            "application_received",
            "assessment_result",
            "offer_sent",
            "interview_scheduled",
            "interview_reminder",
            "interview_cancelled",
            "invitation",
            "payment_failed",
            "invoice_issued",
            "usage_warning",
        }
    )
    assert registry.is_essential("offer_sent") is True
    assert registry.is_essential("stage_advanced") is False


@pytest.mark.django_db
def test_non_essential_email_is_skipped_after_a_marketing_opt_out(company, candidate, job):
    _opt_out(candidate, registry.MARKETING_EMAIL)
    sent = api.send("stage_advanced", candidate, {"company": company, "job": job}, company)
    assert [m.status for m in sent] == [OutboundMessage.SKIPPED]
    assert "non-essential" in sent[0].error


@pytest.mark.django_db
def test_essential_email_still_goes_out_after_a_marketing_opt_out(company, candidate, job):
    _opt_out(candidate, registry.MARKETING_EMAIL)
    sent = api.send("interview_scheduled", candidate, {"company": company, "job": job}, company)
    assert [m.status for m in sent] == [OutboundMessage.SENT]


@pytest.mark.django_db
def test_a_full_email_opt_out_still_stops_everything(company, candidate, job):
    _opt_out(candidate, registry.EMAIL)
    sent = api.send("interview_scheduled", candidate, {"company": company, "job": job}, company)
    assert [m.status for m in sent] == [OutboundMessage.SKIPPED]


@pytest.mark.django_db
def test_footer_link_defaults_to_the_marketing_channel(candidate):
    recipient = api.resolve_recipient(candidate)
    url = api.unsubscribe_url(recipient, registry.MARKETING_EMAIL)
    _, channel = api.read_unsubscribe_token(url.rsplit("/", 2)[-2])
    assert channel == registry.MARKETING_EMAIL


@pytest.mark.django_db
def test_unsubscribe_page_offers_both_email_and_whatsapp(client, candidate):
    token = api.unsubscribe_token(candidate, registry.MARKETING_EMAIL)
    url = reverse("notifications:unsubscribe", args=[token])
    body = client.get(url).content.decode()
    assert "Non-essential email" in body
    assert "WhatsApp" in body

    client.post(url, {"channel": registry.MARKETING_EMAIL})
    assert CandidateChannelOptOut.objects.filter(
        profile=candidate, channel=registry.MARKETING_EMAIL
    ).exists()

    client.post(url, {"channel": registry.WHATSAPP})
    assert CandidateChannelOptOut.objects.filter(
        profile=candidate, channel=registry.WHATSAPP
    ).exists()

    client.post(url, {"channel": registry.MARKETING_EMAIL, "resubscribe": "1"})
    assert not CandidateChannelOptOut.objects.filter(
        profile=candidate, channel=registry.MARKETING_EMAIL
    ).exists()
