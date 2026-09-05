"""Metered usage: quotas, QuotaExceeded and the 80% warning."""

import pytest

from billing import usage
from billing.models import Plan, Subscription, UsageRecord

pytestmark = pytest.mark.django_db


def _upgrade(company, code):
    Subscription.objects.update_or_create(
        company=company,
        defaults={"plan": Plan.objects.get(code=code), "status": Subscription.ACTIVE},
    )
    company.refresh_from_db()
    return company


def test_free_plan_has_no_ai_credits(company):
    # Premise changed in phase 4: AI screening past the allowance is *billed*
    # as overage rather than blocked (see test_placement_pricing for the
    # hard_cap opt-out), so the quota is zero but the call still succeeds.
    assert usage.quota(company, usage.AI_SCREEN) == 0
    record = usage.consume(company, usage.AI_SCREEN)
    assert record.overage is True


def test_ai_credits_come_from_the_plan(company):
    _upgrade(company, Plan.STARTER)
    assert usage.quota(company, usage.AI_SCREEN) == 50
    usage.consume(company, usage.AI_SCREEN, qty=10)
    assert usage.used(company, usage.AI_SCREEN) == 10
    assert usage.remaining(company, usage.AI_SCREEN) == 40


def test_whatsapp_quota_per_tier(company):
    _upgrade(company, Plan.GROWTH)
    assert usage.quota(company, usage.WHATSAPP_MSG) == 500
    _upgrade(company, Plan.AGENCY)
    assert usage.quota(company, usage.WHATSAPP_MSG) == 5000
    _upgrade(company, Plan.STARTER)
    assert usage.quota(company, usage.WHATSAPP_MSG) == 0


def test_video_minutes_are_agency_only(company):
    _upgrade(company, Plan.GROWTH)
    assert usage.quota(company, usage.VIDEO_MINUTE) == 0
    _upgrade(company, Plan.AGENCY)
    assert usage.quota(company, usage.VIDEO_MINUTE) == 300


def test_consume_raises_once_the_quota_is_spent_under_a_hard_cap(company):
    # Premise changed in phase 4: only a hard-capped subscription refuses;
    # otherwise the extra screens land on the monthly invoice.
    _upgrade(company, Plan.STARTER)
    Subscription.objects.filter(company=company).update(hard_cap=True)
    usage.consume(company, usage.AI_SCREEN, qty=50)
    with pytest.raises(usage.QuotaExceeded) as exc:
        usage.consume(company, usage.AI_SCREEN)
    assert exc.value.quota == 50
    assert exc.value.used == 50
    assert UsageRecord.objects.filter(company=company).count() == 1


def test_consume_never_partially_records_an_overflowing_batch(company):
    # Premise changed in phase 4: the all-or-nothing guarantee now applies to a
    # hard-capped subscription (an uncapped one bills the excess instead).
    _upgrade(company, Plan.STARTER)
    Subscription.objects.filter(company=company).update(hard_cap=True)
    with pytest.raises(usage.QuotaExceeded):
        usage.consume(company, usage.AI_SCREEN, qty=51)
    assert usage.used(company, usage.AI_SCREEN) == 0


def test_warning_fires_when_crossing_eighty_percent(company, monkeypatch):
    _upgrade(company, Plan.STARTER)
    seen = []
    monkeypatch.setattr(
        "billing.usage._warn", lambda *args: seen.append(args), raising=True
    )
    usage.consume(company, usage.AI_SCREEN, qty=39)
    assert seen == []
    usage.consume(company, usage.AI_SCREEN)  # 40 of 50 == 80%
    assert len(seen) == 1
    usage.consume(company, usage.AI_SCREEN)  # already warned
    assert len(seen) == 1


def test_warning_degrades_silently_without_the_notifications_app(company):
    """notifications.send may not exist yet; consume must still succeed."""
    _upgrade(company, Plan.STARTER)
    usage.consume(company, usage.AI_SCREEN, qty=40)
    assert usage.used(company, usage.AI_SCREEN) == 40


def test_warning_calls_notifications_send_when_available(company, monkeypatch):
    import sys
    import types

    _upgrade(company, Plan.STARTER)
    calls = []
    module = types.ModuleType("notifications")
    module.send = lambda event, recipient, context, company=None: calls.append(
        (event, context, company)
    )
    monkeypatch.setitem(sys.modules, "notifications", module)
    usage.consume(company, usage.AI_SCREEN, qty=40)
    assert calls and calls[0][0] == "usage_warning"
    assert calls[0][1]["percent"] == 80


def test_trial_company_gets_agency_quotas(trial_company):
    assert usage.quota(trial_company, usage.AI_SCREEN) == 2000
    assert usage.quota(trial_company, usage.VIDEO_MINUTE) == 300


def test_snapshot_flags_the_warning_band(company):
    _upgrade(company, Plan.STARTER)
    usage.consume(company, usage.AI_SCREEN, qty=45)
    row = next(r for r in usage.snapshot(company) if r["kind"] == usage.AI_SCREEN)
    assert row["percent"] == 90
    assert row["warning"] is True
    other = next(r for r in usage.snapshot(company) if r["kind"] == usage.VIDEO_MINUTE)
    assert other["included"] is False


def test_unknown_kind_is_rejected(company):
    with pytest.raises(ValueError):
        usage.consume(company, "TELEPATHY")
