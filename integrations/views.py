"""Owner-only integrations UI: webhooks, delivery log, connectors, API keys.

Every view requires an OWNER role *and* the ``integrations`` plan feature, so
the whole section 403s with plan-aware copy on lower tiers (see
``core.views.permission_denied``).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from billing.entitlements import require_feature
from core.permissions import role_required
from integrations import tokens
from integrations.delivery import send_test_event
from integrations.events import EVENT_CHOICES
from integrations.forms import ConnectorForm, WebhookForm, connector_configs
from integrations.models import ConnectorConfig, ConnectorRun, OutboundWebhook, WebhookDelivery
from integrations.services import probe_connection

#: Applied to every view in this module, in this order.
FEATURE = "integrations"


def owner_only(view):
    """login + OWNER role + ``integrations`` entitlement."""
    return login_required(role_required("OWNER")(require_feature(FEATURE)(view)))


def _webhook(request, pk):
    return get_object_or_404(OutboundWebhook, pk=pk, company=request.company)


@owner_only
def index(request):
    """Webhook list with recent delivery health."""
    webhooks = OutboundWebhook.objects.for_company(request.company)
    recent = (
        WebhookDelivery.objects.for_company(request.company)
        .select_related("webhook")[:10]
    )
    return render(
        request,
        "integrations/index.html",
        {
            "webhooks": webhooks,
            "recent_deliveries": recent,
            "pending_count": WebhookDelivery.objects.for_company(request.company)
            .filter(status=WebhookDelivery.PENDING)
            .count(),
            "failed_count": WebhookDelivery.objects.for_company(request.company)
            .filter(status=WebhookDelivery.FAILED)
            .count(),
        },
    )


@owner_only
def webhook_create(request):
    form = WebhookForm(request.POST or None, company=request.company)
    if request.method == "POST" and form.is_valid():
        webhook = form.save(commit=False)
        webhook.created_by = request.user
        webhook.save()
        messages.success(
            request,
            f"Webhook “{webhook.name}” created. Its signing secret is shown on the edit page.",
        )
        return redirect(reverse("integrations:webhook_edit", args=[webhook.pk]))
    return render(
        request,
        "integrations/webhook_form.html",
        {"form": form, "webhook": None, "events": EVENT_CHOICES},
    )


@owner_only
def webhook_edit(request, pk):
    webhook = _webhook(request, pk)
    form = WebhookForm(request.POST or None, instance=webhook, company=request.company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Webhook updated.")
        return redirect(reverse("integrations:webhook_edit", args=[webhook.pk]))
    return render(
        request,
        "integrations/webhook_form.html",
        {
            "form": form,
            "webhook": webhook,
            "events": EVENT_CHOICES,
            "deliveries": webhook.deliveries.all()[:20],
        },
    )


@owner_only
@require_POST
def webhook_delete(request, pk):
    webhook = _webhook(request, pk)
    name = webhook.name
    webhook.delete()
    messages.success(request, f"Webhook “{name}” deleted.")
    return redirect(reverse("integrations:index"))


@owner_only
@require_POST
def webhook_rotate(request, pk):
    webhook = _webhook(request, pk)
    webhook.rotate_secret()
    messages.warning(
        request,
        "Signing secret rotated — update your receiver before the next event.",
    )
    return redirect(reverse("integrations:webhook_edit", args=[webhook.pk]))


@owner_only
@require_POST
def webhook_test(request, pk):
    webhook = _webhook(request, pk)
    delivery = send_test_event(webhook)
    if delivery.status == WebhookDelivery.SENT:
        messages.success(request, f"Test event accepted (HTTP {delivery.response_code}).")
    else:
        messages.error(request, f"Test event failed: {delivery.last_error}")
    return redirect(reverse("integrations:webhook_edit", args=[webhook.pk]))


@owner_only
def deliveries(request):
    """The delivery log, filterable by status and webhook."""
    qs = WebhookDelivery.objects.for_company(request.company).select_related("webhook")
    status = (request.GET.get("status") or "").upper()
    if status in dict(WebhookDelivery.STATUS_CHOICES):
        qs = qs.filter(status=status)
    webhook_id = request.GET.get("webhook")
    if webhook_id and webhook_id.isdigit():
        qs = qs.filter(webhook_id=int(webhook_id))
    return render(
        request,
        "integrations/deliveries.html",
        {
            "deliveries": qs[:200],
            "status": status,
            "statuses": WebhookDelivery.STATUS_CHOICES,
            "webhooks": OutboundWebhook.objects.for_company(request.company),
            "selected_webhook": webhook_id,
        },
    )


@owner_only
@require_POST
def delivery_redeliver(request, pk):
    delivery = get_object_or_404(
        WebhookDelivery, pk=pk, webhook__company=request.company
    )
    delivery.reset_for_redelivery()
    from integrations.delivery import attempt_delivery

    if attempt_delivery(delivery):
        messages.success(request, f"Redelivered (HTTP {delivery.response_code}).")
    else:
        messages.error(request, f"Redelivery failed: {delivery.last_error}")
    return redirect(request.POST.get("next") or reverse("integrations:deliveries"))


@owner_only
def connectors(request):
    configs = connector_configs(request.company)
    rows = []
    for config in configs:
        adapter = config.adapter()
        rows.append(
            {
                "config": config,
                "adapter": adapter,
                "label": adapter.label if adapter else config.get_kind_display(),
                "configured": bool(adapter and adapter.configured()),
                "is_hrms": config.is_hrms,
            }
        )
    return render(
        request,
        "integrations/connectors.html",
        {
            "rows": rows,
            "runs": ConnectorRun.objects.filter(
                config__company=request.company
            ).select_related("config")[:20],
        },
    )


def _config_for(request, kind):
    if kind not in dict(ConnectorConfig.KIND_CHOICES):
        from django.http import Http404

        raise Http404("Unknown connector")
    config, _ = ConnectorConfig.objects.get_or_create(
        company=request.company, kind=kind, defaults={"settings": {}, "active": False}
    )
    return config


@owner_only
def connector_edit(request, kind):
    config = _config_for(request, kind)
    form = ConnectorForm(request.POST or None, config=config)
    if request.method == "POST" and form.is_valid():
        form.apply()
        messages.success(request, f"{form.adapter_cls.label} settings saved.")
        return redirect(reverse("integrations:connector_edit", args=[kind]))
    adapter = config.adapter()
    return render(
        request,
        "integrations/connector_form.html",
        {
            "form": form,
            "config": config,
            "adapter": adapter,
            "configured": bool(adapter and adapter.configured()),
            "runs": config.runs.all()[:10] if config.pk else [],
        },
    )


@owner_only
@require_POST
def connector_test(request, kind):
    config = _config_for(request, kind)
    result = probe_connection(config)
    if result.ok:
        messages.success(request, f"Connection ok: {result.detail}")
    elif result.status == "SKIPPED":
        messages.warning(request, result.detail)
    else:
        messages.error(request, f"Connection failed: {result.detail}")
    return redirect(reverse("integrations:connector_edit", args=[kind]))


@owner_only
def api_keys(request):
    """The company's API key, shown masked; the plaintext appears once."""
    token = tokens.get_token(request.company)
    return render(
        request,
        "integrations/api_keys.html",
        {
            "token": token,
            "masked": tokens.masked(token.key) if token else "",
            "service_email": tokens.service_email(request.company),
            "issued_key": request.session.pop("integrations_new_key", None),
        },
    )


@owner_only
@require_POST
def api_key_issue(request):
    token = tokens.issue_token(request.company)
    # Shown exactly once, on the next render; never stored anywhere else.
    request.session["integrations_new_key"] = token.key
    messages.success(request, "API key issued. Copy it now — it is shown only once.")
    return redirect(reverse("integrations:api_keys"))


@owner_only
@require_POST
def api_key_revoke(request):
    if tokens.revoke_token(request.company):
        messages.success(request, "API key revoked.")
    else:
        messages.info(request, "There was no API key to revoke.")
    return redirect(reverse("integrations:api_keys"))
