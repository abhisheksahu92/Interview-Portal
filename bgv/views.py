"""BGV views: recruiter workspace, candidate consent, vendor webhook, margin.

Access rules, one per audience:

* **Recruiters** — ``login_required`` + OWNER/RECRUITER + the ``bgv``
  entitlement, composed once in :func:`_recruiter_view`.
* **Candidates** — no login. The order's token *is* the credential, resolved
  through :mod:`core.tokens` so a bad link gets 410/404, never a leak.
* **Platform staff** — ``/bgv/admin-margin/`` is ``is_staff`` only: what the
  vendor charges us is never shown to a tenant.
* **The vendor** — ``/bgv/webhook/`` is csrf-exempt and HMAC-verified; a bad or
  missing signature is a flat 400.
"""

import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from bgv import gateway, services
from bgv.forms import ConsentForm, OrderFilterForm, OrderForm
from bgv.models import CheckPackage, VerificationOrder
from billing.entitlements import require_feature
from core.models import Membership
from core.permissions import role_required
from core.tokens import resolve_token, token_invalid_response
from jobs.models import Application

logger = logging.getLogger(__name__)

RECRUITER_ROLES = (Membership.OWNER, Membership.RECRUITER)
FEATURE = "bgv"


def _recruiter_view(view_func):
    """login + tenant role + feature gate, in that order."""
    return login_required(role_required(*RECRUITER_ROLES)(require_feature(FEATURE)(view_func)))


def _order(request, pk):
    return get_object_or_404(
        VerificationOrder.objects.select_related(
            "candidate__user", "package", "application__job"
        ).for_company(request.company),
        pk=pk,
    )


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


# --------------------------------------------------------------------------- #
# Recruiter workspace
# --------------------------------------------------------------------------- #


@_recruiter_view
def index(request):
    """Orders list with a status filter; margin summary for platform staff."""
    form = OrderFilterForm(request.GET or None)
    orders = VerificationOrder.objects.for_company(request.company).select_related(
        "candidate__user", "package", "application__job"
    )
    status = ""
    if form.is_valid():
        status = form.cleaned_data.get("status") or ""
    if status:
        orders = orders.filter(status=status)
    context = {
        "orders": orders,
        "form": form,
        "packages": services.available_packages(),
        "is_live": gateway.is_live(),
    }
    if request.user.is_staff:
        context["margin"] = services.margin_summary(request.company)
    return render(request, "bgv/index.html", context)


@_recruiter_view
def order_create(request, application_id):
    """Choose a package for one application and raise the order."""
    application = get_object_or_404(
        Application.objects.select_related("candidate__user", "job"),
        pk=application_id,
        job__company=request.company,
    )
    form = OrderForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        order = services.create_order(
            request.company,
            application.candidate,
            form.cleaned_data["package"],
            application=application,
            ordered_by=request.user,
        )
        messages.success(
            request,
            "Consent request sent. Your company is charged only once the candidate consents.",
        )
        return redirect("bgv:order_detail", pk=order.pk)
    return render(
        request,
        "bgv/order_form.html",
        {
            "form": form,
            "application": application,
            "packages": services.available_packages(),
        },
    )


@_recruiter_view
def order_detail(request, pk):
    order = _order(request, pk)
    return render(
        request,
        "bgv/order_detail.html",
        {
            "order": order,
            "rows": order.result_rows,
            "consent_link": services.consent_url(order),
            "show_margin": request.user.is_staff,
        },
    )


@_recruiter_view
@require_POST
def order_cancel(request, pk):
    order = _order(request, pk)
    if services.cancel_order(order):
        messages.success(request, "Order cancelled. Nothing was charged.")
    else:
        messages.error(
            request, "This check has already been consented to and cannot be cancelled here."
        )
    return redirect("bgv:order_detail", pk=order.pk)


@_recruiter_view
@require_POST
def order_refresh(request, pk):
    """Manual poll — the same call `manage.py bgv_poll` makes on a schedule."""
    order = _order(request, pk)
    services.poll_order(order)
    return redirect("bgv:order_detail", pk=order.pk)


@_recruiter_view
def order_report(request, pk):
    order = _order(request, pk)
    if not order.report_file:
        services.build_report(order)
    if not order.report_file:
        messages.error(request, "The report is not available yet.")
        return redirect("bgv:order_detail", pk=order.pk)
    order.report_file.open("rb")
    return FileResponse(
        order.report_file,
        as_attachment=True,
        filename=f"verification-report-{order.pk}.pdf",
        content_type="application/pdf",
    )


@login_required
def admin_margin(request):
    """Platform economics. ``is_staff`` only — tenants never see vendor cost."""
    if not request.user.is_staff:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("Platform staff only.")
    return render(
        request,
        "bgv/admin_margin.html",
        {
            "totals": services.margin_summary(),
            "rows": services.margin_by_company(),
            "packages": CheckPackage.objects.all(),
        },
    )


# --------------------------------------------------------------------------- #
# Candidate consent (token only)
# --------------------------------------------------------------------------- #


def consent(request, token):
    """Standalone consent page. The token in the URL is the only credential."""
    resolution = resolve_token(
        VerificationOrder,
        token,
        select_related=("company", "candidate__user", "package", "application__job"),
    )
    if not resolution.ok:
        return token_invalid_response(request, resolution)
    order = resolution.obj
    if order.status == VerificationOrder.CANCELLED:
        return token_invalid_response(request, resolution, status=410)
    already = order.consent_given_at is not None
    form = ConsentForm(request.POST or None, order=order)
    if request.method == "POST" and not already and form.is_valid():
        services.record_consent(
            order, name=form.cleaned_data["full_name"], ip=client_ip(request)
        )
        return redirect("bgv:consent", token=order.token)
    return render(
        request,
        "bgv/consent.html",
        {"order": order, "form": form, "already": already or order.consent_given_at is not None},
    )


# --------------------------------------------------------------------------- #
# Vendor webhook
# --------------------------------------------------------------------------- #


@csrf_exempt
def webhook(request):
    """Vendor status callback. HMAC-signed body or 400 — no exceptions."""
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    signature = request.META.get(gateway.SIGNATURE_HEADER, "")
    if not gateway.verify_webhook(request.body, signature):
        logger.warning("bgv: rejected webhook with a bad signature")
        return HttpResponseBadRequest("bad signature")
    try:
        payload = json.loads(request.body.decode() or "{}")
    except ValueError:
        return HttpResponseBadRequest("bad payload")
    ref = str(payload.get("provider_ref") or "").strip()
    order = VerificationOrder.objects.filter(provider_ref=ref).first() if ref else None
    if order is None:
        return JsonResponse({"ok": False, "detail": "unknown order"}, status=404)
    services.apply_result(
        order, {"state": payload.get("state") or "", "checks": payload.get("checks") or {}}
    )
    return HttpResponse('{"ok": true}', content_type="application/json")
