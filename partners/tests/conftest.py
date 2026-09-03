import pytest

from billing.models import Plan, Subscription
from core.models import Company, Membership, User


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme Staffing")


@pytest.fixture
def owner(company):
    user = User.objects.create_user(email="owner@partners.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    return user


@pytest.fixture
def pro(company):
    """Put ``company`` on a plan with every feature flag switched on."""
    from billing.entitlements import FEATURES

    plan = Plan.objects.get(code=Plan.PRO)
    plan.features = dict.fromkeys(FEATURES, True)
    plan.save(update_fields=["features"])
    Subscription.objects.update_or_create(
        company=company, defaults={"plan": plan, "status": Subscription.ACTIVE}
    )
    company.refresh_from_db()
    return company


@pytest.fixture
def expired_trial(company):
    """End the 14-day trial so only FREE-plan features remain."""
    from datetime import timedelta

    from django.utils import timezone

    Subscription.objects.update_or_create(
        company=company,
        defaults={
            "plan": Plan.objects.get(code=Plan.FREE),
            "status": Subscription.ACTIVE,
            "trial_ends_at": timezone.now() - timedelta(days=1),
        },
    )
    company.refresh_from_db()
    return company
