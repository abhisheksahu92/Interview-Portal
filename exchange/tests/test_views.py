"""View-level tests, most of them anti-leak: what must never reach the HTML."""

import pytest
from django.urls import reverse

from exchange import services
from exchange.models import ExchangeDeal, ExchangeRequirement, ExchangeSubmission, PartnerLink
from exchange.tests.conftest import set_exchange_feature

pytestmark = pytest.mark.django_db


@pytest.fixture
def submission(responder, requirement, candidate):
    return services.submit_candidate(requirement, responder, candidate)


def test_feed_lists_partner_requirements(client, responder_owner, requirement):
    client.force_login(responder_owner)

    response = client.get(reverse("exchange:index"))

    assert response.status_code == 200
    assert b"Senior Django Engineer" in response.content


def test_feed_hides_your_own_requirement(client, requester_owner, requirement):
    client.force_login(requester_owner)

    response = client.get(reverse("exchange:index"))

    assert b"Senior Django Engineer" not in response.content


def test_feed_masks_the_client_name_on_a_network_requirement(
    client, responder_owner, network_requirement
):
    client.force_login(responder_owner)

    response = client.get(reverse("exchange:index"))

    assert b"Big Bank Ltd" not in response.content
    assert b"Confidential client" in response.content


def test_contact_details_never_reach_the_inbox_html_before_reveal(
    client, requester_owner, submission
):
    client.force_login(requester_owner)

    response = client.get(
        reverse("exchange:requirement_detail", args=[submission.requirement_id])
    )

    body = response.content
    assert b"Asha Rao" not in body
    assert b"asha.rao@example.test" not in body
    assert b"98765 43210" not in body
    assert submission.reference.encode() in body
    # The useful, non-identifying part still shows.
    assert b"Senior Django Developer" in body


def test_reveal_puts_the_contact_details_in_the_html(client, requester_owner, submission):
    client.force_login(requester_owner)

    client.post(reverse("exchange:submission_reveal", args=[submission.pk]))
    response = client.get(
        reverse("exchange:requirement_detail", args=[submission.requirement_id])
    )

    submission.refresh_from_db()
    assert submission.revealed_at is not None
    assert b"Asha Rao" in response.content
    assert b"asha.rao@example.test" in response.content


def test_a_company_cannot_open_another_companys_requirement_inbox(
    client, responder_owner, outsider_owner, submission
):
    for user in (responder_owner, outsider_owner):
        client.force_login(user)
        response = client.get(
            reverse("exchange:requirement_detail", args=[submission.requirement_id])
        )
        assert response.status_code == 404


def test_a_stranger_cannot_reveal_or_shortlist_someone_elses_submission(
    client, outsider_owner, responder_owner, submission
):
    for user in (outsider_owner, responder_owner):
        client.force_login(user)
        assert client.post(
            reverse("exchange:submission_reveal", args=[submission.pk])
        ).status_code == 404
        assert client.post(
            reverse("exchange:submission_shortlist", args=[submission.pk])
        ).status_code == 404
    submission.refresh_from_db()
    assert submission.revealed_at is None


def test_publish_is_gated_for_a_free_plan_but_the_feed_is_not(client, responder_owner, responder):
    client.force_login(responder_owner)

    locked = client.get(reverse("exchange:publish"))

    assert locked.status_code == 403
    assert b"Not included in your plan" in locked.content  # plan-aware 403, not a role error
    assert client.get(reverse("exchange:index")).status_code == 200


def test_publish_creates_a_requirement_for_a_paid_plan(client, requester_owner, job):
    client.force_login(requester_owner)

    response = client.post(
        reverse("exchange:publish"),
        {
            "job": job.pk,
            "client_name": "Big Bank Ltd",
            "fee_split_pct": 60,
            "visibility": ExchangeRequirement.PARTNERS,
            "expires_in_days": 21,
        },
    )

    requirement = ExchangeRequirement.objects.get()
    assert response.status_code == 302
    assert requirement.fee_split_pct == 60
    assert requirement.client_name == "Big Bank Ltd"


def test_submitting_through_the_view_masks_and_dedupes(
    client, responder_owner, requirement, candidate
):
    client.force_login(responder_owner)
    url = reverse("exchange:submit", args=[requirement.pk])

    first = client.post(url, {"talent_profile": candidate.pk, "note": "Great fit"}, follow=True)
    second = client.post(url, {"talent_profile": candidate.pk}, follow=True)

    assert ExchangeSubmission.objects.count() == 1
    assert b"CAND-" in first.content
    assert b"already been submitted" in second.content


def test_a_non_partner_cannot_open_the_submit_page(client, outsider_owner, requirement):
    client.force_login(outsider_owner)

    response = client.get(reverse("exchange:submit", args=[requirement.pk]))

    assert response.status_code == 403


def test_the_outbox_shows_your_own_candidate_and_not_a_partners(
    client, responder_owner, outsider_owner, submission
):
    client.force_login(responder_owner)
    mine = client.get(reverse("exchange:submissions"))
    client.force_login(outsider_owner)
    theirs = client.get(reverse("exchange:submissions"))

    assert b"Asha Rao" in mine.content
    assert b"Asha Rao" not in theirs.content


def test_partners_page_invites_by_slug(client, requester_owner, responder):
    client.force_login(requester_owner)

    client.post(reverse("exchange:partners"), {"target": responder.slug}, follow=True)

    link = PartnerLink.between(requester_owner.memberships.first().company, responder)
    assert link is not None and link.status == PartnerLink.PENDING


def test_partners_page_accepts_and_blocks(client, responder_owner, requester_owner, requester, responder):
    link = services.invite_partner(requester, responder, created_by=requester_owner)
    client.force_login(responder_owner)

    client.post(reverse("exchange:partner_accept", args=[link.pk]))
    link.refresh_from_db()
    assert link.status == PartnerLink.ACTIVE

    client.post(reverse("exchange:partner_block", args=[link.pk]))
    link.refresh_from_db()
    assert link.status == PartnerLink.BLOCKED


def test_an_uninvolved_company_cannot_touch_a_partner_link(client, outsider_owner, partnership):
    client.force_login(outsider_owner)

    response = client.post(reverse("exchange:partner_accept", args=[partnership.pk]))

    assert response.status_code == 404


def test_hire_records_a_deal_and_the_ledger_shows_both_shares(
    client, requester_owner, responder_owner, submission
):
    client.force_login(requester_owner)
    # A placement can only be recorded once the candidate has been revealed.
    client.post(reverse("exchange:submission_reveal", args=[submission.pk]))
    client.post(
        reverse("exchange:submission_hire", args=[submission.pk]),
        {"placement_fee_inr": "200000"},
    )

    deal = ExchangeDeal.objects.get()
    assert deal.responder_share == 88000
    for user in (requester_owner, responder_owner):
        client.force_login(user)
        response = client.get(reverse("exchange:deals"))
        assert response.status_code == 200
        assert b"88,000" in response.content  # Indian-grouped via the inr filter


def test_deals_of_other_companies_are_invisible(client, outsider_owner, requester, submission):
    services.mark_hired(submission, 200000, company=requester)
    client.force_login(outsider_owner)

    response = client.get(reverse("exchange:deals"))

    assert b"Senior Django Engineer" not in response.content


def test_an_interviewer_cannot_reach_the_exchange(client, requester, requirement):
    from core.models import Membership, User

    user = User.objects.create_user(email="int@acme.test", password="pw12345678")
    Membership.objects.create(user=user, company=requester, role=Membership.INTERVIEWER)
    client.force_login(user)

    assert client.get(reverse("exchange:index")).status_code == 403
    assert client.get(reverse("exchange:requirements")).status_code == 403


def test_dispute_from_the_deals_page(client, responder_owner, requester, submission):
    services.mark_hired(submission, 200000, company=requester)
    deal = ExchangeDeal.objects.get()
    client.force_login(responder_owner)

    client.post(reverse("exchange:deal_dispute", args=[deal.pk]), {"reason": "No-show"})

    deal.refresh_from_db()
    assert deal.disputed is True


def test_requirements_page_lists_counts_and_closes(client, requester_owner, submission):
    client.force_login(requester_owner)
    requirement = submission.requirement

    listing = client.get(reverse("exchange:requirements"))
    client.post(reverse("exchange:requirement_close", args=[requirement.pk]))

    requirement.refresh_from_db()
    assert listing.status_code == 200
    assert requirement.status == ExchangeRequirement.CLOSED


def test_publish_page_renders_for_a_paid_plan(client, requester_owner, requester, job):
    set_exchange_feature(requester, True)
    client.force_login(requester_owner)

    assert client.get(reverse("exchange:publish")).status_code == 200
