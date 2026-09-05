"""Issue the monthly invoice for every company (or one), idempotently."""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from billing.invoicing import build_monthly_invoice
from billing.models import Subscription
from core.models import Company


class Command(BaseCommand):
    help = (
        "Assemble and issue one monthly invoice per company: plan fee "
        "(per-seat or flat), success fees, AI overage and ledger charges. "
        "Running it twice for the same period is a no-op."
    )

    def add_arguments(self, parser):
        parser.add_argument("--company", help="Company id or exact name")
        parser.add_argument("--year", type=int)
        parser.add_argument("--month", type=int)
        parser.add_argument(
            "--pdf", action="store_true", help="Also render each invoice PDF"
        )

    def handle(self, *args, **options):
        now = timezone.now()
        year = options.get("year") or now.year
        month = options.get("month") or now.month
        if not 1 <= int(month) <= 12:
            raise CommandError("--month must be between 1 and 12")

        companies = self._companies(options.get("company"))
        issued = skipped = 0
        for company in companies:
            invoice = build_monthly_invoice(
                company, year, month, with_pdf=options.get("pdf", False)
            )
            if invoice is None:
                skipped += 1
                continue
            issued += 1
            self.stdout.write(f"{company}: {invoice.number} ₹{invoice.total}")
        self.stdout.write(
            self.style.SUCCESS(
                f"{issued} invoice(s) for {year}-{month:02d}; {skipped} with nothing to bill."
            )
        )

    def _companies(self, selector):
        qs = Company.objects.filter(
            pk__in=Subscription.objects.values("company_id")
        ).order_by("name")
        if not selector:
            return list(qs)
        company = None
        if str(selector).isdigit():
            company = Company.objects.filter(pk=int(selector)).first()
        company = company or Company.objects.filter(name=selector).first()
        if company is None:
            raise CommandError(f"No such company: {selector}")
        return [company]
