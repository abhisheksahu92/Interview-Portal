"""Live template preview wiring and salary formatting on the sign page."""

import pytest
from django.urls import reverse

from offers.models import OfferTemplate
from offers.rendering import format_money

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client(client, recruiter):
    client.force_login(recruiter)
    return client


def test_template_form_uses_a_trigger_that_actually_fires(staff_client, company):
    template = OfferTemplate.default_for(company)
    body = staff_client.get(
        reverse("offers:template_edit", args=[template.pk])
    ).content.decode()
    assert 'hx-trigger="keyup changed delay:500ms, change"' in body
    assert "from:#" not in body  # the old, never-firing selector


def test_preview_endpoint_still_renders_sample_data(staff_client, company):
    response = staff_client.post(
        reverse("offers:template_preview"), {"body_html": "Hi {{candidate_name}}"}
    )
    assert response.status_code == 200
    assert b"Asha Rao" in response.content


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1800000, "1,800,000"), (2400000, "2,400,000"), (0, "0"), (None, "")],
)
def test_format_money_groups_thousands(value, expected):
    assert format_money(value) == expected


def test_sign_page_subtitle_formats_the_salary(client, draft_offer):
    from offers.services import send_offer

    send_offer(draft_offer)
    body = client.get(
        reverse("offers:sign", args=[draft_offer.sign_token])
    ).content.decode()
    assert "INR 1,800,000" in body
    assert "INR 1800000" not in body
