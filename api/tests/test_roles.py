"""Role enforcement on write endpoints."""

import pytest


@pytest.mark.django_db
def test_interviewer_cannot_create_job(auth, interviewer_a):
    resp = auth(interviewer_a).post(
        "/api/v1/jobs/", {"title": "Nope"}, format="json"
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_interviewer_can_read_jobs(auth, interviewer_a, job_a):
    assert auth(interviewer_a).get("/api/v1/jobs/").status_code == 200


@pytest.mark.django_db
def test_recruiter_can_create_skill(auth, recruiter_a):
    resp = auth(recruiter_a).post("/api/v1/skills/", {"name": "Django"}, format="json")
    assert resp.status_code == 201


@pytest.mark.django_db
def test_duplicate_skill_rejected(auth, recruiter_a, skill_a):
    resp = auth(recruiter_a).post("/api/v1/skills/", {"name": "python"}, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_interviewer_cannot_advance_application(auth, interviewer_a, application):
    resp = auth(interviewer_a).post(f"/api/v1/applications/{application.pk}/advance/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_candidate_me_endpoint(auth, candidate):
    client = auth(candidate.user)
    resp = client.get("/api/v1/candidates/me/")
    assert resp.status_code == 200
    assert resp.data["user"]["email"] == candidate.user.email
    resp = client.patch(
        "/api/v1/candidates/me/", {"headline": "Backend dev"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["headline"] == "Backend dev"


@pytest.mark.django_db
def test_candidate_cannot_see_other_candidates(auth, candidate, application, db):
    from core.models import User
    from jobs.models import CandidateProfile

    other = CandidateProfile.objects.create(
        user=User.objects.create_user(email="other@example.com", password="pw12345!"),
        experience_years=1,
    )
    resp = auth(candidate.user).get("/api/v1/candidates/")
    ids = [c["id"] for c in resp.data["results"]]
    assert other.pk not in ids
