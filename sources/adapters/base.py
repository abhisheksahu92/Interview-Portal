"""The adapter contract plus the small helpers every adapter needs.

An adapter's only job is to turn one feed's payload into :class:`RawItem`
objects. Normalising, hashing, deduping and skill tagging all happen once in
:mod:`sources.services`, so adapters stay boring and testable against a
recorded fixture.
"""

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sources.models import SNIPPET_CHARS

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class RawItem:
    """One posting as the adapter read it, before normalisation."""

    external_id: str
    title: str
    url: str
    kind: str = "JOB"
    company_name: str = ""
    snippet: str = ""
    contact_email: str = ""
    location: str = ""
    remote: bool = False
    salary_min: object = None
    salary_max: object = None
    currency: str = ""
    budget_text: str = ""
    tags: list = field(default_factory=list)
    posted_at: object = None


class Adapter:
    """Subclasses set ``slug`` and implement ``fetch``."""

    slug = ""
    #: Human name used when the seed migration creates the Source row.
    name = ""
    kind = "API"

    def fetch(self, source):
        """Yield :class:`RawItem`. May raise; the runner records the failure."""
        raise NotImplementedError


def strip_html(value):
    """HTML to a single line of text. Feeds mix HTML and plain text freely."""
    text = _TAG_RE.sub(" ", value or "")
    return _WS_RE.sub(" ", html.unescape(text)).strip()


def snippet_of(value, limit=SNIPPET_CHARS):
    """A short excerpt — we never store somebody else's full posting."""
    return strip_html(value)[:limit]


def parse_dt(value):
    """Best-effort timestamp from the many shapes feeds use, else ``None``."""
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    text = str(value).strip()
    if text.isdigit():
        return datetime.fromtimestamp(int(text), tz=UTC)
    text = text.replace("Z", "+00:00")
    for candidate in (text, text[:19], text[:10]):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def looks_remote(*values):
    haystack = " ".join(str(v or "") for v in values).lower()
    return "remote" in haystack or "anywhere" in haystack or "work from home" in haystack
