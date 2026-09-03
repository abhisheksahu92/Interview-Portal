"""End trials whose 14 days are up (entitlements fall back to FREE)."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing.models import Subscription


class Command(BaseCommand):
    help = "Move expired trial subscriptions off TRIALING; paid plans are untouched."

    def handle(self, *args, **options):
        now = timezone.now()
        expired = Subscription.objects.filter(
            status=Subscription.TRIALING, trial_ends_at__lt=now
        ).select_related("plan")
        count = 0
        for subscription in expired:
            subscription.status = Subscription.ACTIVE
            subscription.trial_ends_at = now
            subscription.save(update_fields=["status", "trial_ends_at", "updated_at"])
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Expired {count} trial(s)."))
