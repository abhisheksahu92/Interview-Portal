from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from assessments.models import Assessment, Attempt, Question


@pytest.fixture
def assessment(company_a, job_a):
    a = Assessment.objects.create(
        job=job_a, stage=job_a.first_stage, title="Python basics", pass_mark_percent=60
    )
    q1 = Question.objects.create(
        company=company_a,
        kind=Question.MCQ,
        text="2+2?",
        options=["3", "4", "5"],
        correct_option=1,
    )
    q2 = Question.objects.create(
        company=company_a,
        kind=Question.MCQ,
        text="Capital of France?",
        options=["Paris", "Rome"],
        correct_option=0,
    )
    a.questions.set([q1, q2])
    return a


@pytest.mark.django_db
def test_start_creates_attempt(auth, candidate, application, assessment):
    resp = auth(candidate.user).post(
        "/api/v1/attempts/start/",
        {"assessment": assessment.pk, "application": application.pk},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["submitted_at"] is None


@pytest.mark.django_db
def test_start_twice_returns_same_attempt(auth, candidate, application, assessment):
    client = auth(candidate.user)
    payload = {"assessment": assessment.pk, "application": application.pk}
    first = client.post("/api/v1/attempts/start/", payload, format="json")
    second = client.post("/api/v1/attempts/start/", payload, format="json")
    assert second.status_code == 200
    assert second.data["id"] == first.data["id"]


@pytest.mark.django_db
def test_start_rejects_assessment_from_another_job(
    auth, candidate, application, job_b
):
    other = Assessment.objects.create(job=job_b, title="Java")
    resp = auth(candidate.user).post(
        "/api/v1/attempts/start/",
        {"assessment": other.pk, "application": application.pk},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_submit_grades_mcqs(auth, candidate, application, assessment):
    client = auth(candidate.user)
    start = client.post(
        "/api/v1/attempts/start/",
        {"assessment": assessment.pk, "application": application.pk},
        format="json",
    )
    ids = [q.pk for q in assessment.questions.order_by("pk")]
    resp = client.post(
        f"/api/v1/attempts/{start.data['id']}/submit/",
        {"answers": {str(ids[0]): 1, str(ids[1]): 0}},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert float(resp.data["score_percent"]) == 100.0
    assert resp.data["passed"] is True
    assert resp.data["submitted_at"] is not None


@pytest.mark.django_db
def test_submit_partial_answers_fails_pass_mark(
    auth, candidate, application, assessment
):
    client = auth(candidate.user)
    start = client.post(
        "/api/v1/attempts/start/",
        {"assessment": assessment.pk, "application": application.pk},
        format="json",
    )
    ids = [q.pk for q in assessment.questions.order_by("pk")]
    resp = client.post(
        f"/api/v1/attempts/{start.data['id']}/submit/",
        {"answers": {str(ids[0]): 0, str(ids[1]): 0}},
        format="json",
    )
    assert float(resp.data["score_percent"]) == 50.0
    assert resp.data["passed"] is False


@pytest.mark.django_db
def test_submit_text_answer_uses_mocked_ai(
    auth, candidate, application, assessment, company_a
):
    text_q = Question.objects.create(
        company=company_a, kind=Question.TEXT, text="Explain the GIL."
    )
    assessment.questions.add(text_q)
    client = auth(candidate.user)
    start = client.post(
        "/api/v1/attempts/start/",
        {"assessment": assessment.pk, "application": application.pk},
        format="json",
    )
    mcq_ids = [q.pk for q in assessment.questions.filter(kind="MCQ").order_by("pk")]
    with mock.patch("assessments.ai.grade_text_answer", return_value=100) as graded:
        resp = client.post(
            f"/api/v1/attempts/{start.data['id']}/submit/",
            {
                "answers": {
                    str(mcq_ids[0]): 1,
                    str(mcq_ids[1]): 0,
                    str(text_q.pk): "A mutex around the interpreter.",
                }
            },
            format="json",
        )
    assert graded.called
    assert float(resp.data["score_percent"]) == 100.0


@pytest.mark.django_db
def test_submit_twice_is_rejected(auth, candidate, application, assessment):
    client = auth(candidate.user)
    start = client.post(
        "/api/v1/attempts/start/",
        {"assessment": assessment.pk, "application": application.pk},
        format="json",
    )
    url = f"/api/v1/attempts/{start.data['id']}/submit/"
    assert client.post(url, {"answers": {}}, format="json").status_code == 200
    assert client.post(url, {"answers": {}}, format="json").status_code == 400


@pytest.mark.django_db
def test_other_company_cannot_see_attempts(
    auth, candidate, application, assessment, recruiter_b, recruiter_a
):
    auth(candidate.user).post(
        "/api/v1/attempts/start/",
        {"assessment": assessment.pk, "application": application.pk},
        format="json",
    )
    assert auth(recruiter_a).get("/api/v1/attempts/").data["count"] == 1
    assert auth(recruiter_b).get("/api/v1/attempts/").data["count"] == 0


@pytest.mark.django_db
def test_assessment_and_question_endpoints_scoped(
    auth, recruiter_a, recruiter_b, assessment
):
    assert auth(recruiter_a).get("/api/v1/assessments/").data["count"] == 1
    assert auth(recruiter_b).get("/api/v1/assessments/").data["count"] == 0
    assert auth(recruiter_a).get("/api/v1/questions/").data["count"] == 2
    assert auth(recruiter_b).get("/api/v1/questions/").data["count"] == 0


@pytest.mark.django_db
def test_submit_past_deadline_scores_zero(auth, candidate, application, assessment):
    assessment.time_limit_minutes = 10
    assessment.save()

    client = auth(candidate.user)
    start = client.post(
        "/api/v1/attempts/start/",
        {"assessment": assessment.pk, "application": application.pk},
        format="json",
    )
    attempt_id = start.data["id"]
    attempt = Attempt.objects.get(pk=attempt_id)
    attempt.started_at = timezone.now() - timedelta(minutes=20)
    attempt.save(update_fields=["started_at"])

    ids = [q.pk for q in assessment.questions.order_by("pk")]
    resp = client.post(
        f"/api/v1/attempts/{attempt_id}/submit/",
        {"answers": {str(ids[0]): 1, str(ids[1]): 0}},
        format="json",
    )
    assert resp.status_code == 200
    assert float(resp.data["score_percent"]) == 0.0
    assert resp.data["passed"] is False
    assert resp.data["ai_feedback"] == "Time limit exceeded"


@pytest.mark.django_db
def test_start_expired_attempt_is_rejected(auth, candidate, application, assessment):
    assessment.time_limit_minutes = 10
    assessment.save()

    client = auth(candidate.user)
    start = client.post(
        "/api/v1/attempts/start/",
        {"assessment": assessment.pk, "application": application.pk},
        format="json",
    )
    attempt = Attempt.objects.get(pk=start.data["id"])
    attempt.started_at = timezone.now() - timedelta(minutes=20)
    attempt.save(update_fields=["started_at"])

    resp = client.post(
        "/api/v1/attempts/start/",
        {"assessment": assessment.pk, "application": application.pk},
        format="json",
    )
    assert resp.status_code == 400
    assert "expired" in str(resp.data).lower()
