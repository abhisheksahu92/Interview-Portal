"""End trials whose 14 days are up, and warn before they do.

A trial used to expire straight to ACTIVE on STARTER. Nothing then asked the
company for money: ``run_dunning`` only chases PAST_DUE rows, so a tenant that
never entered a card was never chased and kept using the product for free.
A trial with no payment method now lands PAST_DUE so the existing dunning
ladder picks it up on day 1, 3 and 7.

It also went silent: on day 14 half the product started returning 403 with no
warning. Reminders now go out three days and one day before the end.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing import notify as billing_notify
from billing.models import Plan, Subscription
from billing.services import default_plan

#: Days after a trial ends during which plan limits are not yet enforced.
GRACE_DAYS = 7

#: Days before the end of a trial on which a reminder is sent.
WARN_DAYS = (3, 1)


class Command(BaseCommand):
    help = (
        "Warn about trials about to end, then move expired ones onto STARTER: "
        "PAST_DUE when no payment method is on file, ACTIVE when there is one."
    )

    def handle(self, *args, **options):
        now = timezone.now()
        warned = self._warn_upcoming(now)
        count, chased = self._expire(now)
        self.stdout.write(
            self.style.SUCCESS(f"Warned {warned}; expired {count} trial(s), {chased} now past due.")
        )

    def _warn_upcoming(self, now):
        """One reminder per threshold, deduped by ``trial_warned_days``."""
        warned = 0
        for days in WARN_DAYS:
            window_end = now + timedelta(days=days)
            due = Subscription.objects.filter(
                status=Subscription.TRIALING,
                trial_ends_at__gt=now,
                trial_ends_at__lte=window_end,
            ).select_related("company", "plan")
            for subscription in due:
                sent = list(subscription.trial_warned_days or [])
                if days in sent:
                    continue
                for email in billing_notify.owner_emails(subscription.company):
                    billing_notify.notify(
                        "trial_ending",
                        email,
                        {
                            "company": subscription.company,
                            "days_left": days,
                            "trial_ends_at": subscription.trial_ends_at,
                            "billing_url": billing_notify.billing_url(),
                        },
                        company=subscription.company,
                        subject=f"Your trial ends in {days} day{'' if days == 1 else 's'}",
                        body=(
                            f"Your Interview Portal trial ends in {days} "
                            f"day{'' if days == 1 else 's'}. Add a payment method to keep "
                            f"your workspace: {billing_notify.billing_url()}"
                        ),
                    )
                sent.append(days)
                subscription.trial_warned_days = sent
                subscription.save(update_fields=["trial_warned_days", "updated_at"])
                warned += 1
        return warned

    def _expire(self, now):
        grace_until = now + timedelta(days=GRACE_DAYS)
        expired = Subscription.objects.filter(
            status=Subscription.TRIALING, trial_ends_at__lt=now
        ).select_related("plan", "company")
        starter = None
        count = chased = 0
        for subscription in expired:
            fields = ["status", "trial_ends_at", "grace_until", "updated_at"]
            subscription.trial_ends_at = now
            subscription.grace_until = grace_until
            # No card on file means nobody has agreed to pay: go PAST_DUE so the
            # dunning ladder chases it, rather than ACTIVE and silently free.
            if subscription.has_payment_method:
                subscription.status = Subscription.ACTIVE
            else:
                subscription.status = Subscription.PAST_DUE
                subscription.past_due_since = subscription.past_due_since or now
                fields.append("past_due_since")
                chased += 1
            # A trial billed on FREE is a legacy row; every trial now lands on
            # STARTER (₹999/seat) unless the company has already paid.
            if subscription.plan.code in {Plan.FREE, Plan.STARTER}:
                starter = starter or default_plan()
                subscription.plan = starter
                fields.append("plan")
            subscription.save(update_fields=fields)
            count += 1
        return count, chased
