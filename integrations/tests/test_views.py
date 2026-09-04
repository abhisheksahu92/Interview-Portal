"""The owner-only integrations UI: gating, isolation, and each action."""

import pytest
from django.urls import reverse

from integrations.models import (
    ConnectorConfig,
    ConnectorRun,
    OutboundWebhook,
    WebhookDelivery,
)

pytestmark = pytest.mark.django_db


PAGES = [
    "integrations:index",
    "integrations:webhook_create",
    "integrations:deliveries",
    "integrations:connectors",
    "integrations:api_keys",
]


@pytest.mark.parametrize("name", PAGES)
def test_owner_can_reach_every_page(logged_in, name):
    assert logged_in.get(reverse(name)).status_code == 200


@pytest.mark.parametrize("name", PAGES)
def test_anonymous_visitors_are_redirected_to_login(client, name):
    response = client.get(reverse(name))
    assert response.status_code == 302
    assert "/accounts/login" in response["Location"]


@pytest.mark.parametrize("name", PAGES)
def test_recruiters_are_refused(client, recruiter, name):
    client.force_login(recruiter)
    assert client.get(reverse(name)).status_code == 403


@pytest.mark.parametrize("name", PAGES)
def test_a_plan_without_the_feature_is_refused(client, free_owner, name):
    client.force_login(free_owner)
    assert client.get(reverse(name)).status_code == 403


def test_the_sidebar_links_to_integrations_when_entitled(logged_in):
    html = logged_in.get(reverse("web:dashboard")).content.decode()
    assert reverse("integrations:index") in html


def test_the_sidebar_shows_a_locked_upsell_without_the_feature(client, free_owner):
    client.force_login(free_owner)
    html = client.get(reverse("web:dashboard")).content.decode()
    assert 'data-ip-lock="integrations"' in html
    assert reverse("integrations:index") not in html


# --- webhook CRUD --------------------------------------------------------
def test_creating_a_webhook_assigns_the_company_and_a_secret(logged_in, company, owner):
    response = logged_in.post(
        reverse("integrations:webhook_create"),
        {
            "name": "Ops",
            "url": "https://hooks.example.com/ip",
            "events": ["application.hired"],
            "active": "on",
        },
    )

    hook = OutboundWebhook.objects.get()
    assert response.status_code == 302
    assert hook.company == company
    assert hook.created_by == owner
    assert hook.events == ["application.hired"]
    assert hook.secret


def test_creating_a_webhook_with_no_events_subscribes_to_all(logged_in):
    logged_in.post(
        reverse("integrations:webhook_create"),
        {"name": "Everything", "url": "https://x.test/h", "active": "on"},
    )
    hook = OutboundWebhook.objects.get()
    assert hook.events == []
    assert hook.subscribes_to("offer.accepted")


def test_a_non_http_url_is_rejected(logged_in):
    response = logged_in.post(
        reverse("integrations:webhook_create"),
        {"name": "Bad", "url": "ftp://x.test/h", "active": "on"},
    )
    assert response.status_code == 200
    assert OutboundWebhook.objects.count() == 0


def test_editing_a_webhook_updates_its_events(logged_in, webhook):
    logged_in.post(
        reverse("integrations:webhook_edit", args=[webhook.pk]),
        {
            "name": "Renamed",
            "url": webhook.url,
            "events": ["offer.accepted"],
            "active": "on",
        },
    )
    webhook.refresh_from_db()
    assert webhook.name == "Renamed"
    assert webhook.events == ["offer.accepted"]


def test_deleting_a_webhook(logged_in, webhook):
    logged_in.post(reverse("integrations:webhook_delete", args=[webhook.pk]))
    assert OutboundWebhook.objects.count() == 0


def test_rotating_the_secret_changes_it(logged_in, webhook):
    before = webhook.secret
    logged_in.post(reverse("integrations:webhook_rotate", args=[webhook.pk]))
    webhook.refresh_from_db()
    assert webhook.secret != before


def test_another_companys_webhook_is_a_404(client, other_owner, webhook):
    client.force_login(other_owner)
    assert client.get(reverse("integrations:webhook_edit", args=[webhook.pk])).status_code == 404
    assert (
        client.post(reverse("integrations:webhook_delete", args=[webhook.pk])).status_code
        == 404
    )


def test_send_test_event_delivers_and_reports_success(logged_in, webhook, responder):
    response = logged_in.post(
        reverse("integrations:webhook_test", args=[webhook.pk]), follow=True
    )

    delivery = WebhookDelivery.objects.get()
    assert delivery.status == WebhookDelivery.SENT
    assert delivery.payload["data"]["test"] is True
    assert "Test event accepted" in response.content.decode()


def test_send_test_event_reports_failure(logged_in, webhook, responder):
    responder.status_code = 500
    response = logged_in.post(
        reverse("integrations:webhook_test", args=[webhook.pk]), follow=True
    )
    assert "Test event failed" in response.content.decode()


def test_redelivering_retries_a_failed_delivery(logged_in, webhook, responder):
    delivery = WebhookDelivery.objects.create(
        webhook=webhook,
        event="application.hired",
        payload={"event": "application.hired"},
        status=WebhookDelivery.FAILED,
        attempts=5,
    )

    logged_in.post(reverse("integrations:delivery_redeliver", args=[delivery.pk]))

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.SENT
    assert delivery.attempts == 1


def test_redelivering_another_companys_delivery_is_a_404(client, other_owner, webhook):
    delivery = WebhookDelivery.objects.create(
        webhook=webhook, event="application.hired", payload={}
    )
    client.force_login(other_owner)
    assert (
        client.post(
            reverse("integrations:delivery_redeliver", args=[delivery.pk])
        ).status_code
        == 404
    )


def test_the_delivery_log_filters_by_status(logged_in, webhook):
    WebhookDelivery.objects.create(
        webhook=webhook, event="application.hired", payload={}, status=WebhookDelivery.SENT
    )
    WebhookDelivery.objects.create(
        webhook=webhook, event="offer.accepted", payload={}, status=WebhookDelivery.FAILED
    )

    html = logged_in.get(reverse("integrations:deliveries"), {"status": "FAILED"}).content.decode()

    assert "offer.accepted" in html
    assert "application.hired" not in html


def test_the_delivery_log_only_shows_our_own_deliveries(client, other_owner, webhook):
    WebhookDelivery.objects.create(webhook=webhook, event="application.hired", payload={})
    client.force_login(other_owner)
    html = client.get(reverse("integrations:deliveries")).content.decode()
    assert "No deliveries yet" in html


# --- connectors ----------------------------------------------------------
def test_the_connectors_page_lists_every_kind(logged_in):
    html = logged_in.get(reverse("integrations:connectors")).content.decode()
    for _kind, label in ConnectorConfig.KIND_CHOICES:
        assert label in html


def test_saving_connector_settings_stores_them_encrypted(logged_in, company):
    logged_in.post(
        reverse("integrations:connector_edit", args=[ConnectorConfig.KEKA]),
        {"api_key": "sekret", "subdomain": "acme", "department": "", "active": "on"},
    )

    config = ConnectorConfig.objects.get(company=company, kind=ConnectorConfig.KEKA)
    assert config.settings == {"api_key": "sekret", "subdomain": "acme"}
    assert config.active is True


def test_the_settings_form_masks_the_stored_secret(logged_in, company):
    ConnectorConfig.objects.create(
        company=company,
        kind=ConnectorConfig.KEKA,
        settings={"api_key": "abcd1234wxyz", "subdomain": "acme"},
        active=True,
    )
    html = logged_in.get(
        reverse("integrations:connector_edit", args=[ConnectorConfig.KEKA])
    ).content.decode()

    assert "abcd1234wxyz" not in html
    assert "wxyz" in html  # the masked hint
    assert "acme" in html  # non-secret settings stay editable


def test_submitting_a_blank_secret_keeps_the_stored_one(logged_in, company):
    ConnectorConfig.objects.create(
        company=company,
        kind=ConnectorConfig.KEKA,
        settings={"api_key": "keepme", "subdomain": "acme"},
        active=True,
    )
    logged_in.post(
        reverse("integrations:connector_edit", args=[ConnectorConfig.KEKA]),
        {"api_key": "", "subdomain": "acme2", "department": "", "active": "on"},
    )
    config = ConnectorConfig.objects.get(company=company, kind=ConnectorConfig.KEKA)
    assert config.settings == {"api_key": "keepme", "subdomain": "acme2"}


def test_testing_an_unconfigured_connector_says_so(logged_in):
    response = logged_in.post(
        reverse("integrations:connector_test", args=[ConnectorConfig.KEKA]), follow=True
    )
    assert "not configured" in response.content.decode()
    assert ConnectorRun.objects.get().status == ConnectorRun.SKIPPED


def test_testing_a_configured_connector_reports_ok(logged_in, company, monkeypatch):
    ConnectorConfig.objects.create(
        company=company,
        kind=ConnectorConfig.KEKA,
        settings={"api_key": "k", "subdomain": "acme"},
        active=True,
    )
    monkeypatch.setattr(
        "integrations.connectors.keka.KekaConnector.request",
        lambda self, method, path, json=None: type("R", (), {"status_code": 200})(),
    )
    response = logged_in.post(
        reverse("integrations:connector_test", args=[ConnectorConfig.KEKA]), follow=True
    )
    assert "Connection ok" in response.content.decode()


def test_an_unknown_connector_kind_is_a_404(logged_in):
    assert logged_in.get(reverse("integrations:connector_edit", args=["NOPE"])).status_code == 404


# --- API keys ------------------------------------------------------------
def test_issuing_an_api_key_shows_it_once(logged_in, company):
    from integrations import tokens

    response = logged_in.post(reverse("integrations:api_key_issue"), follow=True)
    key = tokens.get_token(company).key

    assert key in response.content.decode()
    # a second visit shows only the mask
    html = logged_in.get(reverse("integrations:api_keys")).content.decode()
    assert key not in html
    assert tokens.masked(key) in html


def test_revoking_an_api_key(logged_in, company):
    from integrations import tokens

    tokens.issue_token(company)
    logged_in.post(reverse("integrations:api_key_revoke"))
    assert tokens.get_token(company) is None


def test_revoking_without_a_key_is_harmless(logged_in):
    assert logged_in.post(reverse("integrations:api_key_revoke")).status_code == 302
