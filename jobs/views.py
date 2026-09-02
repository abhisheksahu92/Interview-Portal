"""Server-rendered views: public job board plus recruiter job/stage/skill config."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Membership
from core.permissions import for_company, role_required

from .forms import JobForm, PipelineStageForm, SkillForm
from .models import Application, CandidateProfile, Job, PipelineStage, Skill
from .services import apply_to_job, create_job_with_default_stages

MANAGER_ROLES = (Membership.OWNER, Membership.RECRUITER)


def _company_jobs(request):
    return for_company(Job.objects.all(), getattr(request, "company", None))


def _company_skills(request):
    return for_company(Skill.objects.all(), getattr(request, "company", None))


# --- Public job board -----------------------------------------------------


def job_list(request):
    """Public list of OPEN jobs across all companies."""
    jobs = (
        Job.objects.filter(status=Job.OPEN)
        .select_related("company")
        .prefetch_related("skills")
    )
    query = request.GET.get("q", "").strip()
    if query:
        jobs = jobs.filter(
            Q(title__icontains=query)
            | Q(location__icontains=query)
            | Q(skills__name__icontains=query)
        ).distinct()
    return render(request, "jobs/job_list.html", {"jobs": jobs, "query": query})


def job_detail(request, pk):
    """Public detail page for an OPEN job."""
    job = get_object_or_404(
        Job.objects.select_related("company").prefetch_related("skills", "stages"),
        pk=pk,
        status=Job.OPEN,
    )
    application = None
    if request.user.is_authenticated:
        application = Application.objects.filter(
            job=job, candidate__user=request.user
        ).first()
    return render(
        request,
        "jobs/job_detail.html",
        {"job": job, "application": application},
    )


@login_required
def job_apply(request, pk):
    """Candidate applies to an OPEN job (POST only)."""
    if request.method != "POST":
        return redirect("jobs:job_detail", pk=pk)
    job = get_object_or_404(Job, pk=pk)
    profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
    try:
        apply_to_job(job, profile)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Application submitted.")
    return redirect("jobs:job_detail", pk=pk)


@login_required
def my_applications(request):
    """A candidate's own applications."""
    applications = (
        Application.objects.filter(candidate__user=request.user)
        .select_related("job", "job__company", "current_stage")
    )
    return render(
        request, "jobs/my_applications.html", {"applications": applications}
    )


# --- Recruiter job management --------------------------------------------


@login_required
@role_required(*MANAGER_ROLES)
def manage_job_list(request):
    jobs = _company_jobs(request).annotate(
        application_count=Count("applications", distinct=True)
    )
    return render(request, "jobs/manage_job_list.html", {"jobs": jobs})


@login_required
@role_required(*MANAGER_ROLES)
def manage_job_create(request):
    company = request.company
    form = JobForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        job = create_job_with_default_stages(
            company=company,
            created_by=request.user,
            skills=form.cleaned_data.get("skills"),
            **{
                k: v
                for k, v in form.cleaned_data.items()
                if k not in {"skills"}
            },
        )
        messages.success(request, "Job created with a default pipeline.")
        return redirect("jobs:manage_job_detail", pk=job.pk)
    return render(request, "jobs/manage_job_form.html", {"form": form, "job": None})


@login_required
@role_required(*MANAGER_ROLES)
def manage_job_detail(request, pk):
    job = get_object_or_404(_company_jobs(request), pk=pk)
    return render(
        request,
        "jobs/manage_job_detail.html",
        {
            "job": job,
            "stages": job.stages.all(),
            "applications": job.applications.select_related(
                "candidate__user", "current_stage"
            ),
            "stage_form": PipelineStageForm(),
        },
    )


@login_required
@role_required(*MANAGER_ROLES)
def manage_job_edit(request, pk):
    job = get_object_or_404(_company_jobs(request), pk=pk)
    form = JobForm(request.POST or None, instance=job, company=request.company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Job updated.")
        return redirect("jobs:manage_job_detail", pk=job.pk)
    return render(request, "jobs/manage_job_form.html", {"form": form, "job": job})


@login_required
@role_required(*MANAGER_ROLES)
def manage_job_delete(request, pk):
    job = get_object_or_404(_company_jobs(request), pk=pk)
    if request.method == "POST":
        job.delete()
        messages.success(request, "Job deleted.")
        return redirect("jobs:manage_job_list")
    return render(request, "jobs/confirm_delete.html", {"object": job, "kind": "job"})


# --- Pipeline stages ------------------------------------------------------


@login_required
@role_required(*MANAGER_ROLES)
def stage_create(request, job_pk):
    job = get_object_or_404(_company_jobs(request), pk=job_pk)
    form = PipelineStageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        stage = form.save(commit=False)
        stage.job = job
        try:
            stage.save()
        except IntegrityError:
            messages.error(request, "Another stage already uses that order.")
        else:
            messages.success(request, "Stage added.")
        return redirect("jobs:manage_job_detail", pk=job.pk)
    return render(
        request, "jobs/stage_form.html", {"form": form, "job": job, "stage": None}
    )


@login_required
@role_required(*MANAGER_ROLES)
def stage_edit(request, job_pk, pk):
    job = get_object_or_404(_company_jobs(request), pk=job_pk)
    stage = get_object_or_404(job.stages, pk=pk)
    form = PipelineStageForm(request.POST or None, instance=stage)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Stage updated.")
        return redirect("jobs:manage_job_detail", pk=job.pk)
    return render(
        request, "jobs/stage_form.html", {"form": form, "job": job, "stage": stage}
    )


@login_required
@role_required(*MANAGER_ROLES)
def stage_delete(request, job_pk, pk):
    job = get_object_or_404(_company_jobs(request), pk=job_pk)
    stage = get_object_or_404(job.stages, pk=pk)
    if request.method == "POST":
        stage.delete()
        messages.success(request, "Stage removed.")
        return redirect("jobs:manage_job_detail", pk=job.pk)
    return render(request, "jobs/confirm_delete.html", {"object": stage, "kind": "stage"})


@login_required
@role_required(*MANAGER_ROLES)
def stage_reorder(request, job_pk):
    """Reorder stages from a POSTed list of stage ids (``stage_ids``)."""
    job = get_object_or_404(_company_jobs(request), pk=job_pk)
    if request.method != "POST":
        return redirect("jobs:manage_job_detail", pk=job.pk)
    ids = [int(v) for v in request.POST.getlist("stage_ids") if str(v).isdigit()]
    stages = {s.pk: s for s in job.stages.all()}
    if set(ids) != set(stages):
        messages.error(request, "Reorder must include every stage of this job exactly once.")
        return redirect("jobs:manage_job_detail", pk=job.pk)
    with transaction.atomic():
        # Two passes to dodge the (job, order) unique constraint.
        PipelineStage.objects.filter(job=job).update(order=F("order") + 10000)
        for index, pk in enumerate(ids, start=1):
            PipelineStage.objects.filter(pk=pk).update(order=index)
    messages.success(request, "Pipeline reordered.")
    return redirect("jobs:manage_job_detail", pk=job.pk)


# --- Skills ---------------------------------------------------------------


@login_required
@role_required(*MANAGER_ROLES)
def skill_list(request):
    return render(
        request,
        "jobs/skill_list.html",
        {"skills": _company_skills(request), "form": SkillForm(company=request.company)},
    )


@login_required
@role_required(*MANAGER_ROLES)
def skill_create(request):
    form = SkillForm(request.POST or None, company=request.company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Skill added.")
        return redirect("jobs:skill_list")
    return render(
        request,
        "jobs/skill_list.html",
        {"skills": _company_skills(request), "form": form},
    )


@login_required
@role_required(*MANAGER_ROLES)
def skill_edit(request, pk):
    skill = get_object_or_404(_company_skills(request), pk=pk)
    form = SkillForm(request.POST or None, instance=skill, company=request.company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Skill updated.")
        return redirect("jobs:skill_list")
    return render(request, "jobs/skill_form.html", {"form": form, "skill": skill})


@login_required
@role_required(*MANAGER_ROLES)
def skill_delete(request, pk):
    skill = get_object_or_404(_company_skills(request), pk=pk)
    if request.method == "POST":
        skill.delete()
        messages.success(request, "Skill deleted.")
        return redirect("jobs:skill_list")
    return render(request, "jobs/confirm_delete.html", {"object": skill, "kind": "skill"})
