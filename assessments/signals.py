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
    try:
        from assessments import ai

        return ai.summarize_fit(application)
    except Exception:  # pragma: no cover - AI is strictly best-effort
        logger.warning("AI fit scoring failed for application %s", application.pk,
                       exc_info=True)
        return None


@receiver(post_save, sender=Application, dispatch_uid="assessments.score_application")
def _score_new_application(sender, instance, created, **kwargs):
    if created:
        score_application(instance)
