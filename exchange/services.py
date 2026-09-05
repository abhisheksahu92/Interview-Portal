"""Exchange services: partners, requirements, submissions, deals.

Every state change goes through this module — views are thin. Two rules are
enforced here and nowhere else:

* **Publishing is a paid feature** (flag ``exchange``); **responding is free**
  on every plan, because the supply side is what makes the network worth
  joining.
* **Contact details and end-client names are masked** until a reveal; the
  masking itself lives on the models so no template can leak by accident.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from core.models import Company, Membership
from exchange.models import (
    ExchangeDeal,
    ExchangeRequirement,
    ExchangeSubmission,
    PartnerLink,
    email_hash,
)
from exchange.notify import notify_company
from jobs.models import Skill

logger = logging.getLogger(__name__)

#: Feature flag that gates publishing (any plan may respond).
FEATURE = "exchange"
#: Ledger charge kind for the platform's cut of a deal.
CHARGE_KIND = "EXCHANGE_FEE"
DEFAULT_EXPIRY_DAYS = 30


class ExchangeError(Exception):
    """A refused exchange action, with a message safe to show the user."""


# --- entitlements ---------------------------------------------------------


def can_publish(company) -> bool:
    """True when ``company``'s plan includes the exchange (publishing side)."""
    if company is None:
        return False
    try:
        from billing.entitlements import has_feature
    except Exception:  # pragma: no cover - billing always installed
        return False
    return bool(has_feature(company, FEATURE))


def can_respond(company) -> bool:
    """Responding to partner requirements is free on every plan."""
    return company is not None


# --- partners -------------------------------------------------------------


def find_company(value):
    """Resolve a company by slug, or by the email of one of its owners."""
    text = (value or "").strip()
    if not text:
        return None
    company = Company.objects.filter(slug__iexact=text).first()
    if company is not None:
        return company
    membership = (
        Membership.objects.filter(user__email__iexact=text, role=Membership.OWNER)
        .select_related("company")
        .first()
    )
    return membership.company if membership else None


def invite_partner(company, target, created_by=None):
    """Ask ``target`` to partner with ``company``.

    ``target`` may be a Company, a slug or an owner's email.
    """
    if company is None:
        raise ExchangeError("No company selected.")
    if not isinstance(target, Company):
        resolved = find_company(target)
        if resolved is None:
            raise ExchangeError("No company found for that slug or owner email.")
        target = resolved
    if target.pk == company.pk:
        raise ExchangeError("You cannot partner with your own company.")

    existing = PartnerLink.between(company, target)
    if existing is not None:
        if existing.status == PartnerLink.BLOCKED:
            raise ExchangeError("That partnership is blocked.")
        if existing.status == PartnerLink.ACTIVE:
            raise ExchangeError(f"You are already partnered with {target.name}.")
        if existing.to_company_id == company.pk:
            # They asked first — accepting is the sensible reading of an invite.
            return accept_partner(existing, company)
        raise ExchangeError(f"An invite to {target.name} is already pending.")

    link = PartnerLink.objects.create(
        from_company=company, to_company=target, created_by=created_by
    )
    notify_company(
        target,
        "exchange_partner_invite",
        {"partner": company.name},
        subject=f"{company.name} wants to partner on the exchange",
        body=(
            f"{company.name} has invited you to exchange requirements and candidates.\n"
            "Open Exchange ▸ Partners to accept."
        ),
    )
    return link


def accept_partner(link, company):
    """Accept a pending invite; only the invited company may do this."""
    if link.status == PartnerLink.BLOCKED:
        raise ExchangeError("That partnership is blocked.")
    if link.status == PartnerLink.ACTIVE:
        return link
    if link.to_company_id != getattr(company, "pk", None):
        raise ExchangeError("Only the invited company can accept this request.")
    link.status = PartnerLink.ACTIVE
    link.save(update_fields=["status", "updated_at"])
    notify_company(
        link.from_company,
        "exchange_partner_accepted",
        {"partner": company.name},
        subject=f"{company.name} accepted your exchange partnership",
        body=f"{company.name} is now an exchange partner. Their requirements are in your feed.",
    )
    return link


def block_partner(link, company):
    """Either side may block; the link stays as an audit trail."""
    if not link.involves(company):
        raise ExchangeError("That partnership does not involve your company.")
    link.status = PartnerLink.BLOCKED
    link.save(update_fields=["status", "updated_at"])
    return link


def unblock_partner(link, company):
    """Return a blocked link to PENDING so it can be re-accepted."""
    if not link.involves(company):
        raise ExchangeError("That partnership does not involve your company.")
    if link.status != PartnerLink.BLOCKED:
        return link
    link.status = PartnerLink.PENDING
    link.save(update_fields=["status", "updated_at"])
    return link


def partners(company):
    """Every link involving ``company``, newest first."""
    return PartnerLink.involving(company)


def active_partners(company):
    """Companies with an ACTIVE link to ``company``."""
    return Company.objects.filter(pk__in=PartnerLink.active_partner_ids(company))


# --- requirements ---------------------------------------------------------


def publish_requirement(
    job,
    *,
    created_by=None,
    title=None,
    client_name=None,
    description=None,
    location=None,
    skills=None,
    budget_ctc_min=None,
    budget_ctc_max=None,
    fee_split_pct=50,
    visibility=ExchangeRequirement.PARTNERS,
    expires_in_days=DEFAULT_EXPIRY_DAYS,
    expires_at=None,
):
    """Publish ``job`` to the exchange. Requires the ``exchange`` feature."""
    company = job.company
    if not can_publish(company):
        raise ExchangeError(
            "Publishing to the exchange needs the Agency plan. "
            "Responding to partner requirements is free on every plan."
        )
    split = int(fee_split_pct if fee_split_pct is not None else 50)
    if not 0 <= split <= 100:
        raise ExchangeError("Fee split must be between 0 and 100 percent.")
    if visibility not in dict(ExchangeRequirement.VISIBILITY_CHOICES):
        raise ExchangeError("Unknown visibility.")
    if (
        budget_ctc_min is not None
        and budget_ctc_max is not None
        and Decimal(budget_ctc_max) < Decimal(budget_ctc_min)
    ):
        raise ExchangeError("Maximum budget cannot be below the minimum.")

    if expires_at is None and expires_in_days:
        expires_at = timezone.now() + timedelta(days=int(expires_in_days))
    client = client_name
    if client is None:
        client = getattr(getattr(job, "client", None), "name", "") or ""

    requirement = ExchangeRequirement.objects.create(
        company=company,
        job=job,
        title=title or job.title,
        client_name=client,
        description=description if description is not None else job.description,
        location=location if location is not None else job.location,
        budget_ctc_min=budget_ctc_min,
        budget_ctc_max=budget_ctc_max,
        fee_split_pct=split,
        visibility=visibility,
        expires_at=expires_at,
        created_by=created_by,
    )
    chosen = list(skills) if skills is not None else list(job.skills.all())
    if chosen:
        requirement.skills.set(chosen)
    return requirement


def close_requirement(requirement, company, status=ExchangeRequirement.CLOSED):
    """Close (or mark filled) a requirement the caller owns."""
    if requirement.company_id != getattr(company, "pk", None):
        raise ExchangeError("That requirement belongs to another company.")
    requirement.status = status
    requirement.save(update_fields=["status", "updated_at"])
    return requirement


def my_requirements(company):
    return (
        ExchangeRequirement.objects.for_company(company)
        .select_related("job")
        .prefetch_related("skills")
        .annotate(submission_count=models.Count("submissions"))
        .order_by("-created_at", "-id")
    )


def feed(company, *, skills=None, location="", budget_min=None, query=""):
    """OPEN requirements ``company`` may respond to, newest first.

    Partner-visible requirements come from ACTIVE partners only; NETWORK ones
    from anybody. A company never sees its own requirements in the feed.
    """
    if company is None:
        return ExchangeRequirement.objects.none()
    partner_ids = PartnerLink.active_partner_ids(company)
    qs = (
        ExchangeRequirement.objects.filter(status=ExchangeRequirement.OPEN)
        .exclude(company=company)
        .filter(
            models.Q(visibility=ExchangeRequirement.NETWORK)
            | models.Q(visibility=ExchangeRequirement.PARTNERS, company_id__in=partner_ids)
        )
        .filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now()))
        .select_related("company", "job")
        .prefetch_related("skills")
    )
    if skills:
        ids = [s.pk if hasattr(s, "pk") else int(s) for s in skills]
        names = list(Skill.objects.filter(pk__in=ids).values_list("name", flat=True))
        # Skills are per-company rows, so match partners' equivalents by name.
        qs = qs.filter(skills__name__in=names).distinct() if names else qs.none()
    if location:
        qs = qs.filter(location__icontains=location)
    if budget_min is not None:
        qs = qs.filter(
            models.Q(budget_ctc_max__gte=budget_min) | models.Q(budget_ctc_max__isnull=True)
        )
    if query:
        qs = qs.filter(models.Q(title__icontains=query) | models.Q(description__icontains=query))
    return qs


def expire_requirements(now=None):
    """Mark every past-due OPEN requirement CLOSED; returns how many."""
    now = now or timezone.now()
    due = ExchangeRequirement.objects.filter(
        status=ExchangeRequirement.OPEN, expires_at__isnull=False, expires_at__lte=now
    )
    count = due.count()
    if count:
        due.update(status=ExchangeRequirement.CLOSED, updated_at=now)
    return count


# --- submissions ----------------------------------------------------------


def snapshot_from(source):
    """Build a candidate snapshot from a TalentProfile or CandidateProfile."""
    skills = [s.name for s in source.skills.all()] if hasattr(source, "skills") else []
    user = getattr(source, "user", None)
    if user is not None:  # jobs.CandidateProfile
        name = (user.get_full_name() or "").strip() or user.email
        email = user.email
    else:  # talent.TalentProfile
        name = (getattr(source, "name", "") or "").strip() or getattr(source, "email", "")
        email = getattr(source, "email", "")
    return {
        "name": name,
        "email": email,
        "phone": getattr(source, "phone", "") or "",
        "headline": getattr(source, "headline", "") or "",
        "experience_years": str(getattr(source, "experience_years", "") or ""),
        "location": getattr(source, "location", "") or "",
        "skills": skills,
    }


def submit_candidate(requirement, company, source, note="", created_by=None):
    """Offer ``source`` (a TalentProfile or CandidateProfile) to ``requirement``."""
    if company is None:
        raise ExchangeError("No company selected.")
    if requirement.company_id == company.pk:
        raise ExchangeError("You cannot submit candidates to your own requirement.")
    if not requirement.is_visible_to(company):
        raise ExchangeError("That requirement is not open to your company.")
    if not requirement.is_open:
        raise ExchangeError("That requirement is no longer open.")

    snapshot = snapshot_from(source)
    digest = email_hash(snapshot.get("email"))
    if digest and requirement.submissions.filter(email_hash=digest).exists():
        raise ExchangeError(
            "This candidate has already been submitted for this requirement."
        )

    resume = getattr(source, "resume", None)
    kwargs = {}
    if hasattr(source, "user"):
        kwargs["candidate_profile"] = source
    else:
        kwargs["talent_profile"] = source
    try:
        with transaction.atomic():
            submission = ExchangeSubmission.objects.create(
                requirement=requirement,
                responding_company=company,
                candidate_snapshot=snapshot,
                email_hash=digest,
                resume_file=resume.name if resume else "",
                note=note or "",
                created_by=created_by,
                **kwargs,
            )
    except IntegrityError as exc:
        raise ExchangeError(
            "This candidate has already been submitted for this requirement."
        ) from exc

    notify_company(
        requirement.company,
        "exchange_submission_received",
        {
            "requirement": requirement.title,
            "partner": company.name,
            "reference": submission.reference,
        },
        subject=f"New exchange candidate for {requirement.title}",
        body=(
            f"{company.name} submitted a candidate ({submission.reference}) for "
            f"{requirement.title}. Contact details stay hidden until you reveal them."
        ),
    )
    return submission


def submissions_for_requirement(requirement, company):
    """The inbox for one of your own requirements."""
    if requirement.company_id != getattr(company, "pk", None):
        raise ExchangeError("That requirement belongs to another company.")
    return requirement.submissions.select_related("responding_company", "requirement").all()


def my_submissions(company):
    """The outbox: everything ``company`` has submitted."""
    if company is None:
        return ExchangeSubmission.objects.none()
    return ExchangeSubmission.objects.filter(responding_company=company).select_related(
        "requirement", "requirement__company"
    )


def _require_requester(submission, company):
    if submission.requirement.company_id != getattr(company, "pk", None):
        raise ExchangeError("Only the requesting company can do that.")


def set_status(submission, company, status):
    """Move a submission along its status flow (requester only)."""
    _require_requester(submission, company)
    if status not in dict(ExchangeSubmission.STATUS_CHOICES):
        raise ExchangeError("Unknown status.")
    if status == ExchangeSubmission.HIRED:
        raise ExchangeError("Use mark_hired to record a placement.")
    submission.status = status
    submission.save(update_fields=["status", "updated_at"])
    return submission


def shortlist(submission, company):
    """Shortlist a candidate and tell the partner."""
    set_status(submission, company, ExchangeSubmission.SHORTLISTED)
    notify_company(
        submission.responding_company,
        "exchange_submission_shortlisted",
        {"requirement": submission.requirement.title, "reference": submission.reference},
        subject=f"Shortlisted: {submission.reference}",
        body=(
            f"{submission.requirement.company.name} shortlisted {submission.reference} "
            f"for {submission.requirement.title}."
        ),
    )
    return submission


def reject(submission, company, reason=""):
    set_status(submission, company, ExchangeSubmission.REJECTED)
    if reason:
        submission.note = f"{submission.note}\n\nRejected: {reason}".strip()
        submission.save(update_fields=["note", "updated_at"])
    notify_company(
        submission.responding_company,
        "exchange_submission_rejected",
        {"requirement": submission.requirement.title, "reference": submission.reference},
        subject=f"Not proceeding: {submission.reference}",
        body=(
            f"{submission.requirement.company.name} passed on {submission.reference} "
            f"for {submission.requirement.title}."
        ),
    )
    return submission


def reveal(submission, company):
    """Unmask the candidate for the requester and tell the partner."""
    _require_requester(submission, company)
    if submission.is_revealed:
        return submission
    submission.revealed_at = timezone.now()
    if submission.status == ExchangeSubmission.SUBMITTED:
        submission.status = ExchangeSubmission.SHORTLISTED
    submission.save(update_fields=["revealed_at", "status", "updated_at"])
    notify_company(
        submission.responding_company,
        "exchange_submission_revealed",
        {"requirement": submission.requirement.title, "reference": submission.reference},
        subject=f"Contact details revealed: {submission.reference}",
        body=(
            f"{submission.requirement.company.name} accepted {submission.reference} and can "
            f"now see the candidate's contact details for {submission.requirement.title}."
        ),
    )
    return submission


# --- deals ----------------------------------------------------------------


def mark_hired(submission, placement_fee_inr, company=None, platform_fee_pct=None):
    """Record a placement: create the deal and post both platform-fee charges."""
    if company is not None:
        _require_requester(submission, company)
    fee = Decimal(placement_fee_inr or 0)
    if fee <= 0:
        raise ExchangeError("Enter the placement fee that was agreed.")
    if hasattr(submission, "deal") and submission.deal is not None:
        raise ExchangeError("This placement has already been recorded.")

    with transaction.atomic():
        submission.status = ExchangeSubmission.HIRED
        if submission.revealed_at is None:
            submission.revealed_at = timezone.now()
        submission.save(update_fields=["status", "revealed_at", "updated_at"])
        requirement = submission.requirement
        requirement.status = ExchangeRequirement.FILLED
        requirement.save(update_fields=["status", "updated_at"])
        deal = ExchangeDeal.objects.create(
            submission=submission,
            placement_fee_inr=fee,
            split_pct=requirement.fee_split_pct,
            platform_fee_pct=(
                ExchangeDeal.DEFAULT_PLATFORM_FEE_PCT
                if platform_fee_pct is None
                else int(platform_fee_pct)
            ),
        )
    post_platform_fees(deal)
    notify_company(
        submission.responding_company,
        "exchange_submission_hired",
        {
            "requirement": requirement.title,
            "reference": submission.reference,
            "share": str(deal.responder_share),
        },
        subject=f"Placed: {submission.reference}",
        body=(
            f"{requirement.company.name} hired {submission.reference} for {requirement.title}. "
            f"Your share is ₹{deal.responder_share}."
        ),
    )
    return deal


def post_platform_fees(deal):
    """Charge each side its half of the platform fee via the billing ledger.

    The billing ledger is imported late: exchange must keep working (and stay
    testable) when it is unavailable — the deal is still recorded, only the
    charge is skipped.
    """
    try:
        from billing.ledger import add_charge
    except Exception:
        logger.info("exchange: billing.ledger unavailable; deal %s not charged", deal.pk)
        return 0

    posted = 0
    for company, amount, role in (
        (deal.requester_company, deal.requester_platform_fee, "requester"),
        (deal.responder_company, deal.responder_platform_fee, "responder"),
    ):
        if amount <= 0:
            continue
        try:
            add_charge(
                company,
                CHARGE_KIND,
                f"Exchange platform fee ({role}) — {deal.submission.requirement.title}",
                amount,
                f"exchange-deal-{deal.pk}-{role}",
            )
            posted += 1
        except Exception:
            logger.warning(
                "exchange: add_charge failed for deal %s / %s", deal.pk, company, exc_info=True
            )
    if posted:
        deal.charged_at = timezone.now()
        deal.status = ExchangeDeal.INVOICED
        deal.save(update_fields=["charged_at", "status", "updated_at"])
    return posted


def flag_dispute(deal, company, reason):
    """Either party may flag a deal; the reason is recorded for support."""
    if getattr(company, "pk", None) not in (
        deal.requester_company.pk,
        deal.responder_company.pk,
    ):
        raise ExchangeError("That deal does not involve your company.")
    if not (reason or "").strip():
        raise ExchangeError("Describe the problem so we can look into it.")
    deal.disputed = True
    deal.dispute_reason = reason.strip()
    deal.disputed_at = timezone.now()
    deal.save(update_fields=["disputed", "dispute_reason", "disputed_at", "updated_at"])
    other = (
        deal.responder_company
        if company.pk == deal.requester_company.pk
        else deal.requester_company
    )
    notify_company(
        other,
        "exchange_deal_disputed",
        {"deal": deal.pk, "reason": deal.dispute_reason},
        subject=f"Exchange deal #{deal.pk} disputed",
        body=f"{company.name} raised a dispute on deal #{deal.pk}: {deal.dispute_reason}",
    )
    return deal


def deals_for(company):
    """Every deal ``company`` is a party to, newest first."""
    if company is None:
        return ExchangeDeal.objects.none()
    return ExchangeDeal.objects.filter(
        models.Q(submission__responding_company=company)
        | models.Q(submission__requirement__company=company)
    ).select_related(
        "submission",
        "submission__requirement",
        "submission__requirement__company",
        "submission__responding_company",
    )
