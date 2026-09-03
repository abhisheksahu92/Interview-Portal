import pytest
from django.urls import reverse

from video.models import VideoResponse

from .conftest import webm_upload

pytestmark = pytest.mark.usefixtures("video_plan")


@pytest.fixture
def response_row(invite, question):
    return VideoResponse.objects.create(
        invite=invite,
        question=question,
        file=webm_upload(size=1000),
        duration_seconds=30,
        mime="video/webm",
    )


def stream_url(row):
    return reverse("video:response_stream", args=[row.pk])


def test_anonymous_cannot_stream(client, response_row):
    assert client.get(stream_url(response_row)).status_code == 403


def test_company_member_streams_the_whole_file(client, owner, response_row):
    client.force_login(owner)
    reply = client.get(stream_url(response_row))
    assert reply.status_code == 200
    assert reply["Accept-Ranges"] == "bytes"
    assert reply["Content-Length"] == "1000"
    assert b"".join(reply.streaming_content) == b"0" * 1000


def test_range_request_returns_206_with_the_slice(client, owner, response_row):
    client.force_login(owner)
    reply = client.get(stream_url(response_row), HTTP_RANGE="bytes=10-19")
    assert reply.status_code == 206
    assert reply["Content-Range"] == "bytes 10-19/1000"
    assert reply["Content-Length"] == "10"
    assert b"".join(reply.streaming_content) == b"0" * 10


def test_open_ended_and_unsatisfiable_ranges(client, owner, response_row):
    client.force_login(owner)
    tail = client.get(stream_url(response_row), HTTP_RANGE="bytes=990-")
    assert tail.status_code == 206
    assert tail["Content-Range"] == "bytes 990-999/1000"
    bad = client.get(stream_url(response_row), HTTP_RANGE="bytes=5000-6000")
    assert bad.status_code == 416
    assert bad["Content-Range"] == "bytes */1000"


def test_owning_candidate_may_stream_but_a_stranger_may_not(
    client, response_row, candidate, db
):
    client.force_login(candidate.user)
    assert client.get(stream_url(response_row)).status_code == 200

    from core.models import User
    from jobs.models import CandidateProfile

    other = CandidateProfile.objects.create(
        user=User.objects.create_user(
            email="nosy@example.test", password="pw12345678", is_candidate=True
        ),
        experience_years=1,
    )
    client.force_login(other.user)
    assert client.get(stream_url(response_row)).status_code == 403


def test_member_without_the_video_feature_cannot_stream(
    client, owner, company, response_row
):
    from billing.models import Subscription

    Subscription.objects.filter(company=company).delete()
    client.force_login(owner)
    assert client.get(stream_url(response_row)).status_code == 403
