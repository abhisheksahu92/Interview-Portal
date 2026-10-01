"""KAN-11: Server-side PostHog analytics for the core hiring funnel.

The browser snippet (injected via core.context_processors.analytics) covers
page views and frontend interactions.  This module adds *server-side* event
capture for the critical funnel steps that happen in backend code and would
otherwise be invisible to product analytics.

Events captured:
  - application_submitted    — candidate applied to a job
  - application_advanced     — recruiter moved a candidate forward
  - application_rejected     — recruiter or auto-review rejected
  - stage_reviewed           — interviewer submitted a stage review
  - offer_sent               — offer emailed to candidate
  - offer_accepted           — candidate signed the offer
  - offer_declined           — candidate declined the offer
  - ai_scoring_completed     — AI fit score attached to an application
  - job_created              — new job posted

Usage::

    from core.analytics import capture

    capture(
        distinct_id=str(user.pk),         # company member or candidate user pk as str
        event="application_submitted",
        properties={
            "application_id": application.pk,
            "job_id": application.job_id,
            "company_id": application.job.company_id,
        },
    )

When ``POSTHOG_KEY`` is not set (dev, CI), the call is a no-op and never
raises.  The PostHog client is initialised once at import time so there is no
per-request overhead.
"""

import logging

logger = logging.getLogger(__name__)

_client = None  # Lazy-initialised below


def _get_client():
    """Return a configured PostHog client, or None if PostHog is not set up."""
    global _client  # noqa: PLW0603 - module-level singleton
    if _client is not None:
        return _client

    try:
        from django.conf import settings
        import posthog

        key = getattr(settings, "POSTHOG_KEY", "") or ""
        host = getattr(settings, "POSTHOG_HOST", "https://eu.i.posthog.com") or ""
        if not key:
            return None

        client = posthog.Posthog(
            api_key=key,
            host=host,
            # In tests and dev, disable the background flush thread so events
            # are captured synchronously or discarded immediately.
            on_error=lambda e, items: logger.debug("PostHog error: %s", e),
        )
        # Disable noisy internal logging from the PostHog library.
        logging.getLogger("posthog").setLevel(logging.WARNING)
        _client = client
        return _client
    except Exception:
        logger.debug("PostHog client could not be initialised.", exc_info=True)
        return None


def capture(distinct_id: str, event: str, properties: dict | None = None) -> None:
    """Send a server-side event to PostHog.  Never raises.

    Args:
        distinct_id: A stable identifier for the actor — use the Django user PK
            (as a string) or a company/candidate UUID.
        event: Snake-case event name, e.g. ``"application_submitted"``.
        properties: Arbitrary key/value pairs.  Keep values serialisable
            (str, int, float, bool).  PII (emails, names) should be avoided.
    """
    client = _get_client()
    if client is None:
        return
    try:
        client.capture(
            distinct_id=str(distinct_id),
            event=event,
            properties=properties or {},
        )
    except Exception:
        logger.debug("PostHog capture failed for event=%s.", event, exc_info=True)


def identify(distinct_id: str, properties: dict | None = None) -> None:
    """Update the PostHog person record for ``distinct_id``.  Never raises.

    Use sparingly — only when a stable, non-PII trait changes (e.g. plan tier,
    role).  Do NOT send email addresses or real names.
    """
    client = _get_client()
    if client is None:
        return
    try:
        client.identify(
            distinct_id=str(distinct_id),
            properties=properties or {},
        )
    except Exception:
        logger.debug("PostHog identify failed for %s.", distinct_id, exc_info=True)
