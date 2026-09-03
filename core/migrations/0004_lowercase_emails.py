"""Normalise existing user/invitation emails to lower case.

Collisions (two rows differing only in case) are left untouched and logged so a
human can merge them; lowering one would violate ``User.email``'s uniqueness.
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def lowercase_emails(apps, schema_editor):
    User = apps.get_model("core", "User")
    Invitation = apps.get_model("core", "Invitation")

    seen: set = set()
    for user in User.objects.exclude(email="").iterator():
        lowered = (user.email or "").strip().lower()
        if lowered == user.email:
            seen.add(lowered)
            continue
        if User.objects.filter(email=lowered).exclude(pk=user.pk).exists() or (
            lowered in seen
        ):
            logger.warning(
                "core.0004: not lowering user %s (%s) — %s already exists",
                user.pk,
                user.email,
                lowered,
            )
            continue
        seen.add(lowered)
        User.objects.filter(pk=user.pk).update(email=lowered)

    for invitation in Invitation.objects.exclude(email="").iterator():
        lowered = (invitation.email or "").strip().lower()
        if lowered != invitation.email:
            Invitation.objects.filter(pk=invitation.pk).update(email=lowered)


class Migration(migrations.Migration):
    dependencies = [("core", "0003_user_last_company")]

    operations = [
        migrations.RunPython(lowercase_emails, migrations.RunPython.noop),
    ]
