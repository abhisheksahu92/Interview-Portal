"""Uploads are candidate-controlled: sniff the container, cap the duration."""

import struct

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from video import validators
from video.models import VideoResponse

from .conftest import bogus_upload, mp4_upload, webm_upload

pytestmark = pytest.mark.django_db


def upload_url(invite):
    return reverse("video:take_upload", args=[invite.token])


# --- container sniffing ---------------------------------------------------


def test_sniff_recognises_webm_and_mp4():
    assert validators.sniff_container(webm_upload()) == "webm"
    assert validators.sniff_container(mp4_upload()) == "mp4"


def test_sniff_rejects_other_bytes_and_shrugs_at_empty():
    assert validators.sniff_container(bogus_upload()) == ""
    assert validators.sniff_container(SimpleUploadedFile("a.webm", b"")) is None


def test_check_container_flags_a_mislabelled_file():
    with pytest.raises(validators.UnsupportedContainer):
        validators.check_container(mp4_upload(), "video/webm", "webm")
    with pytest.raises(validators.UnsupportedContainer):
        validators.check_container(bogus_upload(), "video/webm", "webm")
    assert validators.check_container(webm_upload(), "video/webm", "webm") == "webm"


def test_check_container_does_not_consume_the_file():
    upload = webm_upload(size=64)
    validators.check_container(upload, "video/webm", "webm")
    assert len(upload.read()) == 64


def test_upload_rejects_a_pdf_dressed_as_a_recording(client, invite, question):
    reply = client.post(
        upload_url(invite),
        {"question": question.pk, "duration": 10, "file": bogus_upload()},
    )
    assert reply.status_code == 415
    assert reply.json()["ok"] is False
    assert VideoResponse.objects.count() == 0


def test_upload_rejects_mp4_bytes_labelled_as_webm(client, invite, question):
    reply = client.post(
        upload_url(invite),
        {
            "question": question.pk,
            "duration": 10,
            "file": mp4_upload(name="answer.webm", content_type="video/webm"),
        },
    )
    assert reply.status_code == 415
    assert VideoResponse.objects.count() == 0


def test_upload_accepts_a_real_mp4_and_records_its_mime(client, invite, question):
    reply = client.post(
        upload_url(invite),
        {"question": question.pk, "duration": 10, "file": mp4_upload()},
    )
    assert reply.status_code == 200
    assert VideoResponse.objects.get().mime == "video/mp4"


def test_sniffed_container_wins_over_a_vague_declared_type(client, invite, question):
    """A browser that sends application/octet-stream still gets classified."""
    reply = client.post(
        upload_url(invite),
        {
            "question": question.pk,
            "duration": 10,
            "file": mp4_upload(content_type="application/octet-stream"),
        },
    )
    assert reply.status_code == 200
    assert VideoResponse.objects.get().mime == "video/mp4"


# --- duration metering ----------------------------------------------------


def test_max_duration_is_the_answer_allowance_plus_slack(question):
    assert question.answer_seconds == 60
    assert validators.max_duration_for(question) == 65


def test_clamp_duration_bounds_and_sanitises(question):
    assert validators.clamp_duration(30, question) == 30
    assert validators.clamp_duration(99999, question) == 65
    assert validators.clamp_duration(-5, question) == 0
    assert validators.clamp_duration("nonsense", question) == 0
    assert validators.clamp_duration(None, question) == 0
    assert validators.clamp_duration("12.9", question) == 12


def test_probe_duration_reads_an_mp4_mvhd():
    body = (
        b"\x00\x00\x00\x18ftypisom"
        + b"\x00\x00\x00\x6cmvhd"
        + bytes([0])            # version
        + b"\x00\x00\x00"       # flags
        + b"\x00" * 8           # creation / modification time
        + struct.pack(">II", 1000, 42_000)  # timescale, duration -> 42s
    )
    assert validators.probe_duration(SimpleUploadedFile("a.mp4", body)) == 42


def test_probe_duration_returns_none_for_webm_and_junk():
    assert validators.probe_duration(webm_upload()) is None
    assert validators.probe_duration(bogus_upload()) is None
    assert validators.probe_duration(mp4_upload()) is None  # ftyp but no mvhd


def test_metered_duration_prefers_the_real_duration_but_still_caps(question):
    long_mp4 = SimpleUploadedFile(
        "a.mp4",
        b"\x00\x00\x00\x18ftypisom"
        + b"\x00\x00\x00\x6cmvhd"
        + bytes([0])
        + b"\x00\x00\x00"
        + b"\x00" * 8
        + struct.pack(">II", 1, 3600),  # an hour of video
    )
    assert validators.metered_duration(long_mp4, 5, question) == 65


def test_upload_caps_an_inflated_client_duration(client, invite, question):
    """Claiming an hour of video must not bill an hour of video minutes."""
    reply = client.post(
        upload_url(invite),
        {"question": question.pk, "duration": 3600, "file": webm_upload()},
    )
    assert reply.status_code == 200
    assert VideoResponse.objects.get().duration_seconds == 65


def test_upload_consumes_only_the_capped_minutes(
    client, invite, question, monkeypatch
):
    seen = []
    monkeypatch.setattr(
        "video.services.consume_minutes",
        lambda company, seconds: seen.append(seconds) or True,
    )
    client.post(
        upload_url(invite),
        {"question": question.pk, "duration": 99999, "file": webm_upload()},
    )
    assert seen == [65]
