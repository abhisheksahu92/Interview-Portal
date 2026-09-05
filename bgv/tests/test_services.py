"""The money rules: consent gates the charge, and the charge happens once."""

from decimal import Decimal

import pytest
from django.utils import timezone

from bgv import services
from bgv.models import CheckPackage, VerificationOrder
from billing.models import BillingCharge

pytestmark = pytest.mark.django_db


def _order(company, candidate, package, application=None, owner=None):
    return services.create_order(
        company, candidate, package, application=application, ordered_by=owner
    )


def test_order_starts_pending_consent_and_bills_nothing(company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    assert order.status == VerificationOrder.CONSENT_PENDING
    assert order.charge_ref == ""
    assert not BillingCharge.objects.filter(company=company).exists()


def test_order_snapshots_price_and_cost(company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    package.price_inr = Decimal("9999.00")
    package.provider_cost_inr = Decimal("8888.00")
    package.save()
    order.refresh_from_db()
    assert order.price_inr == Decimal("1499.00")
    assert order.provider_cost_inr == Decimal("999.00")


def test_consent_charges_the_company_once(company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    services.record_consent(order, name="Priya Sharma", ip="203.0.113.9")
    charges = BillingCharge.objects.filter(company=company, kind=BillingCharge.BGV)
    assert charges.count() == 1
    charge = charges.get()
    assert charge.amount_inr == Decimal("1499.00")
    assert charge.ref == f"bgv:{order.pk}"


def test_charging_is_idempotent(company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    services.record_consent(order, name="Priya Sharma")
    services.charge_order(order)
    services.record_consent(order, name="Priya Sharma")
    assert BillingCharge.objects.filter(company=company, kind=BillingCharge.BGV).count() == 1


def test_consent_records_who_when_and_from_where(company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    before = timezone.now()
    services.record_consent(order, name="  Priya Sharma  ", ip="198.51.100.4")
    order.refresh_from_db()
    assert order.consent_name == "Priya Sharma"
    assert order.consent_ip == "198.51.100.4"
    assert order.consent_given_at >= before
    assert order.status == VerificationOrder.SUBMITTED


def test_cancel_before_consent_never_charges(company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    assert services.cancel_order(order) is True
    order.refresh_from_db()
    assert order.status == VerificationOrder.CANCELLED
    assert not BillingCharge.objects.filter(company=company).exists()


def test_cancel_after_consent_is_refused(company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    services.record_consent(order, name="Priya Sharma")
    assert services.cancel_order(order) is False
    order.refresh_from_db()
    assert order.status != VerificationOrder.CANCELLED


def test_mock_provider_completes_over_two_polls(company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    services.record_consent(order, name="Priya Sharma")
    assert order.provider_ref.startswith("MOCK-")
    services.poll_order(order)
    assert order.status == VerificationOrder.IN_PROGRESS
    services.poll_order(order)
    assert order.status == VerificationOrder.COMPLETED
    assert order.completed_at is not None
    assert all(row["status"] == VerificationOrder.CLEAR for row in order.result_rows)


def test_completion_generates_a_pdf_report(company, candidate, package, owner):
    order = _order(company, candidate, package, owner=owner)
    services.record_consent(order, name="Priya Sharma")
    services.poll_order(order)
    services.poll_order(order)
    order.refresh_from_db()
    assert order.report_file
    order.report_file.open("rb")
    assert order.report_file.read(4) == b"%PDF"


def test_margin_math_uses_only_charged_orders(company, candidate, package, owner, make_candidate):
    charged = _order(company, candidate, package, owner=owner)
    services.record_consent(charged, name="Priya Sharma")
    cancelled = _order(company, make_candidate("b@example.test"), package, owner=owner)
    services.cancel_order(cancelled)
    summary = services.margin_summary(company)
    assert summary["count"] == 1
    assert summary["revenue"] == Decimal("1499.00")
    assert summary["cost"] == Decimal("999.00")
    assert summary["margin"] == Decimal("500.00")
    assert summary["margin_percent"] == Decimal("33.36")


def test_margin_is_zero_safe_with_no_orders(company):
    summary = services.margin_summary(company)
    assert summary == {
        "count": 0,
        "revenue": Decimal("0.00"),
        "cost": Decimal("0.00"),
        "margin": Decimal("0.00"),
        "margin_percent": Decimal("0.00"),
    }


def test_seeded_packages_carry_the_pinned_prices(db):
    prices = dict(CheckPackage.objects.values_list("code", "price_inr"))
    costs = dict(CheckPackage.objects.values_list("code", "provider_cost_inr"))
    assert prices["BASIC"] == Decimal("799.00") and costs["BASIC"] == Decimal("499.00")
    assert prices["STANDARD"] == Decimal("1499.00") and costs["STANDARD"] == Decimal("999.00")
    assert prices["COMPREHENSIVE"] == Decimal("2999.00")
    assert costs["COMPREHENSIVE"] == Decimal("1999.00")
