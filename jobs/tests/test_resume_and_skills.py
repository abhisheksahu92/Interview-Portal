"""Résumé upload validation, old-file cleanup and de-duplicated skill names."""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from jobs.models import CandidateProfile, Skill
from jobs.validators import RESUME_MAX_BYTES, validate_resume_file

PDF = b"%PDF-1.7\n%%EOF\n"
DOCX = b"PK\x03\x04" + b"0" * 40


def _upload(name, content, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, content, content_type=content_type)


@pytest.mark.parametrize(
    "name,content",
    [("cv.pdf", PDF), ("cv.docx", DOCX), ("cv.txt", b"plain text cv")],
)
def test_valid_resumes_pass(name, content):
    assert validate_resume_file(_upload(name, content)) is not None


def test_rejects_disallowed_extension():
    with pytest.raises(ValidationError) as exc:
        validate_resume_file(_upload("cv.exe", b"MZ"))
    assert exc.value.code == "resume_extension"


def test_rejects_pdf_with_wrong_magic_bytes():
    with pytest.raises(ValidationError) as exc:
        validate_resume_file(_upload("cv.pdf", b"<html>not a pdf</html>"))
    assert exc.value.code == "resume_not_pdf"


def test_rejects_docx_with_wrong_magic_bytes():
    with pytest.raises(ValidationError) as exc:
        validate_resume_file(_upload("cv.docx", b"not a zip"))
    assert exc.value.code == "resume_not_docx"


def test_rejects_oversized_file():
    big = _upload("cv.pdf", PDF + b"0" * 16)
    big.size = RESUME_MAX_BYTES + 1
    with pytest.raises(ValidationError) as exc:
        validate_resume_file(big)
    assert exc.value.code == "resume_too_large"


@pytest.mark.django_db
def test_model_full_clean_uses_the_validator(candidate):
    candidate.resume = _upload("cv.exe", b"MZ")
    with pytest.raises(ValidationError):
        candidate.full_clean()


@pytest.mark.django_db
def test_replacing_resume_deletes_the_old_file(candidate, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    candidate.resume.save("first.pdf", ContentFile(PDF), save=True)
    first_name = candidate.resume.name
    storage = candidate.resume.storage
    assert storage.exists(first_name)

    candidate.resume.save("second.pdf", ContentFile(PDF), save=True)
    assert candidate.resume.name != first_name
    assert not storage.exists(first_name)


@pytest.mark.django_db
def test_clearing_resume_deletes_the_file(candidate, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    candidate.resume.save("only.pdf", ContentFile(PDF), save=True)
    name = candidate.resume.name
    storage = candidate.resume.storage

    candidate.resume = ""
    candidate.save()

    assert not storage.exists(name)


@pytest.mark.django_db
def test_distinct_by_name_collapses_per_tenant_rows(company, other_company):
    Skill.objects.create(company=company, name="Python")
    Skill.objects.create(company=other_company, name="python")
    Skill.objects.create(company=company, name="Django")

    names = [s.name for s in Skill.objects.distinct_by_name()]
    assert names == ["Django", "Python"]


@pytest.mark.django_db
def test_distinct_by_name_keeps_m2m_semantics(company, other_company, candidate):
    keep = Skill.objects.create(company=company, name="Python")
    Skill.objects.create(company=other_company, name="Python")
    candidate.skills.set(Skill.objects.distinct_by_name())
    assert list(candidate.skills.all()) == [keep]
    assert isinstance(candidate.skills.first(), Skill)
    assert CandidateProfile.objects.filter(skills=keep).count() == 1
