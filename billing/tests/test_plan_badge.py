"""The sidebar plan badge shows the *effective* plan and the trial countdown."""

import pytest
from django.urls import reverse

from billing.context_processors import billing as billing_context
from billing.models import Plan, Subscription
from core.models import Membership, User

pytestmark = pytest.mark.django_db


def _owner(company, email):
    user = User.objects.create_user(email=email, password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    return user


def test_context_processor_exposes_effective_plan_and_trial(rf, trial_company):
    owner = _owner(trial_company, "trial-owner@acme.test")
    request = rf.get("/")
    request.user = owner
    request.company = trial_company
    context = billing_context(request)
    # Premise changed in phase 4: the billed tier of a new company is STARTER.
    assert context["billing_plan"].code == Plan.STARTER  # billed tier
    assert context["billing_effective_plan"].code == Plan.AGENCY
    assert context["billing_in_trial"] is True
    assert 1 <= context["billing_trial_days_left"] <= 14


def test_sidebar_shows_the_agency_trial_countdown(client, trial_company):
    owner = _owner(trial_company, "sidebar-owner@acme.test")
    client.force_login(owner)
    body = client.get(reverse("web:dashboard")).content.decode()
    assert "Agency trial ·" in body
    assert "days left" in body


def test_sidebar_shows_the_billed_plan_once_the_trial_ends(client, owner, company):
    Subscription.objects.filter(company=company).update(
        plan=Plan.objects.get(code=Plan.GROWTH), status=Subscription.ACTIVE
    )
    client.force_login(owner)
    body = client.get(reverse("web:dashboard")).content.decode()
    assert "trial ·" not in body
    assert "Growth" in body
