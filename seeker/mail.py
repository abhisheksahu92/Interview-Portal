"""Sending from the seeker's *own* mailbox.

Outreach is 1:1 mail from a job hunter to a hiring manager. It must leave from
an address the recipient can reply to and that carries the seeker's own sending
reputation, so nothing here ever touches ``DEFAULT_FROM_EMAIL`` or Django's
mail backend — that is the platform's transactional mailbox and borrowing it
would make every seeker's cold mail our deliverability problem.

Two backends sit behind one :class:`MailBackend` interface: SMTP with an app
password, and the Gmail API with an OAuth refresh token. Both take the same
:class:`Message` and return a provider message id.
"""

import json
import logging
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from email.message import EmailMessage

from django.conf import settings

logger = logging.getLogger(__name__)

TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_SEND_URI = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
#: Send-only: the portal never reads a seeker's inbox.
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class SendError(Exception):
    """The mailbox refused the message. Carries a human-readable reason."""


@dataclass
class Attachment:
    filename: str
    content: bytes
    mimetype: str = "application/octet-stream"


@dataclass
class Message:
    to_email: str
    subject: str
    body: str
    from_email: str
    from_name: str = ""
    reply_to: str = ""
    attachments: list = field(default_factory=list)

    def as_email(self):
        """Build the RFC-822 message both backends put on the wire."""
        mail = EmailMessage()
        mail["To"] = self.to_email
        mail["Subject"] = self.subject
        mail["From"] = (
            f"{self.from_name} <{self.from_email}>" if self.from_name else self.from_email
        )
        mail["Reply-To"] = self.reply_to or self.from_email
        mail.set_content(self.body)
        for attachment in self.attachments:
            main, _, sub = attachment.mimetype.partition("/")
            mail.add_attachment(
                attachment.content,
                maintype=main or "application",
                subtype=sub or "octet-stream",
                filename=attachment.filename,
            )
        return mail


class MailBackend:
    """One method, so the caller never branches on mailbox kind."""

    def send(self, message: Message) -> str:
        raise NotImplementedError


class SMTPBackend(MailBackend):
    """Username + app password against the seeker's own SMTP host."""

    def __init__(self, config):
        self.host = (config.get("host") or "").strip()
        self.port = int(config.get("port") or 587)
        self.username = (config.get("username") or "").strip()
        self.password = config.get("password") or ""
        self.use_ssl = bool(config.get("use_ssl"))

    def send(self, message: Message) -> str:
        if not self.host or not self.username:
            raise SendError("This mailbox is missing its SMTP host or username.")
        mail = message.as_email()
        try:
            opener = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
            with opener(self.host, self.port, timeout=30) as server:
                if not self.use_ssl:
                    server.starttls()
                server.login(self.username, self.password)
                server.send_message(mail)
        except smtplib.SMTPAuthenticationError as exc:
            raise SendError("The mailbox rejected those credentials.") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise SendError(f"The mail could not be sent: {exc}") from exc
        return mail.get("Message-ID", "") or ""


def gmail_configured():
    return bool(
        getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
        and getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "")
    )


def gmail_authorize_url(redirect_uri, state):
    """Consent URL for the send-only scope. ``prompt=consent`` forces a refresh token."""
    query = urllib.parse.urlencode(
        {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"{AUTH_URI}?{query}"


def _post_form(url, data):
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def gmail_exchange_code(code, redirect_uri):
    """Swap the consent code for tokens. Same shape as the calendar adapter's."""
    try:
        return _post_form(
            TOKEN_URI,
            {
                "code": code,
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SendError(f"Google would not issue a token: {exc}") from exc


class GmailBackend(MailBackend):
    """Gmail API ``users.messages.send`` with a stored refresh token."""

    def __init__(self, config):
        self.refresh_token = config.get("refresh_token") or ""

    def _access_token(self):
        if not self.refresh_token:
            raise SendError("Reconnect Gmail: no refresh token is stored.")
        try:
            payload = _post_form(
                TOKEN_URI,
                {
                    "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise SendError(f"Google would not refresh the token: {exc}") from exc
        token = (payload or {}).get("access_token")
        if not token:
            raise SendError("Reconnect Gmail: the refresh token is no longer valid.")
        return token

    def send(self, message: Message) -> str:
        import base64

        raw = base64.urlsafe_b64encode(message.as_email().as_bytes()).decode()
        request = urllib.request.Request(
            GMAIL_SEND_URI,
            data=json.dumps({"raw": raw}).encode(),
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise SendError(f"Gmail refused the message: {exc}") from exc
        return (payload or {}).get("id", "")


def backend_for(seeker):
    """The backend for this seeker's mailbox, or ``None`` when none is connected."""
    config = seeker.get_mailbox_config()
    if seeker.mailbox_kind == seeker.SMTP:
        return SMTPBackend(config)
    if seeker.mailbox_kind == seeker.GMAIL:
        return GmailBackend(config)
    return None
