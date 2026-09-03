from datetime import timedelta

import pytest
from django.utils import timezone

from billing.models import Plan, Subscription
from core.models import Company, Membership, User


@pytest.fixture(autouse=True)
def generous_job_limits(db):
    """These tests are about careers pages, not billing's open-job cap."""
    Plan.objects.update(max_open_jobs=100)
    yield
    Plan.objects.update(max_open_jobs=100)


@pytest.fixture
def company(db):
    company = Company.objects.create(name="Acme Staffing")
    Plan.objects.update(max_open_jobs=100)
    return company


@pytest.fixture
def careers_plan(db):
    plan, _ = Plan.objects.get_or_create(
        code=Plan.PRO,
        defaults={"name": "Pro", "max_open_jobs": 100, "price_monthly": 49},
    )
    plan.max_open_jobs = 100
    plan.features = {"careers_page": True}
    plan.save()
    return plan


@pytest.fixture
def free_only(db):
    plan, _ = Plan.objects.get_or_create(
        code=Plan.FREE, defaults={"name": "Free", "max_open_jobs": 100, "price_monthly": 0}
    )
    plan.max_open_jobs = 100
    plan.features = {}
    plan.save()
    return plan


def _subscribe(company, plan):
    """Point the company's subscription (auto-created with the trial) at ``plan``."""
    # trial_ends_at in the past: a FREE plan then really means FREE, not the
    # full-featured 14-day trial billing grants new companies.
    past = timezone.now() - timedelta(days=1)
    defaults = {"plan": plan, "status": Subscription.ACTIVE}
    if hasattr(Subscription, "trial_ends_at"):
        defaults["trial_ends_at"] = past
    Subscription.objects.update_or_create(company=company, defaults=defaults)


@pytest.fixture
def owner(company, careers_plan):
    _subscribe(company, careers_plan)
    user = User.objects.create_user(email="owner@careers.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    return user


@pytest.fixture
def free_owner(db, free_only):
    company = Company.objects.create(name="Thrift Hiring")
    _subscribe(company, free_only)
    user = User.objects.create_user(email="free@careers.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    return user


@pytest.fixture
def site(company):
    from careers.models import CareersSite

    return CareersSite.objects.create(
        company=company,
        headline="Build hiring with us",
        about="We are hiring.\n\n- Remote friendly\n- Great team",
        brand_color="#123456",
        published=True,
        seo_description="Careers at Acme",
    )


@pytest.fixture
def job(company):
    from jobs.models import Job, Skill

    job = Job.objects.create(
        company=company,
        title="Senior Python Engineer",
        location="Pune, Maharashtra, IN",
        description="Build APIs.",
        requirements="5 years Django.",
        status=Job.OPEN,
    )
    job.skills.add(Skill.objects.create(company=company, name="Python"))
    return job
