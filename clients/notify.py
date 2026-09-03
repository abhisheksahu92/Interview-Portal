"""Outbound notification seam for the clients app.

The notifications app owns the real fan-out (``notifications.send``). It is being
built in parallel, so every call goes through :func:`send_event`, which imports it
late and falls back to a plain Django email when it is unavailable.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_event(event, recipient, context, company=None, subject=None, body=None):
    """Notify ``recipient`` about ``event``; True when something was sent.

    ``recipient`` may be a ``core.User`` or a bare email string.
    """
    try:  # pragma: no cover - exercised through both branches in tests
        from notifications import send as notifications_send
    except Exception:  # ImportError, or the app not ready yet
        notifications_send = None

    if callable(notifications_send):
        try:
            notifications_send(event, recipient, context, company=company)
            return True
        except Exception:  # notifications app still in progress — never block the UI
            logger.warning("clients: notifications.send(%s) failed; emailing", event)

    email = getattr(recipient, "email", recipient)
    if not email:
        return False
    send_mail(
        subject or f"[Interview Portal] {event.replace('_', ' ').title()}",
        body or _default_body(event, context),
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=True,
    )
    return True


def _default_body(event, context):
    lines = [f"Event: {event}", ""]
    lines += [f"{key}: {value}" for key, value in (context or {}).items()]
    return "\n".join(lines)
