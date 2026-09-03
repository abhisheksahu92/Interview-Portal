import pytest
from django.core import mail

from video.models import VideoInvite, VideoResponse, VideoScreen, VideoScreenQuestion
from video.processing import NO_TRANSCRIPT_SUMMARY, process_response

from .conftest import webm_upload


@pytest.fixture
def stage_screen(job, question):
    """An active screen bound to the job's first stage."""
    screen = VideoScreen.objects.create(
        job=job, stage=job.stages.first(), title="Auto screen", deadline_days=4
    )
    VideoScreenQuestion.objects.create(screen=screen, question=question, order=0)
    return screen


def test_auto_invite_on_entering_a_screened_stage(job, candidate, stage_screen):
    from jobs.models import Application

    mail.outbox = []
    application = Application.objects.create(
        job=job, candidate=candidate, current_stage=job.stages.first()
    )
    invite = VideoInvite.objects.get(application=application, screen=stage_screen)
    assert invite.status == VideoInvite.PENDING
    assert any(invite.token in message.body for message in mail.outbox)


def test_no_auto_invite_without_an_active_screen(job, candidate, stage_screen):
    from jobs.models import Application

    stage_screen.is_active = False
    stage_screen.save(update_fields=["is_active"])
    Application.objects.create(
        job=job, candidate=candidate, current_stage=job.stages.first()
    )
    assert VideoInvite.objects.count() == 0


def test_auto_invite_is_not_duplicated_on_resave(job, candidate, stage_screen):
    from jobs.models import Application

    application = Application.objects.create(
        job=job, candidate=candidate, current_stage=job.stages.first()
    )
    application.save()
    assert VideoInvite.objects.filter(application=application).count() == 1


def test_processing_without_a_transcription_key_leaves_a_clear_note(invite, question):
    row = VideoResponse.objects.create(
        invite=invite, question=question, file=webm_upload(), duration_seconds=30
    )
    process_response(row)
    row.refresh_from_db()
    assert row.transcript == ""
    assert row.ai_summary == NO_TRANSCRIPT_SUMMARY
    assert row.ai_score is None
    assert row.status == VideoResponse.PROCESSED
    assert row.processed_at is not None


def test_processing_scores_a_transcript_with_mocked_ai(
    invite, question, monkeypatch
):
    monkeypatch.setattr("video.gateway.configured", lambda: True)
    monkeypatch.setattr("video.gateway.transcribe", lambda row: "I built a REST API.")
    monkeypatch.setattr(
        "video.ai.review_answer",
        lambda text, transcript: {"score": 82, "summary": "Clear and specific."},
    )
    row = VideoResponse.objects.create(
        invite=invite, question=question, file=webm_upload(), duration_seconds=40
    )
    process_response(row)
    row.refresh_from_db()
    assert row.transcript == "I built a REST API."
    assert row.ai_score == 82
    assert row.ai_summary == "Clear and specific."
    assert row.status == VideoResponse.PROCESSED


def test_processing_survives_an_ai_failure(invite, question, monkeypatch):
    monkeypatch.setattr("video.gateway.configured", lambda: True)
    monkeypatch.setattr("video.gateway.transcribe", lambda row: "Some words.")
    monkeypatch.setattr("video.ai.review_answer", lambda text, transcript: None)
    row = VideoResponse.objects.create(
        invite=invite, question=question, file=webm_upload()
    )
    process_response(row)
    row.refresh_from_db()
    assert row.status == VideoResponse.PROCESSED
    assert row.ai_score is None


def test_management_command_processes_pending_responses(invite, question, capsys):
    from django.core.management import call_command

    VideoResponse.objects.create(
        invite=invite, question=question, file=webm_upload(), duration_seconds=30
    )
    call_command("process_video_responses")
    out = capsys.readouterr().out
    assert "Processed 1" in out
    assert VideoResponse.objects.filter(status=VideoResponse.PROCESSED).count() == 1


def test_ai_review_is_key_gated(settings):
    from video import ai

    settings.ANTHROPIC_API_KEY = ""
    assert ai.get_client() is None
    assert ai.review_answer("Q", "some transcript") is None


def test_gateway_is_not_configured_without_a_key(settings):
    from video import gateway

    settings.VIDEO_TRANSCRIBE_API_KEY = ""
    assert gateway.configured() is False
    assert gateway.transcribe(object()) == ""
