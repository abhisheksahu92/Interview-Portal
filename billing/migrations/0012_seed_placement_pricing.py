"""Seed placement-linked pricing onto the existing Plan rows.

Phase 4 turns STARTER into a per-seat tier (₹999 per recruiter seat) and gives
every tier a success fee, an included AI allowance and an overage rate. Fresh
installs get these from ``billing.services.PLAN_SPECS``; rows seeded by earlier
migrations are updated in place here.
"""

from decimal import Decimal

from django.db import migrations

# code: (pricing_model, price_monthly_inr, price_yearly_inr, success_fee, ai_included)
PRICING = {
    "STARTER": ("SEAT", Decimal("999.00"), Decimal("9990.00"), Decimal("4999.00"), 50),
    "GROWTH": ("FLAT", Decimal("4999.00"), Decimal("49990.00"), Decimal("2999.00"), 500),
    "AGENCY": ("FLAT", Decimal("12999.00"), Decimal("129990.00"), Decimal("0.00"), 2000),
    "PRO": ("FLAT", Decimal("4999.00"), Decimal("49990.00"), Decimal("2999.00"), 500),
    "FREE": ("FLAT", Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), 0),
}
OVERAGE = Decimal("5.00")


def seed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for code, (model, monthly, yearly, fee, ai) in PRICING.items():
        plan = Plan.objects.filter(code=code).first()
        if plan is None:
            continue
        plan.pricing_model = model
        plan.price_monthly_inr = monthly
        plan.price_yearly_inr = yearly
        plan.success_fee_inr = fee
        plan.ai_included = ai
        plan.ai_overage_inr = OVERAGE
        if not plan.ai_credits_monthly:
            plan.ai_credits_monthly = ai
        plan.save(
            update_fields=[
                "pricing_model",
                "price_monthly_inr",
                "price_yearly_inr",
                "success_fee_inr",
                "ai_included",
                "ai_overage_inr",
                "ai_credits_monthly",
            ]
        )


def unseed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(code="STARTER").update(
        pricing_model="FLAT",
        price_monthly_inr=Decimal("1499.00"),
        price_yearly_inr=Decimal("14990.00"),
    )
    Plan.objects.all().update(
        success_fee_inr=Decimal("0.00"), ai_included=0, ai_overage_inr=Decimal("0.00")
    )


class Migration(migrations.Migration):
    dependencies = [("billing", "0011_placement_pricing")]

    operations = [migrations.RunPython(seed, unseed)]
