"""Give every company a billing record (FREE unless it already has one)."""

from django.core.management.base import BaseCommand

from billing.models import Subscription
from billing.services import get_subscription
from core.models import Company


class Command(BaseCommand):
    help = "Create a FREE subscription for every company that has no billing record."

    def handle(self, *args, **options):
        created = 0
        for company in Company.objects.all():
            if not Subscription.objects.filter(company=company).exists():
                get_subscription(company)
                created += 1
        self.stdout.write(
            self.style.SUCCESS(f"Provisioned {created} subscription(s).")
        )
