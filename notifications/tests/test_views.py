"""Preferences UI, outbox, unsubscribe page and the WhatsApp webhook."""

import json
from unittest import mock

import pytest
from django.urls import reverse

from notifications import api
from notifications.models import (
    CandidateChannelOptOut,
    NotificationPreference,
    OutboundMessage,
)

pytestmark = pytest.mark.django_db


def test_settings_page_lists_every_event(client, owner):
    client.force_login(owner)
    response = client.get(reverse("notifications:settings"))
    assert response.status_code == 200
    assert b"Application received" in response.content
    assert b"WhatsApp connection" in response.content
    assert b"Not configured" in response.content


def test_settings_page_shows_configured_whatsapp(client, owner, whatsapp_env):
    client.force_login(owner)
    response = client.get(reverse("notifications:settings"))
    assert b">Configured<" in response.content


def test_interviewer_cannot_open_settings(client, interviewer):
    client.force_login(interviewer)
    assert client.get(reverse("notifications:settings")).status_code == 403


def test_toggle_stores_preference(client, owner, company):
    client.force_login(owner)
    url = reverse("notifications:toggle", args=["application_received", "email"])
    response = client.post(url)
    assert response.status_code == 200
    preference = NotificationPreference.objects.get(company=company, event="application_received")
    assert preference.channels == []
    client.post(url)
    preference.refresh_from_db()
    assert preference.channels == ["email"]


def test_toggle_rejects_unknown_event(client, owner):
    client.force_login(owner)
    response = client.post(reverse("notifications:toggle", args=["nope", "email"]))
    assert response.status_code == 400


def test_test_send_delivers_to_the_current_user(client, owner):
    from django.core import mail

    client.force_login(owner)
    response = client.post(
        reverse("notifications:test_send"),
        {"event": "application_received", "channel": "email"},
        follow=True,
    )
    assert response.status_code == 200
    assert mail.outbox and mail.outbox[0].to == [owner.email]


def test_outbox_filters(client, owner, company):
    OutboundMessage.objects.create(
        company=company, event="application_received", channel="email",
        recipient_email="a@x.test", status=OutboundMessage.SENT,
    )
    OutboundMessage.objects.create(
        company=company, event="offer_sent", channel="whatsapp",
        recipient_phone="919", status=OutboundMessage.FAILED,
    )
    client.force_login(owner)
    response = client.get(reverse("notifications:outbox"), {"status": "FAILED"})
    body = response.content.decode()
    assert "Offer sent" in body
    assert "a@x.test" not in body


def test_outbox_resend_retries(client, owner, company):
    message = OutboundMessage.objects.create(
        company=company, event="application_received", channel="email",
        recipient_email="a@x.test", subject="Hi", body="Body",
        status=OutboundMessage.FAILED, error="boom", attempts=1,
    )
    client.force_login(owner)
    client.post(reverse("notifications:resend", args=[message.pk]))
    message.refresh_from_db()
    assert message.status == OutboundMessage.SENT
    assert message.attempts == 2


def test_unsubscribe_page_opts_out_and_back_in(client, candidate):
    token = api.unsubscribe_token(candidate, "whatsapp")
    url = reverse("notifications:unsubscribe", args=[token])
    assert client.get(url).status_code == 200
    client.post(url)
    assert CandidateChannelOptOut.objects.filter(profile=candidate, channel="whatsapp").exists()
    client.post(url, {"resubscribe": "1"})
    assert not CandidateChannelOptOut.objects.filter(profile=candidate, channel="whatsapp").exists()


def test_unsubscribe_rejects_a_tampered_token(client):
    response = client.get(reverse("notifications:unsubscribe", args=["not-a-token"]))
    assert response.status_code == 400
    assert b"invalid" in response.content.lower()


def test_webhook_get_verifies_the_challenge(client, whatsapp_env):
    response = client.get(
        reverse("notifications:whatsapp_webhook"),
        {"hub.mode": "subscribe", "hub.verify_token": "test-token", "hub.challenge": "42"},
    )
    assert response.status_code == 200
    assert response.content == b"42"


def test_webhook_get_rejects_a_bad_token(client, whatsapp_env):
    response = client.get(
        reverse("notifications:whatsapp_webhook"),
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"},
    )
    assert response.status_code == 403


def test_webhook_post_updates_status(client, company):
    message = OutboundMessage.objects.create(
        company=company, event="application_received", channel="whatsapp",
        recipient_phone="919876543210", status=OutboundMessage.SENT,
        provider_ref="wamid.ABC",
    )
    payload = {
        "entry": [
            {"changes": [{"value": {"statuses": [{"id": "wamid.ABC", "status": "delivered"}]}}]}
        ]
    }
    response = client.post(
        reverse("notifications:whatsapp_webhook"),
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.json() == {"updated": 1}
    message.refresh_from_db()
    assert message.status == OutboundMessage.DELIVERED


def test_webhook_post_records_failure(client, company):
    message = OutboundMessage.objects.create(
        company=company, event="application_received", channel="whatsapp",
        status=OutboundMessage.SENT, provider_ref="wamid.FAIL",
    )
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": "wamid.FAIL",
                                    "status": "failed",
                                    "errors": [{"title": "Number not on WhatsApp"}],
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    client.post(
        reverse("notifications:whatsapp_webhook"),
        data=json.dumps(payload),
        content_type="application/json",
    )
    message.refresh_from_db()
    assert message.status == OutboundMessage.FAILED
    assert "Number not on WhatsApp" in message.error


def test_webhook_post_ignores_unknown_refs_and_bad_json(client):
    response = client.post(
        reverse("notifications:whatsapp_webhook"),
        data=json.dumps({"entry": [{"changes": [{"value": {"statuses": [{"id": "x", "status": "read"}]}}]}]}),
        content_type="application/json",
    )
    assert response.json() == {"updated": 0}
    assert client.post(
        reverse("notifications:whatsapp_webhook"), data="{", content_type="application/json"
    ).status_code == 400


def test_webhook_never_calls_out(client, whatsapp_env):
    with mock.patch("requests.post") as post:
        client.get(reverse("notifications:whatsapp_webhook"), {"hub.mode": "subscribe"})
    post.assert_not_called()
