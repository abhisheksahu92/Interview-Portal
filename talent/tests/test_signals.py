import pytest

from core.models import User
from jobs.models import CandidateProfile
from jobs.services import apply_to_job
from talent.models import TalentProfile


@pytest.fixture
def candidate(company, python_skill):
    user = User.objects.create_user(
        email="Chen@example.test",
        password="pw12345678",
        is_candidate=True,
        first_name="Chen",
        last_name="Wu",
    )
    profile = CandidateProfile.objects.create(
        user=user, experience_years=5, phone="+919812345678", headline="Data engineer"
    )
    profile.skills.add(python_skill)
    return profile


@pytest.mark.django_db
def test_application_auto_captures_a_talent_profile(company, job, candidate, python_skill):
    apply_to_job(job, candidate)

    profile = TalentProfile.objects.get(company=company)
    assert profile.email == "chen@example.test"
    assert profile.source == TalentProfile.APPLICANT
    assert profile.name == "Chen Wu"
    assert profile.phone == "+919812345678"
    assert profile.linked_candidate_id == candidate.pk
    assert python_skill in profile.skills.all()


@pytest.mark.django_db
def test_auto_capture_updates_an_existing_pool_profile(company, job, candidate):
    from talent import services

    existing, _ = services.upsert_profile(
        company, email="chen@example.test", name="Chen Wu", tags="sourced"
    )

    apply_to_job(job, candidate)

    assert TalentProfile.objects.count() == 1
    existing.refresh_from_db()
    assert existing.linked_candidate_id == candidate.pk
    assert existing.tags == ["sourced"]


@pytest.mark.django_db
def test_auto_capture_is_scoped_to_the_hiring_company(other_company, job, candidate):
    apply_to_job(job, candidate)

    assert TalentProfile.objects.filter(company=other_company).count() == 0


@pytest.mark.django_db
def test_auto_capture_never_breaks_application_creation(job, candidate, monkeypatch):
    from talent import services

    def boom(application):
        raise RuntimeError("pool is on fire")

    monkeypatch.setattr(services, "capture_applicant", boom)

    application = apply_to_job(job, candidate)

    assert application.pk is not None
    assert TalentProfile.objects.count() == 0
