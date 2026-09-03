"""Give companies that never had a trial their 14 days (idempotent)."""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def start_trials(apps, schema_editor):
    Subscription = apps.get_model("billing", "Subscription")
    now = timezone.now()
    Subscription.objects.filter(
        trial_ends_at__isnull=True, plan__code="FREE", status="ACTIVE"
    ).update(status="TRIALING", trial_ends_at=now + timedelta(days=14))


def stop_trials(apps, schema_editor):
    Subscription = apps.get_model("billing", "Subscription")
    Subscription.objects.filter(status="TRIALING").update(
        status="ACTIVE", trial_ends_at=None
    )


class Migration(migrations.Migration):
    dependencies = [("billing", "0006_seed_tiers")]

    operations = [migrations.RunPython(start_trials, stop_trials)]
