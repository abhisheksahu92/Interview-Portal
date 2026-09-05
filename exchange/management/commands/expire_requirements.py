"""Close exchange requirements whose expiry has passed."""

from django.core.management.base import BaseCommand

from exchange.services import expire_requirements


class Command(BaseCommand):
    help = "Close every OPEN exchange requirement whose expires_at has passed."

    def handle(self, *args, **options):
        count = expire_requirements()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} requirement(s)."))
