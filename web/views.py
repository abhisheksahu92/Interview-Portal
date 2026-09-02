"""Web UI views: landing, recruiter dashboard, interviewer queue, candidate portal."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Membership
from core.permissions import for_company, role_required
from jobs.models import (
    Application,
    CandidateProfile,
    Job,
    PipelineStage,
    Skill,
    StageReview,
)
from web.forms import (
    ApplyForm,
    CandidateProfileForm,
    InviteForm,
    JobForm,
    ReviewForm,
    SkillForm,
    StageForm,
)

STAFF_ROLES = (Membership.OWNER, Membership.RECRUITER)


# --- helpers --------------------------------------------------------------


def _jobs_services():
    """Return ``jobs.services`` if the jobs agent shipped it, else ``None``."""
    try:
        from jobs import services  # type: ignore

        return services
    except ImportError:
        return None


def advance_application(application, user=None):
    """Advance via jobs.services when available, else the model method."""
    services = _jobs_services()
    func = getattr(services, "advance_application", None) if services else None
    if callable(func):
        try:
            return func(application, user=user)
        except TypeError:
            return func(application)
    return application.advance()


def reject_application(application, user=None):
    services = _jobs_services()
    func = getattr(services, "reject_application", None) if services else None
    if callable(func):
        try:
            return func(application, user=user)
        except TypeError:
            return func(application)
    return application.reject()


def record_review(application, stage, reviewer, decision, rating=None, feedback=""):
    """Record a StageReview.

    ``jobs.services.record_review`` also applies the automatic pipeline
    transition (PASS advances, FAIL rejects), so the second element of the
    returned tuple says whether the caller still needs to move the application.
    """
    services = _jobs_services()
    func = getattr(services, "record_review", None) if services else None
    if callable(func):
        review = func(
            application,
            stage=stage,
            reviewer=reviewer,
            decision=decision,
            rating=rating,
            feedback=feedback,
        )
        return review, True
    review, _ = StageReview.objects.update_or_create(
        application=application,
        stage=stage,
        reviewer=reviewer,
        defaults={"decision": decision, "rating": rating, "feedback": feedback},
    )
    return review, False


def assessment_url_for(application):
    """URL of the assessment the candidate should take at their current stage.

    Returns ``None`` when the stage needs no assessment or none is configured.
    """
    stage = application.current_stage
    if stage is None or not stage.requires_assessment:
        return None
    from assessments.models import Assessment

    assessment = (
        Assessment.objects.filter(job=application.job, is_active=True)
        .filter(Q(stage=stage) | Q(stage__isnull=True))
        .order_by("-stage_id")
        .first()
    )
    if assessment is None:
        return None
    return reverse(
        "assessments:take_assessment",
        kwargs={"application_id": application.pk, "assessment_id": assessment.pk},
    )


def _company_jobs(request):
    return for_company(Job.objects.all(), getattr(request, "company", None))


def _company_applications(request):
    company = getattr(request, "company", None)
    if company is None:
        return Application.objects.none()
    return Application.objects.filter(job__company=company)


def _require_member(request):
    company = getattr(request, "company", None)
    if company is None or request.user.role_in(company) is None:
        raise PermissionDenied("Company membership required.")
    return company


# --- landing --------------------------------------------------------------


def home(request):
    """Marketing landing page for anonymous visitors; role redirect otherwise."""
    if request.user.is_authenticated:
        if getattr(request, "company", None) is not None:
            role = request.user.role_in(request.company)
            if role == Membership.INTERVIEWER:
                return redirect("web:interviewer_queue")
            return redirect("web:dashboard")
        if request.user.is_candidate:
            return redirect("web:candidate_home")
        return redirect("core:account_home")
    return render(request, "web/landing.html")


# --- recruiter / owner ----------------------------------------------------


@login_required
@role_required(*STAFF_ROLES)
def dashboard(request):
    company = request.company
    jobs = _company_jobs(request).annotate(
        application_count=Count("applications", distinct=True)
    )
    applications = _company_applications(request)
    now = timezone.now()
    kpis = {
        "open_jobs": jobs.filter(status=Job.OPEN).count(),
        "active_applications": applications.filter(status=Application.ACTIVE).count(),
        "hires_this_month": applications.filter(
            status=Application.HIRED,
            updated_at__year=now.year,
            updated_at__month=now.month,
        ).count(),
        "avg_fit_score": applications.aggregate(v=Avg("ai_fit_score"))["v"],
    }
    return render(
        request,
        "web/dashboard.html",
        {"company": company, "jobs": jobs, "kpis": kpis},
    )


@login_required
@role_required(*STAFF_ROLES)
def job_create(request):
    form = JobForm(request.POST or None, company=request.company)
    if request.method == "POST" and form.is_valid():
        job = form.save(commit=False)
        job.created_by = request.user
        job.company = request.company
        job.save()
        form.save_m2m()
        messages.success(request, f"Job “{job.title}” created with a default pipeline.")
        return redirect("web:job_detail", pk=job.pk)
    return render(request, "web/job_form.html", {"form": form, "job": None})


@login_required
@role_required(*STAFF_ROLES)
def job_edit(request, pk):
    job = get_object_or_404(_company_jobs(request), pk=pk)
    form = JobForm(request.POST or None, instance=job, company=request.company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Job updated.")
        return redirect("web:job_detail", pk=job.pk)
    return render(request, "web/job_form.html", {"form": form, "job": job})


def _kanban_context(request, job):
    stages = list(job.stages.all())
    applications = (
        Application.objects.filter(job=job)
        .select_related("candidate__user", "current_stage")
        .prefetch_related("reviews__reviewer")
    )
    by_stage = {stage.pk: [] for stage in stages}
    unassigned, closed = [], []
    for application in applications:
        application.latest_review = application.reviews.all().first()
        if application.status != Application.ACTIVE:
            closed.append(application)
        elif application.current_stage_id in by_stage:
            by_stage[application.current_stage_id].append(application)
        else:
            unassigned.append(application)
    columns = [{"stage": s, "applications": by_stage[s.pk]} for s in stages]
    return {
        "job": job,
        "columns": columns,
        "unassigned": unassigned,
        "closed": closed,
    }


@login_required
@role_required(*STAFF_ROLES)
def job_detail(request, pk):
    job = get_object_or_404(_company_jobs(request), pk=pk)
    context = _kanban_context(request, job)
    context["stage_form"] = StageForm()
    return render(request, "web/job_detail.html", context)


@login_required
@role_required(*STAFF_ROLES)
def job_kanban(request, pk):
    """HTMX partial: just the board (used to refresh after an action)."""
    job = get_object_or_404(_company_jobs(request), pk=pk)
    return render(request, "web/partials/kanban.html", _kanban_context(request, job))


def _application_card_response(request, application):
    application.latest_review = application.reviews.all().first()
    return render(
        request,
        "web/partials/application_card.html",
        {"application": application, "job": application.job},
    )


@login_required
@role_required(*STAFF_ROLES)
@require_POST
def application_advance(request, pk):
    application = get_object_or_404(_company_applications(request), pk=pk)
    advance_application(application, user=request.user)
    if request.headers.get("HX-Request"):
        return render(
            request, "web/partials/kanban.html", _kanban_context(request, application.job)
        )
    messages.success(request, "Application advanced.")
    return redirect("web:job_detail", pk=application.job_id)


@login_required
@role_required(*STAFF_ROLES)
@require_POST
def application_reject(request, pk):
    application = get_object_or_404(_company_applications(request), pk=pk)
    reject_application(application, user=request.user)
    if request.headers.get("HX-Request"):
        return render(
            request, "web/partials/kanban.html", _kanban_context(request, application.job)
        )
    messages.success(request, "Application rejected.")
    return redirect("web:job_detail", pk=application.job_id)


@login_required
def application_review(request, pk):
    """Inline review form. Any company member may review."""
    company = _require_member(request)
    application = get_object_or_404(
        Application.objects.filter(job__company=company).select_related(
            "candidate__user", "current_stage", "job"
        ),
        pk=pk,
    )
    form = ReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        stage = application.current_stage or application.job.first_stage
        if stage is None:
            messages.error(request, "This job has no pipeline stages yet.")
            return redirect("web:job_detail", pk=application.job_id)
        decision = form.cleaned_data["decision"]
        _review, transitioned = record_review(
            application,
            stage=stage,
            reviewer=request.user,
            decision=decision,
            rating=form.cleaned_data.get("rating") or None,
            feedback=form.cleaned_data.get("feedback", ""),
        )
        if not transitioned:
            if decision == StageReview.FAIL:
                reject_application(application, user=request.user)
            elif decision == StageReview.PASS:
                advance_application(application, user=request.user)
        application.refresh_from_db()
        if request.headers.get("HX-Request"):
            return _application_card_response(request, application)
        messages.success(request, "Review saved.")
        return redirect("web:job_detail", pk=application.job_id)
    return render(
        request,
        "web/partials/review_form.html",
        {"form": form, "application": application},
    )


# --- interviewer ----------------------------------------------------------


@login_required
def interviewer_queue(request):
    company = _require_member(request)
    applications = (
        Application.objects.filter(
            job__company=company,
            status=Application.ACTIVE,
            current_stage__kind__in=[PipelineStage.INTERVIEW, PipelineStage.HR],
        )
        .select_related("candidate__user", "current_stage", "job")
        .prefetch_related("reviews__reviewer")
    )
    rows = []
    for application in applications:
        rows.append(
            {
                "application": application,
                "my_review": application.reviews.filter(
                    reviewer=request.user, stage=application.current_stage
                ).first(),
                "form": ReviewForm(),
            }
        )
    return render(
        request,
        "web/interviewer_queue.html",
        {"rows": rows, "company": company},
    )


# --- company settings -----------------------------------------------------


@login_required
@role_required(*STAFF_ROLES)
def settings_members(request):
    company = request.company
    form = InviteForm(request.POST or None, company=company)
    if request.method == "POST":
        if request.user.role_in(company) != Membership.OWNER:
            raise PermissionDenied("Only owners can manage members.")
        if form.is_valid():
            membership = form.save()
            if form.created_user:
                messages.warning(
                    request,
                    f"{membership.user.email} had no account, so an inactive "
                    "placeholder was created. They must be activated (or sign up) "
                    "before they can log in.",
                )
            else:
                messages.success(request, f"{membership.user.email} added.")
            return redirect("web:settings_members")
    memberships = (
        Membership.objects.filter(company=company)
        .select_related("user")
        .order_by("role", "user__email")
    )
    return render(
        request,
        "web/settings_members.html",
        {"form": form, "memberships": memberships, "company": company},
    )


@login_required
@role_required(Membership.OWNER)
@require_POST
def member_remove(request, pk):
    membership = get_object_or_404(
        Membership.objects.filter(company=request.company), pk=pk
    )
    if membership.user_id == request.user.pk:
        messages.error(request, "You cannot remove yourself.")
    else:
        email = membership.user.email
        membership.delete()
        messages.success(request, f"{email} removed from {request.company.name}.")
    return redirect("web:settings_members")


@login_required
@role_required(*STAFF_ROLES)
def settings_skills(request):
    company = request.company
    form = SkillForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        if Skill.objects.filter(company=company, name__iexact=form.cleaned_data["name"]).exists():
            messages.info(request, "That skill already exists.")
        else:
            form.save()
            messages.success(request, "Skill added.")
        return redirect("web:settings_skills")
    return render(
        request,
        "web/settings_skills.html",
        {
            "form": form,
            "skills": for_company(Skill.objects.all(), company).annotate(
                job_count=Count("jobs", distinct=True)
            ),
            "company": company,
        },
    )


@login_required
@role_required(*STAFF_ROLES)
@require_POST
def skill_delete(request, pk):
    skill = get_object_or_404(for_company(Skill.objects.all(), request.company), pk=pk)
    skill.delete()
    messages.success(request, "Skill removed.")
    return redirect("web:settings_skills")


@login_required
@role_required(*STAFF_ROLES)
def settings_stages(request, pk):
    """Edit the pipeline stage template for one job."""
    job = get_object_or_404(_company_jobs(request), pk=pk)
    form = StageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        stage = form.save(commit=False)
        stage.job = job
        if job.stages.filter(order=stage.order).exists():
            messages.error(request, "Another stage already uses that order number.")
        else:
            stage.save()
            messages.success(request, "Stage added.")
        return redirect("web:settings_stages", pk=job.pk)
    return render(
        request,
        "web/settings_stages.html",
        {"job": job, "form": form, "stages": job.stages.all()},
    )


@login_required
@role_required(*STAFF_ROLES)
@require_POST
def stage_delete(request, pk):
    stage = get_object_or_404(
        PipelineStage.objects.filter(job__company=request.company), pk=pk
    )
    job_id = stage.job_id
    stage.delete()
    messages.success(request, "Stage removed.")
    return redirect("web:settings_stages", pk=job_id)


# --- candidate portal -----------------------------------------------------


def _candidate_profile(request):
    if not request.user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    if getattr(request, "company", None) is not None:
        raise PermissionDenied("Company members use the recruiter workspace.")
    profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
    return profile


@login_required
def candidate_home(request):
    profile = _candidate_profile(request)
    applications = (
        profile.applications.select_related("job__company", "current_stage")
        .prefetch_related("job__stages")
        .all()
    )
    rows = []
    for application in applications:
        stages = list(application.job.stages.all())
        current_order = (
            application.current_stage.order if application.current_stage else 0
        )
        rows.append(
            {
                "application": application,
                "stages": stages,
                "current_order": current_order,
                "assessment_url": assessment_url_for(application),
            }
        )
    return render(
        request,
        "web/candidate_home.html",
        {"profile": profile, "rows": rows},
    )


@login_required
def candidate_profile(request):
    profile = _candidate_profile(request)
    form = CandidateProfileForm(
        request.POST or None, request.FILES or None, instance=profile
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile saved.")
        return redirect("web:candidate_home")
    return render(request, "web/candidate_profile.html", {"form": form, "profile": profile})


def job_browse(request):
    """Public list of open jobs across all companies."""
    query = request.GET.get("q", "").strip()
    jobs = Job.objects.filter(status=Job.OPEN).select_related("company")
    if query:
        jobs = jobs.filter(
            Q(title__icontains=query)
            | Q(location__icontains=query)
            | Q(skills__name__icontains=query)
        ).distinct()
    applied_ids = set()
    if request.user.is_authenticated:
        applied_ids = set(
            Application.objects.filter(candidate__user=request.user).values_list(
                "job_id", flat=True
            )
        )
    if request.headers.get("HX-Request"):
        template = "web/partials/job_results.html"
    else:
        template = "web/job_browse.html"
    return render(
        request, template, {"jobs": jobs, "q": query, "applied_ids": applied_ids}
    )


def job_public_detail(request, pk):
    job = get_object_or_404(Job.objects.select_related("company"), pk=pk, status=Job.OPEN)
    already_applied = (
        request.user.is_authenticated
        and Application.objects.filter(job=job, candidate__user=request.user).exists()
    )
    return render(
        request,
        "web/job_public_detail.html",
        {"job": job, "form": ApplyForm(), "already_applied": already_applied},
    )


@login_required
def job_apply(request, pk):
    profile = _candidate_profile(request)
    job = get_object_or_404(Job, pk=pk, status=Job.OPEN)
    form = ApplyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        application, created = Application.objects.get_or_create(
            job=job,
            candidate=profile,
            defaults={"current_stage": job.first_stage},
        )
        if created:
            # AI fit scoring runs off a post_save signal in assessments/.
            messages.success(request, f"Applied to {job.title}.")
        else:
            messages.info(request, "You have already applied to this job.")
        return redirect("web:candidate_home")
    return render(
        request,
        "web/job_public_detail.html",
        {"job": job, "form": form, "already_applied": False},
    )
