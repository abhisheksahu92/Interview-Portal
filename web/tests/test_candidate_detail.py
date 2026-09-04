"""The recruiter-facing candidate profile page and its résumé stream."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from core.models import Membership
from jobs.models import StageReview
from web.tests.conftest import free_expired, paid


def detail_url(profile):
    return reverse("web:candidate_detail", args=[profile.pk])


def resume_url(profile):
    return reverse("web:candidate_resume", args=[profile.pk])


@pytest.fixture
def application(company, make_job, make_application):
    job = make_job(company)
    return make_application(job, "asha@example.test")


@pytest.fixture
def profile(application):
    return application.candidate


# --- tenant isolation -----------------------------------------------------


@pytest.mark.django_db
def test_a_candidate_of_another_tenant_is_404(
    client, other_owner, other_company, profile
):
    """The profile exists, but not for this workspace."""
    client.force_login(other_owner)
    assert client.get(detail_url(profile)).status_code == 404
    assert client.get(resume_url(profile)).status_code == 404


@pytest.mark.django_db
def test_candidate_with_an_application_here_is_visible(client, owner, profile):
    client.force_login(owner)
    response = client.get(detail_url(profile))
    assert response.status_code == 200
    assert profile.user.email in response.content.decode()


# --- roles ----------------------------------------------------------------


@pytest.mark.django_db
def test_recruiter_may_open_the_profile(client, recruiter, profile):
    client.force_login(recruiter)
    assert client.get(detail_url(profile)).status_code == 200


@pytest.mark.django_db
def test_candidate_user_cannot_open_the_profile(client, candidate, profile):
    client.force_login(candidate)
    assert client.get(detail_url(profile)).status_code == 403


@pytest.mark.django_db
def test_anonymous_is_redirected_to_login(client, profile):
    response = client.get(detail_url(profile))
    assert response.status_code == 302
    assert "/login" in response["Location"]


# --- interviewer conditional access ---------------------------------------


@pytest.mark.django_db
def test_uninvolved_interviewer_is_denied(client, interviewer, profile):
    client.force_login(interviewer)
    assert client.get(detail_url(profile)).status_code == 403
    assert client.get(resume_url(profile)).status_code == 403


@pytest.mark.django_db
def test_interviewer_who_reviewed_gets_read_only_access(
    client, interviewer, application, profile
):
    StageReview.objects.create(
        application=application,
        stage=application.current_stage,
        reviewer=interviewer,
        decision=StageReview.HOLD,
    )
    client.force_login(interviewer)
    response = client.get(detail_url(profile))
    assert response.status_code == 200
    assert response.context["read_only"] is True


@pytest.mark.django_db
def test_interviewer_on_a_scheduled_interview_gets_access(
    client, interviewer, company, application, profile
):
    from scheduling.models import Interview

    interview = Interview.objects.create(
        company=company,
        application=application,
        stage=application.current_stage,
        scheduled_start=timezone.now() + timedelta(days=1),
        scheduled_end=timezone.now() + timedelta(days=1, hours=1),
    )
    interview.interviewers.add(interviewer)
    client.force_login(interviewer)
    assert client.get(detail_url(profile)).status_code == 200


# --- résumé streaming -----------------------------------------------------


@pytest.mark.django_db
def test_resume_is_streamed_as_an_attachment(client, owner, profile):
    profile.resume = SimpleUploadedFile(
        "cv.pdf", b"%PDF-1.4 hello", content_type="application/pdf"
    )
    profile.save()
    client.force_login(owner)
    response = client.get(resume_url(profile))
    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    assert b"".join(response.streaming_content) == b"%PDF-1.4 hello"


@pytest.mark.django_db
def test_resume_page_links_the_view_not_the_media_path(client, owner, profile):
    profile.resume = SimpleUploadedFile(
        "cv.pdf", b"%PDF-1.4 hello", content_type="application/pdf"
    )
    profile.save()
    client.force_login(owner)
    body = client.get(detail_url(profile)).content.decode()
    assert resume_url(profile) in body
    assert "/media/resumes/" not in body


@pytest.mark.django_db
def test_resume_is_404_when_there_is_no_file(client, owner, profile):
    client.force_login(owner)
    assert client.get(resume_url(profile)).status_code == 404


# --- sections -------------------------------------------------------------


def _full_history(company, application, interviewer):
    """One row of every kind the page can show."""
    from assessments.models import Assessment, Attempt
    from clients.models import Client, Submission
    from offers.models import Offer
    from scheduling.models import Interview
    from talent.models import TalentProfile
    from video.models import VideoInvite, VideoScreen

    application.ai_summary = "Strong Django background."
    application.save(update_fields=["ai_summary"])
    StageReview.objects.create(
        application=application,
        stage=application.current_stage,
        reviewer=interviewer,
        decision=StageReview.PASS,
        feedback="Clear thinker.",
    )
    assessment = Assessment.objects.create(
        job=application.job, title="Python basics", stage=application.current_stage
    )
    Attempt.objects.create(
        assessment=assessment,
        application=application,
        submitted_at=timezone.now(),
        score_percent=Decimal("81.00"),
        passed=True,
    )
    interview = Interview.objects.create(
        company=company,
        application=application,
        stage=application.current_stage,
        scheduled_start=timezone.now() + timedelta(days=1),
        scheduled_end=timezone.now() + timedelta(days=1, hours=1),
    )
    interview.interviewers.add(interviewer)
    Offer.objects.create(application=application, salary=Decimal("1500000"))
    client_row = Client.objects.create(company=company, name="Globex Ltd")
    Submission.objects.create(application=application, client=client_row)
    screen = VideoScreen.objects.create(job=application.job, title="Intro screen")
    VideoInvite.objects.create(application=application, screen=screen)
    # The talent app already captures every applicant, so reuse that row.
    talent, _ = TalentProfile.objects.get_or_create(
        company=company,
        email=application.candidate.user.email,
        defaults={"linked_candidate": application.candidate},
    )
    talent.linked_candidate = application.candidate
    talent.name = "Asha R"
    talent.tags = ["referral"]
    talent.save()
    return talent


@pytest.mark.django_db
def test_every_section_renders_when_the_plan_has_the_features(
    client, owner, company, application, profile, interviewer
):
    paid(company)
    talent = _full_history(company, application, interviewer)
    client.force_login(owner)
    response = client.get(detail_url(profile))
    body = response.content.decode()
    assert response.status_code == 200
    for marker in (
        'id="interviews"',
        'id="offers"',
        'id="submissions"',
        'id="video"',
        "Identity",
        "Applications at",
        "Strong Django background.",
        "Clear thinker.",
        "Python basics",
        "Interviews",
        "Offers",
        "Client submissions",
        "Globex Ltd",
        "Video screens",
        "Intro screen",
        "Talent CRM",
        "referral",
        "Timeline",
    ):
        assert marker in body, marker
    assert response.context["interviews"]
    assert response.context["offers"]
    assert response.context["submissions"]
    assert response.context["video_invites"]
    assert response.context["talent_profile"] == talent
    # the timeline merges every source, newest first
    kinds = {event["kind"] for event in response.context["timeline"]}
    assert kinds == {
        "application",
        "review",
        "attempt",
        "interview",
        "offer",
        "submission",
        "video",
    }
    stamps = [event["when"] for event in response.context["timeline"]]
    assert stamps == sorted(stamps, reverse=True)


@pytest.mark.django_db
def test_paid_feature_sections_are_hidden_on_a_free_plan(
    client, owner, company, application, profile, interviewer
):
    _full_history(company, application, interviewer)
    free_expired(company)
    client.force_login(owner)
    response = client.get(detail_url(profile))
    body = response.content.decode()
    assert response.context["interviews"] is None
    assert response.context["offers"] is None
    assert response.context["submissions"] is None
    assert response.context["video_invites"] is None
    for section in ('id="interviews"', 'id="offers"', 'id="submissions"', 'id="video"'):
        assert section not in body, section
    assert "Globex Ltd" not in body
    assert "Intro screen" not in body
    # the always-on sections are still there
    assert "Assessment attempts" in body
    assert "Python basics" in body


# --- talent notes ---------------------------------------------------------


@pytest.mark.django_db
def test_notes_can_be_saved_from_the_page(
    client, owner, company, application, profile, interviewer
):
    talent = _full_history(company, application, interviewer)
    client.force_login(owner)
    response = client.post(detail_url(profile), {"notes": "Called on Monday."})
    assert response.status_code == 302
    talent.refresh_from_db()
    assert talent.notes == "Called on Monday."


@pytest.mark.django_db
def test_notes_post_is_denied_without_a_talent_profile(client, owner, profile):
    from talent.models import TalentProfile

    TalentProfile.objects.all().delete()
    client.force_login(owner)
    response = client.get(detail_url(profile))
    assert response.context["talent_profile"] is None
    assert response.context["note_form"] is None
    assert client.post(detail_url(profile), {"notes": "x"}).status_code == 403


@pytest.mark.django_db
def test_read_only_interviewer_gets_no_notes_form(
    client, interviewer, company, application, profile
):
    _full_history(company, application, interviewer)
    client.force_login(interviewer)
    response = client.get(detail_url(profile))
    assert response.context["note_form"] is None
    assert client.post(detail_url(profile), {"notes": "x"}).status_code == 403


# --- links in ---------------------------------------------------------------


@pytest.mark.django_db
def test_kanban_card_links_the_candidate_display_name(
    client, owner, application, profile
):
    user = profile.user
    user.first_name, user.last_name = "Asha", "Rao"
    user.save()
    client.force_login(owner)
    body = client.get(
        reverse("web:job_detail", args=[application.job_id])
    ).content.decode()
    assert detail_url(profile) in body
    assert "Asha Rao" in body


@pytest.mark.django_db
def test_kanban_card_falls_back_to_the_email(client, owner, application, profile):
    client.force_login(owner)
    body = client.get(
        reverse("web:job_detail", args=[application.job_id])
    ).content.decode()
    assert profile.user.email in body


@pytest.mark.django_db
def test_interviewer_queue_row_links_the_profile(
    client, interviewer, company, make_job, make_application
):
    from jobs.models import PipelineStage

    job = make_job(company)
    stage = job.stages.filter(kind=PipelineStage.INTERVIEW).first()
    application = make_application(job, "queued@example.test", stage=stage)
    StageReview.objects.create(
        application=application,
        stage=stage,
        reviewer=interviewer,
        decision=StageReview.HOLD,
    )
    client.force_login(interviewer)
    body = client.get(reverse("web:interviewer_queue")).content.decode()
    assert detail_url(application.candidate) in body


@pytest.mark.django_db
def test_talent_profile_detail_links_the_candidate_profile(
    client, owner, company, application, profile, interviewer
):
    talent = _full_history(company, application, interviewer)
    client.force_login(owner)
    body = client.get(
        reverse("talent:profile_detail", args=[talent.pk])
    ).content.decode()
    assert detail_url(profile) in body


@pytest.mark.django_db
def test_membership_roles_are_the_only_way_in(client, company, profile):
    """A user with no membership at all never reaches the page."""
    from core.models import User

    stranger = User.objects.create_user(email="nobody@x.test", password="pw12345678")
    client.force_login(stranger)
    assert client.get(detail_url(profile)).status_code == 403
    assert Membership.objects.filter(user=stranger).count() == 0
