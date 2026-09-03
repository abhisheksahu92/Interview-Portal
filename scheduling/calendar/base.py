"""The calendar adapter interface plus the helpers the rest of the app calls."""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone as dj_timezone

from scheduling.models import CalendarConnection

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    """A provider-agnostic event payload."""

    summary: str
    start: datetime
    end: datetime
    description: str = ""
    location: str = ""
    attendees: list = field(default_factory=list)


class NotConfigured(RuntimeError):
    """Raised when an adapter is asked to call out without credentials."""


class CalendarAdapter:
    """Base adapter. Subclasses implement the four provider calls.

    Every public method must be safe to call when :meth:`configured` is False:
    ``busy`` returns ``[]`` and the write methods return ``None``.
    """

    provider = ""
    label = "Calendar"

    #: message shown in the UI when credentials are missing
    unconfigured_note = (
        "Calendar sync is not configured on this deployment. "
        "Ask an administrator to set the OAuth client credentials."
    )

    @classmethod
    def configured(cls) -> bool:
        raise NotImplementedError

    # -- OAuth -------------------------------------------------------------
    def authorize_url(self, redirect_uri, state):
        """The provider consent URL to send the user to."""
        raise NotImplementedError

    def exchange_code(self, code, redirect_uri, state=None):
        """Swap an OAuth ``code`` for a token dict (stored on the connection)."""
        raise NotImplementedError

    # -- Calendar ----------------------------------------------------------
    def busy(self, connection, start, end):
        """Busy ``(start, end)`` UTC intervals for ``connection`` in the window."""
        return []

    def create_event(self, connection, event):
        """Create an event; return the provider event id (or None)."""
        return None

    def update_event(self, connection, event_id, event):
        """Update an event; return the (possibly new) provider event id."""
        return event_id

    def delete_event(self, connection, event_id):
        """Delete an event. Silent when it is already gone."""
        return None


def adapters():
    """All known adapter classes keyed by provider code."""
    from scheduling.calendar.google import GoogleCalendarAdapter
    from scheduling.calendar.outlook import OutlookCalendarAdapter

    return {
        CalendarConnection.GOOGLE: GoogleCalendarAdapter,
        CalendarConnection.OUTLOOK: OutlookCalendarAdapter,
    }


def adapter_for(provider):
    """An adapter instance for ``provider``, or None when unknown."""
    cls = adapters().get(provider)
    return cls() if cls else None


def provider_status():
    """``[{provider, label, configured, note}]`` for the connect-calendar UI."""
    rows = []
    for provider, cls in adapters().items():
        rows.append(
            {
                "provider": provider,
                "label": cls.label,
                "configured": cls.configured(),
                "note": "" if cls.configured() else cls.unconfigured_note,
            }
        )
    return rows


def _live_connections(user):
    return [
        c
        for c in CalendarConnection.objects.filter(user=user, enabled=True)
        if c.is_live
    ]


def busy_for_user(user, start, end):
    """Busy UTC intervals for ``user`` across every live calendar connection.

    Never raises: a provider error is logged and treated as "no busy time
    known", so slot computation degrades to availability-only.
    """
    intervals = []
    for connection in _live_connections(user):
        adapter = adapter_for(connection.provider)
        if adapter is None or not type(adapter).configured():
            continue
        try:
            intervals.extend(adapter.busy(connection, start, end) or [])
        except Exception:  # pragma: no cover - defensive
            logger.warning("calendar busy lookup failed for %s", connection, exc_info=True)
    return intervals


def _event_for(interview):
    candidate = interview.candidate_user
    attendees = [u.email for u in interview.interviewers.all() if u.email]
    if candidate is not None and candidate.email:
        attendees.append(candidate.email)
    return CalendarEvent(
        summary=interview.summary(),
        start=interview.scheduled_start,
        end=interview.scheduled_end,
        description=interview.notes,
        location=interview.location_or_link,
        attendees=attendees,
    )


def upsert_event_for_interview(interview):
    """Push ``interview`` to every connected interviewer calendar.

    Stores provider event ids on ``interview.external_event_ids`` keyed by
    ``"<provider>:<user_id>"``. A no-op when nothing is configured.
    """
    if interview.scheduled_start is None or interview.scheduled_end is None:
        return {}
    event = _event_for(interview)
    ids = dict(interview.external_event_ids or {})
    changed = False
    for user in interview.interviewers.all():
        for connection in _live_connections(user):
            adapter = adapter_for(connection.provider)
            if adapter is None or not type(adapter).configured():
                continue
            key = f"{connection.provider}:{user.pk}"
            try:
                if ids.get(key):
                    new_id = adapter.update_event(connection, ids[key], event)
                else:
                    new_id = adapter.create_event(connection, event)
            except Exception:  # pragma: no cover - defensive
                logger.warning("calendar write failed for %s", connection, exc_info=True)
                continue
            if new_id:
                ids[key] = new_id
                changed = True
            connection.last_synced = dj_timezone.now()
            connection.save(update_fields=["last_synced"])
    if changed:
        interview.external_event_ids = ids
        interview.save(update_fields=["external_event_ids", "updated_at"])
    return ids


def delete_event_for_interview(interview):
    """Remove ``interview`` from every calendar it was pushed to."""
    ids = dict(interview.external_event_ids or {})
    if not ids:
        return
    for user in interview.interviewers.all():
        for connection in _live_connections(user):
            key = f"{connection.provider}:{user.pk}"
            event_id = ids.pop(key, None)
            if not event_id:
                continue
            adapter = adapter_for(connection.provider)
            if adapter is None or not type(adapter).configured():
                continue
            try:
                adapter.delete_event(connection, event_id)
            except Exception:  # pragma: no cover - defensive
                logger.warning("calendar delete failed for %s", connection, exc_info=True)
    interview.external_event_ids = ids
    interview.save(update_fields=["external_event_ids", "updated_at"])
