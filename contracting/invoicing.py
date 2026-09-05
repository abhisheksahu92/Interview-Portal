"""Month-end: approved timesheets → one GST invoice per client, PDF, email.

The FY numbering, the CGST/SGST/IGST split and the HTML→PDF approach are the
same as ``billing.invoicing``; only the counter differs. Client invoices are
numbered ``INV/2026-27/0001`` from :class:`contracting.models.ClientInvoiceCounter`,
which is *per company* as well as per financial year, so one tenant's sequence
never has holes explained by another tenant's billing run.
"""

import logging
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from billing.invoicing import company_state_code, financial_year, gst_split
from contracting import rates
from contracting.models import (
    ClientBillingProfile,
    ClientInvoice,
    ClientInvoiceCounter,
    Timesheet,
    money,
)
from contracting.notify import notify

logger = logging.getLogger(__name__)

NUMBER_PREFIX = "INV"

#: Recorded on an invoice raised while the tenant's own GST state is unknown —
#: the split then defaults to IGST, which may be wrong for a client in the same
#: state. The invoice page shows this as a warning.
MISSING_HOME_STATE_NOTE = (
    "Set your GSTIN in Billing to compute CGST/SGST correctly — this invoice "
    "defaulted to IGST because your company's GST state is unknown."
)


# --------------------------------------------------------------------------- #
# Numbering
# --------------------------------------------------------------------------- #


def next_number(company, moment=None, fy=None):
    """Allocate this company's next client-invoice number for the FY.

    The counter row is locked with ``SELECT ... FOR UPDATE`` inside a
    transaction, so two concurrent billing runs queue up rather than minting the
    same number. SQLite has no row locks but serialises writers, which gives the
    same guarantee, so the code path is identical there.
    """
    fy = fy or financial_year(moment)
    with transaction.atomic():
        counter = (
            ClientInvoiceCounter.objects.select_for_update()
            .filter(company=company, fy=fy)
            .first()
        )
        if counter is None:
            ClientInvoiceCounter.objects.get_or_create(
                company=company, fy=fy, defaults={"last_seq": 0}
            )
            counter = ClientInvoiceCounter.objects.select_for_update().get(
                company=company, fy=fy
            )
        counter.last_seq += 1
        counter.save(update_fields=["last_seq", "updated_at"])
        seq = counter.last_seq
    return f"{NUMBER_PREFIX}/{fy}/{seq:04d}"


def peek_number(company, moment=None, fy=None):
    """The number :func:`next_number` would hand out, without consuming it."""
    fy = fy or financial_year(moment)
    counter = ClientInvoiceCounter.objects.filter(company=company, fy=fy).first()
    seq = (counter.last_seq if counter else 0) + 1
    return f"{NUMBER_PREFIX}/{fy}/{seq:04d}"


# --------------------------------------------------------------------------- #
# Building invoices
# --------------------------------------------------------------------------- #


def billable_timesheets(company, period_start, period_end, client=None):
    """APPROVED, not-yet-invoiced timesheets whose period ends inside the window."""
    qs = (
        Timesheet.objects.for_company(company)
        .billable()
        .filter(
            client_invoice__isnull=True,
            period_end__gte=period_start,
            period_end__lte=period_end,
        )
        .select_related("engagement__contractor", "engagement__client")
        .order_by("engagement__client__name", "period_start")
    )
    if client is not None:
        qs = qs.filter(engagement__client=client)
    return qs


def line_item_for(timesheet):
    """One invoice line describing what a timesheet bills.

    ``total_inr`` is authoritative: for a prorated MONTH rate, ``unit_inr`` is a
    derived per-day figure and ``qty × unit_inr`` may differ from the total by a
    rounding paisa.
    """
    engagement = timesheet.engagement
    quantity = rates.quantity(timesheet)
    return {
        "kind": "TIMESHEET",
        "label": (
            f"{engagement.contractor.name} — {engagement.role_title} "
            f"({timesheet.period_start:%d %b} to {timesheet.period_end:%d %b %Y})"
        ),
        "qty": float(quantity),
        "unit_label": rates.unit_label(engagement.rate_unit),
        "rate_unit": engagement.rate_unit,
        "unit_inr": float(rates.unit_rate_for(timesheet, engagement.bill_rate_inr)),
        "total_inr": float(rates.bill_amount(timesheet)),
        "engagement": engagement.pk,
        "timesheet": timesheet.pk,
        "po_number": engagement.po_number,
    }


@transaction.atomic
def create_client_invoice(company, client, period_start, period_end, timesheets, *, issued_at=None):
    """Raise one invoice for ``client`` covering ``timesheets``."""
    from contracting import services

    timesheets = list(timesheets)
    if not timesheets:
        return None
    profile = ClientBillingProfile.for_client(client)
    issued_at = issued_at or timezone.now()
    line_items = [line_item_for(ts) for ts in timesheets]
    # The invoice period is what was actually billed, not the calendar month it
    # was run in: a week ending 3 May invoiced in the April run still reads
    # "06 Apr – 03 May".
    period_start = min(ts.period_start for ts in timesheets)
    period_end = max(ts.period_end for ts in timesheets)
    subtotal = money(sum(money(item["total_inr"]) for item in line_items))
    # The seller here is the *tenant*, not the platform: an agency in 27
    # billing a client in 27 charges CGST+SGST even though the platform
    # operator sits elsewhere.
    home_state = company_state_code(company)
    cgst, sgst, igst = gst_split(
        subtotal,
        profile.state_code,
        rate=ClientInvoice.GST_RATE,
        home_state_code=home_state,
    )
    basis_note = "" if home_state else MISSING_HOME_STATE_NOTE
    terms = profile.payment_terms_days or 30
    invoice = ClientInvoice.objects.create(
        company=company,
        client=client,
        number=next_number(company, issued_at),
        fy=financial_year(issued_at),
        period_start=period_start,
        period_end=period_end,
        line_items=line_items,
        subtotal=subtotal,
        gst_rate=ClientInvoice.GST_RATE,
        cgst=cgst,
        sgst=sgst,
        igst=igst,
        total=money(subtotal + cgst + sgst + igst),
        gstin=profile.gstin or "",
        place_of_supply=str(profile.state_code or ""),
        issued_at=issued_at,
        due_at=issued_at.date() + timedelta(days=terms),
        gst_basis_note=basis_note,
    )
    for timesheet in timesheets:
        services.mark_invoiced(timesheet, invoice)
    try:
        render_pdf(invoice)
    except Exception as exc:  # never block a billing run on a PDF
        logger.warning("contracting: invoice PDF failed for %s: %s", invoice.number, exc)
    post_platform_fee(invoice)
    return invoice


def generate_client_invoices(company, period, *, period_end=None, client=None):
    """Invoice every client with approved timesheets in ``period``.

    ``period`` is any date inside the billing month (or the explicit start when
    ``period_end`` is given). Returns the list of invoices created — empty when
    nothing was approved, and idempotent because an invoiced timesheet is never
    picked up twice.
    """
    from contracting import services

    if period_end is None:
        period_start, period_end = services.month_bounds(period)
    else:
        period_start = period
    pending = list(billable_timesheets(company, period_start, period_end, client=client))
    grouped = {}
    for timesheet in pending:
        grouped.setdefault(timesheet.engagement.client_id, []).append(timesheet)
    invoices = []
    for timesheets in grouped.values():
        invoice = create_client_invoice(
            company,
            timesheets[0].engagement.client,
            period_start,
            period_end,
            timesheets,
        )
        if invoice is not None:
            invoices.append(invoice)
    return invoices


# --------------------------------------------------------------------------- #
# Platform fee (opt-in)
# --------------------------------------------------------------------------- #

#: Settings key holding a per-invoice platform fee in rupees. Unset = no fee.
PLATFORM_FEE_SETTING = "CONTRACTING_INVOICE_FEE_INR"
#: Plan feature key that overrides the setting for a specific tier.
PLATFORM_FEE_FEATURE = "contracting_invoice_fee_inr"


def platform_fee_inr(company):
    """The per-invoice platform fee for ``company``, or ``None`` when there is none.

    A plan-level figure wins over the project-wide setting; both are optional
    and the default is no fee at all.
    """
    try:
        from billing.entitlements import plan_for

        plan = plan_for(company)
        configured = (getattr(plan, "features", None) or {}).get(PLATFORM_FEE_FEATURE)
    except Exception:  # billing is being reshaped in parallel; degrade quietly
        configured = None
    if configured in (None, "", False):
        configured = getattr(settings, PLATFORM_FEE_SETTING, None)
    if configured in (None, "", False):
        return None
    fee = money(configured)
    return fee if fee > 0 else None


def post_platform_fee(invoice):
    """Push this invoice's platform fee onto the company's billing ledger.

    No-op when no fee is configured, and tolerant of ``billing.ledger`` not
    existing yet (it lands with the parallel billing work).
    """
    fee = platform_fee_inr(invoice.company)
    if fee is None:
        return None
    try:
        from billing.ledger import add_charge
    except ImportError:
        logger.info("contracting: billing.ledger unavailable, platform fee not posted")
        return None
    try:
        return add_charge(
            invoice.company,
            "PLATFORM_FEE",
            f"Contractor invoice {invoice.number}",
            fee,
            ref=f"contracting:invoice:{invoice.pk}",
            occurred_at=invoice.issued_at,
        )
    except Exception as exc:
        logger.warning("contracting: platform fee not posted for %s: %s", invoice.number, exc)
        return None


# --------------------------------------------------------------------------- #
# PDF + delivery
# --------------------------------------------------------------------------- #


def pdf_bytes(invoice):
    """The invoice rendered to PDF bytes, or ``None`` when xhtml2pdf is absent."""
    html = render_to_string(
        "contracting/pdf/client_invoice.html",
        {"invoice": invoice, "client": invoice.client, "company": invoice.company},
    )
    try:
        from xhtml2pdf import pisa
    except ImportError as exc:  # pragma: no cover - depends on environment
        logger.warning("contracting: xhtml2pdf unavailable, PDF skipped: %s", exc)
        return None
    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer)
    if getattr(result, "err", 0):  # pragma: no cover - malformed template
        logger.warning("contracting: PDF rendering failed for %s", invoice.number)
        return None
    return buffer.getvalue()


def pdf_filename(invoice):
    return f"{invoice.number.replace('/', '-')}.pdf"


def render_pdf(invoice):
    """Render and store the invoice PDF on ``invoice.pdf``."""
    content = pdf_bytes(invoice)
    if content is None:
        return None
    invoice.pdf.save(pdf_filename(invoice), ContentFile(content), save=True)
    return invoice.pdf


def recipients_for(invoice):
    profile = ClientBillingProfile.for_client(invoice.client)
    emails = [profile.billing_email, invoice.client.contact_email]
    return [email for email in emails if email][:1]


def send_invoice(invoice, *, request=None):
    """Email the invoice to the client's billing contact and mark it SENT."""
    if not invoice.pdf:
        try:
            render_pdf(invoice)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("contracting: PDF failed for %s: %s", invoice.number, exc)
    attachments = []
    if invoice.pdf:
        try:
            invoice.pdf.open("rb")
            attachments.append((pdf_filename(invoice), invoice.pdf.read(), "application/pdf"))
        except (FileNotFoundError, OSError):  # storage lost the file
            attachments = []
        finally:
            invoice.pdf.close()
    period = f"{invoice.period_start:%d %b} – {invoice.period_end:%d %b %Y}"
    for email in recipients_for(invoice):
        notify(
            "client_invoice_sent",
            email,
            {
                "invoice_number": invoice.number,
                "client_name": invoice.client.name,
                "period": period,
                "total": str(invoice.total),
                "due_at": str(invoice.due_at or ""),
            },
            company=invoice.company,
            subject=f"Invoice {invoice.number} from {invoice.company.name}",
            body=(
                f"Invoice {invoice.number} for {period}.\n\n"
                f"Amount due: INR {invoice.total}"
                + (f", by {invoice.due_at:%d %b %Y}" if invoice.due_at else "")
                + "\n\nThank you for your business."
            ),
            attachments=attachments,
        )
    invoice.status = ClientInvoice.SENT
    invoice.sent_at = timezone.now()
    invoice.save(update_fields=["status", "sent_at"])
    return invoice


def mark_paid(invoice, when=None):
    invoice.status = ClientInvoice.PAID
    invoice.paid_at = when or timezone.now()
    invoice.save(update_fields=["status", "paid_at"])
    return invoice


def refresh_overdue(company):
    """Flag SENT invoices past their due date as OVERDUE; returns the count."""
    today = timezone.localdate()
    stale = ClientInvoice.objects.for_company(company).filter(
        status=ClientInvoice.SENT, due_at__lt=today
    )
    return stale.update(status=ClientInvoice.OVERDUE)
