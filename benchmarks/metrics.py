"""Salary benchmarks computed from accepted offers, at read time.

This app stores nothing. Every number here is derived from
:class:`offers.models.Offer` rows in ``ACCEPTED`` status, which is the only
compensation figure on the platform that someone actually agreed to — job
salary *ranges* are aspirational and are deliberately ignored.

Three rules make the aggregate safe to show one tenant about everyone else:

**Annualisation.** An offer's amount is read in the period its job quotes
(``Job.salary_period``): ``MONTH`` is multiplied by 12, ``YEAR`` is taken as-is.
Mixed-currency offers are dropped rather than converted — a fabricated FX rate
would silently corrupt a median.

**k-anonymity.** Any cell computed from fewer than :data:`MIN_N` offers returns
``None`` instead of numbers. With the default of 5 you cannot single out one
tenant's pay from a published band, and the public teaser raises the bar to 20.
The threshold is settable with ``BENCHMARKS_MIN_N``.

**Percentiles.** p25/median/p75 use linear interpolation between the closest
ranks (the same definition numpy calls "linear"): for ``n`` sorted values the
p-th percentile sits at index ``p*(n-1)``. Documented because a benchmark whose
definition drifts is worse than no benchmark.
"""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import DateTimeField
from django.db.models.functions import Coalesce
from django.utils import timezone

#: Minimum offers behind any published cell. Below this the cell is suppressed.
MIN_N = int(getattr(settings, "BENCHMARKS_MIN_N", 5) or 5)

#: The public teaser is stricter still — it leaves the platform.
PUBLIC_MIN_N = 20

#: Experience bands, in order. ``upper`` is exclusive; ``None`` means open-ended.
EXPERIENCE_BANDS = (
    ("0-2", Decimal("0"), Decimal("3")),
    ("3-5", Decimal("3"), Decimal("6")),
    ("6-9", Decimal("6"), Decimal("10")),
    ("10+", Decimal("10"), None),
)

BAND_CODES = tuple(code for code, _, _ in EXPERIENCE_BANDS)

MONTHS_PER_YEAR = Decimal("12")
ZERO = Decimal("0.00")


def _round(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def experience_band(years):
    """The band label for ``years`` of experience, or ``""`` when unknown."""
    if years is None:
        return ""
    try:
        value = Decimal(str(years))
    except (ArithmeticError, ValueError, TypeError):
        return ""
    if value < 0:
        return ""
    for code, low, high in EXPERIENCE_BANDS:
        if value >= low and (high is None or value < high):
            return code
    return BAND_CODES[-1]


def city_of(location):
    """The city part of a free-text job location: everything before the comma.

    ``"Pune, MH"`` → ``"Pune"``; ``"Remote"`` → ``"Remote"``; blank stays blank.
    """
    head = str(location or "").split(",")[0]
    return " ".join(head.split()).strip()


def annualise(amount, period):
    """An offer amount expressed per year. ``MONTH`` × 12, everything else as-is."""
    if amount is None:
        return None
    value = Decimal(str(amount))
    if str(period or "").upper() == "MONTH":
        value = value * MONTHS_PER_YEAR
    return _round(value)


def percentile(sorted_values, fraction):
    """Linear-interpolation percentile of an already sorted list of Decimals."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return _round(sorted_values[0])
    position = Decimal(str(fraction)) * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    low_value = Decimal(sorted_values[lower])
    high_value = Decimal(sorted_values[upper])
    return _round(low_value + (high_value - low_value) * weight)


# --------------------------------------------------------------------------- #
# Population
# --------------------------------------------------------------------------- #


def _cutoff(period_months):
    months = max(int(period_months or 0), 0)
    if not months:
        return None
    return timezone.now() - dt.timedelta(days=int(months * 30.44))


def offer_rows(period_months=12, currency="INR"):
    """Flatten accepted offers into ``{company_id, skill, city, band, annual}`` rows.

    One row *per skill on the job*, so a Python+Django role counts toward both
    skills — that is what a "salary for skill X" benchmark means.
    """
    from offers.models import Offer

    queryset = (
        Offer.objects.filter(status=Offer.ACCEPTED)
        .annotate(
            decided_at=Coalesce("signed_at", "created_at", output_field=DateTimeField())
        )
        .select_related("application__job", "application__candidate")
        .prefetch_related("application__job__skills")
    )
    cutoff = _cutoff(period_months)
    if cutoff is not None:
        queryset = queryset.filter(decided_at__gte=cutoff)
    if currency:
        queryset = queryset.filter(currency__iexact=currency)

    rows = []
    for offer in queryset:
        application = offer.application
        job = getattr(application, "job", None)
        if job is None:
            continue
        annual = annualise(offer.salary, job.salary_period)
        if not annual or annual <= 0:
            continue
        band = experience_band(
            getattr(getattr(application, "candidate", None), "experience_years", None)
        )
        city = city_of(job.location)
        for skill in job.skills.all():
            rows.append(
                {
                    "company_id": job.company_id,
                    "skill": skill.name,
                    "city": city,
                    "band": band,
                    "annual": annual,
                }
            )
    return rows


def _matches(row, skill, city, band):
    if skill and row["skill"].casefold() != str(skill).casefold():
        return False
    if city and row["city"].casefold() != str(city).casefold():
        return False
    if band and row["band"] != band:
        return False
    return True


def _cell(values, min_n=None):
    """A published cell, or a suppressed one when it is too thin to be safe."""
    threshold = MIN_N if min_n is None else min_n
    n = len(values)
    if n < threshold:
        return {"n": n, "p25": None, "median": None, "p75": None, "suppressed": True}
    ordered = sorted(values)
    return {
        "n": n,
        "p25": percentile(ordered, 0.25),
        "median": percentile(ordered, 0.50),
        "p75": percentile(ordered, 0.75),
        "suppressed": False,
    }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def salary_bands(skill=None, city=None, experience_band=None, period_months=12, rows=None):
    """p25 / median / p75 of accepted offers, one row per skill.

    ``skill`` / ``city`` / ``experience_band`` narrow the population before the
    percentiles are taken; every returned cell with fewer than :data:`MIN_N`
    offers behind it comes back suppressed (``p25``/``median``/``p75`` = None)
    but still reports its ``n``, so the UI can say "not enough data yet" rather
    than lie.
    """
    rows = offer_rows(period_months) if rows is None else rows
    band = experience_band or ""
    buckets = {}
    for row in rows:
        if not _matches(row, skill, city, band):
            continue
        buckets.setdefault(row["skill"], []).append(row["annual"])
    results = []
    for name in sorted(buckets):
        results.append({"skill": name, **_cell(buckets[name])})
    results.sort(key=lambda cell: (cell["median"] or ZERO, cell["n"]), reverse=True)
    return results


def overall_band(skill=None, city=None, experience_band=None, period_months=12, rows=None):
    """One cell across everything the filters select — the headline numbers."""
    rows = offer_rows(period_months) if rows is None else rows
    band = experience_band or ""
    values = [row["annual"] for row in rows if _matches(row, skill, city, band)]
    return _cell(values)


def company_vs_market(company, city=None, experience_band=None, period_months=12, rows=None):
    """This company's own median against the market median, per skill.

    A tenant always sees its *own* numbers — they are its data — but the market
    column obeys k-anonymity, so a comparison against four other offers is
    reported as "not enough market data" rather than as a number.
    """
    rows = offer_rows(period_months) if rows is None else rows
    company_id = getattr(company, "pk", company)
    band = experience_band or ""
    mine, market = {}, {}
    for row in rows:
        if not _matches(row, None, city, band):
            continue
        market.setdefault(row["skill"], []).append(row["annual"])
        if row["company_id"] == company_id:
            mine.setdefault(row["skill"], []).append(row["annual"])
    results = []
    for name in sorted(mine):
        own = sorted(mine[name])
        market_cell = _cell(market.get(name, []))
        own_median = percentile(own, 0.50)
        delta = delta_percent = None
        if market_cell["median"] is not None and own_median is not None:
            delta = _round(own_median - market_cell["median"])
            if market_cell["median"] > 0:
                delta_percent = _round(delta * 100 / market_cell["median"])
        results.append(
            {
                "skill": name,
                "n": len(own),
                "median": own_median,
                "market_n": market_cell["n"],
                "market_median": market_cell["median"],
                "market_suppressed": market_cell["suppressed"],
                "delta": delta,
                "delta_percent": delta_percent,
            }
        )
    results.sort(key=lambda row: row["n"], reverse=True)
    return results


def public_teaser(limit=5, period_months=12, rows=None):
    """Medians for the busiest skills, for the marketing page.

    Only skills with at least :data:`PUBLIC_MIN_N` offers behind them appear:
    this leaves the platform, so the anonymity bar is four times the internal
    one and no p25/p75 spread is published at all.
    """
    rows = offer_rows(period_months) if rows is None else rows
    buckets = {}
    for row in rows:
        buckets.setdefault(row["skill"], []).append(row["annual"])
    cells = []
    for name, values in buckets.items():
        cell = _cell(values, min_n=PUBLIC_MIN_N)
        if cell["suppressed"]:
            continue
        cells.append({"skill": name, "n": cell["n"], "median": cell["median"]})
    cells.sort(key=lambda cell: (cell["n"], cell["median"]), reverse=True)
    return cells[:limit]


def filter_options(rows=None, period_months=12):
    """The skill and city values worth offering in the filter form."""
    rows = offer_rows(period_months) if rows is None else rows
    skills = sorted({row["skill"] for row in rows if row["skill"]})
    cities = sorted({row["city"] for row in rows if row["city"]})
    return {"skills": skills, "cities": cities, "bands": list(BAND_CODES)}
