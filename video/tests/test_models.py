from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from video.models import (
    MAX_RESPONSE_BYTES,
    VideoInvite,
    VideoResponse,
    normalise_mime,
    validate_response_file,
)

from .conftest import webm_upload


def test_invite_gets_token_and_deadline_from_the_screen(application, screen):
    invite = VideoInvite.objects.create(application=application, screen=screen)
    assert invite.token and len(invite.token) > 20
    assert invite.status == VideoInvite.PENDING
    expected = timezone.now() + timedelta(days=screen.deadline_days)
    assert abs((invite.expires_at - expected).total_seconds()) < 60
    assert invite.company == application.job.company


def test_expired_invite_is_not_open(invite):
    invite.expires_at = timezone.now() - timedelta(minutes=1)
    invite.save(update_fields=["expires_at"])
    assert invite.is_expired is True
    assert invite.is_open is False
    invite.mark_expired()
    invite.refresh_from_db()
    assert invite.status == VideoInvite.EXPIRED


def test_next_question_walks_unanswered_questions(invite, question):
    assert invite.next_question() == question
    VideoResponse.objects.create(
        invite=invite, question=question, file=webm_upload(), duration_seconds=30
    )
    assert invite.next_question() is None
    assert invite.progress == {"answered": 1, "total": 1}


def test_one_response_per_question(invite, question):
    VideoResponse.objects.create(invite=invite, question=question, file=webm_upload())
    with pytest.raises(IntegrityError), transaction.atomic():
        VideoResponse.objects.create(
            invite=invite, question=question, file=webm_upload()
        )


def test_minutes_billed_rounds_up(invite, question):
    response = VideoResponse.objects.create(
        invite=invite, question=question, file=webm_upload(), duration_seconds=61
    )
    assert response.minutes_billed == 2
    response.duration_seconds = 0
    assert response.minutes_billed == 1


def test_file_validator_rejects_bad_extension_and_size():
    with pytest.raises(ValidationError):
        validate_response_file(webm_upload(name="answer.mov"))
    big = webm_upload(size=16)
    big.size = MAX_RESPONSE_BYTES + 1
    with pytest.raises(ValidationError):
        validate_response_file(big)


def test_normalise_mime_strips_codecs():
    assert normalise_mime("video/webm;codecs=vp8,opus") == "video/webm"
    assert normalise_mime("") == ""
