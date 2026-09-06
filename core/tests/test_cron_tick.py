"""The external tick endpoint: auth, cadence, and never failing the caller."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import CronState


@pytest.fixture(autouse=True)
def _token(settings):
    settings.CRON_TOKEN = "t0k3n"


@pytest.fixture(autouse=True)
def _no_real_work(monkeypatch):
    calls = {"periodic": 0}

    def fake_call_command(name, **kwargs):
        assert name == "run_periodic" and kwargs.get("skip") == ["fetch_sources"]
        calls["periodic"] += 1

    monkeypatch.setattr("core.cron.call_command", fake_call_command)
    monkeypatch.setattr(
        "sources.services.tick", lambda budget_seconds=25: {"ran": [], "backfilled": 0}
    )
    return calls


def test_missing_or_wrong_token_is_rejected(client):
    assert client.get(reverse("cron_tick")).status_code == 401
    assert client.get(reverse("cron_tick"), {"token": "nope"}).status_code == 401


def test_blank_configured_token_disables_the_endpoint(client, settings):
    settings.CRON_TOKEN = ""
    assert client.get(reverse("cron_tick"), {"token": ""}).status_code == 401


@pytest.mark.django_db
def test_first_tick_runs_maintenance_and_records_it(client, _no_real_work):
    r = client.get(reverse("cron_tick"), {"token": "t0k3n"})

    assert r.status_code == 200
    assert r.json()["maintenance"] == "ran"
    assert _no_real_work["periodic"] == 1
    assert CronState.objects.get(key="run_periodic").last_status == "ok"


@pytest.mark.django_db
def test_maintenance_runs_at_most_every_thirty_minutes(client, _no_real_work):
    CronState.objects.create(key="run_periodic", last_run_at=timezone.now() - timedelta(minutes=10))

    r = client.get(reverse("cron_tick"), {"token": "t0k3n"})

    assert r.json()["maintenance"] == "skipped"
    assert _no_real_work["periodic"] == 0


@pytest.mark.django_db
def test_header_token_is_accepted(client):
    r = client.get(reverse("cron_tick"), HTTP_X_CRON_TOKEN="t0k3n")
    assert r.status_code == 200


@pytest.mark.django_db
def test_a_failing_runner_is_recorded_not_raised(client, monkeypatch):
    def boom(name, **kwargs):
        raise RuntimeError("dunning exploded")

    monkeypatch.setattr("core.cron.call_command", boom)

    r = client.get(reverse("cron_tick"), {"token": "t0k3n"})

    assert r.status_code == 200
    assert r.json()["maintenance"] == "error"
    assert CronState.objects.get(key="run_periodic").last_status.startswith("error:")
