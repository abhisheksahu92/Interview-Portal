"""Auto-capture applicants into the company's talent pool."""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="jobs.Application", dispatch_uid="talent_capture_applicant")
def capture_applicant_profile(sender, instance, created, **kwargs):
    """Mirror every application's candidate into ``TalentProfile(source=APPLICANT)``.

    Best-effort: a failure here must never break an application being created.
    """
    if not created:
        return
    from talent.services import capture_applicant

    try:
        capture_applicant(instance)
    except Exception:
        logger.warning(
            "Could not capture application %s into the talent pool.",
            getattr(instance, "pk", "?"),
            exc_info=True,
        )
