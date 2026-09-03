"""Analytics dashboard, JSON chart feeds, CSV exports and printable report.

Every view is gated twice: the ``analytics`` plan feature (billing entitlements)
and an OWNER/RECRUITER role in the active company.
"""

import csv
import datetime as dt

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone

from analytics import metrics
from billing.entitlements import require_feature
from core.models import Membership
from core.permissions import for_company, role_required
from jobs.models import Job

STAFF_ROLES = (Membership.OWNER, Membership.RECRUITER)


def analytics_view(view_func):
    """login + OWNER/RECRUITER role + the ``analytics`` plan feature."""
    return login_required(role_required(*STAFF_ROLES)(require_feature("analytics")(view_func)))


# --- request parsing ------------------------------------------------------


def _parse_date(raw, fallback):
    if not raw:
        return fallback
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return fallback


def filters_from_request(request):
    """Resolve the date range and optional job filter from the query string."""
    company = request.company
    default_from, default_to = metrics.default_range(timezone.localdate())
    date_from = _parse_date(request.GET.get("date_from"), default_from)
    date_to = _parse_date(request.GET.get("date_to"), default_to)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    job = None
    raw_job = request.GET.get("job") or ""
    if raw_job.isdigit():
        job = for_company(Job.objects.all(), company).filter(pk=int(raw_job)).first()
    return {"date_from": date_from, "date_to": date_to, "job": job}


def _chart_data(data):
    """Compact, Chart.js-shaped arrays for the templates' ``json_script`` block."""
    funnel_stages = data["funnel"]["stages"]
    stage_times = data["time_in_stage"]["stages"]
    weekly = data["weekly"]["points"]
    reviewers = data["interviewers"]["reviewers"]
    return {
        "funnel": {
            "labels": [row["label"] for row in funnel_stages],
            "passed": [row["passed"] for row in funnel_stages],
            "dropped": [row["dropped"] for row in funnel_stages],
        },
        "timeInStage": {
            "labels": [row["label"] for row in stage_times],
            "days": [row["median_days"] for row in stage_times],
        },
        "weekly": {
            "labels": [row["week"] for row in weekly],
            "applications": [row["applications"] for row in weekly],
            "hires": [row["hires"] for row in weekly],
        },
        "interviewers": {
            "labels": [row["reviewer"] for row in reviewers],
            "avg": [row["avg_rating"] for row in reviewers],
        },
    }


def _context(request):
    selected = filters_from_request(request)
    company = request.company
    data = metrics.all_metrics(
        company, selected["date_from"], selected["date_to"], selected["job"]
    )
    return {
        "company": company,
        "filters": selected,
        "date_from": selected["date_from"],
        "date_to": selected["date_to"],
        "selected_job": selected["job"],
        "jobs": for_company(Job.objects.all(), company).order_by("title"),
        "metrics": data,
        "overview": data["overview"],
        "funnel": data["funnel"],
        "time_in_stage": data["time_in_stage"],
        "sources": data["sources"],
        "interviewers": data["interviewers"],
        "assessments": data["assessments"],
        "weekly": data["weekly"],
        "offers": data.get("offers"),
        "chart_data": _chart_data(data),
        "query_string": request.GET.urlencode(),
        "has_funnel": any(row["entered"] for row in data["funnel"]["stages"]),
        "has_weekly": bool(data["overview"]["applications"]),
        "has_time_in_stage": any(row["samples"] for row in data["time_in_stage"]["stages"]),
    }


# --- pages ----------------------------------------------------------------


@analytics_view
def index(request):
    """The analytics dashboard: filters, KPI tiles and every chart."""
    return render(request, "analytics/dashboard.html", _context(request))


@analytics_view
def charts(request):
    """HTMX partial: just the charts/tables, re-rendered for new filters."""
    return render(request, "analytics/_charts.html", _context(request))


@analytics_view
def monthly_report(request):
    """A print-friendly one-page summary of the selected window."""
    return render(request, "analytics/report.html", _context(request))


# --- data endpoints -------------------------------------------------------


@analytics_view
def metric_json(request, slug):
    """One metric as JSON, ready for Chart.js."""
    func = metrics.METRICS.get(slug)
    if func is None:
        raise Http404("Unknown metric")
    selected = filters_from_request(request)
    payload = func(request.company, selected["date_from"], selected["date_to"], selected["job"])
    if payload is None:
        raise Http404("Metric unavailable")
    return JsonResponse(
        {
            "metric": slug,
            "date_from": selected["date_from"].isoformat(),
            "date_to": selected["date_to"].isoformat(),
            "job": selected["job"].pk if selected["job"] else None,
            "data": payload,
        }
    )


# slug -> (row-list key, ordered column names)
CSV_TABLES = {
    "funnel": ("stages", ["label", "entered", "passed", "dropped", "pass_rate_percent"]),
    "time-in-stage": ("stages", ["label", "median_days", "samples"]),
    "sources": (
        "sources",
        ["source", "applications", "hires", "rejected", "hire_rate_percent"],
    ),
    "interviewers": (
        "reviewers",
        ["reviewer", "reviews", "avg_rating", "rating_stddev", "pass_rate_percent"],
    ),
    "assessments": (
        "assessments",
        ["assessment", "attempts", "passed", "pass_rate_percent", "avg_score_percent"],
    ),
    "weekly": ("points", ["week", "applications", "hires"]),
}


@analytics_view
def export_csv(request, slug):
    """Download one metric table as CSV."""
    table = CSV_TABLES.get(slug)
    func = metrics.METRICS.get(slug)
    if table is None or func is None:
        raise Http404("Unknown export")
    key, columns = table
    selected = filters_from_request(request)
    payload = func(request.company, selected["date_from"], selected["date_to"], selected["job"])
    rows = (payload or {}).get(key, [])

    response = HttpResponse(content_type="text/csv")
    filename = f"{slug}-{selected['date_from']}-to-{selected['date_to']}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(["" if row.get(column) is None else row.get(column) for column in columns])
    return response
