"""The seeker portal at ``/portal/opportunities/``.

Every page is for a logged-in candidate: company members have their own
workspace and would only be confused by a job-hunting feed, so
:func:`_seeker_view` turns them away rather than quietly showing an empty page.

The one non-obvious response is the quota wall: over the free limit we return
**402 Payment Required** with the upgrade CTA, not a redirect, so an HTMX bulk
action shows the wall in place instead of silently doing nothing.
"""

import logging
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from seeker import mail, services
from seeker.forms import AddLeadForm, PreferencesForm, SMTPMailboxForm
from seeker.models import MAX_BULK_SENDS, Outreach, SavedItem

logger = logging.getLogger(__name__)

GMAIL_STATE_KEY = "seeker_gmail_state"


def _seeker_view(view_func):
    """Logged in, a candidate, and never inside a tenant workspace."""

    def wrapper(request, *args, **kwargs):
        if not getattr(request.user, "is_candidate", False):
            raise PermissionDenied("The opportunity network is for candidate accounts.")
        if getattr(request, "company", None) is not None:
            raise PermissionDenied("Company members use the recruiter workspace.")
        request.seeker = services.get_profile(request.user)
        return view_func(request, *args, **kwargs)

    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return login_required(wrapper)


def _quota_wall(request, message):
    """402 + upgrade CTA. The one page that answers 'you have sent enough'."""
    return render(
        request,
        "seeker/quota.html",
        {"seeker": request.seeker, "reason": message},
        status=402,
    )


def _selected_items(request):
    """Saved items ticked on the Saved page, scoped to this seeker."""
    ids = request.POST.getlist("item") or request.GET.getlist("item")
    return list(
        SavedItem.objects.filter(seeker=request.seeker, pk__in=ids).select_related(
            "lead", "job__company"
        )
    )


# --------------------------------------------------------------------------- #
# Feed
# --------------------------------------------------------------------------- #


@_seeker_view
def feed(request):
    query = request.GET.get("q", "").strip()
    kind = request.GET.get("kind", "").strip()
    remote = True if request.GET.get("remote") else None
    cards = services.build_feed(request.seeker, query=query, kind=kind, remote=remote)
    context = {
        "seeker": request.seeker,
        "cards": cards,
        "q": query,
        "kind": kind,
        "remote": bool(remote),
        "saved_count": request.seeker.saved_items.count(),
    }
    template = (
        "seeker/partials/feed_cards.html"
        if request.headers.get("HX-Request")
        else "seeker/feed.html"
    )
    return render(request, template, context)


@_seeker_view
@require_POST
def save(request, kind, pk):
    """Save one card. Answers with the card's button so HTMX can swap it."""
    if kind == "lead":
        try:
            from sources.models import Lead
        except ImportError:
            raise PermissionDenied("Lead sources are not available.") from None
        services.save_lead(request.seeker, get_object_or_404(Lead, pk=pk))
    else:
        from jobs.models import Job

        services.save_job(request.seeker, get_object_or_404(Job, pk=pk))
    if request.headers.get("HX-Request"):
        return render(request, "seeker/partials/saved_button.html", {})
    return redirect("seeker:feed")


# --------------------------------------------------------------------------- #
# Saved + bulk actions
# --------------------------------------------------------------------------- #


@_seeker_view
def saved(request):
    items = (
        request.seeker.saved_items.select_related("lead__source", "job__company")
        .prefetch_related("outreach")
        .all()
    )
    status = request.GET.get("status", "").strip()
    if status:
        items = items.filter(status=status)
    return render(
        request,
        "seeker/saved.html",
        {
            "seeker": request.seeker,
            "items": items,
            "status": status,
            "statuses": SavedItem.STATUSES,
            "max_bulk": MAX_BULK_SENDS,
        },
    )


@_seeker_view
@require_POST
def bulk(request):
    """One POST behind the bulk bar: apply, open & track, or draft emails."""
    action = request.POST.get("action", "")
    items = _selected_items(request)
    if not items:
        messages.info(request, "Tick at least one saved opportunity first.")
        return redirect("seeker:saved")

    if action == "apply":
        applied = services.bulk_apply(request.seeker, items)
        messages.success(
            request,
            f"Applied to {applied} job{'' if applied == 1 else 's'}."
            if applied
            else "You had already applied to those jobs.",
        )
        return redirect("seeker:saved")

    if action == "open":
        marked = services.mark_opened(request.seeker, items)
        messages.success(request, f"Marked {marked} as applied.")
        return redirect("seeker:saved")

    if action == "draft":
        mailable = [item for item in items if item.contact_email]
        if not mailable:
            messages.info(request, "None of those have a contact address to write to.")
            return redirect("seeker:saved")
        try:
            services.check_quota(request.seeker, len(mailable))
        except services.QuotaExceeded as exc:
            return _quota_wall(request, str(exc))
        ids = "&".join(f"item={item.pk}" for item in mailable)
        return redirect(f"{reverse('seeker:compose')}?{ids}")

    if action == "archive":
        SavedItem.objects.filter(seeker=request.seeker, pk__in=[i.pk for i in items]).update(
            status=SavedItem.ARCHIVED
        )
        messages.success(request, "Archived.")
        return redirect("seeker:saved")

    messages.error(request, "Unknown action.")
    return redirect("seeker:saved")


# --------------------------------------------------------------------------- #
# Compose
# --------------------------------------------------------------------------- #


@_seeker_view
def compose(request):
    """Draft on GET, send on POST. Drafts are AI-written then edited by hand."""
    if request.method == "POST":
        return _compose_send(request)

    items = _selected_items(request)
    if not items:
        messages.info(request, "Pick the opportunities you want to write to.")
        return redirect("seeker:saved")
    try:
        services.check_quota(request.seeker, len(items))
    except services.QuotaExceeded as exc:
        return _quota_wall(request, str(exc))
    drafts = services.draft_for_items(request.seeker, items)
    if not drafts:
        messages.info(request, "None of those have a contact address to write to.")
        return redirect("seeker:saved")
    return render(
        request,
        "seeker/compose.html",
        {
            "seeker": request.seeker,
            "drafts": drafts,
            "resume": services.resume_attachment(request.seeker) is not None,
        },
    )


def _compose_send(request):
    ids = request.POST.getlist("outreach_id")
    drafts = list(
        Outreach.objects.filter(
            seeker=request.seeker, pk__in=ids, status=Outreach.DRAFT
        ).select_related("saved_item")
    )
    if not drafts:
        messages.info(request, "Nothing left to send.")
        return redirect("seeker:saved")
    if not request.seeker.mailbox_ready:
        messages.error(request, "Connect your own mailbox before sending.")
        return redirect("seeker:mailbox")

    # Apply the seeker's edits before anything leaves. A recipient the seeker
    # typed is allowed (it is their mailbox and their lead), but a malformed one
    # is marked failed here rather than bouncing later with a cryptic SMTP error.
    sendable = []
    for draft in drafts:
        draft.subject = request.POST.get(f"subject_{draft.pk}", draft.subject)[:300]
        draft.body = request.POST.get(f"body_{draft.pk}", draft.body)
        draft.to_email = request.POST.get(f"to_{draft.pk}", draft.to_email).strip()
        try:
            validate_email(draft.to_email)
        except ValidationError:
            draft.status = Outreach.FAILED
            draft.error = "Recipient address is not valid."
            draft.save(update_fields=["subject", "body", "to_email", "status", "error"])
            continue
        draft.save(update_fields=["subject", "body", "to_email"])
        sendable.append(draft)
    invalid = len(drafts) - len(sendable)
    drafts = sendable
    if not drafts:
        messages.error(request, "No valid recipient addresses to send to.")
        return redirect("seeker:saved")

    try:
        sent, failed = services.send_many(request.seeker, drafts)
    except services.QuotaExceeded as exc:
        return _quota_wall(request, str(exc))
    if sent:
        messages.success(request, f"Sent {sent} mail{'' if sent == 1 else 's'}.")
    if failed or invalid:
        messages.error(
            request, f"{failed + invalid} could not be sent; see the saved list for why."
        )
    return redirect("seeker:saved")


# --------------------------------------------------------------------------- #
# Mailbox
# --------------------------------------------------------------------------- #


@_seeker_view
def mailbox(request):
    seeker = request.seeker
    stored = seeker.get_mailbox_config()
    if request.method == "POST":
        form = SMTPMailboxForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            seeker.mailbox_kind = seeker.SMTP
            seeker.mailbox_email = data["mailbox_email"]
            seeker.set_mailbox_config(
                {
                    "host": data["host"],
                    "port": data["port"],
                    "username": data["username"],
                    # A blank field means "keep what is saved", not "clear it".
                    "password": data["password"] or stored.get("password", ""),
                    "use_ssl": data["use_ssl"],
                }
            )
            seeker.save(update_fields=["mailbox_kind", "mailbox_email", "mailbox_config"])
            messages.success(request, "Mailbox saved. Mail will go out from your address.")
            return redirect("seeker:mailbox")
    else:
        form = SMTPMailboxForm(
            initial={
                "mailbox_email": seeker.mailbox_email or request.user.email,
                "host": stored.get("host", ""),
                "port": stored.get("port", 587),
                "username": stored.get("username", ""),
                "use_ssl": stored.get("use_ssl", False),
            }
        )
    return render(
        request,
        "seeker/mailbox.html",
        {
            "seeker": seeker,
            "form": form,
            "preferences": PreferencesForm(instance=seeker),
            "gmail_available": mail.gmail_configured(),
        },
    )


@_seeker_view
@require_POST
def preferences(request):
    form = PreferencesForm(request.POST, instance=request.seeker)
    if form.is_valid():
        form.save()
        messages.success(request, "Preferences saved.")
    return redirect("seeker:mailbox")


@_seeker_view
@require_POST
def mailbox_disconnect(request):
    seeker = request.seeker
    seeker.mailbox_kind = seeker.NONE
    seeker.mailbox_config = ""
    seeker.save(update_fields=["mailbox_kind", "mailbox_config"])
    messages.success(request, "Mailbox disconnected.")
    return redirect("seeker:mailbox")


@_seeker_view
def gmail_connect(request):
    """Kick off Google consent for the send-only scope."""
    if not mail.gmail_configured():
        messages.error(request, "Gmail sending is not configured on this install.")
        return redirect("seeker:mailbox")
    state = secrets.token_urlsafe(24)
    request.session[GMAIL_STATE_KEY] = state
    redirect_uri = request.build_absolute_uri(reverse("seeker:gmail_callback"))
    return redirect(mail.gmail_authorize_url(redirect_uri, state))


@_seeker_view
def gmail_callback(request):
    expected = request.session.pop(GMAIL_STATE_KEY, "")
    if not expected or request.GET.get("state") != expected:
        messages.error(request, "That Google sign-in did not match. Please try again.")
        return redirect("seeker:mailbox")
    code = request.GET.get("code", "")
    if not code:
        messages.error(request, "Google did not return an authorisation code.")
        return redirect("seeker:mailbox")
    redirect_uri = request.build_absolute_uri(reverse("seeker:gmail_callback"))
    try:
        tokens = mail.gmail_exchange_code(code, redirect_uri)
    except mail.SendError as exc:
        messages.error(request, str(exc))
        return redirect("seeker:mailbox")
    seeker = request.seeker
    seeker.mailbox_kind = seeker.GMAIL
    seeker.mailbox_email = seeker.mailbox_email or request.user.email
    seeker.set_mailbox_config({"refresh_token": tokens.get("refresh_token", "")})
    seeker.save(update_fields=["mailbox_kind", "mailbox_email", "mailbox_config"])
    messages.success(request, "Gmail connected. Mail will go out from your own account.")
    return redirect("seeker:mailbox")


# --------------------------------------------------------------------------- #
# Manual capture + upgrade
# --------------------------------------------------------------------------- #


@_seeker_view
def add_lead(request):
    """Paste a posting from a site we may not fetch ourselves."""
    # The bookmarklet arrives as a GET with the page's URL, title and selection.
    initial = {key: request.GET.get(key, "") for key in ("url", "title", "text")}
    form = AddLeadForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        lead = services.create_manual_lead(
            request.seeker,
            url=form.cleaned_data["url"],
            text=form.cleaned_data["text"],
            title=form.cleaned_data["title"],
            company=form.cleaned_data["company"],
        )
        if lead is None:
            messages.error(request, "Saving pasted leads is not available right now.")
        else:
            messages.success(request, "Saved. It is on your list.")
            return redirect("seeker:saved")
    target = request.build_absolute_uri(reverse("seeker:add_lead"))
    bookmarklet = (
        "javascript:(function(){var u=encodeURIComponent(location.href),"
        "t=encodeURIComponent(document.title),"
        "s=encodeURIComponent((window.getSelection()+'').slice(0,600));"
        "window.open('" + target + "?url='+u+'&title='+t+'&text='+s,'_blank');})();"
    )
    return render(
        request,
        "seeker/add_lead.html",
        {"seeker": request.seeker, "form": form, "bookmarklet": bookmarklet},
    )


@_seeker_view
def upgrade(request):
    """Records interest in Pro. No payment code lives here on purpose."""
    if request.method == "POST":
        request.seeker.upgrade_requested_at = timezone.now()
        request.seeker.save(update_fields=["upgrade_requested_at"])
        messages.success(request, "Thanks — we will be in touch about Pro.")
        return redirect("seeker:saved")
    return render(request, "seeker/upgrade.html", {"seeker": request.seeker})
