"""Fixtures for the BGV tests.

The ``bgv`` flag is granted by writing it straight into the plan's ``features``
JSON, which is what ``has_feature`` reads, so these tests do not depend on the
seed migration having run in a particular order. A *paid* plan is used in both
directions because the 14-day trial grants everything and would mask the
disabled case.
"""

from decimal import Decimal

import pytest

from bgv.models import CheckPackage
from billing.models import Plan, Subscription
from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job

FEATURE = "bgv"


def enable_bgv(company, enabled=True):
    plan, _ = Plan.objects.get_or_create(
        code="GROWTH" if enabled else "STARTER",
        defaults={"name": "Growth" if enabled else "Starter"},
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
    enable_bgv(company)
    return company


@pytest.fixture
def other_company(db):
    company = Company.objects.create(name="Globex Tech")
    enable_bgv(company)
    return company


@pytest.fixture
def owner(company):
    return _member(company, "owner@acme.test", Membership.OWNER)


@pytest.fixture
def interviewer(company):
    return _member(company, "int@acme.test", Membership.INTERVIEWER)


@pytest.fixture
def staff_owner(company):
    user = _member(company, "staff@acme.test", Membership.OWNER)
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


@pytest.fixture
def other_owner(other_company):
    return _member(other_company, "owner@globex.test", Membership.OWNER)


@pytest.fixture
def make_candidate(db):
    def factory(email="priya@example.test", years="4.0"):
        user = User.objects.create_user(email=email, password="pw12345678")
        return CandidateProfile.objects.create(user=user, experience_years=Decimal(years))

    return factory


@pytest.fixture
def candidate(make_candidate):
    return make_candidate()


@pytest.fixture
def make_application(db, make_candidate):
    def factory(company, candidate=None, title="Django Developer"):
        job = Job.objects.create(company=company, title=title, location="Pune, MH")
        candidate = candidate or make_candidate(f"c{job.pk}@example.test")
        return Application.objects.create(job=job, candidate=candidate)

    return factory


@pytest.fixture
def application(company, candidate, make_application):
    return make_application(company, candidate)


@pytest.fixture
def package(db):
    return CheckPackage.objects.get_or_create(
        code="STANDARD",
        defaults={
            "name": "Standard",
            "provider_cost_inr": Decimal("999.00"),
            "price_inr": Decimal("1499.00"),
            "checks": ["identity", "address", "employment", "education"],
            "turnaround_days": 5,
        },
    )[0]
