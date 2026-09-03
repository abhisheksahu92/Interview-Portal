"""The 403 page tells a plan problem apart from a role problem."""

import pytest
from django.test import RequestFactory

from billing.entitlements import FeatureNotAvailable
from core.models import Company, Membership, User
from core.views import permission_denied


def _request(user=None, company=None):
    request = RequestFactory().get("/anything/")
    request.user = user
    request.company = company
    return request


@pytest.mark.django_db
def test_role_denial_keeps_the_role_copy():
    user = User.objects.create_user(email="iv@example.com", password="pw12345!")
    response = permission_denied(_request(user), Exception("nope"))
    assert response.status_code == 403
    body = response.content.decode()
    assert "Your role in this workspace does not allow this page." in body
    assert "doesn't include" not in body
    # The header sentence is no longer duplicated inside the card.
    assert body.count("Your role in this workspace does not allow this page.") == 1


@pytest.mark.django_db
def test_feature_denial_shows_plan_copy_and_an_upgrade_button_for_owners():
    company = Company.objects.create(name="Acme")
    user = User.objects.create_user(email="owner@example.com", password="pw12345!")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)

    response = permission_denied(_request(user, company), FeatureNotAvailable("scheduling"))
    assert response.status_code == 403
    body = response.content.decode()
    assert "Your plan doesn't include Scheduling" in body
    assert ">Upgrade<" in body
    assert "Your role in this workspace" not in body


@pytest.mark.django_db
def test_feature_denial_hides_the_upgrade_button_from_non_owners():
    company = Company.objects.create(name="Acme")
    user = User.objects.create_user(email="rec@example.com", password="pw12345!")
    Membership.objects.create(user=user, company=company, role=Membership.RECRUITER)

    body = permission_denied(
        _request(user, company), FeatureNotAvailable("client_portal")
    ).content.decode()
    assert "Your plan doesn't include Client Portal" in body
    assert ">Upgrade<" not in body
