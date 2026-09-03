import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job
from video.models import VideoInvite, VideoQuestion, VideoScreen, VideoScreenQuestion


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme Staffing")


@pytest.fixture(autouse=True)
def fast_hasher(settings):
    """Cheap password hashing keeps this suite quick."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    return settings.PASSWORD_HASHERS


@pytest.fixture(autouse=True)
def media_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    return settings.MEDIA_ROOT


@pytest.fixture
def video_plan(company):
    """Put ``company`` on a plan that includes the video feature."""
    from billing.models import Plan, Subscription

    plan = Plan.objects.get(code=Plan.PRO)
    features = dict(plan.features or {})
    features["video"] = True
    plan.features = features
    plan.save(update_fields=["features"])
    Subscription.objects.update_or_create(
        company=company, defaults={"plan": plan, "status": Subscription.ACTIVE}
    )
    company.refresh_from_db()
    return plan


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
def job(company, owner):
    return Job.objects.create(
        company=company,
        title="Python Engineer",
        location="Pune",
        description="Build things",
        requirements="Python",
        status=Job.OPEN,
        created_by=owner,
    )


@pytest.fixture
def candidate(db):
    user = User.objects.create_user(
        email="cand@example.test", password="pw12345678", is_candidate=True
    )
    return CandidateProfile.objects.create(user=user, experience_years=3)


@pytest.fixture
def question(company):
    return VideoQuestion.objects.create(
        company=company, text="Tell us about yourself", think_seconds=10,
        answer_seconds=60, order=0,
    )


@pytest.fixture
def screen(job, question):
    screen = VideoScreen.objects.create(job=job, title="Intro screen", deadline_days=5)
    VideoScreenQuestion.objects.create(screen=screen, question=question, order=0)
    return screen


@pytest.fixture
def application(job, candidate):
    """An application parked on a stage with no video screen."""
    stage = job.stages.last()
    return Application.objects.create(job=job, candidate=candidate, current_stage=stage)


@pytest.fixture
def invite(application, screen):
    return VideoInvite.objects.create(application=application, screen=screen)


#: Real container magic bytes, so uploads survive the sniffing in
#: :mod:`video.validators` the way a browser recording would.
WEBM_HEADER = b"\x1a\x45\xdf\xa3"
MP4_HEADER = b"\x00\x00\x00\x18ftypisom"


def webm_upload(name="answer.webm", size=1024, content_type="video/webm"):
    """A tiny in-memory WebM recording."""
    body = WEBM_HEADER + b"0" * max(0, size - len(WEBM_HEADER))
    return SimpleUploadedFile(name, body, content_type=content_type)


def mp4_upload(name="answer.mp4", size=1024, content_type="video/mp4"):
    """A tiny in-memory MP4 recording (valid ``ftyp``, no ``mvhd``)."""
    body = MP4_HEADER + b"0" * max(0, size - len(MP4_HEADER))
    return SimpleUploadedFile(name, body, content_type=content_type)


def bogus_upload(name="answer.webm", content_type="video/webm"):
    """A file that claims to be a recording but is really something else."""
    return SimpleUploadedFile(name, b"%PDF-1.7 not a video at all", content_type=content_type)
