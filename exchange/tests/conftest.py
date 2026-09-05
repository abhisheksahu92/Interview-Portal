"""Fixtures for the exchange app: two agencies, a job, and talent to submit."""

import pytest

from billing.models import Plan, Subscription
from core.models import Company, Membership, User
from exchange import services
from exchange.models import ExchangeRequirement, PartnerLink
from jobs.models import Job, Skill
from talent.models import TalentProfile


def _member(company, email, role):
    user = User.objects.create_user(email=email, password="pw12345678")
    Membership.objects.create(user=user, company=company, role=role)
    return user


def set_exchange_feature(company, enabled=True):
    """Put ``company`` on a paid plan whose ``exchange`` flag is ``enabled``.

    A paid plan is used in both directions so the 14-day trial (which grants
    every flag) cannot mask the disabled case.
    """
    plan, _ = Plan.objects.get_or_create(
        code="AGENCY" if enabled else "STARTER",
        defaults={"name": "Agency" if enabled else "Starter"},
    )
    plan.features = {**(plan.features or {}), services.FEATURE: enabled}
    plan.save(update_fields=["features"])
    Subscription.objects.update_or_create(
        company=company,
        defaults={"plan": plan, "status": Subscription.ACTIVE, "trial_ends_at": None},
    )
    return plan


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def requester(db):
    """The agency that publishes requirements (paid, exchange enabled)."""
    company = Company.objects.create(name="Acme Staffing")
    set_exchange_feature(company, True)
    return company


@pytest.fixture
def responder(db):
    """The partner agency that submits candidates (free plan: no publishing)."""
    company = Company.objects.create(name="Globex Talent")
    set_exchange_feature(company, False)
    return company


@pytest.fixture
def outsider(db):
    company = Company.objects.create(name="Initech Hiring")
    set_exchange_feature(company, False)
    return company


@pytest.fixture
def requester_owner(requester):
    return _member(requester, "owner@acme.test", Membership.OWNER)


@pytest.fixture
def responder_owner(responder):
    return _member(responder, "owner@globex.test", Membership.OWNER)


@pytest.fixture
def outsider_owner(outsider):
    return _member(outsider, "owner@initech.test", Membership.OWNER)


@pytest.fixture
def job(requester, requester_owner):
    job = Job.objects.create(
        company=requester,
        title="Senior Django Engineer",
        location="Pune",
        description="Build APIs.",
        status=Job.OPEN,
        created_by=requester_owner,
    )
    job.skills.add(Skill.objects.create(company=requester, name="Django"))
    return job


@pytest.fixture
def partnership(requester, responder, requester_owner):
    link = services.invite_partner(requester, responder, created_by=requester_owner)
    return services.accept_partner(link, responder)


@pytest.fixture
def requirement(job, requester_owner, partnership):
    return services.publish_requirement(
        job,
        created_by=requester_owner,
        client_name="Big Bank Ltd",
        budget_ctc_min=1800000,
        budget_ctc_max=2400000,
        fee_split_pct=50,
    )


@pytest.fixture
def network_requirement(job, requester_owner):
    return services.publish_requirement(
        job,
        created_by=requester_owner,
        client_name="Big Bank Ltd",
        visibility=ExchangeRequirement.NETWORK,
    )


@pytest.fixture
def candidate(responder):
    profile = TalentProfile.objects.create(
        company=responder,
        email="Asha.Rao@example.test",
        name="Asha Rao",
        phone="+91 98765 43210",
        headline="Senior Django Developer",
        location="Pune",
        experience_years=8,
    )
    profile.skills.add(Skill.objects.create(company=responder, name="Django"))
    return profile


@pytest.fixture
def other_candidate(responder):
    return TalentProfile.objects.create(
        company=responder, email="ravi@example.test", name="Ravi Kumar", phone="+91 90000 00000"
    )


@pytest.fixture
def blocked_link(requester, outsider):
    return PartnerLink.objects.create(
        from_company=requester, to_company=outsider, status=PartnerLink.BLOCKED
    )
