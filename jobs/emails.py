"""Candidate-facing transactional email for the hiring pipeline.

Every function here is best-effort: a broken mail backend must never break an
application being created or a stage transition.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _candidate_email(application):
    user = getattr(application.candidate, "user", None)
    return (getattr(user, "email", "") or "").strip()


def _send(template, subject, application, extra=None):
    """Render ``jobs/email/<template>.{txt,html}`` and mail the candidate."""
    recipient = _candidate_email(application)
    if not recipient:
        return 0
    context = {
        "application": application,
        "job": application.job,
        "company": application.job.company,
        "candidate": application.candidate,
        "stage": application.current_stage,
        "site_name": "Interview Portal",
    }
    context.update(extra or {})
    try:
        text_body = render_to_string(f"jobs/email/{template}.txt", context)
        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        try:
            message.attach_alternative(
                render_to_string(f"jobs/email/{template}.html", context), "text/html"
            )
        except Exception:  # pragma: no cover - html part is optional
            logger.debug("No HTML part for %s", template)
        return message.send()
    except Exception:
        logger.warning(
            "Could not send %s email for application %s", template, application.pk,
            exc_info=True,
        )
        return 0


def send_application_received(application):
    return _send(
        "application_received",
        f"We received your application for {application.job.title}",
        application,
    )


def send_stage_advanced(application):
    stage = application.current_stage
    stage_name = stage.name if stage else "the next step"
    return _send(
        "stage_advanced",
        f"You have moved to {stage_name} for {application.job.title}",
        application,
        {"stage_name": stage_name},
    )


def send_application_rejected(application):
    return _send(
        "application_rejected",
        f"Update on your application for {application.job.title}",
        application,
    )


def send_application_hired(application):
    return _send(
        "application_hired",
        f"Great news about {application.job.title}",
        application,
    )


def send_assessment_result(attempt):
    """Assessment outcome mail. Called from ``assessments`` (which may import jobs)."""
    return _send(
        "assessment_result",
        f"Your {attempt.assessment.title} result",
        attempt.application,
        {"attempt": attempt, "assessment": attempt.assessment},
    )
