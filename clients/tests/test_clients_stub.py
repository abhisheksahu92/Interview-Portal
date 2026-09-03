"""Smoke tests kept from the app stub."""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_clients_index_renders(client, owner):
    client.force_login(owner)
    response = client.get(reverse("clients:index"))
    assert response.status_code == 200
    assert b"Clients" in response.content


def test_clients_gateway_not_configured():
    from clients.gateway import configured

    assert configured() is False
