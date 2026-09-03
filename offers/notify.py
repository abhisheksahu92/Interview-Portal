"""Outbound notification seam for the offers app.

The notifications app owns the real fan-out (``notifications.send``); it is built
in parallel, so every call imports it late and falls back to a plain Django email
(with attachments preserved) when it is unavailable.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


def send_event(
    event,
    recipient,
    context,
    company=None,
    subject=None,
    body=None,
    attachments=None,
    use_registry=True,
):
    """Notify ``recipient`` about ``event``; True when something was sent.

    ``recipient`` may be a ``core.User`` or a bare email string. ``attachments``
    is a list of ``(filename, content, mimetype)`` tuples. Pass
    ``use_registry=False`` for internal, recruiter-facing mail that has no
    registered event template of its own — it goes straight to plain email.
    """
    attachments = list(attachments or [])
    payload = dict(context or {})
    if attachments:
        payload["attachments"] = attachments

    try:
        from notifications import send as notifications_send

        if not use_registry:
            notifications_send = None
    except Exception:  # ImportError, or the app not ready yet
        notifications_send = None

    if callable(notifications_send):
        try:
            notifications_send(event, recipient, payload, company=company)
            return True
        except Exception:  # notifications app still in progress — never block the UI
            logger.warning("offers: notifications.send(%s) failed; emailing", event)

    email = getattr(recipient, "email", recipient)
    if not email:
        return False
    message = EmailMessage(
        subject=subject or f"[Interview Portal] {event.replace('_', ' ').title()}",
        body=body or _default_body(event, context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    for filename, content, mimetype in attachments:
        message.attach(filename, content, mimetype)
    message.send(fail_silently=True)
    return True


def _default_body(event, context):
    lines = [f"Event: {event}", ""]
    lines += [
        f"{key}: {value}"
        for key, value in (context or {}).items()
        if key != "attachments"
    ]
    return "\n".join(lines)
