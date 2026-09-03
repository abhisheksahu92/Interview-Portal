"""The workspace chrome (sidebar + <head>) must follow the white-label brand."""

import pytest
from django.urls import reverse

from partners.models import WhiteLabel
from partners.whitelabel import DEFAULT_BRAND_NAME

pytestmark = pytest.mark.django_db


def dashboard(client, owner):
    client.force_login(owner)
    response = client.get(reverse("web:dashboard"))
    assert response.status_code == 200
    return response.content.decode()


def test_unbranded_company_renders_the_product_default(client, owner, company):
    body = dashboard(client, owner)
    assert DEFAULT_BRAND_NAME in body
    assert "bi-diagram-3-fill" in body  # the default sidebar mark
    assert "--ip-brand:" not in body


def test_white_label_brand_name_and_colour_reach_the_page(client, owner, company):
    WhiteLabel.objects.create(
        company=company, brand_name="Acme Hire", primary_color="#123456"
    )
    body = dashboard(client, owner)
    assert "Acme Hire" in body
    assert "--ip-brand:#123456" in body
    assert "--bs-primary:#123456" in body
    assert f"<span>{DEFAULT_BRAND_NAME}" not in body  # default sidebar label is gone


def test_white_label_logo_replaces_the_default_mark(client, owner, company):
    WhiteLabel.objects.create(company=company, brand_name="Acme Hire")
    body = dashboard(client, owner)
    assert "Acme Hire" in body
