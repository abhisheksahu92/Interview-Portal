"""Re-attempt failed notifications, with a backoff based on attempt count."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from notifications import api
from notifications.models import OutboundMessage

MAX_ATTEMPTS = 3
BASE_BACKOFF_MINUTES = 5


def backoff_for(attempts):
    """Exponential wait before the next try: 5m, 10m, 20m …"""
    return timedelta(minutes=BASE_BACKOFF_MINUTES * (2 ** max(attempts - 1, 0)))


def is_due(message, now=None):
    now = now or timezone.now()
    last = message.last_attempt_at or message.created_at
    if last is None:
        return True
    return now - last >= backoff_for(message.attempts)


class Command(BaseCommand):
    help = "Retry FAILED outbound notifications (max 3 attempts, exponential backoff)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-attempts", type=int, default=MAX_ATTEMPTS,
            help=f"Give up after this many attempts (default {MAX_ATTEMPTS}).",
        )
        parser.add_argument(
            "--force", action="store_true", help="Ignore the backoff window."
        )
        parser.add_argument(
            "--limit", type=int, default=200, help="Maximum messages to process."
        )

    def handle(self, *args, **options):
        max_attempts = options["max_attempts"]
        queryset = OutboundMessage.objects.retryable(max_attempts)[: options["limit"]]
        retried = succeeded = skipped = 0
        for message in queryset:
            if not options["force"] and not is_due(message):
                skipped += 1
                continue
            message.status = OutboundMessage.QUEUED
            api.deliver(message)
            retried += 1
            if message.status == OutboundMessage.SENT:
                succeeded += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Retried {retried} message(s): {succeeded} sent, "
                f"{retried - succeeded} still failing, {skipped} not due yet."
            )
        )
        return None
