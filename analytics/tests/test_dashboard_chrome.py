"""Header date range follows the HTMX filter; wide tables scroll on mobile."""

import datetime as dt

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def url(name, *args):
    return reverse(f"analytics:{name}", args=args)


def test_dashboard_header_shows_the_current_range(client, data):
    client.force_login(data.owner)
    body = client.get(url("index")).content.decode()
    assert 'id="viz-range"' in body
    assert "hx-swap-oob" not in body  # only the swapped partial is out-of-band


def test_charts_partial_swaps_the_header_range_out_of_band(client, data):
    client.force_login(data.owner)
    date_from = dt.date(2026, 1, 5)
    date_to = dt.date(2026, 2, 9)
    response = client.get(
        url("charts"), {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()}
    )
    body = response.content.decode()
    assert 'id="viz-range"' in body
    assert 'hx-swap-oob="true"' in body
    assert "Jan. 5, 2026" in body or "5 Jan" in body or str(date_from.year) in body
    assert "<html" not in body


def test_charts_partial_header_names_the_selected_job(client, data):
    client.force_login(data.owner)
    body = client.get(url("charts"), {"job": data.job_b.pk}).content.decode()
    marker = body.split('id="viz-range"')[1].split("</p>")[0]
    assert data.job_b.title in marker


def test_interviewer_table_scrolls_horizontally(client, data):
    client.force_login(data.owner)
    body = client.get(url("index")).content.decode()
    section = body.split("Interviewer consistency")[1]
    assert "overflow-x:auto" in section
