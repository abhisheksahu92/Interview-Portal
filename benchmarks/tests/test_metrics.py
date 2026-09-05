"""Band maths, annualisation, city parsing and the k-anonymity floor."""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone

from benchmarks import metrics
from jobs.models import Job
from offers.models import Offer

pytestmark = pytest.mark.django_db


# --- pure helpers ----------------------------------------------------------- #


def test_percentiles_of_a_known_series():
    values = [Decimal(v) for v in (1000000, 1200000, 1400000, 1600000, 1800000)]
    assert metrics.percentile(values, 0.25) == Decimal("1200000.00")
    assert metrics.percentile(values, 0.50) == Decimal("1400000.00")
    assert metrics.percentile(values, 0.75) == Decimal("1600000.00")


def test_percentiles_interpolate_between_ranks():
    values = [Decimal("100"), Decimal("200"), Decimal("300"), Decimal("400")]
    assert metrics.percentile(values, 0.25) == Decimal("175.00")
    assert metrics.percentile(values, 0.50) == Decimal("250.00")
    assert metrics.percentile(values, 0.75) == Decimal("325.00")


def test_percentile_of_an_empty_or_single_series():
    assert metrics.percentile([], 0.5) is None
    assert metrics.percentile([Decimal("7")], 0.75) == Decimal("7.00")


def test_monthly_pay_is_annualised():
    assert metrics.annualise(Decimal("100000"), "MONTH") == Decimal("1200000.00")
    assert metrics.annualise(Decimal("1200000"), "YEAR") == Decimal("1200000.00")
    assert metrics.annualise(None, "MONTH") is None


def test_city_is_the_text_before_the_comma():
    assert metrics.city_of("Pune, MH") == "Pune"
    assert metrics.city_of("  Bengaluru , Karnataka, India ") == "Bengaluru"
    assert metrics.city_of("Remote") == "Remote"
    assert metrics.city_of("") == ""
    assert metrics.city_of(None) == ""


@pytest.mark.parametrize(
    "years,expected",
    [
        (0, "0-2"), ("2.9", "0-2"), (3, "3-5"), ("5.5", "3-5"),
        (6, "6-9"), ("9.9", "6-9"), (10, "10+"), (25, "10+"),
        (None, ""), (-1, ""),
    ],
)
def test_experience_bands(years, expected):
    assert metrics.experience_band(years) == expected


# --- aggregates ------------------------------------------------------------- #


def test_bands_over_a_known_fixture(five_python_offers):
    rows = metrics.salary_bands()
    assert len(rows) == 1
    row = rows[0]
    assert row["skill"] == "Python"
    assert row["n"] == 5
    assert row["suppressed"] is False
    assert row["p25"] == Decimal("1200000.00")
    assert row["median"] == Decimal("1400000.00")
    assert row["p75"] == Decimal("1600000.00")


def test_a_thin_cell_is_suppressed(company, make_offer):
    for salary in (1000000, 1200000, 1400000, 1600000):
        make_offer(company, salary)
    row = metrics.salary_bands()[0]
    assert row["n"] == 4
    assert row["suppressed"] is True
    assert row["median"] is None and row["p25"] is None and row["p75"] is None


def test_monthly_offers_land_in_the_same_band_as_yearly(company, make_offer):
    for _ in range(5):
        make_offer(company, 100000, period=Job.MONTH)
    row = metrics.salary_bands()[0]
    assert row["median"] == Decimal("1200000.00")


def test_only_accepted_offers_count(company, make_offer):
    for salary in (1000000, 1200000, 1400000, 1600000, 1800000):
        make_offer(company, salary)
    make_offer(company, 9900000, status=Offer.SENT)
    row = metrics.salary_bands()[0]
    assert row["n"] == 5
    assert row["median"] == Decimal("1400000.00")


def test_foreign_currency_offers_are_dropped_not_converted(company, make_offer):
    for salary in (1000000, 1200000, 1400000, 1600000, 1800000):
        make_offer(company, salary)
    make_offer(company, 150000, currency="USD")
    assert metrics.salary_bands()[0]["n"] == 5


def test_offers_outside_the_window_are_excluded(company, make_offer):
    for salary in (1000000, 1200000, 1400000, 1600000, 1800000):
        make_offer(company, salary)
    make_offer(company, 5000000, signed_at=timezone.now() - dt.timedelta(days=800))
    assert metrics.salary_bands(period_months=12)[0]["n"] == 5
    assert metrics.salary_bands(period_months=0)[0]["n"] == 6


def test_city_filter_narrows_the_population(company, make_offer):
    for salary in (1000000, 1200000, 1400000, 1600000, 1800000):
        make_offer(company, salary, location="Pune, MH")
    for salary in (2000000, 2200000, 2400000, 2600000, 2800000):
        make_offer(company, salary, location="Bengaluru, KA")
    pune = metrics.salary_bands(city="Pune")[0]
    blr = metrics.salary_bands(city="Bengaluru")[0]
    assert pune["median"] == Decimal("1400000.00")
    assert blr["median"] == Decimal("2400000.00")


def test_experience_filter_narrows_the_population(company, make_offer):
    for salary in (1000000, 1100000, 1200000, 1300000, 1400000):
        make_offer(company, salary, experience_years="1.0")
    for salary in (2000000, 2100000, 2200000, 2300000, 2400000):
        make_offer(company, salary, experience_years="11.0")
    juniors = metrics.salary_bands(experience_band="0-2")[0]
    seniors = metrics.salary_bands(experience_band="10+")[0]
    assert juniors["median"] == Decimal("1200000.00")
    assert seniors["median"] == Decimal("2200000.00")


def test_overall_band_spans_every_skill(company, make_offer):
    for salary in (1000000, 1200000, 1400000, 1600000, 1800000):
        make_offer(company, salary, skill="Python")
    for salary in (2000000, 2200000, 2400000, 2600000, 2800000):
        make_offer(company, salary, skill="React")
    overall = metrics.overall_band()
    assert overall["n"] == 10
    assert overall["median"] == Decimal("1900000.00")


def test_company_vs_market_compares_medians(company, other_company, make_offer):
    for salary in (1000000, 1100000, 1200000):
        make_offer(company, salary)
    for salary in (1400000, 1500000, 1600000, 1700000, 1800000):
        make_offer(other_company, salary)
    row = metrics.company_vs_market(company)[0]
    assert row["skill"] == "Python"
    assert row["n"] == 3
    assert row["median"] == Decimal("1100000.00")
    assert row["market_n"] == 8
    assert row["market_median"] == Decimal("1450000.00")
    assert row["delta"] == Decimal("-350000.00")
    assert row["delta_percent"] == Decimal("-24.14")


def test_company_vs_market_suppresses_a_thin_market(company, make_offer):
    for salary in (1000000, 1100000):
        make_offer(company, salary)
    row = metrics.company_vs_market(company)[0]
    assert row["median"] == Decimal("1050000.00")
    assert row["market_suppressed"] is True
    assert row["market_median"] is None
    assert row["delta"] is None


def test_public_teaser_needs_twenty_offers(company, make_offer):
    for index in range(19):
        make_offer(company, 1000000 + index * 10000)
    assert metrics.public_teaser() == []
    make_offer(company, 1000000 + 19 * 10000)
    rows = metrics.public_teaser()
    assert len(rows) == 1
    assert rows[0]["skill"] == "Python"
    assert rows[0]["n"] == 20
    assert rows[0]["median"] is not None


def test_filter_options_list_what_the_data_holds(company, make_offer):
    make_offer(company, 1000000, skill="Python", location="Pune, MH")
    make_offer(company, 1000000, skill="React", location="Bengaluru, KA")
    options = metrics.filter_options()
    assert options["skills"] == ["Python", "React"]
    assert options["cities"] == ["Bengaluru", "Pune"]
    assert options["bands"] == ["0-2", "3-5", "6-9", "10+"]
