"""Salary publication on the public careers pages, JSON-LD and the Indeed feed."""

import json
from decimal import Decimal

import pytest
from django.urls import reverse

from careers.feeds import indeed_salary_text
from careers.seo import job_posting_dict


def _with_salary(job, show=True, low="1200000", high="1800000", period="YEAR"):
    job.salary_min = Decimal(low) if low is not None else None
    job.salary_max = Decimal(high) if high is not None else None
    job.salary_period = period
    job.show_salary = show
    job.save()
    return job


@pytest.mark.django_db
def test_public_job_page_shows_a_published_salary(client, site, job):
    _with_salary(job)
    body = client.get(
        reverse("careers:job_detail", args=[site.slug, job.pk])
    ).content.decode()
    assert "₹12,00,000" in body
    assert "₹18,00,000" in body
    assert "per year" in body


@pytest.mark.django_db
def test_public_pages_hide_an_unpublished_salary(client, site, job):
    _with_salary(job, show=False)
    detail = client.get(
        reverse("careers:job_detail", args=[site.slug, job.pk])
    ).content.decode()
    listing = client.get(reverse("careers:site", args=[site.slug])).content.decode()
    assert "12,00,000" not in detail
    assert "12,00,000" not in listing
    assert "baseSalary" not in detail


@pytest.mark.django_db
def test_site_listing_shows_the_range(client, site, job):
    _with_salary(job)
    body = client.get(reverse("careers:site", args=[site.slug])).content.decode()
    assert "₹12,00,000" in body


@pytest.mark.django_db
def test_json_ld_base_salary(site, job):
    _with_salary(job)
    data = job_posting_dict(job, site)
    assert data["baseSalary"] == {
        "@type": "MonetaryAmount",
        "currency": "INR",
        "value": {
            "@type": "QuantitativeValue",
            "unitText": "YEAR",
            "minValue": 1200000.0,
            "maxValue": 1800000.0,
        },
    }
    # and it survives serialisation into the page
    assert "baseSalary" in json.dumps(data)


@pytest.mark.django_db
def test_json_ld_has_no_base_salary_when_hidden(site, job):
    _with_salary(job, show=False)
    assert "baseSalary" not in job_posting_dict(job, site)


@pytest.mark.django_db
def test_json_ld_single_amount_carries_value(site, job):
    _with_salary(job, low="90000", high=None, period="MONTH")
    value = job_posting_dict(job, site)["baseSalary"]["value"]
    assert value["minValue"] == 90000.0
    assert value["unitText"] == "MONTH"
    assert "maxValue" not in value


@pytest.mark.django_db
def test_indeed_feed_includes_salary_only_when_shown(client, site, job):
    _with_salary(job)
    body = client.get(reverse("careers:indeed_feed")).content.decode()
    assert "<salary>INR 1200000 - 1800000 per year</salary>" in body
    _with_salary(job, show=False)
    assert "<salary>" not in client.get(
        reverse("careers:indeed_feed")
    ).content.decode()


@pytest.mark.django_db
def test_indeed_salary_text_orders_numerically(job):
    _with_salary(job, low="900000", high="1000000")
    assert indeed_salary_text(job) == "INR 900000 - 1000000 per year"
