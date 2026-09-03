from datetime import timedelta

import pytest
from django.utils import timezone

from billing.models import Plan, Subscription
from core.models import Company, Membership, User
from jobs.models import CandidateProfile, Job


@pytest.fixture(autouse=True)
def _locmem_mail(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.SITE_URL = "https://portal.test"
    from django.core import mail

    mail.outbox.clear()
    yield
    mail.outbox.clear()


@pytest.fixture
def company(db):
    """A company past its full-featured trial, so only email is on by default."""
    company = Company.objects.create(name="Acme Staffing")
    subscription = getattr(company, "subscription", None)
    if subscription is not None:
        subscription.trial_ends_at = timezone.now() - timedelta(days=1)
        subscription.plan = Plan.objects.get_or_create(
            code=Plan.FREE, defaults={"name": "Free", "features": {}}
        )[0]
        subscription.save()
    company._state.fields_cache.clear()
    return company


@pytest.fixture
def owner(company):
    user = User.objects.create_user(email="owner@notifications.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    return user


@pytest.fixture
def interviewer(company):
    user = User.objects.create_user(email="int@notifications.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.INTERVIEWER)
    return user


@pytest.fixture
def job(company):
    return Job.objects.create(company=company, title="Django Dev", status=Job.OPEN)


@pytest.fixture
def candidate(db):
    user = User.objects.create_user(
        email="cand@notifications.test", password="pw12345678", is_candidate=True
    )
    return CandidateProfile.objects.create(
        user=user, experience_years=3, phone="+91 98765 43210"
    )


@pytest.fixture
def whatsapp_company(company):
    """A company on a plan that includes the whatsapp feature."""
    plan, _ = Plan.objects.get_or_create(
        code=Plan.GROWTH, defaults={"name": "Growth", "features": {"whatsapp": True}}
    )
    plan.features = dict(plan.features or {}, whatsapp=True)
    plan.save(update_fields=["features"])
    Subscription.objects.update_or_create(
        company=company, defaults={"plan": plan, "status": Subscription.ACTIVE}
    )
    company._state.fields_cache.clear()
    return company


@pytest.fixture
def whatsapp_env(settings):
    settings.WHATSAPP_TOKEN = "test-token"
    settings.WHATSAPP_PHONE_ID = "1234567890"
    return settings
