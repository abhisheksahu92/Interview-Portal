"""Upload validation for onboarding documents.

Same shape as :mod:`jobs.validators` — extension, size cap and magic-byte sniff
so a renamed executable cannot pose as a PAN card — with images added, because
most onboarding artefacts arrive as a phone photo.
"""

import os

from django.core.exceptions import ValidationError

from jobs.validators import _DOC_MAGIC, _PDF_MAGIC, _ZIP_MAGIC, _head

DOCUMENT_MAX_BYTES = 5 * 1024 * 1024
DOCUMENT_ALLOWED_EXTENSIONS = (
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
)

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def validate_document_file(value):
    """Validate an onboarding document's extension, size and magic bytes."""
    name = getattr(value, "name", "") or ""
    extension = os.path.splitext(name)[1].lower()
    if extension not in DOCUMENT_ALLOWED_EXTENSIONS:
        raise ValidationError(
            "Upload a PDF, Word, text or image file (got “%(ext)s”).",
            params={"ext": extension or name},
            code="document_extension",
        )

    size = getattr(value, "size", None)
    if size is not None and size > DOCUMENT_MAX_BYTES:
        raise ValidationError(
            "Documents must be 5 MB or smaller.", code="document_too_large"
        )

    head = _head(value)
    if not head:
        return value
    expected = {
        ".pdf": (_PDF_MAGIC,),
        ".docx": (_ZIP_MAGIC,),
        ".doc": (_DOC_MAGIC, _ZIP_MAGIC),
        ".png": (_PNG_MAGIC,),
        ".jpg": (_JPEG_MAGIC,),
        ".jpeg": (_JPEG_MAGIC,),
    }.get(extension)
    if expected and not head.startswith(expected):
        raise ValidationError(
            "That file is not a valid %(ext)s file.",
            params={"ext": extension.lstrip(".").upper()},
            code="document_content",
        )
    return value
