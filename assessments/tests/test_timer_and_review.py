"""Server-side timer enforcement, ungraded TEXT handling and manual scoring."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from assessments import services
from assessments.models import Attempt, Question


@pytest.fixture
def text_assessment(assessment, company, skill):
    """The shared assessment plus one free-text question (5 questions total)."""
    question = Question.objects.create(
        company=company,
        skill=skill,
        kind=Question.TEXT,
        text="Explain the GIL.",
    )
    assessment.questions.add(question)
    return assessment, question


# --- 1. server-side timer -------------------------------------------------


@pytest.mark.django_db
def test_late_submission_scores_zero_even_with_answers(assessment, application):
    attempt = services.start_attempt(assessment, application)
    attempt.started_at = timezone.now() - timezone.timedelta(
        minutes=assessment.time_limit_minutes + 5
    )
    attempt.save(update_fields=["started_at"])

    services.submit_attempt(
        attempt, {str(q.pk): "1" for q in assessment.questions.all()}
    )

    attempt.refresh_from_db()
    assert attempt.score_percent == Decimal("0.00")
    assert attempt.passed is False
    assert attempt.ai_feedback == "Time limit exceeded"
    application.refresh_from_db()
    assert application.status == application.ACTIVE


@pytest.mark.django_db
def test_submission_inside_grace_is_graded(assessment, application):
    attempt = services.start_attempt(assessment, application)
    # Deadline passed 5 seconds ago: inside the 15s grace window.
    attempt.started_at = timezone.now() - timezone.timedelta(
        minutes=assessment.time_limit_minutes, seconds=-5
    )
    attempt.save(update_fields=["started_at"])
    assert services.SUBMIT_GRACE_SECONDS == 15

    services.submit_attempt(
        attempt, {str(q.pk): "1" for q in assessment.questions.all()}
    )
    attempt.refresh_from_db()
    assert attempt.score_percent == Decimal("100.00")
    assert attempt.passed is True


# --- 2. ungraded TEXT answers --------------------------------------------


@pytest.mark.django_db
def test_ungradable_text_answer_is_excluded_from_denominator(
    text_assessment, application, settings
):
    settings.ANTHROPIC_API_KEY = ""
    assessment, text_question = text_assessment
    mcqs = [q for q in assessment.questions.all() if q.is_mcq]
    attempt = services.start_attempt(assessment, application)

    answers = {str(q.pk): "1" for q in mcqs}
    answers[str(text_question.pk)] = "Global interpreter lock."
    services.submit_attempt(attempt, answers)

    attempt.refresh_from_db()
    # 4 MCQs all correct; the TEXT answer is pending, not a zero.
    assert attempt.score_percent == Decimal("100.00")
    assert attempt.passed is True
    assert attempt.needs_review is True
    assert attempt.pending_review == [text_question.pk]
    assert attempt.pending_review_count == 1
    assert "pending manual review" in attempt.ai_feedback


@pytest.mark.django_db
def test_result_page_shows_pending_review_and_zero_percent(
    client, text_assessment, application, settings
):
    settings.ANTHROPIC_API_KEY = ""
    assessment, text_question = text_assessment
    attempt = services.start_attempt(assessment, application)
    services.submit_attempt(attempt, {str(text_question.pk): "Something."})
    attempt.refresh_from_db()
    assert attempt.score_percent == Decimal("0.00")  # 4 MCQs unanswered

    client.force_login(application.candidate.user)
    response = client.get(reverse("assessments:attempt_result", args=[attempt.pk]))
    body = response.content.decode()
    assert response.status_code == 200
    assert "1 answer pending manual review" in body
    assert ">0.00<" in body  # 0% renders as 0, not as an em dash


@pytest.mark.django_db
def test_feedback_labels_questions_by_position_not_pk(
    text_assessment, application, settings
):
    settings.ANTHROPIC_API_KEY = ""
    assessment, text_question = text_assessment
    attempt = services.start_attempt(assessment, application)
    services.submit_attempt(attempt, {str(text_question.pk): "Answer."})
    attempt.refresh_from_db()
    # Questions render in assessment order; the label is the position, not the pk.
    position = [q.pk for q in assessment.questions.all()].index(text_question.pk) + 1
    assert f"Q{position}:" in attempt.ai_feedback
    assert position != text_question.pk
    assert f"Q{text_question.pk}:" not in attempt.ai_feedback


# --- manual scoring -------------------------------------------------------


@pytest.mark.django_db
def test_manual_score_regrades_and_clears_review(
    text_assessment, application, settings
):
    settings.ANTHROPIC_API_KEY = ""
    assessment, text_question = text_assessment
    attempt = services.start_attempt(assessment, application)
    services.submit_attempt(attempt, {str(text_question.pk): "Answer."})

    services.score_text_answer(attempt, text_question, 80)

    attempt.refresh_from_db()
    assert attempt.needs_review is False
    assert attempt.pending_review == []
    # 4 wrong MCQs + one 80 => 80/5
    assert attempt.score_percent == Decimal("16.00")
    assert "Manual score 80/100" in attempt.ai_feedback


@pytest.mark.django_db
def test_manual_score_rejects_out_of_range_and_mcq(text_assessment, application):
    assessment, text_question = text_assessment
    attempt = services.start_attempt(assessment, application)
    services.submit_attempt(attempt, {})
    mcq = assessment.questions.filter(kind=Question.MCQ).first()

    with pytest.raises(ValidationError):
        services.score_text_answer(attempt, text_question, 300)
    with pytest.raises(ValidationError):
        services.score_text_answer(attempt, mcq, 50)


@pytest.mark.django_db
def test_recruiter_can_post_a_manual_score(
    client, recruiter, text_assessment, application, settings
):
    settings.ANTHROPIC_API_KEY = ""
    assessment, text_question = text_assessment
    attempt = services.start_attempt(assessment, application)
    services.submit_attempt(attempt, {str(text_question.pk): "Answer."})

    client.force_login(recruiter)
    listing = client.get(
        reverse("assessments:assessment_attempts", args=[assessment.pk])
    )
    assert "Save score" in listing.content.decode()

    response = client.post(
        reverse("assessments:attempt_manual_score", args=[attempt.pk]),
        {"question": text_question.pk, "score": "100"},
    )
    assert response.status_code == 302
    attempt.refresh_from_db()
    assert attempt.manual_scores == {str(text_question.pk): 100}
    assert attempt.needs_review is False


@pytest.mark.django_db
def test_manual_score_requires_own_company(
    client, other_recruiter, text_assessment, application
):
    assessment, text_question = text_assessment
    attempt = services.start_attempt(assessment, application)
    services.submit_attempt(attempt, {})
    client.force_login(other_recruiter)
    response = client.post(
        reverse("assessments:attempt_manual_score", args=[attempt.pk]),
        {"question": text_question.pk, "score": "50"},
    )
    assert response.status_code in (403, 404)


# --- 3. stage gating -----------------------------------------------------


@pytest.mark.django_db
def test_start_attempt_requires_matching_stage(assessment, application):
    stages = list(application.job.stages.order_by("order"))
    application.current_stage = stages[0]  # Screening, not the assessment stage
    application.save(update_fields=["current_stage"])

    with pytest.raises(ValidationError):
        services.start_attempt(assessment, application)
    assert not Attempt.objects.filter(application=application).exists()


@pytest.mark.django_db
def test_start_attempt_allows_stageless_assessment(assessment, application):
    stages = list(application.job.stages.order_by("order"))
    assessment.stage = None
    assessment.save(update_fields=["stage"])
    application.current_stage = stages[0]
    application.save(update_fields=["current_stage"])

    attempt = services.start_attempt(assessment, application)
    assert attempt.pk is not None


@pytest.mark.django_db
def test_take_view_redirects_when_stage_does_not_match(
    client, assessment, application
):
    stages = list(application.job.stages.order_by("order"))
    application.current_stage = stages[0]
    application.save(update_fields=["current_stage"])
    client.force_login(application.candidate.user)

    response = client.get(
        reverse(
            "assessments:take_assessment",
            kwargs={"application_id": application.pk, "assessment_id": assessment.pk},
        )
    )
    assert response.status_code == 302


# --- 9. candidate result email -------------------------------------------


@pytest.mark.django_db
def test_submission_emails_the_candidate_their_result(
    assessment, application, settings
):
    from django.core import mail

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    attempt = services.start_attempt(assessment, application)
    mail.outbox.clear()

    services.submit_attempt(
        attempt, {str(q.pk): "1" for q in assessment.questions.all()}
    )

    subjects = [m.subject for m in mail.outbox]
    assert any(assessment.title in s for s in subjects)
    result_mail = next(m for m in mail.outbox if assessment.title in m.subject)
    assert result_mail.to == [application.candidate.user.email]
    assert "100" in result_mail.body
