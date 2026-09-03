"""Attempt lifecycle services: starting, submitting and pipeline advancement."""

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from assessments.models import Attempt

logger = logging.getLogger(__name__)

#: Clock skew / in-flight request allowance on top of the time limit.
SUBMIT_GRACE_SECONDS = 15


def _notify_result(attempt):
    """Best-effort "your result is in" email to the candidate."""
    try:
        from jobs import emails

        emails.send_assessment_result(attempt)
    except Exception:  # pragma: no cover - notifications never break grading
        logger.warning("Could not email result for attempt %s", attempt.pk, exc_info=True)


def score_text_answer(attempt, question, score):
    """Recruiter action: store a manual 0-100 score for one TEXT answer, regrade.

    Advances the pipeline if the regrade turns the attempt into a pass.
    """
    if question.is_mcq:
        raise ValidationError("Only free-text answers are scored manually.")
    if not attempt.assessment.questions.filter(pk=question.pk).exists():
        raise ValidationError("That question is not part of this assessment.")
    try:
        score = int(score)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Enter a whole number between 0 and 100.") from exc
    if not 0 <= score <= 100:
        raise ValidationError("Enter a whole number between 0 and 100.")
    attempt.set_manual_score(question, score)
    _advance_on_pass(attempt)
    return attempt


def _advance_on_pass(attempt):
    if not attempt.passed:
        return
    application = attempt.application
    stage_id = attempt.assessment.stage_id
    if stage_id and application.current_stage_id == stage_id:
        try:
            application.advance()
        except Exception:
            logger.exception(
                "Could not advance application %s after a passed attempt.",
                application.pk,
            )


def start_attempt(assessment, application):
    """Return the candidate's attempt at ``assessment``, creating it once.

    Raises ``ValidationError`` when the assessment is inactive, belongs to a
    different job or stage, was already submitted, or the time limit has run out.
    """
    if assessment.job_id != application.job_id:
        raise ValidationError("This assessment does not belong to the applied job.")
    if not assessment.is_active:
        raise ValidationError("This assessment is not currently active.")
    if (
        assessment.stage_id is not None
        and application.current_stage_id != assessment.stage_id
    ):
        raise ValidationError(
            "This assessment is not available at your current pipeline stage."
        )

    attempt = Attempt.objects.filter(
        assessment=assessment, application=application
    ).first()
    if attempt is None:
        return Attempt.objects.create(
            assessment=assessment, application=application, started_at=timezone.now()
        )
    if attempt.submitted_at is not None:
        raise ValidationError("You have already submitted this assessment.")
    if attempt.is_expired:
        raise ValidationError("The time limit for this assessment has expired.")
    return attempt


@transaction.atomic
def submit_attempt(attempt, answers=None):
    """Store ``answers``, grade the attempt and advance the pipeline on a pass."""
    if attempt.submitted_at is not None:
        raise ValidationError("This attempt has already been submitted.")

    now = timezone.now()
    # Server-side clock is authoritative: a late POST scores zero even if the
    # browser managed to send answers.
    late = now > attempt.deadline + timezone.timedelta(seconds=SUBMIT_GRACE_SECONDS)
    if answers:
        attempt.answers = {str(k): v for k, v in answers.items()}
    attempt.submitted_at = now
    attempt.save(update_fields=["answers", "submitted_at"])

    if late:
        attempt.score_percent = 0
        attempt.passed = False
        attempt.needs_review = False
        attempt.pending_review = []
        attempt.ai_feedback = "Time limit exceeded"
        attempt.save(
            update_fields=[
                "score_percent",
                "passed",
                "needs_review",
                "pending_review",
                "ai_feedback",
            ]
        )
        _notify_result(attempt)
        return attempt

    attempt.grade()
    _notify_result(attempt)

    _advance_on_pass(attempt)
    return attempt
