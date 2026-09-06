import pytest

from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme Staffing")


@pytest.fixture
def listed_company(db):
    """A company that consented to public listing: published + on the network.

    ``/openings/`` and the board both require this pair, so a plain ``company``
    fixture is deliberately invisible to the public surfaces.
    """
    from careers.models import CareersSite

    company = Company.objects.create(name="Listed Staffing")
    CareersSite.objects.create(company=company, published=True, list_in_network=True)
    return company


@pytest.fixture
def other_company(db):
    return Company.objects.create(name="Globex Tech")


def _member(company, email, role):
    user = User.objects.create_user(email=email, password="pw12345678")
    Membership.objects.create(user=user, company=company, role=role)
    return user


@pytest.fixture
def owner(company):
    return _member(company, "owner@acme.test", Membership.OWNER)


@pytest.fixture
def recruiter(company):
    return _member(company, "rec@acme.test", Membership.RECRUITER)


@pytest.fixture
def interviewer(company):
    return _member(company, "int@acme.test", Membership.INTERVIEWER)


@pytest.fixture
def other_owner(other_company):
    return _member(other_company, "owner@globex.test", Membership.OWNER)


@pytest.fixture
def candidate(db):
    user = User.objects.create_user(
        email="cand@example.test", password="pw12345678", is_candidate=True
    )
    CandidateProfile.objects.create(user=user, experience_years=3)
    return user


@pytest.fixture
def make_job(db):
    def factory(company, title="Django Developer", status=Job.OPEN):
        return Job.objects.create(company=company, title=title, status=status)

    return factory


@pytest.fixture
def make_application(db):
    def factory(job, user_email, stage=None):
        user = User.objects.create_user(email=user_email, password="pw12345678", is_candidate=True)
        profile = CandidateProfile.objects.create(user=user, experience_years=2)
        return Application.objects.create(
            job=job,
            candidate=profile,
            current_stage=stage or job.first_stage,
            ai_fit_score=71,
        )

    return factory


# --- billing plan helpers -------------------------------------------------
# Creating a Company gives it a 14-day full-featured trial (billing signal), so
# by default the web tests see every paid feature. These flip a company onto a
# steady-state paid plan or onto expired-trial FREE.


def paid(company):
    """Put ``company`` on a genuinely paid AGENCY plan (no trial)."""
    from billing.models import Subscription
    from billing.services import agency_plan, set_plan

    set_plan(
        Subscription.objects.get(company=company),
        agency_plan(),
        status=Subscription.ACTIVE,
        trial_ends_at=None,
    )
    return company


def free_expired(company):
    """Push ``company`` onto FREE with its trial already over."""
    from datetime import timedelta

    from django.utils import timezone

    from billing.models import Subscription
    from billing.services import free_plan, set_plan

    set_plan(
        Subscription.objects.get(company=company),
        free_plan(),
        status=Subscription.ACTIVE,
        trial_ends_at=timezone.now() - timedelta(days=1),
    )
    return company


@pytest.fixture
def paid_company(company):
    return paid(company)


@pytest.fixture
def free_company(company):
    return free_expired(company)
