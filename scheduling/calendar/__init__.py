"""Calendar provider adapters.

``base`` defines the tiny interface (:class:`~scheduling.calendar.base.CalendarAdapter`);
``google`` and ``outlook`` implement it against their SDKs and are *env-gated* —
without OAuth client credentials in settings they report ``configured() is False``
and every call degrades to a no-op so nothing ever touches the network in tests.
"""

from scheduling.calendar.base import (
    CalendarAdapter,
    CalendarEvent,
    adapter_for,
    adapters,
    busy_for_user,
    delete_event_for_interview,
    upsert_event_for_interview,
)

__all__ = [
    "CalendarAdapter",
    "CalendarEvent",
    "adapter_for",
    "adapters",
    "busy_for_user",
    "delete_event_for_interview",
    "upsert_event_for_interview",
]
