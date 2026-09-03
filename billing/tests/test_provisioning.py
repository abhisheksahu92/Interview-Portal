"""Automatic provisioning of subscriptions for new companies."""

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from billing.models import Plan, Subscription
from core.models import Company
from jobs.models import Job


def test_company_creation_provisions_a_trial_subscription(db):
    company = Company.objects.create(name="Brand New Ltd")
    subscription = Subscription.objects.get(company=company)
    assert subscription.plan.code == Plan.FREE
    assert subscription.status == Subscription.TRIALING
    assert subscription.in_trial is True
    assert 13 <= subscription.trial_days_left <= 14


def test_trial_limits_apply_from_the_first_day(db):
    """A trialling company is metered against the trial tier, not FREE."""
    company = Company.objects.create(name="Day One Ltd")  # billed on FREE, trialling
    for i in range(3):
        Job.objects.create(company=company, title=f"Dev {i}", status=Job.OPEN)
    assert Job.objects.filter(company=company, status=Job.OPEN).count() == 3


def test_free_limits_bite_once_the_trial_ends(db):
    """No manual provisioning step: the plan limit bites the moment it applies."""
    from datetime import timedelta

    from django.utils import timezone

    company = Company.objects.create(name="Day Fifteen Ltd")
    Subscription.objects.filter(company=company).update(
        status=Subscription.ACTIVE, trial_ends_at=timezone.now() - timedelta(days=1)
    )
    company.refresh_from_db()
    Job.objects.create(company=company, title="Dev 1", status=Job.OPEN)
    with pytest.raises(ValidationError):
        Job.objects.create(company=company, title="Dev 2", status=Job.OPEN)


def test_saving_a_company_again_does_not_duplicate_the_subscription(db):
    company = Company.objects.create(name="Rename Ltd")
    company.name = "Renamed Ltd"
    company.save()
    assert Subscription.objects.filter(company=company).count() == 1


@pytest.mark.django_db
def test_seed_demo_upgrades_the_demo_company_to_a_paid_plan():
    call_command("seed_demo", verbosity=0)
    subscription = Subscription.objects.get(company__name="Demo Staffing")
    assert subscription.plan.code != Plan.FREE
    assert subscription.plan.max_open_jobs != 1
    assert subscription.status == Subscription.ACTIVE
    # A paid plan's headroom means the demo's two open jobs are fine
    assert Job.objects.filter(company=subscription.company, status=Job.OPEN).count() >= 2
