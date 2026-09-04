"""Salary fields on the job form, the public job page and the INR filter."""

from decimal import Decimal

import pytest
from django.template import Context, Template
from django.urls import reverse

from jobs.models import Job
from web.forms import JobForm
from web.templatetags.web_money import indian_group


def _payload(**extra):
    data = {
        "title": "SRE",
        "location": "Pune",
        "employment_type": "FULL_TIME",
        "status": "OPEN",
        "description": "d",
        "requirements": "r",
    }
    data.update(extra)
    return data


@pytest.mark.parametrize(
    ("digits", "expected"),
    [
        ("5", "5"),
        ("500", "500"),
        ("1500", "1,500"),
        ("120000", "1,20,000"),
        ("1200000", "12,00,000"),
        ("120000000", "12,00,00,000"),
    ],
)
def test_indian_grouping(digits, expected):
    assert indian_group(digits) == expected


def test_inr_filter_renders_indian_groups_and_symbol():
    out = Template(
        "{% load web_money %}{{ code|currency_symbol }}{{ amount|inr }}"
    ).render(Context({"code": "INR", "amount": Decimal("1250000.50")}))
    assert out == "₹12,50,000.50"


def test_inr_filter_is_blank_for_none():
    out = Template("{% load web_money %}[{{ amount|inr }}]").render(
        Context({"amount": None})
    )
    assert out == "[]"


@pytest.mark.django_db
def test_job_form_rejects_a_max_below_the_min(company):
    form = JobForm(
        _payload(salary_min="900000", salary_max="500000", show_salary="on"),
        company=company,
    )
    assert not form.is_valid()
    assert "salary_max" in form.errors


@pytest.mark.django_db
def test_job_form_rejects_publishing_an_empty_salary(company):
    form = JobForm(_payload(show_salary="on"), company=company)
    assert not form.is_valid()
    assert "show_salary" in form.errors


@pytest.mark.django_db
def test_job_form_defaults_currency_and_period(company):
    form = JobForm(
        _payload(salary_min="1200000", salary_max="1800000", show_salary="on"),
        company=company,
    )
    assert form.is_valid(), form.errors
    job = form.save()
    assert (job.salary_currency, job.salary_period) == ("INR", Job.YEAR)
    assert job.salary_published


@pytest.mark.django_db
def test_job_form_saves_without_any_salary(company):
    form = JobForm(_payload(), company=company)
    assert form.is_valid(), form.errors
    job = form.save()
    assert not job.has_salary
    assert not job.salary_published


@pytest.mark.django_db
def test_public_job_detail_shows_and_hides_the_salary(client, company, make_job):
    job = make_job(company)
    job.salary_min, job.salary_max, job.show_salary = (
        Decimal("1200000"),
        Decimal("1800000"),
        True,
    )
    job.save()
    url = reverse("web:job_public_detail", args=[job.pk])
    assert "₹12,00,000" in client.get(url).content.decode()
    job.show_salary = False
    job.save()
    assert "12,00,000" not in client.get(url).content.decode()
