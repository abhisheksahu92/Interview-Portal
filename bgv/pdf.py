"""Verification report PDF (xhtml2pdf — already pinned in requirements.txt)."""

import logging
from io import BytesIO

from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def render_report_pdf(order):
    """The completed order rendered to PDF bytes, or ``None`` when unavailable.

    A missing/failing xhtml2pdf must never break the money flow: the order still
    completes, it just has no downloadable file.
    """
    try:
        from xhtml2pdf import pisa
    except Exception as exc:  # pragma: no cover - dependency is pinned
        logger.warning("bgv: xhtml2pdf unavailable, report PDF skipped: %s", exc)
        return None
    from partners.whitelabel import brand_for

    html = render_to_string(
        "bgv/pdf/report.html",
        {"order": order, "rows": order.result_rows, "brand": brand_for(order.company)},
    )
    buffer = BytesIO()
    result = pisa.CreatePDF(src=html, dest=buffer, encoding="utf-8")
    if result.err:
        logger.warning("bgv: xhtml2pdf reported errors for order %s", order.pk)
        return None
    return buffer.getvalue()
