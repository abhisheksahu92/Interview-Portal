"""Normalisation, dedupe, contact extraction, tagging and the read API."""

from datetime import timedelta

import pytest
from django.utils import timezone

from sources import services
from sources.adapters.base import RawItem
from sources.models import Lead, Source

VOCAB = ["python", "django", "react", "aws", "go"]


def make_item(**kwargs):
    base = {
        "external_id": "1",
        "title": "Senior Django Developer",
        "url": "https://example.test/jobs/1",
        "company_name": "Acme Labs",
        "snippet": "We need a Django and Postgres developer. Remote.",
    }
    return RawItem(**{**base, **kwargs})


def save(source, item):
    lead, created = services.dedupe(services.normalise(item, source))
    if created:
        lead.save()
    return lead, created


# --------------------------------------------------------------------------- #
# Contact extraction
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text,expected",
    [
        ("Mail jobs@acmelabs.dev with a note", "jobs@acmelabs.dev"),
        ("Reach Priya.Sharma+jobs@acme.co.in today", "priya.sharma+jobs@acme.co.in"),
        ("noreply@acme.com is our sender, write to hiring@acme.com", "hiring@acme.com"),
        ("contact us via the form", ""),
        ("someone@example.com only", ""),
        ("logo at cdn@images.png", ""),
    ],
)
def test_extract_contact(text, expected):
    assert services.extract_contact(text) == expected


# --------------------------------------------------------------------------- #
# Normalise and dedupe
# --------------------------------------------------------------------------- #
def test_normalise_caps_snippet_and_sets_expiry(source):
    item = make_item(snippet="x" * 2000, contact_email="")
    fields = services.normalise(item, source())
    assert len(fields["snippet"]) == 600
    assert fields["expires_at"] > fields["posted_at"]
    assert fields["content_hash"]


def test_normalise_pulls_the_contact_out_of_the_snippet(source):
    fields = services.normalise(make_item(snippet="Write to hi@acme.dev"), source())
    assert fields["contact_email"] == "hi@acme.dev"


def test_dedupe_collapses_the_same_posting(db, source):
    feed = source()
    first, created_first = save(feed, make_item())
    second, created_second = save(feed, make_item(external_id="2", url="https://other.test/2"))
    assert created_first and not created_second
    assert second.pk == first.pk
    assert Lead.objects.count() == 1


def test_dedupe_revives_a_closed_lead(db, source):
    feed = source()
    lead, _ = save(feed, make_item())
    Lead.objects.filter(pk=lead.pk).update(is_active=False)
    again, created = save(feed, make_item())
    assert not created and again.is_active


# --------------------------------------------------------------------------- #
# Skill tagging
# --------------------------------------------------------------------------- #
def test_tag_skills_uses_the_llm_answer(db, source, monkeypatch):
    monkeypatch.setattr(services.llm, "complete", lambda *a, **k: '[["python", "django"]]')
    lead = Lead(**services.normalise(make_item(), source()))
    services.tag_skills([lead], vocabulary=VOCAB)
    assert lead.skills == ["python", "django"]


def test_tag_skills_falls_back_to_keywords(db, source, monkeypatch):
    monkeypatch.setattr(services.llm, "complete", lambda *a, **k: None)
    lead = Lead(**services.normalise(make_item(), source()))
    services.tag_skills([lead], vocabulary=VOCAB)
    assert "django" in lead.skills


def test_tag_skills_falls_back_on_a_wrong_length_answer(db, source, monkeypatch):
    monkeypatch.setattr(services.llm, "complete", lambda *a, **k: "[[], [], []]")
    lead = Lead(**services.normalise(make_item(), source()))
    services.tag_skills([lead], vocabulary=VOCAB)
    assert "django" in lead.skills


def test_tag_skills_drops_invented_skills(db, source, monkeypatch):
    monkeypatch.setattr(services.llm, "complete", lambda *a, **k: '[["python", "cobol"]]')
    lead = Lead(**services.normalise(make_item(), source()))
    services.tag_skills([lead], vocabulary=VOCAB)
    assert lead.skills == ["python"]


def test_tag_skills_batches_in_twenties(db, source, monkeypatch):
    calls = []

    def fake(prompt, **kwargs):
        calls.append(prompt)
        return None

    monkeypatch.setattr(services.llm, "complete", fake)
    feed = source()
    leads = [
        Lead(**services.normalise(make_item(title=f"Django Developer {i}"), feed))
        for i in range(25)
    ]
    services.tag_skills(leads, vocabulary=VOCAB)
    assert len(calls) == 2


def test_keyword_skills_respects_word_boundaries():
    assert "go" not in services.keyword_skills("going to the office", VOCAB)
    assert "go" in services.keyword_skills("Go and Python backend", VOCAB)


def test_skill_vocabulary_includes_tenant_skills(db):
    from core.models import Company
    from jobs.models import Skill

    Skill.objects.create(company=Company.objects.create(name="Acme"), name="Snowflake")
    vocabulary = services.skill_vocabulary()
    assert "snowflake" in vocabulary and "python" in vocabulary


# --------------------------------------------------------------------------- #
# Runners
# --------------------------------------------------------------------------- #
def test_run_source_skips_a_credentialless_adapter(db, source, settings):
    settings.REDDIT_CLIENT_ID = settings.REDDIT_CLIENT_SECRET = ""
    stats = services.run_source(source(slug="reddit"))
    assert stats["status"] == Source.SKIPPED


def test_run_source_records_an_adapter_failure(db, source, monkeypatch):
    from sources.adapters import ADAPTERS

    def boom(_source):
        raise RuntimeError("upstream is down")

    monkeypatch.setattr(ADAPTERS["remotive"], "fetch", boom)
    feed = source(slug="remotive")
    stats = services.run_source(feed)
    feed.refresh_from_db()
    assert stats["status"] == Source.ERROR
    assert "upstream is down" in feed.last_error


def test_run_source_stores_leads(db, source, monkeypatch, fixture):
    from sources.adapters import ADAPTERS

    payload = fixture("remotive.json")
    monkeypatch.setattr(
        ADAPTERS["remotive"], "fetch", lambda s: ADAPTERS["remotive"].parse(payload)
    )
    monkeypatch.setattr(services.llm, "complete", lambda *a, **k: None)
    stats = services.run_source(source(slug="remotive"))
    assert stats["created"] == Lead.objects.count() > 0
    assert stats["status"] == Source.OK
    # A second run is a no-op: the same postings hash to the same rows.
    assert services.run_source(source(slug="remotive"))["created"] == 0


def test_ats_run_closes_postings_the_board_dropped(db, source, monkeypatch, fixture):
    from sources.adapters import ADAPTERS

    payload = fixture("greenhouse.json")
    feed = source(slug="greenhouse-checkr", kind=Source.ATS, adapter="greenhouse", slug_="checkr")
    feed.config = {"adapter": "greenhouse", "slug": "checkr"}
    feed.save(update_fields=["config"])
    monkeypatch.setattr(services.llm, "complete", lambda *a, **k: None)
    monkeypatch.setattr(
        ADAPTERS["greenhouse"],
        "fetch",
        lambda s: ADAPTERS["greenhouse"].parse(payload, board="checkr"),
    )
    services.run_source(feed)
    assert Lead.objects.live().count() > 1

    trimmed = {"jobs": payload["jobs"][:1]}
    monkeypatch.setattr(
        ADAPTERS["greenhouse"],
        "fetch",
        lambda s: ADAPTERS["greenhouse"].parse(trimmed, board="checkr"),
    )
    services.run_source(feed)
    assert Lead.objects.live().count() == 1


def test_expire_stale(db, source):
    feed = source()
    lead, _ = save(feed, make_item())
    Lead.objects.filter(pk=lead.pk).update(posted_at=timezone.now() - timedelta(days=60))
    assert services.expire_stale() == 1
    lead.refresh_from_db()
    assert not lead.is_active


# --------------------------------------------------------------------------- #
# Read API
# --------------------------------------------------------------------------- #
@pytest.fixture
def leads(db, source):
    feed = source()
    rows = []
    for index, (title, skills, kind, remote) in enumerate(
        [
            ("Django Developer", ["python", "django"], Lead.JOB, True),
            ("React Engineer", ["react"], Lead.JOB, False),
            ("Scrape a site", ["python"], Lead.FREELANCE, True),
        ]
    ):
        lead, _ = save(feed, make_item(title=title, external_id=str(index), snippet=title))
        lead.skills = skills
        lead.kind = kind
        lead.remote = remote
        lead.posted_at = timezone.now() - timedelta(days=index)
        lead.save()
        rows.append(lead)
    return rows


def test_search_leads_filters(leads):
    assert [lead.title for lead in services.search_leads(query="django")] == ["Django Developer"]
    assert services.search_leads(kind=Lead.FREELANCE).count() == 1
    assert services.search_leads(remote=True).count() == 2
    assert services.search_leads(skills=["react"]).count() == 1


def test_search_leads_hides_closed_leads(leads):
    leads[0].is_active = False
    leads[0].save(update_fields=["is_active"])
    assert services.search_leads(query="django").count() == 0


def test_leads_for_profile_ranks_by_overlap(leads):
    class Profile:
        skills = ["Python", "Django"]

    ranked = services.leads_for_profile(Profile(), limit=5)
    assert ranked[0].title == "Django Developer"


def test_leads_for_profile_without_skills_still_returns_something(leads):
    class Profile:
        skills = []

    assert len(services.leads_for_profile(Profile(), limit=5)) == 3


def test_match_score():
    assert services.match_score(["python"], ["python"]) == 1.0
    assert services.match_score(["python"], ["go"]) == 0.0
    assert services.match_score([], ["go"]) == 0.0


@pytest.mark.django_db
def test_expire_stale_leaves_ats_leads_alone(db):
    """A board still listing a job is authoritative, however old the post date."""
    from datetime import timedelta

    from django.utils import timezone

    from sources import services
    from sources.models import Lead, Source

    old = timezone.now() - timedelta(days=200)
    ats = Source.objects.create(slug="gh-x", name="GH", kind=Source.ATS, config={"slug": "x"})
    api = Source.objects.create(slug="api-x", name="API", kind=Source.API)
    keep = Lead.objects.create(
        source=ats, external_id="1", title="Old but listed", content_hash="h1", posted_at=old
    )
    drop = Lead.objects.create(
        source=api, external_id="2", title="Old feed item", content_hash="h2", posted_at=old
    )

    services.expire_stale()

    keep.refresh_from_db()
    drop.refresh_from_db()
    assert keep.is_active is True
    assert drop.is_active is False


@pytest.mark.django_db
def test_run_all_accepts_a_list_of_slugs(monkeypatch):
    from sources import services
    from sources.models import Source

    for slug in ("a", "b", "c"):
        Source.objects.create(slug=slug, name=slug, kind=Source.API)
    ran = []
    monkeypatch.setattr(services, "run_source", lambda s: ran.append(s.slug))

    services.run_all(only=["a", "c"])

    assert sorted(ran) == ["a", "c"]


@pytest.mark.django_db
def test_dedupe_matches_on_source_external_id_when_text_changes():
    """A retitled posting is the same lead, not a duplicate."""
    from django.utils import timezone

    from sources import services
    from sources.models import Lead, Source, content_hash

    src = Source.objects.create(slug="s", name="S", kind=Source.API)
    now = timezone.now()
    base = dict(
        source=src,
        external_id="42",
        company_name="Acme",
        url="https://x/42",
        snippet="Django dev wanted",
        fetched_at=now,
        expires_at=None,
        posted_at=now,
    )
    first = dict(
        base,
        title="Acme | Django dev",
        content_hash=content_hash("Acme | Django dev", "Acme", "Django dev wanted"),
    )
    lead, created = services.dedupe(first)
    lead.save()
    assert created

    second = dict(
        base,
        title="Acme | Senior Django dev",
        content_hash=content_hash("Acme | Senior Django dev", "Acme", "Django dev wanted"),
    )
    same, created = services.dedupe(second)

    assert created is False and same.pk == lead.pk
    assert Lead.objects.count() == 1
    same.refresh_from_db()
    assert same.title == "Acme | Senior Django dev"
    assert same.content_hash == second["content_hash"]


@pytest.mark.django_db
def test_rerun_of_a_source_uses_a_bounded_number_of_queries(
    django_assert_max_num_queries, monkeypatch
):
    """Re-running a 60-item feed must not cost a SELECT per posting.

    The first live run against a remote database spent four minutes on a
    250-item feed doing exactly that; the runner now prefetches once.
    """
    from sources import services
    from sources.adapters.base import Adapter, RawItem
    from sources.models import Source

    class Sixty(Adapter):
        slug = "sixty"

        def fetch(self, source):
            for i in range(60):
                yield RawItem(
                    external_id=str(i),
                    kind="JOB",
                    title=f"Role {i}",
                    url=f"https://x/{i}",
                    company_name="Acme",
                    snippet=f"Posting {i}",
                )

    monkeypatch.setitem(services.ADAPTERS, "sixty", Sixty())
    monkeypatch.setattr(services, "tag_skills", lambda leads, vocabulary=None: leads)
    src = Source.objects.create(slug="sixty", name="Sixty", kind=Source.API)

    services.run_source(src)  # first run creates 60 rows
    with django_assert_max_num_queries(12):
        stats = services.run_source(src)  # second run only refreshes them

    assert stats["created"] == 0 and stats["seen"] == 60
