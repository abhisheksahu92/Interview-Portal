"""Read-time hiring metrics.

Every public function has the same shape::

    fn(company, date_from, date_to, job=None) -> JSON-serialisable dict

``date_from``/``date_to`` are ``datetime.date`` values and inclusive; they filter
on ``Application.created_at`` (the cohort of applications that arrived in the
window) except for the weekly time series, which buckets hires by hire date too.
Nothing here mutates state and every function runs a bounded number of aggregate
queries (no per-row lookups).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncWeek

from analytics.models import StageTransition
from jobs.models import (
    Application,
    CandidateProfile,
    Job,
    PipelineStage,
    StageReview,
)

# Stage kinds in pipeline order — the funnel and time-in-stage charts use this.
STAGE_KIND_ORDER = [
    PipelineStage.SCREENING,
    PipelineStage.ASSESSMENT,
    PipelineStage.INTERVIEW,
    PipelineStage.HR,
    PipelineStage.OFFER,
]
STAGE_KIND_LABELS = dict(PipelineStage.KIND_CHOICES)

DEFAULT_WINDOW_DAYS = 90


# --- helpers --------------------------------------------------------------


def default_range(today=None):
    """The dashboard's default (inclusive) date range: the last 90 days."""
    today = today or dt.date.today()
    return today - dt.timedelta(days=DEFAULT_WINDOW_DAYS - 1), today


def _applications(company, date_from, date_to, job=None):
    qs = Application.objects.filter(
        job__company=company,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    if job is not None:
        qs = qs.filter(job=job)
    return qs


def _float(value, ndigits=2):
    if value is None:
        return None
    if isinstance(value, Decimal):
        value = float(value)
    return round(float(value), ndigits)


def _median(values):
    """Median of a list of numbers, or None when empty."""
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (float(ordered[middle - 1]) + float(ordered[middle])) / 2


def _stddev(values):
    """Population standard deviation (SQLite has no STDDEV aggregate)."""
    numbers = [float(v) for v in values if v is not None]
    if len(numbers) < 2:
        return 0.0 if numbers else None
    mean = sum(numbers) / len(numbers)
    variance = sum((n - mean) ** 2 for n in numbers) / len(numbers)
    return variance**0.5


def _candidate_has_source():
    """True when ``jobs.CandidateProfile`` has grown a ``source`` field."""
    return any(field.name == "source" for field in CandidateProfile._meta.get_fields())


# --- metrics --------------------------------------------------------------


def overview(company, date_from, date_to, job=None):
    """Headline KPIs for the window: volumes, hire rate, velocity, AI fit."""
    applications = _applications(company, date_from, date_to, job)
    counts = applications.aggregate(
        total=Count("id"),
        hires=Count("id", filter=Q(status=Application.HIRED)),
        rejected=Count("id", filter=Q(status=Application.REJECTED)),
        active=Count("id", filter=Q(status=Application.ACTIVE)),
        avg_fit=Avg("ai_fit_score"),
    )
    open_jobs = Job.objects.filter(company=company, status=Job.OPEN)
    if job is not None:
        open_jobs = open_jobs.filter(pk=job.pk)

    total = counts["total"] or 0
    hires = counts["hires"] or 0
    return {
        "open_jobs": open_jobs.count(),
        "applications": total,
        "hires": hires,
        "rejected": counts["rejected"] or 0,
        "active": counts["active"] or 0,
        "hire_rate_percent": _float(100.0 * hires / total) if total else 0.0,
        "median_time_to_hire_days": _median(_time_to_hire_days(applications)),
        "avg_fit_score": _float(counts["avg_fit"], 1),
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }


def _time_to_hire_days(applications):
    """Days from application to hire, for the hired rows of ``applications``.

    Prefers the recorded HIRED transition; falls back to ``updated_at`` for rows
    that predate the history table.
    """
    hired = list(
        applications.filter(status=Application.HIRED).values_list(
            "id", "created_at", "updated_at"
        )
    )
    if not hired:
        return []
    hired_at = dict(
        StageTransition.objects.filter(
            application_id__in=[row[0] for row in hired],
            status_after=Application.HIRED,
        )
        .order_by("application_id", "at")
        .values_list("application_id", "at")
    )
    days = []
    for pk, created_at, updated_at in hired:
        end = hired_at.get(pk) or updated_at
        days.append(max((end - created_at).total_seconds() / 86400.0, 0.0))
    return days


def funnel(company, date_from, date_to, job=None):
    """Per stage-kind: how many applications entered, passed on, and dropped."""
    applications = _applications(company, date_from, date_to, job)
    rows = list(
        StageTransition.objects.filter(application__in=applications)
        .exclude(to_stage__isnull=True)
        .values_list("application_id", "to_stage__kind", "to_stage__order")
    )
    statuses = dict(applications.values_list("id", "status"))

    entered = defaultdict(set)
    furthest = {}
    entry_order = {}
    for app_id, kind, order in rows:
        entered[kind].add(app_id)
        furthest[app_id] = max(order, furthest.get(app_id, -1))
        key = (app_id, kind)
        entry_order[key] = min(order, entry_order.get(key, order))

    stages = []
    for kind in STAGE_KIND_ORDER:
        app_ids = entered.get(kind, set())
        passed = 0
        for app_id in app_ids:
            first_order = entry_order[(app_id, kind)]
            if statuses.get(app_id) == Application.HIRED or furthest.get(app_id, 0) > first_order:
                passed += 1
        stages.append(
            {
                "kind": kind,
                "label": STAGE_KIND_LABELS.get(kind, kind),
                "entered": len(app_ids),
                "passed": passed,
                "dropped": len(app_ids) - passed,
                "pass_rate_percent": _float(100.0 * passed / len(app_ids)) if app_ids else 0.0,
            }
        )
    return {"stages": stages}


def time_in_stage(company, date_from, date_to, job=None):
    """Median days an application spends in each stage kind."""
    applications = _applications(company, date_from, date_to, job)
    rows = list(
        StageTransition.objects.filter(application__in=applications)
        .order_by("application_id", "at", "id")
        .values_list("application_id", "to_stage__kind", "at")
    )
    durations = defaultdict(list)
    for index, (app_id, kind, at) in enumerate(rows):
        if kind is None:
            continue
        nxt = rows[index + 1] if index + 1 < len(rows) else None
        if nxt is None or nxt[0] != app_id:
            continue  # still in this stage — an open interval tells us nothing
        durations[kind].append(max((nxt[2] - at).total_seconds() / 86400.0, 0.0))
    return {
        "stages": [
            {
                "kind": kind,
                "label": STAGE_KIND_LABELS.get(kind, kind),
                "median_days": _float(_median(durations.get(kind, []))),
                "samples": len(durations.get(kind, [])),
            }
            for kind in STAGE_KIND_ORDER
        ]
    }


def source_effectiveness(company, date_from, date_to, job=None):
    """Applications → hires broken down by candidate source.

    ``CandidateProfile.source`` may not exist (it belongs to a sibling app that
    may ship later); everything then falls into "Direct".
    """
    applications = _applications(company, date_from, date_to, job)
    if _candidate_has_source():
        rows = applications.values_list("candidate__source", "status")
    else:
        rows = (("", status) for status in applications.values_list("status", flat=True))

    buckets = defaultdict(lambda: {"applications": 0, "hires": 0, "rejected": 0})
    for source, status in rows:
        bucket = buckets[(source or "").strip() or "Direct"]
        bucket["applications"] += 1
        if status == Application.HIRED:
            bucket["hires"] += 1
        elif status == Application.REJECTED:
            bucket["rejected"] += 1

    sources = [
        {
            "source": name,
            "applications": data["applications"],
            "hires": data["hires"],
            "rejected": data["rejected"],
            "hire_rate_percent": _float(100.0 * data["hires"] / data["applications"]),
        }
        for name, data in buckets.items()
    ]
    sources.sort(key=lambda row: (-row["applications"], row["source"]))
    return {"sources": sources}


def interviewer_consistency(company, date_from, date_to, job=None):
    """Per reviewer: volume, average rating, rating spread and pass rate."""
    reviews = StageReview.objects.filter(
        application__job__company=company,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    if job is not None:
        reviews = reviews.filter(application__job=job)
    rows = reviews.values_list("reviewer_id", "reviewer__email", "decision", "rating")

    grouped = defaultdict(lambda: {"email": "", "ratings": [], "reviews": 0, "passes": 0})
    for reviewer_id, email, decision, rating in rows:
        entry = grouped[reviewer_id]
        entry["email"] = email
        entry["reviews"] += 1
        if decision == StageReview.PASS:
            entry["passes"] += 1
        if rating is not None:
            entry["ratings"].append(rating)

    reviewers = [
        {
            "reviewer_id": reviewer_id,
            "reviewer": entry["email"],
            "reviews": entry["reviews"],
            "avg_rating": _float(
                sum(entry["ratings"]) / len(entry["ratings"]) if entry["ratings"] else None
            ),
            "rating_stddev": _float(_stddev(entry["ratings"])),
            "pass_rate_percent": _float(100.0 * entry["passes"] / entry["reviews"]),
        }
        for reviewer_id, entry in grouped.items()
    ]
    reviewers.sort(key=lambda row: (-row["reviews"], row["reviewer"]))
    return {"reviewers": reviewers}


def assessment_pass_rates(company, date_from, date_to, job=None):
    """Submitted-attempt pass rate and average score per assessment."""
    from assessments.models import Attempt

    attempts = Attempt.objects.filter(
        application__job__company=company,
        submitted_at__isnull=False,
        submitted_at__date__gte=date_from,
        submitted_at__date__lte=date_to,
    )
    if job is not None:
        attempts = attempts.filter(application__job=job)
    rows = (
        attempts.values("assessment_id", "assessment__title")
        .annotate(
            attempts=Count("id"),
            passed=Count("id", filter=Q(passed=True)),
            avg_score=Avg("score_percent"),
        )
        .order_by("assessment__title")
    )
    assessments = [
        {
            "assessment_id": row["assessment_id"],
            "assessment": row["assessment__title"],
            "attempts": row["attempts"],
            "passed": row["passed"],
            "pass_rate_percent": _float(100.0 * row["passed"] / row["attempts"])
            if row["attempts"]
            else 0.0,
            "avg_score_percent": _float(row["avg_score"], 1),
        }
        for row in rows
    ]
    return {"assessments": assessments}


def weekly_series(company, date_from, date_to, job=None):
    """Applications received and hires made, bucketed by ISO week."""
    applications = _applications(company, date_from, date_to, job)
    received = {
        row["week"].date(): row["n"]
        for row in applications.annotate(week=TruncWeek("created_at"))
        .values("week")
        .annotate(n=Count("id"))
        if row["week"] is not None
    }
    hired = {
        row["week"].date(): row["n"]
        for row in applications.filter(status=Application.HIRED)
        .annotate(week=TruncWeek("updated_at"))
        .values("week")
        .annotate(n=Count("id"))
        if row["week"] is not None
    }
    week = date_from - dt.timedelta(days=date_from.weekday())
    points = []
    while week <= date_to:
        points.append(
            {
                "week": week.isoformat(),
                "applications": received.get(week, 0),
                "hires": hired.get(week, 0),
            }
        )
        week += dt.timedelta(days=7)
    return {"points": points}


def offer_acceptance(company, date_from, date_to, job=None):
    """Offer funnel, when the optional ``offers`` app is installed.

    Returns ``None`` (the dashboard then omits the card) if the app is absent or
    has not shipped its ``Offer`` model yet.
    """
    try:
        from offers.models import Offer
    except (ImportError, ModuleNotFoundError):  # pragma: no cover - app may be absent
        return None
    if not hasattr(Offer, "_meta") or not hasattr(Offer, "status"):
        return None
    offers = Offer.objects.filter(
        application__job__company=company,
        application__created_at__date__gte=date_from,
        application__created_at__date__lte=date_to,
    )
    if job is not None:
        offers = offers.filter(application__job=job)
    rows = dict(offers.values_list("status").annotate(n=Count("id")))
    total = sum(rows.values())
    accepted = rows.get("ACCEPTED", 0)
    return {
        "total": total,
        "accepted": accepted,
        "declined": rows.get("DECLINED", 0),
        "pending": total - accepted - rows.get("DECLINED", 0),
        "acceptance_rate_percent": _float(100.0 * accepted / total) if total else 0.0,
        "by_status": [{"status": status, "count": n} for status, n in sorted(rows.items())],
    }


def all_metrics(company, date_from, date_to, job=None):
    """Every metric in one dict — what the dashboard and report pages render."""
    data = {
        "overview": overview(company, date_from, date_to, job),
        "funnel": funnel(company, date_from, date_to, job),
        "time_in_stage": time_in_stage(company, date_from, date_to, job),
        "sources": source_effectiveness(company, date_from, date_to, job),
        "interviewers": interviewer_consistency(company, date_from, date_to, job),
        "assessments": assessment_pass_rates(company, date_from, date_to, job),
        "weekly": weekly_series(company, date_from, date_to, job),
    }
    offers = offer_acceptance(company, date_from, date_to, job)
    if offers is not None:
        data["offers"] = offers
    return data


# Slug → metric function, used by the JSON and CSV endpoints.
METRICS = {
    "overview": overview,
    "funnel": funnel,
    "time-in-stage": time_in_stage,
    "sources": source_effectiveness,
    "interviewers": interviewer_consistency,
    "assessments": assessment_pass_rates,
    "weekly": weekly_series,
    "offers": offer_acceptance,
}
