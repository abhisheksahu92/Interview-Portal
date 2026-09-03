"""``manage.py seed_demo`` — the Phase 3 artefacts it now seeds, and that a
second run tops up rather than duplicating.
"""

import pytest
from django.core.management import call_command

from billing.models import Plan, Subscription
from core.models import Company

COMPANY = "Demo Staffing"


@pytest.fixture
def seeded(db):
    call_command("seed_demo", verbosity=0)
    return Company.objects.get(name=COMPANY)


@pytest.mark.django_db
def test_demo_company_is_on_a_paid_agency_plan_not_a_trial(seeded):
    subscription = Subscription.objects.get(company=seeded)
    assert subscription.plan.code == Plan.AGENCY
    assert subscription.status == Subscription.ACTIVE
    assert subscription.trial_ends_at is None
    assert not subscription.in_trial


@pytest.mark.django_db
def test_every_paid_feature_is_entitled(seeded):
    from billing.entitlements import FEATURES, has_feature

    missing = [name for name in FEATURES if not has_feature(seeded, name)]
    assert missing == []


@pytest.mark.django_db
def test_seeds_a_client_with_a_live_portal_link_and_one_submission(seeded):
    from clients.models import Client, Submission

    client = Client.objects.get(company=seeded)
    access = client.accesses.get()
    assert access.is_active
    submission = Submission.objects.get(client=client)
    assert submission.application.job.company_id == seeded.pk


@pytest.mark.django_db
def test_seeds_weekday_availability_for_the_interviewer(seeded):
    from datetime import time

    from scheduling.models import InterviewerAvailability

    windows = InterviewerAvailability.objects.filter(
        company=seeded, user__email="interviewer@demo.test"
    )
    assert windows.count() == 5
    assert sorted(windows.values_list("weekday", flat=True)) == [0, 1, 2, 3, 4]
    for window in windows:
        assert (window.start, window.end) == (time(10, 0), time(17, 0))
        assert window.timezone == "Asia/Kolkata"


@pytest.mark.django_db
def test_seeds_one_confirmed_interview_on_the_l2_stage(seeded):
    from scheduling.models import Interview

    interview = Interview.objects.get(company=seeded)
    assert interview.status == Interview.CONFIRMED
    assert interview.stage is not None
    assert interview.stage.name.startswith("L2")
    assert interview.application.current_stage_id == interview.stage_id
    assert interview.booking_token
    assert interview.interviewers.count() == 1


@pytest.mark.django_db
def test_seeds_three_talent_profiles(seeded):
    from talent.models import TalentProfile

    # Applications also auto-source talent profiles, so look for the three
    # explicitly seeded sourced ones.
    profiles = TalentProfile.objects.filter(
        company=seeded, email__endswith="@talent.test"
    )
    assert profiles.count() == 3
    assert all(profile.skills.exists() for profile in profiles)
    assert all(profile.name and profile.headline for profile in profiles)


@pytest.mark.django_db
def test_seeds_a_template_and_an_offer_out_for_signature(seeded):
    from offers.models import Offer, OfferTemplate

    assert OfferTemplate.objects.filter(company=seeded).exists()
    offer = Offer.objects.get(application__job__company=seeded)
    assert offer.status == Offer.SENT
    assert offer.sent_at is not None
    assert offer.sign_token
    assert offer.body_rendered


@pytest.mark.django_db
def test_seeds_a_published_careers_site(seeded):
    from careers.models import CareersSite

    site = CareersSite.objects.get(company=seeded)
    assert site.published
    assert site.slug == seeded.slug


@pytest.mark.django_db
def test_seeds_an_active_video_screen_on_the_second_jobs_screening_stage(seeded):
    from jobs.models import PipelineStage
    from video.models import VideoQuestion, VideoScreen

    assert VideoQuestion.objects.filter(company=seeded).count() == 1
    screen = VideoScreen.objects.get(job__company=seeded)
    assert screen.is_active
    assert screen.stage.kind == PipelineStage.SCREENING
    assert screen.job.title.startswith("Frontend")
    assert screen.questions.count() == 1


@pytest.mark.django_db
def test_every_application_has_analytics_history(seeded):
    from analytics.models import StageTransition
    from jobs.models import Application

    for application in Application.objects.filter(job__company=seeded):
        assert StageTransition.objects.filter(application=application).exists()


@pytest.mark.django_db
def test_prints_the_three_shareable_tokens(seeded, capsys):
    from io import StringIO

    out = StringIO()
    call_command("seed_demo", stdout=out)
    printed = out.getvalue()
    assert "/clients/portal/" in printed
    assert "/scheduling/book/" in printed
    assert "/offers/sign/" in printed


@pytest.mark.django_db
def test_a_second_run_tops_up_instead_of_duplicating(seeded):
    from careers.models import CareersSite
    from clients.models import Client, ClientAccess, Submission
    from offers.models import Offer
    from scheduling.models import Interview, InterviewerAvailability
    from talent.models import TalentProfile
    from video.models import VideoScreen

    counts = {
        model: model.objects.count()
        for model in (
            Client,
            ClientAccess,
            Submission,
            InterviewerAvailability,
            Interview,
            TalentProfile,
            Offer,
            CareersSite,
            VideoScreen,
        )
    }
    call_command("seed_demo", verbosity=0)
    assert {model: model.objects.count() for model in counts} == counts
