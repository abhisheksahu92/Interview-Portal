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
