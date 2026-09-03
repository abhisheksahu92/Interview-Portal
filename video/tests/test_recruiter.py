import pytest
from django.urls import reverse

from jobs.models import StageReview
from video.models import VideoQuestion, VideoResponse, VideoScreen

from .conftest import webm_upload

pytestmark = pytest.mark.usefixtures("video_plan")


def test_index_lists_screens_and_invites(client, owner, invite):
    client.force_login(owner)
    page = client.get(reverse("video:index"))
    assert page.status_code == 200
    assert b"Intro screen" in page.content


def test_feature_gate_blocks_a_company_without_video(client, owner, company):
    from billing.models import Subscription

    Subscription.objects.filter(company=company).delete()
    client.force_login(owner)
    assert client.get(reverse("video:index")).status_code == 403


def test_question_library_crud(client, owner, company):
    client.force_login(owner)
    created = client.post(
        reverse("video:question_create"),
        {"text": "Why us?", "think_seconds": 20, "answer_seconds": 60, "order": 1},
    )
    assert created.status_code == 302
    question = VideoQuestion.objects.get(text="Why us?")
    assert question.company == company

    client.post(
        reverse("video:question_edit", args=[question.pk]),
        {"text": "Why here?", "think_seconds": 20, "answer_seconds": 90, "order": 1},
    )
    question.refresh_from_db()
    assert question.text == "Why here?" and question.answer_seconds == 90

    client.post(reverse("video:question_delete", args=[question.pk]))
    assert not VideoQuestion.objects.filter(pk=question.pk).exists()


def test_question_library_is_tenant_scoped(client, owner, db):
    from core.models import Company

    other = Company.objects.create(name="Other Co")
    stranger = VideoQuestion.objects.create(company=other, text="Theirs")
    client.force_login(owner)
    assert client.get(
        reverse("video:question_edit", args=[stranger.pk])
    ).status_code == 404


def test_screen_builder_creates_a_screen_with_ordered_questions(
    client, owner, job, question
):
    client.force_login(owner)
    second = VideoQuestion.objects.create(company=job.company, text="Second", order=1)
    stage = job.stages.first()
    response = client.post(
        reverse("video:screen_create", args=[job.pk]),
        {
            "title": "Screening video",
            "stage": stage.pk,
            "deadline_days": 3,
            "is_active": "on",
            "questions": [question.pk, second.pk],
        },
    )
    assert response.status_code == 302
    screen = VideoScreen.objects.get(title="Screening video")
    assert screen.stage == stage and screen.deadline_days == 3
    assert list(screen.ordered_questions()) == [question, second]


def test_invite_list_filters_by_status(client, owner, invite):
    client.force_login(owner)
    page = client.get(reverse("video:invite_list"), {"status": "SUBMITTED"})
    assert page.status_code == 200
    assert list(page.context["invites"]) == []
    page = client.get(reverse("video:invite_list"), {"status": "PENDING"})
    assert list(page.context["invites"]) == [invite]


def test_review_page_writes_a_stage_review(client, owner, invite, question):
    VideoResponse.objects.create(
        invite=invite, question=question, file=webm_upload(), duration_seconds=30,
        transcript="I build APIs.", ai_summary="Solid answer.", ai_score=78,
    )
    client.force_login(owner)
    page = client.get(reverse("video:invite_review", args=[invite.pk]))
    assert page.status_code == 200
    assert b"Solid answer." in page.content

    stage = invite.application.current_stage
    posted = client.post(
        reverse("video:invite_review", args=[invite.pk]),
        {"decision": StageReview.HOLD, "rating": 4, "feedback": "Nice comms."},
    )
    assert posted.status_code == 302
    review = StageReview.objects.get(application=invite.application, stage=stage)
    assert review.reviewer == owner
    assert review.decision == StageReview.HOLD
    assert review.rating == 4
    assert review.feedback == "Nice comms."


def test_review_from_another_company_is_404(client, invite, db):
    from core.models import Company, Membership, User

    other = Company.objects.create(name="Other Co")
    user = User.objects.create_user(email="x@other.test", password="pw12345678")
    Membership.objects.create(user=user, company=other, role=Membership.OWNER)
    from billing.models import Plan, Subscription

    Subscription.objects.update_or_create(
        company=other,
        defaults={
            "plan": Plan.objects.get(code=Plan.PRO),
            "status": Subscription.ACTIVE,
        },
    )
    client.force_login(user)
    assert client.get(
        reverse("video:invite_review", args=[invite.pk])
    ).status_code == 404
