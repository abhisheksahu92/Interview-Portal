"""Transcribe and AI-review every uploaded video response."""

from django.core.management.base import BaseCommand

from video import processing


class Command(BaseCommand):
    help = "Transcribe and AI-review uploaded video responses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=None, help="Process at most N responses."
        )

    def handle(self, *args, **options):
        pending = processing.pending_responses().count()
        if not pending:
            self.stdout.write("No video responses are waiting to be processed.")
            return
        done = processing.process_pending(limit=options.get("limit"))
        self.stdout.write(
            self.style.SUCCESS(f"Processed {done} of {pending} pending video response(s).")
        )
