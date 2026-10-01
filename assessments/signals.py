"""Signal hooks that wire AI screening into the jobs domain.

Kept in ``assessments`` so ``jobs`` never imports this app (see ARCHITECTURE.md
cross-app import rules). Everything here is best-effort: a failure in the AI
layer must never break an application being created.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from jobs.models import Application

logger = logging.getLogger(__name__)


def score_application(application):
    """Best-effort AI fit summary/score for ``application``. Never raises."""
    from core.observe import hiring_event

    if not _llm_configured():
        logger.debug("No LLM provider configured; skipping AI fit scoring.")
        return None
    try:
        from assessments import ai

        result = ai.summarize_fit(application)
        hiring_event(
            "ai.scoring.completed",
            application_id=application.pk,
            job_id=application.job_id,
            company_id=application.job.company_id,
            has_result=bool(result),
        )
        return result
    except Exception:  # pragma: no cover - AI is strictly best-effort
        logger.warning("AI fit scoring failed for application %s", application.pk,
                       exc_info=True)
        from core.observe import hiring_event as _he
        _he("ai.scoring.failed", application_id=application.pk)
        return None


def _llm_configured():
    """Return True when at least one LLM provider is usable."""
    try:
        from core import llm
        return llm.is_configured()
    except Exception:
        return False


def async_score_application(application_id):
    """Worker task: score an application in the background."""
    try:
        application = Application.objects.get(pk=application_id)
        return score_application(application)
    except Application.DoesNotExist:
        return None


@receiver(post_save, sender=Application, dispatch_uid="assessments.score_application")
def _score_new_application(sender, instance, created, **kwargs):
    """Score brand-new applications only - updates must not re-hit the API."""
    if not created:
        return
    if kwargs.get("raw"):  # loaddata / fixtures
        return
    from core.queue import enqueue
    enqueue("assessments.signals.async_score_application", instance.pk, queue="ai")
