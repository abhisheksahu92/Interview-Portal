"""Verify a licence key's signature and expiry."""

from django.core.management.base import BaseCommand, CommandError

from partners.licensing import verify_license


class Command(BaseCommand):
    help = "Verify a self-hosted licence key: verify_license KEY"

    def add_arguments(self, parser):
        parser.add_argument("key")

    def handle(self, *args, **options):
        result = verify_license(options["key"])
        if not result["valid"]:
            raise CommandError(f"Licence invalid: {result['reason']}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Licence valid — company {result['company_id']}, {result['seats']} seats, "
                f"expires {result['expires_at']:%Y-%m-%d}"
            )
        )
