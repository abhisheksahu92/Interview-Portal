import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from contracting.validators import DOCUMENT_MAX_BYTES, validate_document_file
from jobs.validators import _DOC_MAGIC, _PDF_MAGIC, _ZIP_MAGIC

PDF = _PDF_MAGIC + b"1.7\n%%EOF\n"
DOCX = _ZIP_MAGIC + b"0" * 40
DOC = _DOC_MAGIC + b"0" * 40
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40
JPG = b"\xff\xd8\xff" + b"0" * 40

def _upload(name, content, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, content, content_type=content_type)

@pytest.mark.parametrize(
    "name,content",
    [
        ("doc.pdf", PDF),
        ("doc.docx", DOCX),
        ("doc.doc", DOC),
        ("doc.txt", b"plain text cv"),
        ("img.png", PNG),
        ("img.jpg", JPG),
        ("img.jpeg", JPG),
    ],
)
def test_valid_documents_pass(name, content):
    validate_document_file(_upload(name, content))

def test_rejects_disallowed_extension():
    with pytest.raises(ValidationError) as exc:
        validate_document_file(_upload("doc.exe", b"MZ"))
    assert exc.value.code == "document_extension"

@pytest.mark.parametrize(
    "name,content",
    [
        ("doc.pdf", b"<html>not a pdf</html>"),
        ("doc.docx", b"not a zip"),
        ("doc.doc", b"not a doc"),
        ("img.png", b"not a png"),
        ("img.jpg", b"not a jpg"),
        ("img.jpeg", b"not a jpeg"),
    ],
)
def test_rejects_invalid_magic_bytes(name, content):
    with pytest.raises(ValidationError) as exc:
        validate_document_file(_upload(name, content))
    assert exc.value.code == "document_content"

def test_rejects_oversized_file():
    big = _upload("doc.pdf", PDF + b"0" * 16)
    big.size = DOCUMENT_MAX_BYTES + 1
    with pytest.raises(ValidationError) as exc:
        validate_document_file(big)
    assert exc.value.code == "document_too_large"
