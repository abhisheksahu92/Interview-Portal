from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse

from assessments.models import Assessment, Attempt, Question
from core.models import User
from jobs.models import Application, CandidateProfile, Job, Skill
from marketplace.pool import card_for, search


def make_candidate(company, email, *, share=True, passed=True, headline="Senior Python dev"):
    """A candidate with an application and (optionally) a passed attempt."""
    user = User.objects.create_user(email=email, password="pw12345678", is_candidate=True)
    profile = CandidateProfile.objects.create(
        user=user,
        phone="+911234567890",
        headline=headline,
        experience_years=Decimal("6.0"),
        share_in_pool=share,
    )
    skill = Skill.objects.get_or_create(company=company, name="Python")[0]
    profile.skills.add(skill)
    job = Job.objects.create(company=company, title="Backend engineer", status=Job.OPEN)
    application = Application.objects.create(job=job, candidate=profile)
    assessment = Assessment.objects.create(job=job, title="Screen")
    assessment.questions.add(
        Question.objects.create(company=company, kind=Question.MCQ, text="Q", options=["a", "b"], correct_option=0)
    )
    Attempt.objects.create(
        assessment=assessment,
        application=application,
        answers={},
        score_percent=Decimal("82.00"),
        passed=passed,
    )
    return profile


@pytest.fixture
def pooled(company):
    return make_candidate(company, "pooled@cand.test")


def test_search_returns_opted_in_passed_candidates(pooled):
    cards = search()
    assert [c.profile_id for c in cards] == [pooled.pk]
    assert cards[0].best_score == Decimal("82.00")


def test_search_excludes_opted_out_candidates(company):
    make_candidate(company, "private@cand.test", share=False)
    assert search() == []


def test_search_excludes_candidates_without_a_passed_attempt(company):
    make_candidate(company, "failed@cand.test", passed=False)
    assert search() == []


def test_cards_are_anonymised(pooled):
    card = card_for(pooled)
    payload = repr(card)
    assert pooled.user.email not in payload and pooled.phone not in payload
    assert card.reference == f"CAND-{pooled.pk:05d}"
    assert not hasattr(card, "email")


def test_search_filters_by_skill_and_experience(pooled):
    assert search(skill="python") and search(skill="cobol") == []
    assert search(min_experience=3) and search(min_experience=20) == []
    assert search(query="Senior") and search(query="Zebra") == []


def test_pool_is_cross_company(company, other_company, pooled):
    """A candidate verified at one company is discoverable by another."""
    from marketplace.pool import verified_pool_queryset

    assert verified_pool_queryset().filter(pk=pooled.pk).exists()


def test_pool_view_requires_the_talent_pool_feature(client, owner, expired_trial, pooled):
    client.force_login(owner)
    assert client.get(reverse("marketplace:pool")).status_code == 403


def test_pool_view_lists_anonymised_cards_on_pro(client, owner, pro, pooled):
    client.force_login(owner)
    response = client.get(reverse("marketplace:pool"))
    assert response.status_code == 200
    assert f"CAND-{pooled.pk:05d}".encode() in response.content
    assert pooled.user.email.encode() not in response.content


def test_invite_falls_back_to_email(client, owner, pro, pooled):
    client.force_login(owner)
    mail.outbox.clear()
    response = client.post(
        reverse("marketplace:pool_invite", args=[pooled.pk]), follow=True
    )
    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [pooled.user.email]


def test_invite_requires_the_feature(client, owner, expired_trial, pooled):
    client.force_login(owner)
    assert client.post(reverse("marketplace:pool_invite", args=[pooled.pk])).status_code == 403


def test_opt_in_toggle_flips_the_flag(client, company):
    profile = make_candidate(company, "toggle@cand.test", share=False)
    client.force_login(profile.user)
    client.post(reverse("marketplace:pool_opt_in"), {"share_in_pool": "1"})
    profile.refresh_from_db()
    assert profile.share_in_pool is True

    client.post(reverse("marketplace:pool_opt_in"), {"share_in_pool": "0"})
    profile.refresh_from_db()
    assert profile.share_in_pool is False


def test_opt_in_rejects_non_candidates(client, owner):
    client.force_login(owner)
    assert client.post(reverse("marketplace:pool_opt_in"), {"share_in_pool": "1"}).status_code == 403
