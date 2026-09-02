import pytest

from core.models import Company, Membership, User


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme Staffing")


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
