"""The phase-3 API surface: entitlement gating, tenant isolation, exports."""

import csv
import io
from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from billing.models import Plan, Subscription
from clients.models import Client, Submission
from core.models import User
from integrations.models import OutboundWebhook
from jobs.models import Application, CandidateProfile
from offers.models import Offer
from scheduling.models import Interview
from talent.models import TalentProfile
from video.models import VideoInvite, VideoScreen

pytestmark = pytest.mark.django_db

#: Every phase-3 collection endpoint, by router basename.
LIST_ROUTES = [
    "api:interview-list",
    "api:offer-list",
    "api:submission-list",
    "api:videoinvite-list",
    "api:talentprofile-list",
    "api:outboundwebhook-list",
]


@pytest.fixture
def downgrade():
    """Put a company on FREE with an expired trial (no ``api`` feature)."""

    def _downgrade(company):
        Subscription.objects.update_or_create(
            company=company,
            defaults={
                "plan": Plan.objects.get(code=Plan.FREE),
                "status": Subscription.ACTIVE,
                "trial_ends_at": timezone.now() - timedelta(days=1),
            },
        )
        company.refresh_from_db()
        return company

    return _downgrade


@pytest.fixture
def interview_a(company_a, application):
    return Interview.objects.create(
        company=company_a,
        application=application,
        scheduled_start=timezone.now() + timedelta(days=1),
        scheduled_end=timezone.now() + timedelta(days=1, hours=1),
        status=Interview.CONFIRMED,
    )


@pytest.fixture
def application_b(job_b):
    user = User.objects.create_user(email="cand-b@example.com", password="pw12345!")
    profile = CandidateProfile.objects.create(user=user, experience_years=2)
    return Application.objects.create(job=job_b, candidate=profile)


@pytest.fixture
def interview_b(company_b, application_b):
    return Interview.objects.create(
        company=company_b,
        application=application_b,
        scheduled_start=timezone.now() + timedelta(days=2),
        scheduled_end=timezone.now() + timedelta(days=2, hours=1),
        status=Interview.CONFIRMED,
    )


# --- gating --------------------------------------------------------------
@pytest.mark.parametrize("route", LIST_ROUTES)
def test_phase3_endpoints_are_open_on_an_entitled_plan(auth, recruiter_a, route):
    assert auth(recruiter_a).get(reverse(route)).status_code == 200


@pytest.mark.parametrize("route", LIST_ROUTES)
def test_phase3_endpoints_403_without_the_api_feature(
    auth, recruiter_a, company_a, downgrade, route
):
    downgrade(company_a)
    response = auth(recruiter_a).get(reverse(route))

    assert response.status_code == 403
    assert "does not include API access" in str(response.data["detail"])


def test_the_hires_export_is_gated_too(auth, recruiter_a, company_a, downgrade):
    downgrade(company_a)
    assert auth(recruiter_a).get(reverse("api:export-hires")).status_code == 403


def test_phase1_endpoints_stay_open_on_a_free_plan(
    auth, recruiter_a, company_a, downgrade
):
    downgrade(company_a)
    assert auth(recruiter_a).get(reverse("api:job-list")).status_code == 200


@pytest.mark.parametrize("route", LIST_ROUTES)
def test_phase3_endpoints_require_authentication(api, route):
    assert api.get(reverse(route)).status_code in (401, 403)


# --- isolation -----------------------------------------------------------
def test_interviews_are_scoped_to_the_callers_company(
    auth, recruiter_a, interview_a, interview_b
):
    data = auth(recruiter_a).get(reverse("api:interview-list")).data

    assert [row["id"] for row in data["results"]] == [interview_a.pk]


def test_another_companys_interview_is_not_retrievable(
    auth, recruiter_a, interview_b
):
    response = auth(recruiter_a).get(
        reverse("api:interview-detail", args=[interview_b.pk])
    )
    assert response.status_code == 404


def test_interview_payload_includes_the_application_and_interviewers(
    auth, recruiter_a, interviewer_a, interview_a
):
    interview_a.interviewers.add(interviewer_a)
    row = auth(recruiter_a).get(reverse("api:interview-list")).data["results"][0]

    assert row["status"] == Interview.CONFIRMED
    assert row["application_detail"]["job_title"] == "Python Developer"
    assert row["interviewer_emails"] == [interviewer_a.email]


def test_offers_are_scoped_by_the_applications_company(
    auth, recruiter_a, application, application_b
):
    mine = Offer.objects.create(application=application, salary=100)
    Offer.objects.create(application=application_b, salary=200)

    data = auth(recruiter_a).get(reverse("api:offer-list")).data
    assert [row["id"] for row in data["results"]] == [mine.pk]


def test_submissions_are_scoped_by_the_clients_company(
    auth, recruiter_a, company_a, company_b, application, application_b
):
    mine = Submission.objects.create(
        application=application,
        client=Client.objects.create(company=company_a, name="Acme Client"),
    )
    Submission.objects.create(
        application=application_b,
        client=Client.objects.create(company=company_b, name="Beta Client"),
    )

    data = auth(recruiter_a).get(reverse("api:submission-list")).data
    assert [row["id"] for row in data["results"]] == [mine.pk]
    assert data["results"][0]["client_name"] == "Acme Client"


def test_video_invites_are_scoped_and_never_expose_the_token(
    auth, recruiter_a, company_a, application
):
    screen = VideoScreen.objects.create(job=application.job)
    invite = VideoInvite.objects.create(
        application=application,
        screen=screen,
        expires_at=timezone.now() + timedelta(days=3),
    )

    row = auth(recruiter_a).get(reverse("api:videoinvite-list")).data["results"][0]
    assert row["id"] == invite.pk
    assert "token" not in row


def test_talent_profiles_are_scoped(auth, recruiter_a, company_a, company_b):
    mine = TalentProfile.objects.create(company=company_a, email="a@x.test", name="A")
    TalentProfile.objects.create(company=company_b, email="b@x.test", name="B")

    data = auth(recruiter_a).get(reverse("api:talentprofile-list")).data
    assert [row["id"] for row in data["results"]] == [mine.pk]


def test_talent_search_filters_by_query(auth, recruiter_a, company_a):
    TalentProfile.objects.create(company=company_a, email="asha@x.test", name="Asha Rao")
    TalentProfile.objects.create(company=company_a, email="bala@x.test", name="Bala K")

    data = auth(recruiter_a).get(reverse("api:talentprofile-list"), {"q": "asha"}).data
    assert [row["name"] for row in data["results"]] == ["Asha Rao"]


def test_creating_a_talent_profile_assigns_the_company(auth, recruiter_a, company_a):
    response = auth(recruiter_a).post(
        reverse("api:talentprofile-list"),
        {"email": "new@x.test", "name": "New Person", "experience_years": "4.0"},
        format="json",
    )

    assert response.status_code == 201
    profile = TalentProfile.objects.get(email="new@x.test")
    assert profile.company == company_a
    assert profile.created_by == recruiter_a


def test_duplicate_talent_emails_are_rejected(auth, recruiter_a, company_a):
    TalentProfile.objects.create(company=company_a, email="dupe@x.test")
    response = auth(recruiter_a).post(
        reverse("api:talentprofile-list"), {"email": "dupe@x.test"}, format="json"
    )
    assert response.status_code == 400


# --- offer creation ------------------------------------------------------
def test_creating_an_offer_always_produces_a_draft(auth, recruiter_a, application):
    response = auth(recruiter_a).post(
        reverse("api:offer-list"),
        {
            "application": application.pk,
            "salary": "1500000.00",
            "currency": "INR",
            "joining_date": "2026-05-01",
            "status": Offer.SENT,
        },
        format="json",
    )

    assert response.status_code == 201
    offer = Offer.objects.get()
    assert offer.status == Offer.DRAFT
    assert offer.created_by == recruiter_a
    assert offer.sign_token


def test_an_offer_cannot_be_created_for_another_companys_application(
    auth, recruiter_a, application_b
):
    response = auth(recruiter_a).post(
        reverse("api:offer-list"),
        {"application": application_b.pk, "salary": "1"},
        format="json",
    )
    assert response.status_code == 400
    assert Offer.objects.count() == 0


def test_interviewers_cannot_create_offers(auth, interviewer_a, application):
    response = auth(interviewer_a).post(
        reverse("api:offer-list"),
        {"application": application.pk, "salary": "1"},
        format="json",
    )
    assert response.status_code == 403


# --- webhook CRUD --------------------------------------------------------
def test_creating_a_webhook_returns_the_secret_exactly_once(
    auth, recruiter_a, company_a
):
    response = auth(recruiter_a).post(
        reverse("api:outboundwebhook-list"),
        {
            "name": "Ops",
            "url": "https://hooks.example.com/ip",
            "events": ["application.hired"],
        },
        format="json",
    )

    assert response.status_code == 201
    hook = OutboundWebhook.objects.get()
    assert hook.company == company_a
    assert response.data["secret"] == hook.secret

    listed = auth(recruiter_a).get(reverse("api:outboundwebhook-list")).data["results"][0]
    assert listed["secret"] != hook.secret
    assert listed["secret"].endswith(hook.secret[-4:])


def test_unknown_events_are_rejected(auth, recruiter_a):
    response = auth(recruiter_a).post(
        reverse("api:outboundwebhook-list"),
        {"name": "Bad", "url": "https://x.test/h", "events": ["nope.nope"]},
        format="json",
    )
    assert response.status_code == 400
    assert "Unknown events" in str(response.data["events"])


def test_webhooks_can_be_updated_and_deleted(auth, recruiter_a, company_a):
    hook = OutboundWebhook.objects.create(
        company=company_a, name="Ops", url="https://x.test/h"
    )
    client = auth(recruiter_a)

    patched = client.patch(
        reverse("api:outboundwebhook-detail", args=[hook.pk]),
        {"active": False},
        format="json",
    )
    assert patched.status_code == 200
    hook.refresh_from_db()
    assert hook.active is False

    assert client.delete(
        reverse("api:outboundwebhook-detail", args=[hook.pk])
    ).status_code == 204
    assert OutboundWebhook.objects.count() == 0


def test_another_companys_webhook_is_invisible(auth, recruiter_a, company_b):
    hook = OutboundWebhook.objects.create(
        company=company_b, name="Theirs", url="https://y.test/h"
    )
    response = auth(recruiter_a).get(
        reverse("api:outboundwebhook-detail", args=[hook.pk])
    )
    assert response.status_code == 404


def test_the_test_action_sends_a_delivery(auth, recruiter_a, company_a, monkeypatch):
    from integrations import delivery as delivery_module

    hook = OutboundWebhook.objects.create(
        company=company_a, name="Ops", url="https://x.test/h"
    )
    monkeypatch.setattr(
        delivery_module,
        "post",
        lambda *a, **k: type("R", (), {"status_code": 200})(),
    )

    response = auth(recruiter_a).post(
        reverse("api:outboundwebhook-send-test", args=[hook.pk])
    )

    assert response.status_code == 200
    assert response.data["status"] == "SENT"
    assert response.data["response_code"] == 200


# --- hires CSV -----------------------------------------------------------
def _rows(response):
    body = b"".join(response.streaming_content).decode()
    return list(csv.reader(io.StringIO(body)))


def _hire(application, when, salary=None, joining=None):
    application.status = Application.HIRED
    application.save(update_fields=["status"])
    if salary is not None:
        Offer.objects.create(
            application=application,
            salary=salary,
            joining_date=joining,
            status=Offer.ACCEPTED,
        )
    Application.objects.filter(pk=application.pk).update(updated_at=when)
    application.refresh_from_db()
    return application


def test_hires_csv_streams_a_header_and_one_row_per_hire(
    auth, recruiter_a, application
):
    _hire(application, timezone.now(), salary=1500000, joining=date(2026, 5, 1))

    response = auth(recruiter_a).get(reverse("api:export-hires"))
    rows = _rows(response)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert 'filename="hires.csv"' in response["Content-Disposition"]
    assert rows[0][:5] == [
        "application_id",
        "candidate_name",
        "candidate_email",
        "candidate_phone",
        "job_title",
    ]
    assert len(rows) == 2

    row = dict(zip(rows[0], rows[1], strict=True))
    assert row["application_id"] == str(application.pk)
    assert row["candidate_email"] == "cand@example.com"
    assert row["job_title"] == "Python Developer"
    assert row["offer_status"] == "ACCEPTED"
    assert row["salary"] == "1500000.00"
    assert row["joining_date"] == "2026-05-01"


def test_hires_csv_excludes_applications_that_are_not_hired(
    auth, recruiter_a, application
):
    rows = _rows(auth(recruiter_a).get(reverse("api:export-hires")))
    assert len(rows) == 1  # header only


def test_hires_csv_excludes_other_companies(auth, recruiter_a, application_b):
    _hire(application_b, timezone.now(), salary=1)
    rows = _rows(auth(recruiter_a).get(reverse("api:export-hires")))
    assert len(rows) == 1


def test_hires_csv_honours_the_date_window(auth, recruiter_a, application):
    _hire(application, timezone.now() - timedelta(days=40))
    url = reverse("api:export-hires")
    client = auth(recruiter_a)

    recent = (timezone.now() - timedelta(days=7)).date().isoformat()
    assert len(_rows(client.get(url, {"from": recent}))) == 1

    old = (timezone.now() - timedelta(days=60)).date().isoformat()
    assert len(_rows(client.get(url, {"from": old}))) == 2


def test_hires_csv_to_is_inclusive_of_the_whole_day(auth, recruiter_a, application):
    hired = _hire(application, timezone.now())
    same_day = hired.updated_at.date().isoformat()
    rows = _rows(auth(recruiter_a).get(reverse("api:export-hires"), {"to": same_day}))
    assert len(rows) == 2


def test_hires_csv_rejects_an_unparseable_date(auth, recruiter_a):
    response = auth(recruiter_a).get(reverse("api:export-hires"), {"from": "last-tuesday"})
    assert response.status_code == 400
    assert "YYYY-MM-DD" in str(response.data)


def test_hires_csv_names_the_client_for_a_staffing_placement(
    auth, recruiter_a, company_a, application
):
    client_row = Client.objects.create(company=company_a, name="Globex")
    application.job.client = client_row
    application.job.save(update_fields=["client"])
    _hire(application, timezone.now())

    rows = _rows(auth(recruiter_a).get(reverse("api:export-hires")))
    assert dict(zip(rows[0], rows[1], strict=True))["client"] == "Globex"


# --- schema --------------------------------------------------------------
def test_the_openapi_schema_documents_the_phase3_paths(auth, owner_a):
    schema = auth(owner_a).get(reverse("api:schema"), {"format": "json"}).data
    for path in (
        "/api/v1/interviews/",
        "/api/v1/offers/",
        "/api/v1/submissions/",
        "/api/v1/video-invites/",
        "/api/v1/talent/",
        "/api/v1/webhooks/",
        "/api/v1/exports/hires.csv",
    ):
        assert path in schema["paths"]
