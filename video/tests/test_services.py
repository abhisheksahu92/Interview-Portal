import sys
import types
from datetime import timedelta

from django.utils import timezone

from video import services
from video.models import VideoInvite


def test_consume_minutes_is_unlimited_without_billing_usage(monkeypatch, company):
    monkeypatch.setitem(sys.modules, "billing.usage", None)
    assert services.consume_minutes(company, 130) is True


def test_consume_minutes_rounds_up_and_passes_the_kind(monkeypatch, company):
    calls = []
    module = types.ModuleType("billing.usage")
    module.consume = lambda c, kind, qty=1: calls.append((c, kind, qty))
    monkeypatch.setitem(sys.modules, "billing.usage", module)
    assert services.consume_minutes(company, 61) is True
    assert calls == [(company, "VIDEO_MINUTE", 2)]


def test_consume_minutes_refuses_when_quota_is_exceeded(monkeypatch, company):
    class QuotaExceeded(Exception):
        pass

    module = types.ModuleType("billing.usage")

    def boom(c, kind, qty=1):
        raise QuotaExceeded("no minutes left")

    module.consume = boom
    monkeypatch.setitem(sys.modules, "billing.usage", module)
    assert services.consume_minutes(company, 30) is False


def test_notify_invite_prefers_notifications_then_falls_back_to_email(
    monkeypatch, invite
):
    sent = []
    module = types.ModuleType("notifications")
    module.send = lambda event, recipient, context, company: sent.append(event)
    monkeypatch.setitem(sys.modules, "notifications", module)
    assert services.notify_invite(invite) is True
    assert sent == ["video_invite"]


def test_expire_stale_invites(invite):
    VideoInvite.objects.filter(pk=invite.pk).update(
        expires_at=timezone.now() - timedelta(hours=1)
    )
    assert services.expire_stale_invites() == 1
    invite.refresh_from_db()
    assert invite.status == VideoInvite.EXPIRED


def test_screen_for_stage_prefers_the_stage_then_the_job(job, screen):
    stage = job.stages.first()
    assert services.screen_for_stage(stage) == screen  # job-wide fallback
    screen.stage = stage
    screen.save(update_fields=["stage"])
    assert services.screen_for_stage(stage) == screen
    assert services.screen_for_stage(None) is None
