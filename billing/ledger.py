"""The public write seam for charges raised by other apps.

Any app that needs to put money on a tenant's next monthly bill calls this
module — never :class:`billing.models.BillingCharge` directly — through a late
import so billing stays an optional dependency::

    from billing.ledger import add_charge   # or, inside a function:
    from billing import ledger
    ledger.add_charge(
        company,
        ledger.BGV,
        "BGV — Priya Sharma",
        499,
        ref=f"bgv:{check.pk}",
    )

``ref`` is an idempotency key scoped to ``(company, kind)``: calling
``add_charge`` twice with the same ref updates the existing row instead of
double-charging, and is refused once the charge has been invoiced.
"""

import logging

from django.db import transaction
from django.utils import timezone

from billing.models import BillingCharge

logger = logging.getLogger(__name__)

SUBSCRIPTION = BillingCharge.SUBSCRIPTION
SUCCESS_FEE = BillingCharge.SUCCESS_FEE
AI_OVERAGE = BillingCharge.AI_OVERAGE
SEAT = BillingCharge.SEAT
BGV = BillingCharge.BGV
PLATFORM_FEE = BillingCharge.PLATFORM_FEE
OTHER = BillingCharge.OTHER


@transaction.atomic
def add_charge(company, kind, label, amount_inr, ref="", occurred_at=None):
    """Record a charge for ``company`` and return the :class:`BillingCharge`.

    ``kind`` is one of the ``BillingCharge`` kinds (``BGV``, ``PLATFORM_FEE``,
    …); ``ref`` makes the call idempotent. Returns ``None`` when ``company`` is
    missing so callers never have to guard the happy path.
    """
    if company is None:
        return None
    kind = str(kind or OTHER)
    occurred_at = occurred_at or timezone.now()
    if ref:
        existing = (
            BillingCharge.objects.select_for_update()
            .filter(company=company, kind=kind, ref=ref)
            .first()
        )
        if existing is not None:
            if existing.invoice_id is not None:
                return existing  # already billed: never move a billed charge
            existing.label = label or existing.label
            existing.amount_inr = amount_inr
            existing.occurred_at = occurred_at
            existing.save(update_fields=["label", "amount_inr", "occurred_at"])
            return existing
    return BillingCharge.objects.create(
        company=company,
        kind=kind,
        label=label or dict(BillingCharge.KIND_CHOICES).get(kind, kind),
        amount_inr=amount_inr,
        ref=ref or "",
        occurred_at=occurred_at,
    )


def charges_for_period(company, start, end, *, uninvoiced_only=True):
    """Charges that fall inside ``[start, end)``, oldest first."""
    qs = BillingCharge.objects.filter(
        company=company, occurred_at__gte=start, occurred_at__lt=end
    )
    if uninvoiced_only:
        qs = qs.filter(invoice__isnull=True)
    return list(qs.order_by("occurred_at", "id"))


def outstanding_total(company):
    """Sum of this company's charges that no invoice has picked up yet."""
    from decimal import Decimal

    from django.db.models import Sum

    total = BillingCharge.objects.filter(
        company=company, invoice__isnull=True
    ).aggregate(total=Sum("amount_inr"))["total"]
    return Decimal(total or 0)
