"""Exchange UI: feed, requirements inbox, submissions outbox, partners, deals.

Views stay thin — every rule lives in ``exchange.services``. Two things are
worth knowing when reading templates:

* Cards render ``submission.snapshot_for(company)``, never
  ``candidate_snapshot`` — that is what keeps contact details out of the HTML
  before a reveal.
* Publishing is gated on the ``exchange`` feature; responding never is.
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import Membership
from core.permissions import role_required
from exchange import services
from exchange.forms import (
    DisputeForm,
    FeedFilterForm,
    HireForm,
    PartnerInviteForm,
    PublishRequirementForm,
    SubmitCandidateForm,
)
from exchange.models import ExchangeRequirement, ExchangeSubmission, PartnerLink

STAFF_ROLES = (Membership.OWNER, Membership.RECRUITER)
PAGE_SIZE = 20


def _company(request):
    company = getattr(request, "company", None)
    if company is None:
        raise PermissionDenied("No company selected for this user.")
    return company


def _paginate(request, queryset):
    return Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))


def _own_requirement(request, pk):
    return get_object_or_404(
        ExchangeRequirement.objects.for_company(_company(request)).select_related("job"), pk=pk
    )


def _own_submission(request, pk):
    """A submission against one of *our* requirements (requester side)."""
    return get_object_or_404(
        ExchangeSubmission.objects.select_related(
            "requirement", "requirement__company", "responding_company"
        ),
        pk=pk,
        requirement__company=_company(request),
    )


# --- feed -----------------------------------------------------------------


@role_required(*STAFF_ROLES)
def index(request):
    """The exchange feed: open requirements from partners and the network."""
    company = _company(request)
    form = FeedFilterForm(request.GET or None, company=company)
    form.is_valid()
    results = services.feed(company, **form.criteria())
    page = _paginate(request, results)
    submitted_ids = set(
        services.my_submissions(company).values_list("requirement_id", flat=True)
    )
    rows = [
        {
            "requirement": requirement,
            # Anonymised here, once, so no template can render the real client.
            "client_label": requirement.client_label_for(company),
            "submitted": requirement.pk in submitted_ids,
        }
        for requirement in page.object_list
    ]
    context = {
        "form": form,
        "page_obj": page,
        "rows": rows,
        "total": page.paginator.count,
        "submitted_ids": submitted_ids,
        "company": company,
        "can_publish": services.can_publish(company),
        "partner_count": len(PartnerLink.active_partner_ids(company)),
    }
    if request.headers.get("HX-Request") and request.GET.get("partial"):
        return render(request, "exchange/partials/feed_results.html", context)
    return render(request, "exchange/index.html", context)


# --- publishing -----------------------------------------------------------


@role_required(*STAFF_ROLES)
def publish(request):
    """Publish a job to the exchange (paid feature)."""
    company = _company(request)
    if not services.can_publish(company):
        return render(
            request,
            "exchange/publish_locked.html",
            {"company": company},
            status=403,
        )
    initial = {}
    job_id = request.GET.get("job")
    if job_id and str(job_id).isdigit():
        initial["job"] = job_id
    form = PublishRequirementForm(request.POST or None, company=company, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            requirement = services.publish_requirement(
                data["job"],
                created_by=request.user,
                title=data.get("title") or None,
                client_name=data.get("client_name") or None,
                location=data.get("location") or None,
                skills=list(data.get("skills") or []) or None,
                budget_ctc_min=data.get("budget_ctc_min"),
                budget_ctc_max=data.get("budget_ctc_max"),
                fee_split_pct=data["fee_split_pct"],
                visibility=data["visibility"],
                expires_in_days=data["expires_in_days"],
            )
        except services.ExchangeError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"“{requirement.title}” is live on the exchange.")
            return redirect("exchange:requirement_detail", pk=requirement.pk)
    return render(request, "exchange/publish.html", {"form": form, "company": company})


@role_required(*STAFF_ROLES)
def requirements(request):
    """My requirements, with submission counts."""
    company = _company(request)
    page = _paginate(request, services.my_requirements(company))
    return render(
        request,
        "exchange/requirements.html",
        {
            "page_obj": page,
            "requirements": page.object_list,
            "company": company,
            "can_publish": services.can_publish(company),
        },
    )


@role_required(*STAFF_ROLES)
def requirement_detail(request, pk):
    """One requirement plus its submissions inbox (masked until revealed)."""
    company = _company(request)
    requirement = _own_requirement(request, pk)
    submissions = services.submissions_for_requirement(requirement, company)
    cards = [
        {"submission": s, "snapshot": s.snapshot_for(company), "deal": getattr(s, "deal", None)}
        for s in submissions
    ]
    return render(
        request,
        "exchange/requirement_detail.html",
        {
            "requirement": requirement,
            "cards": cards,
            "company": company,
            "hire_form": HireForm(),
        },
    )


@role_required(*STAFF_ROLES)
@require_POST
def requirement_close(request, pk):
    company = _company(request)
    requirement = _own_requirement(request, pk)
    try:
        services.close_requirement(requirement, company)
    except services.ExchangeError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Requirement closed.")
    return redirect("exchange:requirements")


# --- responding -----------------------------------------------------------


@role_required(*STAFF_ROLES)
def submit(request, pk):
    """Offer a candidate from our talent pool against a partner requirement."""
    company = _company(request)
    requirement = get_object_or_404(
        ExchangeRequirement.objects.select_related("company", "job"), pk=pk
    )
    if not requirement.is_visible_to(company):
        raise PermissionDenied("That requirement is not open to your company.")
    form = SubmitCandidateForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        try:
            submission = services.submit_candidate(
                requirement,
                company,
                form.cleaned_data["talent_profile"],
                note=form.cleaned_data.get("note", ""),
                created_by=request.user,
            )
        except services.ExchangeError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"Submitted {submission.reference}. Contact details stay hidden "
                "until the partner accepts.",
            )
            return redirect("exchange:submissions")
    return render(
        request,
        "exchange/submit.html",
        {
            "form": form,
            "requirement": requirement,
            "client_label": requirement.client_label_for(company),
            "company": company,
        },
    )


@role_required(*STAFF_ROLES)
def submissions(request):
    """Outbox: what we have submitted and where it stands."""
    company = _company(request)
    page = _paginate(request, services.my_submissions(company))
    rows = [
        {"submission": s, "snapshot": s.snapshot_for(company), "deal": getattr(s, "deal", None)}
        for s in page.object_list
    ]
    return render(
        request,
        "exchange/submissions.html",
        {"page_obj": page, "rows": rows, "company": company},
    )


# --- requester actions ----------------------------------------------------


def _submission_action(request, pk, action, *args, **kwargs):
    company = _company(request)
    submission = _own_submission(request, pk)
    try:
        action(submission, company, *args, **kwargs)
    except services.ExchangeError as exc:
        messages.error(request, str(exc))
        return submission, False
    return submission, True


@role_required(*STAFF_ROLES)
@require_POST
def submission_shortlist(request, pk):
    submission, ok = _submission_action(request, pk, services.shortlist)
    if ok:
        messages.success(request, f"{submission.reference} shortlisted.")
    return redirect("exchange:requirement_detail", pk=submission.requirement_id)


@role_required(*STAFF_ROLES)
@require_POST
def submission_reject(request, pk):
    reason = request.POST.get("reason", "")
    submission, ok = _submission_action(request, pk, services.reject, reason)
    if ok:
        messages.success(request, f"{submission.reference} rejected.")
    return redirect("exchange:requirement_detail", pk=submission.requirement_id)


@role_required(*STAFF_ROLES)
@require_POST
def submission_reveal(request, pk):
    submission, ok = _submission_action(request, pk, services.reveal)
    if ok:
        messages.success(request, "Contact details revealed to your team.")
    return redirect("exchange:requirement_detail", pk=submission.requirement_id)


@role_required(Membership.OWNER)
@require_POST
def submission_hire(request, pk):
    company = _company(request)
    submission = _own_submission(request, pk)
    form = HireForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter the placement fee that was agreed.")
        return redirect("exchange:requirement_detail", pk=submission.requirement_id)
    try:
        deal = services.mark_hired(
            submission, form.cleaned_data["placement_fee_inr"], company=company
        )
    except services.ExchangeError as exc:
        messages.error(request, str(exc))
        return redirect("exchange:requirement_detail", pk=submission.requirement_id)
    messages.success(
        request,
        f"Placement recorded. Your share is ₹{deal.requester_share}, "
        f"the partner's ₹{deal.responder_share}.",
    )
    return redirect("exchange:deals")


# --- partners -------------------------------------------------------------


@role_required(*STAFF_ROLES)
def partners(request):
    """Partner list plus the invite form."""
    company = _company(request)
    form = PartnerInviteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.invite_partner(company, form.cleaned_data["target"], created_by=request.user)
        except services.ExchangeError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Partner request sent.")
            return redirect("exchange:partners")
    links = list(services.partners(company))
    rows = [
        {
            "link": link,
            "other": link.other_company(company),
            "incoming": link.is_incoming_for(company),
        }
        for link in links
    ]
    return render(
        request,
        "exchange/partners.html",
        {"form": form, "rows": rows, "company": company},
    )


def _partner_action(request, pk, action):
    company = _company(request)
    link = get_object_or_404(PartnerLink.involving(company), pk=pk)
    try:
        action(link, company)
    except services.ExchangeError as exc:
        messages.error(request, str(exc))
    return redirect("exchange:partners")


@role_required(*STAFF_ROLES)
@require_POST
def partner_accept(request, pk):
    return _partner_action(request, pk, services.accept_partner)


@role_required(*STAFF_ROLES)
@require_POST
def partner_block(request, pk):
    return _partner_action(request, pk, services.block_partner)


@role_required(*STAFF_ROLES)
@require_POST
def partner_unblock(request, pk):
    return _partner_action(request, pk, services.unblock_partner)


# --- deals ----------------------------------------------------------------


@role_required(*STAFF_ROLES)
def deals(request):
    """Ledger of placements, with each side's share."""
    company = _company(request)
    page = _paginate(request, services.deals_for(company))
    rows = [
        {
            "deal": deal,
            "is_requester": deal.requester_company.pk == company.pk,
            "counterparty": (
                deal.responder_company
                if deal.requester_company.pk == company.pk
                else deal.requester_company
            ),
            "share": deal.share_for(company),
            "platform_fee": deal.platform_fee_for(company),
        }
        for deal in page.object_list
    ]
    return render(
        request,
        "exchange/deals.html",
        {"page_obj": page, "rows": rows, "company": company, "dispute_form": DisputeForm()},
    )


@role_required(*STAFF_ROLES)
@require_POST
def deal_dispute(request, pk):
    company = _company(request)
    deal = get_object_or_404(services.deals_for(company), pk=pk)
    form = DisputeForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Describe the problem so we can look into it.")
        return redirect("exchange:deals")
    try:
        services.flag_dispute(deal, company, form.cleaned_data["reason"])
    except services.ExchangeError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Dispute raised — we will be in touch.")
    return redirect("exchange:deals")
