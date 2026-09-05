"""Benchmark report, exports and the public teaser.

Everything is computed at read time from accepted offers — see
:mod:`benchmarks.metrics` for the annualisation, percentile and k-anonymity
rules. No view ever hands a tenant another tenant's row: only aggregates that
clear the anonymity threshold leave this module.
"""

import csv
import datetime as dt
import logging
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone

from benchmarks import metrics
from billing.entitlements import require_feature
from core.models import Membership
from core.permissions import role_required

logger = logging.getLogger(__name__)

STAFF_ROLES = (Membership.OWNER, Membership.RECRUITER)
FEATURE = "analytics"
DEFAULT_PERIOD_MONTHS = 12


def benchmarks_view(view_func):
    """login + OWNER/RECRUITER role + the ``analytics`` plan feature."""
    return login_required(role_required(*STAFF_ROLES)(require_feature(FEATURE)(view_func)))


def filters_from_request(request):
    """Resolve skill / city / experience filters, ignoring anything unknown."""
    band = (request.GET.get("experience") or "").strip()
    return {
        "skill": (request.GET.get("skill") or "").strip(),
        "city": (request.GET.get("city") or "").strip(),
        "experience_band": band if band in metrics.BAND_CODES else "",
        "period_months": DEFAULT_PERIOD_MONTHS,
    }


def _report(company, filters):
    """Everything both the HTML report and the PDF need, computed once."""
    rows = metrics.offer_rows(filters["period_months"])
    bands = metrics.salary_bands(
        skill=filters["skill"],
        city=filters["city"],
        experience_band=filters["experience_band"],
        rows=rows,
    )
    return {
        "filters": filters,
        "bands": bands,
        "overall": metrics.overall_band(
            skill=filters["skill"],
            city=filters["city"],
            experience_band=filters["experience_band"],
            rows=rows,
        ),
        "comparison": metrics.company_vs_market(
            company,
            city=filters["city"],
            experience_band=filters["experience_band"],
            rows=rows,
        ),
        "options": metrics.filter_options(rows=rows),
        "min_n": metrics.MIN_N,
        "period_months": filters["period_months"],
        "generated_at": timezone.now(),
    }


def _chart_data(bands):
    """Chart.js-shaped arrays for the published (unsuppressed) cells only."""
    published = [row for row in bands if not row["suppressed"]][:12]
    return {
        "labels": [row["skill"] for row in published],
        "p25": [float(row["p25"]) for row in published],
        "median": [float(row["median"]) for row in published],
        "p75": [float(row["p75"]) for row in published],
    }


@benchmarks_view
def index(request):
    context = _report(request.company, filters_from_request(request))
    context["chart"] = _chart_data(context["bands"])
    return render(request, "benchmarks/report.html", context)


@benchmarks_view
def export_csv(request):
    """The same table as the report, suppressed cells included as blanks."""
    context = _report(request.company, filters_from_request(request))
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="salary-benchmarks.csv"'
    writer = csv.writer(response)
    writer.writerow(["skill", "offers", "p25_inr", "median_inr", "p75_inr", "suppressed"])
    for row in context["bands"]:
        writer.writerow(
            [
                row["skill"],
                row["n"],
                row["p25"] if row["p25"] is not None else "",
                row["median"] if row["median"] is not None else "",
                row["p75"] if row["p75"] is not None else "",
                "yes" if row["suppressed"] else "no",
            ]
        )
    return response


@benchmarks_view
def export_pdf(request):
    """"Quarterly Compensation Snapshot", branded with the tenant's white label."""
    from partners.whitelabel import brand_for

    context = _report(request.company, filters_from_request(request))
    context["brand"] = brand_for(request.company)
    context["company"] = request.company
    context["quarter"] = _quarter_label(context["generated_at"])
    html = render_to_string("benchmarks/pdf/snapshot.html", context)
    try:
        from xhtml2pdf import pisa
    except Exception as exc:  # pragma: no cover - dependency is pinned
        logger.warning("benchmarks: xhtml2pdf unavailable: %s", exc)
        return HttpResponse("PDF generation is unavailable.", status=503)
    buffer = BytesIO()
    result = pisa.CreatePDF(src=html, dest=buffer, encoding="utf-8")
    if result.err:
        logger.warning("benchmarks: xhtml2pdf reported errors")
        return HttpResponse("PDF generation failed.", status=503)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        'attachment; filename="quarterly-compensation-snapshot.pdf"'
    )
    return response


def _quarter_label(moment):
    """Indian financial quarter, e.g. ``Q3 FY2026-27``."""
    date = moment.date() if isinstance(moment, dt.datetime) else moment
    fy_start = date.year if date.month >= 4 else date.year - 1
    quarter = ((date.month - 4) % 12) // 3 + 1
    return f"Q{quarter} FY{fy_start}-{str(fy_start + 1)[-2:]}"


def public(request):
    """Marketing teaser: medians for the busiest skills only, n ≥ 20."""
    return render(
        request,
        "benchmarks/public.html",
        {
            "rows": metrics.public_teaser(),
            "min_n": metrics.PUBLIC_MIN_N,
            "generated_at": timezone.now(),
        },
    )
