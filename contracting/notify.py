"""Outbound mail for the contracting app, with a plain-email fallback.

``notifications.send`` is the house entrypoint, but its event registry is owned
by another app and may not carry the contracting events (``timesheet_submitted``,
``client_invoice_sent``, …). Rather than block a month-end invoice run on a
missing template, :func:`notify` tries the registry first and falls back to a
direct ``django.core.mail`` send. Neither path is ever allowed to raise into a
money flow.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def notify(event, recipient, context, *, company=None, subject="", body="", attachments=()):
    """Send ``event`` to ``recipient``; returns ``"notifications"``/``"email"``/``""``."""
    email = _email_of(recipient)
    try:
        from notifications import send as notifications_send

        notifications_send(event, recipient, context, company=company)
        return "notifications"
    except Exception as exc:  # unknown event, missing template, broken channel
        logger.info("contracting: notifications.send(%s) unavailable: %s", event, exc)
    if not email:
        return ""
    return "email" if _plain_email(email, subject, body, attachments) else ""


def _email_of(recipient):
    if isinstance(recipient, str):
        return recipient
    if isinstance(recipient, dict):
        return recipient.get("email", "")
    for attr in ("email", "contact_email"):
        value = getattr(recipient, attr, "")
        if value:
            return value
    user = getattr(recipient, "user", None)
    return getattr(user, "email", "") or ""


def _plain_email(email, subject, body, attachments=()):
    from django.core.mail import EmailMessage

    sender = getattr(settings, "DEFAULT_FROM_EMAIL", "") or "no-reply@localhost"
    try:
        if attachments:
            message = EmailMessage(
                subject or "Update", body or "", sender, [email]
            )
            for name, content, content_type in attachments:
                message.attach(name, content, content_type)
            message.send(fail_silently=True)
        else:
            send_mail(
                subject or "Update", body or "", sender, [email], fail_silently=True
            )
        return True
    except Exception as exc:  # pragma: no cover - console/locmem backends do not fail
        logger.warning("contracting: fallback email to %s failed: %s", email, exc)
        return False
