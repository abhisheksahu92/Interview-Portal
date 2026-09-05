"""PartnerLink state machine: invite → accept → block, and the pair uniqueness."""

import pytest
from django.db.utils import IntegrityError

from exchange import services
from exchange.models import PartnerLink


def test_invite_creates_a_pending_link(requester, responder, requester_owner):
    link = services.invite_partner(requester, responder, created_by=requester_owner)
    assert link.status == PartnerLink.PENDING
    assert link.is_incoming_for(responder) is True
    assert link.is_incoming_for(requester) is False


def test_invite_by_slug_and_by_owner_email(requester, responder, responder_owner):
    assert services.find_company(responder.slug) == responder
    assert services.find_company("owner@globex.test") == responder
    link = services.invite_partner(requester, responder.slug)
    assert link.to_company == responder


def test_invite_unknown_target_is_refused(requester):
    with pytest.raises(services.ExchangeError):
        services.invite_partner(requester, "nobody@nowhere.test")


def test_cannot_partner_with_yourself(requester):
    with pytest.raises(services.ExchangeError):
        services.invite_partner(requester, requester)


def test_only_the_invited_company_can_accept(requester, responder, outsider):
    link = services.invite_partner(requester, responder)
    with pytest.raises(services.ExchangeError):
        services.accept_partner(link, requester)
    with pytest.raises(services.ExchangeError):
        services.accept_partner(link, outsider)
    assert services.accept_partner(link, responder).status == PartnerLink.ACTIVE


def test_accept_makes_the_link_mutual(requester, responder, partnership):
    assert PartnerLink.are_partners(requester, responder)
    assert PartnerLink.are_partners(responder, requester)
    assert PartnerLink.active_partner_ids(requester) == {responder.pk}
    assert PartnerLink.active_partner_ids(responder) == {requester.pk}


def test_duplicate_invite_is_refused_in_either_direction(requester, responder):
    services.invite_partner(requester, responder)
    with pytest.raises(services.ExchangeError):
        services.invite_partner(requester, responder)
    # The reverse invite is read as an acceptance of the pending request.
    link = services.invite_partner(responder, requester)
    assert link.status == PartnerLink.ACTIVE


def test_the_unique_pair_constraint_holds_at_the_database(requester, responder):
    PartnerLink.objects.create(from_company=requester, to_company=responder)
    with pytest.raises(IntegrityError):
        PartnerLink.objects.create(from_company=requester, to_company=responder)


def test_either_side_can_block_and_a_third_party_cannot(requester, responder, outsider, partnership):
    with pytest.raises(services.ExchangeError):
        services.block_partner(partnership, outsider)
    services.block_partner(partnership, responder)
    partnership.refresh_from_db()
    assert partnership.status == PartnerLink.BLOCKED
    assert not PartnerLink.are_partners(requester, responder)


def test_blocked_partnership_cannot_be_invited_or_accepted_again(requester, outsider, blocked_link):
    with pytest.raises(services.ExchangeError):
        services.invite_partner(requester, outsider)
    with pytest.raises(services.ExchangeError):
        services.accept_partner(blocked_link, outsider)
    services.unblock_partner(blocked_link, requester)
    blocked_link.refresh_from_db()
    assert blocked_link.status == PartnerLink.PENDING
