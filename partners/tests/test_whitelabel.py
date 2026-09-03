import pytest
from django.template import Context, Template
from django.urls import reverse

from partners.models import WhiteLabel
from partners.whitelabel import DEFAULT_BRAND_COLOR, DEFAULT_BRAND_NAME, brand_for, safe_color

TAGS = Template(
    "{% load whitelabel %}{% brand_name %}|{% brand_color %}|{% brand_logo_url %}|{% powered_by %}"
)


def render(company=None):
    return TAGS.render(Context({"current_company": company}))


def test_tags_fall_back_to_product_defaults(db):
    assert render() == f"{DEFAULT_BRAND_NAME}|{DEFAULT_BRAND_COLOR}||Powered by {DEFAULT_BRAND_NAME}"


def test_tags_fall_back_when_company_has_no_white_label(company):
    assert render(company).startswith(DEFAULT_BRAND_NAME)


def test_tags_use_the_white_label_row(company):
    WhiteLabel.objects.create(
        company=company, brand_name="Acme Hire", primary_color="#123456", hide_powered_by=True
    )
    name, color, logo, powered = render(company).split("|")
    assert (name, color, logo, powered) == ("Acme Hire", "#123456", "", "")


def test_brand_for_none_is_the_default_brand(db):
    brand = brand_for(None)
    assert brand.name == DEFAULT_BRAND_NAME and brand.is_custom is False


def test_email_from_name_defaults_to_brand_name(company):
    WhiteLabel.objects.create(company=company, brand_name="Acme Hire")
    assert brand_for(company).email_from_name == "Acme Hire"


@pytest.mark.parametrize("bad", ["red; background:url(x)", "</style><script>", "12345"])
def test_unsafe_colors_are_rejected(bad):
    assert safe_color(bad) == DEFAULT_BRAND_COLOR


def test_base_template_renders_brand_name_for_company(client, owner):
    client.force_login(owner)
    WhiteLabel.objects.create(company=owner.memberships.first().company, brand_name="Acme Hire")
    response = client.get(reverse("partners:settings"))
    assert response.status_code == 200
