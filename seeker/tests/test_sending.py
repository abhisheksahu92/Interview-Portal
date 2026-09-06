"""Sending goes out of the seeker's own SMTP mailbox, and only then costs a send."""

import smtplib

import pytest

from seeker import services
from seeker.mail import SMTPBackend
from seeker.models import Outreach, SavedItem

pytestmark = pytest.mark.django_db


class FakeSMTP:
    """Stands in for ``smtplib.SMTP``; records what was logged in and sent."""

    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.started_tls = False
        self.login_args = None
        self.messages = []
        self.fail_login = False
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        if self.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"nope")
        self.login_args = (user, password)

    def send_message(self, message):
        self.messages.append(message)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


@pytest.fixture
def mailbox(seeker):
    seeker.mailbox_kind = seeker.SMTP
    seeker.mailbox_email = "priya@example.test"
    seeker.set_mailbox_config(
        {"host": "smtp.example.test", "port": 587, "username": "priya", "password": "app-pw"}
    )
    seeker.save()
    return seeker


def _outreach(seeker, make_lead, to="hiring@zeta.test"):
    item = SavedItem.objects.create(seeker=seeker, lead=make_lead())
    return Outreach.objects.create(
        seeker=seeker, saved_item=item, to_email=to, subject="Hi", body="Hello there."
    )


def test_send_uses_the_seekers_own_mailbox(smtp, mailbox, make_lead):
    outreach = _outreach(mailbox, make_lead)
    assert services.send_outreach(outreach) is True
    sent = smtp.instances[0].messages[0]
    assert smtp.instances[0].login_args == ("priya", "app-pw")
    assert smtp.instances[0].started_tls
    assert sent["To"] == "hiring@zeta.test"
    assert "priya@example.test" in sent["From"]
    assert sent["Reply-To"] == "priya@example.test"


def test_a_successful_send_marks_contacted_and_costs_one(smtp, mailbox, make_lead):
    outreach = _outreach(mailbox, make_lead)
    services.send_outreach(outreach)
    outreach.refresh_from_db()
    assert outreach.status == Outreach.SENT
    assert (
        outreach.saved_item.__class__.objects.get(pk=outreach.saved_item_id).status == "CONTACTED"
    )
    mailbox.refresh_from_db()
    assert mailbox.sends_left() == 9


def test_a_failed_login_costs_nothing(smtp, mailbox, make_lead):
    outreach = _outreach(mailbox, make_lead)
    original = FakeSMTP.__init__

    def failing_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.fail_login = True

    FakeSMTP.__init__ = failing_init
    try:
        assert services.send_outreach(outreach) is False
    finally:
        FakeSMTP.__init__ = original
    outreach.refresh_from_db()
    assert outreach.status == Outreach.FAILED
    mailbox.refresh_from_db()
    assert mailbox.sends_left() == 10


def test_without_a_mailbox_nothing_leaves(seeker, make_lead):
    outreach = _outreach(seeker, make_lead)
    assert services.send_outreach(outreach) is False
    outreach.refresh_from_db()
    assert outreach.status == Outreach.FAILED
    assert "No mailbox" in outreach.error


def test_the_resume_is_attached_when_there_is_one(smtp, mailbox, make_lead):
    from django.core.files.base import ContentFile

    candidate = services.candidate_profile_for(mailbox.user)
    candidate.resume.save("priya.pdf", ContentFile(b"%PDF-1.4 fake"), save=True)
    outreach = _outreach(mailbox, make_lead)
    services.send_outreach(outreach)
    sent = smtp.instances[0].messages[0]
    names = [part.get_filename() for part in sent.iter_attachments()]
    assert any(name and name.endswith(".pdf") for name in names)
    candidate.resume.delete(save=True)


def test_send_many_checks_the_quota_before_sending_anything(smtp, mailbox, make_lead):
    services.record_send(mailbox, 10)
    outreach = _outreach(mailbox, make_lead)
    with pytest.raises(services.QuotaExceeded):
        services.send_many(mailbox, [outreach])
    assert smtp.instances == []


def test_smtp_backend_reports_a_missing_host(mailbox):
    from seeker.mail import Message, SendError

    backend = SMTPBackend({"username": "priya"})
    with pytest.raises(SendError):
        backend.send(Message(to_email="a@b.test", subject="s", body="b", from_email="c@d.test"))
