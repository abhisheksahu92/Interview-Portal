"""``run_periodic`` runs every maintenance job in order and survives failures."""

from io import StringIO

import pytest
from django.core.management import call_command

from core.management.commands.run_periodic import PERIODIC_COMMANDS, available_commands

pytestmark = pytest.mark.django_db


def test_every_listed_command_exists_in_this_install():
    assert available_commands() == PERIODIC_COMMANDS


def test_list_prints_the_commands_in_order():
    out = StringIO()
    call_command("run_periodic", "--list", stdout=out)
    assert out.getvalue().split() == PERIODIC_COMMANDS


def test_all_commands_run_and_report_ok():
    out = StringIO()
    call_command("run_periodic", stdout=out)
    output = out.getvalue()
    for name in PERIODIC_COMMANDS:
        assert f"{name}: ok" in output
    assert f"Ran {len(PERIODIC_COMMANDS)} periodic command(s), 0 failed." in output


def test_commands_run_in_the_declared_order(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "core.management.commands.run_periodic.call_command",
        lambda name, *a, **kw: calls.append(name),
    )
    call_command("run_periodic", stdout=StringIO())
    assert calls == PERIODIC_COMMANDS


def test_a_failing_command_is_logged_and_the_rest_still_run(monkeypatch):
    calls = []

    def flaky(name, *args, **kwargs):
        calls.append(name)
        if name == "run_dunning":
            raise RuntimeError("boom")

    monkeypatch.setattr("core.management.commands.run_periodic.call_command", flaky)
    out, err = StringIO(), StringIO()
    call_command("run_periodic", stdout=out, stderr=err)
    assert calls == PERIODIC_COMMANDS  # nothing was skipped
    assert "run_dunning: FAILED (boom)" in err.getvalue()
    assert "1 failed" in err.getvalue()


def test_only_and_skip_narrow_the_run(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "core.management.commands.run_periodic.call_command",
        lambda name, *a, **kw: calls.append(name),
    )
    call_command(
        "run_periodic", only=["expire_trials", "run_dunning"], stdout=StringIO()
    )
    assert calls == ["expire_trials", "run_dunning"]

    calls.clear()
    call_command("run_periodic", skip=["expire_trials"], stdout=StringIO())
    assert "expire_trials" not in calls
    assert len(calls) == len(PERIODIC_COMMANDS) - 1
