"""Hacker News' monthly hiring threads, through the Algolia search API.

Two threads matter, both posted by ``whoishiring``: "Who is hiring?" (jobs) and
"Freelancer? Seeking freelancer?" (freelance). We find the newest of each that
is still recent, then pull their *top-level* comments - one comment is one
posting. Titles on HN are free text, so the company is taken as the text before
the first pipe, which is the convention both threads have used for years.

Two lessons from the first live run. HN stopped posting the freelancer thread
after October 2025, so "newest" alone picked a year-old thread; anything older
than ``MAX_THREAD_AGE_DAYS`` is now ignored. And that thread mixes demand and
supply: posts opening with "SEEKING WORK" are freelancers advertising
themselves, not clients, and a seeker must never be handed another seeker's
address as a lead.
"""

import re
from datetime import UTC, datetime, timedelta

from sources.adapters.base import Adapter, RawItem, parse_dt, snippet_of, strip_html
from sources.http import get_json

STORIES = (
    "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=48"
)
COMMENTS = (
    "https://hn.algolia.com/api/v1/search?tags=comment,story_{story_id}"
    "&hitsPerPage=100&page={page}"
)
MAX_PAGES = 10  # the hiring thread runs to ~400 top-level posts
MAX_THREAD_AGE_DAYS = 60

THREADS = (("who is hiring", "JOB"), ("freelancer", "FREELANCE"))
SUPPLY_MARKERS = ("seeking work",)
_PARA_RE = re.compile(r"<p>|<br\s*/?>|\n", re.I)


def pick_threads(stories, now=None):
    """Newest recent story id per thread kind. Algolia returns newest first."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=MAX_THREAD_AGE_DAYS)
    picked = {}
    for hit in stories.get("hits") or []:
        title = (hit.get("title") or "").lower()
        created = parse_dt(hit.get("created_at"))
        if created is not None and created < cutoff:
            continue
        for marker, kind in THREADS:
            if marker in title and kind not in picked:
                picked[kind] = str(hit.get("objectID"))
    return picked


def _shorten(text, limit):
    """Cut at a word boundary. A long first paragraph is a pitch, not a title."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" |,-") + "…"


def is_supply_post(text):
    """True for a freelancer offering their services rather than hiring."""
    head = text[:120].lower()
    return any(marker in head for marker in SUPPLY_MARKERS)


class HackerNewsAdapter(Adapter):
    slug = "hn"
    name = "Hacker News hiring threads"
    kind = "API"

    def fetch(self, source):
        for kind, story_id in pick_threads(get_json(STORIES)).items():
            for page in range(MAX_PAGES):
                payload = get_json(COMMENTS.format(story_id=story_id, page=page))
                yield from self.parse(payload, kind=kind)
                if page + 1 >= int(payload.get("nbPages") or 1):
                    break

    def parse(self, payload, *, kind="JOB"):
        for hit in payload.get("hits") or []:
            text = strip_html(hit.get("comment_text"))
            # A top-level comment hangs off the story itself; replies are
            # discussion, not postings.
            if not text or str(hit.get("parent_id")) != str(hit.get("story_id")):
                continue
            if is_supply_post(text):
                continue
            # First paragraph, not first sentence: splitting on "." mangled company
            # URLs such as "vlm.run" into "vlm". HN separates paragraphs with <p>.
            first_para = _PARA_RE.split(hit.get("comment_text") or "", 1)[0]
            headline = _shorten(strip_html(first_para), 140)
            company = headline.split("|")[0].strip()[:200]
            yield RawItem(
                external_id=str(hit.get("objectID") or ""),
                kind=kind,
                title=headline,
                url=f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                company_name=company,
                snippet=snippet_of(text),
                remote="remote" in text.lower(),
                posted_at=parse_dt(hit.get("created_at")),
            )
