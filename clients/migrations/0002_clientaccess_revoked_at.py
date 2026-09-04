"""Adopt core.tokens.TokenMixin on ClientAccess.

Purely additive on the data side: the ``revoked`` boolean is copied into the
new ``revoked_at`` timestamp (backdated to ``created_at``, the best information
we have) before the column goes away. Tokens and expiries are untouched — the
token column only widens from 64 to 100 characters.
"""

import core.tokens
from django.db import migrations, models


def revoked_bool_to_timestamp(apps, schema_editor):
    ClientAccess = apps.get_model("clients", "ClientAccess")
    ClientAccess.objects.filter(revoked=True).update(revoked_at=models.F("created_at"))


def revoked_timestamp_to_bool(apps, schema_editor):
    ClientAccess = apps.get_model("clients", "ClientAccess")
    ClientAccess.objects.filter(revoked_at__isnull=False).update(revoked=True)


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientaccess",
            name="revoked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="clientaccess",
            name="token",
            field=models.CharField(
                default=core.tokens.generate_token, max_length=100, unique=True
            ),
        ),
        migrations.RunPython(revoked_bool_to_timestamp, revoked_timestamp_to_bool),
        migrations.RemoveField(
            model_name="clientaccess",
            name="revoked",
        ),
    ]
