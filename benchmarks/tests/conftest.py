"""Fixtures for the benchmark tests.

The suite builds offers with *known* salaries so the percentile assertions are
exact rather than approximate. ``analytics`` is the gating flag (benchmarks are
part of the analytics tier), granted by writing it into the plan's features
JSON — the same thing ``has_feature`` reads.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from billing.models import Plan, Subscription
from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job, Skill
from offers.models import Offer

FEATURE = "analytics"


def enable_analytics(company, enabled=True):
    plan, _ = Plan.objects.get_or_create(
        code="GROWTH" if enabled else "FREE",
        defaults={"name": "Growth" if enabled else "Free"},
    )
    plan.features = {**(plan.features or {}), FEATURE: enabled}
    plan.save(update_fields=["features"])
    defaults = {"plan": plan, "status": Subscription.ACTIVE}
    if any(f.name == "trial_ends_at" for f in Subscription._meta.get_fields()):
        defaults["trial_ends_at"] = None
    Subscription.objects.update_or_create(company=company, defaults=defaults)
    return plan


def _member(company, email, role):
    user = User.objects.create_user(email=email, password="pw12345678")
    Membership.objects.create(user=user, company=company, role=role)
    return user


@pytest.fixture
def company(db):
    company = Company.objects.create(name="Acme Staffing")
    enable_analytics(company)
    return company


@pytest.fixture
def other_company(db):
    company = Company.objects.create(name="Globex Tech")
    enable_analytics(company)
    return company


@pytest.fixture
def owner(company):
    return _member(company, "owner@acme.test", Membership.OWNER)


@pytest.fixture
def interviewer(company):
    return _member(company, "int@acme.test", Membership.INTERVIEWER)


@pytest.fixture
def make_offer(db):
    """Create one ACCEPTED offer with an exactly known annual salary."""
    counter = {"n": 0}

    def factory(
        company,
        salary,
        *,
        skill="Python",
        location="Pune, MH",
        experience_years="4.0",
        period=Job.YEAR,
        status=Offer.ACCEPTED,
        currency="INR",
        signed_at=None,
    ):
        counter["n"] += 1
        index = counter["n"]
        job = Job.objects.create(
            company=company,
            title=f"Role {index}",
            location=location,
            salary_period=period,
        )
        if skill:
            job.skills.add(Skill.objects.get_or_create(company=company, name=skill)[0])
        user = User.objects.create_user(email=f"cand{index}@example.test", password="pw12345678")
        profile = CandidateProfile.objects.create(
            user=user, experience_years=Decimal(experience_years)
        )
        application = Application.objects.create(job=job, candidate=profile)
        return Offer.objects.create(
            application=application,
            salary=Decimal(str(salary)),
            currency=currency,
            status=status,
            signed_at=signed_at or timezone.now(),
        )

    return factory


@pytest.fixture
def five_python_offers(company, make_offer):
    """Salaries 10, 12, 14, 16, 18 lakh — p25=12L, median=14L, p75=16L."""
    for salary in (1000000, 1200000, 1400000, 1600000, 1800000):
        make_offer(company, salary)
    return company
