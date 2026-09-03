"""Shared fixtures for the scheduling tests.

Nothing here touches the network: calendar adapters are unconfigured by default
and every provider call is patched where a test needs one.
"""

from datetime import date, time, timedelta

import pytest
from django.utils import timezone as dj_timezone

from billing.models import Plan, Subscription
from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job, PipelineStage
from scheduling.models import InterviewerAvailability

WEEKDAYS_MON_FRI = (0, 1, 2, 3, 4)


def _paid_plan():
    """A plan whose feature flags include ``scheduling``."""
    plan = Plan.objects.exclude(code=Plan.FREE).order_by("-price_monthly").first()
    if plan is None:
        plan = Plan.objects.create(code="PRO", name="Pro", max_open_jobs=100)
    features = dict(plan.features or {})
    features["scheduling"] = True
    plan.features = features
    plan.save(update_fields=["features"])
    return plan


@pytest.fixture
def company(db):
    company = Company.objects.create(name="Acme Staffing")
    Subscription.objects.update_or_create(
        company=company,
        defaults={
            "plan": _paid_plan(),
            "status": Subscription.TRIALING,
            "trial_ends_at": dj_timezone.now() + timedelta(days=7),
        },
    )
    return company


@pytest.fixture
def free_company(db):
    """A company on the FREE plan — no ``scheduling`` entitlement."""
    company = Company.objects.create(name="Frugal Hiring")
    plan, _ = Plan.objects.get_or_create(
        code=Plan.FREE, defaults={"name": "Free", "max_open_jobs": 1}
    )
    plan.features = {}
    plan.save(update_fields=["features"])
    Subscription.objects.update_or_create(
        company=company,
        defaults={
            "plan": plan,
            "status": Subscription.ACTIVE,
            # An expired trial, so the FREE flag set really applies.
            "trial_ends_at": dj_timezone.now() - timedelta(days=1),
        },
    )
    return company


def _member(company, email, role):
    user = User.objects.create_user(email=email, password="pw12345678")
    Membership.objects.create(user=user, company=company, role=role)
    return user


@pytest.fixture
def owner(company):
    return _member(company, "owner@acme.test", Membership.OWNER)


@pytest.fixture
def interviewer(company):
    return _member(company, "iv@acme.test", Membership.INTERVIEWER)


@pytest.fixture
def other_interviewer(company):
    return _member(company, "iv2@acme.test", Membership.INTERVIEWER)


@pytest.fixture
def candidate(db):
    user = User.objects.create_user(
        email="candidate@example.test", password="pw12345678", is_candidate=True
    )
    return CandidateProfile.objects.create(user=user, experience_years=3)


@pytest.fixture
def job(company, owner):
    return Job.objects.create(
        company=company, title="Python Engineer", status=Job.OPEN, created_by=owner
    )


@pytest.fixture
def screening_stage(job):
    return job.stages.get(kind=PipelineStage.SCREENING)


@pytest.fixture
def interview_stage(job):
    return job.stages.filter(kind=PipelineStage.INTERVIEW).order_by("order").first()


@pytest.fixture
def application(job, candidate, screening_stage):
    return Application.objects.create(
        job=job, candidate=candidate, current_stage=screening_stage
    )


@pytest.fixture
def weekday_availability(company, interviewer):
    """Mon–Fri 09:00–17:00 UTC for ``interviewer``."""

    def _make(user=None, tz="UTC", start=time(9, 0), end=time(17, 0), weekdays=None):
        weekdays = WEEKDAYS_MON_FRI if weekdays is None else weekdays
        user = user or interviewer
        return [
            InterviewerAvailability.objects.create(
                company=company,
                user=user,
                weekday=weekday,
                start=start,
                end=end,
                timezone=tz,
            )
            for weekday in weekdays
        ]

    return _make


@pytest.fixture
def next_monday():
    """The next Monday strictly after today, as a date."""
    today = dj_timezone.now().date()
    return date.fromordinal(today.toordinal() + (7 - today.weekday()))
