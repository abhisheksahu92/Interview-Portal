"""Turn on the phase-4 ``contracting`` and ``exchange`` feature flags.

Contracting (timesheets, client invoices, payroll) is a GROWTH+AGENCY feature;
the agency requirement exchange is AGENCY-only — any plan may still *respond*
to a requirement for free, which is enforced in the exchange app rather than by
this flag. ``billing.services.PLAN_SPECS`` carries the same values for freshly
seeded installs.
"""

from django.db import migrations

GRANTS = {"contracting": ("GROWTH", "AGENCY"), "exchange": ("AGENCY",)}


def grant(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for feature, codes in GRANTS.items():
        for plan in Plan.objects.filter(code__in=codes):
            features = dict(plan.features or {})
            if features.get(feature) is True:
                continue
            features[feature] = True
            plan.features = features
            plan.save(update_fields=["features"])


def revoke(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for feature, codes in GRANTS.items():
        for plan in Plan.objects.filter(code__in=codes):
            features = dict(plan.features or {})
            if features.pop(feature, None) is None:
                continue
            plan.features = features
            plan.save(update_fields=["features"])


class Migration(migrations.Migration):
    dependencies = [("billing", "0012_seed_placement_pricing")]

    operations = [migrations.RunPython(grant, revoke)]
