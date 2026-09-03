"""Turn on the ``ai_extraction`` feature flag for GROWTH, AGENCY and legacy PRO.

``talent.services.ai_enabled`` gates AI resume extraction on this flag, but the
flag only becomes real once ``billing.entitlements.FEATURES`` knows it *and* the
seeded plans carry it. Existing rows were seeded before the flag existed, so
they need the value merged in without disturbing their other features.
"""

from django.db import migrations

FEATURE = "ai_extraction"
GRANTED_TO = ("GROWTH", "AGENCY", "PRO")


def grant(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for plan in Plan.objects.filter(code__in=GRANTED_TO):
        features = dict(plan.features or {})
        if features.get(FEATURE) is True:
            continue
        features[FEATURE] = True
        plan.features = features
        plan.save(update_fields=["features"])


def revoke(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for plan in Plan.objects.filter(code__in=GRANTED_TO):
        features = dict(plan.features or {})
        if features.pop(FEATURE, None) is None:
            continue
        plan.features = features
        plan.save(update_fields=["features"])


class Migration(migrations.Migration):
    dependencies = [("billing", "0007_trial_for_existing_companies")]

    operations = [migrations.RunPython(grant, revoke)]
