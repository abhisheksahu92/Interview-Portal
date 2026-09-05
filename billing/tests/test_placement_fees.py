"""Per-hire placement fees, created when an application is marked HIRED."""

from decimal import Decimal

import pytest

from billing.models import PlacementFee, Plan, Subscription
from core.models import User
from jobs.models import Application, CandidateProfile, Job

pytestmark = pytest.mark.django_db


def _application(company):
    job = Job.objects.create(company=company, title="Python Dev", status=Job.DRAFT)
    user = User.objects.create_user(email="cand@example.test", password="pw12345678")
    candidate = CandidateProfile.objects.create(user=user, experience_years=Decimal("3.0"))
    return Application.objects.create(job=job, candidate=candidate)


def _plan_with_fee(company, amount):
    plan = Plan.objects.get(code=Plan.AGENCY)
    plan.per_hire_fee_inr = Decimal(amount)
    plan.save(update_fields=["per_hire_fee_inr"])
    Subscription.objects.update_or_create(
        company=company, defaults={"plan": plan, "status": Subscription.ACTIVE}
    )
    company.refresh_from_db()
    return plan


def test_no_fee_when_the_plan_has_none(company):
    """The legacy FREE tier carries neither a success fee nor a per-hire fee."""
    application = _application(company)
    application.status = Application.HIRED
    application.save()
    assert PlacementFee.objects.count() == 0


def test_fee_created_on_hire(company):
    _plan_with_fee(company, "25000.00")
    application = _application(company)
    application.status = Application.HIRED
    application.save()
    fee = PlacementFee.objects.get(application=application)
    assert fee.company_id == company.pk
    assert fee.amount == Decimal("25000.00")
    assert fee.status == PlacementFee.PENDING


def test_fee_is_created_only_once(company):
    _plan_with_fee(company, "25000.00")
    application = _application(company)
    application.status = Application.HIRED
    application.save()
    application.save()
    assert PlacementFee.objects.filter(application=application).count() == 1


def test_placement_fees_are_listed_on_the_overview(client, owner, company):
    _plan_with_fee(company, "25000.00")
    application = _application(company)
    application.status = Application.HIRED
    application.save()
    client.force_login(owner)
    response = client.get("/billing/")
    assert response.status_code == 200
    assert len(response.context["placement_fees"]) == 1
    assert b"Placement fees" in response.content
