import pytest

from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job


@pytest.fixture(autouse=True)
def _plain_staticfiles(settings):
    """Avoid needing a collectstatic manifest when rendering templates in tests."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme Staffing")


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
        user = User.objects.create_user(
            email=user_email, password="pw12345678", is_candidate=True
        )
        profile = CandidateProfile.objects.create(user=user, experience_years=2)
        return Application.objects.create(
            job=job,
            candidate=profile,
            current_stage=stage or job.first_stage,
            ai_fit_score=71,
        )

    return factory
