"""Trial companies get the trial tier's *limits*, not just its feature flags."""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from billing import usage as usage_module
from billing.limits import can_open_job
from billing.models import Plan, Subscription
from billing.services import get_subscription
from jobs.models import Job

pytestmark = pytest.mark.django_db


def test_trial_company_may_open_more_than_one_job(trial_company):
    subscription = get_subscription(trial_company)
    assert subscription.effective_plan.code == Plan.AGENCY
    assert subscription.max_open_jobs == Plan.objects.get(code=Plan.AGENCY).max_open_jobs

    for i in range(3):
        Job.objects.create(company=trial_company, title=f"Dev {i}", status=Job.OPEN)
    allowed, reason = can_open_job(trial_company)
    assert allowed is True and reason == ""


def test_expired_trial_is_capped_at_the_free_limit(trial_company):
    Job.objects.create(company=trial_company, title="Dev 1", status=Job.OPEN)
    Subscription.objects.filter(company=trial_company).update(
        trial_ends_at=timezone.now() - timedelta(minutes=1)
    )
    trial_company.refresh_from_db()

    subscription = get_subscription(trial_company)
    assert subscription.max_open_jobs == 1
    allowed, reason = can_open_job(trial_company)
    assert allowed is False
    assert "Free plan allows 1 open job" in reason
    with pytest.raises(ValidationError):
        Job.objects.create(company=trial_company, title="Dev 2", status=Job.OPEN)


def test_trial_quotas_follow_the_trial_plan(trial_company):
    agency = Plan.objects.get(code=Plan.AGENCY)
    subscription = get_subscription(trial_company)
    assert subscription.ai_credits_monthly == agency.ai_credits_monthly
    assert usage_module.quota(trial_company, usage_module.AI_SCREEN) == agency.ai_credits_monthly
    assert usage_module.quota(trial_company, usage_module.VIDEO_MINUTE) > 0


def test_cancelled_paid_subscription_drops_to_free_limits(company):
    subscription = get_subscription(company)
    subscription.plan = Plan.objects.get(code=Plan.AGENCY)
    subscription.status = Subscription.CANCELED
    subscription.save()
    company.refresh_from_db()
    assert subscription.max_open_jobs == 1
    assert subscription.max_seats == Plan.objects.get(code=Plan.FREE).max_seats
