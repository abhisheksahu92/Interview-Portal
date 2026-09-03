"""Offer lifecycle services: render, send, sign, decline, withdraw, expire."""

import logging

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from jobs.models import Application
from offers import notify
from offers.models import Offer, OfferEvent, OfferTemplate
from offers.pdf import PdfUnavailable, offer_pdf_bytes, offer_pdf_filename
from offers.rendering import offer_context, render_body

logger = logging.getLogger(__name__)


def render_offer(offer, save=False):
    """Render the offer body from its template (or the company default)."""
    template = offer.template or OfferTemplate.default_for(offer.company)
    context = offer_context(offer)
    offer.template = template
    offer.body_rendered = render_body(template.body_html, context)
    if save:
        offer.save(update_fields=["template", "body_rendered", "updated_at"])
    return offer.body_rendered


def rendered_subject(offer):
    template = offer.template or OfferTemplate.default_for(offer.company)
    return template.render_subject(offer_context(offer)) or (
        f"Your offer from {offer.company.name}"
    )


def build_pdf(offer, include_signature=None):
    """Generate the offer PDF and store it on the model; None when unavailable."""
    try:
        content = offer_pdf_bytes(offer, include_signature=include_signature)
    except PdfUnavailable:
        logger.warning("offers: PDF generation unavailable for offer %s", offer.pk)
        return None
    offer.pdf.save(offer_pdf_filename(offer), ContentFile(content), save=False)
    offer.save(update_fields=["pdf", "updated_at"])
    offer.log(OfferEvent.PDF_GENERATED, signed=bool(include_signature or offer.signed_at))
    return offer.pdf


@transaction.atomic
def send_offer(offer, request=None, resend=False):
    """Render, generate the PDF, email the candidate, and mark the offer SENT."""
    render_offer(offer, save=True)
    build_pdf(offer, include_signature=False)

    attachments = []
    if offer.pdf:
        try:
            offer.pdf.open("rb")
            attachments.append((offer_pdf_filename(offer), offer.pdf.read(), "application/pdf"))
        finally:
            offer.pdf.close()

    sign_url = offer.sign_url(request)
    subject = rendered_subject(offer)
    # ``job``/``offer``/``offer_url`` are what the notifications app's
    # ``offer_sent`` templates read; the flat keys serve the email fallback.
    context = {
        "offer": offer,
        "job": offer.application.job,
        "application": offer.application,
        "offer_url": sign_url,
        "offer_id": offer.pk,
        "candidate_name": offer.application.candidate.user.get_full_name()
        or offer.candidate_user.email,
        "job_title": offer.application.job.title,
        "company_name": offer.company.name,
        "salary": str(offer.salary),
        "currency": offer.currency,
        "joining_date": str(offer.joining_date or ""),
        "expires_at": str(offer.expires_at or ""),
        "sign_url": sign_url,
        "subject": subject,
    }
    body = (
        f"{context['candidate_name']},\n\n"
        f"Your offer for {context['job_title']} at {context['company_name']} is attached.\n"
        f"Review and sign it here: {sign_url}\n"
    )
    notify.send_event(
        "offer_sent",
        offer.candidate_user,
        context,
        company=offer.company,
        subject=subject,
        body=body,
        attachments=attachments,
    )

    now = timezone.now()
    offer.status = Offer.SENT
    offer.sent_at = offer.sent_at or now
    offer.viewed_at = None if resend else offer.viewed_at
    offer.save(update_fields=["status", "sent_at", "viewed_at", "updated_at"])
    offer.log(OfferEvent.RESENT if resend else OfferEvent.SENT, to=offer.candidate_user.email)
    return offer


def mark_viewed(offer):
    """Record the candidate opening the signing page."""
    if offer.status != Offer.SENT:
        return offer
    offer.status = Offer.VIEWED
    offer.viewed_at = timezone.now()
    offer.save(update_fields=["status", "viewed_at", "updated_at"])
    offer.log(OfferEvent.VIEWED)
    return offer


def client_ip(request):
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded or request.META.get("REMOTE_ADDR") or None


@transaction.atomic
def accept_offer(offer, signed_name, request=None):
    """Record the signature, mark ACCEPTED and set the application HIRED."""
    now = timezone.now()
    offer.status = Offer.ACCEPTED
    offer.signed_name = signed_name.strip()[:150]
    offer.signed_at = now
    if request is not None:
        offer.signed_ip = client_ip(request)
        offer.signed_user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:400]
    offer.save(
        update_fields=[
            "status",
            "signed_name",
            "signed_at",
            "signed_ip",
            "signed_user_agent",
            "updated_at",
        ]
    )
    offer.log(
        OfferEvent.ACCEPTED,
        signed_name=offer.signed_name,
        ip=offer.signed_ip,
        user_agent=offer.signed_user_agent,
    )
    build_pdf(offer, include_signature=True)

    application = offer.application
    if application.status != Application.HIRED:
        application.status = Application.HIRED
        application.save(update_fields=["status", "updated_at"])

    _notify_recruiter(offer, "accepted")
    return offer


@transaction.atomic
def decline_offer(offer, reason="", request=None):
    offer.status = Offer.DECLINED
    offer.decline_reason = (reason or "").strip()
    offer.signed_at = timezone.now()
    if request is not None:
        offer.signed_ip = client_ip(request)
        offer.signed_user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:400]
    offer.save(
        update_fields=[
            "status",
            "decline_reason",
            "signed_at",
            "signed_ip",
            "signed_user_agent",
            "updated_at",
        ]
    )
    offer.log(OfferEvent.DECLINED, reason=offer.decline_reason, ip=offer.signed_ip)
    _notify_recruiter(offer, "declined")
    return offer


def withdraw_offer(offer, by=None):
    offer.status = Offer.WITHDRAWN
    offer.save(update_fields=["status", "updated_at"])
    offer.log(OfferEvent.WITHDRAWN, by=getattr(by, "email", None))
    return offer


def expire_offers(now=None):
    """Mark every open, past-expiry offer EXPIRED. Returns the count."""
    now = now or timezone.now()
    stale = list(Offer.objects.expiring_before(now).select_related("application__job__company"))
    for offer in stale:
        offer.status = Offer.EXPIRED
        offer.save(update_fields=["status", "updated_at"])
        offer.log(OfferEvent.EXPIRED, at=now.isoformat())
    return len(stale)


def _notify_recruiter(offer, outcome):
    recipient = offer.created_by or offer.application.job.created_by
    if recipient is None:
        return False
    candidate = offer.candidate_user
    name = candidate.get_full_name() or candidate.email
    subject = f"[Interview Portal] Offer {outcome}: {name} — {offer.application.job.title}"
    body = (
        f"{name} has {outcome} the offer for {offer.application.job.title}.\n"
        f"{('Reason: ' + offer.decline_reason) if offer.decline_reason else ''}"
    )
    return notify.send_event(
        "offer_sent",
        recipient,
        {
            "offer": offer,
            "job": offer.application.job,
            "application": offer.application,
            "offer_url": offer.sign_url(),
            "offer_id": offer.pk,
            "outcome": outcome,
            "candidate_name": name,
            "job_title": offer.application.job.title,
            "decline_reason": offer.decline_reason,
        },
        company=offer.company,
        subject=subject,
        body=body,
        use_registry=False,
    )
