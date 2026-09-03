"""Talent-pool UI: search, profile detail, bulk import and bulk actions.

Talent is included on every paid plan, so nothing here is feature-gated; only
the AI extraction step inside ``talent.services`` consults billing.
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Membership
from core.permissions import for_company, role_required
from talent import services
from talent.forms import ImportForm, NoteForm, TalentProfileForm, TalentSearchForm
from talent.models import ImportBatch, TalentProfile

STAFF_ROLES = (Membership.OWNER, Membership.RECRUITER)
PAGE_SIZE = 25


def _company(request):
    company = getattr(request, "company", None)
    if company is None:
        raise PermissionDenied("No company selected for this user.")
    return company


def _get_profile(request, pk):
    return get_object_or_404(
        for_company(TalentProfile.objects.all(), _company(request)).prefetch_related("skills"),
        pk=pk,
    )


def _selected_profiles(request, company):
    ids = [int(v) for v in request.POST.getlist("selected") if str(v).isdigit()]
    if not ids:
        return TalentProfile.objects.none()
    return for_company(TalentProfile.objects.all(), company).filter(pk__in=ids)


# --- search ---------------------------------------------------------------


@role_required(*STAFF_ROLES)
def index(request):
    """Talent pool search + results table."""
    company = _company(request)
    form = TalentSearchForm(request.GET or None, company=company)
    form.is_valid()
    results = services.search_profiles(company, **form.criteria())
    paginator = Paginator(results, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    context = {
        "form": form,
        "page_obj": page,
        "profiles": page.object_list,
        "total": paginator.count,
        "jobs": services.company_jobs(company),
        "pool_size": for_company(TalentProfile.objects.all(), company).count(),
        "querystring": _querystring(request),
        "recent_batches": for_company(ImportBatch.objects.all(), company)[:5],
    }
    if request.headers.get("HX-Request") and request.GET.get("partial"):
        return render(request, "talent/partials/results.html", context)
    return render(request, "talent/index.html", context)


def _querystring(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


# --- profile --------------------------------------------------------------


@role_required(*STAFF_ROLES)
def profile_detail(request, pk):
    """Profile detail: resume, skills, applications timeline and notes."""
    profile = _get_profile(request, pk)
    note_form = NoteForm(instance=profile)
    if request.method == "POST":
        note_form = NoteForm(request.POST, instance=profile)
        if note_form.is_valid():
            note_form.save()
            messages.success(request, "Notes saved.")
            return redirect("talent:profile_detail", pk=profile.pk)
    return render(
        request,
        "talent/profile_detail.html",
        {
            "profile": profile,
            "note_form": note_form,
            "applications": profile.applications(),
            "jobs": services.company_jobs(_company(request)),
        },
    )


@role_required(*STAFF_ROLES)
def profile_create(request):
    """Manually add someone to the pool."""
    company = _company(request)
    form = TalentProfileForm(request.POST or None, request.FILES or None, company=company)
    if request.method == "POST" and form.is_valid():
        profile = form.save(commit=False)
        profile.company = company
        profile.source = TalentProfile.MANUAL
        profile.created_by = request.user
        profile.save()
        form.save_m2m()
        services.link_candidate(profile)
        messages.success(request, f"Added {profile.display_name} to the talent pool.")
        return redirect("talent:profile_detail", pk=profile.pk)
    return render(
        request,
        "talent/profile_form.html",
        {"form": form, "heading": "Add to talent pool", "profile": None},
    )


@role_required(*STAFF_ROLES)
def profile_edit(request, pk):
    """Edit a pool profile."""
    profile = _get_profile(request, pk)
    form = TalentProfileForm(
        request.POST or None, request.FILES or None, instance=profile, company=profile.company
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("talent:profile_detail", pk=profile.pk)
    return render(
        request,
        "talent/profile_form.html",
        {"form": form, "heading": f"Edit {profile.display_name}", "profile": profile},
    )


@role_required(*STAFF_ROLES)
def profile_resume(request, pk):
    """Stream a pool resume to staff of the owning company only."""
    profile = _get_profile(request, pk)
    if not profile.resume:
        raise Http404("This profile has no resume on file.")
    try:
        handle = profile.resume.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("The resume file is missing from storage.") from None
    return FileResponse(handle, filename=profile.resume.name.rsplit("/", 1)[-1])


@role_required(*STAFF_ROLES)
@require_POST
def profile_contacted(request, pk):
    """Stamp ``last_contacted`` (used by the quick actions)."""
    profile = _get_profile(request, pk)
    profile.last_contacted = timezone.now()
    profile.save(update_fields=["last_contacted", "updated_at"])
    messages.success(request, f"Marked {profile.display_name} as contacted.")
    return redirect(request.POST.get("next") or reverse("talent:profile_detail", args=[pk]))


# --- bulk actions ---------------------------------------------------------


@role_required(*STAFF_ROLES)
@require_POST
def bulk_action(request):
    """Add a tag, add to a job, or export the selection as CSV."""
    company = _company(request)
    action = request.POST.get("action") or ""
    profiles = list(_selected_profiles(request, company))
    back = request.POST.get("next") or reverse("talent:index")

    if not profiles:
        messages.error(request, "Select at least one profile first.")
        return redirect(back)

    if action == "tag":
        tag = (request.POST.get("tag") or "").strip()
        if not tag:
            messages.error(request, "Enter a tag to add.")
            return redirect(back)
        changed = services.add_tag(profiles, tag)
        messages.success(request, f"Tagged {changed} profile(s) with “{tag}”.")
        return redirect(back)

    if action == "add_to_job":
        job = services.company_jobs(company).filter(pk=request.POST.get("job") or 0).first()
        if job is None:
            messages.error(request, "Choose an open job.")
            return redirect(back)
        try:
            result = services.add_to_job(profiles, job, actor=request.user)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect(back)
        if result["added"]:
            messages.success(request, f"Added {result['added']} candidate(s) to {job.title}.")
        if result["existing"]:
            messages.info(request, f"{result['existing']} had already applied.")
        for error in result["errors"]:
            messages.warning(request, error)
        return redirect(back)

    if action == "export":
        return _csv_response(profiles)

    messages.error(request, "Unknown bulk action.")
    return redirect(back)


@role_required(*STAFF_ROLES)
def export(request):
    """Export the current search result set as CSV."""
    company = _company(request)
    form = TalentSearchForm(request.GET or None, company=company)
    form.is_valid()
    return _csv_response(services.search_profiles(company, **form.criteria()))


def _csv_response(profiles):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="talent-pool.csv"'
    services.export_csv(profiles, response)
    return response


# --- import ---------------------------------------------------------------


@role_required(*STAFF_ROLES)
def import_wizard(request):
    """Upload resumes / a zip / a CSV and process them synchronously."""
    company = _company(request)
    form = ImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        uploads = form.uploads(request)
        if not uploads:
            form.add_error("files", "Choose at least one file to import.")
        else:
            try:
                batch = services.run_import(company, uploads, uploaded_by=request.user)
            except ValidationError as exc:
                form.add_error("files", exc.messages)
            else:
                messages.success(
                    request,
                    f"Imported {batch.created} new and updated {batch.updated} profile(s).",
                )
                return redirect("talent:batch_report", pk=batch.pk)
    return render(
        request,
        "talent/import.html",
        {
            "form": form,
            "batches": for_company(ImportBatch.objects.all(), company)[:10],
            "max_files": services.MAX_FILES,
            "max_mb": services.MAX_ARCHIVE_BYTES // (1024 * 1024),
            "ai_enabled": services.ai_enabled(company),
        },
    )


def _get_batch(request, pk):
    return get_object_or_404(for_company(ImportBatch.objects.all(), _company(request)), pk=pk)


@role_required(*STAFF_ROLES)
def batch_report(request, pk):
    """Per-batch report: counts, progress and per-item errors."""
    batch = _get_batch(request, pk)
    return render(request, "talent/batch_report.html", {"batch": batch})


@role_required(*STAFF_ROLES)
def batch_status(request, pk):
    """HTMX progress fragment; stops polling once the batch is finished."""
    batch = _get_batch(request, pk)
    return render(request, "talent/partials/batch_status.html", {"batch": batch})
