"""The placeholder renderer must never behave like the Django template engine."""

from decimal import Decimal

import pytest

from offers.models import Offer, OfferTemplate
from offers.rendering import offer_context, render_body


def test_whitelisted_placeholders_are_substituted_and_escaped():
    body = "<p>{{candidate_name}} / {{job_title}} / {{currency}} {{salary}}</p>"
    out = render_body(
        body,
        {
            "candidate_name": "A<b>sha</b>",
            "job_title": "Dev",
            "currency": "INR",
            "salary": Decimal("1800000"),
        },
    )
    assert "A&lt;b&gt;sha&lt;/b&gt;" in out
    assert "1,800,000" in out
    assert "<b>" not in out


def test_custom_placeholders_resolve_from_custom_fields():
    out = render_body("Bonus: {{custom.bonus}}", {"custom": {"bonus": "10%"}})
    assert out == "Bonus: 10%"


@pytest.mark.parametrize(
    "injection",
    [
        "{% load static %}",
        "{% for x in 'abc' %}{{ x }}{% endfor %}",
        "{{ settings.SECRET_KEY }}",
        "{{ user.password }}",
        "{{ 7|add:3 }}",
        "{{ candidate_name.__class__ }}",
    ],
)
def test_template_syntax_is_never_executed(injection):
    """Unknown/unsafe tokens survive as literal text — nothing is evaluated."""
    out = render_body(f"before {injection} after", {"candidate_name": "Asha"})
    # The token survives verbatim: it was neither rendered nor stripped.
    assert out == f"before {injection} after"


def test_unknown_bare_placeholder_is_left_alone():
    assert render_body("{{secret_sauce}}", {"secret_sauce": "x"}) == "{{secret_sauce}}"


@pytest.mark.django_db
def test_offer_context_and_template_render(draft_offer):
    context = offer_context(draft_offer)
    assert context["candidate_name"] == "Asha Rao"
    assert context["job_title"] == "Senior Python Engineer"
    assert "(Bengaluru)" in context["location"]
    body = draft_offer.template.render(context)
    assert "Asha Rao" in body
    assert "{{" not in body


@pytest.mark.django_db
def test_default_template_seeded_lazily_once(company):
    first = OfferTemplate.default_for(company)
    second = OfferTemplate.default_for(company)
    assert first.pk == second.pk
    assert first.is_default
    assert OfferTemplate.objects.for_company(company).count() == 1


@pytest.mark.django_db
def test_only_one_default_template_per_company(company):
    first = OfferTemplate.default_for(company)
    second = OfferTemplate.objects.create(
        company=company, name="Contractor", body_html="hi", is_default=True
    )
    first.refresh_from_db()
    assert second.is_default and not first.is_default


@pytest.mark.django_db
def test_sign_token_is_generated_and_unique(application, recruiter):
    a = Offer.objects.create(application=application, created_by=recruiter)
    b = Offer.objects.create(application=application, created_by=recruiter)
    assert a.sign_token and b.sign_token and a.sign_token != b.sign_token
