"""Model signals that feed the outbound event bus.

Senders are late-bound by label (``"jobs.Application"``) rather than imported,
so this module can be imported from ``AppConfig.ready`` regardless of app
loading order and without integrations becoming a hard dependency of the domain
apps it observes.

Transitions (hired, rejected, stage moved, offer accepted, interview confirmed)
need the *previous* value, which model saves do not carry. A ``pre_save``
receiver snapshots the stored row onto the instance as ``_integrations_prev``
and the matching ``post_save`` compares against it. A snapshot read costs one
extra query on updates of these five models only, and a missing snapshot (bulk
loads, fixtures) degrades to "treat every save as no transition" rather than
firing spurious events.
"""

import logging

from django.apps import apps
from django.db.models.signals import post_save, pre_save

from integrations import payloads
from integrations.events import (
    APPLICATION_CREATED,
    APPLICATION_HIRED,
    APPLICATION_REJECTED,
    APPLICATION_STAGE_CHANGED,
    ASSESSMENT_SUBMITTED,
    INTERVIEW_CONFIRMED,
    OFFER_ACCEPTED,
    emit,
)

logger = logging.getLogger(__name__)

SNAPSHOT_ATTR = "_integrations_prev"

#: model label -> the fields whose previous value a receiver needs.
WATCHED = {
    "jobs.Application": ("status", "current_stage_id"),
    "offers.Offer": ("status",),
    "scheduling.Interview": ("status",),
    "assessments.Attempt": ("submitted_at",),
}


def _snapshot(sender, instance, **kwargs):
    """Stash the currently-stored values of the watched fields."""
    fields = WATCHED.get(sender._meta.label, ())
    if not fields or instance.pk is None:
        instance.__dict__[SNAPSHOT_ATTR] = None
        return
    prev = sender.objects.filter(pk=instance.pk).values(*fields).first()
    instance.__dict__[SNAPSHOT_ATTR] = prev


def _prev(instance, field):
    prev = instance.__dict__.get(SNAPSHOT_ATTR)
    if not prev:
        return None
    return prev.get(field)


def _changed(instance, field, to):
    """True when ``field`` now equals ``to`` and previously did not."""
    return getattr(instance, field, None) == to and _prev(instance, field) != to


def _safe_emit(company, event, data):
    try:
        emit(company, event, data)
    except Exception:  # a webhook must never break a hiring action
        logger.exception("integrations: emit(%s) failed", event)


# --- jobs.Application ----------------------------------------------------
def on_application_saved(sender, instance, created, **kwargs):
    company = instance.company
    if created:
        _safe_emit(company, APPLICATION_CREATED, payloads.application_data(instance))
        return

    Application = sender
    if _changed(instance, "status", Application.REJECTED):
        _safe_emit(company, APPLICATION_REJECTED, payloads.application_data(instance))
    if _changed(instance, "status", Application.HIRED):
        _safe_emit(company, APPLICATION_HIRED, payloads.application_data(instance))
        _on_hired(instance)
    prev_stage = _prev(instance, "current_stage_id")
    if instance.current_stage_id and prev_stage != instance.current_stage_id:
        _safe_emit(company, APPLICATION_STAGE_CHANGED, payloads.application_data(instance))


def _on_hired(application):
    """Fan a hire out to the company's active HRMS connectors."""
    from integrations.services import push_hire_to_hrms

    try:
        push_hire_to_hrms(application)
    except Exception:
        logger.exception("integrations: HRMS push failed for application %s", application.pk)


# --- offers.Offer --------------------------------------------------------
def on_offer_saved(sender, instance, created, **kwargs):
    if created or not _changed(instance, "status", sender.ACCEPTED):
        return
    _safe_emit(instance.company, OFFER_ACCEPTED, payloads.offer_data(instance))


# --- scheduling.Interview ------------------------------------------------
def on_interview_saved(sender, instance, created, **kwargs):
    if not _changed(instance, "status", sender.CONFIRMED):
        return
    _safe_emit(instance.company, INTERVIEW_CONFIRMED, payloads.interview_data(instance))


# --- assessments.Attempt -------------------------------------------------
def on_attempt_saved(sender, instance, created, **kwargs):
    if instance.submitted_at is None or _prev(instance, "submitted_at") is not None:
        return
    application = instance.application
    company = getattr(application, "company", None)
    _safe_emit(company, ASSESSMENT_SUBMITTED, payloads.attempt_data(instance))


RECEIVERS = {
    "jobs.Application": on_application_saved,
    "offers.Offer": on_offer_saved,
    "scheduling.Interview": on_interview_saved,
    "assessments.Attempt": on_attempt_saved,
}


def register():
    """Connect every receiver. Idempotent (``dispatch_uid`` per model)."""
    for label, receiver in RECEIVERS.items():
        try:
            model = apps.get_model(label)
        except LookupError:  # pragma: no cover - app not installed
            logger.warning("integrations: %s not installed, events skipped", label)
            continue
        pre_save.connect(
            _snapshot, sender=model, dispatch_uid=f"integrations.snapshot.{label}"
        )
        post_save.connect(
            receiver, sender=model, dispatch_uid=f"integrations.emit.{label}"
        )


register()
