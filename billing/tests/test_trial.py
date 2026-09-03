"""The 14-day full-featured trial and its expiry."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from billing.entitlements import FEATURES, has_feature, plan_for
from billing.models import Plan, Subscription
from billing.services import get_subscription

pytestmark = pytest.mark.django_db


def test_trial_grants_every_agency_feature(trial_company):
    assert plan_for(trial_company).code == Plan.AGENCY
    assert all(has_feature(trial_company, name) for name in FEATURES)


def test_trial_is_billed_on_free_but_entitled_to_agency(trial_company):
    subscription = get_subscription(trial_company)
    assert subscription.plan.code == Plan.FREE
    assert subscription.status == Subscription.TRIALING
    assert plan_for(trial_company).max_seats == Plan.objects.get(code=Plan.AGENCY).max_seats


def test_expired_trial_falls_back_to_free(trial_company):
    Subscription.objects.filter(company=trial_company).update(
        trial_ends_at=timezone.now() - timedelta(minutes=1)
    )
    trial_company.refresh_from_db()
    assert plan_for(trial_company).code == Plan.FREE
    assert has_feature(trial_company, "client_portal") is False


def test_paid_plan_beats_the_trial(trial_company):
    subscription = get_subscription(trial_company)
    subscription.plan = Plan.objects.get(code=Plan.STARTER)
    subscription.status = Subscription.ACTIVE
    subscription.save()
    trial_company.refresh_from_db()
    assert plan_for(trial_company).code == Plan.STARTER
    assert has_feature(trial_company, "analytics") is True
    assert has_feature(trial_company, "video") is False


def test_expire_trials_command_is_idempotent(trial_company):
    Subscription.objects.filter(company=trial_company).update(
        trial_ends_at=timezone.now() - timedelta(days=1)
    )
    call_command("expire_trials", verbosity=0)
    subscription = Subscription.objects.get(company=trial_company)
    assert subscription.status == Subscription.ACTIVE
    assert subscription.in_trial is False
    call_command("expire_trials", verbosity=0)
    assert Subscription.objects.get(company=trial_company).status == Subscription.ACTIVE


def test_expire_trials_leaves_running_trials_alone(trial_company):
    call_command("expire_trials", verbosity=0)
    assert Subscription.objects.get(company=trial_company).status == Subscription.TRIALING


def test_seats_used_counts_memberships(company, owner, recruiter):
    subscription = get_subscription(company)
    assert subscription.seats_used == 2
    assert subscription.max_seats == Plan.objects.get(code=Plan.FREE).max_seats
