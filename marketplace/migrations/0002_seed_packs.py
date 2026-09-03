"""Seed the sample question packs so a fresh install has a populated storefront."""

from django.db import migrations


def seed(apps, schema_editor):
    from marketplace.management.commands.seed_packs import PACKS, build_questions

    QuestionPack = apps.get_model("marketplace", "QuestionPack")
    for spec in PACKS:
        QuestionPack.objects.update_or_create(
            slug=spec["slug"],
            defaults={
                "title": spec["title"],
                "skill_name": spec["skill_name"],
                "description": spec["description"],
                "price_inr": spec["price_inr"],
                "author": spec["author"],
                "questions": build_questions(spec["rows"]),
                "published": True,
            },
        )


def unseed(apps, schema_editor):
    from marketplace.management.commands.seed_packs import PACKS

    QuestionPack = apps.get_model("marketplace", "QuestionPack")
    QuestionPack.objects.filter(slug__in=[s["slug"] for s in PACKS]).delete()


class Migration(migrations.Migration):

    dependencies = [("marketplace", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
