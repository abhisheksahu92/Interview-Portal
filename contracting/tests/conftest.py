"""Fixtures for the contracting tests.

The ``contracting`` flag may not exist in ``billing.entitlements.FEATURES``
while the billing app is being reshaped in parallel, so
:func:`enable_contracting` grants it by writing the key straight into the plan's
``features`` JSON — which is what ``has_feature`` reads either way. A *paid*
plan is used in both directions so the 14-day trial (which grants everything)
cannot mask the disabled case.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from billing.models import Plan, Subscription
from clients.models import Client, ClientAccess
from contracting.models import Contractor, Engagement, Timesheet
from core.models import Company, Membership, User

FEATURE = "contracting"


def enable_contracting(company, enabled=True):
    plan, _ = Plan.objects.get_or_create(
        code="GROWTH" if enabled else "STARTER",
        defaults={"name": "Growth" if enabled else "Starter"},
    )
    plan.features = {**(plan.features or {}), FEATURE: enabled, "client_portal": True}
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
    enable_contracting(company)
    return company


@pytest.fixture
def other_company(db):
    company = Company.objects.create(name="Globex Tech")
    enable_contracting(company)
    return company


@pytest.fixture
def owner(company):
    return _member(company, "owner@acme.test", Membership.OWNER)


@pytest.fixture
def interviewer(company):
    return _member(company, "int@acme.test", Membership.INTERVIEWER)


@pytest.fixture
def other_owner(other_company):
    return _member(other_company, "owner@globex.test", Membership.OWNER)


@pytest.fixture
def make_client_row(db):
    def factory(company, name="Initech"):
        return Client.objects.create(
            company=company, name=name, contact_email="ap@initech.test"
        )

    return factory


@pytest.fixture
def client_row(company, make_client_row):
    return make_client_row(company)


@pytest.fixture
def access(client_row):
    return ClientAccess.objects.create(client=client_row, email="ap@initech.test")


@pytest.fixture
def make_contractor(db):
    def factory(company, name="Ravi Kumar", **kwargs):
        fields = {
            "email": "ravi@example.test",
            "pan": "ABCDE1234F",
            "bank": {"account_number": "12345678901", "ifsc": "HDFC0000123"},
            "status": Contractor.ACTIVE,
        }
        fields.update(kwargs)
        return Contractor.objects.create(company=company, name=name, **fields)

    return factory


@pytest.fixture
def contractor(company, make_contractor):
    return make_contractor(company)


@pytest.fixture
def make_engagement(db):
    def factory(contractor, client, **kwargs):
        fields = {
            "role_title": "Django Developer",
            "start": date(2026, 4, 1),
            "bill_rate_inr": Decimal("2000"),
            "pay_rate_inr": Decimal("1500"),
            "rate_unit": Engagement.HOUR,
        }
        fields.update(kwargs)
        return Engagement.objects.create(contractor=contractor, client=client, **fields)

    return factory


@pytest.fixture
def engagement(contractor, client_row, make_engagement):
    return make_engagement(contractor, client_row)


@pytest.fixture
def make_timesheet(db):
    def factory(engagement, start=date(2026, 4, 6), days=5, hours=8, **kwargs):
        entries = [
            {"date": (start + timedelta(days=i)).isoformat(), "hours": hours, "note": ""}
            for i in range(days)
        ]
        fields = {
            "period_start": start,
            "period_end": start + timedelta(days=6),
            "entries": entries,
        }
        fields.update(kwargs)
        return Timesheet.objects.create(engagement=engagement, **fields)

    return factory


@pytest.fixture
def timesheet(engagement, make_timesheet):
    return make_timesheet(engagement)


@pytest.fixture(autouse=True)
def _media_root(settings, tmp_path):
    """Keep generated PDFs, CSVs and uploads out of the real MEDIA_ROOT."""
    settings.MEDIA_ROOT = str(tmp_path / "media")
    return settings.MEDIA_ROOT
