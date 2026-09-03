"""Calendar adapters: the unconfigured path and mocked provider clients."""

import pytest

from scheduling import gateway
from scheduling.calendar import adapter_for, busy_for_user
from scheduling.calendar.base import NotConfigured, provider_status
from scheduling.calendar.google import GoogleCalendarAdapter
from scheduling.calendar.outlook import OutlookCalendarAdapter
from scheduling.models import CalendarConnection


@pytest.fixture(autouse=True)
def no_oauth(settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = ""
    settings.GOOGLE_OAUTH_CLIENT_SECRET = ""
    settings.MS_OAUTH_CLIENT_ID = ""
    settings.MS_OAUTH_CLIENT_SECRET = ""


def test_gateway_reports_unconfigured_without_credentials():
    assert gateway.configured() is False
    rows = gateway.status()
    assert {r["provider"] for r in rows} == {"GOOGLE", "OUTLOOK"}
    assert all(not r["configured"] and r["note"] for r in rows)


def test_unconfigured_adapters_never_call_out(db, owner):
    connection = CalendarConnection.objects.create(
        user=owner, provider="GOOGLE", tokens={"token": "x"}
    )
    for adapter in (GoogleCalendarAdapter(), OutlookCalendarAdapter()):
        assert adapter.busy(connection, None, None) == []
        assert adapter.create_event(connection, None) is None
        assert adapter.update_event(connection, "evt", None) == "evt"
        assert adapter.delete_event(connection, "evt") is None


def test_authorize_url_refuses_when_unconfigured():
    with pytest.raises(NotConfigured):
        GoogleCalendarAdapter().authorize_url("https://example.test/cb", "state")
    with pytest.raises(NotConfigured):
        OutlookCalendarAdapter().authorize_url("https://example.test/cb", "state")


def test_busy_for_user_is_empty_without_a_configured_provider(db, owner):
    CalendarConnection.objects.create(user=owner, provider="GOOGLE", tokens={"token": "x"})
    assert busy_for_user(owner, None, None) == []


def test_adapter_for_unknown_provider_is_none():
    assert adapter_for("FAXCAL") is None


def test_provider_status_flips_when_credentials_are_present(settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "cid"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "secret"
    google = next(r for r in provider_status() if r["provider"] == "GOOGLE")
    assert google["configured"] is True
    assert google["note"] == ""
    assert gateway.configured() is True


def test_google_busy_parses_freebusy_with_a_mocked_service(db, owner, settings, monkeypatch):
    from datetime import UTC, datetime

    settings.GOOGLE_OAUTH_CLIENT_ID = "cid"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "secret"
    connection = CalendarConnection.objects.create(
        user=owner, provider="GOOGLE", tokens={"token": "x"}
    )

    class FakeQuery:
        def execute(self):
            return {
                "calendars": {
                    "primary": {
                        "busy": [
                            {
                                "start": "2026-06-01T10:00:00Z",
                                "end": "2026-06-01T11:00:00Z",
                            }
                        ]
                    }
                }
            }

    class FakeFreebusy:
        def query(self, body):
            return FakeQuery()

    class FakeService:
        def freebusy(self):
            return FakeFreebusy()

    monkeypatch.setattr(
        GoogleCalendarAdapter, "_service", lambda self, connection: FakeService()
    )
    start = datetime(2026, 6, 1, tzinfo=UTC)
    end = datetime(2026, 6, 2, tzinfo=UTC)
    assert GoogleCalendarAdapter().busy(connection, start, end) == [
        (datetime(2026, 6, 1, 10, tzinfo=UTC), datetime(2026, 6, 1, 11, tzinfo=UTC))
    ]


def test_outlook_busy_skips_free_blocks(db, owner, settings, monkeypatch):
    from datetime import UTC, datetime

    settings.MS_OAUTH_CLIENT_ID = "cid"
    settings.MS_OAUTH_CLIENT_SECRET = "secret"
    connection = CalendarConnection.objects.create(
        user=owner, provider="OUTLOOK", tokens={"token": "x"}
    )
    payload = {
        "value": [
            {
                "showAs": "busy",
                "start": {"dateTime": "2026-06-01T09:00:00"},
                "end": {"dateTime": "2026-06-01T09:30:00"},
            },
            {
                "showAs": "free",
                "start": {"dateTime": "2026-06-01T12:00:00"},
                "end": {"dateTime": "2026-06-01T13:00:00"},
            },
        ]
    }
    monkeypatch.setattr(
        OutlookCalendarAdapter,
        "_request",
        lambda self, method, path, connection, **kw: payload,
    )
    start = datetime(2026, 6, 1, tzinfo=UTC)
    end = datetime(2026, 6, 2, tzinfo=UTC)
    assert OutlookCalendarAdapter().busy(connection, start, end) == [
        (datetime(2026, 6, 1, 9, tzinfo=UTC), datetime(2026, 6, 1, 9, 30, tzinfo=UTC))
    ]


def test_upsert_and_delete_round_trip_with_a_mocked_adapter(
    db, owner, settings, monkeypatch, application, interview_stage
):
    from datetime import UTC, datetime

    from scheduling.calendar import delete_event_for_interview, upsert_event_for_interview
    from scheduling.models import Interview

    settings.GOOGLE_OAUTH_CLIENT_ID = "cid"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "secret"
    CalendarConnection.objects.create(user=owner, provider="GOOGLE", tokens={"token": "x"})
    interview = Interview.objects.create(
        company=application.job.company,
        application=application,
        stage=interview_stage,
        scheduled_start=datetime(2026, 6, 1, 10, tzinfo=UTC),
        scheduled_end=datetime(2026, 6, 1, 11, tzinfo=UTC),
        status=Interview.CONFIRMED,
    )
    interview.interviewers.set([owner])

    deleted = []
    monkeypatch.setattr(
        GoogleCalendarAdapter, "create_event", lambda self, c, e: "evt-1"
    )
    monkeypatch.setattr(
        GoogleCalendarAdapter, "delete_event", lambda self, c, i: deleted.append(i)
    )

    ids = upsert_event_for_interview(interview)
    assert ids == {f"GOOGLE:{owner.pk}": "evt-1"}
    interview.refresh_from_db()
    assert interview.external_event_ids == ids

    delete_event_for_interview(interview)
    assert deleted == ["evt-1"]
    interview.refresh_from_db()
    assert interview.external_event_ids == {}
