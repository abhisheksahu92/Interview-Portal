from unittest.mock import patch

import pytest
from django.db import connection

from jobs.models import Skill
from talent import services
from talent.models import TalentProfile


@pytest.fixture
def pool(company, other_company, python_skill):
    react = Skill.objects.create(company=company, name="React")
    asha, _ = services.upsert_profile(
        company,
        email="asha@example.test",
        name="Asha Rao",
        headline="Senior Django Developer",
        experience_years=8,
        resume_text="Built payment services with Django and Celery.",
        tags="shortlist, senior",
        source=TalentProfile.IMPORT,
    )
    asha.skills.set([python_skill, react])
    ben, _ = services.upsert_profile(
        company,
        email="ben@example.test",
        name="Ben Iyer",
        headline="Frontend Engineer",
        experience_years=3,
        resume_text="React and TypeScript single page apps.",
        source=TalentProfile.MANUAL,
    )
    ben.skills.set([react])
    services.upsert_profile(other_company, email="mallory@globex.test", name="Mallory")
    return {"asha": asha, "ben": ben}


@pytest.mark.django_db
def test_search_uses_the_icontains_fallback_on_sqlite(company, pool):
    assert connection.vendor == "sqlite"

    results = services.search_profiles(company, "celery")

    assert [p.email for p in results] == ["asha@example.test"]


@pytest.mark.django_db
def test_search_matches_name_email_headline_and_tags(company, pool):
    assert [p.email for p in services.search_profiles(company, "Ben")] == ["ben@example.test"]
    assert [p.email for p in services.search_profiles(company, "asha@example")] == [
        "asha@example.test"
    ]
    assert [p.email for p in services.search_profiles(company, "Frontend")] == [
        "ben@example.test"
    ]
    assert [p.email for p in services.search_profiles(company, "shortlist")] == [
        "asha@example.test"
    ]


@pytest.mark.django_db
def test_search_is_company_isolated(company, other_company, pool):
    assert services.search_profiles(company, "Mallory").count() == 0
    assert services.search_profiles(other_company, "Asha").count() == 0
    assert services.search_profiles(other_company).count() == 1
    assert services.search_profiles(None).count() == 0


@pytest.mark.django_db
def test_postgres_branch_falls_back_when_search_vector_is_unavailable(company, pool, monkeypatch):
    """On Postgres we annotate a SearchVector; a failure degrades, never 500s."""
    monkeypatch.setattr(connection, "vendor", "postgresql", raising=False)
    with patch(
        "django.contrib.postgres.search.SearchVector", side_effect=RuntimeError("no pg")
    ):
        results = list(services.search_profiles(company, "celery"))

    assert [p.email for p in results] == ["asha@example.test"]


@pytest.mark.django_db
def test_filter_by_any_and_all_skills(company, pool, python_skill):
    react = Skill.objects.get(company=company, name="React")

    any_match = services.search_profiles(company, skills=[python_skill.pk, react.pk])
    all_match = services.search_profiles(
        company, skills=[python_skill.pk, react.pk], match_all=True
    )

    assert {p.email for p in any_match} == {"asha@example.test", "ben@example.test"}
    assert [p.email for p in all_match] == ["asha@example.test"]


@pytest.mark.django_db
def test_filter_by_experience_range_tags_and_source(company, pool):
    assert [p.email for p in services.search_profiles(company, min_experience=5)] == [
        "asha@example.test"
    ]
    assert [p.email for p in services.search_profiles(company, max_experience=4)] == [
        "ben@example.test"
    ]
    assert [p.email for p in services.search_profiles(company, tags="senior")] == [
        "asha@example.test"
    ]
    assert [
        p.email for p in services.search_profiles(company, source=TalentProfile.MANUAL)
    ] == ["ben@example.test"]


@pytest.mark.django_db
def test_ordering_options(company, pool):
    by_name = [p.name for p in services.search_profiles(company, ordering="name")]
    by_experience = [p.name for p in services.search_profiles(company, ordering="experience")]

    assert by_name == ["Asha Rao", "Ben Iyer"]
    assert by_experience == ["Asha Rao", "Ben Iyer"]
