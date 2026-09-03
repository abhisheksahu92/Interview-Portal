"""Upload validation helpers for the jobs app (currently résumé files)."""

import os

from django.core.exceptions import ValidationError

RESUME_MAX_BYTES = 5 * 1024 * 1024
RESUME_ALLOWED_EXTENSIONS = (".pdf", ".doc", ".docx", ".txt")

#: Leading magic bytes for the formats we can sniff.
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"  # .docx is a zip container
_DOC_MAGIC = b"\xd0\xcf\x11\xe0"  # legacy OLE .doc


def _head(uploaded, size=8):
    """Read the first ``size`` bytes of a file-like object without consuming it."""
    try:
        position = uploaded.tell()
    except (AttributeError, OSError):
        position = None
    try:
        uploaded.seek(0)
        head = uploaded.read(size) or b""
    except (AttributeError, OSError, ValueError):
        return b""
    finally:
        try:
            uploaded.seek(position or 0)
        except (AttributeError, OSError, ValueError):
            pass
    if isinstance(head, str):  # pragma: no cover - text-mode handles
        head = head.encode("utf-8", "ignore")
    return head


def validate_resume_file(value):
    """Validate extension, size and (for PDF/DOC/DOCX) the file's magic bytes."""
    name = getattr(value, "name", "") or ""
    extension = os.path.splitext(name)[1].lower()
    if extension not in RESUME_ALLOWED_EXTENSIONS:
        raise ValidationError(
            "Upload a PDF, DOC, DOCX or TXT file (got “%(ext)s”).",
            params={"ext": extension or name},
            code="resume_extension",
        )

    size = getattr(value, "size", None)
    if size is not None and size > RESUME_MAX_BYTES:
        raise ValidationError(
            "Résumé files must be 5 MB or smaller.", code="resume_too_large"
        )

    head = _head(value)
    if not head:
        return value
    if extension == ".pdf" and not head.startswith(_PDF_MAGIC):
        raise ValidationError(
            "That file is not a valid PDF.", code="resume_not_pdf"
        )
    if extension == ".docx" and not head.startswith(_ZIP_MAGIC):
        raise ValidationError(
            "That file is not a valid DOCX document.", code="resume_not_docx"
        )
    if extension == ".doc" and not head.startswith((_DOC_MAGIC, _ZIP_MAGIC)):
        raise ValidationError(
            "That file is not a valid Word document.", code="resume_not_doc"
        )
    return value
