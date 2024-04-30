# Generated by Django 5.0.4 on 2024-04-30 17:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('candidate', '0005_candidatequestionmodel_skill'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='candidate',
            name='score',
        ),
        migrations.AddField(
            model_name='candidate',
            name='assessment_data',
            field=models.JSONField(null=True, verbose_name='Score'),
        ),
        migrations.AddField(
            model_name='candidate',
            name='assessment_result',
            field=models.BooleanField(default=False),
        ),
        migrations.DeleteModel(
            name='CandidateResponse',
        ),
    ]
