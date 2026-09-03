import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import Company, Membership, User
from jobs.models import Job, Skill

RESUME_TEXT = """Asha Rao
Senior Django Developer
asha.rao@example.test
+91 98765 43210

Summary
8 years of experience building Python and Django services.

Skills
Python, Django, PostgreSQL
"""


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme Staffing")


@pytest.fixture
def other_company(db):
    return Company.objects.create(name="Globex Tech")


def _member(company, email, role):
    user = User.objects.create_user(email=email, password="pw12345678")
    Membership.objects.create(user=user, company=company, role=role)
    return user


@pytest.fixture
def owner(company):
    return _member(company, "owner@acme.test", Membership.OWNER)


@pytest.fixture
def other_owner(other_company):
    return _member(other_company, "owner@globex.test", Membership.OWNER)


@pytest.fixture
def interviewer(company):
    return _member(company, "int@acme.test", Membership.INTERVIEWER)


@pytest.fixture
def job(company):
    return Job.objects.create(company=company, title="Django Developer", status=Job.OPEN)


@pytest.fixture
def python_skill(company):
    return Skill.objects.create(company=company, name="Python")


@pytest.fixture
def txt_resume():
    def factory(name="asha_rao_resume.txt", text=RESUME_TEXT):
        return SimpleUploadedFile(name, text.encode(), content_type="text/plain")

    return factory


@pytest.fixture
def zip_upload():
    def factory(members, name="resumes.zip"):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for member_name, text in members.items():
                archive.writestr(member_name, text)
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/zip")

    return factory


@pytest.fixture
def csv_upload():
    def factory(rows=None, name="people.csv"):
        rows = rows or [
            "name,email,phone,skills,experience",
            "Asha Rao,asha.rao@example.test,+919876543210,\"Python, Django\",8",
            "Ben Iyer,ben@example.test,+919876500000,React,4",
        ]
        return SimpleUploadedFile(name, ("\n".join(rows)).encode(), content_type="text/csv")

    return factory
