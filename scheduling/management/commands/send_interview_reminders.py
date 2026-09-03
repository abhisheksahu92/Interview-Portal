"""Send 24h / 1h interview reminders.

Idempotent: each interview carries ``reminder_24h_sent_at`` /
``reminder_1h_sent_at`` stamps, so re-running the command (or running it every
few minutes from cron) never re-sends the same reminder. Rescheduling clears the
stamps so the candidate is reminded about the new time.

    manage.py send_interview_reminders [--window-minutes 30] [--dry-run]
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone as dj_timezone

from scheduling import notify as notifications
from scheduling.models import Interview

#: (label, lead time, model field holding the sent stamp, notification event)
REMINDERS = (
    ("24h", timedelta(hours=24), "reminder_24h_sent_at", notifications.REMINDER_24H),
    ("1h", timedelta(hours=1), "reminder_1h_sent_at", notifications.REMINDER_1H),
)
DEFAULT_WINDOW_MINUTES = 30


class Command(BaseCommand):
    help = "Send 24-hour and 1-hour interview reminders (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--window-minutes",
            type=int,
            default=DEFAULT_WINDOW_MINUTES,
            help="How far ahead of each lead time to look (default 30).",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Report without sending or stamping."
        )

    def handle(self, *args, **options):
        window = timedelta(minutes=max(1, options["window_minutes"]))
        dry_run = options["dry_run"]
        now = dj_timezone.now()
        total = 0

        for label, lead, field, event in REMINDERS:
            due = (
                Interview.objects.filter(
                    status__in=[Interview.CONFIRMED, Interview.RESCHEDULED],
                    scheduled_start__gt=now,
                    scheduled_start__lte=now + lead + window,
                    **{f"{field}__isnull": True},
                )
                .select_related("application__job", "application__candidate__user", "stage")
                .prefetch_related("interviewers")
            )
            for interview in due:
                total += 1
                if dry_run:
                    self.stdout.write(f"[dry-run] {label} reminder for interview {interview.pk}")
                    continue
                notifications.notify_candidate(event, interview)
                notifications.notify_interviewers(event, interview)
                setattr(interview, field, dj_timezone.now())
                interview.save(update_fields=[field, "updated_at"])
                self.stdout.write(f"Sent {label} reminder for interview {interview.pk}")

        self.stdout.write(
            self.style.SUCCESS(f"{'Would send' if dry_run else 'Sent'} {total} reminder(s).")
        )
