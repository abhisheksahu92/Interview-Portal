"""Offer letter UI: recruiter templates/offers plus the candidate signing page."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from billing.entitlements import require_feature
from core.models import Membership
from core.permissions import role_required
from jobs.models import Application
from offers import services
from offers.forms import DeclineForm, OfferForm, OfferTemplateForm, SignForm
from offers.models import Offer, OfferEvent, OfferTemplate
from offers.pdf import offer_pdf_filename
from offers.rendering import PLACEHOLDERS, offer_context, render_body, sample_context

STAFF_ROLES = (Membership.OWNER, Membership.RECRUITER)

FEATURE = "offers"


def recruiter_view(view_func):
    """login + staff role + the ``offers`` plan feature."""
    return login_required(role_required(*STAFF_ROLES)(require_feature(FEATURE)(view_func)))


def _company(request):
    company = getattr(request, "company", None)
    if company is None:
        raise PermissionDenied("No company selected for this user.")
    return company


def _offers(request):
    return Offer.objects.for_company(_company(request)).select_related(
        "application__job", "application__candidate__user", "template"
    )


def _get_offer(request, pk):
    return get_object_or_404(_offers(request), pk=pk)


# --- recruiter: offers list & detail ---------------------------------------


@recruiter_view
def index(request):
    """All offers for the active company, newest first."""
    offers = list(_offers(request))
    status = request.GET.get("status") or ""
    if status:
        offers = [offer for offer in offers if offer.status == status]
    counts = {}
    for offer in _offers(request):
        counts[offer.status] = counts.get(offer.status, 0) + 1
    return render(
        request,
        "offers/offer_list.html",
        {
            "offers": offers,
            "status_choices": Offer.STATUS_CHOICES,
            "status": status,
            "counts": counts,
            "open_count": sum(counts.get(s, 0) for s in Offer.OPEN_STATUSES),
        },
    )


@recruiter_view
def offer_detail(request, pk):
    offer = _get_offer(request, pk)
    return render(
        request,
        "offers/offer_detail.html",
        {
            "offer": offer,
            "events": offer.events.all(),
            "sign_url": offer.sign_url(request),
            "esign_configured": _esign_configured(),
        },
    )


def _esign_configured():
    from offers.gateway import configured

    return configured()


@recruiter_view
def offer_create(request, application_id):
    """Create (and optionally send) an offer for one application."""
    application = get_object_or_404(
        Application.objects.select_related("job__company", "candidate__user"),
        pk=application_id,
        job__company=_company(request),
    )
    template = OfferTemplate.default_for(application.job.company)
    initial = {
        "template": template.pk,
        "currency": "INR",
        "expires_at": (timezone.localtime() + timezone.timedelta(days=7)).strftime(
            "%Y-%m-%dT%H:%M"
        ),
    }
    if request.method == "POST":
        form = OfferForm(request.POST, company=application.job.company)
        if form.is_valid():
            offer = form.save(commit=False)
            offer.application = application
            offer.created_by = request.user
            offer.template = form.cleaned_data.get("template") or template
            offer.custom_fields = form.cleaned_data.get("custom_fields_text") or {}
            offer.save()
            offer.log(OfferEvent.CREATED, by=request.user.email)
            services.render_offer(offer, save=True)
            if request.POST.get("action") == "send":
                services.send_offer(offer, request=request)
                messages.success(request, "Offer sent to the candidate.")
            else:
                messages.success(request, "Offer saved as a draft.")
            return redirect("offers:detail", pk=offer.pk)
    else:
        form = OfferForm(initial=initial, company=application.job.company)
    return render(
        request,
        "offers/offer_form.html",
        {
            "form": form,
            "application": application,
            "placeholders": PLACEHOLDERS,
            "preview_url": reverse("offers:offer_preview", args=[application.pk]),
        },
    )


@recruiter_view
def offer_preview(request, application_id):
    """HTMX live preview of the offer body while the recruiter edits it."""
    application = get_object_or_404(
        Application.objects.select_related("job__company", "candidate__user"),
        pk=application_id,
        job__company=_company(request),
    )
    form = OfferForm(request.POST or None, company=application.job.company)
    form.is_valid()
    data = form.cleaned_data if hasattr(form, "cleaned_data") else {}
    draft = Offer(
        application=application,
        template=data.get("template"),
        salary=data.get("salary") or 0,
        currency=data.get("currency") or "INR",
        joining_date=data.get("joining_date"),
        expires_at=data.get("expires_at"),
        custom_fields=data.get("custom_fields_text") or {},
    )
    template = draft.template or OfferTemplate.default_for(application.job.company)
    body = render_body(template.body_html, offer_context(draft))
    return render(request, "offers/_preview.html", {"body": body})


@recruiter_view
@require_POST
def offer_send(request, pk):
    offer = _get_offer(request, pk)
    if offer.status not in (Offer.DRAFT, Offer.WITHDRAWN, Offer.EXPIRED):
        messages.error(request, "This offer has already been sent.")
    else:
        services.send_offer(offer, request=request)
        messages.success(request, "Offer sent to the candidate.")
    return redirect("offers:detail", pk=offer.pk)


@recruiter_view
@require_POST
def offer_resend(request, pk):
    offer = _get_offer(request, pk)
    if offer.status in (Offer.ACCEPTED, Offer.DECLINED):
        messages.error(request, "This offer has already been decided.")
    else:
        services.send_offer(offer, request=request, resend=True)
        messages.success(request, "Offer email resent.")
    return redirect("offers:detail", pk=offer.pk)


@recruiter_view
@require_POST
def offer_withdraw(request, pk):
    offer = _get_offer(request, pk)
    if offer.status in (Offer.ACCEPTED, Offer.DECLINED):
        messages.error(request, "A decided offer cannot be withdrawn.")
    else:
        services.withdraw_offer(offer, by=request.user)
        messages.success(request, "Offer withdrawn.")
    return redirect("offers:detail", pk=offer.pk)


@recruiter_view
def offer_pdf(request, pk):
    offer = _get_offer(request, pk)
    return _pdf_response(offer)


def _pdf_response(offer):
    if not offer.pdf:
        services.build_pdf(offer)
    if not offer.pdf:
        raise Http404("The offer PDF could not be generated.")
    offer.pdf.open("rb")
    return FileResponse(
        offer.pdf, as_attachment=True, filename=offer_pdf_filename(offer),
        content_type="application/pdf",
    )


# --- recruiter: templates --------------------------------------------------


@recruiter_view
def template_list(request):
    company = _company(request)
    OfferTemplate.default_for(company)
    return render(
        request,
        "offers/template_list.html",
        {
            "templates": OfferTemplate.objects.for_company(company),
            "placeholders": PLACEHOLDERS,
        },
    )


@recruiter_view
def template_create(request):
    company = _company(request)
    from offers.models import DEFAULT_TEMPLATE_BODY, DEFAULT_TEMPLATE_SUBJECT

    if request.method == "POST":
        form = OfferTemplateForm(request.POST, company=company)
        if form.is_valid():
            template = form.save()
            messages.success(request, f"Template “{template.name}” created.")
            return redirect("offers:template_edit", pk=template.pk)
    else:
        form = OfferTemplateForm(
            company=company,
            initial={
                "subject": DEFAULT_TEMPLATE_SUBJECT,
                "body_html": DEFAULT_TEMPLATE_BODY,
            },
        )
    return render(
        request,
        "offers/template_form.html",
        {"form": form, "placeholders": PLACEHOLDERS, "creating": True},
    )


@recruiter_view
def template_edit(request, pk):
    company = _company(request)
    template = get_object_or_404(OfferTemplate.objects.for_company(company), pk=pk)
    if request.method == "POST":
        form = OfferTemplateForm(request.POST, instance=template, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Template saved.")
            return redirect("offers:template_edit", pk=template.pk)
    else:
        form = OfferTemplateForm(instance=template, company=company)
    return render(
        request,
        "offers/template_form.html",
        {
            "form": form,
            "template": template,
            "placeholders": PLACEHOLDERS,
            "preview": render_body(template.body_html, sample_context(company)),
        },
    )


@recruiter_view
@require_POST
def template_delete(request, pk):
    company = _company(request)
    template = get_object_or_404(OfferTemplate.objects.for_company(company), pk=pk)
    name = template.name
    template.delete()
    messages.success(request, f"Template “{name}” deleted.")
    return redirect("offers:template_list")


@recruiter_view
@require_POST
def template_preview(request):
    """HTMX preview of a template body with sample placeholder values."""
    body = render_body(request.POST.get("body_html", ""), sample_context(_company(request)))
    return render(request, "offers/_preview.html", {"body": body})


# --- candidate: signing page ----------------------------------------------


def _offer_by_token(token):
    offer = (
        Offer.objects.select_related(
            "application__job__company", "application__candidate__user", "template"
        )
        .filter(sign_token=token)
        .first()
    )
    if offer is None:
        raise Http404("Unknown offer link.")
    return offer


def _sync_expiry(offer):
    if offer.is_open and offer.is_expired:
        offer.status = Offer.EXPIRED
        offer.save(update_fields=["status", "updated_at"])
        offer.log(OfferEvent.EXPIRED)
    return offer


def _blocked_message(offer):
    if offer.status == Offer.DRAFT:
        return "This offer has not been sent yet."
    if offer.status == Offer.WITHDRAWN:
        return "This offer has been withdrawn by the employer. Please contact your recruiter."
    if offer.status == Offer.EXPIRED:
        return "This offer link has expired. Please contact your recruiter for a new offer."
    if offer.status == Offer.ACCEPTED:
        return "You have already accepted this offer."
    if offer.status == Offer.DECLINED:
        return "You have already declined this offer."
    return ""


def sign(request, token):
    """Public, token-gated signing page."""
    offer = _sync_expiry(_offer_by_token(token))
    if offer.is_signable:
        services.mark_viewed(offer)
    if not offer.body_rendered:
        services.render_offer(offer, save=True)
    candidate = offer.candidate_user
    return render(
        request,
        "offers/sign.html",
        {
            "offer": offer,
            "blocked": _blocked_message(offer),
            "sign_form": SignForm(expected_name=candidate.get_full_name()),
            "decline_form": DeclineForm(),
            "candidate": candidate,
        },
    )


@require_POST
def sign_accept(request, token):
    offer = _sync_expiry(_offer_by_token(token))
    if not offer.is_signable:
        messages.error(request, _blocked_message(offer) or "This offer can no longer be signed.")
        return redirect("offers:sign", token=token)
    form = SignForm(request.POST, expected_name=offer.candidate_user.get_full_name())
    if not form.is_valid():
        return render(
            request,
            "offers/sign.html",
            {
                "offer": offer,
                "blocked": "",
                "sign_form": form,
                "decline_form": DeclineForm(),
                "candidate": offer.candidate_user,
            },
            status=400,
        )
    services.accept_offer(offer, form.cleaned_data["signed_name"], request=request)
    messages.success(request, "Offer accepted — welcome aboard!")
    return redirect("offers:sign", token=token)


@require_POST
def sign_decline(request, token):
    offer = _sync_expiry(_offer_by_token(token))
    if not offer.is_signable:
        messages.error(request, _blocked_message(offer) or "This offer can no longer be declined.")
        return redirect("offers:sign", token=token)
    form = DeclineForm(request.POST)
    reason = form.cleaned_data.get("decline_reason", "") if form.is_valid() else ""
    services.decline_offer(offer, reason=reason, request=request)
    messages.info(request, "Offer declined. Thank you for letting us know.")
    return redirect("offers:sign", token=token)


def sign_pdf(request, token):
    """Token-checked streaming PDF download for the candidate."""
    offer = _offer_by_token(token)
    if offer.status == Offer.DRAFT:
        raise Http404("This offer has not been sent yet.")
    return _pdf_response(offer)


# --- candidate: my offers -------------------------------------------------


@login_required
def my_offers(request):
    profile = getattr(request.user, "candidate_profile", None)
    offers = (
        Offer.objects.filter(application__candidate=profile)
        .exclude(status=Offer.DRAFT)
        .select_related("application__job__company")
        if profile is not None
        else Offer.objects.none()
    )
    return render(request, "offers/my_offers.html", {"offers": offers})


def healthz(request):  # pragma: no cover - trivial helper kept out of urls
    return HttpResponse("ok")
