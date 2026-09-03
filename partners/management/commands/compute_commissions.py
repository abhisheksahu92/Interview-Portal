"""Record commissions for paid invoices of referred companies.

``billing.Invoice`` is built by the billing agent; this command imports it
lazily and exits cleanly when the model does not exist yet.
"""

from django.core.management.base import BaseCommand

from partners.services import record_commission


def _invoice_model():
    """The billing Invoice model, or None when billing has not shipped it."""
    try:
        from django.apps import apps

        return apps.get_model("billing", "Invoice")
    except Exception:
        return None


class Command(BaseCommand):
    help = "Scan paid billing invoices and record reseller commissions."

    def handle(self, *args, **options):
        model = _invoice_model()
        if model is None:
            self.stdout.write("billing.Invoice is not available yet — nothing to do.")
            return
        recorded = 0
        scanned = 0
        for invoice in model.objects.filter(paid_at__isnull=False).select_related("company"):
            scanned += 1
            ref = getattr(invoice, "number", None) or f"invoice-{invoice.pk}"
            amount = getattr(invoice, "amount", 0)
            if record_commission(invoice.company, amount, ref) is not None:
                recorded += 1
        self.stdout.write(
            self.style.SUCCESS(f"Scanned {scanned} paid invoices, {recorded} with commissions.")
        )
