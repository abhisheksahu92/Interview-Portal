import pytest
from django.urls import reverse

from core.models import Company, Membership, User


@pytest.fixture
def owner(db):
    company = Company.objects.create(name="Acme Staffing")
    user = User.objects.create_user(email="owner@analytics.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    return user


def test_analytics_index_renders(client, owner):
    client.force_login(owner)
    response = client.get(reverse("analytics:index"))
    assert response.status_code == 200
    assert b"Coming soon" in response.content


def test_analytics_gateway_not_configured():
    from analytics.gateway import configured

    assert configured() is False
