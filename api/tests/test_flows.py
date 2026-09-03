"""Application pipeline flow and assessment attempt flow."""


import pytest

from jobs.models import Application, StageReview


@pytest.mark.django_db
def test_advance_moves_to_next_stage(auth, recruiter_a, application, job_a):
    stages = list(job_a.stages.order_by("order"))
    resp = auth(recruiter_a).post(f"/api/v1/applications/{application.pk}/advance/")
    assert resp.status_code == 200
    assert resp.data["current_stage"] == stages[1].pk


@pytest.mark.django_db
def test_advance_at_last_stage_marks_hired(auth, recruiter_a, application, job_a):
    application.current_stage = job_a.stages.order_by("-order").first()
    application.save()
    resp = auth(recruiter_a).post(f"/api/v1/applications/{application.pk}/advance/")
    assert resp.data["status"] == Application.HIRED


@pytest.mark.django_db
def test_reject_then_advance_is_rejected(auth, recruiter_a, application):
    client = auth(recruiter_a)
    resp = client.post(f"/api/v1/applications/{application.pk}/reject/")
    assert resp.data["status"] == Application.REJECTED
    resp = client.post(f"/api/v1/applications/{application.pk}/advance/")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_review_action_creates_stage_review(auth, interviewer_a, application):
    resp = auth(interviewer_a).post(
        f"/api/v1/applications/{application.pk}/review/",
        {"decision": "PASS", "rating": 4, "feedback": "Strong"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    review = StageReview.objects.get(application=application)
    assert review.reviewer == interviewer_a
    assert review.decision == "PASS"
    assert review.stage == application.current_stage


@pytest.mark.django_db
def test_review_is_idempotent_per_reviewer_and_stage(auth, interviewer_a, application):
    client = auth(interviewer_a)
    for decision in ("HOLD", "FAIL"):
        resp = client.post(
            f"/api/v1/applications/{application.pk}/review/",
            {"decision": decision},
            format="json",
        )
        assert resp.status_code == 201
    assert StageReview.objects.filter(application=application).count() == 1
    assert StageReview.objects.get(application=application).decision == "FAIL"


@pytest.mark.django_db
def test_review_rejects_stage_from_another_job(auth, interviewer_a, application, job_b):
    resp = auth(interviewer_a).post(
        f"/api/v1/applications/{application.pk}/review/",
        {"decision": "PASS", "stage": job_b.first_stage.pk},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_reviews_list_scoped_to_company(auth, interviewer_a, recruiter_b, application):
    StageReview.objects.create(
        application=application,
        stage=application.current_stage,
        reviewer=interviewer_a,
        decision="PASS",
    )
    assert auth(interviewer_a).get("/api/v1/reviews/").data["count"] == 1
    assert auth(recruiter_b).get("/api/v1/reviews/").data["count"] == 0
