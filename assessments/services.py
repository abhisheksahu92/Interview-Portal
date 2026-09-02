"""Attempt lifecycle services: starting, submitting and pipeline advancement."""

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from assessments.models import Attempt

logger = logging.getLogger(__name__)


def start_attempt(assessment, application):
    """Return the candidate's attempt at ``assessment``, creating it once.

    Raises ``ValidationError`` when the assessment is inactive, belongs to a
    different job, was already submitted, or the time limit has already run out.
    """
    if assessment.job_id != application.job_id:
        raise ValidationError("This assessment does not belong to the applied job.")
    if not assessment.is_active:
        raise ValidationError("This assessment is not currently active.")

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

    expired = attempt.is_expired
    if answers:
        attempt.answers = {str(k): v for k, v in answers.items()}
    attempt.submitted_at = timezone.now()
    attempt.save(update_fields=["answers", "submitted_at"])

    if expired and not attempt.answers:
        attempt.score_percent = 0
        attempt.passed = False
        attempt.ai_feedback = "Not submitted before the time limit."
        attempt.save(update_fields=["score_percent", "passed", "ai_feedback"])
        return attempt

    attempt.grade()

    if attempt.passed:
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
    return attempt
