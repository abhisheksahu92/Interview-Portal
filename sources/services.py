"""Running sources, normalising what comes back, and serving leads to other apps.

The pipeline is deliberately one-way: an adapter yields
:class:`~sources.adapters.base.RawItem`, :func:`normalise` turns that into
model fields, :func:`dedupe` collapses it onto an existing row by
``content_hash``, and only genuinely new leads go through skill tagging (the
only step that costs money).

Public API for the seeker and board apps: :func:`search_leads` and
:func:`leads_for_profile`.
"""

import json
import logging
import re
import time
from datetime import UTC, timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from core import llm
from sources.adapters import ADAPTERS
from sources.models import SNIPPET_CHARS, STALE_AFTER_DAYS, Lead, Source, content_hash

logger = logging.getLogger(__name__)

# Deliberately permissive on the local part, strict on the domain - we only
# want addresses a human typed into a posting, not tracking pixels.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

#: Addresses that are never a person you can write to.
BLOCKED_EMAIL_PARTS = (
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "@example.",
    "@sentry.",
    "@domain.com",
    "@email.com",
    "@yourcompany",
)

#: Baseline vocabulary, extended at runtime with every jobs.Skill name.
BASE_SKILLS = [
    "python",
    "django",
    "flask",
    "fastapi",
    "javascript",
    "typescript",
    "react",
    "next.js",
    "vue",
    "angular",
    "node.js",
    "go",
    "rust",
    "java",
    "spring",
    "kotlin",
    "swift",
    "ios",
    "android",
    "react native",
    "flutter",
    "php",
    "laravel",
    "ruby",
    "rails",
    "c++",
    "c#",
    ".net",
    "sql",
    "postgresql",
    "mysql",
    "mongodb",
    "redis",
    "elasticsearch",
    "kafka",
    "aws",
    "gcp",
    "azure",
    "docker",
    "kubernetes",
    "terraform",
    "ansible",
    "linux",
    "devops",
    "sre",
    "ci/cd",
    "graphql",
    "rest api",
    "html",
    "css",
    "tailwind",
    "figma",
    "ui/ux",
    "product management",
    "data science",
    "machine learning",
    "deep learning",
    "nlp",
    "pytorch",
    "tensorflow",
    "pandas",
    "spark",
    "airflow",
    "dbt",
    "tableau",
    "power bi",
    "excel",
    "qa",
    "selenium",
    "cypress",
    "playwright",
    "salesforce",
    "sap",
    "wordpress",
    "shopify",
    "seo",
    "content writing",
    "copywriting",
    "video editing",
    "customer support",
    "sales",
    "recruiting",
    "accounting",
    "blockchain",
    "solidity",
    "security",
    "networking",
]

#: One LLM call per this many leads - tagging is the only paid step here.
TAG_BATCH_SIZE = 20
TAG_BATCH_PAUSE = 1.5  # seconds between batches

TAG_SYSTEM = (
    "You tag job postings with skills. Use only skills from the supplied "
    "vocabulary, lower-case, at most 8 per posting. Reply with JSON only."
)


# --------------------------------------------------------------------------- #
# Contact extraction
# --------------------------------------------------------------------------- #
def extract_contact(text):
    """First real-looking email in poster-written text, or ``""``.

    Only ever called on the snippet, which is the poster's own words — we do
    not harvest addresses out of a site's page furniture.
    """
    for match in EMAIL_RE.finditer(text or ""):
        candidate = match.group(0).strip(".,;:)").lower()
        if any(part in candidate for part in BLOCKED_EMAIL_PARTS):
            continue
        if candidate.endswith((".png", ".jpg", ".gif", ".webp")):
            continue
        return candidate[:254]
    return ""


# --------------------------------------------------------------------------- #
# Skill vocabulary and tagging
# --------------------------------------------------------------------------- #
def skill_vocabulary():
    """Built-in skills plus every distinct ``jobs.Skill`` name, lower-cased."""
    from jobs.models import Skill

    names = set(BASE_SKILLS)
    try:
        names.update(n.strip().lower() for n in Skill.objects.values_list("name", flat=True) if n)
    except Exception:  # pragma: no cover - only if jobs is mid-migration
        logger.debug("Skill table unavailable; using the built-in vocabulary only.")
    return sorted(names)


def keyword_skills(text, vocabulary=None):
    """Substring match on the vocabulary — the fallback when the LLM is off.

    Word boundaries are used where the skill is alphanumeric so that "go" does
    not match "going"; skills with punctuation (``c++``, ``ci/cd``) fall back to
    a plain substring test because ``\\b`` does not behave around symbols.
    """
    haystack = (text or "").lower()
    found = []
    for skill in vocabulary if vocabulary is not None else skill_vocabulary():
        if skill.replace(" ", "").isalnum():
            hit = re.search(rf"\b{re.escape(skill)}\b", haystack)
        else:
            hit = skill in haystack
        if hit:
            found.append(skill)
    return found[:8]


def _parse_tag_response(text, count):
    """Read the model's JSON back into a list-of-lists, or ``None``."""
    if not text:
        return None
    body = text.strip()
    start, end = body.find("["), body.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        parsed = json.loads(body[start : end + 1])
    except ValueError:
        return None
    if not isinstance(parsed, list) or len(parsed) != count:
        return None
    return [[str(s).lower() for s in row][:8] if isinstance(row, list) else [] for row in parsed]


def tag_skills(leads, vocabulary=None, *, use_llm=True):
    """Fill ``skills`` on each lead, in batches. Returns the leads touched.

    Any LLM problem — no key, bad JSON, wrong length — degrades to keyword
    matching rather than leaving leads untagged, because an untagged lead is
    invisible to the seeker feed's ranking.
    """
    leads = [lead for lead in leads if lead is not None]
    if not leads:
        return []
    vocabulary = vocabulary if vocabulary is not None else skill_vocabulary()
    for start in range(0, len(leads), TAG_BATCH_SIZE):
        if start and use_llm:
            time.sleep(TAG_BATCH_PAUSE)  # stay under the provider's per-minute quota
        batch = leads[start : start + TAG_BATCH_SIZE]
        postings = [
            {"i": i, "title": lead.title, "text": (lead.snippet or "")[:400]}
            for i, lead in enumerate(batch)
        ]
        prompt = (
            f"Vocabulary: {', '.join(vocabulary)}\n\n"
            f"Postings: {json.dumps(postings, ensure_ascii=False)}\n\n"
            f"Return a JSON array of {len(batch)} arrays of skill strings, in order."
        )
        answer = None
        if use_llm:
            answer = _parse_tag_response(
                llm.complete(prompt, system=TAG_SYSTEM, max_tokens=1500), len(batch)
            )
        for index, lead in enumerate(batch):
            allowed = set(vocabulary)
            if answer:
                lead.skills = [s for s in answer[index] if s in allowed]
            if not answer or not lead.skills:
                lead.skills = keyword_skills(f"{lead.title} {lead.snippet}", vocabulary)
    return leads


# --------------------------------------------------------------------------- #
# Normalisation and dedupe
# --------------------------------------------------------------------------- #
def normalise(item, source):
    """RawItem → a field dict ready for :class:`~sources.models.Lead`."""
    title = " ".join((item.title or "").split())[:300]
    company = " ".join((item.company_name or "").split())[:200]
    snippet = (item.snippet or "")[:SNIPPET_CHARS]
    posted_at = item.posted_at or timezone.now()
    if timezone.is_naive(posted_at):
        posted_at = posted_at.replace(tzinfo=UTC)
    return {
        "source": source,
        "external_id": str(item.external_id or "")[:128],
        "kind": item.kind or Lead.JOB,
        "title": title,
        "company_name": company,
        "snippet": snippet,
        "url": (item.url or "")[:600],
        "contact_email": item.contact_email or extract_contact(snippet),
        "location": " ".join((item.location or "").split())[:200],
        "remote": bool(item.remote),
        "salary_min": item.salary_min,
        "salary_max": item.salary_max,
        "currency": (item.currency or "")[:8],
        "budget_text": (item.budget_text or "")[:120],
        "tags": [t for t in (item.tags or []) if t][:20],
        "posted_at": posted_at,
        "fetched_at": timezone.now(),
        "content_hash": content_hash(title, company, snippet),
        "is_active": True,
        "expires_at": posted_at + timedelta(days=STALE_AFTER_DAYS),
    }


def existing_index(source, rows):
    """Two lookups for a whole payload in one query: by (source, external_id) and by hash.

    Dedupe used to issue one or two SELECTs per posting. Against a database in
    another region that was the entire runtime - a 250-item feed took four
    minutes - so the runner now prefetches everything it might match against.
    """
    by_ext, by_hash = {}, {}
    if not rows:
        return by_ext, by_hash
    ext_ids = {r["external_id"] for r in rows if r.get("external_id")}
    hashes = {r["content_hash"] for r in rows}
    matches = Lead.objects.filter(
        Q(source=source, external_id__in=ext_ids) | Q(content_hash__in=hashes)
    )
    for lead in matches:
        if lead.source_id == source.pk and lead.external_id:
            by_ext[lead.external_id] = lead
        by_hash[lead.content_hash] = lead
    return by_ext, by_hash


REFRESH_FIELDS = [
    "fetched_at",
    "expires_at",
    "is_active",
    "title",
    "snippet",
    "url",
    "company_name",
    "content_hash",
]


def dedupe(fields, index=None, *, defer_save=False):
    """Upsert by source id, then ``content_hash``. Returns ``(lead, created)``.

    An existing lead is only *refreshed* (it is still live, we saw it again) -
    its skills and contact are left alone so a re-run never re-pays for tagging.
    ``index`` is the prefetched pair from :func:`existing_index`; with
    ``defer_save`` the caller bulk-updates refreshed rows itself.
    """
    by_ext, by_hash = index if index is not None else ({}, {})
    existing = None
    if fields.get("external_id"):
        # The source's own id is the stable identity. Matching on the content
        # hash alone meant any change to how we derive a title re-created every
        # lead and let the ATS sweep expire the originals.
        existing = by_ext.get(fields["external_id"])
        if existing is None and index is None:
            existing = Lead.objects.filter(
                source=fields["source"], external_id=fields["external_id"]
            ).first()
    if existing is None:
        existing = by_hash.get(fields["content_hash"])
        if existing is None and index is None:
            existing = Lead.objects.filter(content_hash=fields["content_hash"]).first()
    if existing:
        existing.fetched_at = fields["fetched_at"]
        existing.expires_at = fields["expires_at"]
        existing.is_active = True
        if existing.content_hash != fields["content_hash"]:
            taken = by_hash.get(fields["content_hash"])
            if taken is None and index is None:
                taken = (
                    Lead.objects.filter(content_hash=fields["content_hash"])
                    .exclude(pk=existing.pk)
                    .first()
                )
            if taken is None or taken.pk == existing.pk:
                for name in ("title", "snippet", "url", "company_name", "content_hash"):
                    setattr(existing, name, fields[name])
        if not defer_save:
            existing.save(update_fields=REFRESH_FIELDS)
        return existing, False
    return Lead(**fields), True


# --------------------------------------------------------------------------- #
# Runners
# --------------------------------------------------------------------------- #
def run_source(source, *, use_llm=True):
    """Fetch one source and persist its leads. Never raises — records instead."""
    stats = {"source": source.slug, "seen": 0, "created": 0, "status": Source.OK}
    adapter = ADAPTERS.get(source.adapter_slug)
    if adapter is None:
        stats["status"] = Source.ERROR
        _finish(source, stats, f"No adapter for {source.adapter_slug!r}.")
        return stats
    if hasattr(adapter, "available") and not adapter.available():
        stats["status"] = Source.SKIPPED
        _finish(source, stats, "Credentials are not configured.")
        return stats

    rows = []
    seen_hashes = set()
    try:
        for item in adapter.fetch(source):
            if not item.title or not item.url:
                continue
            stats["seen"] += 1
            fields = normalise(item, source)
            if fields["content_hash"] in seen_hashes:
                continue  # the same posting twice inside one payload
            seen_hashes.add(fields["content_hash"])
            rows.append(fields)
    except Exception as exc:
        logger.warning("Source %s failed: %s", source.slug, exc)
        stats["status"] = Source.ERROR
        _finish(source, stats, str(exc)[:1000])
        return stats

    # One prefetch for the whole payload, then match in memory; refreshed rows
    # go back in a single bulk_update rather than one save each.
    index = existing_index(source, rows)
    fresh, refreshed = [], []
    for fields in rows:
        lead, created = dedupe(fields, index, defer_save=True)
        (fresh if created else refreshed).append(lead)

    tag_skills(fresh, use_llm=use_llm)
    with transaction.atomic():
        Lead.objects.bulk_create(fresh, ignore_conflicts=True)
        if refreshed:
            Lead.objects.bulk_update(refreshed, REFRESH_FIELDS, batch_size=500)
    stats["created"] = len(fresh)
    if source.kind == Source.ATS:
        # An ATS board is authoritative: a posting it stopped returning is closed.
        expire_missing(source, seen_hashes)
    _finish(source, stats, "")
    return stats


def _finish(source, stats, error):
    source.last_run_at = timezone.now()
    source.last_status = stats["status"]
    source.last_error = error
    source.items_seen = stats["seen"]
    source.save(update_fields=["last_run_at", "last_status", "last_error", "items_seen"])


def backfill_tags(limit=100):
    """Model-tag a slice of leads that only have keyword tags (or none).

    A bulk import tags by keyword to stay fast; each periodic run then upgrades
    ``limit`` of the oldest untagged live leads so the whole pool converges on
    model tags without ever spending an hour in one go.
    """
    leads = list(Lead.objects.filter(is_active=True, skills=[]).order_by("fetched_at")[:limit])
    if not leads:
        return 0
    tag_skills(leads, use_llm=True)
    Lead.objects.bulk_update(leads, ["skills"], batch_size=200)
    return len(leads)


def run_all(only=None, *, use_llm=True):
    """Run every enabled source, or just ``only`` (a slug or list of slugs).

    ``use_llm=False`` tags by keyword only. A first bulk import of thousands of
    leads would otherwise spend an hour in model calls and rate-limit backoff;
    the periodic run afterwards tags the trickle of new leads with the model.
    """
    sources = Source.objects.filter(enabled=True)
    if only:
        slugs = [only] if isinstance(only, str) else list(only)
        sources = sources.filter(slug__in=slugs)
    return [run_source(source, use_llm=use_llm) for source in sources]


def expire_missing(source, seen_hashes):
    """Close leads an authoritative source no longer lists."""
    return (
        Lead.objects.filter(source=source, is_active=True)
        .exclude(content_hash__in=seen_hashes)
        .update(is_active=False)
    )


def expire_stale(days=STALE_AFTER_DAYS):
    """Deactivate anything older than ``days``. Returns the count."""
    cutoff = timezone.now() - timedelta(days=days)
    # ATS boards are authoritative: a posting still listed is live no matter how
    # old its publish date (Stripe keeps roles open for months). Their leads are
    # closed by expire_missing when the board stops returning them.
    return (
        Lead.objects.filter(is_active=True, posted_at__lt=cutoff)
        .exclude(source__kind=Source.ATS)
        .update(is_active=False)
    )


# --------------------------------------------------------------------------- #
# Public read API
# --------------------------------------------------------------------------- #
def search_leads(query="", skills=None, kind=None, remote=None, since=None, limit=50):
    """Live leads matching the filters, newest first."""
    leads = Lead.objects.live().select_related("source")
    if query:
        leads = leads.filter(
            Q(title__icontains=query)
            | Q(company_name__icontains=query)
            | Q(snippet__icontains=query)
        )
    if skills:
        wanted = Q()
        for skill in skills:
            wanted |= Q(skills__icontains=str(skill).lower())
        leads = leads.filter(wanted)
    if kind:
        leads = leads.filter(kind=kind)
    if remote is not None:
        leads = leads.filter(remote=bool(remote))
    if since:
        leads = leads.filter(posted_at__gte=since)
    return leads.order_by("-posted_at", "-id")[: max(1, int(limit))]


def match_score(lead_skills, wanted):
    """Jaccard overlap of two skill sets, 0.0-1.0."""
    left, right = set(lead_skills or []), set(wanted or [])
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def leads_for_profile(candidate_profile, limit=50):
    """Leads ranked by skill overlap with the candidate, then recency.

    Ranking happens in Python on a bounded candidate set: ``skills`` is a JSON
    list, so there is no index that would order by overlap in SQL, and the
    seeker feed only ever shows a page or two.
    """
    wanted = {str(s).lower() for s in _profile_skills(candidate_profile)}
    pool = list(search_leads(skills=sorted(wanted) or None, limit=max(limit * 4, 200)))
    if not pool:
        pool = list(search_leads(limit=max(limit * 4, 200)))
    pool.sort(
        key=lambda lead: (match_score(lead.skills, wanted), lead.posted_at or lead.fetched_at),
        reverse=True,
    )
    return pool[:limit]


def _profile_skills(candidate_profile):
    """Skill names off a CandidateProfile, whichever shape it stores them in."""
    if candidate_profile is None:
        return []
    raw = getattr(candidate_profile, "skills", None)
    if raw is None:
        return []
    if isinstance(raw, list | tuple | set):
        return [str(s) for s in raw]
    values = getattr(raw, "values_list", None)
    return list(values("name", flat=True)) if values else []


#: A source is not refetched more often than this by the tick loop.
TICK_MIN_INTERVAL = timedelta(hours=4)


def tick(budget_seconds=25, now=None):
    """Run as many due sources as fit in ``budget_seconds``, oldest first.

    Called from the tick endpoint every few minutes, this replaces the nightly
    bulk fetch on hosting without a cron: 48 sources at one or two per call
    means each is refreshed every few hours. Model tagging is skipped inside a
    web request and picked up by :func:`backfill_tags` a few leads at a time.
    """
    now = now or timezone.now()
    started = time.monotonic()
    due = (
        Source.objects.filter(enabled=True)
        .filter(Q(last_run_at=None) | Q(last_run_at__lt=now - TICK_MIN_INTERVAL))
        .order_by(F("last_run_at").asc(nulls_first=True))
    )
    ran = []
    for source in due:
        if ran and time.monotonic() - started > budget_seconds * 0.6:
            break  # leave headroom: a big board can take ten seconds
        stats = run_source(source, use_llm=False)
        ran.append(f"{source.slug}:{stats['status']}:{stats['created']}")
    backfilled = 0
    if time.monotonic() - started < budget_seconds * 0.7:
        backfilled = backfill_tags(limit=20)
    return {"ran": ran, "backfilled": backfilled, "seconds": round(time.monotonic() - started, 1)}
