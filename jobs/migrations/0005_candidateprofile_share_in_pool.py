from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0004_job_client"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidateprofile",
            name="share_in_pool",
            field=models.BooleanField(default=False),
        ),
    ]
