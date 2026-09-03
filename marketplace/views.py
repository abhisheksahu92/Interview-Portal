"""Marketplace storefront, pack installation and the verified talent pool."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from billing.entitlements import has_feature, require_feature
from core.permissions import role_required
from marketplace.models import PackPurchase, QuestionPack
from marketplace.pool import card_for, invite, search, verified_pool_queryset
from marketplace.services import BillingNotConfigured, create_order, install_pack


def _published_packs(request):
    qs = QuestionPack.objects.filter(published=True)
    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(skill_name__icontains=query)
            | Q(description__icontains=query)
        )
    return qs, query


@login_required
@role_required("OWNER", "RECRUITER")
def index(request):
    """Storefront: published question packs, with an "Installed" state."""
    packs, query = _published_packs(request)
    installed = set(
        PackPurchase.objects.filter(company=request.company).values_list("pack_id", flat=True)
    )
    return render(
        request,
        "marketplace/index.html",
        {
            "packs": packs,
            "q": query,
            "installed_ids": installed,
            "can_pool": has_feature(request.company, "talent_pool_search"),
        },
    )


@login_required
@role_required("OWNER", "RECRUITER")
def pack_detail(request, slug):
    """Pack page with a 3-question preview and the install/buy action."""
    pack = get_object_or_404(QuestionPack, slug=slug, published=True)
    purchase = PackPurchase.objects.filter(company=request.company, pack=pack).first()
    return render(
        request,
        "marketplace/pack_detail.html",
        {"pack": pack, "purchase": purchase, "preview": pack.preview(3)},
    )


@login_required
@role_required("OWNER", "RECRUITER")
@require_POST
def pack_install(request, slug):
    """Install a free pack directly; start a checkout for a paid one."""
    pack = get_object_or_404(QuestionPack, slug=slug, published=True)
    if PackPurchase.objects.filter(company=request.company, pack=pack).exists():
        messages.info(request, f"{pack.title} is already installed.")
        return redirect(reverse("marketplace:pack_detail", args=[pack.slug]))

    if pack.is_free:
        purchase = install_pack(request.company, pack, user=request.user)
        messages.success(
            request, f"Installed {pack.title} — {purchase.questions_created} questions added."
        )
        return redirect(reverse("marketplace:pack_detail", args=[pack.slug]))

    try:
        order = create_order(request.company, pack)
    except BillingNotConfigured:
        messages.error(
            request,
            "Billing is not configured, so paid packs cannot be purchased yet.",
        )
        return redirect(reverse("marketplace:pack_detail", args=[pack.slug]))
    return render(request, "marketplace/checkout.html", {"pack": pack, "order": order})


@login_required
@role_required("OWNER", "RECRUITER")
def purchases(request):
    """The company's installed packs."""
    rows = (
        PackPurchase.objects.filter(company=request.company)
        .select_related("pack")
        .order_by("-purchased_at")
    )
    return render(request, "marketplace/purchases.html", {"purchases": rows})


@login_required
@role_required("OWNER", "RECRUITER")
@require_feature("talent_pool_search")
def pool(request):
    """Cross-company search of verified, opted-in candidates (anonymised)."""
    cards = search(
        query=request.GET.get("q", ""),
        skill=request.GET.get("skill", ""),
        min_experience=request.GET.get("min_experience", ""),
    )
    return render(
        request,
        "marketplace/pool.html",
        {
            "cards": cards,
            "q": request.GET.get("q", ""),
            "skill": request.GET.get("skill", ""),
            "min_experience": request.GET.get("min_experience", ""),
        },
    )


@login_required
@role_required("OWNER", "RECRUITER")
@require_feature("talent_pool_search")
@require_POST
def pool_invite(request, profile_id):
    """Invite a pooled candidate to apply, without revealing their contact data."""
    profile = get_object_or_404(verified_pool_queryset(), pk=profile_id)
    card = card_for(profile)
    if invite(profile, request.company, actor=request.user):
        messages.success(request, f"Invitation sent to {card.reference}.")
    else:
        messages.warning(request, f"Could not reach {card.reference} right now.")
    return redirect(reverse("marketplace:pool"))


@login_required
@require_POST
def pool_opt_in(request):
    """Candidate toggle for ``CandidateProfile.share_in_pool``."""
    profile = getattr(request.user, "candidate_profile", None)
    if profile is None:
        raise PermissionDenied("Only candidates can join the talent pool.")
    profile.share_in_pool = request.POST.get("share_in_pool") in {"1", "on", "true", "True"}
    profile.save(update_fields=["share_in_pool"])
    messages.success(
        request,
        "You are now visible to verified employers."
        if profile.share_in_pool
        else "You have left the talent pool.",
    )
    if getattr(request, "htmx", False):
        return render(request, "marketplace/partials/pool_opt_in.html", {"profile": profile})
    return redirect(request.POST.get("next") or reverse("web:candidate_profile"))
