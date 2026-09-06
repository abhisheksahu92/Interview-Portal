"""Fixtures for the seeker tests.

``sources`` is built in parallel, so ``make_lead`` skips the test rather than
erroring when the model is not importable yet.
"""

import pytest

from core.models import Company, User
from jobs.models import CandidateProfile, Job
from seeker.services import get_profile


@pytest.fixture
def seeker_user(db):
    user = User.objects.create_user(
        email="priya@example.test", password="pw12345678", is_candidate=True
    )
    CandidateProfile.objects.create(
        user=user,
        headline="Django developer",
        resume_text="Shipped a payments API at Zeta. " "Led a team of four on a Django migration.",
    )
    return user


@pytest.fixture
def seeker(seeker_user):
    return get_profile(seeker_user)


@pytest.fixture
def make_lead(db):
    def factory(**kwargs):
        try:
            from sources.models import Lead, Source
        except ImportError:  # pragma: no cover - sources lands before release
            pytest.skip("the sources app is not available yet")
        source, _ = Source.objects.get_or_create(
            slug="manual", defaults={"name": "Pasted", "kind": "API"}
        )
        data = {
            "source": source,
            "title": "Django contractor",
            "company_name": "Zeta Labs",
            "snippet": "We need a Django contractor for a payments integration in Bengaluru.",
            "url": f"https://example.test/{kwargs.get('content_hash', 'a')}",
            "contact_email": "hiring@zeta.test",
            "content_hash": "a" * 64,
            "skills": ["python", "django"],
        }
        data.update(kwargs)
        return Lead.objects.create(**data)

    return factory


@pytest.fixture
def job(db):
    company = Company.objects.create(name="Acme Staffing")
    return Job.objects.create(company=company, title="Backend Engineer", status=Job.OPEN)
