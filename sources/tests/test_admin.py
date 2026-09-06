"""The admin's "Run now" action drives the same service the command does."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from sources import services
from sources.admin import SourceAdmin
from sources.models import Lead, Source


@pytest.fixture
def request_with_messages(db):
    request = RequestFactory().post("/admin/sources/source/")
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def test_run_now(db, monkeypatch, fixture, request_with_messages):
    from sources.adapters import ADAPTERS

    payload = fixture("remotive.json")
    monkeypatch.setattr(
        ADAPTERS["remotive"], "fetch", lambda source: ADAPTERS["remotive"].parse(payload)
    )
    monkeypatch.setattr(services.llm, "complete", lambda *a, **k: None)
    admin = SourceAdmin(Source, AdminSite())
    admin.run_now(request_with_messages, Source.objects.filter(slug="remotive"))
    assert Lead.objects.count() > 0
