"""Drafting: use the model when it answers, and a real letter when it does not."""

import pytest

from seeker import services
from seeker.models import Outreach, SavedItem

pytestmark = pytest.mark.django_db


def _item(seeker, make_lead):
    return SavedItem.objects.create(seeker=seeker, lead=make_lead())


def test_draft_uses_the_model_answer(monkeypatch, seeker, make_lead):
    monkeypatch.setattr(
        "core.llm.complete",
        lambda *a, **k: "Subject: Django contractor — Priya\n\nHi, I saw the brief.\n\nPriya",
    )
    subject, body = services.draft_outreach(seeker, _item(seeker, make_lead))
    assert subject == "Django contractor — Priya"
    assert "I saw the brief" in body


def test_draft_falls_back_when_the_model_is_off(monkeypatch, seeker, make_lead):
    monkeypatch.setattr("core.llm.complete", lambda *a, **k: None)
    subject, body = services.draft_outreach(seeker, _item(seeker, make_lead))
    assert "Django contractor" in subject
    assert "Zeta Labs" in body
    # A fallback that ships placeholders is worse than no draft at all.
    assert "[" not in body


def test_draft_falls_back_on_a_body_less_answer(monkeypatch, seeker, make_lead):
    monkeypatch.setattr("core.llm.complete", lambda *a, **k: "Subject: hello")
    subject, body = services.draft_outreach(seeker, _item(seeker, make_lead))
    assert body


def test_drafts_are_made_only_for_items_with_an_address(monkeypatch, seeker, make_lead, job):
    monkeypatch.setattr("core.llm.complete", lambda *a, **k: "Subject: Hi\n\nBody.\n\nPriya")
    with_email = _item(seeker, make_lead)
    without = SavedItem.objects.create(seeker=seeker, job=job)
    drafts = services.draft_for_items(seeker, [with_email, without])
    assert len(drafts) == 1
    assert drafts[0].saved_item_id == with_email.pk
    assert drafts[0].status == Outreach.DRAFT
