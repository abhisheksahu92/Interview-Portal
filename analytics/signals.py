"""Signals that append :class:`analytics.models.StageTransition` history rows.

``jobs`` never imports ``analytics``; the wiring lives here and is registered in
:meth:`analytics.apps.AnalyticsConfig.ready`.
"""

from django.db.models.signals import post_save, pre_save
from django.utils import timezone

PREV_ATTR = "_analytics_prev"


def remember_previous_state(sender, instance, **kwargs):
    """pre_save: stash the stage/status currently stored in the database."""
    if not instance.pk:
        setattr(instance, PREV_ATTR, None)
        return
    previous = (
        sender.objects.filter(pk=instance.pk)
        .values_list("current_stage_id", "status")
        .first()
    )
    setattr(instance, PREV_ATTR, previous)


def record_transition(sender, instance, created, **kwargs):
    """post_save: write a transition row when the stage or status changed."""
    from analytics.models import StageTransition

    previous = getattr(instance, PREV_ATTR, None)
    if created:
        from_stage_id = None
    else:
        if previous is None:
            return
        from_stage_id, previous_status = previous
        if from_stage_id == instance.current_stage_id and previous_status == instance.status:
            return
    StageTransition.objects.create(
        application=instance,
        from_stage_id=from_stage_id,
        to_stage_id=instance.current_stage_id,
        status_after=instance.status,
        at=timezone.now(),
    )
    setattr(instance, PREV_ATTR, (instance.current_stage_id, instance.status))


def register():
    """Connect the signal pair (idempotent thanks to dispatch_uid)."""
    from jobs.models import Application

    pre_save.connect(
        remember_previous_state, sender=Application, dispatch_uid="analytics_prev_state"
    )
    post_save.connect(
        record_transition, sender=Application, dispatch_uid="analytics_record_transition"
    )
