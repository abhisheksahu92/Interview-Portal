"""Seed StageTransition history from the current state of each application.

Applications created before the analytics app existed have no history rows; this
command gives each of them a single synthetic transition into its current stage
so funnel and velocity metrics are not blind to them. It is idempotent: an
application that already has history is skipped.
"""

from django.core.management.base import BaseCommand

from analytics.models import StageTransition
from core.models import Company
from jobs.models import Application


class Command(BaseCommand):
    help = "Create StageTransition rows for applications that have no history yet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--company",
            dest="company",
            default=None,
            help="Limit the backfill to one company slug.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created without writing anything.",
        )

    def handle(self, *args, **options):
        applications = Application.objects.exclude(stage_transitions__isnull=False)
        slug = options.get("company")
        if slug:
            company = Company.objects.filter(slug=slug).first()
            if company is None:
                self.stderr.write(self.style.ERROR(f"No company with slug '{slug}'."))
                return
            applications = applications.filter(job__company=company)

        rows = [
            StageTransition(
                application_id=pk,
                from_stage=None,
                to_stage_id=stage_id,
                status_after=status,
                at=updated_at or created_at,
            )
            for pk, stage_id, status, created_at, updated_at in applications.values_list(
                "id", "current_stage_id", "status", "created_at", "updated_at"
            )
        ]
        if options.get("dry_run"):
            self.stdout.write(f"Would create {len(rows)} stage transition(s).")
            return
        StageTransition.objects.bulk_create(rows, batch_size=500)
        self.stdout.write(self.style.SUCCESS(f"Created {len(rows)} stage transition(s)."))
