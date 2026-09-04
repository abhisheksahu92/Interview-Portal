"""The outbound event bus.

``emit(company, event, payload)`` is the only way an event reaches customer
webhooks. It fans the event out to every active :class:`OutboundWebhook` in the
company that subscribes to it, records a :class:`WebhookDelivery` row per
webhook, and tries each one synchronously with a short timeout. Anything that
does not succeed immediately is left PENDING with ``next_attempt_at`` set, and
the ``deliver_webhooks`` management command (run from ``run_periodic``) picks it
up with exponential backoff.

Emitting is best-effort by construction: a webhook receiver being down, slow or
misconfigured must never break the hiring action that produced the event, so
every failure is caught and logged.
"""

import logging

logger = logging.getLogger(__name__)

# --- Event catalogue ------------------------------------------------------
APPLICATION_CREATED = "application.created"
APPLICATION_STAGE_CHANGED = "application.stage_changed"
APPLICATION_REJECTED = "application.rejected"
APPLICATION_HIRED = "application.hired"
OFFER_ACCEPTED = "offer.accepted"
INTERVIEW_CONFIRMED = "interview.confirmed"
ASSESSMENT_SUBMITTED = "assessment.submitted"

#: (name, human label) for every event a webhook may subscribe to.
EVENT_CHOICES = [
    (APPLICATION_CREATED, "Application created"),
    (APPLICATION_STAGE_CHANGED, "Application moved stage"),
    (APPLICATION_REJECTED, "Application rejected"),
    (APPLICATION_HIRED, "Candidate hired"),
    (OFFER_ACCEPTED, "Offer accepted"),
    (INTERVIEW_CONFIRMED, "Interview confirmed"),
    (ASSESSMENT_SUBMITTED, "Assessment submitted"),
]

EVENTS = [name for name, _ in EVENT_CHOICES]


def is_known_event(name) -> bool:
    return name in EVENTS


def emit(company, event, payload=None):
    """Record and attempt a delivery of ``event`` to ``company``'s webhooks.

    Returns the list of created :class:`WebhookDelivery` rows (empty when the
    company has no matching webhook, or has no ``api`` entitlement).
    """
    if company is None:
        return []
    if not is_known_event(event):
        logger.warning("integrations: refusing to emit unknown event %r", event)
        return []

    from billing.entitlements import has_feature
    from integrations.delivery import attempt_delivery, build_envelope
    from integrations.models import OutboundWebhook, WebhookDelivery

    # The integrations tier is a paid feature; without it we do not fan out.
    try:
        if not has_feature(company, "integrations"):
            return []
    except Exception:  # pragma: no cover - entitlement lookup must never break emit
        logger.exception("integrations: entitlement check failed for %s", company)
        return []

    webhooks = [
        hook
        for hook in OutboundWebhook.objects.filter(company=company, active=True)
        if hook.subscribes_to(event)
    ]
    if not webhooks:
        return []

    envelope = build_envelope(company, event, payload or {})
    deliveries = []
    for hook in webhooks:
        delivery = WebhookDelivery.objects.create(
            webhook=hook, event=event, payload=envelope
        )
        deliveries.append(delivery)
        try:
            attempt_delivery(delivery)
        except Exception:  # pragma: no cover - defensive; attempt_delivery catches
            logger.exception("integrations: delivery %s crashed", delivery.pk)
    return deliveries
