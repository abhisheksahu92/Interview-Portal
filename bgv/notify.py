"""Outbound mail for BGV, with a plain-email fallback.

``notifications.send`` is the house entrypoint but its event registry is owned
by another app and may not carry the BGV events, so a missing template must
never stop a consent request or a completed report from reaching someone.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def notify(event, recipient, context, *, company=None, subject="", body=""):
    """Send ``event`` to ``recipient``; returns ``"notifications"``/``"email"``/``""``."""
    try:
        from notifications import send as notifications_send

        notifications_send(event, recipient, context, company=company)
        return "notifications"
    except Exception as exc:  # unknown event, missing template, broken channel
        logger.info("bgv: notifications.send(%s) unavailable: %s", event, exc)
    email = _email_of(recipient)
    if not email:
        return ""
    sender = getattr(settings, "DEFAULT_FROM_EMAIL", "") or "no-reply@localhost"
    try:
        send_mail(subject or "Update", body or "", sender, [email], fail_silently=True)
        return "email"
    except Exception as exc:  # pragma: no cover - locmem/console backends do not fail
        logger.warning("bgv: fallback email to %s failed: %s", email, exc)
        return ""


def _email_of(recipient):
    if isinstance(recipient, str):
        return recipient
    if isinstance(recipient, dict):
        return recipient.get("email", "")
    email = getattr(recipient, "email", "")
    if email:
        return email
    return getattr(getattr(recipient, "user", None), "email", "") or ""
