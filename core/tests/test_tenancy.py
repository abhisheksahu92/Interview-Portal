"""Tests for tenant isolation, multi-hop scoping, and cross-tenant security."""

import pytest
from core.models import Company, Membership, User
from core.tenancy import for_company, get_company_lookup
from jobs.models import Application, CandidateProfile, Job, PipelineStage



@pytest.fixture
def company_a(db):
    return Company.objects.create(name="Company A", slug="company-a")


@pytest.fixture
def company_b(db):
    return Company.objects.create(name="Company B", slug="company-b")


@pytest.fixture
def job_a(company_a):
    return Job.objects.create(company=company_a, title="Job A", description="Desc")


@pytest.fixture
def job_b(company_b):
    return Job.objects.create(company=company_b, title="Job B", description="Desc")


@pytest.fixture
def stage_a(job_a):
    return job_a.stages.first()


@pytest.fixture
def stage_b(job_b):
    return job_b.stages.first()


@pytest.fixture
def candidate_user(db):
    return User.objects.create(email="cand@example.com")


@pytest.fixture
def candidate_profile(candidate_user):
    return CandidateProfile.objects.create(user=candidate_user)


@pytest.fixture
def application_a(job_a, candidate_profile, stage_a):
    return Application.objects.create(
        job=job_a,
        candidate=candidate_profile,
        current_stage=stage_a,
    )


@pytest.fixture
def application_b(job_b, candidate_profile, stage_b):
    return Application.objects.create(
        job=job_b,
        candidate=candidate_profile,
        current_stage=stage_b,
    )


def test_get_company_lookup_direct_and_indirect():
    assert get_company_lookup(Job) == "company"
    assert get_company_lookup(PipelineStage) == "job__company"
    assert get_company_lookup(Application) == "job__company"


def test_for_company_direct_scoping(company_a, company_b, job_a, job_b):
    # Company A sees only job A
    qs_a = for_company(Job.objects.all(), company_a)
    assert list(qs_a) == [job_a]

    # Company B sees only job B
    qs_b = for_company(Job.objects.all(), company_b)
    assert list(qs_b) == [job_b]

    # None returns empty queryset, preventing leak
    assert for_company(Job.objects.all(), None).count() == 0


def test_for_company_multihop_traversal(company_a, company_b, stage_a, stage_b, application_a, application_b):
    # Stages traversal via job__company
    stages_a = for_company(PipelineStage.objects.all(), company_a)
    assert stages_a.count() > 0
    assert set(stages_a.values_list("job__company_id", flat=True)) == {company_a.id}

    stages_b = for_company(PipelineStage.objects.all(), company_b)
    assert stages_b.count() > 0
    assert set(stages_b.values_list("job__company_id", flat=True)) == {company_b.id}

    assert for_company(PipelineStage.objects.all(), None).count() == 0

    # Applications traversal via job__company
    assert list(for_company(Application.objects.all(), company_a)) == [application_a]
    assert list(for_company(Application.objects.all(), company_b)) == [application_b]
    assert for_company(Application.objects.all(), None).count() == 0
