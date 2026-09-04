"""Connector credentials must never sit in the database as plaintext."""

import pytest
from django.db import connection
from django.test import override_settings

from integrations.crypto import decrypt_json, derive_key, encrypt_json
from integrations.models import ConnectorConfig


def test_round_trip():
    token = encrypt_json({"api_key": "abc123", "subdomain": "acme"})
    assert decrypt_json(token) == {"api_key": "abc123", "subdomain": "acme"}


def test_ciphertext_does_not_contain_the_secret():
    token = encrypt_json({"api_key": "supersecret"})
    assert "supersecret" not in token


def test_bad_token_degrades_to_default():
    assert decrypt_json("not-a-fernet-token") == {}
    assert decrypt_json("") == {}
    assert decrypt_json(None, default={"x": 1}) == {"x": 1}


def test_key_derivation_is_deterministic_and_secret_specific():
    assert derive_key("aaa") == derive_key("aaa")
    assert derive_key("aaa") != derive_key("bbb")


@override_settings(
    INTEGRATIONS_ENCRYPTION_KEY="dGVzdC1rZXktMzItYnl0ZXMtZXhhY3RseS1va2F5MDA="
)
def test_explicit_key_override_is_used():
    assert decrypt_json(encrypt_json({"a": 1})) == {"a": 1}


@pytest.mark.django_db
def test_model_field_stores_ciphertext(db):
    from core.models import Company

    company = Company.objects.create(name="Crypto Co")
    config = ConnectorConfig.objects.create(
        company=company, kind=ConnectorConfig.KEKA, settings={"api_key": "tops3cret"}
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT settings FROM integrations_connectorconfig WHERE id = %s",
            [config.pk],
        )
        stored = cursor.fetchone()[0]
    assert "tops3cret" not in stored
    assert ConnectorConfig.objects.get(pk=config.pk).settings == {"api_key": "tops3cret"}


@pytest.mark.django_db
def test_unreadable_settings_read_back_empty(db, monkeypatch):
    from core.models import Company

    company = Company.objects.create(name="Rotated Co")
    config = ConnectorConfig.objects.create(
        company=company, kind=ConnectorConfig.KEKA, settings={"api_key": "x"}
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE integrations_connectorconfig SET settings = %s WHERE id = %s",
            ["gAAAAAmangled", config.pk],
        )
    assert ConnectorConfig.objects.get(pk=config.pk).settings == {}
