"""Verified cross-company candidate pool.

Only candidates who opted in (``CandidateProfile.share_in_pool``) *and* passed
at least one assessment appear, and cards are anonymised: contact details are
never exposed until the candidate accepts an invitation.
"""

from dataclasses import dataclass, field


@dataclass
class PoolCard:
    """An anonymised pool result. Deliberately carries no email or phone."""

    profile_id: int
    reference: str
    headline: str
    experience_years: object
    skills: list = field(default_factory=list)
    best_score: object = None


def verified_pool_queryset():
    """Opted-in candidate profiles with at least one passed attempt."""
    from django.db.models import Exists, Max, OuterRef

    from assessments.models import Attempt
    from jobs.models import CandidateProfile

    passed = Attempt.objects.filter(application__candidate=OuterRef("pk"), passed=True)
    return (
        CandidateProfile.objects.filter(share_in_pool=True)
        .annotate(has_passed=Exists(passed))
        .filter(has_passed=True)
        .annotate(best_score=Max("applications__attempts__score_percent"))
        .prefetch_related("skills")
        .distinct()
    )


def search(query="", skill="", min_experience=None, limit=50):
    """Search the verified pool, returning anonymised :class:`PoolCard` rows."""
    qs = verified_pool_queryset()
    query = (query or "").strip()
    if query:
        qs = qs.filter(headline__icontains=query)
    skill = (skill or "").strip()
    if skill:
        qs = qs.filter(skills__name__icontains=skill)
    if min_experience not in (None, ""):
        try:
            qs = qs.filter(experience_years__gte=float(min_experience))
        except (TypeError, ValueError):
            pass
    return [card_for(profile) for profile in qs.distinct()[:limit]]


def card_for(profile):
    """Build the anonymised card for one profile."""
    return PoolCard(
        profile_id=profile.pk,
        reference=f"CAND-{profile.pk:05d}",
        headline=profile.headline or "Verified candidate",
        experience_years=profile.experience_years,
        skills=sorted({s.name for s in profile.skills.all()}),
        best_score=getattr(profile, "best_score", None),
    )


def invite(profile, company, job=None, actor=None):
    """Invite a pooled candidate to apply. Returns True when a message went out.

    Uses ``notifications.send`` when the notifications app exposes it, and falls
    back to a plain email otherwise.
    """
    context = {
        "company_name": getattr(company, "name", ""),
        "job_title": getattr(job, "title", ""),
        "candidate_reference": f"CAND-{profile.pk:05d}",
    }
    try:
        import notifications

        sender = getattr(notifications, "send", None)
        if callable(sender):
            sender(
                "talent_pool_invite",
                profile.user,
                context,
                company=company,
            )
            return True
    except Exception:  # pragma: no cover - notifications is optional
        pass
    return _fallback_email(profile, company, job)


def _fallback_email(profile, company, job):
    from django.core.mail import send_mail

    company_name = getattr(company, "name", "A hiring team")
    subject = f"{company_name} would like you to apply"
    role = getattr(job, "title", "") or "an open role"
    body = (
        f"Hello,\n\n{company_name} found your verified profile in the Interview Portal "
        f"talent pool and would like you to apply for {role}.\n\n"
        "Sign in to your candidate portal to see the invitation.\n"
    )
    sent = send_mail(subject, body, None, [profile.user.email], fail_silently=True)
    return bool(sent)
