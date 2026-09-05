"""Submission rules: free to respond, deduped, self-blocked, masked until reveal."""

import pytest

from exchange import services
from exchange.models import REDACTED, ExchangeSubmission
from exchange.tests.conftest import set_exchange_feature


def test_a_free_plan_can_respond_even_though_it_cannot_publish(
    responder, requirement, candidate, job
):
    assert services.can_publish(responder) is False
    assert services.can_respond(responder) is True
    submission = services.submit_candidate(requirement, responder, candidate)
    assert submission.status == ExchangeSubmission.SUBMITTED


def test_submission_snapshot_captures_the_candidate(responder, requirement, candidate):
    submission = services.submit_candidate(requirement, responder, candidate, note="Strong fit")
    snapshot = submission.candidate_snapshot
    assert snapshot["name"] == "Asha Rao"
    assert snapshot["email"] == "asha.rao@example.test"
    assert snapshot["skills"] == ["Django"]
    assert submission.note == "Strong fit"
    assert submission.talent_profile == candidate


def test_duplicate_email_is_rejected_for_the_same_requirement(
    responder, outsider, requirement, candidate
):
    services.submit_candidate(requirement, responder, candidate)
    with pytest.raises(services.ExchangeError) as excinfo:
        services.submit_candidate(requirement, responder, candidate)
    assert "already been submitted" in str(excinfo.value)
    assert requirement.submissions.count() == 1


def test_duplicate_detection_ignores_case_and_crosses_companies(
    responder, outsider, requirement, candidate
):
    from talent.models import TalentProfile

    services.invite_partner(requirement.company, outsider)
    link = services.PartnerLink.between(requirement.company, outsider)
    services.accept_partner(link, outsider)
    twin = TalentProfile.objects.create(
        company=outsider, email="asha.rao@example.test", name="A. Rao"
    )
    services.submit_candidate(requirement, responder, candidate)
    with pytest.raises(services.ExchangeError):
        services.submit_candidate(requirement, outsider, twin)


def test_the_same_candidate_may_go_to_a_different_requirement(
    responder, requirement, network_requirement, candidate
):
    services.submit_candidate(requirement, responder, candidate)
    second = services.submit_candidate(network_requirement, responder, candidate)
    assert second.pk is not None


def test_self_submission_is_blocked(requester, requirement, requester_owner):
    from talent.models import TalentProfile

    own = TalentProfile.objects.create(
        company=requester, email="inhouse@acme.test", name="In House"
    )
    with pytest.raises(services.ExchangeError) as excinfo:
        services.submit_candidate(requirement, requester, own)
    assert "your own requirement" in str(excinfo.value)


def test_a_non_partner_cannot_submit(outsider, requirement, candidate):
    with pytest.raises(services.ExchangeError):
        services.submit_candidate(requirement, outsider, candidate)


def test_a_closed_requirement_takes_no_submissions(responder, requirement, candidate, requester):
    services.close_requirement(requirement, requester)
    with pytest.raises(services.ExchangeError):
        services.submit_candidate(requirement, responder, candidate)


def test_the_requester_sees_a_masked_snapshot_before_reveal(
    requester, responder, requirement, candidate
):
    submission = services.submit_candidate(requirement, responder, candidate)
    masked = submission.snapshot_for(requester)
    assert masked["name"] == REDACTED
    assert masked["email"] == REDACTED
    assert masked["phone"] == REDACTED
    # Non-identifying detail still reaches the requester, which is the point.
    assert masked["headline"] == "Senior Django Developer"
    assert submission.snapshot_for(responder)["email"] == "asha.rao@example.test"
    assert submission.reference.startswith("CAND-")


def test_reveal_unmasks_for_the_requester_only(
    requester, responder, outsider, requirement, candidate
):
    submission = services.submit_candidate(requirement, responder, candidate)
    with pytest.raises(services.ExchangeError):
        services.reveal(submission, responder)
    services.reveal(submission, requester)
    submission.refresh_from_db()
    assert submission.revealed_at is not None
    assert submission.snapshot_for(requester)["email"] == "asha.rao@example.test"
    assert submission.snapshot_for(outsider)["email"] == REDACTED
    assert submission.snapshot_for(None)["phone"] == REDACTED


def test_shortlist_and_reject_are_requester_only(requester, responder, requirement, candidate):
    submission = services.submit_candidate(requirement, responder, candidate)
    with pytest.raises(services.ExchangeError):
        services.shortlist(submission, responder)
    services.shortlist(submission, requester)
    submission.refresh_from_db()
    assert submission.status == ExchangeSubmission.SHORTLISTED
    services.reject(submission, requester, reason="Budget")
    submission.refresh_from_db()
    assert submission.status == ExchangeSubmission.REJECTED
    assert "Budget" in submission.note


def test_status_cannot_be_forced_to_hired(requester, responder, requirement, candidate):
    submission = services.submit_candidate(requirement, responder, candidate)
    with pytest.raises(services.ExchangeError):
        services.set_status(submission, requester, ExchangeSubmission.HIRED)
    with pytest.raises(services.ExchangeError):
        services.set_status(submission, requester, "NONSENSE")


def test_a_candidate_profile_can_be_submitted_too(responder, requirement, db):
    from core.models import User
    from jobs.models import CandidateProfile

    user = User.objects.create_user(
        email="dev@example.test", password="pw12345678", first_name="Dev", last_name="Patel"
    )
    profile = CandidateProfile.objects.create(user=user, phone="+91 12345 67890")
    submission = services.submit_candidate(requirement, responder, profile)
    assert submission.candidate_profile == profile
    assert submission.candidate_snapshot["name"] == "Dev Patel"
    assert submission.candidate_snapshot["email"] == "dev@example.test"


def test_outbox_and_inbox_are_scoped(requester, responder, outsider, requirement, candidate):
    submission = services.submit_candidate(requirement, responder, candidate)
    assert list(services.my_submissions(responder)) == [submission]
    assert list(services.my_submissions(outsider)) == []
    assert list(services.submissions_for_requirement(requirement, requester)) == [submission]
    with pytest.raises(services.ExchangeError):
        services.submissions_for_requirement(requirement, outsider)


def test_publishing_stays_gated_even_for_a_busy_responder(responder, job):
    set_exchange_feature(responder, False)
    assert services.can_publish(responder) is False
