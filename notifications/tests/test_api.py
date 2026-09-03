"""Routing, rendering and delivery through notifications.send."""

from unittest import mock

import pytest
from django.core import mail

from notifications import api, registry
from notifications.models import CandidateChannelOptOut, OutboundMessage

pytestmark = pytest.mark.django_db


def _ok_response(message_id="wamid.TEST"):
    response = mock.Mock()
    response.status_code = 200
    response.json.return_value = {"messages": [{"id": message_id}]}
    return response


def test_send_defaults_to_email_only(company, candidate, job):
    sent = api.send(
        "application_received", candidate, {"job": job, "company": company}, company=company
    )
    assert [m.channel for m in sent] == [registry.EMAIL]
    assert sent[0].status == OutboundMessage.SENT
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [candidate.user.email]


def test_recipient_accepts_user_email_string_and_dict(company, candidate, job):
    from_user = api.resolve_recipient(candidate.user)
    assert from_user.email == candidate.user.email
    assert from_user.phone == candidate.phone
    assert api.resolve_recipient("someone@example.test").email == "someone@example.test"
    as_dict = api.resolve_recipient({"email": "a@b.test", "phone": "919", "name": "A"})
    assert (as_dict.email, as_dict.phone, as_dict.name) == ("a@b.test", "919", "A")
    with pytest.raises(TypeError):
        api.resolve_recipient(object())


def test_preference_disables_email(company, candidate, job):
    api.set_preference(company, "application_received", [])
    sent = api.send("application_received", candidate, {"job": job}, company=company)
    assert sent == []
    assert mail.outbox == []


def test_preference_adds_whatsapp(whatsapp_company, whatsapp_env, candidate, job):
    api.set_preference(whatsapp_company, "stage_advanced", ["email", "whatsapp"])
    with mock.patch("requests.post", return_value=_ok_response()) as post:
        sent = api.send(
            "stage_advanced",
            candidate,
            {"job": job, "stage_name": "L1 Interview"},
            company=whatsapp_company,
        )
    assert [m.channel for m in sent] == ["email", "whatsapp"]
    assert all(m.status == OutboundMessage.SENT for m in sent)
    assert post.call_count == 1
    body = post.call_args.kwargs["json"]
    assert body["messaging_product"] == "whatsapp"
    assert body["to"] == "919876543210"
    assert "L1 Interview" in body["text"]["body"]
    assert sent[1].provider_ref == "wamid.TEST"


def test_whatsapp_is_a_default_channel_when_entitled(whatsapp_company, whatsapp_env, candidate, job):
    with mock.patch("requests.post", return_value=_ok_response()):
        sent = api.send("application_received", candidate, {"job": job}, company=whatsapp_company)
    assert [m.channel for m in sent] == ["email", "whatsapp"]


def test_whatsapp_skipped_without_phone(whatsapp_company, whatsapp_env, candidate, job):
    candidate.phone = ""
    candidate.save(update_fields=["phone"])
    api.set_preference(whatsapp_company, "application_received", ["whatsapp"])
    with mock.patch("requests.post") as post:
        sent = api.send("application_received", candidate, {"job": job}, company=whatsapp_company)
    assert sent[0].status == OutboundMessage.SKIPPED
    assert "phone" in sent[0].error.lower()
    post.assert_not_called()


def test_whatsapp_skipped_without_feature(company, whatsapp_env, candidate, job):
    api.set_preference(company, "application_received", ["whatsapp"])
    with mock.patch("requests.post") as post:
        sent = api.send("application_received", candidate, {"job": job}, company=company)
    assert sent[0].status == OutboundMessage.SKIPPED
    assert "plan" in sent[0].error.lower()
    post.assert_not_called()


def test_whatsapp_skipped_without_config(whatsapp_company, settings, candidate, job):
    settings.WHATSAPP_TOKEN = ""
    settings.WHATSAPP_PHONE_ID = ""
    api.set_preference(whatsapp_company, "application_received", ["whatsapp"])
    with mock.patch("requests.post") as post:
        sent = api.send("application_received", candidate, {"job": job}, company=whatsapp_company)
    assert sent[0].status == OutboundMessage.SKIPPED
    assert "not configured" in sent[0].error.lower()
    post.assert_not_called()


def test_whatsapp_template_message_used_when_asked(whatsapp_company, whatsapp_env, candidate, job):
    with mock.patch("requests.post", return_value=_ok_response()) as post:
        api.send(
            "interview_reminder",
            candidate,
            {"job": job, "template_name": "interview_reminder_v1"},
            company=whatsapp_company,
            channels=["whatsapp"],
        )
    body = post.call_args.kwargs["json"]
    assert body["type"] == "template"
    assert body["template"]["name"] == "interview_reminder_v1"


def test_whatsapp_failure_recorded(whatsapp_company, whatsapp_env, candidate, job):
    bad = mock.Mock()
    bad.status_code = 400
    bad.json.return_value = {"error": {"message": "Invalid recipient"}}
    with mock.patch("requests.post", return_value=bad):
        sent = api.send(
            "application_received", candidate, {"job": job},
            company=whatsapp_company, channels=["whatsapp"],
        )
    message = sent[0]
    assert message.status == OutboundMessage.FAILED
    assert "Invalid recipient" in message.error
    assert message.attempts == 1


def test_network_error_is_recorded_not_raised(whatsapp_company, whatsapp_env, candidate, job):
    with mock.patch("requests.post", side_effect=OSError("no route to host")):
        sent = api.send(
            "application_received", candidate, {"job": job},
            company=whatsapp_company, channels=["whatsapp"],
        )
    assert sent[0].status == OutboundMessage.FAILED
    assert "no route to host" in sent[0].error


def test_broken_mail_backend_records_failure(company, candidate, job, settings):
    settings.EMAIL_BACKEND = "notifications.tests.test_api.ExplodingBackend"
    sent = api.send("application_received", candidate, {"job": job}, company=company)
    assert sent[0].status == OutboundMessage.FAILED


class ExplodingBackend:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("SMTP is down")


def test_candidate_opt_out_is_honoured(whatsapp_company, whatsapp_env, candidate, job):
    CandidateChannelOptOut.objects.create(profile=candidate, channel="whatsapp")
    with mock.patch("requests.post") as post:
        sent = api.send(
            "application_received", candidate, {"job": job},
            company=whatsapp_company, channels=["email", "whatsapp"],
        )
    statuses = {m.channel: m.status for m in sent}
    assert statuses["email"] == OutboundMessage.SENT
    assert statuses["whatsapp"] == OutboundMessage.SKIPPED
    post.assert_not_called()


def test_email_carries_unsubscribe_url(company, candidate, job):
    api.send("application_received", candidate, {"job": job}, company=company)
    body = mail.outbox[0].body
    assert "/notifications/unsubscribe/" in body


def test_email_attachments_are_attached(company, candidate, job):
    api.send(
        "interview_scheduled",
        candidate,
        {"job": job, "attachments": [("invite.ics", b"BEGIN:VCALENDAR", "text/calendar")]},
        company=company,
    )
    assert mail.outbox[0].attachments[0][0] == "invite.ics"


def test_sms_channel_is_a_stub(company, candidate, job):
    sent = api.send(
        "application_received", candidate, {"job": job}, company=company, channels=["sms"]
    )
    assert sent[0].status == OutboundMessage.FAILED
    assert "not implemented" in sent[0].error


def test_unknown_event_raises(company, candidate):
    with pytest.raises(registry.UnknownEvent):
        api.send("no_such_event", candidate, {}, company=company)


def test_all_registered_events_render_on_every_channel(company, candidate, job):
    for event in registry.all_events():
        context = {"job": job, "company": company, "stage_name": "L1"}
        email = api.render_all(event.name, context, channel=registry.EMAIL)
        assert email["subject"].strip(), event.name
        assert email["text"].strip(), event.name
        assert email["html"].strip(), event.name
        if registry.WHATSAPP in event.channels:
            whatsapp = api.render_all(event.name, context, channel=registry.WHATSAPP)
            assert whatsapp["whatsapp"].strip(), event.name


def test_whatsapp_usage_is_metered(whatsapp_company, whatsapp_env, candidate, job):
    import billing

    consume = mock.Mock()
    fake_billing_usage = mock.Mock(consume=consume, QuotaExceeded=RuntimeError)
    with mock.patch.object(
        billing, "usage", fake_billing_usage, create=True
    ), mock.patch("requests.post", return_value=_ok_response()):
        api.send(
            "application_received", candidate, {"job": job},
            company=whatsapp_company, channels=["whatsapp"],
        )
    consume.assert_called_once_with(whatsapp_company, "WHATSAPP_MSG")


def test_whatsapp_skipped_when_quota_exceeded(whatsapp_company, whatsapp_env, candidate, job):
    class QuotaExceeded(Exception):
        pass

    import billing

    fake_billing_usage = mock.Mock(
        consume=mock.Mock(side_effect=QuotaExceeded("no credits left")),
        QuotaExceeded=QuotaExceeded,
    )
    with mock.patch.object(
        billing, "usage", fake_billing_usage, create=True
    ), mock.patch("requests.post") as post:
        sent = api.send(
            "application_received", candidate, {"job": job},
            company=whatsapp_company, channels=["whatsapp"],
        )
    assert sent[0].status == OutboundMessage.SKIPPED
    assert "quota" in sent[0].error.lower()
    post.assert_not_called()


def test_company_is_inferred_from_context(company, candidate, job):
    sent = api.send("application_received", candidate, {"job": job, "company": company})
    assert sent[0].company_id == company.pk


def test_effective_channels_reports_stored_preference(company):
    assert api.effective_channels(company, "application_received") == ["email"]
    api.set_preference(company, "application_received", ["whatsapp", "email"])
    assert api.effective_channels(company, "application_received") == ["email", "whatsapp"]
