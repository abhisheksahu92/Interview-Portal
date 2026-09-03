"""Pack purchase / installation and paid-order handling."""

from django.db import transaction

from marketplace.models import PackPurchase


class BillingNotConfigured(Exception):
    """A paid pack was requested but no payment gateway is available."""


def skill_for(company, name):
    """Get-or-create the company's ``jobs.Skill`` matching ``name``."""
    from jobs.models import Skill

    name = (name or "").strip()
    if not name:
        return None
    skill = Skill.objects.filter(company=company, name__iexact=name).first()
    if skill is not None:
        return skill
    return Skill.objects.create(company=company, name=name)


@transaction.atomic
def install_pack(company, pack, user=None, invoice_ref=""):
    """Copy ``pack``'s questions into ``company``'s bank with source=MARKETPLACE.

    Idempotent: an already-installed pack returns its existing purchase without
    duplicating questions.
    """
    from assessments.models import Question

    purchase = PackPurchase.objects.filter(company=company, pack=pack).first()
    if purchase is not None:
        return purchase

    skill = skill_for(company, pack.skill_name)
    created = 0
    for item in pack.questions or []:
        kind = (item.get("kind") or Question.MCQ).upper()
        if kind not in dict(Question.KIND_CHOICES):
            kind = Question.MCQ
        difficulty = (item.get("difficulty") or Question.MEDIUM).upper()
        if difficulty not in dict(Question.DIFFICULTY_CHOICES):
            difficulty = Question.MEDIUM
        options = item.get("options") or []
        correct = item.get("correct_option")
        Question.objects.create(
            company=company,
            skill=skill,
            kind=kind,
            text=item.get("text", ""),
            options=options if kind == Question.MCQ else [],
            correct_option=correct if kind == Question.MCQ else None,
            difficulty=difficulty,
            source=Question.MARKETPLACE,
        )
        created += 1

    purchase = PackPurchase.objects.create(
        company=company,
        pack=pack,
        invoice_ref=invoice_ref or "",
        purchased_by=user,
        questions_created=created,
    )
    pack.downloads = (pack.downloads or 0) + 1
    pack.save(update_fields=["downloads"])
    return purchase


def create_order(company, pack):
    """Start a paid checkout for ``pack`` via the billing app's payment gateway.

    ``billing`` owns every payment integration, so this only ever reaches it
    through a late import and raises :class:`BillingNotConfigured` when no
    gateway is usable, letting the view show a clear "billing not configured"
    message instead of failing.
    """
    gateway = _payment_gateway()
    if gateway is None:
        raise BillingNotConfigured("No payment gateway is configured for marketplace purchases.")
    amount_paise = int(round(float(pack.price_inr) * 100))
    try:
        client = gateway.get_client()
        return client.order.create(
            {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": f"pack-{pack.slug}-{company.pk}",
                "notes": {"company_id": str(company.pk), "pack": pack.slug},
            }
        )
    except Exception as exc:  # gateway unavailable / not installed / network off
        raise BillingNotConfigured(str(exc)) from exc


def _payment_gateway():
    """The billing gateway module when it is configured, else None."""
    try:
        from billing import razorpay_gateway
    except ImportError:
        return None
    is_configured = getattr(razorpay_gateway, "is_configured", None)
    if not callable(is_configured) or not is_configured():
        return None
    if not callable(getattr(razorpay_gateway, "get_client", None)):
        return None
    return razorpay_gateway
