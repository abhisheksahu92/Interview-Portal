"""Seed the STARTER/GROWTH/AGENCY tiers and re-map legacy PRO features."""

from django.db import migrations

from billing.services import PLAN_SPECS

CODES = ("FREE", "STARTER", "GROWTH", "AGENCY")


def _defaults(apps, code):
    """PLAN_SPECS trimmed to the fields this migration's Plan actually has.

    ``PLAN_SPECS`` is the live spec and grows over time (phase 4 added
    ``pricing_model``, ``success_fee_inr``, …); the historical model here does
    not have those columns yet, so unknown keys are dropped and later data
    migrations fill them in.
    """
    Plan = apps.get_model("billing", "Plan")
    known = {field.name for field in Plan._meta.get_fields()}
    return {k: v for k, v in PLAN_SPECS[code].items() if k in known}


def seed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for code in CODES:
        Plan.objects.update_or_create(code=code, defaults=_defaults(apps, code))
    # Legacy PRO subscribers keep their row but get the GROWTH feature set.
    Plan.objects.filter(code="PRO").update(
        name="Pro (legacy)",
        max_seats=PLAN_SPECS["GROWTH"]["max_seats"],
        ai_credits_monthly=PLAN_SPECS["GROWTH"]["ai_credits_monthly"],
        price_monthly_inr=PLAN_SPECS["GROWTH"]["price_monthly_inr"],
        price_yearly_inr=PLAN_SPECS["GROWTH"]["price_yearly_inr"],
        features=dict(PLAN_SPECS["GROWTH"]["features"]),
    )


def unseed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(code__in=("STARTER", "GROWTH", "AGENCY")).delete()


class Migration(migrations.Migration):
    dependencies = [("billing", "0005_alter_plan_options_plan_ai_credits_monthly_and_more")]

    operations = [migrations.RunPython(seed, unseed)]
