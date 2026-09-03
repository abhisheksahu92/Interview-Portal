"""Auto-invite candidates when an application enters a video-screened stage."""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="jobs.Application", dispatch_uid="video_auto_invite")
def auto_invite_on_stage(sender, instance, **kwargs):
    """Create + notify a video invite when the current stage has an active screen."""
    from jobs.models import Application
    from video.services import create_invite, screen_for_stage

    if instance.status != Application.ACTIVE or instance.current_stage_id is None:
        return
    try:
        screen = screen_for_stage(instance.current_stage)
        if screen is None:
            return
        create_invite(instance, screen)
    except Exception:  # pragma: no cover - never break an application save
        logger.exception("Auto video invite failed for application %s.", instance.pk)
