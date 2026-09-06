"""Talent-pool services: bulk import, search and bulk actions.

Everything a view, management command or test needs lives here; views stay thin.
Imports are processed synchronously (an ``ImportBatch`` row carries progress so
the UI can poll it), never touch the network in tests, and never raise on a
single bad file - failures land in ``ImportBatch.errors``.
"""

import csv
import io
import logging
import os
import zipfile
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.db.models import Q

from assessments.resume import extract_text
from core.permissions import for_company
from jobs.models import Application, CandidateProfile, Job, Skill
from jobs.services import apply_to_job
from talent.models import ImportBatch, TalentProfile, normalize_email
from talent.parsing import name_from_filename, parse_resume_text, split_skills

logger = logging.getLogger(__name__)

#: Upload guards for bulk import.
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_FILES = 200
MAX_FILE_BYTES = 5 * 1024 * 1024
RESUME_EXTENSIONS = (".pdf", ".docx", ".doc", ".txt")
CSV_EXTENSIONS = (".csv",)

#: Entitlement flag consulted before any AI extraction call.
AI_FEATURE = "ai_extraction"


class ImportTooLarge(ValidationError):
    """The upload exceeds the archive-size or file-count cap."""


# --- AI gating ------------------------------------------------------------


def ai_enabled(company):
    """True when AI resume extraction may run for ``company``.

    Requires an API key *and* the entitlement flag. Talent itself is available
    on every paid plan; only the AI extraction step is gated. When the billing
    app does not know the flag yet we do not block on it.
    """
    from talent import ai

    if not ai.is_configured():
        return False
    try:
        from billing.entitlements import FEATURES, has_feature
    except Exception:  # pragma: no cover - billing is always installed
        return True
    if AI_FEATURE not in FEATURES:
        return True
    return has_feature(company, AI_FEATURE)


# --- upsert ---------------------------------------------------------------


def _decimal_years(value):
    if value in (None, ""):
        return None
    try:
        years = Decimal(str(value)).quantize(Decimal("0.1"))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if years < 0 or years > 60:
        return None
    return years


def _find_existing(company, email, phone):
    """Dedupe: match on email first, then on phone."""
    email = normalize_email(email)
    if email:
        found = TalentProfile.objects.filter(company=company, email=email).first()
        if found is not None:
            return found
    phone = (phone or "").strip()
    if phone:
        return TalentProfile.objects.filter(company=company, phone=phone).first()
    return None


def link_candidate(profile, save=True):
    """Attach an existing ``jobs.CandidateProfile`` with the same email, if any."""
    if profile.linked_candidate_id or not profile.email:
        return profile.linked_candidate
    candidate = CandidateProfile.objects.filter(user__email__iexact=profile.email).first()
    if candidate is None:
        return None
    profile.linked_candidate = candidate
    if save and profile.pk:
        profile.save(update_fields=["linked_candidate", "updated_at"])
    return candidate


def resolve_skills(company, names):
    """Get-or-create per-company ``jobs.Skill`` rows for ``names``."""
    skills = []
    for name in split_skills(names):
        skill = Skill.objects.filter(company=company, name__iexact=name).first()
        if skill is None:
            skill = Skill.objects.create(company=company, name=name)
        skills.append(skill)
    return skills


@transaction.atomic
def upsert_profile(
    company,
    *,
    email="",
    name="",
    phone="",
    headline="",
    experience_years=None,
    current_company="",
    location="",
    resume=None,
    resume_text="",
    skills=None,
    tags=None,
    source=TalentProfile.MANUAL,
    created_by=None,
):
    """Create or update one talent profile. Returns ``(profile, created)``.

    Deduped by email then phone; blank incoming values never overwrite stored
    ones, and skills/tags are merged rather than replaced.
    """
    email = normalize_email(email)
    phone = (phone or "").strip()
    if not email and not phone:
        raise ValidationError("A talent profile needs at least an email or a phone number.")

    profile = _find_existing(company, email, phone)
    created = profile is None
    if created:
        # A phone-only import still needs a unique key for (company, email).
        profile = TalentProfile(
            company=company,
            email=email or f"unknown+{phone}@talent.local",
            source=source,
            created_by=created_by,
        )
    elif email and not profile.email:
        profile.email = email

    for field, value in (
        ("name", name),
        ("phone", phone),
        ("headline", headline),
        ("current_company", current_company),
        ("location", location),
    ):
        value = (value or "").strip()
        if value and (created or not getattr(profile, field)):
            setattr(profile, field, value)

    years = _decimal_years(experience_years)
    if years is not None and (created or not profile.experience_years):
        profile.experience_years = years

    if resume_text and (created or len(resume_text) > len(profile.resume_text or "")):
        profile.resume_text = resume_text

    merged = list(profile.tags or [])
    lowered = {t.lower() for t in merged}
    for tag in split_skills(tags):
        if tag.lower() not in lowered:
            merged.append(tag)
            lowered.add(tag.lower())
    profile.tags = merged

    if resume is not None:
        name_hint = getattr(resume, "name", None) or "resume.txt"
        content = resume.read() if hasattr(resume, "read") else bytes(resume)
        profile.resume.save(os.path.basename(name_hint), ContentFile(content), save=False)

    link_candidate(profile, save=False)
    profile.save()

    if skills:
        profile.skills.add(*resolve_skills(company, skills))
    return profile, created


# --- import ---------------------------------------------------------------


def _guard_upload(upload):
    size = getattr(upload, "size", 0) or 0
    if size > MAX_ARCHIVE_BYTES:
        raise ImportTooLarge(
            f"Uploads must be {MAX_ARCHIVE_BYTES // (1024 * 1024)} MB or smaller."
        )


def _is_csv(name):
    return (name or "").lower().endswith(CSV_EXTENSIONS)


def _is_resume(name):
    return (name or "").lower().endswith(RESUME_EXTENSIONS)


def _profile_fields_from_resume(company, filename, text):
    """Regex heuristics, refined by AI extraction when it is available."""
    fields = parse_resume_text(text, filename)
    fields["skills"] = []
    fields.setdefault("headline", "")
    fields["current_company"] = ""
    fields["location"] = ""
    if not ai_enabled(company):
        return fields
    from talent import ai

    extracted = ai.extract_profile(text)
    if not extracted:
        return fields
    for key in ("name", "email", "phone", "headline", "current_company", "location"):
        if extracted.get(key):
            fields[key] = extracted[key]
    if extracted.get("experience_years") is not None:
        fields["experience_years"] = extracted["experience_years"]
    fields["skills"] = extracted.get("skills") or []
    return fields


def _import_resume_bytes(batch, filename, raw):
    """Upsert one resume file into the pool. Returns "created"/"updated"/"skipped"."""
    if len(raw) > MAX_FILE_BYTES:
        batch.note_error(filename, "File is larger than 5 MB.")
        batch.note_item(filename, "error", "File is larger than 5 MB.")
        return "skipped"
    text = extract_text(ContentFile(raw, name=filename))
    fields = _profile_fields_from_resume(batch.company, filename, text)
    if not fields.get("email") and not fields.get("phone"):
        batch.note_error(filename, "No email or phone number found in the resume.")
        batch.note_item(filename, "error", "No email or phone number found in the resume.")
        return "skipped"
    if not fields.get("name"):
        fields["name"] = name_from_filename(filename)
    _, created = upsert_profile(
        batch.company,
        email=fields.get("email", ""),
        name=fields.get("name", ""),
        phone=fields.get("phone", ""),
        headline=fields.get("headline", ""),
        experience_years=fields.get("experience_years"),
        current_company=fields.get("current_company", ""),
        location=fields.get("location", ""),
        resume=ContentFile(raw, name=os.path.basename(filename)),
        resume_text=text,
        skills=fields.get("skills"),
        source=TalentProfile.IMPORT,
        created_by=batch.uploaded_by,
    )
    outcome = "created" if created else "updated"
    batch.note_item(filename, outcome, fields.get("email", ""))
    return outcome


CSV_ALIASES = {
    "name": "name",
    "full name": "name",
    "candidate": "name",
    "email": "email",
    "email address": "email",
    "e-mail": "email",
    "phone": "phone",
    "mobile": "phone",
    "phone number": "phone",
    "skills": "skills",
    "skill": "skills",
    "experience": "experience",
    "experience_years": "experience",
    "years": "experience",
    "headline": "headline",
    "title": "headline",
    "location": "location",
    "current_company": "current_company",
    "company": "current_company",
    "tags": "tags",
}


def _csv_rows(raw):
    text = raw.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        mapped = {}
        for key, value in (row or {}).items():
            field = CSV_ALIASES.get((key or "").strip().lower())
            if field and value:
                mapped[field] = str(value).strip()
        yield mapped


def _import_csv_bytes(batch, raw, source=""):
    """Import every row of one CSV. Each *row* counts towards ``batch.total``."""
    rows = list(_csv_rows(raw))
    batch.add_total(len(rows))
    _touch(batch)
    for index, row in enumerate(rows, start=2):
        label = row.get("email") or row.get("phone") or f"{source}row {index}".strip()
        if not row.get("email") and not row.get("phone"):
            batch.skipped += 1
            batch.note_error(f"{source}row {index}", "Missing both email and phone.")
            batch.note_item(f"{source}row {index}", "error", "Missing both email and phone.")
            _touch(batch)
            continue
        try:
            _, created = upsert_profile(
                batch.company,
                email=row.get("email", ""),
                name=row.get("name", ""),
                phone=row.get("phone", ""),
                headline=row.get("headline", ""),
                experience_years=row.get("experience"),
                current_company=row.get("current_company", ""),
                location=row.get("location", ""),
                skills=row.get("skills"),
                tags=row.get("tags"),
                source=TalentProfile.IMPORT,
                created_by=batch.uploaded_by,
            )
        except ValidationError as exc:
            batch.skipped += 1
            batch.note_error(f"{source}row {index}", "; ".join(exc.messages))
            batch.note_item(f"{source}row {index}", "error", "; ".join(exc.messages))
            _touch(batch)
            continue
        batch.created += 1 if created else 0
        batch.updated += 0 if created else 1
        batch.note_item(label, "created" if created else "updated")
        _touch(batch)


def _touch(batch):
    batch.save(
        update_fields=["created", "updated", "skipped", "errors", "items", "total", "status"]
    )


def _zip_members(raw, batch):
    """Yield ``(name, bytes)`` for importable members of a zip archive."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValidationError("That file is not a readable zip archive.") from exc
    members = [
        info
        for info in archive.infolist()
        if not info.is_dir()
        and not os.path.basename(info.filename).startswith(".")
        and (_is_resume(info.filename) or _is_csv(info.filename))
    ]
    if len(members) > MAX_FILES:
        raise ImportTooLarge(f"Archives may contain at most {MAX_FILES} files.")
    if sum(info.file_size for info in members) > MAX_ARCHIVE_BYTES:
        raise ImportTooLarge("The archive's uncompressed contents exceed 25 MB.")
    for info in members:
        try:
            with archive.open(info) as handle:
                yield info.filename, handle.read(MAX_FILE_BYTES + 1)
        except Exception as exc:  # pragma: no cover - corrupt member
            batch.note_error(info.filename, str(exc) or "Could not read this file.")
            batch.note_item(info.filename, "error", str(exc) or "Could not read this file.")
            batch.skipped += 1
            batch.add_total(1)
            _touch(batch)


def run_import(company, uploads, uploaded_by=None):
    """Import ``uploads`` (a list of uploaded files) synchronously.

    Accepts a single zip, a single CSV, or many individual resumes. Returns the
    ``ImportBatch`` carrying counts, per-item errors and final status.
    """
    uploads = [u for u in (uploads or []) if u is not None]
    if not uploads:
        raise ValidationError("Choose at least one file to import.")
    if len(uploads) > MAX_FILES:
        raise ImportTooLarge(f"Upload at most {MAX_FILES} files at a time.")
    total_bytes = sum(getattr(u, "size", 0) or 0 for u in uploads)
    if total_bytes > MAX_ARCHIVE_BYTES:
        raise ImportTooLarge(
            f"Uploads must total {MAX_ARCHIVE_BYTES // (1024 * 1024)} MB or less."
        )
    for upload in uploads:
        _guard_upload(upload)

    first = uploads[0]
    batch = ImportBatch.objects.create(
        company=company,
        uploaded_by=uploaded_by,
        file=first if len(uploads) == 1 else None,
        status=ImportBatch.RUNNING,
        # Grown as work is discovered: a zip contributes one unit per member and
        # a CSV one per row, so ``total`` counts items, not uploads.
        total=0,
    )
    try:
        _process(batch, uploads)
    except ValidationError as exc:
        batch.status = ImportBatch.FAILED
        batch.note_error("upload", "; ".join(exc.messages))
        _touch(batch)
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Talent import batch %s failed.", batch.pk)
        batch.status = ImportBatch.FAILED
        batch.note_error("upload", str(exc))
        _touch(batch)
        return batch
    batch.status = ImportBatch.DONE
    _touch(batch)
    return batch


def _is_zip(name, raw):
    """A zip we should expand (a .docx is also a zip, so the name decides)."""
    lowered = (name or "").lower()
    if lowered.endswith((".docx", ".doc")):
        return False
    return lowered.endswith(".zip") or raw[:4] == b"PK\x03\x04"


def _process(batch, uploads):
    for upload in uploads:
        name = getattr(upload, "name", "") or "upload"
        upload.seek(0)
        raw = upload.read()
        if _is_zip(name, raw):
            for member, data in _zip_members(raw, batch):
                if _is_csv(member):
                    _import_csv_bytes(batch, data, source=f"{member}: ")
                    continue
                batch.add_total(1)
                outcome = _import_resume_bytes(batch, member, data)
                _bump(batch, outcome)
            continue
        if _is_csv(name):
            _import_csv_bytes(batch, raw)
            continue
        batch.add_total(1)
        if not _is_resume(name):
            batch.skipped += 1
            batch.note_error(name, "Unsupported file type (use PDF, DOCX, TXT, CSV or ZIP).")
            batch.note_item(
                name, "error", "Unsupported file type (use PDF, DOCX, TXT, CSV or ZIP)."
            )
            _touch(batch)
            continue
        outcome = _import_resume_bytes(batch, name, raw)
        _bump(batch, outcome)


def _bump(batch, outcome):
    setattr(batch, outcome, getattr(batch, outcome) + 1)
    _touch(batch)


# --- search ---------------------------------------------------------------

ORDERINGS = {
    "recent": "-updated_at",
    "name": "name",
    "experience": "-experience_years",
    "created": "-created_at",
}


def search_profiles(
    company,
    query="",
    *,
    skills=None,
    match_all=False,
    min_experience=None,
    max_experience=None,
    tags=None,
    source="",
    ordering="recent",
):
    """Filtered talent-pool queryset for ``company``.

    Uses Postgres full-text search (``SearchVector``) when the active connection
    is Postgres, and falls back to case-insensitive ``icontains`` elsewhere
    (SQLite in dev/tests).
    """
    qs = for_company(TalentProfile.objects.all(), company).prefetch_related("skills")

    query = (query or "").strip()
    if query:
        qs = _apply_text_search(qs, query)

    skill_ids = [int(s) for s in (skills or []) if str(s).isdigit()]
    if skill_ids:
        if match_all:
            for skill_id in skill_ids:
                qs = qs.filter(skills__id=skill_id)
        else:
            qs = qs.filter(skills__id__in=skill_ids)
        qs = qs.distinct()

    low = _decimal_years(min_experience)
    if low is not None:
        qs = qs.filter(experience_years__gte=low)
    high = _decimal_years(max_experience)
    if high is not None:
        qs = qs.filter(experience_years__lte=high)

    for tag in split_skills(tags):
        qs = qs.filter(tags__icontains=tag)

    if source:
        qs = qs.filter(source=source)

    return qs.order_by(ORDERINGS.get(ordering or "recent", "-updated_at"), "-id")


def _substring_match(query):
    return (
        Q(name__icontains=query)
        | Q(email__icontains=query)
        | Q(headline__icontains=query)
        | Q(resume_text__icontains=query)
        | Q(tags__icontains=query)
    )


def _apply_text_search(qs, query):
    substring = _substring_match(query)
    if connection.vendor == "postgresql":
        try:
            from django.contrib.postgres.search import SearchQuery, SearchVector

            vector = SearchVector("name", "email", "headline", "resume_text")
            # Full text alone answers "developer" with "developers", but it only
            # matches whole lexemes: a recruiter typing half a name or half an
            # email ("asha@exam") would get nothing. OR in the substring match so
            # partial queries keep working, which is how the box is actually used.
            return qs.annotate(search=vector).filter(
                Q(search=SearchQuery(query, search_type="websearch")) | substring
            )
        except Exception:  # pragma: no cover - falls back on any PG hiccup
            logger.warning("Postgres full-text search failed; using icontains.", exc_info=True)
    return qs.filter(substring)


# --- bulk actions ---------------------------------------------------------


def add_tag(profiles, tag):
    """Add ``tag`` to every profile. Returns the number changed."""
    return sum(1 for profile in profiles if profile.add_tag(tag))


def ensure_candidate_profile(profile):
    """Return a ``jobs.CandidateProfile`` for ``profile``, creating the shell user.

    A brand-new user gets ``is_candidate=True`` and an unusable password so they
    must use the password-reset / invite flow to claim the account.
    """
    from core.models import User

    if profile.linked_candidate_id:
        return profile.linked_candidate
    candidate = link_candidate(profile)
    if candidate is not None:
        return candidate

    email = normalize_email(profile.email)
    if not email or email.endswith("@talent.local"):
        raise ValidationError("This profile needs a real email address before it can apply.")

    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        user = User(email=email, is_candidate=True)
        parts = (profile.name or "").split()
        if parts:
            user.first_name = parts[0][:150]
            user.last_name = " ".join(parts[1:])[:150]
        user.set_unusable_password()
        user.save()
    candidate = getattr(user, "candidate_profile", None)
    if candidate is None:
        candidate = CandidateProfile.objects.create(
            user=user,
            phone=profile.phone or "",
            headline=profile.headline or "",
            experience_years=profile.experience_years or 0,
            resume_text=profile.resume_text or "",
        )
    if profile.skills.exists():
        candidate.skills.add(*profile.skills.all())
    profile.linked_candidate = candidate
    profile.save(update_fields=["linked_candidate", "updated_at"])
    return candidate


def _notify_application(application):
    """Best-effort candidate notification; the notifications app may not be ready."""
    try:
        from notifications import send

        send(
            "application_received",
            application.candidate.user,
            {"application": application, "job": application.job},
            company=application.job.company,
        )
    except Exception:
        logger.info("Could not send the application_received notification.", exc_info=True)


def add_to_job(profiles, job, actor=None):
    """Apply each profile to ``job``. Returns ``{"added", "existing", "errors"}``."""
    result = {"added": 0, "existing": 0, "errors": []}
    for profile in profiles:
        if profile.company_id != job.company_id:
            result["errors"].append(f"{profile.display_name}: different company.")
            continue
        try:
            candidate = ensure_candidate_profile(profile)
        except ValidationError as exc:
            result["errors"].append(f"{profile.display_name}: {'; '.join(exc.messages)}")
            continue
        if Application.objects.filter(job=job, candidate=candidate).exists():
            result["existing"] += 1
            continue
        try:
            application = apply_to_job(job, candidate)
        except ValidationError as exc:
            result["errors"].append(f"{profile.display_name}: {'; '.join(exc.messages)}")
            continue
        result["added"] += 1
        _notify_application(application)
    return result


EXPORT_COLUMNS = (
    "name",
    "email",
    "phone",
    "headline",
    "experience_years",
    "current_company",
    "location",
    "skills",
    "tags",
    "source",
    "created_at",
)


def export_csv(profiles, stream=None):
    """Write ``profiles`` as CSV into ``stream`` (or a new ``StringIO``)."""
    stream = stream if stream is not None else io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(EXPORT_COLUMNS)
    for profile in profiles:
        writer.writerow(
            [
                profile.name,
                profile.email,
                profile.phone,
                profile.headline,
                profile.experience_years,
                profile.current_company,
                profile.location,
                ", ".join(s.name for s in profile.skills.all()),
                ", ".join(profile.tags or []),
                profile.source,
                profile.created_at.isoformat() if profile.created_at else "",
            ]
        )
    return stream


def capture_applicant(application):
    """Create/refresh the APPLICANT talent profile behind ``application``."""
    candidate = getattr(application, "candidate", None)
    job = getattr(application, "job", None)
    if candidate is None or job is None:
        return None
    user = getattr(candidate, "user", None)
    email = normalize_email(getattr(user, "email", ""))
    if not email:
        return None
    profile, created = upsert_profile(
        job.company,
        email=email,
        name=(user.get_full_name() or "").strip(),
        phone=candidate.phone or "",
        headline=candidate.headline or "",
        experience_years=candidate.experience_years,
        resume_text=candidate.resume_text or "",
        source=TalentProfile.APPLICANT,
    )
    updates = []
    if profile.linked_candidate_id != candidate.pk:
        profile.linked_candidate = candidate
        updates.append("linked_candidate")
    if created and profile.source != TalentProfile.APPLICANT:
        profile.source = TalentProfile.APPLICANT
        updates.append("source")
    if updates:
        profile.save(update_fields=[*updates, "updated_at"])
    skills = list(candidate.skills.all())
    if skills:
        profile.skills.add(*skills)
    return profile


def company_jobs(company):
    """Open jobs of ``company`` (targets for the "Add to job" action)."""
    return for_company(Job.objects.filter(status=Job.OPEN), company).order_by("title")
