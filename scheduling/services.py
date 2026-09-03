"""Scheduling domain services.

Public API::

    free_slots(interviewers, date_range, duration_min=60, tz="UTC") -> list[Slot]
    propose_interview(application, interviewers, duration=60, ...) -> Interview
    confirm(interview, start) -> Interview
    reschedule(interview, start) -> Interview
    cancel(interview) -> Interview

All datetimes crossing this boundary are timezone-aware; everything persisted is
UTC. ``timezone`` strings are IANA names resolved with :mod:`zoneinfo`.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from django.db import transaction
from django.utils import timezone as dj_timezone

from scheduling import notify as notifications
from scheduling.models import (
    DEFAULT_TIMEZONE,
    Interview,
    InterviewerAvailability,
    InterviewSlotProposal,
    valid_timezone,
    zone,
)

logger = logging.getLogger(__name__)

#: slots are offered on this grid (minutes)
SLOT_STEP_MINUTES = 30
#: how far ahead the candidate booking page looks
BOOKING_HORIZON_DAYS = 14
#: minimum lead time before a slot may be offered
MIN_LEAD_MINUTES = 60
DEFAULT_DURATION_MINUTES = 60


@dataclass(frozen=True)
class Slot:
    """A bookable interval. ``start``/``end`` are aware UTC datetimes."""

    start: datetime
    end: datetime

    def local(self, tz):
        tzinfo = zone(tz)
        return self.start.astimezone(tzinfo), self.end.astimezone(tzinfo)

    @property
    def key(self):
        """Stable form used in form fields and URLs."""
        return self.start.astimezone(UTC).isoformat()


# ---------------------------------------------------------------- helpers


def _as_utc(value):
    if value is None:
        return None
    if dj_timezone.is_naive(value):
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_slot_key(value):
    """Inverse of :attr:`Slot.key`; returns an aware UTC datetime or None."""
    if not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return None


def normalize_range(date_range):
    """Coerce ``date_range`` into an aware ``(start_utc, end_utc)`` pair.

    Accepts a ``(datetime, datetime)`` pair or a ``(date, date)`` pair (the end
    date is inclusive, expanded to end-of-day UTC).
    """
    start, end = date_range
    if isinstance(start, datetime):
        start = _as_utc(start)
    else:
        start = datetime.combine(start, time.min, tzinfo=UTC)
    if isinstance(end, datetime):
        end = _as_utc(end)
    elif isinstance(end, date):
        end = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
    return start, end


def default_range(days=BOOKING_HORIZON_DAYS, now=None):
    """The default ``(start, end)`` booking window starting from now."""
    now = now or dj_timezone.now()
    return now, now + timedelta(days=days)


def _merge(intervals):
    """Merge overlapping ``(start, end)`` intervals."""
    ordered = sorted((i for i in intervals if i[0] < i[1]), key=lambda i: i[0])
    merged = []
    for begin, finish in ordered:
        if merged and begin <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], finish))
        else:
            merged.append((begin, finish))
    return merged


def _subtract(windows, busy):
    """Remove ``busy`` intervals from ``windows`` (both merged, UTC)."""
    result = []
    busy = _merge(busy)
    for begin, finish in windows:
        cursor = begin
        for block_start, block_end in busy:
            if block_end <= cursor or block_start >= finish:
                continue
            if block_start > cursor:
                result.append((cursor, min(block_start, finish)))
            cursor = max(cursor, block_end)
            if cursor >= finish:
                break
        if cursor < finish:
            result.append((cursor, finish))
    return [i for i in result if i[0] < i[1]]


def _intersect(a, b):
    """Intersection of two merged interval lists."""
    out = []
    for a_start, a_end in a:
        for b_start, b_end in b:
            start, end = max(a_start, b_start), min(a_end, b_end)
            if start < end:
                out.append((start, end))
    return _merge(out)


def availability_windows(user, window_start, window_end, company=None):
    """UTC intervals ``user`` declared available inside the given window."""
    rows = InterviewerAvailability.objects.filter(user=user)
    if company is not None:
        rows = rows.filter(company=company)
    rows = list(rows)
    if not rows:
        return []
    windows = []
    # Walk a day either side so windows crossing UTC midnight are included.
    day = (window_start - timedelta(days=1)).date()
    last = (window_end + timedelta(days=1)).date()
    while day <= last:
        for row in rows:
            tzinfo = row.tzinfo
            local_day = day
            if local_day.weekday() != row.weekday:
                continue
            begin = datetime.combine(local_day, row.start, tzinfo=tzinfo)
            finish = datetime.combine(local_day, row.end, tzinfo=tzinfo)
            if finish <= begin:  # window wrapping midnight
                finish += timedelta(days=1)
            begin, finish = _as_utc(begin), _as_utc(finish)
            begin, finish = max(begin, window_start), min(finish, window_end)
            if begin < finish:
                windows.append((begin, finish))
        day += timedelta(days=1)
    return _merge(windows)


def booked_intervals(users, window_start, window_end, exclude=None):
    """UTC intervals already taken by interviews for any of ``users``."""
    qs = (
        Interview.objects.filter(
            interviewers__in=list(users),
            status__in=Interview.BLOCKING_STATUSES,
            scheduled_start__isnull=False,
            scheduled_end__isnull=False,
            scheduled_start__lt=window_end,
            scheduled_end__gt=window_start,
        )
        .distinct()
        .values_list("id", "scheduled_start", "scheduled_end")
    )
    exclude_id = getattr(exclude, "pk", exclude)
    return [
        (_as_utc(start), _as_utc(end))
        for pk, start, end in qs
        if exclude_id is None or pk != exclude_id
    ]


def _calendar_busy(user, window_start, window_end):
    try:
        from scheduling.calendar import busy_for_user

        return [
            (_as_utc(a), _as_utc(b)) for a, b in busy_for_user(user, window_start, window_end)
        ]
    except Exception:  # pragma: no cover - defensive
        logger.warning("calendar busy lookup failed", exc_info=True)
        return []


# ---------------------------------------------------------------- slots


def free_slots(
    interviewers,
    date_range=None,
    duration_min=DEFAULT_DURATION_MINUTES,
    tz=DEFAULT_TIMEZONE,
    company=None,
    exclude_interview=None,
    limit=None,
    now=None,
    min_lead_minutes=MIN_LEAD_MINUTES,
):
    """Slots where **every** interviewer is free for ``duration_min`` minutes.

    Intersects each interviewer's weekly availability, then subtracts existing
    interviews and (when a calendar is connected) external busy blocks. Slots
    are laid out on a :data:`SLOT_STEP_MINUTES` grid anchored to ``tz`` so the
    times look natural to whoever is booking.
    """
    interviewers = [u for u in (interviewers or []) if u is not None]
    if not interviewers or duration_min <= 0:
        return []

    window_start, window_end = normalize_range(date_range or default_range(now=now))
    now = _as_utc(now or dj_timezone.now())
    earliest = now + timedelta(minutes=min_lead_minutes or 0)
    window_start = max(window_start, earliest)
    if window_start >= window_end:
        return []

    combined = None
    for user in interviewers:
        windows = availability_windows(user, window_start, window_end, company=company)
        if not windows:
            return []
        windows = _subtract(
            windows,
            booked_intervals([user], window_start, window_end, exclude=exclude_interview)
            + _calendar_busy(user, window_start, window_end),
        )
        if not windows:
            return []
        combined = windows if combined is None else _intersect(combined, windows)
        if not combined:
            return []

    duration = timedelta(minutes=duration_min)
    step = timedelta(minutes=min(SLOT_STEP_MINUTES, duration_min))
    tzinfo = zone(valid_timezone(tz))
    slots = []
    for begin, finish in combined:
        cursor = _grid_start(begin, tzinfo, step)
        while cursor + duration <= finish:
            if cursor >= window_start:
                slots.append(Slot(cursor, cursor + duration))
                if limit and len(slots) >= limit:
                    return slots
            cursor += step
    return slots


def _grid_start(moment, tzinfo, step):
    """Round ``moment`` up to the next ``step`` boundary in ``tzinfo``."""
    local = moment.astimezone(tzinfo)
    step_seconds = int(step.total_seconds())
    seconds = local.minute * 60 + local.second
    remainder = seconds % step_seconds
    if remainder or local.microsecond:
        local = local.replace(second=0, microsecond=0) + timedelta(
            seconds=step_seconds - remainder
        )
        local = local.replace(second=0, microsecond=0)
    return _as_utc(local)


def slots_by_day(slots, tz):
    """Group ``slots`` into ``[{date, slots}]`` in the viewer's timezone."""
    tzinfo = zone(valid_timezone(tz))
    days = {}
    for slot in slots:
        local = slot.start.astimezone(tzinfo)
        days.setdefault(local.date(), []).append(
            {"slot": slot, "key": slot.key, "local_start": local,
             "local_end": slot.end.astimezone(tzinfo)}
        )
    return [{"date": day, "slots": items} for day, items in sorted(days.items())]


# ---------------------------------------------------------------- lifecycle


def eligible_interviewers(company):
    """Company members who have declared at least one availability window."""
    from core.models import User

    return User.objects.filter(
        interviewer_availability__company=company, memberships__company=company
    ).distinct()


def default_interviewers(application):
    """Fallback interviewer set used by the auto-proposal signal."""
    return list(eligible_interviewers(application.job.company)[:1])


def _availability_timezone(company, interviewers):
    """The timezone the interviewers publish availability in, else the default.

    Keeps the candidate booking page in the timezone the slots were authored in
    rather than silently falling back to UTC.
    """
    window = (
        InterviewerAvailability.objects.filter(company=company, user__in=interviewers)
        .order_by("weekday", "start")
        .first()
        if interviewers
        else None
    )
    return window.timezone if window else DEFAULT_TIMEZONE


@transaction.atomic
def propose_interview(
    application,
    interviewers,
    duration=DEFAULT_DURATION_MINUTES,
    stage=None,
    tz=None,
    created_by=None,
    location_or_link="",
    notes="",
    notify_candidate=True,
    offer_slots=True,
):
    """Create a PROPOSED :class:`~scheduling.models.Interview` with a token.

    No time is chosen yet — the candidate picks one from the booking page. The
    slots on offer at creation time are recorded as
    :class:`~scheduling.models.InterviewSlotProposal` rows for auditing.
    """
    interviewers = [u for u in (interviewers or []) if u is not None]
    tz = tz or _availability_timezone(application.job.company, interviewers)
    interview = Interview.objects.create(
        company=application.job.company,
        application=application,
        stage=stage or application.current_stage,
        duration_minutes=duration or DEFAULT_DURATION_MINUTES,
        timezone=valid_timezone(tz or DEFAULT_TIMEZONE),
        location_or_link=location_or_link,
        notes=notes,
        status=Interview.PROPOSED,
        created_by=created_by,
    )
    if interviewers:
        interview.interviewers.set(interviewers)
    if offer_slots and interviewers:
        slots = free_slots(
            interviewers,
            duration_min=interview.duration_minutes,
            tz=interview.timezone,
            company=interview.company,
            exclude_interview=interview,
            limit=40,
        )
        InterviewSlotProposal.objects.bulk_create(
            [
                InterviewSlotProposal(interview=interview, start=s.start, end=s.end)
                for s in slots
            ],
            ignore_conflicts=True,
        )
    if notify_candidate:
        notifications.notify_candidate(notifications.INTERVIEW_PROPOSED, interview)
    return interview


def _slot_is_available(interview, start):
    users = list(interview.interviewers.all())
    if not users:
        return True
    end = start + timedelta(minutes=interview.duration_minutes)
    slots = free_slots(
        users,
        date_range=(start - timedelta(minutes=1), end + timedelta(minutes=1)),
        duration_min=interview.duration_minutes,
        tz=interview.timezone,
        company=interview.company,
        exclude_interview=interview,
        min_lead_minutes=0,
    )
    return any(slot.start == start for slot in slots)


class SlotUnavailable(ValueError):
    """The requested start time is no longer bookable."""


def _set_time(interview, start, status):
    start = _as_utc(start)
    interview.scheduled_start = start
    interview.scheduled_end = start + timedelta(minutes=interview.duration_minutes)
    interview.status = status
    interview.save(
        update_fields=["scheduled_start", "scheduled_end", "status", "updated_at"]
    )
    return interview


def _reset_reminders(interview):
    interview.reminder_24h_sent_at = None
    interview.reminder_1h_sent_at = None
    interview.save(update_fields=["reminder_24h_sent_at", "reminder_1h_sent_at", "updated_at"])


def _push_calendar(interview):
    try:
        from scheduling.calendar import upsert_event_for_interview

        upsert_event_for_interview(interview)
    except Exception:  # pragma: no cover - defensive
        logger.warning("calendar upsert failed for interview %s", interview.pk, exc_info=True)


def confirm(interview, start, check=True, notify=True):
    """Lock ``interview`` to ``start`` and push it to connected calendars."""
    start = _as_utc(start)
    if check and not _slot_is_available(interview, start):
        raise SlotUnavailable("That time is no longer available.")
    _set_time(interview, start, Interview.CONFIRMED)
    interview.slot_proposals.update(chosen=False)
    interview.slot_proposals.filter(start=start).update(chosen=True)
    _reset_reminders(interview)
    _push_calendar(interview)
    if notify:
        notifications.notify_candidate(notifications.INTERVIEW_SCHEDULED, interview)
        notifications.notify_interviewers(notifications.INTERVIEW_SCHEDULED, interview)
    return interview


def reschedule(interview, start, check=True, notify=True):
    """Move ``interview`` to ``start``, keeping the same booking token."""
    start = _as_utc(start)
    if check and not _slot_is_available(interview, start):
        raise SlotUnavailable("That time is no longer available.")
    previous = interview.scheduled_start
    _set_time(interview, start, Interview.RESCHEDULED)
    _reset_reminders(interview)
    _push_calendar(interview)
    if notify:
        extra = {"previous_when": previous.isoformat() if previous else ""}
        notifications.notify_candidate(notifications.INTERVIEW_RESCHEDULED, interview, extra)
        notifications.notify_interviewers(notifications.INTERVIEW_RESCHEDULED, interview, extra)
    return interview


def cancel(interview, reason="", notify=True):
    """Cancel ``interview`` and remove it from connected calendars."""
    interview.status = Interview.CANCELLED
    if reason:
        interview.notes = f"{interview.notes}\n\nCancelled: {reason}".strip()
    interview.save(update_fields=["status", "notes", "updated_at"])
    try:
        from scheduling.calendar import delete_event_for_interview

        delete_event_for_interview(interview)
    except Exception:  # pragma: no cover - defensive
        logger.warning("calendar delete failed for interview %s", interview.pk, exc_info=True)
    if notify:
        extra = {"reason": reason}
        notifications.notify_candidate(notifications.INTERVIEW_CANCELLED, interview, extra)
        notifications.notify_interviewers(notifications.INTERVIEW_CANCELLED, interview, extra)
    return interview


def complete(interview):
    interview.status = Interview.COMPLETED
    interview.save(update_fields=["status", "updated_at"])
    return interview


def upcoming_for_company(company, limit=None, user=None):
    """Open, future interviews for ``company``, soonest first.

    Pass ``user`` to restrict the result to the interviews that user is on
    (used for the INTERVIEWER role, who should not see the whole workspace).
    """
    qs = (
        Interview.objects.for_company(company)
        .filter(status__in=Interview.OPEN_STATUSES, scheduled_end__gte=dj_timezone.now())
        .select_related("application__job", "application__candidate__user", "stage")
        .prefetch_related("interviewers")
    )
    if user is not None:
        qs = qs.filter(interviewers=user)
    return qs[:limit] if limit else qs


def interviews_for_application(application):
    """Every interview for ``application``, newest scheduling first."""
    return (
        Interview.objects.filter(application=application)
        .select_related("stage")
        .prefetch_related("interviewers")
        .order_by("-scheduled_start", "-created_at")
    )


def needs_proposal(application):
    """True when ``application`` sits on an INTERVIEW/HR stage with no live interview."""
    from jobs.models import PipelineStage

    stage = application.current_stage
    if stage is None or application.status != application.ACTIVE:
        return False
    if stage.kind not in {PipelineStage.INTERVIEW, PipelineStage.HR}:
        return False
    return not Interview.objects.filter(
        application=application, stage=stage, status__in=Interview.OPEN_STATUSES
    ).exists()


def auto_propose(application):
    """Create a proposal for ``application`` when the feature and staff allow.

    Returns the new :class:`~scheduling.models.Interview`, or None when the
    company lacks the ``scheduling`` entitlement or has no interviewer with
    declared availability.
    """
    if not needs_proposal(application):
        return None
    try:
        from billing.entitlements import has_feature

        if not has_feature(application.job.company, "scheduling"):
            return None
    except Exception:  # pragma: no cover - billing always present
        logger.debug("entitlement check unavailable", exc_info=True)
        return None
    interviewers = default_interviewers(application)
    if not interviewers:
        return None
    return propose_interview(
        application,
        interviewers,
        stage=application.current_stage,
        duration=DEFAULT_DURATION_MINUTES,
    )
