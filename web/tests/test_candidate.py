import pytest
from django.urls import reverse

from jobs.models import Application


@pytest.mark.django_db
def test_candidate_cannot_access_recruiter_pages(client, candidate, company, make_job):
    job = make_job(company)
    client.force_login(candidate)
    for url in [
        reverse("web:dashboard"),
        reverse("web:job_create"),
        reverse("web:settings_members"),
        reverse("web:settings_skills"),
        reverse("web:job_detail", args=[job.pk]),
        reverse("web:interviewer_queue"),
    ]:
        assert client.get(url).status_code == 403, url


@pytest.mark.django_db
def test_member_cannot_use_candidate_portal(client, recruiter):
    client.force_login(recruiter)
    assert client.get(reverse("web:candidate_home")).status_code == 403


@pytest.mark.django_db
def test_candidate_can_edit_profile(client, candidate):
    client.force_login(candidate)
    response = client.post(
        reverse("web:candidate_profile"),
        {
            "headline": "Senior Django dev",
            "phone": "+91 99999 99999",
            "experience_years": "6.5",
            "notice_period_days": "30",
        },
    )
    assert response.status_code == 302
    candidate.candidate_profile.refresh_from_db()
    assert candidate.candidate_profile.headline == "Senior Django dev"


@pytest.mark.django_db
def test_candidate_can_apply_and_see_stepper(client, candidate, company, make_job):
    job = make_job(company, title="Platform Engineer")
    client.force_login(candidate)
    response = client.post(reverse("web:job_apply", args=[job.pk]), {"confirm": "on"})
    assert response.status_code == 302
    application = Application.objects.get(job=job, candidate__user=candidate)
    assert application.current_stage == job.first_stage

    portal = client.get(reverse("web:candidate_home"))
    assert portal.status_code == 200
    assert b"Platform Engineer" in portal.content
    assert b"ip-stepper" in portal.content


@pytest.mark.django_db
def test_apply_is_idempotent(client, candidate, company, make_job):
    job = make_job(company)
    client.force_login(candidate)
    client.post(reverse("web:job_apply", args=[job.pk]), {"confirm": "on"})
    client.post(reverse("web:job_apply", args=[job.pk]), {"confirm": "on"})
    assert Application.objects.filter(job=job, candidate__user=candidate).count() == 1


@pytest.mark.django_db
def test_take_assessment_cta_appears_when_active_assessment_exists(
    client, candidate, company, make_job
):
    from assessments.models import Assessment

    job = make_job(company)
    stage = job.stages.filter(requires_assessment=True).first()
    application = Application.objects.create(
        job=job, candidate=candidate.candidate_profile, current_stage=stage
    )
    client.force_login(candidate)

    without = client.get(reverse("web:candidate_home"))
    assert b"has not published one yet" in without.content

    Assessment.objects.create(job=job, stage=stage, title="Python basics", is_active=True)
    with_assessment = client.get(reverse("web:candidate_home"))
    row = with_assessment.context["rows"][0]
    assert row["application"] == application
    assert row["assessment_url"]
    assert b"Take assessment" in with_assessment.content


@pytest.mark.django_db
def test_public_job_detail_requires_open_status(client, company, make_job):
    from jobs.models import Job

    draft = make_job(company, status=Job.DRAFT)
    assert client.get(reverse("web:job_public_detail", args=[draft.pk])).status_code == 404


# --- apply flow (QA fix 8) ------------------------------------------------


@pytest.mark.django_db
def test_apply_validation_error_returns_to_the_job_url(
    client, candidate, company, make_job
):
    """A missing confirmation redirects back to the shareable job URL."""
    job = make_job(company, title="Platform Engineer")
    client.force_login(candidate)
    response = client.post(reverse("web:job_apply", args=[job.pk]), {})
    assert response.status_code == 302
    assert response.url == reverse("web:job_public_detail", args=[job.pk])
    assert not Application.objects.filter(job=job).exists()

    followed = client.get(response.url)
    assert followed.status_code == 200
    assert b"confirm" in followed.content


@pytest.mark.django_db
def test_apply_get_redirects_to_job_detail(client, candidate, company, make_job):
    job = make_job(company)
    client.force_login(candidate)
    response = client.get(reverse("web:job_apply", args=[job.pk]))
    assert response.url == reverse("web:job_public_detail", args=[job.pk])


@pytest.mark.django_db
def test_anonymous_apply_redirects_to_login_with_next(client, company, make_job):
    job = make_job(company)
    apply_url = reverse("web:job_apply", args=[job.pk])
    for response in (client.get(apply_url), client.post(apply_url, {"confirm": "on"})):
        assert response.status_code == 302
        assert reverse("core:login") in response.url
        assert apply_url in response.url
    assert not Application.objects.exists()


@pytest.mark.django_db
def test_openings_search_pushes_url_for_sharing(client, company, make_job):
    make_job(company, title="Platform Engineer")
    page = client.get(reverse("web:job_browse"))
    assert b'hx-push-url="true"' in page.content


# --- profile: résumé + skills (QA fixes 5 & 6) ---------------------------


@pytest.mark.django_db
def test_profile_rejects_a_bogus_resume(client, candidate):
    from django.core.files.uploadedfile import SimpleUploadedFile

    client.force_login(candidate)
    response = client.post(
        reverse("web:candidate_profile"),
        {
            "headline": "Dev",
            "experience_years": "3",
            "notice_period_days": "0",
            "resume": SimpleUploadedFile("cv.pdf", b"<html>nope</html>"),
        },
    )
    assert response.status_code == 200
    assert b"not a valid PDF" in response.content
    candidate.candidate_profile.refresh_from_db()
    assert not candidate.candidate_profile.resume


@pytest.mark.django_db
def test_profile_accepts_a_real_pdf(client, candidate, tmp_path, settings):
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.MEDIA_ROOT = tmp_path
    client.force_login(candidate)
    response = client.post(
        reverse("web:candidate_profile"),
        {
            "headline": "Dev",
            "experience_years": "3",
            "notice_period_days": "0",
            "resume": SimpleUploadedFile("cv.pdf", b"%PDF-1.4 hello"),
        },
    )
    assert response.status_code == 302
    candidate.candidate_profile.refresh_from_db()
    assert candidate.candidate_profile.resume.name.endswith(".pdf")


@pytest.mark.django_db
def test_profile_form_has_accept_attribute_and_deduplicated_skills(
    client, candidate, company, other_company
):
    from jobs.models import Skill

    Skill.objects.create(company=company, name="Python")
    Skill.objects.create(company=other_company, name="Python")
    Skill.objects.create(company=company, name="Django")

    client.force_login(candidate)
    body = client.get(reverse("web:candidate_profile")).content.decode()
    assert 'accept=".pdf,.doc,.docx,.txt' in body
    assert body.count(">Python<") == 1
    assert body.count(">Django<") == 1
    assert "ip-pill-check" in body
