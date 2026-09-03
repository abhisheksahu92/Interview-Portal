"""``{% load features %}`` — the template seam onto billing entitlements."""

import pytest
from django.template import Context, Template

from web.tests.conftest import free_expired, paid


def _render(template, **context):
    return Template("{% load features %}" + template).render(Context(context)).strip()


class FakeRequest:
    def __init__(self, company):
        self.company = company




@pytest.mark.django_db
def test_feature_enabled_reads_request_company(company):
    paid(company)
    out = _render(
        '{% feature_enabled "video" as ok %}{{ ok }}', request=FakeRequest(company)
    )
    assert out == "True"


@pytest.mark.django_db
def test_feature_enabled_is_false_for_a_free_expired_company(company):
    free_expired(company)
    out = _render(
        '{% feature_enabled "video" as ok %}{{ ok }}', request=FakeRequest(company)
    )
    assert out == "False"


@pytest.mark.django_db
def test_feature_enabled_falls_back_to_current_company(company):
    paid(company)
    out = _render(
        '{% feature_enabled "offers" as ok %}{{ ok }}', current_company=company
    )
    assert out == "True"


@pytest.mark.django_db
def test_feature_enabled_accepts_an_explicit_company(company, other_company):
    paid(company)
    free_expired(other_company)
    template = '{% feature_enabled "offers" other as ok %}{{ ok }}'
    assert _render(template, request=FakeRequest(company), other=other_company) == "False"


def test_feature_enabled_without_any_company_is_false():
    assert _render('{% feature_enabled "video" as ok %}{{ ok }}') == "False"


@pytest.mark.django_db
def test_has_feature_filter(company):
    paid(company)
    assert _render('{{ c|has_feature:"scheduling" }}', c=company) == "True"
    assert _render('{{ c|has_feature:"nonsense" }}', c=company) == "False"


@pytest.mark.django_db
def test_has_feature_filter_on_a_free_company(company):
    free_expired(company)
    assert _render('{{ c|has_feature:"scheduling" }}', c=company) == "False"


def test_has_feature_filter_tolerates_none():
    assert _render('{{ c|has_feature:"scheduling" }}', c=None) == "False"
