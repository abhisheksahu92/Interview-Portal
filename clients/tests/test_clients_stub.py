import pytest
from django.urls import reverse

from core.models import Company, Membership, User


@pytest.fixture
def owner(db):
    company = Company.objects.create(name="Acme Staffing")
    user = User.objects.create_user(email="owner@clients.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.OWNER)
    return user


def test_clients_index_renders(client, owner):
    client.force_login(owner)
    response = client.get(reverse("clients:index"))
    assert response.status_code == 200
    assert b"Coming soon" in response.content


def test_clients_gateway_not_configured():
    from clients.gateway import configured

    assert configured() is False
