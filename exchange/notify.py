"""Outbound notification seam for the exchange app.

Mirrors ``clients/notify.py``: ``notifications.send`` is imported late and a
plain email is used when it is unavailable, so exchange flows never break on the
notifications app.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

#: Recipient roles that get exchange notifications.
STAFF_ROLES = ("OWNER", "RECRUITER")


def send_event(event, recipient, context, company=None, subject=None, body=None):
    """Notify ``recipient`` (User or email string) about ``event``."""
    try:  # pragma: no cover - both branches are exercised in tests
        from notifications import send as notifications_send
    except Exception:
        notifications_send = None

    if callable(notifications_send):
        try:
            notifications_send(event, recipient, context, company=company)
            return True
        except Exception:
            logger.warning("exchange: notifications.send(%s) failed; emailing", event)

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


def notify_company(company, event, context, subject=None, body=None):
    """Send ``event`` to every owner/recruiter of ``company``; count sent."""
    if company is None:
        return 0
    emails = list(
        company.memberships.filter(role__in=STAFF_ROLES)
        .values_list("user__email", flat=True)
        .distinct()
    )
    sent = 0
    for email in emails:
        if send_event(event, email, context, company=company, subject=subject, body=body):
            sent += 1
    return sent
