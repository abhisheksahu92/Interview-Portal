"""Outbound mail for billing, with a plain-email fallback.

``notifications.send`` is the house entrypoint, but its registry lives in
another app and a missing template must never stop a bill going out — an
invoice nobody is told about is an invoice nobody pays. :func:`notify` tries
the registry first and falls back to a direct ``django.core.mail`` send;
neither path is allowed to raise into a money flow. Same shape as
``contracting.notify``.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


def owner_emails(company):
    """Email addresses of the company's owners — who the bill is addressed to."""
    from core.models import Membership

    return [
        email
        for email in Membership.objects.filter(
            company_id=getattr(company, "pk", None), role=Membership.OWNER
        ).values_list("user__email", flat=True)
        if email
    ]


def billing_url():
    """Absolute link to the billing page, where invoices are paid."""
    from django.urls import reverse

    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    return f"{base}{reverse('billing:overview')}"


def notify(event, recipient, context, *, company=None, subject="", body="", attachments=()):
    """Send ``event`` to ``recipient``; returns ``"notifications"``/``"email"``/``""``."""
    payload = dict(context or {})
    if attachments:
        payload.setdefault("attachments", list(attachments))
    try:
        from notifications import send as notifications_send

        notifications_send(event, recipient, payload, company=company)
        return "notifications"
    except Exception as exc:  # unknown event, missing template, broken channel
        logger.info("billing: notifications.send(%s) unavailable: %s", event, exc)
    email = recipient if isinstance(recipient, str) else getattr(recipient, "email", "")
    if not email:
        return ""
    return "email" if _plain_email(email, subject, body, attachments) else ""


def _plain_email(email, subject, body, attachments=()):
    sender = getattr(settings, "DEFAULT_FROM_EMAIL", "") or "no-reply@localhost"
    try:
        message = EmailMessage(subject or "Update", body or "", sender, [email])
        for name, content, content_type in attachments or ():
            message.attach(name, content, content_type)
        message.send(fail_silently=True)
        return True
    except Exception as exc:  # pragma: no cover - locmem/console backends do not fail
        logger.warning("billing: fallback email to %s failed: %s", email, exc)
        return False
