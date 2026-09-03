"""Proposal / confirm / reschedule / cancel, auto-proposal and reminders."""

from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone as dj_timezone

from jobs.models import Application, PipelineStage
from scheduling import services
from scheduling.models import Interview


def _monday(hour=0, minute=0):
    return datetime(2026, 6, 1, hour, minute, tzinfo=UTC)


@pytest.fixture
def proposal(application, interviewer, weekday_availability, interview_stage):
    weekday_availability(weekdays=[0, 1, 2, 3, 4])
    return services.propose_interview(
        application, [interviewer], duration=60, stage=interview_stage, tz="Asia/Kolkata"
    )


def test_propose_interview_creates_a_tokenised_proposal(proposal, interviewer):
    assert proposal.status == Interview.PROPOSED
    assert proposal.booking_token and len(proposal.booking_token) > 20
    assert proposal.scheduled_start is None
    assert list(proposal.interviewers.all()) == [interviewer]
    assert proposal.timezone == "Asia/Kolkata"
    assert proposal.token_expires_at > dj_timezone.now()
    assert proposal.slot_proposals.exists(), "offered slots are recorded for auditing"


def test_confirm_locks_the_time_and_marks_the_chosen_slot(proposal):
    start = proposal.slot_proposals.first().start
    services.confirm(proposal, start)
    proposal.refresh_from_db()
    assert proposal.status == Interview.CONFIRMED
    assert proposal.scheduled_start == start
    assert proposal.scheduled_end == start + timedelta(minutes=60)
    assert proposal.slot_proposals.filter(chosen=True).count() == 1


def test_confirm_rejects_a_time_outside_availability(proposal):
    with pytest.raises(services.SlotUnavailable):
        services.confirm(proposal, _monday(3, 0))


def test_reschedule_keeps_the_token_and_clears_reminders(proposal):
    slots = list(proposal.slot_proposals.all())
    services.confirm(proposal, slots[0].start)
    token = proposal.booking_token
    proposal.reminder_24h_sent_at = dj_timezone.now()
    proposal.save(update_fields=["reminder_24h_sent_at"])

    services.reschedule(proposal, slots[4].start)
    proposal.refresh_from_db()
    assert proposal.status == Interview.RESCHEDULED
    assert proposal.scheduled_start == slots[4].start
    assert proposal.booking_token == token
    assert proposal.reminder_24h_sent_at is None


def test_cancel_marks_cancelled_and_records_the_reason(proposal):
    services.cancel(proposal, reason="Candidate withdrew")
    proposal.refresh_from_db()
    assert proposal.status == Interview.CANCELLED
    assert "Candidate withdrew" in proposal.notes


def test_confirm_pushes_to_connected_calendars(proposal, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scheduling.calendar.upsert_event_for_interview", lambda i: calls.append(i.pk)
    )
    services.confirm(proposal, proposal.slot_proposals.first().start)
    assert calls == [proposal.pk]


def test_cancel_removes_the_calendar_event(proposal, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "scheduling.calendar.delete_event_for_interview", lambda i: calls.append(i.pk)
    )
    services.cancel(proposal)
    assert calls == [proposal.pk]


# ------------------------------------------------------------ auto-proposal


def test_auto_propose_fires_when_an_application_enters_an_interview_stage(
    application, interview_stage, interviewer, weekday_availability
):
    weekday_availability(weekdays=[0, 1, 2, 3, 4])
    application.current_stage = interview_stage
    application.save(update_fields=["current_stage"])

    interview = Interview.objects.get(application=application)
    assert interview.status == Interview.PROPOSED
    assert interview.stage == interview_stage
    assert list(interview.interviewers.all()) == [interviewer]


def test_auto_propose_also_fires_for_the_hr_stage(
    application, job, interviewer, weekday_availability
):
    weekday_availability(weekdays=[0, 1, 2, 3, 4])
    application.current_stage = job.stages.get(kind=PipelineStage.HR)
    application.save(update_fields=["current_stage"])
    assert Interview.objects.filter(application=application).count() == 1


def test_auto_propose_is_idempotent_across_saves(
    application, interview_stage, interviewer, weekday_availability
):
    weekday_availability(weekdays=[0, 1, 2, 3, 4])
    application.current_stage = interview_stage
    application.save(update_fields=["current_stage"])
    application.save()
    application.save()
    assert Interview.objects.filter(application=application).count() == 1


def test_auto_propose_skipped_without_the_scheduling_entitlement(
    free_company, interview_stage, candidate, weekday_availability, interviewer
):
    from jobs.models import Job

    weekday_availability(weekdays=[0, 1, 2, 3, 4])
    job = Job.objects.create(company=free_company, title="Ops", status=Job.OPEN)
    stage = job.stages.filter(kind=PipelineStage.INTERVIEW).first()
    application = Application.objects.create(job=job, candidate=candidate, current_stage=stage)
    assert not Interview.objects.filter(application=application).exists()


def test_auto_propose_skipped_when_nobody_declared_availability(
    application, interview_stage, interviewer
):
    application.current_stage = interview_stage
    application.save(update_fields=["current_stage"])
    assert not Interview.objects.filter(application=application).exists()


def test_needs_proposal_is_false_on_a_screening_stage(application):
    assert services.needs_proposal(application) is False


def test_needs_proposal_is_false_for_an_inactive_application(
    application, interview_stage
):
    application.current_stage = interview_stage
    application.status = Application.REJECTED
    assert services.needs_proposal(application) is False


# ------------------------------------------------------------ reminders


def _confirm_in(interview, hours):
    start = dj_timezone.now() + timedelta(hours=hours)
    services.confirm(interview, start, check=False, notify=False)
    return interview


def test_reminders_are_sent_once_and_only_once(proposal):
    _confirm_in(proposal, 23)
    out = StringIO()
    call_command("send_interview_reminders", stdout=out)
    proposal.refresh_from_db()
    assert proposal.reminder_24h_sent_at is not None
    first = proposal.reminder_24h_sent_at

    call_command("send_interview_reminders", stdout=StringIO())
    proposal.refresh_from_db()
    assert proposal.reminder_24h_sent_at == first
    assert "Sent 1 reminder(s)." in out.getvalue()


def test_one_hour_reminder_is_tracked_separately(proposal):
    _confirm_in(proposal, 1)
    call_command("send_interview_reminders", stdout=StringIO())
    proposal.refresh_from_db()
    assert proposal.reminder_1h_sent_at is not None
    assert proposal.reminder_24h_sent_at is not None


def test_dry_run_sends_nothing(proposal):
    _confirm_in(proposal, 23)
    out = StringIO()
    call_command("send_interview_reminders", dry_run=True, stdout=out)
    proposal.refresh_from_db()
    assert proposal.reminder_24h_sent_at is None
    assert "Would send" in out.getvalue()


def test_reminders_ignore_cancelled_interviews(proposal):
    _confirm_in(proposal, 23)
    services.cancel(proposal, notify=False)
    call_command("send_interview_reminders", stdout=StringIO())
    proposal.refresh_from_db()
    assert proposal.reminder_24h_sent_at is None


# ------------------------------------------------------------ notifications


def test_email_fallback_attaches_an_ics_when_notifications_fail(proposal, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("notifications unavailable")

    monkeypatch.setattr("notifications.api.send", boom)
    mail.outbox.clear()
    services.confirm(proposal, proposal.slot_proposals.first().start)

    assert mail.outbox, "expected the django.core.mail fallback to fire"
    attachments = mail.outbox[0].attachments
    assert attachments and attachments[0][0] == "interview.ics"
    payload = attachments[0][1]
    payload = payload.encode() if isinstance(payload, str) else payload
    assert b"BEGIN:VCALENDAR" in payload
