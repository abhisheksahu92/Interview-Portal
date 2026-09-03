from decimal import Decimal

from django.db import migrations

PLANS = [
    {"code": "FREE", "name": "Free", "max_open_jobs": 1, "price_monthly": Decimal("0.00")},
    {"code": "PRO", "name": "Pro", "max_open_jobs": 25, "price_monthly": Decimal("49.00")},
]


def seed_plans(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for spec in PLANS:
        Plan.objects.update_or_create(code=spec["code"], defaults=spec)


def unseed_plans(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(code__in=[p["code"] for p in PLANS]).delete()


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]

    operations = [migrations.RunPython(seed_plans, unseed_plans)]
