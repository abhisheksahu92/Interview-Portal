"""Deterministic analytics fixtures.

The metric fixtures rewrite the signal-recorded history with explicit timestamps
so every median in the tests is an exact, hand-checkable number. Signal
behaviour itself is covered by ``test_transitions.py``.
"""

import datetime as dt
from types import SimpleNamespace

import pytest
from django.utils import timezone

from analytics.models import StageTransition
from assessments.models import Assessment, Attempt
from billing.models import Plan, Subscription
from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job, PipelineStage, StageReview


def _plan(code, features):
    plan, _ = Plan.objects.get_or_create(
        code=code, defaults={"name": code.title(), "max_open_jobs": 50}
    )
    plan.features = features
    plan.save(update_fields=["features"])
    return plan


def entitle(company, analytics=True):
    """Give ``company`` a usable subscription with/without the analytics flag."""
    if analytics:
        plan = _plan(Plan.AGENCY, {"analytics": True})
    else:
        plan = _plan(Plan.FREE, {})
    subscription, _ = Subscription.objects.update_or_create(
        company=company, defaults={"plan": plan, "status": Subscription.ACTIVE}
    )
    if hasattr(subscription, "trial_ends_at"):
        # Expire any trial so the FREE case really is un-entitled.
        subscription.trial_ends_at = timezone.now() - dt.timedelta(days=1)
        subscription.save(update_fields=["trial_ends_at"])
    return subscription


def make_candidate(email):
    user = User.objects.create_user(email=email, password="pw12345678", is_candidate=True)
    return CandidateProfile.objects.create(user=user, experience_years=3)


def stage(job, kind, order):
    return job.stages.get(order=order, kind=kind)


@pytest.fixture
def data(db):
    """A company with two open jobs and four applications with known history."""
    company = Company.objects.create(name="Acme Staffing")
    entitle(company)

    owner = User.objects.create_user(email="owner@analytics.test", password="pw12345678")
    recruiter = User.objects.create_user(email="rec@analytics.test", password="pw12345678")
    interviewer = User.objects.create_user(email="int@analytics.test", password="pw12345678")
    Membership.objects.create(user=owner, company=company, role=Membership.OWNER)
    Membership.objects.create(user=recruiter, company=company, role=Membership.RECRUITER)
    Membership.objects.create(
        user=interviewer, company=company, role=Membership.INTERVIEWER
    )

    job_a = Job.objects.create(company=company, title="Backend Engineer", status=Job.OPEN)
    job_b = Job.objects.create(company=company, title="QA Analyst", status=Job.OPEN)

    screening = stage(job_a, PipelineStage.SCREENING, 1)
    assessment_stage = stage(job_a, PipelineStage.ASSESSMENT, 2)
    l1 = stage(job_a, PipelineStage.INTERVIEW, 3)
    b_screening = stage(job_b, PipelineStage.SCREENING, 1)

    base = timezone.now() - dt.timedelta(days=30)

    def application(job, email, current_stage, status, fit, created_offset=0):
        app = Application.objects.create(
            job=job,
            candidate=make_candidate(email),
            current_stage=current_stage,
            status=status,
            ai_fit_score=fit,
        )
        Application.objects.filter(pk=app.pk).update(
            created_at=base + dt.timedelta(days=created_offset),
            updated_at=base + dt.timedelta(days=created_offset + 1),
        )
        app.refresh_from_db()
        return app

    hired = application(job_a, "hired@c.test", l1, Application.HIRED, 80)
    rejected = application(job_a, "rejected@c.test", assessment_stage, Application.REJECTED, 60)
    active = application(job_a, "active@c.test", screening, Application.ACTIVE, 40)
    other_job = application(job_b, "other@c.test", b_screening, Application.ACTIVE, None)

    # Replace signal history with an exact, hand-built timeline.
    StageTransition.objects.all().delete()

    def transition(app, to_stage, status, day):
        return StageTransition.objects.create(
            application=app,
            from_stage=None,
            to_stage=to_stage,
            status_after=status,
            at=base + dt.timedelta(days=day),
        )

    transition(hired, screening, Application.ACTIVE, 0)
    transition(hired, assessment_stage, Application.ACTIVE, 2)
    transition(hired, l1, Application.ACTIVE, 5)
    transition(hired, l1, Application.HIRED, 10)

    transition(rejected, screening, Application.ACTIVE, 0)
    transition(rejected, assessment_stage, Application.ACTIVE, 3)
    transition(rejected, assessment_stage, Application.REJECTED, 4)

    transition(active, screening, Application.ACTIVE, 0)
    transition(other_job, b_screening, Application.ACTIVE, 0)

    StageReview.objects.create(
        application=hired, stage=l1, reviewer=interviewer,
        decision=StageReview.PASS, rating=4,
    )
    StageReview.objects.create(
        application=rejected, stage=assessment_stage, reviewer=interviewer,
        decision=StageReview.FAIL, rating=2,
    )

    quiz = Assessment.objects.create(job=job_a, stage=assessment_stage, title="Python basics")
    Attempt.objects.create(
        assessment=quiz, application=hired, submitted_at=base + dt.timedelta(days=2),
        score_percent=90, passed=True,
    )
    Attempt.objects.create(
        assessment=quiz, application=rejected, submitted_at=base + dt.timedelta(days=3),
        score_percent=30, passed=False,
    )

    return SimpleNamespace(
        company=company,
        owner=owner,
        recruiter=recruiter,
        interviewer=interviewer,
        job_a=job_a,
        job_b=job_b,
        screening=screening,
        assessment_stage=assessment_stage,
        l1=l1,
        hired=hired,
        rejected=rejected,
        active=active,
        other_job=other_job,
        quiz=quiz,
        base=base,
        date_from=(base - dt.timedelta(days=1)).date(),
        date_to=timezone.localdate() + dt.timedelta(days=1),
    )
