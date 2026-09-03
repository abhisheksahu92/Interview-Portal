"""Recruiter, interviewer and candidate-facing views, plus feature gating."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone as dj_timezone

from core.models import Company, Membership, User
from scheduling import services
from scheduling.models import CalendarConnection, Interview


@pytest.fixture
def logged_in(client, owner):
    client.force_login(owner)
    return client


@pytest.fixture
def proposal(application, interviewer, weekday_availability, interview_stage):
    weekday_availability(weekdays=[0, 1, 2, 3, 4, 5, 6])
    return services.propose_interview(
        application, [interviewer], duration=60, stage=interview_stage
    )


# ------------------------------------------------------------ gating


def test_index_renders_for_an_entitled_company(logged_in):
    response = logged_in.get(reverse("scheduling:index"))
    assert response.status_code == 200
    assert b"Upcoming interviews" in response.content


def test_index_is_403_for_a_free_plan(client, free_company):
    user = User.objects.create_user(email="free@owner.test", password="pw12345678")
    Membership.objects.create(user=user, company=free_company, role=Membership.OWNER)
    client.force_login(user)
    assert client.get(reverse("scheduling:index")).status_code == 403


def test_index_requires_login(client):
    response = client.get(reverse("scheduling:index"))
    assert response.status_code == 302
    assert "/login" in response["Location"] or "login" in response["Location"]


def test_week_view_is_available_as_an_htmx_fragment(logged_in, proposal):
    services.confirm(proposal, proposal.slot_proposals.first().start, check=False)
    response = logged_in.get(
        reverse("scheduling:index"), {"week": "0"}, HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 200
    assert b"scheduling-week" in response.content
    assert b"ip-page-head" not in response.content


# ------------------------------------------------------------ recruiter


def test_schedule_panel_creates_a_proposal(
    logged_in, application, interviewer, weekday_availability
):
    weekday_availability(weekdays=[0, 1, 2, 3, 4])
    url = reverse("scheduling:application_schedule", args=[application.pk])
    assert logged_in.get(url).status_code == 200

    response = logged_in.post(
        url,
        {
            "interviewers": [interviewer.pk],
            "duration": "45",
            "timezone": "Asia/Kolkata",
            "location_or_link": "https://meet.example/abc",
            "notes": "Panel round",
        },
    )
    assert response.status_code == 302
    interview = Interview.objects.get(application=application)
    assert interview.status == Interview.PROPOSED
    assert interview.duration_minutes == 45
    assert interview.created_by_id is not None
    assert interview.location_or_link == "https://meet.example/abc"


def test_schedule_panel_is_tenant_scoped(logged_in, candidate):
    from jobs.models import Application, Job

    other = Company.objects.create(name="Rival Corp")
    job = Job.objects.create(company=other, title="Elsewhere")
    application = Application.objects.create(job=job, candidate=candidate)
    url = reverse("scheduling:application_schedule", args=[application.pk])
    assert logged_in.get(url).status_code == 404


def test_application_interviews_partial_renders(logged_in, proposal, application):
    response = logged_in.get(
        reverse("scheduling:application_interviews", args=[application.pk])
    )
    assert response.status_code == 200
    assert b"scheduling-application-interviews" in response.content


def test_recruiter_can_cancel_an_interview(logged_in, proposal):
    response = logged_in.post(
        reverse("scheduling:interview_cancel", args=[proposal.pk]), {"reason": "Role paused"}
    )
    assert response.status_code == 302
    proposal.refresh_from_db()
    assert proposal.status == Interview.CANCELLED


# ------------------------------------------------------------ interviewer


def test_availability_editor_adds_and_removes_windows(client, interviewer):
    client.force_login(interviewer)
    url = reverse("scheduling:availability")
    assert client.get(url).status_code == 200

    response = client.post(
        url, {"weekday": "2", "start": "10:00", "end": "16:00", "timezone": "Asia/Kolkata"}
    )
    assert response.status_code == 302
    window = interviewer.interviewer_availability.get()
    assert (window.weekday, window.timezone) == (2, "Asia/Kolkata")

    client.post(reverse("scheduling:availability_delete", args=[window.pk]))
    assert not interviewer.interviewer_availability.exists()


def test_availability_rejects_an_inverted_window(client, interviewer):
    client.force_login(interviewer)
    response = client.post(
        reverse("scheduling:availability"),
        {"weekday": "2", "start": "16:00", "end": "10:00", "timezone": "UTC"},
    )
    assert response.status_code == 200
    assert b"end time must be after" in response.content
    assert not interviewer.interviewer_availability.exists()


def test_connect_calendar_is_disabled_when_unconfigured(logged_in, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = ""
    settings.MS_OAUTH_CLIENT_ID = ""
    response = logged_in.get(reverse("scheduling:availability"))
    assert response.status_code == 200
    assert b"is not configured" in response.content
    assert b"disabled" in response.content


def test_oauth_start_warns_instead_of_redirecting_when_unconfigured(logged_in, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = ""
    settings.GOOGLE_OAUTH_CLIENT_SECRET = ""
    response = logged_in.get(reverse("scheduling:oauth_start", args=["GOOGLE"]))
    assert response.status_code == 302
    assert response["Location"] == reverse("scheduling:availability")


def test_oauth_start_redirects_to_the_provider_when_configured(
    logged_in, settings, monkeypatch
):
    settings.GOOGLE_OAUTH_CLIENT_ID = "cid"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "secret"
    monkeypatch.setattr(
        "scheduling.calendar.google.GoogleCalendarAdapter.authorize_url",
        lambda self, redirect_uri, state: f"https://accounts.example/auth?state={state}",
    )
    response = logged_in.get(reverse("scheduling:oauth_start", args=["GOOGLE"]))
    assert response.status_code == 302
    assert response["Location"].startswith("https://accounts.example/auth")


def test_oauth_callback_stores_tokens_with_a_mocked_client(
    logged_in, owner, settings, monkeypatch
):
    settings.GOOGLE_OAUTH_CLIENT_ID = "cid"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "secret"
    monkeypatch.setattr(
        "scheduling.calendar.google.GoogleCalendarAdapter.authorize_url",
        lambda self, redirect_uri, state: f"https://accounts.example/auth?state={state}",
    )
    monkeypatch.setattr(
        "scheduling.calendar.google.GoogleCalendarAdapter.exchange_code",
        lambda self, code, redirect_uri, state=None: {"token": "at", "refresh_token": "rt"},
    )
    logged_in.get(reverse("scheduling:oauth_start", args=["GOOGLE"]))
    state = logged_in.session["scheduling_oauth_state"]["state"]

    response = logged_in.get(
        reverse("scheduling:oauth_callback", args=["GOOGLE"]),
        {"code": "abc", "state": state},
    )
    assert response.status_code == 302
    connection = CalendarConnection.objects.get(user=owner, provider="GOOGLE")
    assert connection.tokens["token"] == "at"
    assert connection.is_live is True


def test_oauth_callback_rejects_a_mismatched_state(logged_in, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "cid"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "secret"
    response = logged_in.get(
        reverse("scheduling:oauth_callback", args=["GOOGLE"]),
        {"code": "abc", "state": "forged"},
    )
    assert response.status_code == 302
    assert not CalendarConnection.objects.exists()


def test_calendar_can_be_disconnected(logged_in, owner):
    connection = CalendarConnection.objects.create(
        user=owner, provider="GOOGLE", tokens={"token": "x"}
    )
    logged_in.post(reverse("scheduling:calendar_disconnect", args=[connection.pk]))
    assert not CalendarConnection.objects.exists()


# ------------------------------------------------------------ candidate booking


def test_booking_page_lists_slots_without_login(client, proposal):
    response = client.get(reverse("scheduling:book", args=[proposal.booking_token]))
    assert response.status_code == 200
    assert b"Book your interview" in response.content
    assert b"slot-picker" in response.content
    assert response.context["slot_count"] > 0


def test_booking_page_honours_the_candidate_timezone(client, proposal):
    response = client.get(
        reverse("scheduling:book", args=[proposal.booking_token]), {"tz": "Asia/Kolkata"}
    )
    assert response.context["tz"] == "Asia/Kolkata"


def test_booking_page_falls_back_to_utc_for_a_bogus_timezone(client, proposal):
    response = client.get(
        reverse("scheduling:book", args=[proposal.booking_token]), {"tz": "Mars/Olympus"}
    )
    assert response.context["tz"] == "UTC"


def test_a_wrong_booking_token_is_a_404(client, proposal):
    assert client.get(reverse("scheduling:book", args=["not-a-real-token"])).status_code == 404


def test_an_expired_booking_token_is_gone(client, proposal):
    proposal.token_expires_at = dj_timezone.now() - timedelta(minutes=1)
    proposal.save(update_fields=["token_expires_at"])
    response = client.get(reverse("scheduling:book", args=[proposal.booking_token]))
    assert response.status_code == 410
    assert b"expired" in response.content


def test_candidate_confirms_a_slot(client, proposal):
    slot = services.free_slots(
        list(proposal.interviewers.all()),
        duration_min=60,
        company=proposal.company,
        exclude_interview=proposal,
        limit=1,
    )[0]
    response = client.post(
        reverse("scheduling:book_confirm", args=[proposal.booking_token]),
        {"slot": slot.key, "timezone": "Asia/Kolkata"},
    )
    assert response.status_code == 302
    proposal.refresh_from_db()
    assert proposal.status == Interview.CONFIRMED
    assert proposal.scheduled_start == slot.start
    assert proposal.timezone == "Asia/Kolkata"

    done = client.get(response["Location"])
    assert done.status_code == 200
    assert b"You&#x27;re booked" in done.content or b"booked" in done.content


def test_candidate_reschedules_an_already_confirmed_interview(client, proposal):
    slots = services.free_slots(
        list(proposal.interviewers.all()),
        duration_min=60,
        company=proposal.company,
        exclude_interview=proposal,
        limit=6,
    )
    services.confirm(proposal, slots[0].start)
    client.post(
        reverse("scheduling:book_confirm", args=[proposal.booking_token]),
        {"slot": slots[5].key},
    )
    proposal.refresh_from_db()
    assert proposal.status == Interview.RESCHEDULED
    assert proposal.scheduled_start == slots[5].start


def test_candidate_cannot_book_a_time_that_was_not_offered(client, proposal):
    bogus = (dj_timezone.now() + timedelta(days=1)).replace(
        hour=3, minute=17, second=0, microsecond=0
    )
    response = client.post(
        reverse("scheduling:book_confirm", args=[proposal.booking_token]),
        {"slot": bogus.isoformat()},
    )
    assert response.status_code == 302
    proposal.refresh_from_db()
    assert proposal.status == Interview.PROPOSED


def test_candidate_cancels_from_the_booking_page(client, proposal):
    response = client.post(
        reverse("scheduling:book_cancel", args=[proposal.booking_token]),
        {"reason": "Accepted another offer"},
    )
    assert response.status_code == 302
    proposal.refresh_from_db()
    assert proposal.status == Interview.CANCELLED
    assert client.get(response["Location"]).status_code == 200


def test_candidate_ics_download(client, proposal):
    services.confirm(proposal, proposal.slot_proposals.first().start)
    response = client.get(reverse("scheduling:book_ics", args=[proposal.booking_token]))
    assert response.status_code == 200
    assert response["Content-Type"] == "text/calendar"
    assert b"BEGIN:VEVENT" in response.content


def test_ics_download_404s_before_a_time_is_chosen(client, proposal):
    assert (
        client.get(reverse("scheduling:book_ics", args=[proposal.booking_token])).status_code
        == 404
    )
