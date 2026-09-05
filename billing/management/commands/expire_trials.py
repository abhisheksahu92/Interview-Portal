"""End trials whose 14 days are up: drop to STARTER with a 7-day grace."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing.models import Plan, Subscription
from billing.services import default_plan

#: Days after a trial ends during which plan limits are not yet enforced.
GRACE_DAYS = 7


class Command(BaseCommand):
    help = (
        "Move expired trial subscriptions onto STARTER with a 7-day grace "
        "window; paid plans are untouched."
    )

    def handle(self, *args, **options):
        now = timezone.now()
        grace_until = now + timedelta(days=GRACE_DAYS)
        expired = Subscription.objects.filter(
            status=Subscription.TRIALING, trial_ends_at__lt=now
        ).select_related("plan")
        starter = None
        count = 0
        for subscription in expired:
            fields = ["status", "trial_ends_at", "grace_until", "updated_at"]
            subscription.status = Subscription.ACTIVE
            subscription.trial_ends_at = now
            subscription.grace_until = grace_until
            # A trial billed on FREE is a legacy row; every trial now lands on
            # STARTER (₹999/seat) unless the company has already paid.
            if subscription.plan.code in {Plan.FREE, Plan.STARTER}:
                starter = starter or default_plan()
                subscription.plan = starter
                fields.append("plan")
            subscription.save(update_fields=fields)
            count += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Expired {count} trial(s); grace until {grace_until:%Y-%m-%d}."
            )
        )
