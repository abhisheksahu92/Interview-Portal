"""GST invoicing: financial-year numbering, tax split and HTML→PDF rendering."""

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from billing.models import Invoice, InvoiceCounter

logger = logging.getLogger(__name__)

NUMBER_PREFIX = "IP"
TWO = Decimal("0.01")


def financial_year(moment=None):
    """Indian FY label for ``moment`` — 2026-04-01 → ``2026-27``."""
    moment = moment or timezone.now()
    date = getattr(moment, "date", lambda: moment)()
    year = date.year if date.month >= 4 else date.year - 1
    return f"{year}-{(year + 1) % 100:02d}"


def next_number(moment=None, fy=None):
    """Allocate the next invoice number for the FY, e.g. ``IP/2026-27/0001``.

    The FY counter row is locked with ``SELECT ... FOR UPDATE`` inside a
    transaction, so concurrent payments queue up instead of racing for the same
    sequence number (the old "read the highest existing number" scan could hand
    the same number to two writers). SQLite has no row locks but serialises
    writers with a whole-database write lock, which gives the same guarantee —
    ``select_for_update`` is simply a no-op there, so the code path is identical.

    Note this *consumes* a number; use :func:`peek_number` for a read-only look.
    """
    fy = fy or financial_year(moment)
    with transaction.atomic():
        counter = InvoiceCounter.objects.select_for_update().filter(fy=fy).first()
        if counter is None:
            # Another writer may create the row first; create-then-lock.
            InvoiceCounter.objects.get_or_create(fy=fy, defaults={"last_seq": 0})
            counter = InvoiceCounter.objects.select_for_update().get(fy=fy)
        counter.last_seq += 1
        counter.save(update_fields=["last_seq", "updated_at"])
        seq = counter.last_seq
    return f"{NUMBER_PREFIX}/{fy}/{seq:04d}"


def peek_number(moment=None, fy=None):
    """The number :func:`next_number` would hand out next, without taking it."""
    fy = fy or financial_year(moment)
    counter = InvoiceCounter.objects.filter(fy=fy).first()
    seq = (counter.last_seq if counter else 0) + 1
    return f"{NUMBER_PREFIX}/{fy}/{seq:04d}"


def _q(value):
    return Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP)


def gst_split(amount, state_code, rate=Invoice.GST_RATE):
    """Split ``amount`` into (cgst, sgst, igst) for a customer state code.

    Intra-state (customer state == ``settings.COMPANY_STATE_CODE``) is split
    into equal CGST/SGST halves; anything else — including an unknown state —
    is IGST.
    """
    amount = Decimal(amount or 0)
    tax = _q(amount * Decimal(rate) / Decimal(100))
    home = str(getattr(settings, "COMPANY_STATE_CODE", "") or "").strip()
    customer = str(state_code or "").strip()
    if home and customer and customer == home:
        half = _q(tax / 2)
        return half, _q(tax - half), Decimal("0.00")
    return Decimal("0.00"), Decimal("0.00"), tax


def render_pdf(invoice):
    """Render the invoice HTML to a PDF and store it on ``invoice.pdf``."""
    html = render_to_string("billing/invoice_pdf.html", {"invoice": invoice})
    try:
        from xhtml2pdf import pisa
    except ImportError as exc:  # pragma: no cover - depends on environment
        logger.warning("billing: xhtml2pdf unavailable, invoice PDF skipped: %s", exc)
        return None
    from io import BytesIO

    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer)
    if getattr(result, "err", 0):  # pragma: no cover - malformed template
        logger.warning("billing: invoice PDF rendering failed for %s", invoice.number)
        return None
    name = f"{invoice.number.replace('/', '-')}.pdf"
    invoice.pdf.save(name, ContentFile(buffer.getvalue()), save=True)
    return invoice.pdf


@transaction.atomic
def create_invoice(
    company,
    amount,
    *,
    description="",
    provider="",
    provider_ref="",
    gstin=None,
    state_code=None,
    paid=True,
    issued_at=None,
    with_pdf=True,
):
    """Issue a GST invoice for ``company`` and return it."""
    from billing.services import get_subscription

    subscription = get_subscription(company)
    if gstin is None:
        gstin = subscription.gstin
    if state_code is None:
        state_code = subscription.billing_state_code
    amount = _q(amount)
    cgst, sgst, igst = gst_split(amount, state_code)
    issued_at = issued_at or timezone.now()
    invoice = Invoice.objects.create(
        company=company,
        number=next_number(issued_at),
        fy=financial_year(issued_at),
        amount=amount,
        gst_rate=Invoice.GST_RATE,
        cgst=cgst,
        sgst=sgst,
        igst=igst,
        total=_q(amount + cgst + sgst + igst),
        gstin=gstin or "",
        place_of_supply=str(state_code or ""),
        description=description or f"{subscription.plan.name} subscription",
        provider=provider or subscription.provider or "",
        provider_ref=provider_ref or "",
        issued_at=issued_at,
        paid_at=issued_at if paid else None,
    )
    if with_pdf:
        try:
            render_pdf(invoice)
        except Exception as exc:  # pragma: no cover - never block a payment
            logger.warning("billing: invoice PDF failed for %s: %s", invoice.number, exc)
    return invoice


def invoice_for_payment(subscription, *, amount=None, provider_ref="", provider=""):
    """Issue the invoice that follows a successful payment webhook."""
    plan = subscription.plan
    if amount is None:
        amount = plan.price_for(subscription.interval)
    if not amount:
        return None
    interval = subscription.get_interval_display().lower()
    return create_invoice(
        subscription.company,
        amount,
        description=f"{plan.name} plan — {interval} subscription",
        provider=provider or subscription.provider,
        provider_ref=provider_ref,
        paid=True,
    )
