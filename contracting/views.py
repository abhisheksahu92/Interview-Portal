"""Contracting views: recruiter workspace, contractor token pages, portal actions.

Three audiences, three access rules:

* **Recruiters** — ``login_required`` + OWNER/RECRUITER role + the
  ``contracting`` entitlement, composed once in :func:`_recruiter_view`.
* **Contractors** — no login at all; the ``Contractor`` token in the URL is the
  credential, resolved through :mod:`core.tokens` exactly like a client-portal
  link. Bad tokens get 410/404 from ``TokenState.default_status``.
* **Clients** — the timesheet approval controls live inside the existing client
  portal and reuse its ``ClientAccess`` token via ``clients.views.portal_guard``.
"""

import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from billing.entitlements import require_feature
from clients.models import Client
from clients.views import portal_guard
from contracting import invoicing, metrics, payroll, rates, services
from contracting.forms import (
    ClientBillingProfileForm,
    ContractorForm,
    EngagementForm,
    OnboardingDocumentForm,
    PeriodForm,
    TimesheetGridForm,
)
from contracting.models import (
    ClientBillingProfile,
    ClientInvoice,
    Contractor,
    Engagement,
    OnboardingDocument,
    PayrollRun,
    Timesheet,
)
from core.models import Membership
from core.permissions import role_required
from core.tokens import resolve_token, token_invalid_response

logger = logging.getLogger(__name__)

RECRUITER_ROLES = (Membership.OWNER, Membership.RECRUITER)
FEATURE = "contracting"


def _recruiter_view(view_func):
    """login + tenant role + feature gate, in that order."""
    return login_required(role_required(*RECRUITER_ROLES)(require_feature(FEATURE)(view_func)))


def _contractor(request, pk):
    return get_object_or_404(Contractor.objects.for_company(request.company), pk=pk)


def _engagement(request, pk):
    return get_object_or_404(
        Engagement.objects.select_related("contractor", "client"),
        pk=pk,
        contractor__company=request.company,
    )


def _timesheet(request, pk):
    return get_object_or_404(
        Timesheet.objects.select_related("engagement__contractor", "engagement__client"),
        pk=pk,
        engagement__contractor__company=request.company,
    )


def _invoice(request, pk):
    return get_object_or_404(
        ClientInvoice.objects.for_company(request.company).select_related("client"), pk=pk
    )


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #


@_recruiter_view
def index(request):
    """Margin dashboard: bill − pay per engagement, DSO and receivables."""
    invoicing.refresh_overdue(request.company)
    context = metrics.summary(request.company)
    context["pending"] = (
        Timesheet.objects.for_company(request.company)
        .awaiting_approval()
        .select_related("engagement__contractor", "engagement__client")[:8]
    )
    return render(request, "contracting/dashboard.html", context)


# --------------------------------------------------------------------------- #
# Contractors
# --------------------------------------------------------------------------- #


@_recruiter_view
def contractor_list(request):
    status = request.GET.get("status") or ""
    contractors = Contractor.objects.for_company(request.company).prefetch_related(
        "documents", "engagements__client"
    )
    if status:
        contractors = contractors.filter(status=status)
    rows = [
        {"contractor": c, "progress": services.onboarding_progress(c)} for c in contractors
    ]
    return render(
        request,
        "contracting/contractor_list.html",
        {
            "rows": rows,
            "status": status,
            "status_choices": Contractor.STATUS_CHOICES,
        },
    )


@_recruiter_view
def contractor_create(request):
    form = ContractorForm(request.POST or None, company=request.company)
    if request.method == "POST" and form.is_valid():
        contractor = form.save()
        messages.success(request, f"Contractor “{contractor.name}” added.")
        return redirect("contracting:contractor_detail", pk=contractor.pk)
    return render(
        request, "contracting/contractor_form.html", {"form": form, "mode": "create"}
    )


@_recruiter_view
def contractor_edit(request, pk):
    contractor = _contractor(request, pk)
    form = ContractorForm(
        request.POST or None, instance=contractor, company=request.company
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Contractor updated.")
        return redirect("contracting:contractor_detail", pk=contractor.pk)
    return render(
        request,
        "contracting/contractor_form.html",
        {"form": form, "mode": "edit", "contractor": contractor},
    )


@_recruiter_view
def contractor_detail(request, pk):
    contractor = _contractor(request, pk)
    return render(
        request,
        "contracting/contractor_detail.html",
        {
            "contractor": contractor,
            "checklist": services.onboarding_checklist(contractor),
            "progress": services.onboarding_progress(contractor),
            "document_form": OnboardingDocumentForm(),
            "engagements": contractor.engagements.select_related("client"),
            "timesheets": Timesheet.objects.filter(
                engagement__contractor=contractor
            ).select_related("engagement__client")[:10],
            "timesheet_url": request.build_absolute_uri(contractor_link(contractor)),
        },
    )


def contractor_link(contractor):
    from django.urls import reverse

    return reverse("contracting:contractor_portal", args=[contractor.token])


@require_POST
@_recruiter_view
def document_upload(request, pk):
    contractor = _contractor(request, pk)
    form = OnboardingDocumentForm(request.POST, request.FILES)
    if form.is_valid():
        services.add_document(
            contractor,
            form.cleaned_data["kind"],
            form.cleaned_data["file"],
            uploaded_by=request.user,
            note=form.cleaned_data.get("note", ""),
        )
        messages.success(request, "Document uploaded.")
    else:
        messages.error(request, form.errors.as_text())
    return redirect("contracting:contractor_detail", pk=contractor.pk)


@require_POST
@_recruiter_view
def document_verify(request, pk, document_id):
    contractor = _contractor(request, pk)
    document = get_object_or_404(
        OnboardingDocument, pk=document_id, contractor=contractor
    )
    document.mark_verified()
    services.activate_if_ready(contractor)
    messages.success(request, f"{document.get_kind_display()} marked verified.")
    return redirect("contracting:contractor_detail", pk=contractor.pk)


@require_POST
@_recruiter_view
def contractor_rotate_link(request, pk):
    """Issue a fresh timesheet link; the old URL stops working immediately."""
    contractor = _contractor(request, pk)
    contractor.rotate()
    messages.success(request, "A new timesheet link was generated.")
    return redirect("contracting:contractor_detail", pk=contractor.pk)


# --------------------------------------------------------------------------- #
# Engagements
# --------------------------------------------------------------------------- #


@_recruiter_view
def engagement_list(request):
    engagements = Engagement.objects.filter(
        contractor__company=request.company
    ).select_related("contractor", "client")
    return render(
        request, "contracting/engagement_list.html", {"engagements": engagements}
    )


@_recruiter_view
def engagement_create(request, contractor_id):
    contractor = _contractor(request, contractor_id)
    form = EngagementForm(
        request.POST or None, company=request.company, contractor=contractor
    )
    if request.method == "POST" and form.is_valid():
        engagement = services.create_engagement(
            contractor,
            form.cleaned_data["client"],
            role_title=form.cleaned_data["role_title"],
            start=form.cleaned_data["start"],
            end=form.cleaned_data.get("end"),
            job=form.cleaned_data.get("job"),
            bill_rate_inr=form.cleaned_data["bill_rate_inr"],
            pay_rate_inr=form.cleaned_data["pay_rate_inr"],
            rate_unit=form.cleaned_data["rate_unit"],
            po_number=form.cleaned_data.get("po_number", ""),
            tds_percent=form.cleaned_data.get("tds_percent"),
            status=form.cleaned_data["status"],
        )
        messages.success(request, f"Engagement with {engagement.client.name} created.")
        return redirect("contracting:contractor_detail", pk=contractor.pk)
    return render(
        request,
        "contracting/engagement_form.html",
        {"form": form, "contractor": contractor, "mode": "create"},
    )


@_recruiter_view
def engagement_edit(request, pk):
    engagement = _engagement(request, pk)
    form = EngagementForm(
        request.POST or None,
        instance=engagement,
        company=request.company,
        contractor=engagement.contractor,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Engagement updated.")
        return redirect("contracting:contractor_detail", pk=engagement.contractor_id)
    return render(
        request,
        "contracting/engagement_form.html",
        {"form": form, "contractor": engagement.contractor, "engagement": engagement, "mode": "edit"},
    )


# --------------------------------------------------------------------------- #
# Timesheets (recruiter queue)
# --------------------------------------------------------------------------- #


@_recruiter_view
def timesheet_queue(request):
    # "All statuses" posts an empty ``status``; only a *missing* parameter means
    # "show me the default queue", so a present-but-empty value lists everything.
    status = request.GET.get("status", Timesheet.SUBMITTED)
    timesheets = Timesheet.objects.for_company(request.company).select_related(
        "engagement__contractor", "engagement__client"
    )
    if status:
        timesheets = timesheets.filter(status=status)
    rows = [
        {"timesheet": ts, "totals": services.timesheet_totals(ts)} for ts in timesheets[:200]
    ]
    return render(
        request,
        "contracting/timesheet_queue.html",
        {"rows": rows, "status": status, "status_choices": Timesheet.STATUS_CHOICES},
    )


@require_POST
@_recruiter_view
def timesheet_decide(request, pk, decision):
    timesheet = _timesheet(request, pk)
    note = request.POST.get("note", "")
    action = services.approve if decision == "approve" else services.reject
    try:
        action(timesheet, user=request.user, note=note)
    except services.InvalidTransition as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Timesheet {timesheet.get_status_display().lower()}.")
    return redirect("contracting:timesheet_queue")


# --------------------------------------------------------------------------- #
# Client invoices
# --------------------------------------------------------------------------- #


@_recruiter_view
def invoice_list(request):
    invoicing.refresh_overdue(request.company)
    invoices = ClientInvoice.objects.for_company(request.company).select_related("client")
    return render(
        request,
        "contracting/invoice_list.html",
        {
            "invoices": invoices,
            "form": PeriodForm(),
            "receivables": metrics.receivables(request.company),
            "dso": metrics.dso(request.company),
        },
    )


@_recruiter_view
def invoice_detail(request, pk):
    invoice = _invoice(request, pk)
    return render(
        request,
        "contracting/invoice_detail.html",
        {"invoice": invoice, "profile": ClientBillingProfile.for_client(invoice.client)},
    )


@require_POST
@_recruiter_view
def invoice_generate(request):
    form = PeriodForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Pick a month to invoice.")
        return redirect("contracting:invoice_list")
    invoices = invoicing.generate_client_invoices(request.company, form.cleaned_data["month"])
    if invoices:
        messages.success(
            request, f"{len(invoices)} invoice(s) raised from approved timesheets."
        )
    else:
        messages.info(request, "No approved timesheets were waiting to be invoiced.")
    return redirect("contracting:invoice_list")


@require_POST
@_recruiter_view
def invoice_send(request, pk):
    invoice = _invoice(request, pk)
    invoicing.send_invoice(invoice, request=request)
    messages.success(request, f"Invoice {invoice.number} sent.")
    return redirect("contracting:invoice_detail", pk=invoice.pk)


@require_POST
@_recruiter_view
def invoice_mark_paid(request, pk):
    invoice = _invoice(request, pk)
    invoicing.mark_paid(invoice)
    messages.success(request, f"Invoice {invoice.number} marked paid.")
    return redirect("contracting:invoice_detail", pk=invoice.pk)


@_recruiter_view
def invoice_pdf(request, pk):
    """Stream the invoice PDF, rendering it on the fly when not stored."""
    invoice = _invoice(request, pk)
    if invoice.pdf:
        try:
            return FileResponse(
                invoice.pdf.open("rb"),
                as_attachment=True,
                filename=invoicing.pdf_filename(invoice),
                content_type="application/pdf",
            )
        except (FileNotFoundError, OSError):
            logger.warning("contracting: stored PDF missing for %s", invoice.number)
    content = invoicing.pdf_bytes(invoice)
    if content is None:
        raise Http404("PDF rendering is unavailable on this install.")
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{invoicing.pdf_filename(invoice)}"'
    return response


@_recruiter_view
def billing_profile(request, client_id):
    """Edit the GST/billing details this app keeps for a client."""
    client = get_object_or_404(Client.objects.for_company(request.company), pk=client_id)
    profile = ClientBillingProfile.for_client(client)
    form = ClientBillingProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.client = client
        saved.save()
        messages.success(request, "Billing details saved.")
        return redirect("contracting:invoice_list")
    return render(
        request,
        "contracting/billing_profile_form.html",
        {"form": form, "client": client},
    )


# --------------------------------------------------------------------------- #
# Payroll
# --------------------------------------------------------------------------- #


@_recruiter_view
def payroll_list(request):
    return render(
        request,
        "contracting/payroll_list.html",
        {
            "runs": PayrollRun.objects.for_company(request.company),
            "form": PeriodForm(),
        },
    )


@_recruiter_view
def payroll_detail(request, pk):
    run = get_object_or_404(PayrollRun.objects.for_company(request.company), pk=pk)
    return render(request, "contracting/payroll_detail.html", {"run": run})


@require_POST
@_recruiter_view
def payroll_run(request):
    form = PeriodForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Pick a payroll month.")
        return redirect("contracting:payroll_list")
    run = payroll.run_payroll(
        request.company, form.cleaned_data["month"], created_by=request.user
    )
    messages.success(request, f"Payroll for {run.label} computed for {run.headcount} contractor(s).")
    return redirect("contracting:payroll_detail", pk=run.pk)


@_recruiter_view
def payroll_download(request, pk):
    """The HRMS-importable CSV for one run."""
    run = get_object_or_404(PayrollRun.objects.for_company(request.company), pk=pk)
    content = payroll.csv_bytes(run.rows or [])
    response = HttpResponse(content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{payroll.csv_filename(run)}"'
    return response


# --------------------------------------------------------------------------- #
# Contractor self-service (token, no login)
# --------------------------------------------------------------------------- #


def contractor_token_guard(view_func):
    """Resolve the URL token to a live Contractor or render the shared error page."""

    from functools import wraps

    @wraps(view_func)
    def _wrapped(request, token, *args, **kwargs):
        resolution = resolve_token(Contractor, token, select_related=("company",))
        if not resolution.ok:
            return token_invalid_response(
                request,
                resolution,
                context={
                    "page_title": "Timesheet link no longer valid",
                    "contact_hint": (
                        "Ask your recruitment contact to send you a fresh timesheet link."
                    ),
                },
            )
        return view_func(request, resolution.obj, *args, **kwargs)

    return _wrapped


@contractor_token_guard
def contractor_portal(request, contractor):
    """A contractor's own timesheets across every engagement they hold."""
    contractor.touch()
    engagements = contractor.engagements.filter(
        status=Engagement.ACTIVE
    ).select_related("client")
    week_start, week_end = services.week_bounds()
    cards = []
    for engagement in engagements:
        current = services.get_or_create_timesheet(engagement, week_start, week_end)
        cards.append(
            {
                "engagement": engagement,
                "current": current,
                "recent": engagement.timesheets.exclude(pk=current.pk)[:5],
            }
        )
    return render(
        request,
        "contracting/portal/contractor_home.html",
        {
            "contractor": contractor,
            "cards": cards,
            "week_start": week_start,
            "week_end": week_end,
        },
    )


def _grid_days(timesheet):
    """``[{date, iso, hours, note}]`` for every day of the timesheet period."""
    logged = {e["date"]: e for e in (timesheet.entries or [])}
    days = []
    day = timesheet.period_start
    while day <= timesheet.period_end:
        entry = logged.get(day.isoformat(), {})
        days.append(
            {
                "date": day,
                "iso": day.isoformat(),
                "hours": entry.get("hours", ""),
                "note": entry.get("note", ""),
                "is_weekend": day.weekday() >= 5,
            }
        )
        day += timedelta(days=1)
    return days


@contractor_token_guard
def contractor_timesheet(request, contractor, pk):
    """The weekly grid: save a draft, or submit it for client approval."""
    timesheet = get_object_or_404(
        Timesheet.objects.select_related("engagement__client"),
        pk=pk,
        engagement__contractor=contractor,
    )
    if request.method == "POST":
        form = TimesheetGridForm(request.POST, timesheet=timesheet)
        if not timesheet.is_editable:
            messages.error(request, "This timesheet can no longer be edited.")
        elif form.is_valid():
            action = request.POST.get("action", "save")
            try:
                if action == "submit":
                    services.submit(timesheet, form.entries)
                    messages.success(request, "Timesheet submitted for approval.")
                else:
                    services.save_draft(timesheet, form.entries)
                    messages.success(request, "Draft saved.")
            except services.InvalidTransition as exc:
                messages.error(request, str(exc))
            return redirect("contracting:contractor_timesheet", token=contractor.token, pk=timesheet.pk)
        else:
            messages.error(request, form.errors.as_text())
    return render(
        request,
        "contracting/portal/timesheet_form.html",
        {
            "contractor": contractor,
            "timesheet": timesheet,
            "days": _grid_days(timesheet),
            "engagement": timesheet.engagement,
            "quantity": rates.quantity(timesheet),
            "unit_label": rates.unit_label(timesheet.engagement.rate_unit),
        },
    )


# --------------------------------------------------------------------------- #
# Client portal (inside clients/, authenticated by the ClientAccess token)
# --------------------------------------------------------------------------- #


def portal_timesheets_context(access):
    """Timesheets this client link may see — pending first, then recent history."""
    base = (
        Timesheet.objects.for_client(access.client)
        .select_related("engagement__contractor", "engagement__client")
    )
    return {
        "access": access,
        "pending": base.awaiting_approval(),
        "recent": base.exclude(status=Timesheet.SUBMITTED)[:10],
    }


@require_POST
@portal_guard
def portal_timesheet_decide(request, access, pk, decision):
    """Approve or reject one timesheet from inside the client portal (HTMX)."""
    timesheet = get_object_or_404(
        Timesheet.objects.select_related("engagement__contractor"),
        pk=pk,
        engagement__client=access.client,
    )
    access.touch()
    note = request.POST.get("note", "")
    action = services.approve if decision == "approve" else services.reject
    try:
        action(timesheet, access=access, note=note)
    except services.InvalidTransition as exc:
        logger.info("contracting: portal transition refused: %s", exc)
    context = portal_timesheets_context(access)
    context["decided"] = timesheet
    return render(request, "contracting/partials/portal_timesheets.html", context)
