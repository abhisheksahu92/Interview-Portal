"""Plan/subscription helpers shared by views, signals, usage and limits."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from billing.models import Plan, Subscription

# Canonical tier definitions; mirrored by the seed data migration.
PLAN_SPECS = {
    Plan.FREE: {
        "name": "Free",
        "max_open_jobs": 1,
        "max_seats": 2,
        "ai_credits_monthly": 0,
        "price_monthly": Decimal("0.00"),
        "price_monthly_inr": Decimal("0.00"),
        "price_yearly_inr": Decimal("0.00"),
        "features": {},
    },
    Plan.STARTER: {
        "name": "Starter",
        "max_open_jobs": 3,
        "max_seats": 3,
        "ai_credits_monthly": 50,
        "price_monthly": Decimal("19.00"),
        "price_monthly_inr": Decimal("1499.00"),
        "price_yearly_inr": Decimal("14990.00"),
        "features": {"analytics": True},
    },
    Plan.GROWTH: {
        "name": "Growth",
        "max_open_jobs": 25,
        "max_seats": 10,
        "ai_credits_monthly": 500,
        "price_monthly": Decimal("59.00"),
        "price_monthly_inr": Decimal("4999.00"),
        "price_yearly_inr": Decimal("49990.00"),
        "features": {
            "analytics": True,
            "scheduling": True,
            "careers_page": True,
            "offers": True,
            "whatsapp": True,
            "ai_extraction": True,
        },
    },
    Plan.AGENCY: {
        "name": "Agency",
        "max_open_jobs": 200,
        "max_seats": 50,
        "ai_credits_monthly": 2000,
        "price_monthly": Decimal("149.00"),
        "price_monthly_inr": Decimal("12999.00"),
        "price_yearly_inr": Decimal("129990.00"),
        "per_hire_fee_inr": None,
        "features": {
            "analytics": True,
            "scheduling": True,
            "careers_page": True,
            "offers": True,
            "whatsapp": True,
            "client_portal": True,
            "video": True,
            "api": True,
            "talent_pool_search": True,
            "marketplace": True,
            "white_label": True,
            "ai_extraction": True,
        },
    },
}


def _plan(code):
    """Fetch (or create on demand, so tests never depend on fixtures) a tier."""
    defaults = dict(PLAN_SPECS[code])
    plan, _ = Plan.objects.get_or_create(code=code, defaults=defaults)
    return plan


def free_plan():
    return _plan(Plan.FREE)


def starter_plan():
    return _plan(Plan.STARTER)


def growth_plan():
    return _plan(Plan.GROWTH)


def agency_plan():
    return _plan(Plan.AGENCY)


def trial_plan():
    """The plan a company is entitled to during its 14-day trial."""
    return agency_plan()


def pro_plan():
    """Legacy PRO tier (kept so old Stripe flows and data keep working)."""
    plan, _ = Plan.objects.get_or_create(
        code=Plan.PRO,
        defaults={
            "name": "Pro",
            "max_open_jobs": 25,
            "max_seats": 10,
            "ai_credits_monthly": 500,
            "price_monthly": Decimal("49.00"),
            "price_monthly_inr": Decimal("4999.00"),
            "price_yearly_inr": Decimal("49990.00"),
            "features": dict(PLAN_SPECS[Plan.GROWTH]["features"]),
        },
    )
    return plan


def sellable_plans():
    """The tiers shown on the plan-comparison table, cheapest first."""
    return list(
        Plan.objects.filter(code__in=Plan.PAID_CODES).order_by("price_monthly_inr")
    )


def plan_by_code(code):
    return Plan.objects.filter(code=code).first()


def trial_end_from(moment=None):
    return (moment or timezone.now()) + timedelta(days=Subscription.TRIAL_DAYS)


def get_subscription(company):
    """Return ``company``'s subscription, lazily creating a trialing one."""
    subscription = Subscription.objects.filter(company=company).select_related("plan").first()
    if subscription is None:
        subscription = Subscription.objects.create(
            company=company,
            plan=free_plan(),
            status=Subscription.TRIALING,
            trial_ends_at=trial_end_from(),
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
    """Move a subscription to ``plan`` and persist any extra provider fields."""
    subscription.plan = plan
    for key, value in fields.items():
        setattr(subscription, key, value)
    subscription.save()
    return subscription
