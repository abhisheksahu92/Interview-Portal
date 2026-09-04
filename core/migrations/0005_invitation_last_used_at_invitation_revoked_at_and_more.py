"""Adopt core.tokens.TokenMixin on Invitation.

Additive only: existing ``token`` / ``expires_at`` values are untouched
(``token`` merely gains a default and ``expires_at`` becomes nullable so the
shared mixin definition can be reused; Invitation.save() still fills it in).
``revoked_at`` and ``last_used_at`` are new and start out NULL.
"""


import core.tokens
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_lowercase_emails'),
    ]

    operations = [
        migrations.AddField(
            model_name='invitation',
            name='last_used_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='invitation',
            name='revoked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='invitation',
            name='expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='invitation',
            name='token',
            field=models.CharField(default=core.tokens.generate_token, max_length=100, unique=True),
        ),
    ]
