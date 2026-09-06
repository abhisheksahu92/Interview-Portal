"""Web UI views: landing, recruiter dashboard, interviewer queue, candidate portal."""

import mimetypes
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.db.models import Avg, Count, Max, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.emails import send_invitation
from core.models import Invitation, Membership
from core.permissions import for_company, role_required
from jobs.models import (
    Application,
    CandidateProfile,
    Job,
    PipelineStage,
    Skill,
    StageReview,
)
from jobs.services import (
    advance_application,
    record_review,
    reject_application,
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
from web.services.apply import apply_to_job

STAFF_ROLES = (Membership.OWNER, Membership.RECRUITER)


# --- helpers --------------------------------------------------------------


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
    jobs = _company_jobs(request).annotate(application_count=Count("applications", distinct=True))
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
        {
            "company": company,
            "jobs": jobs,
            "kpis": kpis,
            **_dashboard_extras(request, company),
        },
    )


def _dashboard_extras(request, company):
    """Plan-dependent dashboard cards: upcoming interviews and pending offers.

    Each block is skipped entirely (no query at all) when the tenant's plan does
    not include the feature, so the FREE dashboard stays exactly as cheap as it
    was before these cards existed.
    """
    from billing.entitlements import has_feature

    extras = {"upcoming_interviews": None, "pending_offer_count": None}
    if has_feature(company, "scheduling"):
        from scheduling.models import Interview

        extras["upcoming_interviews"] = list(
            Interview.objects.filter(
                company=company,
                status__in=[Interview.CONFIRMED, Interview.PROPOSED],
                scheduled_start__gte=timezone.now(),
            )
            .select_related("application__candidate__user", "application__job", "stage")
            .order_by("scheduled_start")[:5]
        )
    if has_feature(company, "offers"):
        from offers.models import Offer

        extras["pending_offer_count"] = Offer.objects.filter(
            application__job__company=company,
            status__in=[Offer.SENT, Offer.VIEWED],
        ).count()
    return extras


def _valid(form):
    """True when ``form`` is absent (feature off) or validates."""
    return form is None or form.is_valid()


def _add_plan_limit_errors(form, error):
    """Surface a billing ValidationError from Job.save() as form errors."""
    message_dict = getattr(error, "message_dict", None)
    if message_dict:
        for field, messages_ in message_dict.items():
            for message in messages_:
                form.add_error(field if field in form.fields else None, message)
    else:
        for message in error.messages:
            form.add_error(None, message)


def _job_client_form(request, job=None):
    """``clients.JobClientForm`` for the job screens, or None when not entitled.

    The end-client field only exists for tenants on a plan with the client
    portal, so the job form renders (and applies) it conditionally.
    """
    from billing.entitlements import has_feature

    if not has_feature(getattr(request, "company", None), "client_portal"):
        return None
    from clients.forms import JobClientForm

    return JobClientForm(request.POST or None, company=request.company, job=job)


@login_required
@role_required(*STAFF_ROLES)
def job_create(request):
    form = JobForm(request.POST or None, company=request.company)
    client_form = _job_client_form(request)
    plan_limit_hit = False
    if request.method == "POST" and form.is_valid() and _valid(client_form):
        job = form.save(commit=False)
        job.created_by = request.user
        job.company = request.company
        try:
            job.save()
        except ValidationError as exc:
            _add_plan_limit_errors(form, exc)
            plan_limit_hit = True
        else:
            form.save_m2m()
            if client_form is not None:
                client_form.apply(job)
            messages.success(request, f"Job “{job.title}” created with a default pipeline.")
            return redirect("web:job_detail", pk=job.pk)
    return render(
        request,
        "web/job_form.html",
        {
            "form": form,
            "client_form": client_form,
            "job": None,
            "plan_limit_hit": plan_limit_hit,
        },
    )


@login_required
@role_required(*STAFF_ROLES)
def job_edit(request, pk):
    job = get_object_or_404(_company_jobs(request), pk=pk)
    form = JobForm(request.POST or None, instance=job, company=request.company)
    client_form = _job_client_form(request, job=job)
    plan_limit_hit = False
    if request.method == "POST" and form.is_valid() and _valid(client_form):
        try:
            form.save()
        except ValidationError as exc:
            _add_plan_limit_errors(form, exc)
            plan_limit_hit = True
        else:
            if client_form is not None:
                client_form.apply(job)
            messages.success(request, "Job updated.")
            return redirect("web:job_detail", pk=job.pk)
    return render(
        request,
        "web/job_form.html",
        {
            "form": form,
            "client_form": client_form,
            "job": job,
            "plan_limit_hit": plan_limit_hit,
        },
    )


def _upcoming_interview(application):
    """The soonest still-open interview on ``application``, or None.

    Reads the ``interviews`` prefetch rather than querying, so the board stays
    at a constant number of queries however many cards it renders.
    """
    from scheduling.models import Interview

    now = timezone.now()
    upcoming = [
        interview
        for interview in application.interviews.all()
        if interview.status in Interview.OPEN_STATUSES
        and interview.scheduled_start is not None
        and interview.scheduled_start >= now
    ]
    upcoming.sort(key=lambda i: i.scheduled_start)
    return upcoming[0] if upcoming else None


def _active_video_screen(job):
    """The job's live video screen, or None — used by the card's video action."""
    from video.models import VideoScreen

    return VideoScreen.objects.filter(job=job, is_active=True).order_by("pk").first()


def _kanban_context(request, job, notice=None):
    stages = list(job.stages.all())
    applications = (
        Application.objects.filter(job=job)
        .select_related("candidate__user", "current_stage")
        .prefetch_related("reviews__reviewer", "interviews")
    )
    by_stage = {stage.pk: [] for stage in stages}
    unassigned, closed = [], []
    for application in applications:
        application.latest_review = application.reviews.all().first()
        application.upcoming_interview = _upcoming_interview(application)
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
        "stages": stages,
        "board_notice": notice,
        "active_video_screen": _active_video_screen(job),
    }


@login_required
@role_required(*STAFF_ROLES)
def job_detail(request, pk):
    job = get_object_or_404(_company_jobs(request), pk=pk)
    context = _kanban_context(request, job)
    context["stage_form"] = StageForm(job=job)
    return render(request, "web/job_detail.html", context)


@login_required
@role_required(*STAFF_ROLES)
def job_kanban(request, pk):
    """HTMX partial: just the board (used to refresh after an action)."""
    job = get_object_or_404(_company_jobs(request), pk=pk)
    if not request.headers.get("HX-Request"):
        # Opened directly in a browser: the bare partial is useless, send them
        # to the full job page instead.
        return redirect("web:job_detail", pk=job.pk)
    return render(request, "web/partials/kanban.html", _kanban_context(request, job))


def _board_response(request, application, notice=None, success=""):
    """Refresh the whole board (HTMX) or fall back to a redirect + message."""
    if request.headers.get("HX-Request"):
        return render(
            request,
            "web/partials/kanban.html",
            _kanban_context(request, application.job, notice=notice),
        )
    if notice:
        messages.warning(request, notice)
    elif success:
        messages.success(request, success)
    return redirect("web:job_detail", pk=application.job_id)


STALE_STAGE_NOTICE = "That application already moved on — the board below is up to date."


def _locked_application(request, pk):
    """Re-read the application inside the transaction, locked for update."""
    return get_object_or_404(_company_applications(request).select_for_update(), pk=pk)


def _expected_stage_matches(request, application):
    """True when the client's expected stage id still matches the server state.

    Guards against a double-clicked Advance/Reject: the second POST carries the
    stage the card was rendered at, which no longer matches after the first one
    landed, so it becomes a no-op.
    """
    expected = request.POST.get("expected_stage")
    if not expected:
        return True
    if expected == "":
        return True
    current = application.current_stage_id
    if expected in {"none", "None", "0"}:
        return current is None
    try:
        return current == int(expected)
    except (TypeError, ValueError):
        return False


@login_required
@role_required(*STAFF_ROLES)
@require_POST
def application_advance(request, pk):
    with transaction.atomic():
        application = _locked_application(request, pk)
        if application.status != Application.ACTIVE or not _expected_stage_matches(
            request, application
        ):
            return _board_response(request, application, notice=STALE_STAGE_NOTICE)
        advance_application(application)
    return _board_response(request, application, success="Application advanced.")


@login_required
@role_required(*STAFF_ROLES)
@require_POST
def application_reject(request, pk):
    with transaction.atomic():
        application = _locked_application(request, pk)
        if application.status != Application.ACTIVE or not _expected_stage_matches(
            request, application
        ):
            return _board_response(request, application, notice=STALE_STAGE_NOTICE)
        reject_application(application)
    return _board_response(request, application, success="Application rejected.")


@login_required
@role_required(*STAFF_ROLES)
@require_POST
def application_set_stage(request, pk):
    """Put an application (typically an unassigned one) onto a chosen stage."""
    application = get_object_or_404(_company_applications(request), pk=pk)
    stage = get_object_or_404(
        PipelineStage.objects.filter(job=application.job), pk=request.POST.get("stage")
    )
    application.current_stage = stage
    application.save(update_fields=["current_stage", "updated_at"])
    return _board_response(request, application, success=f"Moved to {stage.name}.")


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
    queue_mode = request.POST.get("ui", request.GET.get("ui")) == "queue"
    form = ReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        stage = application.current_stage or application.job.first_stage
        if stage is None:
            messages.error(request, "This job has no pipeline stages yet.")
            return redirect("web:job_detail", pk=application.job_id)
        # record_review also applies the pipeline transition: a PASS at the
        # current stage advances, a FAIL rejects, a HOLD changes nothing.
        record_review(
            application,
            stage=stage,
            reviewer=request.user,
            decision=form.cleaned_data["decision"],
            rating=form.cleaned_data.get("rating") or None,
            feedback=form.cleaned_data.get("feedback", ""),
        )
        application.refresh_from_db()
        if request.headers.get("HX-Request"):
            if queue_mode:
                # Interviewer queue: hand back this row's own form with a
                # confirmation. Never the recruiter card (it carries
                # advance/reject buttons interviewers must not see).
                return render(
                    request,
                    "web/partials/review_form.html",
                    {
                        "form": ReviewForm(),
                        "application": application,
                        "queue_mode": True,
                        "saved": True,
                    },
                )
            # Recruiter board: the card may have changed column, so swap the
            # whole board exactly like advance/reject does.
            return render(
                request,
                "web/partials/kanban.html",
                _kanban_context(request, application.job),
            )
        messages.success(request, "Review saved.")
        return redirect("web:job_detail", pk=application.job_id)
    return render(
        request,
        "web/partials/review_form.html",
        {"form": form, "application": application, "queue_mode": queue_mode},
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
        {
            "rows": rows,
            "company": company,
            # Interviewers have no access to the recruiter board, so the link
            # to it is only rendered for staff roles.
            "can_open_board": request.user.role_in(company) in STAFF_ROLES,
        },
    )


# --- company settings -----------------------------------------------------


@login_required
@role_required(*STAFF_ROLES)
def settings_members(request):
    company = request.company
    form = InviteForm(request.POST or None, company=company, invited_by=request.user)
    if request.method == "POST":
        if request.user.role_in(company) != Membership.OWNER:
            raise PermissionDenied("Only owners can manage members.")
        if form.is_valid():
            invitation = form.save()
            send_invitation(invitation, request)
            messages.success(request, f"Invitation sent to {invitation.email}.")
            return redirect("web:settings_members")
    memberships = (
        Membership.objects.filter(company=company)
        .select_related("user")
        .order_by("role", "user__email")
    )
    invitations = [
        inv
        for inv in Invitation.objects.filter(
            company=company, accepted_at__isnull=True
        ).select_related("invited_by")
    ]
    return render(
        request,
        "web/settings_members.html",
        {
            "form": form,
            "memberships": memberships,
            "invitations": invitations,
            "company": company,
        },
    )


@login_required
@role_required(Membership.OWNER)
@require_POST
def invite_resend(request, pk):
    invitation = get_object_or_404(
        Invitation.objects.filter(company=request.company, accepted_at__isnull=True),
        pk=pk,
    )
    invitation.refresh_token()
    send_invitation(invitation, request)
    messages.success(request, f"Invitation re-sent to {invitation.email}.")
    return redirect("web:settings_members")


@login_required
@role_required(Membership.OWNER)
@require_POST
def invite_revoke(request, pk):
    invitation = get_object_or_404(Invitation.objects.filter(company=request.company), pk=pk)
    email = invitation.email
    invitation.delete()
    messages.success(request, f"Invitation for {email} revoked.")
    return redirect("web:settings_members")


@login_required
@role_required(Membership.OWNER)
@require_POST
def member_remove(request, pk):
    membership = get_object_or_404(Membership.objects.filter(company=request.company), pk=pk)
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
        form.save()
        messages.success(request, "Skill added.")
        return redirect("web:settings_skills")
    return render(
        request,
        "web/settings_skills.html",
        {"form": form, "skills": _skill_rows(company), "company": company},
    )


def _skill_rows(company):
    return for_company(Skill.objects.all(), company).annotate(
        job_count=Count("jobs", distinct=True)
    )


@login_required
@role_required(*STAFF_ROLES)
def skill_edit(request, pk):
    """Rename a skill; invalid input comes back with the typed value kept."""
    company = request.company
    skill = get_object_or_404(for_company(Skill.objects.all(), company), pk=pk)
    form = SkillForm(request.POST or None, instance=skill, company=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Skill renamed.")
        return redirect("web:settings_skills")
    return render(
        request,
        "web/settings_skills.html",
        {
            "form": SkillForm(company=company),
            "edit_form": form,
            "edit_skill": skill,
            "skills": _skill_rows(company),
            "company": company,
        },
    )


@login_required
@role_required(*STAFF_ROLES)
@require_POST
def skill_delete(request, pk):
    skill = get_object_or_404(for_company(Skill.objects.all(), request.company), pk=pk)
    name = skill.name
    skill.delete()
    messages.success(request, f"Skill “{name}” removed.")
    return redirect("web:settings_skills")


@login_required
@role_required(*STAFF_ROLES)
def settings_stages(request, pk):
    """Edit the pipeline stage template for one job."""
    job = get_object_or_404(_company_jobs(request), pk=pk)
    form = StageForm(request.POST or None, job=job)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Stage added.")
        return redirect("web:settings_stages", pk=job.pk)
    return render(
        request,
        "web/settings_stages.html",
        {"job": job, "form": form, "stages": job.stages.all()},
    )


def _company_stages(request):
    return PipelineStage.objects.filter(job__company=request.company)


@login_required
@role_required(*STAFF_ROLES)
def stage_edit(request, pk):
    """Rename a stage or change its kind / assessment requirement."""
    stage = get_object_or_404(_company_stages(request), pk=pk)
    job = stage.job
    form = StageForm(request.POST or None, instance=stage, job=job)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Stage updated.")
        return redirect("web:settings_stages", pk=job.pk)
    return render(
        request,
        "web/settings_stages.html",
        {
            "job": job,
            "form": StageForm(job=job),
            "edit_form": form,
            "edit_stage": stage,
            "stages": job.stages.all(),
        },
    )


@login_required
@role_required(*STAFF_ROLES)
@require_POST
def stage_move(request, pk, direction):
    """Swap a stage's order with its neighbour (simple up/down reordering)."""
    stage = get_object_or_404(_company_stages(request), pk=pk)
    siblings = stage.job.stages.all()
    if direction == "up":
        neighbour = siblings.filter(order__lt=stage.order).order_by("-order").first()
    else:
        neighbour = siblings.filter(order__gt=stage.order).order_by("order").first()
    if neighbour is None:
        messages.info(request, f"“{stage.name}” is already at the end of the pipeline.")
    else:
        with transaction.atomic():
            stage_order, neighbour_order = stage.order, neighbour.order
            # unique (job, order): park one stage out of the way first.
            parked = (siblings.aggregate(m=Max("order"))["m"] or stage_order) + 1
            stage.order = parked
            stage.save(update_fields=["order"])
            neighbour.order = stage_order
            neighbour.save(update_fields=["order"])
            stage.order = neighbour_order
            stage.save(update_fields=["order"])
        messages.success(request, f"“{stage.name}” moved {direction}.")
    return redirect("web:settings_stages", pk=stage.job_id)


def stage_blockers(stage):
    """Counts of the things that would break if ``stage`` were deleted."""
    from assessments.models import Assessment

    return {
        "applications": Application.objects.filter(current_stage=stage).count(),
        "assessments": Assessment.objects.filter(stage=stage).count(),
    }


@login_required
@role_required(*STAFF_ROLES)
@require_POST
def stage_delete(request, pk):
    """Delete a stage, refusing while anything still points at it.

    Passing ``move_applications=1`` first parks the stage's applications on the
    previous stage (or the next one, for the first stage) so the delete can go
    ahead without silently orphaning candidates.
    """
    stage = get_object_or_404(_company_stages(request), pk=pk)
    job_id = stage.job_id
    blockers = stage_blockers(stage)

    if blockers["applications"] and request.POST.get("move_applications"):
        siblings = stage.job.stages.exclude(pk=stage.pk)
        target = siblings.filter(order__lt=stage.order).order_by("-order").first() or (
            siblings.filter(order__gt=stage.order).order_by("order").first()
        )
        if target is None:
            messages.error(
                request,
                "This is the only stage on the pipeline, so its "
                f"{blockers['applications']} application(s) have nowhere to go. "
                "Add another stage first.",
            )
            return redirect("web:settings_stages", pk=job_id)
        Application.objects.filter(current_stage=stage).update(current_stage=target)
        messages.info(
            request,
            f"{blockers['applications']} application(s) moved to “{target.name}”.",
        )
        blockers = stage_blockers(stage)

    if blockers["applications"] or blockers["assessments"]:
        parts = []
        if blockers["applications"]:
            parts.append(f"{blockers['applications']} application(s) sit on it")
        if blockers["assessments"]:
            parts.append(f"{blockers['assessments']} assessment(s) use it")
        messages.error(
            request,
            f"“{stage.name}” cannot be deleted because " + " and ".join(parts) + ". "
            "Move the applications to another stage (or repoint the assessments) "
            "and try again.",
        )
        return redirect("web:settings_stages", pk=job_id)

    name = stage.name
    stage.delete()
    messages.success(request, f"Stage “{name}” removed.")
    return redirect("web:settings_stages", pk=job_id)


# --- candidate portal -----------------------------------------------------


def _candidate_profile(request):
    if not request.user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    if getattr(request, "company", None) is not None:
        raise PermissionDenied("Company members use the recruiter workspace.")
    profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
    return profile


def _upcoming_interviews_by_application(applications):
    """Map application id -> the next still-open, scheduled interview.

    Purely presentational: the portal card shows a "join" chip for a booked
    interview.  Scheduling is an optional app, so a missing table or model must
    never break the portal.
    """
    try:
        from scheduling.models import Interview
    except Exception:  # pragma: no cover - scheduling always installed today
        return {}
    try:
        rows = (
            Interview.objects.filter(
                application__in=list(applications),
                status__in=Interview.OPEN_STATUSES,
                scheduled_start__isnull=False,
            )
            .select_related("stage")
            .order_by("scheduled_start")
        )
        upcoming = {}
        for interview in rows:
            upcoming.setdefault(interview.application_id, interview)
        return upcoming
    except DatabaseError:  # pragma: no cover - defensive
        return {}


@login_required
def candidate_home(request):
    profile = _candidate_profile(request)
    applications = (
        profile.applications.select_related("job__company", "current_stage")
        .prefetch_related("job__stages")
        .all()
    )
    upcoming = _upcoming_interviews_by_application(applications)
    rows = []
    for application in applications:
        stages = list(application.job.stages.all())
        current_order = application.current_stage.order if application.current_stage else 0
        rows.append(
            {
                "application": application,
                "stages": stages,
                "current_order": current_order,
                "assessment_url": assessment_url_for(application),
                "interview": upcoming.get(application.pk),
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
    form = CandidateProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile saved.")
        return redirect("web:candidate_home")
    return render(request, "web/candidate_profile.html", {"form": form, "profile": profile})


def _publicly_listable_jobs():
    """Open jobs whose company actually consented to a public listing.

    ``status=OPEN`` only means the requisition is open in the tenant's own
    pipeline; it is not permission to publish. Consent is the pair of switches
    the board already honours - a published careers site that is listed on the
    network - so this surface uses the same rule instead of showing every
    tenant's roles, including those of companies that opted out.
    """
    return Job.objects.filter(
        status=Job.OPEN,
        company__careers_site__published=True,
        company__careers_site__list_in_network=True,
    ).select_related("company")


def job_browse(request):
    """Public list of open jobs across every company that opted in."""
    query = request.GET.get("q", "").strip()
    jobs = _publicly_listable_jobs()
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
    return render(request, template, {"jobs": jobs, "q": query, "applied_ids": applied_ids})


def job_public_detail(request, pk):
    job = get_object_or_404(_publicly_listable_jobs(), pk=pk)
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
    """Handle the apply POST. Always ends on a redirect so the job URL stays shareable."""
    _candidate_profile(request)  # raises for company members; also creates the profile
    job = get_object_or_404(Job, pk=pk, status=Job.OPEN)
    if request.method != "POST":
        return redirect("web:job_public_detail", pk=job.pk)
    form = ApplyForm(request.POST)
    if not form.is_valid():
        errors = [e for field in form for e in field.errors] or ["Please try again."]
        messages.error(request, errors[0])
        return redirect("web:job_public_detail", pk=job.pk)
    application = apply_to_job(request.user, job)
    if application.was_created:
        # AI fit scoring runs off a post_save signal in assessments/.
        messages.success(request, f"Applied to {job.title}.")
    else:
        messages.info(request, "You have already applied to this job.")
    return redirect("web:candidate_home")


# --- recruiter candidate profile -----------------------------------------


def _candidate_applications(company, profile):
    """Every application this candidate has to ``company``'s jobs.

    This is the whole tenant boundary of the profile page: a candidate with no
    application here is simply not visible (404), however real their profile is
    to another tenant.
    """
    return (
        Application.objects.filter(job__company=company, candidate=profile)
        .select_related("job", "current_stage")
        .prefetch_related("job__stages", "reviews__reviewer", "reviews__stage")
        .order_by("-created_at")
    )


def _interviewer_may_see(user, company, applications):
    """True when an interviewer has a stake in one of these applications.

    Interviewers get read-only access to the candidates they were actually
    asked about: someone they reviewed, or someone they are on an interview
    for. Everyone else on the interviewer role gets a 403.
    """
    if StageReview.objects.filter(application__in=applications, reviewer=user).exists():
        return True
    from billing.entitlements import has_feature

    if has_feature(company, "scheduling"):
        from scheduling.models import Interview

        return Interview.objects.filter(application__in=applications, interviewers=user).exists()
    return False


def _candidate_page_access(request, pk):
    """(company, profile, applications, read_only) for the profile page, or raise.

    Raises ``Http404`` when the profile has nothing to do with this tenant and
    ``PermissionDenied`` when the viewer's role does not reach it.
    """
    company = _require_member(request)
    profile = get_object_or_404(
        CandidateProfile.objects.select_related("user").prefetch_related("skills"),
        pk=pk,
    )
    applications = _candidate_applications(company, profile)
    if not applications.exists():
        raise Http404("No such candidate in this workspace.")
    role = request.user.role_in(company)
    if role in STAFF_ROLES:
        return company, profile, applications, False
    if role == Membership.INTERVIEWER and _interviewer_may_see(request.user, company, applications):
        return company, profile, applications, True
    raise PermissionDenied("You do not have access to this candidate.")


def _stage_steps(application):
    """The job's stages plus a done/current flag, for the stepper."""
    current_order = application.current_stage.order if application.current_stage else 0
    steps = []
    for stage in application.job.stages.all():
        steps.append(
            {
                "stage": stage,
                "is_current": application.current_stage_id == stage.pk,
                "is_done": stage.order < current_order or application.status == Application.HIRED,
            }
        )
    return steps


def _candidate_attempts(applications):
    from assessments.models import Attempt

    return list(
        Attempt.objects.filter(application__in=applications)
        .select_related("assessment", "application__job")
        .order_by("-started_at")
    )


def _candidate_interviews(company, applications):
    from billing.entitlements import has_feature

    if not has_feature(company, "scheduling"):
        return None
    from scheduling.models import Interview

    return list(
        Interview.objects.filter(application__in=applications)
        .select_related("stage", "application__job")
        .prefetch_related("interviewers")
        .order_by("-scheduled_start")
    )


def _candidate_offers(company, applications):
    from billing.entitlements import has_feature

    if not has_feature(company, "offers"):
        return None
    from offers.models import Offer

    return list(
        Offer.objects.filter(application__in=applications)
        .select_related("application__job")
        .order_by("-created_at")
    )


def _candidate_submissions(company, applications):
    from billing.entitlements import has_feature

    if not has_feature(company, "client_portal"):
        return None
    from clients.models import Submission

    return list(
        Submission.objects.filter(application__in=applications)
        .select_related("client", "application__job")
        .order_by("-created_at")
    )


def _candidate_video_invites(company, applications):
    from billing.entitlements import has_feature

    if not has_feature(company, "video"):
        return None
    from video.models import VideoInvite

    return list(
        VideoInvite.objects.filter(application__in=applications)
        .select_related("screen", "application__job")
        .order_by("-created_at")
    )


def _talent_profile_for(company, profile):
    from talent.models import TalentProfile

    return (
        TalentProfile.objects.filter(company=company, linked_candidate=profile)
        .prefetch_related("skills")
        .first()
    )


def _timeline(applications, attempts, interviews, offers, submissions, invites):
    """One time-ordered stream (newest first) of everything on this candidate."""
    events = []

    def add(when, kind, label, detail="", icon="bi-dot"):
        if when is None:
            return
        events.append({"when": when, "kind": kind, "label": label, "detail": detail, "icon": icon})

    for application in applications:
        add(
            application.created_at,
            "application",
            f"Applied to {application.job.title}",
            application.get_status_display(),
            "bi-send",
        )
        for review in application.reviews.all():
            add(
                review.created_at,
                "review",
                f"{review.stage.name}: {review.get_decision_display()}",
                f"by {review.reviewer.email}",
                "bi-chat-left-text",
            )
    for attempt in attempts:
        add(
            attempt.submitted_at or attempt.started_at,
            "attempt",
            f"Assessment: {attempt.assessment.title}",
            "" if attempt.score_percent is None else f"{attempt.score_percent}%",
            "bi-clipboard-check",
        )
    for interview in interviews or []:
        add(
            interview.scheduled_start or interview.created_at,
            "interview",
            f"Interview · {interview.get_status_display()}",
            interview.stage.name if interview.stage else "",
            "bi-calendar2-check",
        )
    for offer in offers or []:
        add(
            offer.sent_at or offer.created_at,
            "offer",
            f"Offer {offer.get_status_display()}",
            offer.application.job.title,
            "bi-file-earmark-text",
        )
    for submission in submissions or []:
        add(
            submission.created_at,
            "submission",
            f"Submitted to {submission.client.name}",
            submission.get_status_display(),
            "bi-briefcase",
        )
    for invite in invites or []:
        add(
            invite.created_at,
            "video",
            f"Video screen · {invite.get_status_display()}",
            invite.screen.title if invite.screen else "",
            "bi-camera-video",
        )
    events.sort(key=lambda e: e["when"], reverse=True)
    return events


@login_required
def candidate_detail(request, pk):
    """Recruiter-facing candidate profile: everything this tenant knows.

    Interviewers reach it read-only for candidates they reviewed or are
    scheduled with; every paid-feature block is skipped entirely (no query at
    all) when the tenant's plan does not include it.
    """
    company, profile, applications, read_only = _candidate_page_access(request, pk)
    applications = list(applications)
    talent_profile = _talent_profile_for(company, profile)
    note_form = None
    if talent_profile is not None and not read_only:
        from talent.forms import NoteForm

        note_form = NoteForm(instance=talent_profile)
        if request.method == "POST":
            note_form = NoteForm(request.POST, instance=talent_profile)
            if note_form.is_valid():
                note_form.save()
                messages.success(request, "Notes saved.")
                return redirect("web:candidate_detail", pk=profile.pk)
    elif request.method == "POST":
        raise PermissionDenied("Notes cannot be edited here.")

    attempts = _candidate_attempts(applications)
    interviews = _candidate_interviews(company, applications)
    offers = _candidate_offers(company, applications)
    submissions = _candidate_submissions(company, applications)
    invites = _candidate_video_invites(company, applications)
    rows = [
        {
            "application": application,
            "steps": _stage_steps(application),
            "reviews": list(application.reviews.all()),
        }
        for application in applications
    ]
    return render(
        request,
        "web/candidate_detail.html",
        {
            "company": company,
            "profile": profile,
            "candidate_user": profile.user,
            "rows": rows,
            "read_only": read_only,
            "attempts": attempts,
            "interviews": interviews,
            "offers": offers,
            "submissions": submissions,
            "video_invites": invites,
            "talent_profile": talent_profile,
            "note_form": note_form,
            "timeline": _timeline(applications, attempts, interviews, offers, submissions, invites),
        },
    )


@login_required
def candidate_resume(request, pk):
    """Stream a candidate's résumé through the same permission check as the page.

    The file is served by this view rather than linked at its ``/media`` URL so
    that a résumé is never readable by anyone who happens to guess the path.
    """
    _company, profile, _applications, _read_only = _candidate_page_access(request, pk)
    resume = profile.resume
    if not resume:
        raise Http404("No résumé on file for this candidate.")
    content_type = mimetypes.guess_type(resume.name)[0] or "application/octet-stream"
    try:
        handle = resume.open("rb")
    except (FileNotFoundError, OSError) as exc:  # storage lost the file
        raise Http404("Résumé file is unavailable.") from exc
    extension = os.path.splitext(resume.name)[1] or ".pdf"
    return FileResponse(
        handle,
        as_attachment=True,
        filename=f"resume-{profile.pk}{extension}",
        content_type=content_type,
    )
