"""Phase 4 placement-linked pricing: seats, success fees, monthly bills.

Covers the seat-vs-flat pricing model, the per-hire success fee, the assembled
monthly invoice (subscription + success fees + AI overage + ledger charges),
billed AI overage vs a hard cap, the trial → STARTER downgrade with its grace
window, ``bill_month`` idempotency, the running projection and the two new
feature flags.
"""

from datetime import UTC, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from billing import invoicing, ledger
from billing import usage as usage_module
from billing.entitlements import FEATURES, has_feature
from billing.limits import can_open_job
from billing.models import BillingCharge, Invoice, PlacementFee, Plan, Subscription
from billing.services import get_subscription
from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job

pytestmark = pytest.mark.django_db


def _on_plan(company, code, **fields):
    plan = Plan.objects.get(code=code)
    Subscription.objects.update_or_create(
        company=company,
        defaults={
            "plan": plan,
            "status": Subscription.ACTIVE,
            # Trial ended well before this billing period, so the plan line is
            # a full month (proration only applies in the month a trial ends).
            "trial_ends_at": timezone.now() - timedelta(days=60),
            **fields,
        },
    )
    company.refresh_from_db()
    return plan


def _seat(company, email):
    user = User.objects.create_user(email=email, password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.RECRUITER)
    return user


def _hire(company, email="hire@example.test", title="Python Dev"):
    job = Job.objects.create(company=company, title=title, status=Job.DRAFT)
    user = User.objects.create_user(email=email, password="pw12345678")
    candidate = CandidateProfile.objects.create(user=user, experience_years=Decimal("3.0"))
    application = Application.objects.create(job=job, candidate=candidate)
    application.status = Application.HIRED
    application.save()
    return application


def _lines(invoice_or_projection):
    items = getattr(invoice_or_projection, "line_items", None)
    if items is None:
        items = invoice_or_projection["lines"]
    return {line["kind"]: line for line in items}


# --- Plan pricing --------------------------------------------------------


def test_starter_is_seat_based_and_the_others_are_flat():
    starter = Plan.objects.get(code=Plan.STARTER)
    assert starter.pricing_model == Plan.SEAT
    assert starter.is_seat_based is True
    assert starter.price_monthly_inr == 999
    for code in (Plan.GROWTH, Plan.AGENCY):
        assert Plan.objects.get(code=code).pricing_model == Plan.FLAT


def test_success_fees_and_ai_allowances_per_tier():
    tiers = {p.code: p for p in Plan.objects.all()}
    assert tiers[Plan.STARTER].success_fee_inr == 4999
    assert tiers[Plan.GROWTH].success_fee_inr == 2999
    assert tiers[Plan.AGENCY].success_fee_inr == 0
    assert [tiers[c].ai_included for c in (Plan.STARTER, Plan.GROWTH, Plan.AGENCY)] == [
        50,
        500,
        2000,
    ]
    assert all(tiers[c].ai_overage_inr == 5 for c in Plan.PAID_CODES)


def test_seat_pricing_multiplies_by_seats():
    starter = Plan.objects.get(code=Plan.STARTER)
    assert starter.subscription_amount(seats=1) == Decimal("999.00")
    assert starter.subscription_amount(seats=4) == Decimal("3996.00")
    growth = Plan.objects.get(code=Plan.GROWTH)
    assert growth.subscription_amount(seats=4) == Decimal("4999.00")


def test_subscription_line_prices_starter_per_seat(company, owner):
    _on_plan(company, Plan.STARTER)
    _seat(company, "second@acme.test")
    lines = _lines(invoicing.projected_bill(company))
    assert lines["SUBSCRIPTION"]["qty"] == 2
    assert lines["SUBSCRIPTION"]["total_inr"] == "1998.00"
    assert "recruiter seat" in lines["SUBSCRIPTION"]["label"]


def test_subscription_line_is_flat_for_growth(company, owner):
    _on_plan(company, Plan.GROWTH)
    _seat(company, "second@acme.test")
    lines = _lines(invoicing.projected_bill(company))
    assert lines["SUBSCRIPTION"]["qty"] == 1
    assert lines["SUBSCRIPTION"]["total_inr"] == "4999.00"


# --- Success fees --------------------------------------------------------


def test_every_hire_raises_the_plan_success_fee(company):
    _on_plan(company, Plan.STARTER)
    _hire(company, "one@example.test")
    _hire(company, "two@example.test", title="QA")
    fees = PlacementFee.objects.filter(company=company)
    assert fees.count() == 2
    assert {f.amount for f in fees} == {Decimal("4999.00")}


def test_success_fee_is_idempotent_per_application(company):
    _on_plan(company, Plan.GROWTH)
    application = _hire(company)
    application.save()
    application.save()
    assert PlacementFee.objects.filter(application=application).count() == 1
    assert PlacementFee.objects.get(application=application).amount == Decimal("2999.00")


def test_agency_hires_carry_no_success_fee(company):
    _on_plan(company, Plan.AGENCY)
    _hire(company)
    assert PlacementFee.objects.filter(company=company).count() == 0


# --- Ledger --------------------------------------------------------------


def test_add_charge_records_a_charge(company):
    charge = ledger.add_charge(company, ledger.BGV, "BGV — Priya", 499, ref="bgv:1")
    assert charge.company_id == company.pk
    assert charge.amount_inr == Decimal("499.00")
    assert charge.is_invoiced is False


def test_add_charge_is_idempotent_on_ref(company):
    ledger.add_charge(company, ledger.PLATFORM_FEE, "Exchange fee", 1200, ref="deal:7")
    ledger.add_charge(company, ledger.PLATFORM_FEE, "Exchange fee", 1500, ref="deal:7")
    charge = BillingCharge.objects.get(company=company, ref="deal:7")
    assert BillingCharge.objects.filter(company=company).count() == 1
    assert charge.amount_inr == Decimal("1500.00")


def test_add_charge_without_a_company_is_a_no_op(db):
    assert ledger.add_charge(None, ledger.BGV, "nobody", 100) is None


# --- Monthly invoice -----------------------------------------------------


def test_monthly_invoice_assembles_every_line(company, owner):
    _on_plan(company, Plan.STARTER)
    _hire(company)
    ledger.add_charge(company, ledger.BGV, "BGV — Priya", 499, ref="bgv:1")
    now = timezone.now()
    invoice = invoicing.build_monthly_invoice(company, now.year, now.month)
    lines = _lines(invoice)
    assert set(lines) >= {"SUBSCRIPTION", "SUCCESS_FEE", "BGV"}
    assert invoice.amount == Decimal("6497.00")  # 999 + 4999 + 499
    assert invoice.total == Decimal("7666.46")  # + 18% GST
    assert invoice.period_start.day == 1


def test_monthly_invoice_marks_fees_and_charges_as_invoiced(company, owner):
    _on_plan(company, Plan.STARTER)
    _hire(company)
    ledger.add_charge(company, ledger.BGV, "BGV", 499, ref="bgv:2")
    now = timezone.now()
    invoice = invoicing.build_monthly_invoice(company, now.year, now.month)
    fee = PlacementFee.objects.get(company=company)
    assert fee.status == PlacementFee.INVOICED
    assert fee.invoice_id == invoice.pk
    assert BillingCharge.objects.get(company=company).invoice_id == invoice.pk


def test_monthly_invoice_is_idempotent(company, owner):
    _on_plan(company, Plan.STARTER)
    now = timezone.now()
    first = invoicing.build_monthly_invoice(company, now.year, now.month)
    second = invoicing.build_monthly_invoice(company, now.year, now.month)
    assert first.pk == second.pk
    assert Invoice.objects.filter(company=company).count() == 1


def test_nothing_to_bill_yields_no_invoice(company):
    # Legacy FREE tier with no hires and no charges.
    now = timezone.now()
    assert invoicing.build_monthly_invoice(company, now.year, now.month) is None


def test_ai_overage_is_billed_on_the_monthly_invoice(company, owner):
    _on_plan(company, Plan.STARTER)
    usage_module.consume(company, usage_module.AI_SCREEN, qty=50)
    usage_module.consume(company, usage_module.AI_SCREEN, qty=10)
    now = timezone.now()
    invoice = invoicing.build_monthly_invoice(company, now.year, now.month)
    line = _lines(invoice)["AI_OVERAGE"]
    assert line["qty"] == 10  # billed as units × unit price, not one lump sum
    assert Decimal(line["unit_inr"]) == Decimal("5.00")
    assert Decimal(line["total_inr"]) == Decimal("50.00")  # 10 x ₹5


def test_charges_from_other_months_are_not_billed(company, owner):
    _on_plan(company, Plan.STARTER)
    last_month = timezone.now() - timedelta(days=40)
    ledger.add_charge(company, ledger.BGV, "Old BGV", 999, ref="bgv:old", occurred_at=last_month)
    now = timezone.now()
    invoice = invoicing.build_monthly_invoice(company, now.year, now.month)
    assert "BGV" not in _lines(invoice)


# --- bill_month command --------------------------------------------------


def test_bill_month_issues_one_invoice_per_company(company, owner):
    _on_plan(company, Plan.STARTER)
    _hire(company)
    call_command("bill_month", verbosity=0)
    call_command("bill_month", verbosity=0)
    assert Invoice.objects.filter(company=company).count() == 1


def test_bill_month_can_target_one_company(company, owner, db):
    _on_plan(company, Plan.STARTER)
    other = Company.objects.create(name="Other Ltd")
    _on_plan(other, Plan.GROWTH)
    call_command("bill_month", company=company.name, verbosity=0)
    assert Invoice.objects.filter(company=company).count() == 1
    assert Invoice.objects.filter(company=other).count() == 0


def test_bill_month_accepts_an_explicit_period(company, owner):
    _on_plan(company, Plan.STARTER)
    call_command("bill_month", year=2026, month=1, verbosity=0)
    invoice = Invoice.objects.get(company=company)
    assert (invoice.period_start.year, invoice.period_start.month) == (2026, 1)


# --- Projection ----------------------------------------------------------


def test_projection_totals_the_running_month(company, owner):
    _on_plan(company, Plan.STARTER)
    _hire(company)
    projection = invoicing.projected_bill(company)
    assert projection["subtotal"] == Decimal("5998.00")
    assert projection["total"] == Decimal("7077.64")
    assert projection["invoiced"] is False


def test_projection_marks_an_already_issued_period(company, owner):
    _on_plan(company, Plan.STARTER)
    now = timezone.now()
    invoicing.build_monthly_invoice(company, now.year, now.month)
    assert invoicing.projected_bill(company)["invoiced"] is True


def test_overview_shows_the_projection_card(client, owner, company):
    _on_plan(company, Plan.STARTER)
    _hire(company)
    client.force_login(owner)
    response = client.get("/billing/")
    assert response.context["projection"]["subtotal"] == Decimal("5998.00")
    assert b"This month so far" in response.content


# --- Metered overage vs hard cap -----------------------------------------


def test_overage_is_billed_instead_of_blocked(company):
    _on_plan(company, Plan.STARTER)
    usage_module.consume(company, usage_module.AI_SCREEN, qty=50)
    record = usage_module.consume(company, usage_module.AI_SCREEN, qty=5)
    assert record.overage is True
    charge = BillingCharge.objects.get(company=company, kind=ledger.AI_OVERAGE)
    assert charge.amount_inr == Decimal("25.00")


def test_hard_cap_still_raises_quota_exceeded(company):
    _on_plan(company, Plan.STARTER, hard_cap=True)
    usage_module.consume(company, usage_module.AI_SCREEN, qty=50)
    with pytest.raises(usage_module.QuotaExceeded):
        usage_module.consume(company, usage_module.AI_SCREEN)
    assert BillingCharge.objects.filter(company=company).count() == 0


def test_overage_charge_accumulates_within_a_period(company):
    _on_plan(company, Plan.STARTER)
    usage_module.consume(company, usage_module.AI_SCREEN, qty=50)
    usage_module.consume(company, usage_module.AI_SCREEN, qty=3)
    usage_module.consume(company, usage_module.AI_SCREEN, qty=2)
    charges = BillingCharge.objects.filter(company=company, kind=ledger.AI_OVERAGE)
    assert charges.count() == 1
    assert charges.first().amount_inr == Decimal("25.00")  # 5 x ₹5


def test_the_eighty_percent_warning_still_fires(company, monkeypatch):
    _on_plan(company, Plan.STARTER)
    seen = []
    monkeypatch.setattr("billing.usage._warn", lambda *args: seen.append(args), raising=True)
    usage_module.consume(company, usage_module.AI_SCREEN, qty=45)
    assert seen and seen[0][2] == 45


# --- Trial → STARTER + grace ---------------------------------------------


def test_expire_trials_moves_the_company_to_starter_with_grace(db):
    company = Company.objects.create(name="Grace Ltd")
    Subscription.objects.filter(company=company).update(
        trial_ends_at=timezone.now() - timedelta(days=1)
    )
    call_command("expire_trials", verbosity=0)
    subscription = Subscription.objects.get(company=company)
    assert subscription.plan.code == Plan.STARTER
    # No card was ever entered, so the company owes money and must be chased.
    # This used to assert ACTIVE, which is why nobody was ever billed.
    assert subscription.status == Subscription.PAST_DUE
    assert subscription.in_grace is True
    assert 6 <= (subscription.grace_until - timezone.now()).days <= 7


def test_limits_are_not_enforced_during_grace(db):
    company = Company.objects.create(name="Grace Limits Ltd")
    Subscription.objects.filter(company=company).update(
        trial_ends_at=timezone.now() - timedelta(days=1)
    )
    call_command("expire_trials", verbosity=0)
    for i in range(6):  # well past STARTER's three open jobs
        Job.objects.create(company=company, title=f"Dev {i}", status=Job.OPEN)
    allowed, reason = can_open_job(company)
    assert allowed is True and reason == ""


def test_limits_bite_once_the_grace_window_closes(db):
    company = Company.objects.create(name="Post Grace Ltd")
    Subscription.objects.filter(company=company).update(
        status=Subscription.ACTIVE,
        trial_ends_at=timezone.now() - timedelta(days=30),
        grace_until=timezone.now() - timedelta(days=1),
    )
    company.refresh_from_db()
    for i in range(3):
        Job.objects.create(company=company, title=f"Dev {i}", status=Job.OPEN)
    allowed, reason = can_open_job(company)
    assert allowed is False
    assert "Starter" in reason


def test_no_new_company_is_billed_on_free(db):
    company = Company.objects.create(name="Never Free Ltd")
    assert get_subscription(company).plan.code == Plan.STARTER


# --- Feature flags -------------------------------------------------------


def test_contracting_and_exchange_are_known_flags():
    assert {"contracting", "exchange"} <= set(FEATURES)


def test_contracting_is_growth_and_agency(company):
    _on_plan(company, Plan.GROWTH)
    assert has_feature(company, "contracting") is True
    _on_plan(company, Plan.AGENCY)
    assert has_feature(company, "contracting") is True
    _on_plan(company, Plan.STARTER)
    assert has_feature(company, "contracting") is False


def test_exchange_is_agency_only(company):
    _on_plan(company, Plan.AGENCY)
    assert has_feature(company, "exchange") is True
    for code in (Plan.GROWTH, Plan.STARTER):
        _on_plan(company, code)
        assert has_feature(company, "exchange") is False


def test_subscription_is_prorated_in_the_month_the_trial_ends(company, owner):
    """A trial ending on the 1st bills (days_in_month - 1)/days_in_month of the plan."""
    import calendar
    from decimal import ROUND_HALF_UP

    now = timezone.now()
    trial_end = now.replace(day=1, hour=12, minute=0, second=0, microsecond=0)
    _on_plan(company, Plan.GROWTH, trial_ends_at=trial_end)
    invoice = invoicing.build_monthly_invoice(company, now.year, now.month)
    line = _lines(invoice)["SUBSCRIPTION"]
    days = calendar.monthrange(now.year, now.month)[1]
    expected = (Decimal("4999") * Decimal(days - 1) / Decimal(days)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    assert Decimal(line["total_inr"]) == expected
    assert "after trial" in line["label"]


@pytest.mark.django_db
def test_bill_month_without_arguments_bills_the_month_that_just_ended(company, owner, monkeypatch):
    """Run from cron on the 1st, it must invoice the finished month.

    Defaulting to "now" produced an invoice for a month a few hours old holding
    only the plan fee, and the unique (company, period_start) constraint then
    made that empty invoice permanent - the finished month's success fees,
    AI overage, BGV and exchange charges were never billed.
    """
    from datetime import datetime

    from django.core.management import call_command

    from billing.management.commands import bill_month as command_module

    billed = []
    monkeypatch.setattr(
        command_module,
        "build_monthly_invoice",
        lambda company, year, month, with_pdf=False: billed.append((year, month)),
    )
    monkeypatch.setattr(
        command_module.timezone,
        "now",
        lambda: datetime(2026, 10, 1, 20, 30, tzinfo=UTC),
    )

    call_command("bill_month")

    assert billed and {(y, m) for y, m in billed} == {(2026, 9)}


@pytest.mark.django_db
def test_explicit_year_and_month_are_still_honoured(company, owner, monkeypatch):
    from django.core.management import call_command

    from billing.management.commands import bill_month as command_module

    billed = []
    monkeypatch.setattr(
        command_module,
        "build_monthly_invoice",
        lambda company, year, month, with_pdf=False: billed.append((year, month)),
    )

    call_command("bill_month", year=2026, month=3)

    assert {(y, m) for y, m in billed} == {(2026, 3)}


@pytest.mark.django_db
def test_expired_trial_without_a_card_goes_past_due_so_dunning_chases_it(company, owner):
    """Landing on ACTIVE meant nobody was ever asked to pay."""
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    from billing.models import Subscription
    from billing.services import get_subscription

    subscription = get_subscription(company)
    subscription.status = Subscription.TRIALING
    subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    subscription.razorpay_customer_id = ""
    subscription.stripe_customer_id = ""
    subscription.save()

    call_command("expire_trials")

    subscription.refresh_from_db()
    assert subscription.status == Subscription.PAST_DUE
    assert subscription.past_due_since is not None


@pytest.mark.django_db
def test_expired_trial_with_a_card_stays_active(company, owner):
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    from billing.models import Subscription
    from billing.services import get_subscription

    subscription = get_subscription(company)
    subscription.status = Subscription.TRIALING
    subscription.trial_ends_at = timezone.now() - timedelta(days=1)
    subscription.razorpay_customer_id = "cust_live"
    subscription.save()

    call_command("expire_trials")

    subscription.refresh_from_db()
    assert subscription.status == Subscription.ACTIVE


@pytest.mark.django_db
def test_trial_ending_reminder_is_sent_once_per_threshold(company, owner, mailoutbox):
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    from billing.models import Subscription
    from billing.services import get_subscription

    subscription = get_subscription(company)
    subscription.status = Subscription.TRIALING
    subscription.trial_ends_at = timezone.now() + timedelta(hours=12)
    subscription.save()

    call_command("expire_trials")
    first = len(mailoutbox)
    call_command("expire_trials")

    assert first >= 1
    assert len(mailoutbox) == first  # a second run must not re-send
    subscription.refresh_from_db()
    assert 1 in subscription.trial_warned_days
