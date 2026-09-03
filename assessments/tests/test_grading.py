from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from assessments import services
from assessments.models import Attempt, Question
from jobs.models import Application


@pytest.mark.django_db
def test_mcq_grading_all_correct(assessment, application):
    attempt = services.start_attempt(assessment, application)
    answers = {str(q.pk): "1" for q in assessment.questions.all()}
    services.submit_attempt(attempt, answers)
    attempt.refresh_from_db()
    assert attempt.score_percent == Decimal("100.00")
    assert attempt.passed is True


@pytest.mark.django_db
def test_mcq_grading_partial_and_fail_threshold(assessment, application):
    questions = list(assessment.questions.order_by("id"))
    attempt = services.start_attempt(assessment, application)
    answers = {str(questions[0].pk): "1", str(questions[1].pk): "0"}
    services.submit_attempt(attempt, answers)
    attempt.refresh_from_db()
    assert attempt.score_percent == Decimal("25.00")
    assert attempt.passed is False


@pytest.mark.django_db
def test_pass_mark_boundary_is_inclusive(assessment, application):
    questions = list(assessment.questions.order_by("id"))
    assessment.pass_mark_percent = 50
    assessment.save()
    attempt = services.start_attempt(assessment, application)
    services.submit_attempt(
        attempt, {str(questions[0].pk): "1", str(questions[1].pk): "1"}
    )
    attempt.refresh_from_db()
    assert attempt.score_percent == Decimal("50.00")
    assert attempt.passed is True


@pytest.mark.django_db
def test_pass_advances_application_stage(assessment, application):
    before = application.current_stage
    attempt = services.start_attempt(assessment, application)
    services.submit_attempt(
        attempt, {str(q.pk): "1" for q in assessment.questions.all()}
    )
    application.refresh_from_db()
    assert application.current_stage != before
    assert application.current_stage.order == before.order + 1


@pytest.mark.django_db
def test_fail_does_not_advance(assessment, application):
    before = application.current_stage_id
    attempt = services.start_attempt(assessment, application)
    services.submit_attempt(attempt, {})
    application.refresh_from_db()
    assert application.current_stage_id == before


@pytest.mark.django_db
def test_pass_on_other_stage_does_not_advance(assessment, application, job):
    """An assessment bound to another stage is not even startable."""
    assessment.stage = job.stages.order_by("order")[3]
    assessment.save()
    before = application.current_stage_id
    with pytest.raises(ValidationError):
        services.start_attempt(assessment, application)
    application.refresh_from_db()
    assert application.current_stage_id == before


@pytest.mark.django_db
def test_start_attempt_is_idempotent_and_blocks_resubmission(assessment, application):
    first = services.start_attempt(assessment, application)
    assert services.start_attempt(assessment, application).pk == first.pk
    services.submit_attempt(first, {})
    assert Attempt.objects.filter(application=application).count() == 1
    with pytest.raises(ValidationError):
        services.start_attempt(assessment, application)
    with pytest.raises(ValidationError):
        services.submit_attempt(first, {})


@pytest.mark.django_db
def test_start_attempt_rejects_expired_and_inactive(assessment, application):
    attempt = services.start_attempt(assessment, application)
    assessment.time_limit_minutes = 0
    assessment.save()
    attempt.refresh_from_db()
    assert attempt.is_expired is True
    with pytest.raises(ValidationError):
        services.start_attempt(assessment, application)

    assessment.is_active = False
    assessment.save()
    Attempt.objects.all().delete()
    with pytest.raises(ValidationError):
        services.start_attempt(assessment, application)


@pytest.mark.django_db
def test_start_attempt_rejects_mismatched_job(assessment, application, company, candidate):
    from jobs.models import Job

    other_job = Job.objects.create(company=company, title="QA")
    other_application = Application.objects.create(job=other_job, candidate=candidate)
    with pytest.raises(ValidationError):
        services.start_attempt(assessment, other_application)


@pytest.mark.django_db
def test_expired_empty_submission_scores_zero(assessment, application):
    from django.utils import timezone

    attempt = services.start_attempt(assessment, application)
    attempt.started_at = timezone.now() - timezone.timedelta(
        minutes=assessment.time_limit_minutes + 1
    )
    attempt.save(update_fields=["started_at"])
    services.submit_attempt(attempt, {})
    attempt.refresh_from_db()
    assert attempt.score_percent == 0
    assert attempt.passed is False
    assert attempt.ai_feedback == "Time limit exceeded"


@pytest.mark.django_db
def test_text_question_graded_by_ai(monkeypatch, company, job, application, skill):
    from assessments.models import Assessment

    question = Question.objects.create(
        company=company, skill=skill, kind=Question.TEXT, text="Explain the GIL."
    )
    assessment = Assessment.objects.create(
        job=job, stage=application.current_stage, title="Text screen"
    )
    assessment.questions.add(question)

    monkeypatch.setattr("assessments.ai.grade_text_answer", lambda q, a: 80)
    attempt = services.start_attempt(assessment, application)
    services.submit_attempt(attempt, {str(question.pk): "It is a lock."})
    attempt.refresh_from_db()
    assert attempt.score_percent == Decimal("80.00")
    assert attempt.passed is True
    assert "AI score 80" in attempt.ai_feedback


@pytest.mark.django_db
def test_text_question_pending_when_ai_unavailable(
    monkeypatch, company, job, application, skill
):
    from assessments.models import Assessment

    question = Question.objects.create(
        company=company, skill=skill, kind=Question.TEXT, text="Explain the GIL."
    )
    assessment = Assessment.objects.create(job=job, title="Text screen")
    assessment.questions.add(question)

    monkeypatch.setattr("assessments.ai.grade_text_answer", lambda q, a: None)
    attempt = services.start_attempt(assessment, application)
    services.submit_attempt(attempt, {str(question.pk): "something"})
    attempt.refresh_from_db()
    # Nothing gradable: the attempt stays open for manual review instead of 0.
    assert attempt.score_percent is None
    assert attempt.passed is None
    assert attempt.needs_review is True
    assert "manual review" in attempt.ai_feedback


@pytest.mark.django_db
def test_grade_with_no_questions(job, application):
    from assessments.models import Assessment

    assessment = Assessment.objects.create(job=job, title="Empty")
    attempt = services.start_attempt(assessment, application)
    assert attempt.grade() == 0
    assert attempt.passed is False
