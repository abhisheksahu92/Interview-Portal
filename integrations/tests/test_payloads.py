from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from unittest.mock import Mock

import pytest

from integrations.payloads import (
    _iso,
    application_data,
    candidate_data,
    interview_data,
    offer_data,
)


# ==========================================
# _iso helper tests (PR #29)
# ==========================================
def test_iso_helper():
    assert _iso(None) is None

    dt = datetime(2023, 1, 1, 12, 0, 0)
    assert _iso(dt) == dt.isoformat()

    d = date(2023, 1, 1)
    assert _iso(d) == d.isoformat()


# ==========================================
# candidate_data tests (PR #29)
# ==========================================
def test_candidate_data_is_empty_when_none():
    assert candidate_data(None) == {}


def test_candidate_data_with_full_candidate(candidate):
    data = candidate_data(candidate)

    assert data["id"] == candidate.pk
    assert data["email"] == candidate.user.email
    assert data["name"] == candidate.user.get_full_name()
    assert data["phone"] == candidate.phone
    assert data["experience_years"] == str(candidate.experience_years)


def test_candidate_data_handles_missing_user():
    class DummyCandidate:
        pk = 1
        phone = "+1234567890"
        experience_years = 5.0

    candidate = DummyCandidate()
    data = candidate_data(candidate)

    assert data["id"] == 1
    assert data["email"] is None
    assert data["name"] is None
    assert data["phone"] == "+1234567890"
    assert data["experience_years"] == "5.0"


def test_candidate_data_handles_empty_fields(candidate):
    candidate.phone = ""
    candidate.experience_years = 0.0
    candidate.user.first_name = ""
    candidate.user.last_name = ""

    data = candidate_data(candidate)

    assert data["phone"] is None
    assert data["name"] is None
    assert data["experience_years"] == "0.0"


# ==========================================
# application_data tests (PR #17)
# ==========================================
def test_application_data_full():
    """Test application_data payload builder with fully populated fields."""
    job_mock = Mock()
    job_mock.pk = 123
    job_mock.title = "Software Engineer"
    job_mock.location = "San Francisco, CA"
    job_mock.status = "open"

    stage_mock = Mock()
    stage_mock.pk = 456
    stage_mock.name = "Initial Screen"
    stage_mock.kind = "screening"

    candidate_mock = Mock()
    candidate_mock.pk = 789
    candidate_mock.phone = "123-456-7890"
    candidate_mock.experience_years = 5
    user_mock = Mock()
    user_mock.email = "test@example.com"
    user_mock.get_full_name.return_value = "Test User"
    candidate_mock.user = user_mock

    application_mock = Mock()
    application_mock.pk = 101112
    application_mock.status = "active"
    application_mock.created_at = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    application_mock.job = job_mock
    application_mock.current_stage = stage_mock
    application_mock.candidate = candidate_mock
    application_mock.ai_fit_score = 0.95

    result = application_data(application_mock)

    assert result == {
        "id": 101112,
        "status": "active",
        "created_at": "2023-01-01T12:00:00+00:00",
        "job": {
            "id": 123,
            "title": "Software Engineer",
            "location": "San Francisco, CA",
            "status": "open",
        },
        "stage": {
            "id": 456,
            "name": "Initial Screen",
            "kind": "screening",
        },
        "candidate": {
            "id": 789,
            "email": "test@example.com",
            "name": "Test User",
            "phone": "123-456-7890",
            "experience_years": "5",
        },
        "ai_fit_score": 0.95,
    }


def test_application_data_minimal():
    """Test application_data payload builder with minimal or empty fields to verify null handling."""
    job_mock = Mock()
    job_mock.pk = 123
    job_mock.title = "Software Engineer"
    job_mock.location = "San Francisco, CA"
    job_mock.status = "open"

    candidate_mock = Mock()
    candidate_mock.pk = 789
    candidate_mock.phone = None
    candidate_mock.experience_years = 0
    candidate_mock.user = None

    application_mock = Mock()
    application_mock.pk = 101112
    application_mock.status = "active"
    application_mock.created_at = None
    application_mock.job = job_mock
    application_mock.current_stage = None
    application_mock.candidate = candidate_mock
    application_mock.ai_fit_score = None

    result = application_data(application_mock)

    assert result == {
        "id": 101112,
        "status": "active",
        "created_at": None,
        "job": {
            "id": 123,
            "title": "Software Engineer",
            "location": "San Francisco, CA",
            "status": "open",
        },
        "stage": None,
        "candidate": {
            "id": 789,
            "email": None,
            "name": None,
            "phone": None,
            "experience_years": "0",
        },
        "ai_fit_score": None,
    }


# ==========================================
# interview_data tests (PR #25)
# ==========================================
def test_interview_data_payload_structure():
    mock_interviewer = Mock()
    mock_interviewer.email = "interviewer@example.com"

    mock_application = Mock()
    mock_application.job = Mock(pk=2, title="Job Title", location="Location", status="OPEN")

    mock_stage = Mock(pk=3, kind="INTERVIEW")
    mock_stage.name = "Stage"
    mock_application.current_stage = mock_stage

    mock_application.pk = 1
    mock_application.status = "ACTIVE"
    mock_application.created_at = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    mock_application.candidate = Mock(
        pk=4,
        phone="+1234567890",
        experience_years=5,
        user=Mock(email="candidate@example.com", get_full_name=lambda: "Candidate Name"),
    )
    mock_application.ai_fit_score = 85.5

    mock_interview = Mock()
    mock_interview.pk = 10
    mock_interview.status = "CONFIRMED"
    mock_interview.scheduled_start = datetime(2023, 2, 1, 10, 0, 0, tzinfo=UTC)
    mock_interview.scheduled_end = datetime(2023, 2, 1, 11, 0, 0, tzinfo=UTC)
    mock_interview.timezone = "UTC"
    mock_interview.location_or_link = "https://zoom.us/j/123"

    mock_interview.interviewers.all.return_value = [mock_interviewer]
    mock_interview.application = mock_application

    payload = interview_data(mock_interview)

    expected_payload = {
        "id": 10,
        "status": "CONFIRMED",
        "scheduled_start": "2023-02-01T10:00:00+00:00",
        "scheduled_end": "2023-02-01T11:00:00+00:00",
        "timezone": "UTC",
        "location_or_link": "https://zoom.us/j/123",
        "interviewers": ["interviewer@example.com"],
        "application": {
            "id": 1,
            "status": "ACTIVE",
            "created_at": "2023-01-01T12:00:00+00:00",
            "job": {
                "id": 2,
                "title": "Job Title",
                "location": "Location",
                "status": "OPEN",
            },
            "stage": {"id": 3, "name": "Stage", "kind": "INTERVIEW"},
            "candidate": {
                "id": 4,
                "email": "candidate@example.com",
                "name": "Candidate Name",
                "phone": "+1234567890",
                "experience_years": "5",
            },
            "ai_fit_score": 85.5,
        },
    }

    assert payload == expected_payload


def test_interview_data_with_missing_dates_and_location():
    mock_interviewer = Mock()
    mock_interviewer.email = "interviewer@example.com"

    mock_application = Mock()
    mock_application.job = Mock(pk=2, title="Job Title", location="Location", status="OPEN")
    mock_stage = Mock(pk=3, kind="INTERVIEW")
    mock_stage.name = "Stage"
    mock_application.current_stage = mock_stage
    mock_application.pk = 1
    mock_application.status = "ACTIVE"
    mock_application.created_at = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    mock_application.candidate = Mock(
        pk=4,
        phone="+1234567890",
        experience_years=5,
        user=Mock(email="candidate@example.com", get_full_name=lambda: "Candidate Name"),
    )
    mock_application.ai_fit_score = 85.5

    mock_interview = Mock()
    mock_interview.pk = 10
    mock_interview.status = "PROPOSED"
    mock_interview.scheduled_start = None
    mock_interview.scheduled_end = None
    mock_interview.timezone = "UTC"
    mock_interview.location_or_link = ""

    mock_interview.interviewers.all.return_value = []
    mock_interview.application = mock_application

    payload = interview_data(mock_interview)

    expected_payload = {
        "id": 10,
        "status": "PROPOSED",
        "scheduled_start": None,
        "scheduled_end": None,
        "timezone": "UTC",
        "location_or_link": "",
        "interviewers": [],
        "application": {
            "id": 1,
            "status": "ACTIVE",
            "created_at": "2023-01-01T12:00:00+00:00",
            "job": {
                "id": 2,
                "title": "Job Title",
                "location": "Location",
                "status": "OPEN",
            },
            "stage": {"id": 3, "name": "Stage", "kind": "INTERVIEW"},
            "candidate": {
                "id": 4,
                "email": "candidate@example.com",
                "name": "Candidate Name",
                "phone": "+1234567890",
                "experience_years": "5",
            },
            "ai_fit_score": 85.5,
        },
    }

    assert payload == expected_payload


# ==========================================
# offer_data tests (PR #7)
# ==========================================
@dataclass
class FakeJob:
    pk: int = 1
    title: str = "Software Engineer"
    location: str = "Remote"
    status: str = "open"


@dataclass
class FakeStage:
    pk: int = 2
    name: str = "Offer"
    kind: str = "offer"


@dataclass
class FakeUser:
    email: str = "cand@example.com"

    def get_full_name(self):
        return "John Doe"


@dataclass
class FakeCandidate:
    pk: int = 3
    user: FakeUser | None = field(default_factory=FakeUser)
    phone: str | None = "+1234567890"
    experience_years: int | None = 5


@dataclass
class FakeApplication:
    pk: int = 4
    status: str = "hired"
    created_at: datetime | None = datetime(2023, 1, 1, tzinfo=UTC)
    job: FakeJob = field(default_factory=FakeJob)
    current_stage: FakeStage | None = field(default_factory=FakeStage)
    candidate: FakeCandidate | None = field(default_factory=FakeCandidate)
    ai_fit_score: float | None = 0.95


@dataclass
class FakeOffer:
    pk: int = 5
    status: str = "accepted"
    salary: int = 100000
    currency: str = "USD"
    joining_date: date | None = date(2023, 2, 1)
    signed_name: str | None = "John Doe"
    signed_at: datetime | None = datetime(2023, 1, 15, tzinfo=UTC)
    application: FakeApplication = field(default_factory=FakeApplication)


def test_offer_data():
    offer = FakeOffer()
    payload = offer_data(offer)

    assert payload["id"] == 5
    assert payload["status"] == "accepted"
    assert payload["salary"] == "100000"
    assert payload["currency"] == "USD"
    assert payload["joining_date"] == "2023-02-01"
    assert payload["signed_name"] == "John Doe"
    assert payload["signed_at"] == "2023-01-15T00:00:00+00:00"

    app_data = payload["application"]
    assert app_data["id"] == 4
    assert app_data["status"] == "hired"
    assert app_data["created_at"] == "2023-01-01T00:00:00+00:00"
    assert app_data["ai_fit_score"] == 0.95

    job_data = app_data["job"]
    assert job_data["id"] == 1
    assert job_data["title"] == "Software Engineer"
    assert job_data["location"] == "Remote"
    assert job_data["status"] == "open"

    stage_data = app_data["stage"]
    assert stage_data["id"] == 2
    assert stage_data["name"] == "Offer"
    assert stage_data["kind"] == "offer"

    cand_data = app_data["candidate"]
    assert cand_data["id"] == 3
    assert cand_data["email"] == "cand@example.com"
    assert cand_data["name"] == "John Doe"
    assert cand_data["phone"] == "+1234567890"
    assert cand_data["experience_years"] == "5"


def test_offer_data_with_nulls():
    offer = FakeOffer(
        signed_name=None,
        signed_at=None,
        joining_date=None,
        application=FakeApplication(
            current_stage=None,
            candidate=None,
        ),
    )
    payload = offer_data(offer)

    assert payload["signed_name"] is None
    assert payload["signed_at"] is None
    assert payload["joining_date"] is None

    app_data = payload["application"]
    assert app_data["stage"] is None
    assert app_data["candidate"] == {}


def test_offer_data_with_empty_strings():
    offer = FakeOffer(
        signed_name="",
        application=FakeApplication(
            candidate=FakeCandidate(
                phone="",
            )
        ),
    )
    payload = offer_data(offer)

    assert payload["signed_name"] is None

    app_data = payload["application"]
    cand_data = app_data["candidate"]
    assert cand_data["phone"] is None


def test_candidate_without_user():
    offer = FakeOffer(
        application=FakeApplication(
            candidate=FakeCandidate(
                user=None,
            )
        )
    )
    payload = offer_data(offer)

    cand_data = payload["application"]["candidate"]
    assert cand_data["email"] is None
    assert cand_data["name"] is None
