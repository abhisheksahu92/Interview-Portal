"""Project-wide test fixtures.

Settings are loaded from the developer's own ``.env``, so whichever gateway
keys happen to be present on that machine would otherwise leak into the test
run. Tests that assert "billing is not configured" then pass on CI and fail on
a machine with real keys. Payment credentials are therefore cleared for every
test; the handful of tests that need a configured gateway set them explicitly.
"""

import pytest


@pytest.fixture(autouse=True)
def _no_ambient_payment_credentials(settings):
    settings.RAZORPAY_KEY_ID = ""
    settings.RAZORPAY_KEY_SECRET = ""
    settings.RAZORPAY_WEBHOOK_SECRET = ""
    settings.STRIPE_SECRET_KEY = ""
    settings.STRIPE_PUBLISHABLE_KEY = ""
    settings.STRIPE_WEBHOOK_SECRET = ""
