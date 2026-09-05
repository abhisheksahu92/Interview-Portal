"""Exchange notifications fall back to plain email while the registry lacks the events."""

import pytest
from django.core import mail

from exchange import services

pytestmark = pytest.mark.django_db


@pytest.fixture
def submission(responder, requirement, candidate, requester_owner, responder_owner):
    mail.outbox.clear()
    return services.submit_candidate(requirement, responder, candidate)


def test_the_requester_is_told_about_a_new_submission_without_the_contact_details(
    submission, requester_owner
):
    assert [m.to for m in mail.outbox] == [["owner@acme.test"]]
    body = mail.outbox[0].body
    assert submission.reference in body
    assert "asha.rao@example.test" not in body
    assert "Asha Rao" not in body


def test_shortlist_reveal_and_hire_notify_the_partner(
    submission, requester, responder_owner
):
    mail.outbox.clear()
    services.shortlist(submission, requester)
    services.reveal(submission, requester)
    services.mark_hired(submission, 200000, company=requester)

    recipients = [m.to[0] for m in mail.outbox]
    assert recipients == ["owner@globex.test"] * 3
    assert "88000" in mail.outbox[-1].body


def test_a_partner_invite_emails_the_target_company(requester, outsider, outsider_owner):
    mail.outbox.clear()

    services.invite_partner(requester, outsider)

    assert mail.outbox[0].to == ["owner@initech.test"]
    assert "Acme Staffing" in mail.outbox[0].body


def test_a_dispute_notifies_the_other_side(submission, requester, responder, responder_owner, requester_owner):
    deal = services.mark_hired(submission, 100000, company=requester)
    mail.outbox.clear()

    services.flag_dispute(deal, responder, "Candidate never joined")

    assert mail.outbox[0].to == ["owner@acme.test"]
    assert "never joined" in mail.outbox[0].body
