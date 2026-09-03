import csv
import io
import json

import pytest
from django.urls import reverse

from analytics.tests.conftest import entitle


def url(name, *args):
    return reverse(f"analytics:{name}", args=args)


def test_dashboard_renders_for_owner(client, data):
    client.force_login(data.owner)
    response = client.get(url("index"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Pipeline funnel" in body
    assert "Median time to hire" in body
    assert "cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1" in body


def test_dashboard_renders_for_recruiter(client, data):
    client.force_login(data.recruiter)
    assert client.get(url("index")).status_code == 200


def test_dashboard_forbidden_for_interviewer(client, data):
    client.force_login(data.interviewer)
    assert client.get(url("index")).status_code == 403


def test_dashboard_requires_login(client, data):
    response = client.get(url("index"))
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_dashboard_gated_on_the_analytics_feature(client, data):
    entitle(data.company, analytics=False)
    client.force_login(data.owner)
    assert client.get(url("index")).status_code == 403


def test_charts_partial_is_html_fragment(client, data):
    client.force_login(data.owner)
    response = client.get(url("charts"), {"job": data.job_b.pk})
    assert response.status_code == 200
    body = response.content.decode()
    assert "<html" not in body
    assert "Pipeline funnel" in body


def test_report_page_renders(client, data):
    client.force_login(data.owner)
    response = client.get(url("report"))
    assert response.status_code == 200
    assert "Hiring report" in response.content.decode()


@pytest.mark.parametrize(
    "slug", ["overview", "funnel", "time-in-stage", "sources", "interviewers", "assessments", "weekly"]
)
def test_metric_json_endpoints(client, data, slug):
    client.force_login(data.owner)
    response = client.get(url("metric_json", slug))
    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["metric"] == slug
    assert isinstance(payload["data"], dict)


def test_metric_json_honours_date_and_job_filters(client, data):
    client.force_login(data.owner)
    response = client.get(
        url("metric_json", "overview"),
        {"date_from": "2020-01-01", "date_to": "2020-12-31", "job": data.job_a.pk},
    )
    payload = json.loads(response.content)
    assert payload["data"]["applications"] == 0
    assert payload["job"] == data.job_a.pk
    assert payload["date_from"] == "2020-01-01"


def test_metric_json_unknown_slug_is_404(client, data):
    client.force_login(data.owner)
    assert client.get(url("metric_json", "nonsense")).status_code == 404


def test_invalid_dates_fall_back_to_the_default_window(client, data):
    client.force_login(data.owner)
    response = client.get(url("metric_json", "overview"), {"date_from": "not-a-date"})
    assert response.status_code == 200


def test_csv_export_of_the_funnel(client, data):
    client.force_login(data.owner)
    response = client.get(url("export_csv", "funnel"))
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "attachment; filename=" in response["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(response.content.decode())))
    assert rows[0] == ["label", "entered", "passed", "dropped", "pass_rate_percent"]
    screening = next(row for row in rows[1:] if row[0] == "Screening")
    assert screening[1:4] == ["4", "2", "2"]


def test_csv_export_of_sources(client, data):
    client.force_login(data.owner)
    rows = list(
        csv.reader(io.StringIO(client.get(url("export_csv", "sources")).content.decode()))
    )
    assert rows[0][0] == "source"
    assert rows[1][:3] == ["Direct", "4", "1"]


def test_csv_export_unknown_slug_is_404(client, data):
    client.force_login(data.owner)
    assert client.get(url("export_csv", "overview")).status_code == 404


def test_csv_export_is_gated(client, data):
    entitle(data.company, analytics=False)
    client.force_login(data.owner)
    assert client.get(url("export_csv", "funnel")).status_code == 403


def test_empty_state_when_the_window_has_no_data(client, data):
    client.force_login(data.owner)
    response = client.get(url("charts"), {"date_from": "2020-01-01", "date_to": "2020-01-31"})
    body = response.content.decode()
    assert "No applications in this date range." in body
    assert "No stage movement recorded in this date range." in body
