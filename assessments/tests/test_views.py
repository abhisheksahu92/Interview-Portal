import pytest
from django.urls import reverse

from assessments.models import Assessment, Question


@pytest.mark.django_db
def test_question_list_requires_login(client):
    response = client.get(reverse("assessments:question_list"))
    assert response.status_code in (302, 403)


@pytest.mark.django_db
def test_recruiter_sees_only_own_company_questions(
    client, recruiter, other_company, mcq_questions
):
    Question.objects.create(
        company=other_company, kind=Question.MCQ, text="Foreign question",
        options=["a", "b"], correct_option=0,
    )
    client.force_login(recruiter)
    response = client.get(reverse("assessments:question_list"))
    assert response.status_code == 200
    assert b"Foreign question" not in response.content
    assert b"Question 0?" in response.content


@pytest.mark.django_db
def test_interviewer_cannot_manage_question_bank(client, interviewer):
    client.force_login(interviewer)
    assert client.get(reverse("assessments:question_list")).status_code == 403


@pytest.mark.django_db
def test_candidate_cannot_reach_recruiter_views(client, candidate):
    client.force_login(candidate.user)
    assert client.get(reverse("assessments:question_list")).status_code == 403


@pytest.mark.django_db
def test_question_create_assigns_company(client, recruiter, company, skill):
    client.force_login(recruiter)
    response = client.post(
        reverse("assessments:question_create"),
        {
            "skill": skill.pk,
            "kind": "MCQ",
            "text": "Which is a Python web framework?",
            "options_text": "Django\nSpring\nRails",
            "correct_option": 0,
            "difficulty": "EASY",
        },
    )
    assert response.status_code == 302
    question = Question.objects.get(text__startswith="Which is")
    assert question.company == company
    assert question.options == ["Django", "Spring", "Rails"]


@pytest.mark.django_db
def test_cannot_edit_other_company_question(client, recruiter, other_company):
    foreign = Question.objects.create(
        company=other_company, kind=Question.TEXT, text="Foreign"
    )
    client.force_login(recruiter)
    url = reverse("assessments:question_edit", args=[foreign.pk])
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_generate_with_ai_returns_partial(monkeypatch, client, recruiter, job, skill):
    created = []

    def fake_generate(job_arg, skill_arg, n=5, kind="MCQ"):
        created.append((job_arg, skill_arg, n, kind))
        return [
            Question.objects.create(
                company=job_arg.company, kind=Question.MCQ, text="Generated?",
                options=["a", "b"], correct_option=0, source=Question.AI,
            )
        ]

    monkeypatch.setattr("assessments.views.ai.generate_questions", fake_generate)
    client.force_login(recruiter)
    response = client.post(
        reverse("assessments:question_generate"),
        {"job": job.pk, "skill": skill.pk, "n": 3, "kind": "MCQ"},
    )
    assert response.status_code == 200
    assert b"Generated?" in response.content
    assert created and created[0][2] == 3


@pytest.mark.django_db
def test_generate_with_ai_shows_warning_without_key(
    monkeypatch, client, recruiter, job, settings
):
    settings.ANTHROPIC_API_KEY = ""
    client.force_login(recruiter)
    response = client.post(
        reverse("assessments:question_generate"), {"job": job.pk, "n": 2, "kind": "MCQ"}
    )
    assert response.status_code == 200
    assert b"ANTHROPIC_API_KEY" in response.content


@pytest.mark.django_db
def test_assessment_builder_creates_assessment(client, recruiter, job, mcq_questions):
    client.force_login(recruiter)
    stage = job.stages.order_by("order")[1]
    response = client.post(
        reverse("assessments:assessment_create", args=[job.pk]),
        {
            "title": "Screen",
            "stage": stage.pk,
            "questions": [q.pk for q in mcq_questions[:2]],
            "time_limit_minutes": 20,
            "pass_mark_percent": 70,
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    assessment = Assessment.objects.get(title="Screen")
    assert assessment.job == job
    assert assessment.questions.count() == 2


@pytest.mark.django_db
def test_assessment_isolated_by_company(client, other_recruiter, assessment, job):
    client.force_login(other_recruiter)
    assert client.get(
        reverse("assessments:assessment_edit", args=[assessment.pk])
    ).status_code == 404
    assert client.get(
        reverse("assessments:job_assessments", args=[job.pk])
    ).status_code == 404


@pytest.mark.django_db
def test_candidate_take_and_submit_flow(client, candidate, application, assessment):
    client.force_login(candidate.user)
    response = client.get(
        reverse("assessments:take_assessment", args=[application.pk, assessment.pk])
    )
    assert response.status_code == 200
    assert b"Time left" in response.content

    attempt = application.attempts.get()
    response = client.post(
        reverse("assessments:submit_attempt", args=[attempt.pk]),
        {f"q{q.pk}": "1" for q in assessment.questions.all()},
    )
    assert response.status_code == 302
    attempt.refresh_from_db()
    assert attempt.passed is True

    result = client.get(reverse("assessments:attempt_result", args=[attempt.pk]))
    assert result.status_code == 200
    assert b"Passed" in result.content


@pytest.mark.django_db
def test_other_candidate_cannot_view_attempt(
    client, candidate, application, assessment, db
):
    from core.models import User
    from jobs.models import CandidateProfile

    intruder = User.objects.create_user(
        email="other@x.test", password="pw12345678", is_candidate=True
    )
    CandidateProfile.objects.create(user=intruder)
    from assessments import services

    attempt = services.start_attempt(assessment, application)
    client.force_login(intruder)
    assert client.get(
        reverse("assessments:attempt_result", args=[attempt.pk])
    ).status_code == 403
    assert client.get(
        reverse("assessments:take_assessment", args=[application.pk, assessment.pk])
    ).status_code == 403
