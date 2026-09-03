import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from django.utils import timezone

from billing.models import Subscription
from core.models import Company, Membership, User


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    """Keep generated invoice PDFs out of the repo."""
    settings.MEDIA_ROOT = str(tmp_path / "media")
    return settings.MEDIA_ROOT


def end_trial(company):
    """Push a company past its 14-day trial (most tests want steady state)."""
    Subscription.objects.filter(company=company).update(
        status=Subscription.ACTIVE, trial_ends_at=timezone.now() - timedelta(days=1)
    )
    company.refresh_from_db()
    return company


@pytest.fixture
def trial_company(db):
    """A brand-new company, still inside its trial."""
    return Company.objects.create(name="Fresh Start Ltd")


@pytest.fixture
def company(db):
    """A company whose trial has ended (billed on FREE unless a test upgrades)."""
    return end_trial(Company.objects.create(name="Acme Staffing"))


def _member(company, email, role):
    user = User.objects.create_user(email=email, password="pw12345678")
    Membership.objects.create(user=user, company=company, role=role)
    return user


@pytest.fixture
def owner(company):
    return _member(company, "owner@acme.test", Membership.OWNER)


@pytest.fixture
def recruiter(company):
    return _member(company, "rec@acme.test", Membership.RECRUITER)


class FakeStripe:
    """Stand-in for the stripe SDK. Records calls, never touches the network."""

    class _Sessions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return {"id": "cs_test_1", "url": "https://stripe.test/session"}

    class _Webhook:
        valid = True

        @classmethod
        def construct_event(cls, payload, signature, secret):
            if not cls.valid or signature != "good-signature":
                raise ValueError("Invalid signature")
            import json

            return json.loads(payload)

    def __init__(self):
        self.api_key = None
        self.checkout = type("checkout", (), {"Session": self._Sessions()})()
        self.billing_portal = type("billing_portal", (), {"Session": self._Sessions()})()
        self.Webhook = self._Webhook


@pytest.fixture
def fake_stripe(monkeypatch, settings):
    """Patch the gateway's single import seam with a fake stripe module."""
    settings.STRIPE_SECRET_KEY = "sk_test_123"
    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
    settings.STRIPE_PRICE_ID_PRO = "price_pro_123"
    stub = FakeStripe()
    monkeypatch.setattr("billing.gateway.get_stripe", lambda: stub)
    return stub


class FakeRazorpay:
    """Stand-in for the razorpay SDK client; records calls, no network."""

    def __init__(self):
        self.calls = []
        self.plan = self._Resource(self, "plan", "plan_test_1")
        self.subscription = self._Resource(self, "subscription", "sub_test_1")
        self.order = self._Resource(self, "order", "order_test_1")

    class _Resource:
        def __init__(self, parent, name, remote_id):
            self.parent = parent
            self.name = name
            self.remote_id = remote_id

        def create(self, data):
            self.parent.calls.append((self.name, data))
            return {"id": self.remote_id, **data}


@pytest.fixture
def fake_razorpay(monkeypatch, settings):
    settings.RAZORPAY_KEY_ID = "rzp_test_key"
    settings.RAZORPAY_KEY_SECRET = "rzp_test_secret"
    settings.RAZORPAY_WEBHOOK_SECRET = "rzp_hook_secret"
    stub = FakeRazorpay()
    monkeypatch.setattr("billing.razorpay_gateway.get_client", lambda: stub)
    return stub


def razorpay_signature(payload, secret):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), body
