"""iCalendar (.ics) generation for interview invitations."""

from django.utils import timezone as dj_timezone

FILENAME = "interview.ics"
MIMETYPE = "text/calendar"

_METHODS = {
    "CANCELLED": "CANCEL",
}


def interview_ics(interview, method=None) -> bytes:
    """A single-event VCALENDAR for ``interview``.

    Uses ``icalendar`` when available and falls back to a hand-rolled VEVENT so
    emails still carry an attachment on a minimal install.
    """
    if interview.scheduled_start is None or interview.scheduled_end is None:
        return b""
    method = method or _METHODS.get(interview.status, "REQUEST")
    uid = f"interview-{interview.pk}@interview-portal"
    attendees = [u.email for u in interview.interviewers.all() if u.email]
    candidate = interview.candidate_user
    if candidate is not None and candidate.email:
        attendees.append(candidate.email)

    try:
        from icalendar import Calendar, Event
    except ImportError:  # pragma: no cover - icalendar is pinned
        return _fallback(interview, uid, method)

    cal = Calendar()
    cal.add("prodid", "-//Interview Portal//Scheduling//EN")
    cal.add("version", "2.0")
    cal.add("method", method)
    event = Event()
    event.add("uid", uid)
    event.add("summary", interview.summary())
    event.add("dtstart", interview.scheduled_start)
    event.add("dtend", interview.scheduled_end)
    event.add("dtstamp", dj_timezone.now())
    event.add("status", "CANCELLED" if method == "CANCEL" else "CONFIRMED")
    event.add("sequence", 1 if method == "CANCEL" else 0)
    if interview.location_or_link:
        event.add("location", interview.location_or_link)
    if interview.notes:
        event.add("description", interview.notes)
    for email in attendees:
        event.add("attendee", f"MAILTO:{email}")
    cal.add_component(event)
    return cal.to_ical()


def _fallback(interview, uid, method):  # pragma: no cover - icalendar is pinned
    def stamp(value):
        return value.astimezone(dj_timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Interview Portal//Scheduling//EN",
        f"METHOD:{method}",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"SUMMARY:{interview.summary()}",
        f"DTSTART:{stamp(interview.scheduled_start)}",
        f"DTEND:{stamp(interview.scheduled_end)}",
        f"DTSTAMP:{stamp(dj_timezone.now())}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines).encode()
