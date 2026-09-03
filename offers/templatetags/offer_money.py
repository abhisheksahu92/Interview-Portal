"""``{% load offer_money %}`` — money formatting shared by offer screens.

The rendered offer body formats ``{{salary}}`` through
:func:`offers.rendering._stringify`; this filter reuses exactly that so page
chrome (e.g. the sign-page subtitle) never disagrees with the letter itself.
"""

from django import template

from offers.rendering import format_money

register = template.Library()


@register.filter(name="offer_money")
def offer_money(value):
    """Group a salary in thousands, the same way the offer body does."""
    return format_money(value)
