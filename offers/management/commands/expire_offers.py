"""Mark open offers past their expiry date as EXPIRED."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from offers.services import expire_offers


class Command(BaseCommand):
    help = "Expire offers whose expires_at has passed (run from cron/scheduler)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would expire without changing anything.",
        )

    def handle(self, *args, **options):
        from offers.models import Offer

        now = timezone.now()
        if options["dry_run"]:
            count = Offer.objects.expiring_before(now).count()
            self.stdout.write(f"{count} offer(s) would be expired.")
            return
        count = expire_offers(now=now)
        self.stdout.write(self.style.SUCCESS(f"Expired {count} offer(s)."))
