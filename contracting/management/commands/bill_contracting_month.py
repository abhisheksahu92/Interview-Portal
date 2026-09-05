"""Raise client invoices from approved timesheets for every tenant.

Month-end automation for operators who would rather cron this than click it:
``manage.py bill_contracting_month [--month YYYY-MM] [--company <id>] [--send]``.
Companies whose plan lacks the ``contracting`` flag are skipped, and the run is
idempotent — an already-invoiced timesheet is never picked up twice.
"""

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from billing.entitlements import has_feature
from contracting import invoicing
from core.models import Company


class Command(BaseCommand):
    help = "Invoice approved contractor timesheets for a month."

    def add_arguments(self, parser):
        parser.add_argument("--month", help="Billing month as YYYY-MM (default: last month).")
        parser.add_argument("--company", type=int, help="Limit the run to one company id.")
        parser.add_argument(
            "--send", action="store_true", help="Email each invoice after raising it."
        )

    def handle(self, *args, **options):
        month = self._month(options.get("month"))
        companies = Company.objects.all()
        if options.get("company"):
            companies = companies.filter(pk=options["company"])
        total = 0
        for company in companies:
            if not has_feature(company, "contracting"):
                continue
            invoices = invoicing.generate_client_invoices(company, month)
            for invoice in invoices:
                if options.get("send"):
                    invoicing.send_invoice(invoice)
            invoicing.refresh_overdue(company)
            total += len(invoices)
            if invoices:
                self.stdout.write(f"{company.name}: {len(invoices)} invoice(s)")
        self.stdout.write(self.style.SUCCESS(f"{total} invoice(s) raised for {month:%B %Y}."))
        return None

    def _month(self, raw):
        if not raw:
            today = timezone.localdate().replace(day=1)
            from datetime import timedelta

            return (today - timedelta(days=1)).replace(day=1)
        try:
            return datetime.strptime(raw, "%Y-%m").date().replace(day=1)
        except ValueError as exc:
            raise CommandError("--month must look like 2026-04.") from exc
