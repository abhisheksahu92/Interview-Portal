import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from billing.models import Plan, Subscription
from clients.models import Client, ClientAccess, Submission
from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job


def _member(company, email, role):
    user = User.objects.create_user(email=email, password="pw12345678")
    Membership.objects.create(user=user, company=company, role=role)
    return user


def enable_client_portal(company, enabled=True):
    """Put ``company`` on a paid plan whose client_portal flag is ``enabled``.

    A *paid* plan is used in both directions so the 14-day trial (which grants
    every flag) cannot mask the disabled case.
    """
    plan, _ = Plan.objects.get_or_create(
        code="PRO" if enabled else "STARTER",
        defaults={"name": "Pro" if enabled else "Starter"},
    )
    plan.features = {**(plan.features or {}), "client_portal": enabled}
    plan.save(update_fields=["features"])
    defaults = {"plan": plan, "status": Subscription.ACTIVE}
    if any(f.name == "trial_ends_at" for f in Subscription._meta.get_fields()):
        defaults["trial_ends_at"] = None
    Subscription.objects.update_or_create(company=company, defaults=defaults)
    return plan


@pytest.fixture
def company(db):
    company = Company.objects.create(name="Acme Staffing")
    enable_client_portal(company)
    return company


@pytest.fixture
def other_company(db):
    company = Company.objects.create(name="Globex Tech")
    enable_client_portal(company)
    return company


@pytest.fixture
def owner(company):
    return _member(company, "owner@acme.test", Membership.OWNER)


@pytest.fixture
def recruiter(company):
    return _member(company, "rec@acme.test", Membership.RECRUITER)


@pytest.fixture
def interviewer(company):
    return _member(company, "int@acme.test", Membership.INTERVIEWER)


@pytest.fixture
def other_owner(other_company):
    return _member(other_company, "owner@globex.test", Membership.OWNER)


@pytest.fixture
def make_client_row(db):
    def factory(company, name="Initech"):
        return Client.objects.create(
            company=company, name=name, contact_email="hr@initech.test"
        )

    return factory


@pytest.fixture
def client_row(company, make_client_row):
    return make_client_row(company)


@pytest.fixture
def make_job(db):
    def factory(company, title="Django Developer", client=None):
        return Job.objects.create(
            company=company, title=title, status=Job.OPEN, client=client
        )

    return factory


@pytest.fixture
def job(company, client_row, make_job):
    return make_job(company, client=client_row)


@pytest.fixture
def make_application(db):
    counter = {"n": 0}

    def factory(job, resume=False, email=None):
        counter["n"] += 1
        user = User.objects.create_user(
            email=email or f"cand{counter['n']}@example.test",
            password="pw12345678",
            is_candidate=True,
        )
        profile = CandidateProfile.objects.create(
            user=user,
            experience_years=4,
            headline="Senior Django engineer",
        )
        if resume:
            profile.resume = SimpleUploadedFile(
                "cv.pdf", b"%PDF-1.4 fake resume", content_type="application/pdf"
            )
            profile.save()
        return Application.objects.create(
            job=job,
            candidate=profile,
            current_stage=job.first_stage,
            ai_summary="Strong match on Django and DRF.",
            ai_fit_score=82,
        )

    return factory


@pytest.fixture
def application(job, make_application):
    return make_application(job)


@pytest.fixture
def submission(application, client_row, owner):
    return Submission.objects.create(
        application=application, client=client_row, submitted_by=owner, note="Great fit"
    )


@pytest.fixture
def access(client_row):
    from clients.services import issue_access

    return issue_access(client_row, "hr@initech.test", valid_days=14)


@pytest.fixture
def revoked_access(client_row):
    access = ClientAccess.objects.create(client=client_row, email="old@initech.test")
    access.revoke()
    return access


@pytest.fixture(autouse=True)
def _media_root(settings, tmp_path):
    """Keep uploaded logos/resumes out of the real MEDIA_ROOT."""
    settings.MEDIA_ROOT = str(tmp_path / "media")
    return settings.MEDIA_ROOT
