"""Shared fixtures for the offers test suite."""

import pytest
from django.utils import timezone

from billing.models import Plan, Subscription
from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job


def grant_offers(company, enabled=True):
    """Give ``company`` a plan whose features include (or exclude) ``offers``."""
    plan, _ = Plan.objects.get_or_create(
        code=Plan.PRO if enabled else Plan.FREE,
        defaults={
            "name": "Pro" if enabled else "Free",
            "max_open_jobs": 25 if enabled else 1,
        },
    )
    plan.features = {"offers": enabled}
    plan.save(update_fields=["features"])
    defaults = {"plan": plan, "status": Subscription.ACTIVE}
    if hasattr(Subscription, "trial_ends_at"):
        # A company inside its 14-day trial gets every flag, so an "off" plan
        # only bites once the trial window has closed.
        defaults["trial_ends_at"] = timezone.now() - timezone.timedelta(days=1)
    Subscription.objects.update_or_create(company=company, defaults=defaults)
    return plan


@pytest.fixture
def company(db):
    company = Company.objects.create(name="Acme Staffing")
    grant_offers(company)
    return company


@pytest.fixture
def other_company(db):
    company = Company.objects.create(name="Rival Staffing")
    grant_offers(company)
    return company


@pytest.fixture
def recruiter(company):
    user = User.objects.create_user(
        email="recruiter@offers.test", password="pw12345678", first_name="Riya"
    )
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    return user


@pytest.fixture
def candidate(db):
    user = User.objects.create_user(
        email="asha@offers.test", password="pw12345678", first_name="Asha", last_name="Rao"
    )
    return CandidateProfile.objects.create(user=user, phone="+91 99999 11111")


def make_application(company, candidate, title="Senior Python Engineer"):
    job = Job.objects.create(
        company=company, title=title, location="Bengaluru", status=Job.OPEN
    )
    return Application.objects.create(
        job=job, candidate=candidate, current_stage=job.stages.last()
    )


@pytest.fixture
def application(company, candidate):
    return make_application(company, candidate)


@pytest.fixture
def draft_offer(application, recruiter):
    from offers.models import Offer, OfferTemplate
    from offers.services import render_offer

    offer = Offer.objects.create(
        application=application,
        template=OfferTemplate.default_for(application.job.company),
        salary=1800000,
        currency="INR",
        joining_date=timezone.localdate() + timezone.timedelta(days=30),
        expires_at=timezone.now() + timezone.timedelta(days=7),
        created_by=recruiter,
    )
    render_offer(offer, save=True)
    return offer
