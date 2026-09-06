"""Seed the source catalogue.

Every slug here was called live while this was written; boards that 404'd or
returned an empty list were dropped rather than shipped as permanently-failing
rows. Existing rows are left untouched — an operator who disabled a noisy feed
must not have that undone by a deploy.

ATS rows all point at one of four vendor adapters via ``config["adapter"]`` and
differ only by ``config["slug"]``, which is the company's public board name.
"""

from django.db import migrations

PUBLIC = [
    ("hn", "Hacker News hiring threads", "API"),
    ("remotive", "Remotive", "API"),
    ("arbeitnow", "Arbeitnow", "API"),
    ("remoteok", "RemoteOK", "API"),
    ("jobicy", "Jobicy", "API"),
    ("himalayas", "Himalayas", "API"),
    ("wwr_rss", "We Work Remotely", "RSS"),
    ("freelancer", "Freelancer.com", "API"),
    ("reddit", "Reddit hiring subreddits", "API"),
    ("adzuna", "Adzuna (India)", "API"),
    ("manual", "Pasted by a person", "API"),
]

# Verified 200-with-jobs on 2026-09-06.
GREENHOUSE = [
    "gitlab", "stripe", "airbnb", "coinbase", "robinhood", "reddit", "figma",
    "databricks", "cloudflare", "dropbox", "asana", "instacart", "gusto", "brex",
    "checkr", "samsara", "affirm", "flexport", "lyft", "pinterest", "twilio",
    "zscaler", "mongodb", "elastic", "postman", "groww",
]
LEVER = ["spotify", "binance", "tala", "nium"]
ASHBY = ["ramp", "openai", "notion", "linear", "vanta", "cohere", "posthog", "replit", "modal"]
SMARTRECRUITERS = ["BoschGroup"]

# Shipped switched off, with the reason. WeWorkRemotely's robots.txt disallows
# its RSS for non-browser agents and we honour that; flip it on if that changes.
DISABLED = {"wwr_rss": "robots.txt disallows the RSS feed"}


def ats_rows():
    for adapter, boards in (
        ("greenhouse", GREENHOUSE),
        ("lever", LEVER),
        ("ashby", ASHBY),
        ("smartrecruiters", SMARTRECRUITERS),
    ):
        for board in boards:
            yield f"{adapter}-{board.lower()}", f"{board} ({adapter.title()})", adapter, board


def seed(apps, schema_editor):
    Source = apps.get_model("sources", "Source")
    for slug, name, kind in PUBLIC:
        Source.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "kind": kind,
                "enabled": slug not in DISABLED,
                "last_error": DISABLED.get(slug, ""),
            },
        )
    for slug, name, adapter, board in ats_rows():
        Source.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "kind": "ATS",
                "config": {"adapter": adapter, "slug": board},
            },
        )


def unseed(apps, schema_editor):
    Source = apps.get_model("sources", "Source")
    slugs = [row[0] for row in PUBLIC] + [row[0] for row in ats_rows()]
    Source.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):
    dependencies = [("sources", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
