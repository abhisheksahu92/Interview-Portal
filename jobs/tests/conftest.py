import pytest

from core.models import Company, Membership, User
from jobs.models import CandidateProfile, Job


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme")


@pytest.fixture
def other_company(db):
    return Company.objects.create(name="Globex")


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
def other_recruiter(other_company):
    return _member(other_company, "rec@globex.test", Membership.RECRUITER)


@pytest.fixture
def job(company):
    return Job.objects.create(company=company, title="Django Dev", status=Job.OPEN)


@pytest.fixture
def candidate(db):
    user = User.objects.create_user(
        email="cand@example.test", password="pw12345678", is_candidate=True
    )
    return CandidateProfile.objects.create(user=user, experience_years=3)
