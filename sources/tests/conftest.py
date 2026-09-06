"""Fixtures for the sources tests.

Every payload here was recorded from the live feed once (see the fixtures
directory) so that adapter parsing is exercised against the shapes those APIs
actually return, without a single test touching the network.
"""

import json
from pathlib import Path

import pytest

from sources.models import Source

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    """Raw bytes for an XML fixture, parsed JSON for anything else."""
    raw = (FIXTURES / name).read_bytes()
    return raw if name.endswith(".xml") else json.loads(raw)


@pytest.fixture
def fixture():
    return load


@pytest.fixture
def source(db):
    def factory(slug="remotive", kind=Source.API, **config):
        return Source.objects.get_or_create(
            slug=slug, defaults={"name": slug, "kind": kind, "config": config}
        )[0]

    return factory
