"""Turn on the ``bgv`` feature flag for GROWTH and AGENCY.

Background verification is resold at a margin, so it is a paid-tier feature;
``billing.services.PLAN_SPECS`` carries the same values for freshly seeded
installs.
"""

from django.db import migrations

FEATURE = "bgv"
CODES = ("GROWTH", "AGENCY")


def grant(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for plan in Plan.objects.filter(code__in=CODES):
        features = dict(plan.features or {})
        if features.get(FEATURE) is True:
            continue
        features[FEATURE] = True
        plan.features = features
        plan.save(update_fields=["features"])


def revoke(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for plan in Plan.objects.filter(code__in=CODES):
        features = dict(plan.features or {})
        if features.pop(FEATURE, None) is None:
            continue
        plan.features = features
        plan.save(update_fields=["features"])


class Migration(migrations.Migration):
    dependencies = [("billing", "0013_contracting_exchange_features")]

    operations = [migrations.RunPython(grant, revoke)]
