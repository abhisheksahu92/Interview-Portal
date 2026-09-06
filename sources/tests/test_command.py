"""The periodic command runs with the network mocked out."""

import pytest
from django.core.management import call_command

from sources import services
from sources.models import Lead, Source


@pytest.fixture(autouse=True)
def _no_network(monkeypatch, fixture):
    """Every adapter returns its fixture; nothing reaches the internet."""
    from sources.adapters import ADAPTERS

    payload = fixture("remotive.json")
    for adapter in ADAPTERS.values():
        monkeypatch.setattr(adapter, "fetch", lambda source: [], raising=False)
    monkeypatch.setattr(
        ADAPTERS["remotive"], "fetch", lambda source: ADAPTERS["remotive"].parse(payload)
    )
    monkeypatch.setattr(services.llm, "complete", lambda *a, **k: None)


def test_seed_created_the_catalogue(db):
    assert Source.objects.filter(slug="manual").exists()
    assert Source.objects.filter(kind=Source.ATS).count() >= 30
    assert Source.objects.count() >= 40


def test_fetch_sources_only_one(db, capsys):
    call_command("fetch_sources", "--only", "remotive")
    assert Lead.objects.count() > 0
    assert "remotive: OK" in capsys.readouterr().out


def test_fetch_sources_rejects_an_unknown_slug(db, capsys):
    call_command("fetch_sources", "--only", "nope")
    assert Lead.objects.count() == 0


def test_fetch_sources_runs_every_enabled_source(db, capsys):
    Source.objects.filter(slug="remoteok").update(enabled=False)
    call_command("fetch_sources")
    out = capsys.readouterr().out
    assert "remoteok" not in out
    assert "new lead(s)" in out
