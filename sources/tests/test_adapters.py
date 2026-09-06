"""Every adapter parses its recorded payload into sane RawItems."""

from datetime import UTC

import pytest

from sources.adapters import ADAPTERS
from sources.adapters.hn import pick_threads
from sources.models import Source

# (adapter slug, fixture, parse kwargs) - one row per shipped adapter.
CASES = [
    ("remotive", "remotive.json", {}),
    ("arbeitnow", "arbeitnow.json", {}),
    ("remoteok", "remoteok.json", {}),
    ("jobicy", "jobicy.json", {}),
    ("himalayas", "himalayas.json", {}),
    ("wwr_rss", "wwr.xml", {}),
    ("freelancer", "freelancer.json", {}),
    ("greenhouse", "greenhouse.json", {"board": "checkr"}),
    ("lever", "lever.json", {"board": "leverdemo"}),
    ("ashby", "ashby.json", {"board": "posthog"}),
    ("smartrecruiters", "smartrecruiters.json", {"board": "BoschGroup"}),
    ("reddit", "reddit.json", {}),
    ("adzuna", "adzuna.json", {}),
    ("hn", "hn_comments.json", {}),
]


@pytest.mark.parametrize("slug,name,kwargs", CASES)
def test_adapter_parses_fixture(fixture, slug, name, kwargs):
    items = list(ADAPTERS[slug].parse(fixture(name), **kwargs))
    assert items, f"{slug} parsed nothing"
    for item in items:
        assert item.title and item.url.startswith("http")
        assert len(item.snippet) <= 600
        assert item.kind in {"JOB", "FREELANCE", "GIG"}


def test_remoteok_skips_the_legal_row(fixture):
    payload = fixture("remoteok.json")
    assert "legal" in payload[0]
    items = list(ADAPTERS["remoteok"].parse(payload))
    assert len(items) == len(payload) - 1
    assert all("remoteok.com" in item.url.lower() for item in items)


def test_freelancer_is_freelance_with_a_budget(fixture):
    items = list(ADAPTERS["freelancer"].parse(fixture("freelancer.json")))
    assert all(item.kind == "FREELANCE" for item in items)
    assert any(item.budget_text and item.currency for item in items)


def test_hn_picks_both_monthly_threads(fixture):
    """With the clock pinned to when the fixture was recorded, both threads qualify.

    Against today's clock only the hiring thread survives the recency cutoff,
    which is the behaviour ``test_hn_ignores_threads_older_than_the_cutoff`` pins.
    """
    from datetime import datetime

    picked = pick_threads(fixture("hn_stories.json"), now=datetime(2025, 10, 20, tzinfo=UTC))
    assert set(picked) == {"JOB", "FREELANCE"}


def test_hn_keeps_only_top_level_comments(fixture):
    payload = fixture("hn_comments.json")
    payload["hits"].append({**payload["hits"][0], "objectID": "x1", "parent_id": 999999999})
    items = list(ADAPTERS["hn"].parse(payload, kind="JOB"))
    assert "x1" not in {item.external_id for item in items}


def test_reddit_drops_people_offering_themselves(fixture):
    items = list(ADAPTERS["reddit"].parse(fixture("reddit.json")))
    titles = " ".join(item.title.lower() for item in items)
    assert "[for hire]" not in titles and "[task]" not in titles


def test_manual_adapter_never_fetches(db):
    source = Source.objects.create(slug="manual-test", name="Manual", kind=Source.API)
    assert list(ADAPTERS["manual"].fetch(source)) == []


@pytest.mark.parametrize("slug", ["reddit", "adzuna"])
def test_credentialled_adapters_are_unavailable_without_keys(settings, slug):
    settings.REDDIT_CLIENT_ID = settings.REDDIT_CLIENT_SECRET = ""
    settings.ADZUNA_APP_ID = settings.ADZUNA_APP_KEY = ""
    assert ADAPTERS[slug].available() is False


def test_hn_ignores_threads_older_than_the_cutoff():
    from datetime import datetime

    from sources.adapters.hn import pick_threads

    stories = {
        "hits": [
            {
                "objectID": "1",
                "title": "Ask HN: Who is hiring? (September 2026)",
                "created_at": "2026-09-01T15:00:00Z",
            },
            {
                "objectID": "2",
                "title": "Ask HN: Freelancer? Seeking freelancer? (October 2025)",
                "created_at": "2025-10-01T15:00:00Z",
            },
        ]
    }
    picked = pick_threads(stories, now=datetime(2026, 9, 6, tzinfo=UTC))

    assert picked == {"JOB": "1"}


def test_hn_drops_freelancers_advertising_themselves():
    """'SEEKING WORK' posts are supply; a seeker must never be mailed as a lead."""
    from sources.adapters.hn import HackerNewsAdapter

    payload = {
        "hits": [
            {
                "objectID": "10",
                "story_id": 5,
                "parent_id": 5,
                "created_at": "2026-09-02T10:00:00Z",
                "comment_text": "SEEKING WORK | Remote | Python dev, email me@example.com",
            },
            {
                "objectID": "11",
                "story_id": 5,
                "parent_id": 5,
                "created_at": "2026-09-02T10:00:00Z",
                "comment_text": "SEEKING FREELANCER | Remote | Need a Django contractor, hr@acme.co",
            },
        ]
    }
    items = list(HackerNewsAdapter().parse(payload, kind="FREELANCE"))

    assert [i.external_id for i in items] == ["11"]


def test_hn_fetch_paginates_comment_pages(monkeypatch):
    from sources.adapters import hn

    calls = []

    def fake_get_json(url):
        calls.append(url)
        if "search_by_date" in url:
            return {
                "hits": [
                    {"objectID": "5", "title": "Ask HN: Who is hiring? (Now)", "created_at": None}
                ]
            }
        page = int(url.rsplit("page=", 1)[1])
        return {
            "nbPages": 3,
            "hits": [
                {
                    "objectID": f"c{page}",
                    "story_id": 5,
                    "parent_id": 5,
                    "comment_text": f"Co {page} | Remote | role",
                    "created_at": None,
                }
            ],
        }

    monkeypatch.setattr(hn, "get_json", fake_get_json)
    items = list(hn.HackerNewsAdapter().fetch(source=None))

    assert [i.external_id for i in items] == ["c0", "c1", "c2"]
    assert sum("page=" in c for c in calls) == 3


def test_hn_headline_is_the_first_line_not_the_first_sentence():
    from sources.adapters.hn import HackerNewsAdapter

    payload = {
        "hits": [
            {
                "objectID": "1",
                "story_id": 5,
                "parent_id": 5,
                "created_at": None,
                "comment_text": "VLM Run (https://vlm.run) | ML Engineer | Remote<p>We build vision models.",
            }
        ]
    }
    item = next(HackerNewsAdapter().parse(payload))

    assert item.title == "VLM Run (https://vlm.run) | ML Engineer | Remote"
    assert item.company_name == "VLM Run (https://vlm.run)"
