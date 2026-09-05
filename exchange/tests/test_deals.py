"""Deal money: split, platform fee, the billing hook and disputes."""

import sys
import types
from decimal import Decimal

import pytest

from exchange import services
from exchange.models import ExchangeDeal, ExchangeRequirement, ExchangeSubmission


@pytest.fixture
def submission(responder, requirement, candidate):
    return services.submit_candidate(requirement, responder, candidate)


@pytest.fixture
def fake_ledger(monkeypatch):
    """Stand in for ``billing.ledger`` (owned by the billing agent)."""
    charges = []

    def add_charge(company, kind, label, amount_inr, ref, occurred_at=None):
        charges.append(
            {
                "company": company,
                "kind": kind,
                "label": label,
                "amount": Decimal(amount_inr),
                "ref": ref,
            }
        )
        return charges[-1]

    module = types.ModuleType("billing.ledger")
    module.add_charge = add_charge
    monkeypatch.setitem(sys.modules, "billing.ledger", module)
    return charges


def test_deal_math_is_exact(requester, submission):
    deal = services.mark_hired(submission, 200000, company=requester)
    assert deal.placement_fee_inr == Decimal("200000")
    assert deal.split_pct == 50
    assert deal.platform_fee_pct == 12
    assert deal.responder_gross == Decimal("100000.00")
    assert deal.requester_gross == Decimal("100000.00")
    assert deal.responder_platform_fee == Decimal("12000.00")
    assert deal.requester_platform_fee == Decimal("12000.00")
    assert deal.platform_fee == Decimal("24000.00")
    assert deal.responder_share == Decimal("88000.00")
    assert deal.requester_share == Decimal("88000.00")
    # Nothing is created or lost: shares plus platform fee equal the fee.
    assert deal.responder_share + deal.requester_share + deal.platform_fee == Decimal("200000.00")


def test_an_uneven_split_favours_the_responder(requester, submission):
    submission.requirement.fee_split_pct = 70
    submission.requirement.save(update_fields=["fee_split_pct"])
    deal = services.mark_hired(submission, 100000, company=requester)
    assert deal.responder_gross == Decimal("70000.00")
    assert deal.responder_share == Decimal("61600.00")
    assert deal.requester_share == Decimal("26400.00")
    assert deal.platform_fee == Decimal("12000.00")


def test_share_lookup_by_company(requester, responder, outsider, submission):
    deal = services.mark_hired(submission, 200000, company=requester)
    assert deal.share_for(responder) == Decimal("88000.00")
    assert deal.share_for(requester) == Decimal("88000.00")
    assert deal.share_for(outsider) is None
    assert deal.platform_fee_for(outsider) is None


def test_hiring_marks_the_submission_and_fills_the_requirement(requester, submission):
    deal = services.mark_hired(submission, 150000, company=requester)
    submission.refresh_from_db()
    assert submission.status == ExchangeSubmission.HIRED
    assert submission.revealed_at is not None
    deal.submission.requirement.refresh_from_db()
    assert deal.submission.requirement.status == ExchangeRequirement.FILLED


def test_a_zero_fee_and_a_second_deal_are_refused(requester, submission):
    with pytest.raises(services.ExchangeError):
        services.mark_hired(submission, 0, company=requester)
    services.mark_hired(submission, 100000, company=requester)
    submission.refresh_from_db()
    with pytest.raises(services.ExchangeError):
        services.mark_hired(submission, 100000, company=requester)


def test_only_the_requester_can_record_a_placement(responder, submission):
    with pytest.raises(services.ExchangeError):
        services.mark_hired(submission, 100000, company=responder)


def test_the_platform_fee_is_charged_to_both_companies(
    requester, responder, submission, fake_ledger
):
    deal = services.mark_hired(submission, 200000, company=requester)
    assert len(fake_ledger) == 2
    assert {c["company"] for c in fake_ledger} == {requester, responder}
    assert {c["kind"] for c in fake_ledger} == {"EXCHANGE_FEE"}
    assert {c["amount"] for c in fake_ledger} == {Decimal("12000.00")}
    assert sorted(c["ref"] for c in fake_ledger) == [
        f"exchange-deal-{deal.pk}-requester",
        f"exchange-deal-{deal.pk}-responder",
    ]
    deal.refresh_from_db()
    assert deal.status == ExchangeDeal.INVOICED
    assert deal.charged_at is not None


def test_a_missing_billing_ledger_never_blocks_the_deal(requester, submission, monkeypatch):
    monkeypatch.setitem(sys.modules, "billing.ledger", None)
    deal = services.mark_hired(submission, 200000, company=requester)
    assert deal.pk is not None
    assert deal.status == ExchangeDeal.PENDING
    assert deal.charged_at is None


def test_a_failing_ledger_is_logged_and_swallowed(requester, submission, monkeypatch):
    module = types.ModuleType("billing.ledger")

    def boom(*args, **kwargs):
        raise RuntimeError("ledger down")

    module.add_charge = boom
    monkeypatch.setitem(sys.modules, "billing.ledger", module)
    deal = services.mark_hired(submission, 200000, company=requester)
    assert deal.status == ExchangeDeal.PENDING


def test_either_party_can_dispute_and_a_stranger_cannot(
    requester, responder, outsider, submission
):
    deal = services.mark_hired(submission, 200000, company=requester)
    with pytest.raises(services.ExchangeError):
        services.flag_dispute(deal, outsider, "not mine")
    with pytest.raises(services.ExchangeError):
        services.flag_dispute(deal, responder, "   ")
    services.flag_dispute(deal, responder, "Candidate never joined")
    deal.refresh_from_db()
    assert deal.disputed is True
    assert deal.dispute_reason == "Candidate never joined"
    assert deal.disputed_at is not None


def test_deals_are_visible_to_both_parties_only(requester, responder, outsider, submission):
    deal = services.mark_hired(submission, 200000, company=requester)
    assert list(services.deals_for(requester)) == [deal]
    assert list(services.deals_for(responder)) == [deal]
    assert list(services.deals_for(outsider)) == []
    assert list(services.deals_for(None)) == []
