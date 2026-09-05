"""Gating, exports and the public teaser."""

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse

from benchmarks.tests.conftest import enable_analytics
from offers.models import Offer

pytestmark = pytest.mark.django_db


def test_report_requires_the_analytics_feature(client, owner, company):
    enable_analytics(company, enabled=False)
    client.force_login(owner)
    assert client.get(reverse("benchmarks:index")).status_code == 403


def test_interviewers_are_not_allowed_in(client, interviewer):
    client.force_login(interviewer)
    assert client.get(reverse("benchmarks:index")).status_code == 403


def test_anonymous_visitors_are_redirected_or_refused(client):
    assert client.get(reverse("benchmarks:index")).status_code in (302, 403)


def test_report_renders_published_bands(client, owner, five_python_offers):
    client.force_login(owner)
    response = client.get(reverse("benchmarks:index"))
    body = response.content.decode()
    assert response.status_code == 200
    assert "Python" in body
    assert "14,00,000" in body


def test_report_marks_a_thin_band_as_hidden(client, owner, company, make_offer):
    make_offer(company, 1000000)
    client.force_login(owner)
    body = client.get(reverse("benchmarks:index")).content.decode()
    assert "fewer than 5 offers" in body


def test_filters_are_applied_to_the_report(client, owner, company, make_offer):
    for salary in (1000000, 1200000, 1400000, 1600000, 1800000):
        make_offer(company, salary, location="Pune, MH")
    client.force_login(owner)
    body = client.get(reverse("benchmarks:index"), {"city": "Bengaluru"}).content.decode()
    assert "No accepted offers in this window" in body


def test_csv_export_carries_the_bands(client, owner, five_python_offers):
    client.force_login(owner)
    response = client.get(reverse("benchmarks:csv"))
    body = response.content.decode()
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "skill,offers,p25_inr,median_inr,p75_inr,suppressed" in body
    assert "Python,5,1200000.00,1400000.00,1600000.00,no" in body


def test_csv_export_blanks_a_suppressed_row(client, owner, company, make_offer):
    make_offer(company, 1000000)
    client.force_login(owner)
    body = client.get(reverse("benchmarks:csv")).content.decode()
    assert "Python,1,,,,yes" in body


def test_pdf_snapshot_is_a_pdf(client, owner, five_python_offers):
    client.force_login(owner)
    response = client.get(reverse("benchmarks:pdf"))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"
    assert "quarterly-compensation-snapshot.pdf" in response["Content-Disposition"]


def test_pdf_is_gated_like_the_report(client, owner, company):
    enable_analytics(company, enabled=False)
    client.force_login(owner)
    assert client.get(reverse("benchmarks:pdf")).status_code == 403
    assert client.get(reverse("benchmarks:csv")).status_code == 403


def test_public_teaser_needs_no_login_and_hides_thin_data(client, company, make_offer):
    for salary in (1000000, 1200000, 1400000, 1600000, 1800000):
        make_offer(company, salary)
    response = client.get(reverse("benchmarks:public"))
    body = response.content.decode()
    assert response.status_code == 200
    assert "Not enough accepted offers yet" in body
    assert "14,00,000" not in body


def test_public_teaser_publishes_a_busy_skill(client, company, make_offer):
    for index in range(20):
        make_offer(company, 1000000 + index * 10000)
    body = client.get(reverse("benchmarks:public")).content.decode()
    assert "Python" in body
    assert "20" in body


def test_seed_command_creates_enough_offers_to_publish(db):
    call_command("benchmarks_seed_demo", verbosity=0)
    from benchmarks import metrics

    assert Offer.objects.filter(status=Offer.ACCEPTED).count() >= 40
    rows = {row["skill"]: row for row in metrics.salary_bands()}
    assert set(rows) == {"Python", "React", "QA Automation"}
    assert all(not row["suppressed"] for row in rows.values())
    assert rows["Python"]["median"] > Decimal("0")


def test_seed_command_is_idempotent(db):
    call_command("benchmarks_seed_demo", verbosity=0)
    first = Offer.objects.count()
    call_command("benchmarks_seed_demo", verbosity=0)
    assert Offer.objects.count() == first
