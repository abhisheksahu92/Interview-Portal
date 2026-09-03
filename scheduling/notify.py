"""Outbound messaging for scheduling events.

Prefers the notifications app's single entrypoint
``notifications.send(event, recipient, context, company)`` via a late import, and
falls back to ``django.core.mail`` with an ``.ics`` attachment when that app is
absent or raises. Never lets a delivery problem break scheduling.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage

from scheduling.ics import FILENAME, MIMETYPE, interview_ics

logger = logging.getLogger(__name__)

#: notifications-app event names used by this app
INTERVIEW_SCHEDULED = "interview_scheduled"
INTERVIEW_PROPOSED = "interview_proposed"
INTERVIEW_RESCHEDULED = "interview_rescheduled"
INTERVIEW_CANCELLED = "interview_cancelled"
REMINDER_24H = "reminder_24h"
REMINDER_1H = "reminder_1h"

_SUBJECTS = {
    INTERVIEW_PROPOSED: "Choose a time for your interview",
    INTERVIEW_SCHEDULED: "Your interview is confirmed",
    INTERVIEW_RESCHEDULED: "Your interview has been rescheduled",
    INTERVIEW_CANCELLED: "Your interview has been cancelled",
    REMINDER_24H: "Reminder: your interview is tomorrow",
    REMINDER_1H: "Reminder: your interview starts soon",
}


def booking_url(interview):
    """Absolute-ish booking URL for ``interview`` (site base from settings)."""
    base = (getattr(settings, "SITE_BASE_URL", "") or "").rstrip("/")
    return f"{base}{interview.booking_path()}"


def interview_context(interview, extra=None):
    """Template context shared by every scheduling notification."""
    start = interview.local_start()
    context = {
        "interview_id": interview.pk,
        "job_title": interview.application.job.title,
        "company_name": interview.company.name,
        "stage": interview.stage.name if interview.stage else "Interview",
        "status": interview.status,
        "timezone": interview.timezone,
        "when": start.strftime("%a %d %b %Y, %H:%M") if start else "",
        "when_iso": interview.scheduled_start.isoformat() if interview.scheduled_start else "",
        "location_or_link": interview.location_or_link,
        "booking_url": booking_url(interview),
        "interviewers": [u.get_full_name() or u.email for u in interview.interviewers.all()],
    }
    if extra:
        context.update(extra)
    return context


def _body(event, context):
    lines = [
        f"{_SUBJECTS.get(event, 'Interview update')}",
        "",
        f"Role: {context['job_title']} ({context['company_name']})",
        f"Stage: {context['stage']}",
    ]
    if context["when"]:
        lines.append(f"When: {context['when']} ({context['timezone']})")
    if context["location_or_link"]:
        lines.append(f"Where: {context['location_or_link']}")
    lines += ["", f"Manage your interview: {context['booking_url']}", ""]
    return "\n".join(lines)


def _fallback_email(event, recipient, interview, context):
    """Plain email with an .ics attachment when notifications is unavailable."""
    email = getattr(recipient, "email", recipient)
    if not email:
        return False
    message = EmailMessage(
        subject=f"{_SUBJECTS.get(event, 'Interview update')} — {context['job_title']}",
        body=_body(event, context),
        to=[email],
    )
    if interview is not None and interview.scheduled_start is not None:
        payload = interview_ics(interview)
        if payload:
            message.attach(FILENAME, payload, MIMETYPE)
    message.send(fail_silently=True)
    return True


def notify(event, recipient, interview, extra=None):
    """Send one scheduling notification. Returns True when something was sent."""
    if recipient is None:
        return False
    context = interview_context(interview, extra)
    company = interview.company
    try:
        from notifications import send as notifications_send  # late import by design

        notifications_send(event, recipient, context, company)
        return True
    except Exception:
        logger.debug("notifications app unavailable; falling back to email", exc_info=True)
    try:
        return _fallback_email(event, recipient, interview, context)
    except Exception:  # pragma: no cover - defensive
        logger.warning("scheduling email delivery failed", exc_info=True)
        return False


def notify_candidate(event, interview, extra=None):
    return notify(event, interview.candidate_user, interview, extra)


def notify_interviewers(event, interview, extra=None):
    sent = 0
    for user in interview.interviewers.all():
        if notify(event, user, interview, extra):
            sent += 1
    return sent
