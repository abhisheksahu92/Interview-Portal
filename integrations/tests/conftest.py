"""Fixtures for the integrations tests.

Nothing here touches the network: :func:`responder` and the ``patch_post``
fixture replace ``integrations.delivery.post`` with an in-memory recorder, and
connector adapters are patched at their ``request`` seam.
"""

from dataclasses import dataclass, field

import pytest

from billing.entitlements import FEATURES
from billing.models import Plan, Subscription
from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job


@dataclass
class FakeResponse:
    status_code: int = 200
    text: str = "ok"


@dataclass
class Recorder:
    """Stands in for ``integrations.delivery.post``."""

    status_code: int = 200
    raises: Exception | None = None
    calls: list = field(default_factory=list)

    def __call__(self, url, body, headers, timeout=None):
        self.calls.append(
            {"url": url, "body": body, "headers": headers, "timeout": timeout}
        )
        if self.raises is not None:
            raise self.raises
        return FakeResponse(self.status_code)

    @property
    def last(self):
        return self.calls[-1]


@pytest.fixture
def responder(monkeypatch):
    """Patch the single outbound HTTP seam and hand back the recorder."""
    from integrations import delivery

    recorder = Recorder()
    monkeypatch.setattr(delivery, "post", recorder)
    return recorder


def _agency(company):
    plan = Plan.objects.get(code=Plan.AGENCY)
    plan.features = dict(plan.features or {}, **dict.fromkeys(FEATURES, True))
    plan.save(update_fields=["features"])
    Subscription.objects.update_or_create(
        company=company, defaults={"plan": plan, "status": Subscription.ACTIVE}
    )
    company.refresh_from_db()
    return company


@pytest.fixture
def company(db):
    return _agency(Company.objects.create(name="Acme Staffing"))


@pytest.fixture
def other_company(db):
    return _agency(Company.objects.create(name="Beta Consulting"))


@pytest.fixture
def free_company(db):
    """A company on FREE with an expired trial: no ``integrations`` feature."""
    from datetime import timedelta

    from django.utils import timezone

    company = Company.objects.create(name="Thrifty Hiring")
    Subscription.objects.update_or_create(
        company=company,
        defaults={
            "plan": Plan.objects.get(code=Plan.FREE),
            "status": Subscription.ACTIVE,
            "trial_ends_at": timezone.now() - timedelta(days=1),
        },
    )
    company.refresh_from_db()
    return company


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


@pytest.fixture
def other_owner(other_company):
    return _member(other_company, "owner@beta.test", Membership.OWNER)


@pytest.fixture
def free_owner(free_company):
    return _member(free_company, "owner@thrifty.test", Membership.OWNER)


@pytest.fixture
def job(company):
    return Job.objects.create(company=company, title="Python Developer", status=Job.OPEN)


@pytest.fixture
def candidate(db):
    user = User.objects.create_user(
        email="cand@example.com",
        password="pw12345678",
        first_name="Asha",
        last_name="Rao",
        is_candidate=True,
    )
    return CandidateProfile.objects.create(user=user, phone="+919000000000")


@pytest.fixture
def application(job, candidate):
    return Application.objects.create(
        job=job, candidate=candidate, current_stage=job.first_stage
    )


@pytest.fixture
def webhook(company, owner):
    from integrations.models import OutboundWebhook

    return OutboundWebhook.objects.create(
        company=company,
        name="Ops receiver",
        url="https://hooks.example.com/ip",
        events=[],
        created_by=owner,
    )


@pytest.fixture
def logged_in(client, owner):
    client.force_login(owner)
    return client
