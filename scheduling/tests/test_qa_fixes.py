"""Regressions for the QA findings on the scheduling app.

Timezone rendering, the booking page's timezone selector, absolute links in
notification emails, RFC 5545 attendees and the interviewer-scoped index.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.urls import reverse

from core.models import Membership, User
from scheduling import notify, services
from scheduling.ics import interview_ics
from scheduling.models import Interview

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def ist_availability(company, interviewer, weekday_availability):
    """10:00–17:00 Asia/Kolkata, every day of the week."""
    return weekday_availability(
        tz="Asia/Kolkata", start=time(10, 0), end=time(17, 0),
        weekdays=[0, 1, 2, 3, 4, 5, 6],
    )


@pytest.fixture
def ist_interview(application, interviewer, ist_availability, interview_stage):
    return services.propose_interview(
        application, [interviewer], duration=60, stage=interview_stage
    )


# ---------------------------------------------------------------- timezones


def test_proposal_defaults_to_the_availability_timezone(ist_interview):
    assert ist_interview.timezone == "Asia/Kolkata"


def test_booking_page_shows_ist_wall_clock_times(client, ist_interview):
    response = client.get(reverse("scheduling:book", args=[ist_interview.booking_token]))
    assert response.status_code == 200
    body = response.content.decode()
    # Availability opens at 10:00 IST, so the first offered slot must say 10:00.
    assert ">\n                10:00\n" in body or ">10:00<" in body or "10:00" in body
    assert "Times shown in Asia/Kolkata" in body
    assert 'value="Asia/Kolkata" selected' in body


def test_booking_page_timezone_selector_changes_the_displayed_times(client, ist_interview):
    url = reverse("scheduling:book", args=[ist_interview.booking_token])
    ist = client.get(url).content.decode()
    utc = client.get(url, {"tz": "UTC"}).content.decode()
    assert ist != utc
    assert "Times shown in UTC" in utc
    # 10:00 IST is 04:30 UTC.
    assert "04:30" in utc


def test_booking_page_falls_back_to_the_interview_timezone_for_junk(client, ist_interview):
    response = client.get(
        reverse("scheduling:book", args=[ist_interview.booking_token]), {"tz": "Not/AZone"}
    )
    assert "Times shown in Asia/Kolkata" in response.content.decode()


def _confirm_at(interview, local):
    start = local.astimezone(ZoneInfo("UTC"))
    services.confirm(interview, start, check=False)
    return interview


def test_recruiter_rows_render_the_interview_timezone(logged_in_owner, ist_interview):
    _confirm_at(ist_interview, datetime(2030, 6, 3, 11, 0, tzinfo=IST))
    response = logged_in_owner.get(reverse("scheduling:index"))
    body = response.content.decode()
    assert "11:00" in body
    assert "05:30" not in body  # the UTC wall clock must not leak through


def test_booked_page_renders_the_chosen_timezone(client, ist_interview):
    _confirm_at(ist_interview, datetime(2030, 6, 3, 11, 0, tzinfo=IST))
    url = reverse("scheduling:booked", args=[ist_interview.booking_token])
    assert "11:00" in client.get(url).content.decode()
    assert "05:30" in client.get(url, {"tz": "UTC"}).content.decode()


# ---------------------------------------------------------------- notify


def test_booking_email_carries_an_absolute_url(settings, ist_interview):
    settings.SITE_URL = "https://portal.example"
    url = notify.booking_url(ist_interview)
    assert url.startswith("https://portal.example/")
    assert ist_interview.booking_token in url


def test_booking_url_prefers_the_request_host(rf, ist_interview):
    request = rf.get("/", HTTP_HOST="testserver")
    assert notify.booking_url(ist_interview, request).startswith("http://testserver/")


def test_proposal_email_body_contains_an_absolute_link(settings, application, interviewer,
                                                       ist_availability, interview_stage):
    settings.SITE_URL = "https://portal.example"
    mail.outbox.clear()
    interview = services.propose_interview(
        application, [interviewer], duration=60, stage=interview_stage
    )
    body = "\n".join(m.body for m in mail.outbox)
    assert "http" in body
    assert f"https://portal.example{interview.booking_path()}" in body


# ---------------------------------------------------------------- ics


def test_ics_attendees_use_lowercase_mailto(ist_interview, interviewer):
    _confirm_at(ist_interview, datetime(2030, 6, 3, 11, 0, tzinfo=IST))
    payload = interview_ics(ist_interview).decode()
    assert "ATTENDEE;CN=" in payload
    assert ":mailto:" in payload
    assert "MAILTO:" not in payload


# ---------------------------------------------------------------- role scoping


@pytest.fixture
def logged_in_owner(client, owner):
    client.force_login(owner)
    return client


def test_interviewer_index_shows_only_their_own_interviews(
    client, company, application, interviewer, other_interviewer, ist_availability,
    interview_stage,
):
    mine = services.propose_interview(
        application, [interviewer], duration=60, stage=interview_stage
    )
    theirs = services.propose_interview(
        application, [other_interviewer], duration=60, stage=interview_stage
    )
    start = datetime(2030, 6, 3, 11, 0, tzinfo=IST).astimezone(ZoneInfo("UTC"))
    services.confirm(mine, start, check=False)
    services.confirm(theirs, start + timedelta(hours=2), check=False)

    client.force_login(interviewer)
    body = client.get(reverse("scheduling:index")).content.decode()
    assert "Interviews you are on" in body
    assert str(mine.pk) in body
    assert f"/interviews/{theirs.pk}/" not in body


def test_owner_index_shows_every_interview(
    logged_in_owner, application, interviewer, other_interviewer, ist_availability,
    interview_stage,
):
    theirs = services.propose_interview(
        application, [other_interviewer], duration=60, stage=interview_stage
    )
    start = datetime(2030, 6, 3, 11, 0, tzinfo=IST).astimezone(ZoneInfo("UTC"))
    services.confirm(theirs, start, check=False)
    body = logged_in_owner.get(reverse("scheduling:index")).content.decode()
    assert f"/interviews/{theirs.pk}/" in body
    assert "Interviews you are on" not in body


def test_recruiter_index_is_not_scoped(client, company, application, other_interviewer,
                                       ist_availability, interview_stage):
    user = User.objects.create_user(email="rec@acme.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.RECRUITER)
    interview = services.propose_interview(
        application, [other_interviewer], duration=60, stage=interview_stage
    )
    services.confirm(
        interview, datetime(2030, 6, 3, 11, 0, tzinfo=IST).astimezone(ZoneInfo("UTC")),
        check=False,
    )
    client.force_login(user)
    body = client.get(reverse("scheduling:index")).content.decode()
    assert f"/interviews/{interview.pk}/" in body


def test_upcoming_for_company_can_be_scoped_to_a_user(
    company, application, interviewer, other_interviewer, ist_availability, interview_stage
):
    mine = services.propose_interview(
        application, [interviewer], duration=60, stage=interview_stage
    )
    services.confirm(
        mine, datetime(2030, 6, 3, 11, 0, tzinfo=IST).astimezone(ZoneInfo("UTC")), check=False
    )
    assert list(services.upcoming_for_company(company, user=interviewer)) == [mine]
    assert list(services.upcoming_for_company(company, user=other_interviewer)) == []
    assert Interview.objects.filter(pk=mine.pk).exists()
