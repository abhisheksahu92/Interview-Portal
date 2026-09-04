"""Retry PENDING webhook deliveries whose backoff window has elapsed.

Registered in ``core.management.commands.run_periodic.PERIODIC_COMMANDS`` so a
single cron entry keeps the queue moving:

    python manage.py deliver_webhooks [--limit 200]
"""

from django.core.management.base import BaseCommand

from integrations.delivery import deliver_due


class Command(BaseCommand):
    help = "Retry due outbound webhook deliveries with exponential backoff."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Maximum deliveries to attempt in this run (default 200).",
        )

    def handle(self, *args, **options):
        sent, pending, failed = deliver_due(limit=options["limit"])
        total = sent + pending + failed
        self.stdout.write(
            f"deliver_webhooks: {total} attempted, {sent} sent, "
            f"{pending} rescheduled, {failed} exhausted."
        )
