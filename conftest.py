"""Project-wide test fixtures.

Settings are loaded from the developer's own ``.env``, so whichever gateway
keys happen to be present on that machine would otherwise leak into the test
run. Tests that assert "billing is not configured" then pass on CI and fail on
a machine with real keys. Payment credentials are therefore cleared for every
test; the handful of tests that need a configured gateway set them explicitly.

Model keys are cleared for the same reason, plus a sharper one: a real key
would make the AI tests issue billable network calls.
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


@pytest.fixture(autouse=True)
def _no_ambient_model_credentials(settings):
    settings.ANTHROPIC_API_KEY = ""
    settings.GEMINI_API_KEY = ""
