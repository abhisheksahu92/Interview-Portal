"""Plan/subscription helpers shared by views, signals and limits."""

from billing.models import Plan, Subscription


def free_plan():
    """The FREE plan row, created on demand so tests never depend on fixtures."""
    plan, _ = Plan.objects.get_or_create(
        code=Plan.FREE,
        defaults={"name": "Free", "max_open_jobs": 1, "price_monthly": 0},
    )
    return plan


def pro_plan():
    plan, _ = Plan.objects.get_or_create(
        code=Plan.PRO,
        defaults={"name": "Pro", "max_open_jobs": 25, "price_monthly": 49},
    )
    return plan


def get_subscription(company):
    """Return ``company``'s subscription, lazily creating a FREE one."""
    subscription = Subscription.objects.filter(company=company).select_related("plan").first()
    if subscription is None:
        subscription = Subscription.objects.create(
            company=company, plan=free_plan(), status=Subscription.ACTIVE
        )
    return subscription


def open_job_count(company, exclude_pk=None):
    """How many jobs the company currently has in OPEN status."""
    from jobs.models import Job

    qs = Job.objects.filter(company=company, status=Job.OPEN)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.count()


def set_plan(subscription, plan, **fields):
    """Move a subscription to ``plan`` and persist any extra Stripe fields."""
    subscription.plan = plan
    for key, value in fields.items():
        setattr(subscription, key, value)
    subscription.save()
    return subscription
