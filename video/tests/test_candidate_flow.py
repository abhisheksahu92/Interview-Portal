from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from video.models import VideoInvite, VideoResponse

from .conftest import webm_upload


def take_url(invite):
    return reverse("video:take", args=[invite.token])


def upload_url(invite):
    return reverse("video:take_upload", args=[invite.token])


def test_take_page_renders_for_a_valid_token(client, invite, question):
    response = client.get(take_url(invite))
    assert response.status_code == 200
    assert question.text.encode() in response.content


def test_unknown_token_is_404(client, db):
    assert client.get(reverse("video:take", args=["nope"])).status_code == 404


def test_take_page_is_gone_after_the_deadline(client, invite):
    VideoInvite.objects.filter(pk=invite.pk).update(
        expires_at=timezone.now() - timedelta(days=1)
    )
    response = client.get(take_url(invite))
    assert response.status_code == 410
    invite.refresh_from_db()
    assert invite.status == VideoInvite.EXPIRED


def test_upload_stores_a_response_and_starts_the_invite(client, invite, question):
    response = client.post(
        upload_url(invite),
        {"question": question.pk, "duration": 45, "file": webm_upload()},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["answered"] == 1
    assert payload["next_question_id"] is None
    row = VideoResponse.objects.get(pk=payload["response_id"])
    assert row.mime == "video/webm"
    assert row.duration_seconds == 45
    invite.refresh_from_db()
    assert invite.status == VideoInvite.IN_PROGRESS


def test_upload_rejects_an_unsupported_mime_type(client, invite, question):
    response = client.post(
        upload_url(invite),
        {
            "question": question.pk,
            "file": webm_upload(name="answer.mov", content_type="video/quicktime"),
        },
    )
    assert response.status_code == 415
    assert VideoResponse.objects.count() == 0


def test_upload_rejects_files_over_the_size_cap(client, invite, question, monkeypatch):
    monkeypatch.setattr("video.views.MAX_RESPONSE_BYTES", 10)
    response = client.post(
        upload_url(invite), {"question": question.pk, "file": webm_upload(size=64)}
    )
    assert response.status_code == 413
    assert VideoResponse.objects.count() == 0


def test_upload_refuses_a_second_answer_to_the_same_question(client, invite, question):
    client.post(upload_url(invite), {"question": question.pk, "file": webm_upload()})
    again = client.post(
        upload_url(invite), {"question": question.pk, "file": webm_upload()}
    )
    assert again.status_code == 409
    assert VideoResponse.objects.count() == 1


def test_upload_refused_after_the_deadline(client, invite, question):
    VideoInvite.objects.filter(pk=invite.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    response = client.post(
        upload_url(invite), {"question": question.pk, "file": webm_upload()}
    )
    assert response.status_code == 410
    assert VideoResponse.objects.count() == 0


def test_upload_rejects_a_question_from_another_screen(client, invite, company):
    from video.models import VideoQuestion

    stranger = VideoQuestion.objects.create(company=company, text="Not on the screen")
    response = client.post(
        upload_url(invite), {"question": stranger.pk, "file": webm_upload()}
    )
    assert response.status_code == 400


def test_resume_skips_already_answered_questions(client, invite, question):
    client.post(upload_url(invite), {"question": question.pk, "file": webm_upload()})
    page = client.get(take_url(invite))
    assert page.status_code == 200
    assert page.context["next_question"] is None
    assert page.context["answered_ids"] == [question.pk]


def test_submit_requires_every_question_then_marks_submitted(client, invite, question):
    early = client.post(reverse("video:take_submit", args=[invite.token]))
    assert early.status_code == 302
    invite.refresh_from_db()
    assert invite.status == VideoInvite.PENDING

    client.post(upload_url(invite), {"question": question.pk, "file": webm_upload()})
    done = client.post(reverse("video:take_submit", args=[invite.token]))
    assert done.status_code == 302
    invite.refresh_from_db()
    assert invite.status == VideoInvite.SUBMITTED
    assert invite.submitted_at is not None
    assert client.get(reverse("video:take_done", args=[invite.token])).status_code == 200


def test_usage_is_consumed_per_recorded_minute(client, invite, question, monkeypatch):
    calls = []

    def fake_consume(company, kind, qty=1):
        calls.append((company, kind, qty))

    import video.services as services

    monkeypatch.setattr(
        services, "consume_minutes", lambda company, seconds: (
            fake_consume(company, "VIDEO_MINUTE", max(1, -(-seconds // 60))) or True
        )
    )
    response = client.post(
        upload_url(invite), {"question": question.pk, "duration": 90, "file": webm_upload()}
    )
    assert response.status_code == 200
    assert calls == [(invite.company, "VIDEO_MINUTE", 2)]


def test_over_quota_upload_is_refused(client, invite, question, monkeypatch):
    import video.services as services

    monkeypatch.setattr(services, "consume_minutes", lambda company, seconds: False)
    response = client.post(
        upload_url(invite), {"question": question.pk, "file": webm_upload()}
    )
    assert response.status_code == 402
    assert VideoResponse.objects.count() == 0
