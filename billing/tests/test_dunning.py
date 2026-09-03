"""Dunning: day 1/3/7 reminders, idempotency and the day-7 downgrade."""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from billing import dunning
from billing.models import DunningReminder, Plan, Subscription
from billing.services import get_subscription

pytestmark = pytest.mark.django_db


def _past_due(company, days):
    subscription = get_subscription(company)
    subscription.plan = Plan.objects.get(code=Plan.GROWTH)
    subscription.status = Subscription.PAST_DUE
    subscription.past_due_since = timezone.now() - timedelta(days=days)
    subscription.save()
    return subscription


def test_no_reminder_on_the_day_it_fails(company, owner):
    subscription = _past_due(company, 0)
    assert dunning.due_reminders(subscription) == []


def test_reminder_schedule_is_day_1_3_7(company, owner):
    assert dunning.due_reminders(_past_due(company, 1)) == [1]
    assert dunning.due_reminders(_past_due(company, 3)) == [1, 3]
    assert dunning.due_reminders(_past_due(company, 7)) == [1, 3, 7]


def test_run_dunning_sends_and_records_reminders(company, owner):
    _past_due(company, 3)
    sent, downgraded = dunning.run()
    assert sent == 2
    assert downgraded == 0
    assert sorted(DunningReminder.objects.values_list("day", flat=True)) == [1, 3]


def test_run_dunning_is_idempotent(company, owner):
    _past_due(company, 3)
    call_command("run_dunning", verbosity=0)
    call_command("run_dunning", verbosity=0)
    assert DunningReminder.objects.count() == 2


def test_reminder_falls_back_to_email(company, owner):
    _past_due(company, 1)
    mail.outbox.clear()
    dunning.run()
    assert len(mail.outbox) == 1
    assert owner.email in mail.outbox[0].to


def test_reminder_prefers_the_notifications_app(company, owner, monkeypatch):
    import sys
    import types

    _past_due(company, 1)
    calls = []
    module = types.ModuleType("notifications")
    module.send = lambda event, recipient, context, company=None: calls.append(
        (event, recipient)
    )
    monkeypatch.setitem(sys.modules, "notifications", module)
    mail.outbox.clear()
    dunning.run()
    assert calls == [("payment_failed", owner.email)]
    assert mail.outbox == []


def test_day_seven_downgrades_to_free(company, owner):
    _past_due(company, 7)
    sent, downgraded = dunning.run()
    assert downgraded == 1
    subscription = Subscription.objects.get(company=company)
    assert subscription.plan.code == Plan.FREE
    assert subscription.status == Subscription.CANCELED


def test_active_subscriptions_are_left_alone(company, owner):
    dunning.run()
    assert DunningReminder.objects.count() == 0
