"""Advance every open verification order by polling the provider.

``manage.py bgv_poll [--company <id>] [--order <id>]``

With no vendor configured this drives the :class:`bgv.gateway.MockProvider`,
which moves an order one step per run (SUBMITTED → IN_PROGRESS → COMPLETED with
every check CLEAR) — enough to demo the whole flow, including the PDF report,
without a vendor account. Wire it into ``run_periodic`` alongside the other
maintenance commands.
"""

from django.core.management.base import BaseCommand

from bgv import services
from bgv.models import VerificationOrder


class Command(BaseCommand):
    help = "Poll the BGV provider for open verification orders."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Limit the run to one company id.")
        parser.add_argument("--order", type=int, help="Poll a single order id.")

    def handle(self, *args, **options):
        orders = services.pollable_orders()
        if options.get("company"):
            orders = orders.filter(company_id=options["company"])
        if options.get("order"):
            orders = orders.filter(pk=options["order"])
        moved = 0
        for order in list(orders.select_related("company", "candidate__user", "package")):
            before = order.status
            services.poll_order(order)
            if order.status != before:
                moved += 1
                self.stdout.write(f"#{order.pk}: {before} → {order.status}")
        completed = VerificationOrder.objects.filter(status=VerificationOrder.COMPLETED).count()
        self.stdout.write(
            self.style.SUCCESS(f"{moved} order(s) advanced; {completed} completed in total.")
        )
        return None
