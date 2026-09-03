"""Candidate-facing signing page: token access, accept, decline, expiry."""

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from jobs.models import Application
from offers.models import Offer, OfferEvent
from offers.services import send_offer


@pytest.fixture
def sent_offer(draft_offer, mailoutbox):
    send_offer(draft_offer)
    mail.outbox.clear()
    return draft_offer


def sign_url(offer):
    return reverse("offers:sign", args=[offer.sign_token])


def test_unknown_token_is_404(client, db):
    assert client.get(reverse("offers:sign", args=["nope"])).status_code == 404


def test_opening_the_link_marks_the_offer_viewed(client, sent_offer):
    response = client.get(sign_url(sent_offer))
    assert response.status_code == 200
    assert b"Sign &amp; accept" in response.content
    sent_offer.refresh_from_db()
    assert sent_offer.status == Offer.VIEWED
    assert sent_offer.viewed_at is not None
    assert sent_offer.events.filter(kind=OfferEvent.VIEWED).count() == 1


def test_pdf_download_is_token_checked_and_streams(client, sent_offer):
    response = client.get(reverse("offers:sign_pdf", args=[sent_offer.sign_token]))
    assert response.status_code == 200
    assert b"".join(response.streaming_content)[:5] == b"%PDF-"
    assert client.get(reverse("offers:sign_pdf", args=["bogus-token"])).status_code == 404


def test_draft_offer_pdf_is_not_downloadable(client, draft_offer):
    assert client.get(reverse("offers:sign_pdf", args=[draft_offer.sign_token])).status_code == 404


def test_accept_records_signature_hires_and_notifies(client, sent_offer, mailoutbox):
    response = client.post(
        reverse("offers:sign_accept", args=[sent_offer.sign_token]),
        {"signed_name": "Asha Rao", "consent": "on"},
        HTTP_USER_AGENT="pytest-browser/1.0",
        REMOTE_ADDR="203.0.113.9",
    )
    assert response.status_code == 302
    sent_offer.refresh_from_db()
    assert sent_offer.status == Offer.ACCEPTED
    assert sent_offer.signed_name == "Asha Rao"
    assert sent_offer.signed_ip == "203.0.113.9"
    assert sent_offer.signed_user_agent == "pytest-browser/1.0"
    assert sent_offer.signed_at is not None

    sent_offer.application.refresh_from_db()
    assert sent_offer.application.status == Application.HIRED

    assert sent_offer.events.filter(kind=OfferEvent.ACCEPTED).exists()
    event = sent_offer.events.get(kind=OfferEvent.ACCEPTED)
    assert event.meta["signed_name"] == "Asha Rao"
    assert event.meta["ip"] == "203.0.113.9"

    # Recruiter is told.
    assert any("recruiter@offers.test" in message.to for message in mail.outbox)


def test_accepted_pdf_carries_the_signature_block(client, sent_offer):
    from offers.pdf import offer_pdf_html

    client.post(
        reverse("offers:sign_accept", args=[sent_offer.sign_token]),
        {"signed_name": "Asha Rao", "consent": "on"},
    )
    sent_offer.refresh_from_db()
    html = offer_pdf_html(sent_offer)
    assert "Electronically signed" in html
    assert "Asha Rao" in html
    assert sent_offer.pdf and sent_offer.pdf.size > 800
    assert sent_offer.events.filter(kind=OfferEvent.PDF_GENERATED).count() >= 2


def test_accept_requires_name_and_consent(client, sent_offer):
    response = client.post(
        reverse("offers:sign_accept", args=[sent_offer.sign_token]),
        {"signed_name": "Asha Rao"},
    )
    assert response.status_code == 400
    sent_offer.refresh_from_db()
    assert sent_offer.status != Offer.ACCEPTED


def test_decline_records_the_reason(client, sent_offer, mailoutbox):
    client.post(
        reverse("offers:sign_decline", args=[sent_offer.sign_token]),
        {"decline_reason": "Accepted another role"},
    )
    sent_offer.refresh_from_db()
    assert sent_offer.status == Offer.DECLINED
    assert sent_offer.decline_reason == "Accepted another role"
    assert sent_offer.application.status == Application.ACTIVE
    event = sent_offer.events.get(kind=OfferEvent.DECLINED)
    assert event.meta["reason"] == "Accepted another role"
    assert any("recruiter@offers.test" in message.to for message in mail.outbox)


def test_withdrawn_offer_shows_a_clear_message_and_blocks_signing(client, sent_offer):
    sent_offer.status = Offer.WITHDRAWN
    sent_offer.save()
    page = client.get(sign_url(sent_offer))
    assert b"withdrawn by the employer" in page.content
    assert b"Sign &amp; accept" not in page.content

    client.post(
        reverse("offers:sign_accept", args=[sent_offer.sign_token]),
        {"signed_name": "Asha Rao", "consent": "on"},
    )
    sent_offer.refresh_from_db()
    assert sent_offer.status == Offer.WITHDRAWN


def test_past_expiry_link_expires_itself_and_blocks_signing(client, sent_offer):
    Offer.objects.filter(pk=sent_offer.pk).update(
        expires_at=timezone.now() - timezone.timedelta(minutes=1)
    )
    page = client.get(sign_url(sent_offer))
    assert b"expired" in page.content.lower()
    sent_offer.refresh_from_db()
    assert sent_offer.status == Offer.EXPIRED

    client.post(
        reverse("offers:sign_accept", args=[sent_offer.sign_token]),
        {"signed_name": "Asha Rao", "consent": "on"},
    )
    sent_offer.refresh_from_db()
    assert sent_offer.status == Offer.EXPIRED
    assert sent_offer.application.status == Application.ACTIVE


def test_signing_page_needs_no_login(client, sent_offer):
    """The page is token-based: an anonymous visitor with the link can sign."""
    assert client.session.get("_auth_user_id") is None
    assert client.get(sign_url(sent_offer)).status_code == 200
