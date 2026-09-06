import pytest

from careers.models import CareersSite
from core.models import Company, Membership, User
from jobs.models import Job, Skill


def make_company(name, published=True, list_in_network=True):
    company = Company.objects.create(name=name)
    CareersSite.objects.create(
        company=company, published=published, list_in_network=list_in_network
    )
    return company


def make_job(company, title="Senior Python Engineer", **kwargs):
    skills = kwargs.pop("skills", [])
    job = Job.objects.create(
        company=company,
        title=title,
        location=kwargs.pop("location", "Pune, Maharashtra, IN"),
        description=kwargs.pop("description", "Build APIs."),
        status=kwargs.pop("status", Job.OPEN),
        **kwargs,
    )
    for name in skills:
        job.skills.add(Skill.objects.create(company=company, name=name))
    return job


@pytest.fixture
def company(db):
    return make_company("Acme Staffing")


@pytest.fixture
def job(company):
    return make_job(company, skills=["Python", "Django"])


@pytest.fixture
def candidate(db):
    return User.objects.create_user(
        email="cand@board.test", password="pw12345678", is_candidate=True
    )


@pytest.fixture
def recruiter(company):
    user = User.objects.create_user(email="rec@board.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    return user
