"""Dunning: chase past-due subscriptions, then downgrade them.

Reminders go out on day 1, 3 and 7 after a subscription went PAST_DUE; on day 7
(and after) the company is downgraded to FREE. Every step is recorded in
``DunningReminder`` so the management command is idempotent.

A subscription goes PAST_DUE two ways: the gateway told us a charge failed, or
:func:`flag_overdue_invoices` found an invoice we issued ourselves that is past
its due date and still unpaid. The second case is what makes an unpaid monthly
bill chaseable at all — before it, only gateway failures were ever dunned.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from billing.models import DunningReminder, Invoice, Subscription
from billing.services import free_plan

logger = logging.getLogger(__name__)

#: Days after going past due on which a reminder is sent.
REMINDER_DAYS = (1, 3, 7)
#: Day on which an unpaid subscription drops back to FREE.
DOWNGRADE_DAY = 7


def unpaid_overdue_invoices(company, today=None):
    """Invoices this company was billed for and has not paid on time."""
    today = today or timezone.localdate()
    return Invoice.objects.filter(
        company=company,
        status__in=[Invoice.DRAFT, Invoice.ISSUED],
        paid_at__isnull=True,
        due_at__lt=today,
    )


def flag_overdue_invoices(now=None):
    """Mark companies with an overdue invoice PAST_DUE. Returns the count.

    ``past_due_since`` is dated from the *oldest* overdue invoice, so a bill
    that has been outstanding for a week enters the ladder where it belongs
    rather than restarting at day 0.
    """
    now = now or timezone.now()
    today = timezone.localdate(now)
    flagged = 0
    overdue = (
        Invoice.objects.filter(
            status__in=[Invoice.DRAFT, Invoice.ISSUED],
            paid_at__isnull=True,
            due_at__lt=today,
        )
        .order_by("company_id", "due_at")
        .values_list("company_id", "due_at")
    )
    oldest = {}
    for company_id, due_at in overdue:
        oldest.setdefault(company_id, due_at)
    if not oldest:
        return 0
    for subscription in Subscription.objects.filter(company_id__in=oldest).select_related(
        "company", "plan"
    ):
        if subscription.status in {Subscription.PAST_DUE, Subscription.CANCELED}:
            continue
        due_at = oldest[subscription.company_id]
        subscription.status = Subscription.PAST_DUE
        subscription.past_due_since = subscription.past_due_since or _aware(due_at)
        subscription.save(update_fields=["status", "past_due_since", "updated_at"])
        flagged += 1
    return flagged


def settle(company):
    """Clear PAST_DUE once nothing is overdue any more (called when paid)."""
    subscription = Subscription.objects.filter(company=company).first()
    if subscription is None or subscription.status != Subscription.PAST_DUE:
        return None
    if unpaid_overdue_invoices(company).exists():
        return subscription
    subscription.status = Subscription.ACTIVE
    subscription.past_due_since = None
    subscription.save(update_fields=["status", "past_due_since", "updated_at"])
    subscription.dunning_reminders.all().delete()
    return subscription


def _aware(day):
    """Midnight of ``day`` in the current timezone."""
    from datetime import datetime, time

    stamp = datetime.combine(day, time.min)
    if timezone.is_naive(stamp):
        stamp = timezone.make_aware(stamp)
    return stamp


def days_past_due(subscription, now=None):
    since = subscription.past_due_since
    if since is None:
        return 0
    return max(0, ((now or timezone.now()) - since).days)


def due_reminders(subscription, now=None):
    """Reminder day numbers that are due and not yet sent."""
    elapsed = days_past_due(subscription, now)
    already = set(
        subscription.dunning_reminders.values_list("day", flat=True)
    )
    return [day for day in REMINDER_DAYS if day <= elapsed and day not in already]


def _recipients(subscription):
    from core.models import Membership

    return list(
        Membership.objects.filter(
            company_id=subscription.company_id, role=Membership.OWNER
        ).values_list("user__email", flat=True)
    )


def send_reminder(subscription, day):
    """Send one payment-failed reminder; records it and returns the row."""
    context = {
        "company": subscription.company.name,
        "plan": subscription.plan.name,
        "day": day,
        "days_left": max(0, DOWNGRADE_DAY - day),
    }
    delivered = False
    try:  # the notifications app may not be finished yet
        from notifications import send

        for email in _recipients(subscription):
            send("payment_failed", email, context, company=subscription.company)
        delivered = True
    except Exception as exc:
        logger.info("billing: payment_failed notification unavailable: %s", exc)

    if not delivered:
        recipients = _recipients(subscription)
        if recipients:
            send_mail(
                subject=f"Payment failed for {subscription.company.name}",
                message=(
                    f"We could not collect your {subscription.plan.name} subscription "
                    f"payment. Please update your payment method within "
                    f"{context['days_left']} day(s) to keep your plan."
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=recipients,
                fail_silently=True,
            )
    return DunningReminder.objects.create(subscription=subscription, day=day)


def downgrade(subscription):
    """Drop a stubbornly unpaid subscription back to FREE."""
    subscription.plan = free_plan()
    subscription.status = Subscription.CANCELED
    subscription.trial_ends_at = None
    subscription.save()
    return subscription


def run(now=None):
    """Process every past-due subscription. Returns ``(sent, downgraded)``."""
    now = now or timezone.now()
    flag_overdue_invoices(now)
    sent = downgraded = 0
    queryset = Subscription.objects.filter(
        status=Subscription.PAST_DUE, past_due_since__isnull=False
    ).select_related("company", "plan")
    for subscription in queryset:
        for day in due_reminders(subscription, now):
            send_reminder(subscription, day)
            sent += 1
        if days_past_due(subscription, now) >= DOWNGRADE_DAY:
            downgrade(subscription)
            downgraded += 1
    return sent, downgraded
