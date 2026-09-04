"""Turn on the ``integrations`` feature flag for AGENCY.

The integrations tier (outbound webhooks, HRMS/BGV connectors, per-company API
tokens and the phase-3 REST endpoints) is the top-tier differentiator, so AGENCY
alone gets it. ``billing.services.PLAN_SPECS`` carries the flag for freshly
seeded installs; existing Plan rows were seeded before the flag existed and
need the value merged into their JSON without disturbing the other flags.

Legacy PRO is deliberately excluded: ``billing.services`` maps PRO onto the
GROWTH feature set, and GROWTH does not include this tier.
"""

from django.db import migrations

FEATURE = "integrations"
GRANTED_TO = ("AGENCY",)


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
    dependencies = [("billing", "0009_invoicecounter_processedwebhookevent")]

    operations = [migrations.RunPython(grant, revoke)]
