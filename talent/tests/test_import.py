from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError

from talent import services
from talent.models import ImportBatch, TalentProfile
from talent.tests.conftest import RESUME_TEXT


@pytest.mark.django_db
def test_import_single_resume_creates_profile(company, owner, txt_resume):
    batch = services.run_import(company, [txt_resume()], uploaded_by=owner)

    assert batch.status == ImportBatch.DONE
    assert (batch.created, batch.updated, batch.skipped) == (1, 0, 0)
    profile = TalentProfile.objects.get(company=company)
    assert profile.email == "asha.rao@example.test"
    assert profile.name == "Asha Rao"
    assert profile.phone.endswith("9876543210")
    assert profile.source == TalentProfile.IMPORT
    assert float(profile.experience_years) == 8.0
    assert "Django" in profile.resume_text
    assert profile.resume.name.startswith("talent/")


@pytest.mark.django_db
def test_import_zip_of_resumes(company, owner, zip_upload):
    second = (
        RESUME_TEXT.replace("asha.rao@example.test", "ben@example.test")
        .replace("Asha Rao", "Ben Iyer")
        .replace("+91 98765 43210", "+91 98765 40000")
    )
    upload = zip_upload({"asha.txt": RESUME_TEXT, "nested/ben.txt": second})

    batch = services.run_import(company, [upload], uploaded_by=owner)

    assert batch.total == 2
    assert batch.created == 2
    assert set(TalentProfile.objects.values_list("email", flat=True)) == {
        "asha.rao@example.test",
        "ben@example.test",
    }
    assert batch.percent == 100


@pytest.mark.django_db
def test_import_csv_creates_profiles_with_skills(company, owner, csv_upload):
    batch = services.run_import(company, [csv_upload()], uploaded_by=owner)

    assert (batch.total, batch.created, batch.updated) == (2, 2, 0)
    asha = TalentProfile.objects.get(email="asha.rao@example.test")
    assert float(asha.experience_years) == 8.0
    assert sorted(asha.skills.values_list("name", flat=True)) == ["Django", "Python"]


@pytest.mark.django_db
def test_import_csv_dedupes_by_email_and_updates(company, owner, csv_upload):
    services.run_import(company, [csv_upload()], uploaded_by=owner)
    rows = [
        "name,email,phone,skills,experience",
        "Asha Rao,ASHA.RAO@example.test,+919876543210,Airflow,8",
    ]
    batch = services.run_import(company, [csv_upload(rows, name="again.csv")], uploaded_by=owner)

    assert (batch.created, batch.updated) == (0, 1)
    assert TalentProfile.objects.filter(email="asha.rao@example.test").count() == 1
    asha = TalentProfile.objects.get(email="asha.rao@example.test")
    assert "Airflow" in asha.skills.values_list("name", flat=True)


@pytest.mark.django_db
def test_dedupe_falls_back_to_phone_when_email_differs(company):
    services.upsert_profile(company, email="one@example.test", phone="+919876543210", name="Asha")
    profile, created = services.upsert_profile(
        company, phone="+919876543210", headline="Django dev"
    )

    assert created is False
    assert profile.email == "one@example.test"
    assert profile.headline == "Django dev"
    assert TalentProfile.objects.count() == 1


@pytest.mark.django_db
def test_import_skips_rows_without_contact_details(company, owner, csv_upload):
    rows = ["name,email,phone", "No Contact,,"]
    batch = services.run_import(company, [csv_upload(rows)], uploaded_by=owner)

    assert (batch.created, batch.skipped) == (0, 1)
    assert batch.errors[0]["error"].startswith("Missing")
    assert TalentProfile.objects.count() == 0


@pytest.mark.django_db
def test_import_skips_resume_without_contact_details(company, owner, txt_resume):
    upload = txt_resume(name="mystery.txt", text="Some notes with no way to reach anyone.")
    batch = services.run_import(company, [upload], uploaded_by=owner)

    assert batch.skipped == 1
    assert "No email or phone" in batch.errors[0]["error"]


@pytest.mark.django_db
def test_import_rejects_unsupported_file_type(company, owner, txt_resume):
    batch = services.run_import(company, [txt_resume(name="notes.rtf")], uploaded_by=owner)

    assert batch.skipped == 1
    assert "Unsupported file type" in batch.errors[0]["error"]


@pytest.mark.django_db
def test_import_enforces_file_count_cap(company, owner, txt_resume):
    uploads = [txt_resume(name=f"cv{i}.txt") for i in range(services.MAX_FILES + 1)]
    with pytest.raises(ValidationError):
        services.run_import(company, uploads, uploaded_by=owner)


@pytest.mark.django_db
def test_import_enforces_total_size_cap(company, owner, monkeypatch, txt_resume):
    upload = txt_resume()
    monkeypatch.setattr(upload, "size", services.MAX_ARCHIVE_BYTES + 1, raising=False)
    with pytest.raises(ValidationError):
        services.run_import(company, [upload], uploaded_by=owner)
    assert ImportBatch.objects.count() == 0


@pytest.mark.django_db
def test_zip_with_too_many_members_fails_the_batch(company, owner, zip_upload, monkeypatch):
    monkeypatch.setattr(services, "MAX_FILES", 2)
    upload = zip_upload({f"cv{i}.txt": RESUME_TEXT for i in range(3)})

    with pytest.raises(ValidationError):
        services.run_import(company, [upload], uploaded_by=owner)
    batch = ImportBatch.objects.get()
    assert batch.status == ImportBatch.FAILED
    assert batch.errors


@pytest.mark.django_db
def test_import_requires_a_file(company, owner):
    with pytest.raises(ValidationError):
        services.run_import(company, [], uploaded_by=owner)


@pytest.mark.django_db
def test_ai_extraction_is_used_when_configured(company, owner, settings, txt_resume):
    settings.ANTHROPIC_API_KEY = "test-key"
    payload = {
        "name": "Asha Rao",
        "email": "asha.ai@example.test",
        "phone": "+919999999999",
        "headline": "Staff Engineer",
        "current_company": "Globex",
        "location": "Pune, IN",
        "experience_years": 9,
        "skills": ["Python", "Kubernetes"],
    }
    with patch("talent.ai.extract_profile", return_value=payload) as mocked:
        batch = services.run_import(company, [txt_resume()], uploaded_by=owner)

    assert mocked.called
    assert batch.created == 1
    profile = TalentProfile.objects.get()
    assert profile.email == "asha.ai@example.test"
    assert profile.headline == "Staff Engineer"
    assert profile.current_company == "Globex"
    assert float(profile.experience_years) == 9.0
    assert sorted(profile.skills.values_list("name", flat=True)) == ["Kubernetes", "Python"]


@pytest.mark.django_db
def test_ai_extraction_is_skipped_without_a_key(company, owner, settings, txt_resume):
    settings.ANTHROPIC_API_KEY = ""
    with patch("talent.ai.extract_profile") as mocked:
        services.run_import(company, [txt_resume()], uploaded_by=owner)

    assert not mocked.called
    assert services.ai_enabled(company) is False


@pytest.mark.django_db
def test_ai_extract_profile_parses_mocked_response(settings):
    from talent import ai

    settings.ANTHROPIC_API_KEY = "test-key"
    with patch(
        "talent.ai._ask",
        return_value={"name": "Asha Rao", "experience_years": "7.5", "skills": "Python; Django"},
    ):
        data = ai.extract_profile("resume text")

    assert data["name"] == "Asha Rao"
    assert data["experience_years"] == 7.5
    assert data["skills"] == ["Python", "Django"]


@pytest.mark.django_db
def test_ai_extract_profile_returns_none_without_a_key(settings):
    from talent import ai

    settings.ANTHROPIC_API_KEY = ""
    assert ai.extract_profile("resume text") is None
