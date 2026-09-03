"""Free-slot computation: timezones, conflicts, calendar busy time, lead time."""

from datetime import UTC, datetime, time, timedelta

import pytest

from scheduling import services
from scheduling.models import Interview


def _monday(hour=0, minute=0):
    """A fixed Monday used as the clock for deterministic slot maths."""
    return datetime(2026, 6, 1, hour, minute, tzinfo=UTC)  # 2026-06-01 is a Monday


def _window(days=2, start=None):
    start = start or _monday()
    return (start, start + timedelta(days=days))


def test_free_slots_inside_declared_availability(interviewer, weekday_availability):
    weekday_availability(weekdays=[0])
    slots = services.free_slots(
        [interviewer], _window(), duration_min=60, now=_monday(), min_lead_minutes=0
    )
    assert slots, "expected slots on the Monday window"
    assert slots[0].start == _monday(9, 0)
    assert slots[0].end == _monday(10, 0)
    # 09:00–17:00 on a 30-minute grid with 60-minute meetings = 15 starts.
    assert len(slots) == 15
    assert all(s.start.tzinfo is not None for s in slots)


def test_no_availability_means_no_slots(interviewer):
    assert services.free_slots([interviewer], _window(), now=_monday()) == []


def test_no_interviewers_means_no_slots(db):
    assert services.free_slots([], _window(), now=_monday()) == []


def test_availability_is_interpreted_in_the_interviewers_timezone(
    interviewer, weekday_availability
):
    """09:00–17:00 Asia/Kolkata is 03:30–11:30 UTC."""
    weekday_availability(tz="Asia/Kolkata", weekdays=[0])
    slots = services.free_slots(
        [interviewer], _window(), duration_min=60, tz="UTC", now=_monday(),
        min_lead_minutes=0,
    )
    assert slots[0].start == _monday(3, 30)
    assert slots[-1].end == _monday(11, 30)


def test_slot_grid_is_anchored_to_the_viewer_timezone(interviewer, weekday_availability):
    """A half-hour-offset viewer zone still yields on-the-half-hour local starts."""
    weekday_availability(tz="UTC", weekdays=[0])
    slots = services.free_slots(
        [interviewer], _window(), duration_min=60, tz="Asia/Kolkata", now=_monday(),
        min_lead_minutes=0,
    )
    local = slots[0].start.astimezone(services.zone("Asia/Kolkata"))
    assert local.minute in {0, 30}


def test_existing_interview_removes_the_conflicting_slot(
    interviewer, weekday_availability, application, interview_stage
):
    weekday_availability(weekdays=[0])
    booked = Interview.objects.create(
        company=application.job.company,
        application=application,
        stage=interview_stage,
        scheduled_start=_monday(10, 0),
        scheduled_end=_monday(11, 0),
        status=Interview.CONFIRMED,
    )
    booked.interviewers.set([interviewer])

    starts = [
        s.start
        for s in services.free_slots(
            [interviewer], _window(), duration_min=60, now=_monday(), min_lead_minutes=0
        )
    ]
    assert _monday(10, 0) not in starts
    assert _monday(9, 30) not in starts  # would overlap the 10:00 booking
    assert _monday(11, 0) in starts


def test_cancelled_interviews_do_not_block(
    interviewer, weekday_availability, application, interview_stage
):
    weekday_availability(weekdays=[0])
    booked = Interview.objects.create(
        company=application.job.company,
        application=application,
        stage=interview_stage,
        scheduled_start=_monday(10, 0),
        scheduled_end=_monday(11, 0),
        status=Interview.CANCELLED,
    )
    booked.interviewers.set([interviewer])
    starts = [
        s.start
        for s in services.free_slots(
            [interviewer], _window(), duration_min=60, now=_monday(), min_lead_minutes=0
        )
    ]
    assert _monday(10, 0) in starts


def test_two_interviewers_slots_are_intersected(
    interviewer, other_interviewer, weekday_availability
):
    weekday_availability(user=interviewer, start=time(9, 0), end=time(12, 0), weekdays=[0])
    weekday_availability(
        user=other_interviewer, start=time(11, 0), end=time(17, 0), weekdays=[0]
    )
    slots = services.free_slots(
        [interviewer, other_interviewer], _window(), duration_min=60, now=_monday(),
        min_lead_minutes=0,
    )
    assert [s.start for s in slots] == [_monday(11, 0)]


def test_one_interviewer_without_availability_blocks_everything(
    interviewer, other_interviewer, weekday_availability
):
    weekday_availability(user=interviewer, weekdays=[0])
    assert (
        services.free_slots(
            [interviewer, other_interviewer], _window(), now=_monday(), min_lead_minutes=0
        )
        == []
    )


def test_calendar_busy_blocks_are_subtracted(
    interviewer, weekday_availability, monkeypatch
):
    weekday_availability(weekdays=[0])
    monkeypatch.setattr(
        "scheduling.calendar.busy_for_user",
        lambda user, start, end: [(_monday(9, 0), _monday(12, 0))],
    )
    slots = services.free_slots(
        [interviewer], _window(), duration_min=60, now=_monday(), min_lead_minutes=0
    )
    assert slots[0].start == _monday(12, 0)


def test_minimum_lead_time_hides_imminent_slots(interviewer, weekday_availability):
    weekday_availability(weekdays=[0])
    slots = services.free_slots(
        [interviewer], _window(), duration_min=60, now=_monday(9, 0), min_lead_minutes=120
    )
    assert slots[0].start >= _monday(11, 0)


def test_duration_longer_than_the_window_yields_nothing(interviewer, weekday_availability):
    weekday_availability(start=time(9, 0), end=time(10, 0), weekdays=[0])
    assert (
        services.free_slots(
            [interviewer], _window(), duration_min=120, now=_monday(), min_lead_minutes=0
        )
        == []
    )


def test_slots_by_day_groups_in_the_viewer_timezone(interviewer, weekday_availability):
    weekday_availability(weekdays=[0, 1])
    slots = services.free_slots(
        [interviewer], _window(days=3), duration_min=60, now=_monday(), min_lead_minutes=0
    )
    days = services.slots_by_day(slots, "Asia/Kolkata")
    assert len(days) >= 2
    assert days[0]["date"] <= days[1]["date"]
    assert all(item["local_start"].tzinfo is not None for item in days[0]["slots"])


@pytest.mark.parametrize("value", ["", None, "not-a-date"])
def test_parse_slot_key_rejects_junk(value):
    assert services.parse_slot_key(value) is None


def test_slot_key_roundtrips():
    slot = services.Slot(_monday(9, 0), _monday(10, 0))
    assert services.parse_slot_key(slot.key) == slot.start
