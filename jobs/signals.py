"""Candidate notification hooks for pipeline transitions.

We snapshot ``status`` / ``current_stage_id`` when an Application is loaded and
compare on save, so every write path (services, admin, API, web) notifies the
candidate exactly once per real transition. Mail sending is best-effort.
"""

import logging

from django.db.models.signals import post_init, post_save
from django.dispatch import receiver

from jobs import emails
from jobs.models import Application

logger = logging.getLogger(__name__)

_SNAPSHOT = "_jobs_snapshot"


def _snapshot(instance):
    return (instance.status, instance.current_stage_id)


@receiver(post_init, sender=Application, dispatch_uid="jobs.application_snapshot")
def _remember_state(sender, instance, **kwargs):
    setattr(instance, _SNAPSHOT, _snapshot(instance))


@receiver(post_save, sender=Application, dispatch_uid="jobs.application_notify")
def _notify_on_transition(sender, instance, created, **kwargs):
    if kwargs.get("raw"):  # loaddata / fixtures
        return
    previous = getattr(instance, _SNAPSHOT, None)
    setattr(instance, _SNAPSHOT, _snapshot(instance))
    try:
        if created:
            emails.send_application_received(instance)
            return
        if previous is None:
            return
        old_status, old_stage_id = previous
        if instance.status != old_status:
            if instance.status == Application.REJECTED:
                emails.send_application_rejected(instance)
                return
            if instance.status == Application.HIRED:
                emails.send_application_hired(instance)
                return
        if (
            instance.status == Application.ACTIVE
            and instance.current_stage_id
            and instance.current_stage_id != old_stage_id
        ):
            emails.send_stage_advanced(instance)
    except Exception:  # pragma: no cover - notifications never break a write
        logger.warning(
            "Candidate notification failed for application %s", instance.pk,
            exc_info=True,
        )
