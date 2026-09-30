"""Domain services for the jobs app.

All pipeline transitions go through here so views, API and management commands
share one set of rules.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from core.models import Membership
from core.analytics import capture as ph_capture
from core.observe import hiring_event

from .models import Application, Job, StageReview

REVIEW_ROLES = (Membership.OWNER, Membership.RECRUITER, Membership.INTERVIEWER)
ADVANCING_ROLES = (Membership.OWNER, Membership.RECRUITER, Membership.INTERVIEWER)


@transaction.atomic
def create_job_with_default_stages(company, created_by=None, skills=None, **fields):
    """Create a job for ``company``; default pipeline stages are seeded by Job.save()."""
    job = Job.objects.create(company=company, created_by=created_by, **fields)
    if skills:
        job.skills.set(skills)
    return job


@transaction.atomic
def apply_to_job(job, candidate_profile):
    """Create an ACTIVE application at the job's first stage.

    Raises ValidationError when the job is not OPEN or the candidate already
    applied. AI fit scoring is attached to Application creation by a post_save
    receiver in ``assessments.signals`` (best-effort, never raises), so every
    creation path -- services, web and API -- gets it.
    """
    if job.status != Job.OPEN:
        raise ValidationError("This job is not open for applications.")
    if Application.objects.filter(job=job, candidate=candidate_profile).exists():
        raise ValidationError("You have already applied to this job.")
    application = Application.objects.create(
        job=job,
        candidate=candidate_profile,
        current_stage=job.first_stage,
        status=Application.ACTIVE,
    )
    hiring_event(
        "application.created",
        application_id=application.pk,
        job_id=job.pk,
        company_id=job.company_id,
        candidate_id=candidate_profile.pk,
        stage_id=application.current_stage_id,
    )
    ph_capture(
        distinct_id=str(candidate_profile.user_id),
        event="application_submitted",
        properties={
            "application_id": application.pk,
            "job_id": job.pk,
            "company_id": job.company_id,
        },
    )
    return application


def advance_application(application):
    """Move an application forward one stage (or hire it at the last stage)."""
    result = application.advance()
    hiring_event(
        "application.advanced",
        application_id=application.pk,
        job_id=application.job_id,
        company_id=application.job.company_id,
        new_stage_id=application.current_stage_id,
        new_status=application.status,
    )
    return result


def reject_application(application):
    """Reject an application."""
    result = application.reject()
    hiring_event(
        "application.rejected",
        application_id=application.pk,
        job_id=application.job_id,
        company_id=application.job.company_id,
    )
    return result


@transaction.atomic
def record_review(application, stage, reviewer, decision, rating=None, feedback=""):
    """Record a StageReview and apply the automatic pipeline transition.

    A PASS at the application's *current* stage by an interviewer/recruiter/owner
    advances the application; a FAIL rejects it. HOLD changes nothing.
    """
    if stage.job_id != application.job_id:
        raise ValidationError("Stage does not belong to this application's job.")

    review, _ = StageReview.objects.update_or_create(
        application=application,
        stage=stage,
        reviewer=reviewer,
        defaults={"decision": decision, "rating": rating, "feedback": feedback or ""},
    )

    hiring_event(
        "stage.reviewed",
        application_id=application.pk,
        job_id=application.job_id,
        company_id=application.job.company_id,
        stage_id=stage.pk,
        reviewer_id=reviewer.pk,
        decision=decision,
        rating=rating or "",
    )

    role = reviewer.role_in(application.company)
    at_current_stage = application.current_stage_id == stage.id
    if (
        application.status == Application.ACTIVE
        and at_current_stage
        and role in ADVANCING_ROLES
    ):
        if decision == StageReview.PASS:
            advance_application(application)
        elif decision == StageReview.FAIL:
            reject_application(application)
    return review
