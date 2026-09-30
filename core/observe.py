"""KAN-10: Production observability helpers for the hiring pipeline.

Provides a thin ``hiring_event()`` helper that emits a structured log line
and, when Sentry is active, captures a breadcrumb.  All critical hiring
workflow events (application created, stage advanced, application rejected,
offer sent, AI scoring result) should funnel through here.

Usage::

    from core.observe import hiring_event

    hiring_event(
        "application.created",
        application_id=application.pk,
        job_id=application.job_id,
        company_id=application.job.company_id,
        candidate_id=application.candidate_id,
    )

Log format (one JSON-like line per event)::

    hiring_event event=application.created application_id=42 job_id=7 ...

Sentry breadcrumb category: ``hiring``

The module intentionally has **no Django model or settings import** at module
level so it can be imported from any signal or view without risking circular
imports.  ``sentry_sdk`` is imported lazily and silently skipped when absent.
"""

import logging
import time

logger = logging.getLogger("hiring")


def hiring_event(event: str, **kwargs) -> None:
    """Emit a structured log line for a hiring pipeline event.

    Args:
        event: Dot-separated event name, e.g. ``"application.created"``.
        **kwargs: Arbitrary key/value pairs added to the log line and Sentry
            breadcrumb.  All values are coerced to str for safe serialisation.
    """
    pairs = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info("hiring_event event=%s %s", event, pairs)

    # Sentry breadcrumb — best effort, never raises
    try:
        import sentry_sdk  # noqa: PLC0415 — lazy import by design

        sentry_sdk.add_breadcrumb(
            category="hiring",
            message=event,
            data={k: str(v) for k, v in kwargs.items()},
            level="info",
        )
    except Exception:  # pragma: no cover — Sentry not installed / not init'd
        pass


def timed_hiring_event(event: str, **kwargs):
    """Context manager: emits *event*.started and *event*.finished with duration_ms."""

    class _Timer:
        def __enter__(self):
            self._t0 = time.monotonic()
            hiring_event(f"{event}.started", **kwargs)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration_ms = int((time.monotonic() - self._t0) * 1000)
            outcome = "error" if exc_type else "ok"
            hiring_event(f"{event}.finished", outcome=outcome, duration_ms=duration_ms, **kwargs)
            return False  # do not suppress exceptions

    return _Timer()
