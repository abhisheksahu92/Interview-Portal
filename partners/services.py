"""Commission accounting for referred companies."""

from decimal import ROUND_HALF_UP, Decimal

from partners.models import CommissionLedger, Referral


def _money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def referral_for(company):
    """The active :class:`~partners.models.Referral` for ``company``, or None."""
    if company is None:
        return None
    return Referral.objects.select_related("reseller").filter(company=company).first()


def record_commission(company, amount_inr, invoice_ref):
    """Record the reseller commission for one paid invoice.

    Idempotent: calling it twice with the same ``invoice_ref`` returns the
    existing ledger row. Returns None when the company was not referred or its
    reseller is inactive. ``billing`` calls this when an invoice is paid.
    """
    referral = referral_for(company)
    if referral is None or not referral.reseller.active:
        return None
    amount = _money(amount_inr)
    pct = Decimal(str(referral.reseller.commission_pct or 0))
    commission = _money(amount * pct / Decimal("100"))
    entry, created = CommissionLedger.objects.get_or_create(
        reseller=referral.reseller,
        invoice_ref=str(invoice_ref),
        defaults={"company": company, "amount_inr": amount, "commission_inr": commission},
    )
    if created and referral.first_payment_at is None:
        from django.utils import timezone

        referral.first_payment_at = timezone.now()
        referral.save(update_fields=["first_payment_at"])
    return entry


def reseller_totals(reseller):
    """Aggregate earned / paid / pending commission for a reseller dashboard."""
    from django.db.models import Sum

    rows = CommissionLedger.objects.filter(reseller=reseller)
    earned = rows.aggregate(total=Sum("commission_inr"))["total"] or Decimal("0")
    paid = rows.filter(paid_out_at__isnull=False).aggregate(total=Sum("commission_inr"))[
        "total"
    ] or Decimal("0")
    return {
        "earned": _money(earned),
        "paid": _money(paid),
        "pending": _money(earned - paid),
        "invoiced": _money(rows.aggregate(total=Sum("amount_inr"))["total"] or 0),
    }
