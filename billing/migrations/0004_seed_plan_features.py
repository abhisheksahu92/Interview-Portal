from django.db import migrations

from billing.entitlements import FEATURES

PRO_FEATURES = dict.fromkeys(FEATURES, True)


def seed_features(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(code="FREE").update(features={})
    Plan.objects.filter(code="PRO").update(features=PRO_FEATURES)


def unseed_features(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.all().update(features={})


class Migration(migrations.Migration):
    dependencies = [("billing", "0003_plan_features")]

    operations = [migrations.RunPython(seed_features, unseed_features)]
