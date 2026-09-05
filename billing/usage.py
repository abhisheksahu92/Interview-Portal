"""Metered usage: monthly quotas per plan, consumption and 80% warnings.

Public API::

    from billing import usage

    usage.consume(company, usage.AI_SCREEN)        # billed overage, or QuotaExceeded
    usage.remaining(company, usage.WHATSAPP_MSG)   # int, or None = unlimited
    usage.quota(company, usage.VIDEO_MINUTE)
    usage.snapshot(company)                        # for the billing overview
"""

import logging
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from billing.models import Plan, UsageRecord

logger = logging.getLogger(__name__)

AI_SCREEN = UsageRecord.AI_SCREEN
WHATSAPP_MSG = UsageRecord.WHATSAPP_MSG
VIDEO_MINUTE = UsageRecord.VIDEO_MINUTE
KINDS = (AI_SCREEN, WHATSAPP_MSG, VIDEO_MINUTE)

#: Fraction of the quota at which a "running low" notification is sent.
warn_threshold = 0.8

# Per-tier allowances that are not stored on the Plan row. PRO is the legacy
# equivalent of GROWTH.
WHATSAPP_QUOTAS = {Plan.GROWTH: 500, Plan.PRO: 500, Plan.AGENCY: 5000}
VIDEO_QUOTAS = {Plan.AGENCY: 300}


class QuotaExceeded(Exception):
    """Raised by :func:`consume` when a company is out of monthly allowance."""

    def __init__(self, kind, quota, used):
        self.kind = kind
        self.quota = quota
        self.used = used
        super().__init__(
            f"Monthly {kind} quota of {quota} reached ({used} used). "
            "Upgrade your plan for more."
        )


def period_start(moment=None):
    """First day of the current monthly billing period."""
    now = moment or timezone.now()
    return now.date().replace(day=1)


def quota(company, kind):
    """Monthly allowance of ``kind`` for ``company`` (0 when not included)."""
    from billing.entitlements import plan_for

    plan = plan_for(company)
    if plan is None:
        return 0
    if kind == AI_SCREEN:
        return plan.ai_allowance
    if kind == WHATSAPP_MSG:
        return int(WHATSAPP_QUOTAS.get(plan.code, 0))
    if kind == VIDEO_MINUTE:
        return int(VIDEO_QUOTAS.get(plan.code, 0))
    raise ValueError(f"Unknown usage kind: {kind}")


def used(company, kind, moment=None):
    """How much of ``kind`` this company consumed in the current period."""
    total = UsageRecord.objects.filter(
        company=company, kind=kind, period_start=period_start(moment)
    ).aggregate(total=Sum("quantity"))["total"]
    return int(total or 0)


def remaining(company, kind, moment=None):
    """Allowance left this period (never negative)."""
    return max(0, quota(company, kind) - used(company, kind, moment=moment))


def hard_capped(company):
    """True when this company has opted out of billed overage."""
    from billing.models import Subscription

    return bool(
        Subscription.objects.filter(company=company, hard_cap=True).exists()
    )


def overage_price(company, kind):
    """Per-unit price of one unit beyond the allowance (0 = not billable)."""
    from billing.entitlements import plan_for

    if kind != AI_SCREEN:
        return Decimal("0")
    plan = plan_for(company)
    return Decimal(getattr(plan, "ai_overage_inr", 0) or 0)


def consume(company, kind, qty=1):
    """Record ``qty`` units of ``kind`` for ``company``.

    Past the plan allowance AI screening is *billed*, not blocked: the record
    is flagged ``overage`` and a matching ``AI_OVERAGE`` charge lands on the
    next monthly invoice through :func:`billing.ledger.add_charge`. A company
    that would rather stop than pay sets ``Subscription.hard_cap``, and other
    metered kinds (WhatsApp, video) still raise :class:`QuotaExceeded`. The
    ``usage_warning`` notification still fires the first time usage crosses 80%.
    """
    if company is None:
        raise QuotaExceeded(kind, 0, 0)
    if kind not in KINDS:
        raise ValueError(f"Unknown usage kind: {kind}")
    qty = int(qty)
    if qty <= 0:
        raise ValueError("qty must be positive")

    allowance = quota(company, kind)
    before = used(company, kind)
    after = before + qty
    is_overage = after > allowance
    if is_overage:
        unit = overage_price(company, kind)
        if not unit or hard_capped(company):
            raise QuotaExceeded(kind, allowance, before)

    record = UsageRecord.objects.create(
        company=company,
        kind=kind,
        quantity=qty,
        period_start=period_start(),
        overage=is_overage,
    )
    if is_overage:
        _bill_overage(company, kind, before, after, allowance)
    if allowance and before < allowance * warn_threshold <= after:
        _warn(company, kind, after, allowance)
    return record


def _bill_overage(company, kind, before, after, allowance):
    """Keep this period's AI overage charge in step with recorded usage."""
    from billing import ledger

    units = after - max(before, allowance)
    if units <= 0:
        return None
    start = period_start()
    total_units = max(0, after - allowance)
    unit = overage_price(company, kind)
    return ledger.add_charge(
        company,
        ledger.AI_OVERAGE,
        f"AI screening overage — {total_units} beyond {allowance} included",
        Decimal(total_units) * unit,
        ref=f"ai-overage:{start:%Y-%m}",
    )


def _warn(company, kind, used_now, allowance):
    """Notify the tenant that a quota is running low; degrade silently."""
    try:  # the notifications app may not be finished yet
        from notifications import send

        send(
            "usage_warning",
            None,
            {
                "kind": kind,
                "used": used_now,
                "quota": allowance,
                "percent": int(round(100 * used_now / allowance)),
            },
            company=company,
        )
    except Exception as exc:  # pragma: no cover - depends on sibling app
        logger.info("billing: usage_warning notification skipped: %s", exc)


def snapshot(company):
    """Per-kind usage rows for the billing overview page."""
    labels = dict(UsageRecord.KIND_CHOICES)
    rows = []
    for kind in KINDS:
        allowance = quota(company, kind)
        consumed = used(company, kind)
        percent = int(round(100 * consumed / allowance)) if allowance else 0
        rows.append(
            {
                "kind": kind,
                "label": labels[kind],
                "quota": allowance,
                "used": consumed,
                "remaining": max(0, allowance - consumed),
                "percent": min(100, percent),
                "warning": bool(allowance) and percent >= int(warn_threshold * 100),
                "included": bool(allowance),
                "over": max(0, consumed - allowance),
                "overage_inr": overage_price(company, kind),
            }
        )
    return rows
