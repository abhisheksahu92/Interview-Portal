"""Shared fixtures for API tests."""

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job, Skill


@pytest.fixture
def api():
    return APIClient()


def _member(company, email, role):
    user = User.objects.create_user(email=email, password="pw12345!")
    Membership.objects.create(user=user, company=company, role=role)
    return user


@pytest.fixture
def company_a(db):
    return Company.objects.create(name="Acme Staffing")


@pytest.fixture
def company_b(db):
    return Company.objects.create(name="Beta Consulting")


@pytest.fixture
def owner_a(company_a):
    return _member(company_a, "owner-a@example.com", Membership.OWNER)


@pytest.fixture
def recruiter_a(company_a):
    return _member(company_a, "rec-a@example.com", Membership.RECRUITER)


@pytest.fixture
def interviewer_a(company_a):
    return _member(company_a, "int-a@example.com", Membership.INTERVIEWER)


@pytest.fixture
def recruiter_b(company_b):
    return _member(company_b, "rec-b@example.com", Membership.RECRUITER)


@pytest.fixture
def job_a(company_a):
    return Job.objects.create(
        company=company_a, title="Python Developer", status=Job.OPEN
    )


@pytest.fixture
def job_b(company_b):
    return Job.objects.create(company=company_b, title="Java Developer", status=Job.OPEN)


@pytest.fixture
def skill_a(company_a):
    return Skill.objects.create(company=company_a, name="Python")


@pytest.fixture
def candidate(db):
    user = User.objects.create_user(
        email="cand@example.com", password="pw12345!", is_candidate=True
    )
    return CandidateProfile.objects.create(user=user, experience_years=3)


@pytest.fixture
def application(job_a, candidate):
    return Application.objects.create(
        job=job_a, candidate=candidate, current_stage=job_a.first_stage
    )


@pytest.fixture
def auth(api):
    def _auth(user):
        token, _ = Token.objects.get_or_create(user=user)
        api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return api

    return _auth
