"""Candidate-facing transactional notifications for the hiring pipeline.

This module is now a thin compatibility shim: every function delegates to
``notifications.send`` with the matching event, so channel selection,
templating and the outbound log all live in the notifications app. The
function names, signatures and best-effort behaviour are unchanged — a broken
mail backend must never break an application being created or a stage moving.
"""

import logging

logger = logging.getLogger(__name__)


def _candidate_email(application):
    user = getattr(application.candidate, "user", None)
    return (getattr(user, "email", "") or "").strip()


def _context(application, extra=None):
    context = {
        "application": application,
        "job": application.job,
        "company": application.job.company,
        "candidate": application.candidate,
        "stage": application.current_stage,
    }
    context.update(extra or {})
    return context


def _send(event, application, extra=None):
    """Delegate to ``notifications.send`` and return the number of emails sent."""
    if not _candidate_email(application):
        return 0
    try:
        from notifications import api as notifications_api

        messages = notifications_api.send(
            event,
            application.candidate,
            _context(application, extra),
            company=application.job.company,
        )
    except Exception:
        logger.warning(
            "Could not send %s notification for application %s", event, application.pk,
            exc_info=True,
        )
        return 0
    return sum(
        1
        for message in messages
        if message.channel == "email" and message.status == message.SENT
    )


def send_application_received(application):
    return _send("application_received", application)


def send_stage_advanced(application):
    stage = application.current_stage
    stage_name = stage.name if stage else "the next step"
    return _send("stage_advanced", application, {"stage_name": stage_name})


def send_application_rejected(application):
    return _send("application_rejected", application)


def send_application_hired(application):
    return _send("application_hired", application)


def send_assessment_result(attempt):
    """Assessment outcome mail. Called from ``assessments`` (which may import jobs)."""
    return _send(
        "assessment_result",
        attempt.application,
        {"attempt": attempt, "assessment": attempt.assessment},
    )
