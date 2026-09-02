import pytest
from django.core.exceptions import ValidationError

from billing.limits import can_open_job, usage
from billing.models import Plan, Subscription
from billing.services import get_subscription, pro_plan
from jobs.models import Job


def test_free_subscription_is_created_lazily(company):
    assert not Subscription.objects.filter(company=company).exists()
    subscription = get_subscription(company)
    assert subscription.plan.code == Plan.FREE
    assert subscription.plan.max_open_jobs == 1
    assert subscription.status == Subscription.ACTIVE
    # idempotent
    assert get_subscription(company).pk == subscription.pk


def test_seed_migration_created_both_plans(db):
    assert Plan.objects.get(code=Plan.FREE).max_open_jobs == 1
    pro = Plan.objects.get(code=Plan.PRO)
    assert pro.max_open_jobs == 25
    assert pro.price_monthly == 49


def test_first_open_job_allowed_second_blocked(company):
    get_subscription(company)
    Job.objects.create(company=company, title="Dev 1", status=Job.OPEN)

    allowed, reason = can_open_job(company)
    assert allowed is False
    assert "Free plan allows 1 open job" in reason

    with pytest.raises(ValidationError) as exc:
        Job.objects.create(company=company, title="Dev 2", status=Job.OPEN)
    assert "status" in exc.value.message_dict


def test_draft_jobs_are_never_blocked(company):
    get_subscription(company)
    Job.objects.create(company=company, title="Dev 1", status=Job.OPEN)
    job = Job.objects.create(company=company, title="Dev 2", status=Job.DRAFT)
    assert job.pk


def test_publishing_a_draft_beyond_the_limit_is_blocked(company):
    get_subscription(company)
    Job.objects.create(company=company, title="Dev 1", status=Job.OPEN)
    job = Job.objects.create(company=company, title="Dev 2", status=Job.DRAFT)
    job.status = Job.OPEN
    with pytest.raises(ValidationError):
        job.save()


def test_editing_an_already_open_job_is_not_blocked(company):
    get_subscription(company)
    job = Job.objects.create(company=company, title="Dev 1", status=Job.OPEN)
    job.title = "Senior Dev"
    job.save()
    job.refresh_from_db()
    assert job.title == "Senior Dev"


def test_pro_plan_allows_more_open_jobs(company):
    subscription = get_subscription(company)
    subscription.plan = pro_plan()
    subscription.save()

    for i in range(5):
        Job.objects.create(company=company, title=f"Dev {i}", status=Job.OPEN)

    allowed, reason = can_open_job(company)
    assert allowed is True
    assert reason == ""
    assert Job.objects.filter(company=company, status=Job.OPEN).count() == 5


def test_unmetered_company_is_not_blocked(company):
    """A company with no billing record predates billing and is left alone."""
    Job.objects.create(company=company, title="Dev 1", status=Job.OPEN)
    job = Job.objects.create(company=company, title="Dev 2", status=Job.OPEN)
    assert job.pk


def test_provision_subscriptions_command_meters_existing_companies(company):
    from django.core.management import call_command

    call_command("provision_subscriptions", verbosity=0)
    subscription = Subscription.objects.get(company=company)
    assert subscription.plan.code == Plan.FREE


def test_canceled_pro_subscription_falls_back_to_free_limits(company):
    subscription = get_subscription(company)
    subscription.plan = pro_plan()
    subscription.status = Subscription.CANCELED
    subscription.save()

    Job.objects.create(company=company, title="Dev 1", status=Job.OPEN)
    allowed, _ = can_open_job(company)
    assert allowed is False


def test_closing_a_job_frees_a_slot(company):
    job = Job.objects.create(company=company, title="Dev 1", status=Job.OPEN)
    job.status = Job.CLOSED
    job.save()
    allowed, _ = can_open_job(company)
    assert allowed is True


def test_usage_snapshot(company):
    Job.objects.create(company=company, title="Dev 1", status=Job.OPEN)
    data = usage(company)
    assert data["open_jobs"] == 1
    assert data["max_open_jobs"] == 1
    assert data["remaining"] == 0
    assert data["at_limit"] is True


def test_can_open_job_without_company():
    allowed, reason = can_open_job(None)
    assert allowed is False
    assert reason
