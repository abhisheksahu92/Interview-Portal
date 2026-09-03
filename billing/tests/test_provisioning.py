"""Automatic provisioning of subscriptions for new companies."""

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from billing.models import Plan, Subscription
from core.models import Company
from jobs.models import Job


def test_company_creation_provisions_a_free_subscription(db):
    company = Company.objects.create(name="Brand New Ltd")
    subscription = Subscription.objects.get(company=company)
    assert subscription.plan.code == Plan.FREE
    assert subscription.status == Subscription.ACTIVE


def test_limits_apply_from_the_first_day(db):
    """No manual provisioning step: the plan limit bites immediately."""
    company = Company.objects.create(name="Day One Ltd")
    Job.objects.create(company=company, title="Dev 1", status=Job.OPEN)
    with pytest.raises(ValidationError):
        Job.objects.create(company=company, title="Dev 2", status=Job.OPEN)


def test_saving_a_company_again_does_not_duplicate_the_subscription(db):
    company = Company.objects.create(name="Rename Ltd")
    company.name = "Renamed Ltd"
    company.save()
    assert Subscription.objects.filter(company=company).count() == 1


@pytest.mark.django_db
def test_seed_demo_upgrades_the_demo_company_to_pro():
    call_command("seed_demo", verbosity=0)
    subscription = Subscription.objects.get(company__name="Demo Staffing")
    assert subscription.plan.code == Plan.PRO
    assert subscription.status == Subscription.ACTIVE
    # PRO headroom means the demo's two open jobs are fine
    assert Job.objects.filter(company=subscription.company, status=Job.OPEN).count() >= 2
