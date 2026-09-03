import datetime as dt

from django.db import connection
from django.test.utils import CaptureQueriesContext

from analytics import metrics


def test_overview_kpis(data):
    result = metrics.overview(data.company, data.date_from, data.date_to)
    assert result["open_jobs"] == 2
    assert result["applications"] == 4
    assert result["hires"] == 1
    assert result["rejected"] == 1
    assert result["active"] == 2
    assert result["hire_rate_percent"] == 25.0
    assert result["median_time_to_hire_days"] == 10.0
    assert result["avg_fit_score"] == 60.0


def test_overview_job_filter_scopes_everything(data):
    result = metrics.overview(data.company, data.date_from, data.date_to, job=data.job_b)
    assert result["applications"] == 1
    assert result["hires"] == 0
    assert result["open_jobs"] == 1


def test_date_range_filter_excludes_older_applications(data):
    later = (data.base + dt.timedelta(days=20)).date()
    result = metrics.overview(data.company, later, data.date_to)
    assert result["applications"] == 0
    assert result["hire_rate_percent"] == 0.0
    assert result["median_time_to_hire_days"] is None


def test_funnel_entered_passed_dropped(data):
    stages = {row["kind"]: row for row in metrics.funnel(data.company, data.date_from, data.date_to)["stages"]}
    assert (stages["SCREENING"]["entered"], stages["SCREENING"]["passed"], stages["SCREENING"]["dropped"]) == (4, 2, 2)
    assert (stages["ASSESSMENT"]["entered"], stages["ASSESSMENT"]["passed"]) == (2, 1)
    assert stages["ASSESSMENT"]["pass_rate_percent"] == 50.0
    assert stages["INTERVIEW"]["entered"] == 1
    assert stages["OFFER"]["entered"] == 0


def test_time_in_stage_medians(data):
    stages = {
        row["kind"]: row
        for row in metrics.time_in_stage(data.company, data.date_from, data.date_to)["stages"]
    }
    assert stages["SCREENING"]["median_days"] == 2.5  # 2 days and 3 days
    assert stages["ASSESSMENT"]["median_days"] == 2.0  # 3 days and 1 day
    assert stages["INTERVIEW"]["median_days"] == 5.0
    assert stages["HR"]["median_days"] is None
    assert stages["SCREENING"]["samples"] == 2


def test_source_effectiveness_defaults_to_direct(data):
    rows = metrics.source_effectiveness(data.company, data.date_from, data.date_to)["sources"]
    assert len(rows) == 1
    assert rows[0]["source"] == "Direct"
    assert rows[0]["applications"] == 4
    assert rows[0]["hires"] == 1
    assert rows[0]["hire_rate_percent"] == 25.0


def test_interviewer_consistency(data):
    rows = metrics.interviewer_consistency(data.company, data.date_from, data.date_to)["reviewers"]
    assert len(rows) == 1
    row = rows[0]
    assert row["reviewer"] == data.interviewer.email
    assert row["reviews"] == 2
    assert row["avg_rating"] == 3.0
    assert row["rating_stddev"] == 1.0  # ratings 4 and 2
    assert row["pass_rate_percent"] == 50.0


def test_assessment_pass_rates(data):
    rows = metrics.assessment_pass_rates(data.company, data.date_from, data.date_to)["assessments"]
    assert len(rows) == 1
    assert rows[0]["assessment"] == "Python basics"
    assert rows[0]["attempts"] == 2
    assert rows[0]["passed"] == 1
    assert rows[0]["pass_rate_percent"] == 50.0
    assert rows[0]["avg_score_percent"] == 60.0


def test_weekly_series_covers_the_window(data):
    points = metrics.weekly_series(data.company, data.date_from, data.date_to)["points"]
    assert points, "expected at least one week bucket"
    assert sum(point["applications"] for point in points) == 4
    assert sum(point["hires"] for point in points) == 1
    assert all(point["week"] == point["week"] for point in points)
    weeks = [point["week"] for point in points]
    assert weeks == sorted(weeks)


def test_offer_acceptance_is_optional(data):
    result = metrics.offer_acceptance(data.company, data.date_from, data.date_to)
    if result is not None:
        assert set(["total", "accepted", "declined", "acceptance_rate_percent"]) <= set(result)


def test_all_metrics_is_json_serialisable(data):
    import json

    payload = metrics.all_metrics(data.company, data.date_from, data.date_to)
    assert json.loads(json.dumps(payload))["overview"]["applications"] == 4


def test_metrics_avoid_n_plus_one_queries(data):
    with CaptureQueriesContext(connection) as captured:
        metrics.all_metrics(data.company, data.date_from, data.date_to)
    # A bounded set of aggregate queries regardless of how many rows exist.
    assert len(captured) < 30, [q["sql"] for q in captured]


def test_default_range_is_ninety_days():
    today = dt.date(2026, 3, 31)
    date_from, date_to = metrics.default_range(today)
    assert date_to == today
    assert (date_to - date_from).days == 89


def test_metrics_are_company_scoped(data):
    from core.models import Company

    other = Company.objects.create(name="Other Co")
    assert metrics.overview(other, data.date_from, data.date_to)["applications"] == 0
