"""Signal receivers for the scheduling app.

Registered from :meth:`scheduling.apps.SchedulingConfig.ready`. The only
receiver auto-creates an interview proposal when an application lands on an
INTERVIEW or HR stage — but only when the company's plan includes the
``scheduling`` feature and someone has declared availability.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

#: set to False in tests that must not trigger auto-proposals
AUTO_PROPOSE_ENABLED = True


@receiver(post_save, sender="jobs.Application", dispatch_uid="scheduling_auto_propose")
def auto_propose_on_stage_entry(sender, instance, **kwargs):
    """Propose an interview when an application enters an INTERVIEW/HR stage."""
    if not AUTO_PROPOSE_ENABLED:
        return
    from scheduling import services

    try:
        services.auto_propose(instance)
    except Exception:  # pragma: no cover - never break the caller's save
        logger.warning("auto-propose failed for application %s", instance.pk, exc_info=True)


def register():
    """Import-time hook; connecting happens via the decorator above."""
    return True
