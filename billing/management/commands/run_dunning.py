"""Send dunning reminders for past-due subscriptions and downgrade stragglers."""

from django.core.management.base import BaseCommand

from billing import dunning


class Command(BaseCommand):
    help = "Send day 1/3/7 payment reminders, then downgrade unpaid companies to FREE."

    def handle(self, *args, **options):
        sent, downgraded = dunning.run()
        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {sent} reminder(s); downgraded {downgraded} subscription(s)."
            )
        )
