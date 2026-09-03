"""Offer letter PDF generation (xhtml2pdf — pinned in requirements.txt)."""

import logging
from io import BytesIO

from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


class PdfUnavailable(RuntimeError):
    """xhtml2pdf could not turn the offer HTML into a PDF."""


def html_to_pdf(html) -> bytes:
    """Render an HTML string to PDF bytes."""
    try:
        from xhtml2pdf import pisa
    except Exception as exc:  # pragma: no cover - dependency is pinned
        raise PdfUnavailable("xhtml2pdf is not installed") from exc

    buffer = BytesIO()
    result = pisa.CreatePDF(src=html, dest=buffer, encoding="utf-8")
    if getattr(result, "err", 0):
        raise PdfUnavailable("xhtml2pdf reported errors while rendering the offer")
    return buffer.getvalue()


def offer_pdf_html(offer, include_signature=None):
    """The print stylesheet + offer body used for the PDF."""
    if include_signature is None:
        include_signature = bool(offer.signed_at)
    return render_to_string(
        "offers/pdf/offer_letter.html",
        {"offer": offer, "include_signature": include_signature},
    )


def offer_pdf_bytes(offer, include_signature=None) -> bytes:
    return html_to_pdf(offer_pdf_html(offer, include_signature=include_signature))


def offer_pdf_filename(offer) -> str:
    slug = "".join(
        ch if ch.isalnum() else "-" for ch in (offer.application.job.title or "offer")
    ).strip("-")
    return f"offer-{offer.pk}-{slug.lower()[:40] or 'letter'}.pdf"
