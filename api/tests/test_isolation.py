"""Company isolation and the X-Company header."""

import pytest

from core.models import Membership


@pytest.mark.django_db
def test_user_cannot_see_other_company_jobs(auth, recruiter_a, job_a, job_b):
    resp = auth(recruiter_a).get("/api/v1/jobs/")
    titles = [j["title"] for j in resp.data["results"]]
    assert titles == [job_a.title]


@pytest.mark.django_db
def test_retrieving_other_company_job_is_404(auth, recruiter_a, job_b):
    assert auth(recruiter_a).get(f"/api/v1/jobs/{job_b.pk}/").status_code == 404


@pytest.mark.django_db
def test_x_company_header_selects_tenant(auth, recruiter_a, company_b, job_a, job_b):
    Membership.objects.create(
        user=recruiter_a, company=company_b, role=Membership.RECRUITER
    )
    client = auth(recruiter_a)
    resp = client.get("/api/v1/jobs/", HTTP_X_COMPANY=company_b.slug)
    assert [j["title"] for j in resp.data["results"]] == [job_b.title]


@pytest.mark.django_db
def test_x_company_header_without_membership_is_denied(auth, recruiter_a, company_b):
    resp = auth(recruiter_a).get("/api/v1/jobs/", HTTP_X_COMPANY=company_b.slug)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_created_job_belongs_to_resolved_company(auth, recruiter_a, company_a):
    resp = auth(recruiter_a).post(
        "/api/v1/jobs/", {"title": "SRE", "description": "d"}, format="json"
    )
    assert resp.status_code == 201, resp.data
    from jobs.models import Job

    job = Job.objects.get(pk=resp.data["id"])
    assert job.company == company_a
    assert job.created_by == recruiter_a
    assert job.stages.count() == 6
    assert len(resp.data["stages"]) == 6


@pytest.mark.django_db
def test_applications_scoped_by_job_company(auth, recruiter_b, application):
    resp = auth(recruiter_b).get("/api/v1/applications/")
    assert resp.status_code == 200
    assert resp.data["results"] == []


@pytest.mark.django_db
def test_skill_list_scoped(auth, recruiter_a, recruiter_b, skill_a):
    assert auth(recruiter_a).get("/api/v1/skills/").data["count"] == 1
    assert auth(recruiter_b).get("/api/v1/skills/").data["count"] == 0
