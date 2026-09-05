"""Adapter selection and the stub vendor's refusal to pretend."""

import pytest

from bgv import gateway

pytestmark = pytest.mark.django_db


def test_blank_key_selects_the_mock_provider(settings):
    settings.BGV_API_KEY = ""
    settings.BGV_PROVIDER = "authbridge"
    assert isinstance(gateway.get_provider(), gateway.MockProvider)
    assert gateway.is_live() is False


def test_a_key_selects_the_real_adapter(settings):
    settings.BGV_API_KEY = "vendor-secret"
    settings.BGV_PROVIDER = "authbridge"
    assert isinstance(gateway.get_provider(), gateway.AuthBridgeLikeProvider)
    assert gateway.is_live() is True


def test_the_stub_adapter_refuses_to_pretend(settings):
    settings.BGV_API_KEY = "vendor-secret"
    settings.BGV_API_BASE = "https://vendor.example"
    provider = gateway.AuthBridgeLikeProvider()
    assert provider.configured() is True
    with pytest.raises(gateway.NotConfigured):
        provider.submit(None)
    with pytest.raises(gateway.NotConfigured):
        provider.fetch_status(None)


def test_signature_verification_is_key_bound(settings):
    settings.BGV_API_KEY = "vendor-secret"
    settings.BGV_PROVIDER = "authbridge"
    body = b'{"provider_ref": "X"}'
    assert gateway.verify_webhook(body, gateway.sign_payload(body)) is True
    assert gateway.verify_webhook(body + b" ", gateway.sign_payload(body)) is False
    assert gateway.verify_webhook(body, "") is False
