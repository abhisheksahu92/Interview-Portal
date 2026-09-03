import pytest
from django.urls import reverse

from jobs.models import Application
from talent import services
from talent.models import ImportBatch, TalentProfile


@pytest.fixture
def profile(company, python_skill):
    profile, _ = services.upsert_profile(
        company,
        email="asha@example.test",
        name="Asha Rao",
        headline="Senior Django Developer",
        experience_years=8,
        resume_text="Django, Celery, PostgreSQL",
    )
    profile.skills.add(python_skill)
    return profile


@pytest.mark.django_db
def test_index_lists_the_pool_with_skill_chips(client, owner, profile):
    client.force_login(owner)

    response = client.get(reverse("talent:index"))

    assert response.status_code == 200
    assert b"Asha Rao" in response.content
    assert b"Python" in response.content


@pytest.mark.django_db
def test_index_applies_the_search_query(client, owner, profile):
    client.force_login(owner)

    hit = client.get(reverse("talent:index"), {"q": "celery"})
    miss = client.get(reverse("talent:index"), {"q": "kubernetes"})

    assert b"Asha Rao" in hit.content
    assert b"Asha Rao" not in miss.content


@pytest.mark.django_db
def test_index_is_closed_to_interviewers(client, interviewer, profile):
    client.force_login(interviewer)

    assert client.get(reverse("talent:index")).status_code == 403


@pytest.mark.django_db
def test_another_companys_profile_is_not_reachable(client, other_owner, profile):
    client.force_login(other_owner)

    response = client.get(reverse("talent:profile_detail", args=[profile.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_profile_detail_shows_applications_and_saves_notes(client, owner, profile, job):
    services.add_to_job([profile], job)
    client.force_login(owner)
    url = reverse("talent:profile_detail", args=[profile.pk])

    detail = client.get(url)
    assert detail.status_code == 200
    assert job.title.encode() in detail.content

    posted = client.post(url, {"notes": "Great phone screen."})
    profile.refresh_from_db()
    assert posted.status_code == 302
    assert profile.notes == "Great phone screen."


@pytest.mark.django_db
def test_resume_view_streams_for_staff_and_404s_without_a_file(
    client, owner, other_owner, company, txt_resume
):
    batch = services.run_import(company, [txt_resume()], uploaded_by=owner)
    assert batch.created == 1
    with_resume = TalentProfile.objects.get(company=company)
    url = reverse("talent:profile_resume", args=[with_resume.pk])

    client.force_login(owner)
    response = client.get(url)
    assert response.status_code == 200
    assert b"Asha Rao" in b"".join(response.streaming_content)

    client.force_login(other_owner)
    assert client.get(url).status_code == 404

    empty, _ = services.upsert_profile(company, email="noresume@example.test")
    client.force_login(owner)
    assert client.get(reverse("talent:profile_resume", args=[empty.pk])).status_code == 404


@pytest.mark.django_db
def test_bulk_add_tag_and_add_to_job(client, owner, profile, job):
    client.force_login(owner)
    url = reverse("talent:bulk_action")

    client.post(url, {"action": "tag", "selected": [profile.pk], "tag": "shortlist"})
    profile.refresh_from_db()
    assert profile.tags == ["shortlist"]

    client.post(url, {"action": "add_to_job", "selected": [profile.pk], "job": job.pk})
    assert Application.objects.filter(job=job).count() == 1


@pytest.mark.django_db
def test_bulk_action_requires_a_selection(client, owner, profile):
    client.force_login(owner)

    response = client.post(reverse("talent:bulk_action"), {"action": "tag", "tag": "x"})

    assert response.status_code == 302
    profile.refresh_from_db()
    assert profile.tags == []


@pytest.mark.django_db
def test_export_returns_csv(client, owner, profile):
    client.force_login(owner)

    response = client.get(reverse("talent:export"))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert b"asha@example.test" in response.content


@pytest.mark.django_db
def test_import_wizard_uploads_and_redirects_to_the_report(client, owner, csv_upload):
    client.force_login(owner)

    response = client.post(reverse("talent:import"), {"files": csv_upload()}, follow=True)

    assert response.status_code == 200
    batch = ImportBatch.objects.get()
    assert batch.created == 2
    assert b"Progress" in response.content


@pytest.mark.django_db
def test_import_wizard_reports_an_oversized_upload(client, owner, monkeypatch, txt_resume):
    monkeypatch.setattr(services, "MAX_ARCHIVE_BYTES", 10)
    client.force_login(owner)

    response = client.post(reverse("talent:import"), {"files": txt_resume()})

    assert response.status_code == 200
    assert b"MB or less" in response.content or b"MB or smaller" in response.content
    assert TalentProfile.objects.count() == 0


@pytest.mark.django_db
def test_batch_status_partial_stops_polling_when_finished(client, owner, company, csv_upload):
    batch = services.run_import(company, [csv_upload()], uploaded_by=owner)
    client.force_login(owner)

    response = client.get(reverse("talent:batch_status", args=[batch.pk]))

    assert response.status_code == 200
    assert b"hx-trigger" not in response.content
    assert b"100%" in response.content


@pytest.mark.django_db
def test_manual_profile_creation(client, owner, company):
    client.force_login(owner)

    response = client.post(
        reverse("talent:profile_create"),
        {"name": "New Person", "email": "New@Example.test", "experience_years": "2"},
    )

    assert response.status_code == 302
    profile = TalentProfile.objects.get(company=company)
    assert profile.email == "new@example.test"
    assert profile.source == TalentProfile.MANUAL
    assert profile.created_by == owner
