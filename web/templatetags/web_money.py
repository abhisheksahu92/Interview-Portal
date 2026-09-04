"""``{% load web_money %}`` — money formatting for job/candidate screens.

Salaries on this platform are quoted in INR, which groups digits 2-2-3 from the
right (``12,50,000``) rather than 3-3-3, which ``offers.rendering.format_money``
(built for offer letters, and Western-grouped) does not do — so the grouping
lives here instead, deliberately duplicated rather than imported so a change to
offer-letter formatting can never silently reshape a public job page.
"""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()

CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}


def indian_group(digits: str) -> str:
    """Group a run of digits the Indian way: last three, then pairs."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join([*parts, tail])


@register.filter(name="inr")
def inr(value):
    """Indian-grouped amount without a currency symbol (blank when unusable)."""
    if value is None or value == "":
        return ""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ArithmeticError, ValueError, TypeError):
        return str(value)
    negative = amount < 0
    amount = abs(amount)
    if amount == amount.to_integral():
        body = indian_group(str(int(amount)))
    else:
        # Keep the stored scale (2dp for a salary) rather than normalising it
        # away: "12,50,000.50" is money, "12,50,000.5" is not.
        whole, _, frac = f"{amount:f}".partition(".")
        body = f"{indian_group(whole)}.{frac}"
    return f"-{body}" if negative else body


@register.filter(name="currency_symbol")
def currency_symbol(code):
    """``₹`` for INR, else the code itself followed by a space."""
    code = (code or "INR").upper()
    return CURRENCY_SYMBOLS.get(code, f"{code} ")


@register.simple_tag(name="salary_range")
def salary_range(job):
    """``₹12,00,000 – ₹18,00,000 per year`` for a job, or "" when not shown."""
    if not getattr(job, "salary_published", False):
        return ""
    symbol = currency_symbol(job.salary_currency)
    low, high = job.salary_min, job.salary_max
    if low is not None and high is not None and low != high:
        amount = f"{symbol}{inr(low)} – {symbol}{inr(high)}"
    else:
        amount = f"{symbol}{inr(low if low is not None else high)}"
    return f"{amount} {job.get_salary_period_display()}"
