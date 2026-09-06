"""Seeker services: the feed, the send quota, AI drafting, sending and bulk apply.

The awkward bits live here rather than in views because each one has a rule
worth stating once:

* the feed blends two very different inventories (external ``sources.Lead``
  rows and our own network jobs) and both apps are optional at import time;
* the quota is checked *before* a bulk action starts, so a 20-mail run cannot
  half-succeed past the free limit;
* a draft that reads like a mail-merge gets ignored, so the prompt demands
  concrete facts from both sides and the fallback template does the same.
"""

import logging
import re

from django.db import transaction
from django.utils import timezone

from jobs.models import CandidateProfile
from seeker.mail import Attachment, Message, SendError, backend_for
from seeker.models import MAX_BULK_SENDS, Outreach, SavedItem, SeekerProfile, month_key

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


class QuotaExceeded(Exception):
    """Raised before anything is sent when the month's allowance is spent."""


# --------------------------------------------------------------------------- #
# Profiles
# --------------------------------------------------------------------------- #


def get_profile(user):
    """The seeker profile for ``user``, created on first visit."""
    profile, created = SeekerProfile.objects.get_or_create(user=user)
    if created:
        profile.skills = candidate_skills(user)
        profile.mailbox_email = user.email
        profile.save(update_fields=["skills", "mailbox_email"])
    return profile


def candidate_profile_for(user):
    profile, _ = CandidateProfile.objects.get_or_create(user=user)
    return profile


def candidate_skills(user):
    """Lower-cased skill names off the candidate profile — the matching vocabulary."""
    candidate = CandidateProfile.objects.filter(user=user).first()
    if not candidate:
        return []
    return sorted({name.lower() for name in candidate.skills.values_list("name", flat=True)})


# --------------------------------------------------------------------------- #
# Feed
# --------------------------------------------------------------------------- #


def match_percent(wanted, offered):
    """Jaccard overlap of two skill lists, as a whole percent."""
    left, right = {s.lower() for s in wanted or []}, {s.lower() for s in offered or []}
    if not left or not right:
        return 0
    return round(100 * len(left & right) / len(left | right))


def feed_leads(seeker, *, query="", kind="", remote=None, limit=50):
    """External leads for this seeker. Empty list while ``sources`` is unavailable."""
    try:
        from sources import services as source_services
    except ImportError:  # pragma: no cover - sources is a hard dependency in prod
        return []
    candidate = CandidateProfile.objects.filter(user=seeker.user).first()
    try:
        if query or kind or remote:
            leads = source_services.search_leads(
                query=query, kind=kind or None, remote=remote, limit=limit
            )
        else:
            leads = source_services.leads_for_profile(candidate, limit=limit)
    except Exception:
        logger.exception("seeker: the lead feed could not be built")
        return []
    return list(leads)


def feed_jobs(seeker, limit=25):
    """Network jobs from ``board``; empty while that app has no service yet."""
    try:
        from board import services as board_services
    except ImportError:
        return []
    candidate = CandidateProfile.objects.filter(user=seeker.user).first()
    try:
        return list(board_services.network_jobs_for(candidate, limit=limit))
    except Exception:
        logger.exception("seeker: network jobs could not be listed")
        return []


def build_feed(seeker, *, query="", kind="", remote=None, limit=50):
    """Cards for the feed page: leads then network jobs, each with a match %."""
    saved_leads = set(
        seeker.saved_items.filter(lead__isnull=False).values_list("lead_id", flat=True)
    )
    saved_jobs = set(seeker.saved_items.filter(job__isnull=False).values_list("job_id", flat=True))
    cards = []
    for lead in feed_leads(seeker, query=query, kind=kind, remote=remote, limit=limit):
        cards.append(
            {
                "kind": "lead",
                "id": lead.pk,
                "title": lead.title,
                "company": lead.company_name,
                "snippet": lead.snippet,
                "url": lead.url,
                "source": getattr(lead.source, "name", ""),
                "remote": lead.remote,
                "match": match_percent(seeker.skills, lead.skills),
                "saved": lead.pk in saved_leads,
            }
        )
    if not kind or kind == "JOB":
        for job in feed_jobs(seeker):
            job_skills = [s.name for s in job.skills.all()]
            cards.append(
                {
                    "kind": "job",
                    "id": job.pk,
                    "title": job.title,
                    "company": job.company.name,
                    "snippet": (job.description or "")[:600],
                    "url": "",
                    "source": "Network",
                    "remote": getattr(job, "remote", False),
                    "match": match_percent(seeker.skills, job_skills),
                    "saved": job.pk in saved_jobs,
                }
            )
    cards.sort(key=lambda card: card["match"], reverse=True)
    return cards


def save_lead(seeker, lead):
    item, _ = SavedItem.objects.get_or_create(seeker=seeker, lead=lead)
    return item


def save_job(seeker, job):
    item, _ = SavedItem.objects.get_or_create(seeker=seeker, job=job)
    return item


# --------------------------------------------------------------------------- #
# Manual capture
# --------------------------------------------------------------------------- #


def extract_email(text):
    """First plausible address in ``text``; ignores the obvious non-humans."""
    for match in EMAIL_RE.findall(text or ""):
        low = match.lower()
        if any(bad in low for bad in ("noreply", "no-reply", "example.com", "donotreply")):
            continue
        return match
    return ""


def create_manual_lead(seeker, *, url, text, title="", company=""):
    """Turn a pasted posting into a ``sources.Lead`` under the ``manual`` source.

    Pages we may not scrape (LinkedIn, Upwork, Naukri) can still reach the
    seeker's board this way — the seeker did the reading, we only store what
    they pasted, capped at the same 600-char snippet every adapter uses.
    """
    try:
        from sources.models import Lead, Source
    except ImportError:
        return None
    import hashlib

    snippet = (text or "").strip()[:600]
    title = (title or snippet.splitlines()[0] if snippet else "").strip()[:300] or "Saved link"
    source, _ = Source.objects.get_or_create(
        slug="manual", defaults={"name": "Pasted by seekers", "kind": "API", "enabled": False}
    )
    digest = hashlib.sha256(f"{title}|{company}|{url}|{snippet[:300]}".lower().encode()).hexdigest()
    lead, _ = Lead.objects.get_or_create(
        content_hash=digest,
        defaults={
            "source": source,
            "title": title,
            "company_name": (company or "")[:200],
            "snippet": snippet,
            "url": url or "",
            "contact_email": extract_email(text),
            "posted_at": timezone.now(),
        },
    )
    save_lead(seeker, lead)
    return lead


# --------------------------------------------------------------------------- #
# Quota
# --------------------------------------------------------------------------- #


def check_quota(seeker, count=1):
    """Raise :class:`QuotaExceeded` unless ``count`` more sends fit this month."""
    if count > MAX_BULK_SENDS:
        raise QuotaExceeded(f"Send at most {MAX_BULK_SENDS} mails at a time.")
    left = seeker.sends_left()
    if left is not None and count > left:
        raise QuotaExceeded(
            f"{left} send{'' if left == 1 else 's'} left this month on the free plan."
        )
    return True


def record_send(seeker, count=1):
    """Bump the monthly counter, rolling it over on the first send of a new month."""
    key = month_key()
    if seeker.month_key != key:
        seeker.month_key = key
        seeker.sends_this_month = 0
    seeker.sends_this_month += count
    seeker.save(update_fields=["month_key", "sends_this_month"])


# --------------------------------------------------------------------------- #
# Drafting
# --------------------------------------------------------------------------- #

DRAFT_SYSTEM = (
    "You write short cold emails for a job seeker in India. Plain text only. "
    "Never use placeholders like [Name] or [Company]. Under 180 words. "
    "First line 'Subject: ...', then a blank line, then the body."
)


def _facts(text, count=2):
    """A couple of concrete lines from a blob, for the fallback template."""
    lines = [line.strip() for line in re.split(r"[\n.]", text or "") if len(line.strip()) > 25]
    return lines[:count]


def fallback_draft(seeker, item):
    """A decent template for when the model is off or fails — never a placeholder."""
    name = seeker.user.get_full_name() or seeker.user.email.split("@")[0]
    candidate = CandidateProfile.objects.filter(user=seeker.user).first()
    role = (item.title or "the role").strip()
    company = item.company_name or "your team"
    lead_facts = _facts(getattr(item.lead, "snippet", "") if item.lead_id else "")
    mine = _facts(getattr(candidate, "resume_text", ""))
    lines = ["Hi,", "", f"I saw the {role} opening at {company} and would like to be considered."]
    if lead_facts:
        lines.append(f"What stood out: {lead_facts[0]}")
    if mine:
        lines.append(f"On my side: {mine[0]}")
    if len(mine) > 1:
        lines.append(mine[1])
    if candidate and candidate.headline:
        lines.append(candidate.headline)
    lines += ["", "Happy to share more or send my résumé in the format you prefer.", "", name]
    return f"{role} — {name}"[:300], "\n".join(lines)


def draft_outreach(seeker, item):
    """Return ``(subject, body)`` for one saved item, AI-written when possible."""
    from core.llm import complete

    candidate = CandidateProfile.objects.filter(user=seeker.user).first()
    resume_text = (getattr(candidate, "resume_text", "") or "")[:3000]
    snippet = (getattr(item.lead, "snippet", "") if item.lead_id else "")[:1500]
    name = seeker.user.get_full_name() or seeker.user.email.split("@")[0]
    prompt = (
        f"Seeker name: {name}\n"
        f"Role: {item.title}\nCompany: {item.company_name}\n"
        f"Posting snippet:\n{snippet}\n\n"
        f"Seeker resume:\n{resume_text}\n\n"
        "Write the email. Reference two concrete facts from the posting and two "
        "from the resume. Sign off with the seeker's name."
    )
    text = complete(prompt, system=DRAFT_SYSTEM, max_tokens=700)
    if not text:
        return fallback_draft(seeker, item)
    subject, _, body = text.partition("\n")
    subject = subject.removeprefix("Subject:").strip()[:300]
    body = body.strip()
    if not subject or not body:
        return fallback_draft(seeker, item)
    return subject, body


def draft_for_items(seeker, items):
    """Create (or refresh) a DRAFT ``Outreach`` per item that has an address."""
    drafts = []
    for item in items:
        to_email = item.contact_email
        if not to_email:
            continue
        subject, body = draft_outreach(seeker, item)
        outreach, _ = Outreach.objects.update_or_create(
            seeker=seeker,
            saved_item=item,
            status=Outreach.DRAFT,
            defaults={"to_email": to_email, "subject": subject, "body": body},
        )
        drafts.append(outreach)
    return drafts


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #


def resume_attachment(seeker):
    """The seeker's résumé as an attachment, or ``None`` when there is none."""
    candidate = CandidateProfile.objects.filter(user=seeker.user).first()
    if not candidate or not candidate.resume:
        return None
    try:
        with candidate.resume.open("rb") as handle:
            content = handle.read()
    except (OSError, ValueError):
        logger.warning("seeker: résumé file missing for %s", seeker.user.email)
        return None
    import mimetypes
    import os

    filename = os.path.basename(candidate.resume.name)
    mimetype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Attachment(filename=filename, content=content, mimetype=mimetype)


def send_outreach(outreach, attachment=None):
    """Send one mail from the seeker's mailbox. Returns True on success.

    Quota is charged only on success: a bounced SMTP login should not cost the
    seeker one of ten monthly sends.
    """
    seeker = outreach.seeker
    backend = backend_for(seeker)
    if backend is None:
        outreach.status = Outreach.FAILED
        outreach.error = "No mailbox is connected."
        outreach.save(update_fields=["status", "error"])
        return False
    if attachment is None:
        attachment = resume_attachment(seeker)
    message = Message(
        to_email=outreach.to_email,
        subject=outreach.subject,
        body=outreach.body,
        from_email=seeker.mailbox_email or seeker.user.email,
        from_name=seeker.user.get_full_name(),
        reply_to=seeker.mailbox_email or seeker.user.email,
        attachments=[attachment] if attachment else [],
    )
    try:
        message_id = backend.send(message)
    except SendError as exc:
        outreach.status = Outreach.FAILED
        outreach.error = str(exc)
        outreach.save(update_fields=["status", "error"])
        return False
    outreach.status = Outreach.SENT
    outreach.provider_message_id = message_id or ""
    outreach.sent_at = timezone.now()
    outreach.error = ""
    outreach.save(update_fields=["status", "provider_message_id", "sent_at", "error"])
    outreach.resume_attached = bool(attachment)
    Outreach.objects.filter(pk=outreach.pk).update(resume_attached=bool(attachment))
    SavedItem.objects.filter(pk=outreach.saved_item_id, status=SavedItem.SAVED).update(
        status=SavedItem.CONTACTED
    )
    record_send(seeker, 1)
    return True


def send_many(seeker, outreaches):
    """Send a batch after one quota check. Returns ``(sent, failed)`` counts."""
    outreaches = list(outreaches)
    check_quota(seeker, len(outreaches))
    attachment = resume_attachment(seeker)
    sent = failed = 0
    for outreach in outreaches:
        if send_outreach(outreach, attachment=attachment):
            sent += 1
        else:
            failed += 1
    return sent, failed


# --------------------------------------------------------------------------- #
# Bulk apply
# --------------------------------------------------------------------------- #


def bulk_apply(seeker, items):
    """Apply to every internal job in ``items``; one Application per job, ever."""
    from web.services.apply import apply_to_job

    applied = 0
    with transaction.atomic():
        for item in items:
            if not item.job_id:
                continue
            application = apply_to_job(seeker.user, item.job)
            if getattr(application, "was_created", False):
                applied += 1
            SavedItem.objects.filter(pk=item.pk).update(status=SavedItem.APPLIED)
    return applied


def mark_opened(seeker, items):
    """ "Open & track": external links get marked APPLIED once the seeker leaves."""
    ids = [item.pk for item in items if item.lead_id]
    SavedItem.objects.filter(seeker=seeker, pk__in=ids).update(status=SavedItem.APPLIED)
    return len(ids)
