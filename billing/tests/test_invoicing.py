"""GST invoices: FY numbering, CGST/SGST vs IGST split and PDF rendering."""

from datetime import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from billing import invoicing
from billing.models import Invoice
from billing.services import get_subscription

pytestmark = pytest.mark.django_db


def _aware(*args):
    return timezone.make_aware(datetime(*args))


def test_financial_year_label_rolls_over_on_1_april():
    assert invoicing.financial_year(_aware(2026, 3, 31)) == "2025-26"
    assert invoicing.financial_year(_aware(2026, 4, 1)) == "2026-27"
    assert invoicing.financial_year(_aware(2027, 1, 15)) == "2026-27"


def test_numbering_is_sequential_within_a_financial_year(company):
    first = invoicing.create_invoice(
        company, 1000, issued_at=_aware(2026, 4, 2), with_pdf=False
    )
    second = invoicing.create_invoice(
        company, 1000, issued_at=_aware(2026, 6, 2), with_pdf=False
    )
    assert first.number == "IP/2026-27/0001"
    assert second.number == "IP/2026-27/0002"


def test_numbering_restarts_on_1_april(company):
    invoicing.create_invoice(company, 1000, issued_at=_aware(2026, 3, 31), with_pdf=False)
    rollover = invoicing.create_invoice(
        company, 1000, issued_at=_aware(2026, 4, 1), with_pdf=False
    )
    assert Invoice.objects.get(fy="2025-26").number == "IP/2025-26/0001"
    assert rollover.number == "IP/2026-27/0001"
    assert rollover.fy == "2026-27"


def test_intra_state_supply_splits_cgst_and_sgst(company, settings):
    settings.COMPANY_STATE_CODE = "27"
    cgst, sgst, igst = invoicing.gst_split(Decimal("1000.00"), "27")
    assert (cgst, sgst, igst) == (Decimal("90.00"), Decimal("90.00"), Decimal("0.00"))


def test_inter_state_supply_is_igst(company, settings):
    settings.COMPANY_STATE_CODE = "27"
    cgst, sgst, igst = invoicing.gst_split(Decimal("1000.00"), "29")
    assert (cgst, sgst, igst) == (Decimal("0.00"), Decimal("0.00"), Decimal("180.00"))


def test_unknown_customer_state_is_treated_as_inter_state(settings):
    settings.COMPANY_STATE_CODE = "27"
    assert invoicing.gst_split(Decimal("100.00"), "")[2] == Decimal("18.00")


def test_invoice_uses_the_subscription_billing_state(company, settings):
    settings.COMPANY_STATE_CODE = "27"
    subscription = get_subscription(company)
    subscription.gstin = "27AAAAA0000A1Z5"
    subscription.billing_address = {"state_code": "27", "city": "Pune"}
    subscription.save()
    invoice = invoicing.create_invoice(company, Decimal("4999.00"), with_pdf=False)
    assert invoice.is_intra_state is True
    assert invoice.total == Decimal("5898.82")
    assert invoice.gstin == "27AAAAA0000A1Z5"
    assert invoice.tax_total == invoice.cgst + invoice.sgst


def test_invoice_pdf_is_rendered_and_downloadable(client, owner, company):
    invoice = invoicing.create_invoice(company, Decimal("1499.00"))
    assert invoice.pdf.name.endswith(".pdf")
    client.force_login(owner)
    response = client.get(reverse("billing:invoice_download", args=[invoice.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


def test_invoices_are_scoped_to_the_company(client, owner, company, db):
    from core.models import Company

    other = Company.objects.create(name="Someone Else Ltd")
    invoice = invoicing.create_invoice(other, 1000, with_pdf=False)
    client.force_login(owner)
    assert client.get(reverse("billing:invoice_download", args=[invoice.pk])).status_code == 404
