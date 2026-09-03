import pytest
from django.core.exceptions import ValidationError

from core.models import User
from jobs.models import Application, CandidateProfile, Job
from talent import services
from talent.models import TalentProfile


@pytest.fixture
def profile(company, python_skill):
    profile, _ = services.upsert_profile(
        company,
        email="asha@example.test",
        name="Asha Rao",
        experience_years=8,
        headline="Django dev",
    )
    profile.skills.add(python_skill)
    return profile


@pytest.mark.django_db
def test_add_tag_is_deduped_case_insensitively(profile):
    assert services.add_tag([profile], "Shortlist") == 1
    assert services.add_tag([profile], "shortlist") == 0

    profile.refresh_from_db()
    assert profile.tags == ["Shortlist"]


@pytest.mark.django_db
def test_add_to_job_creates_shell_user_candidate_and_application(profile, job, python_skill):
    result = services.add_to_job([profile], job)

    assert result == {"added": 1, "existing": 0, "errors": []}
    user = User.objects.get(email="asha@example.test")
    assert user.is_candidate is True
    assert user.has_usable_password() is False
    application = Application.objects.get(job=job)
    assert application.candidate.user == user
    assert application.current_stage == job.first_stage
    profile.refresh_from_db()
    assert profile.linked_candidate_id == application.candidate_id
    assert python_skill in application.candidate.skills.all()


@pytest.mark.django_db
def test_add_to_job_is_idempotent(profile, job):
    services.add_to_job([profile], job)
    result = services.add_to_job([profile], job)

    assert result["added"] == 0
    assert result["existing"] == 1
    assert Application.objects.filter(job=job).count() == 1


@pytest.mark.django_db
def test_add_to_job_refuses_a_profile_from_another_company(profile, other_company):
    other_job = Job.objects.create(company=other_company, title="SRE", status=Job.OPEN)

    result = services.add_to_job([profile], other_job)

    assert result["added"] == 0
    assert "different company" in result["errors"][0]
    assert Application.objects.count() == 0


@pytest.mark.django_db
def test_add_to_job_reports_a_closed_job(profile, company):
    closed = Job.objects.create(company=company, title="Closed role", status=Job.DRAFT)

    result = services.add_to_job([profile], closed)

    assert result["added"] == 0
    assert result["errors"]


@pytest.mark.django_db
def test_add_to_job_sends_the_application_received_notification(profile, job, monkeypatch):
    sent = []
    monkeypatch.setattr(
        services,
        "_notify_application",
        lambda application: sent.append(application),
    )

    services.add_to_job([profile], job)

    assert len(sent) == 1


@pytest.mark.django_db
def test_notification_failure_never_breaks_the_flow(profile, job):
    # The notifications app may not expose send() yet; add_to_job must still work.
    result = services.add_to_job([profile], job)
    assert result["added"] == 1


@pytest.mark.django_db
def test_existing_candidate_account_is_linked_not_recreated(company, python_skill):
    user = User.objects.create_user(
        email="ben@example.test", password="pw12345678", is_candidate=True
    )
    candidate = CandidateProfile.objects.create(user=user, experience_years=4)

    profile, _ = services.upsert_profile(company, email="BEN@example.test", name="Ben Iyer")

    assert profile.linked_candidate_id == candidate.pk
    assert services.ensure_candidate_profile(profile) == candidate
    assert User.objects.filter(email="ben@example.test").count() == 1


@pytest.mark.django_db
def test_phone_only_profile_cannot_be_added_to_a_job(company, job):
    profile, _ = services.upsert_profile(company, phone="+919876543210", name="Anon")

    with pytest.raises(ValidationError):
        services.ensure_candidate_profile(profile)


@pytest.mark.django_db
def test_export_csv_lists_the_selection(profile):
    profile.add_tag("shortlist")

    text = services.export_csv([profile]).getvalue()

    header, row = text.splitlines()[0], text.splitlines()[1]
    assert header.startswith("name,email,phone")
    assert "asha@example.test" in row
    assert "Python" in row
    assert "shortlist" in row


@pytest.mark.django_db
def test_upsert_never_blanks_stored_values(company):
    services.upsert_profile(company, email="asha@example.test", name="Asha Rao", phone="+91999")
    profile, created = services.upsert_profile(company, email="asha@example.test", name="")

    assert created is False
    assert profile.name == "Asha Rao"
    assert profile.phone == "+91999"


@pytest.mark.django_db
def test_upsert_requires_an_email_or_phone(company):
    with pytest.raises(ValidationError):
        services.upsert_profile(company, name="Nobody")


@pytest.mark.django_db
def test_email_is_stored_lowercased_and_unique_per_company(company, other_company):
    profile, _ = services.upsert_profile(company, email="ASHA@Example.Test", name="Asha")
    twin, created = services.upsert_profile(other_company, email="asha@example.test", name="Asha")

    assert profile.email == "asha@example.test"
    assert created is True
    assert TalentProfile.objects.filter(email="asha@example.test").count() == 2
