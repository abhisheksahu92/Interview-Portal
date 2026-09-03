from decimal import Decimal

import pytest

from core.models import Company
from partners.models import CommissionLedger, Referral, Reseller
from partners.services import record_commission, reseller_totals


@pytest.fixture
def referred(db):
    reseller = Reseller.objects.create(name="P", code="p", commission_pct=Decimal("20"))
    company = Company.objects.create(name="Referred Co")
    Referral.objects.create(reseller=reseller, company=company)
    return reseller, company


def test_record_commission_applies_pct_and_sets_first_payment(referred):
    reseller, company = referred
    entry = record_commission(company, Decimal("5000"), "IP/2026-27/0001")
    assert entry.commission_inr == Decimal("1000.00")
    assert Referral.objects.get(company=company).first_payment_at is not None


def test_record_commission_is_idempotent_per_invoice(referred):
    reseller, company = referred
    record_commission(company, 5000, "IP/2026-27/0001")
    record_commission(company, 5000, "IP/2026-27/0001")
    assert CommissionLedger.objects.filter(reseller=reseller).count() == 1


def test_record_commission_skips_unreferred_company(db):
    company = Company.objects.create(name="Direct Co")
    assert record_commission(company, 1000, "IP/1") is None


def test_record_commission_skips_inactive_reseller(referred):
    reseller, company = referred
    reseller.active = False
    reseller.save()
    assert record_commission(company, 1000, "IP/1") is None


def test_reseller_totals_split_paid_and_pending(referred):
    from django.utils import timezone

    reseller, company = referred
    record_commission(company, 1000, "IP/1")
    entry = record_commission(company, 2000, "IP/2")
    entry.paid_out_at = timezone.now()
    entry.save()
    totals = reseller_totals(reseller)
    assert totals["earned"] == Decimal("600.00")
    assert totals["paid"] == Decimal("400.00")
    assert totals["pending"] == Decimal("200.00")


def test_compute_commissions_command_without_invoice_model(db, capsys):
    """The command must degrade cleanly while billing.Invoice does not exist."""
    from django.core.management import call_command

    from partners.management.commands import compute_commissions

    monkey = compute_commissions._invoice_model
    compute_commissions._invoice_model = lambda: None
    try:
        call_command("compute_commissions")
    finally:
        compute_commissions._invoice_model = monkey
    assert "not available" in capsys.readouterr().out
