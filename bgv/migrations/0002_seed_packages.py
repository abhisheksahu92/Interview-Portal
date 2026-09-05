"""Seed the three resale packages.

Prices and vendor costs are the Phase 4 pinned numbers: Basic ₹799 (cost ₹499),
Standard ₹1,499 (cost ₹999), Comprehensive ₹2,999 (cost ₹1,999) — a 37-38%
gross margin on every tier. Existing rows are left alone: an operator who has
re-priced a package in the admin must not have that reverted by a deploy.
"""

from decimal import Decimal

from django.db import migrations

PACKAGES = [
    {
        "code": "BASIC",
        "name": "Basic",
        "description": "Identity and address confirmation — the fastest sanity check.",
        "provider_cost_inr": Decimal("499.00"),
        "price_inr": Decimal("799.00"),
        "checks": ["identity", "address"],
        "turnaround_days": 2,
    },
    {
        "code": "STANDARD",
        "name": "Standard",
        "description": "Adds employment and education history to the basic checks.",
        "provider_cost_inr": Decimal("999.00"),
        "price_inr": Decimal("1499.00"),
        "checks": ["identity", "address", "employment", "education"],
        "turnaround_days": 5,
    },
    {
        "code": "COMPREHENSIVE",
        "name": "Comprehensive",
        "description": "Every check including a criminal record search. Client-ready.",
        "provider_cost_inr": Decimal("1999.00"),
        "price_inr": Decimal("2999.00"),
        "checks": ["identity", "address", "employment", "education", "criminal"],
        "turnaround_days": 7,
    },
]


def seed(apps, schema_editor):
    CheckPackage = apps.get_model("bgv", "CheckPackage")
    for spec in PACKAGES:
        CheckPackage.objects.get_or_create(code=spec["code"], defaults=spec)


def unseed(apps, schema_editor):
    CheckPackage = apps.get_model("bgv", "CheckPackage")
    CheckPackage.objects.filter(code__in=[spec["code"] for spec in PACKAGES]).delete()


class Migration(migrations.Migration):
    dependencies = [("bgv", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
