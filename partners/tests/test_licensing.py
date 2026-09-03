from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from partners.licensing import issue_license, make_key, verify_license
from partners.models import License


def test_issue_license_command_persists_and_verifies(company, capsys):
    call_command("issue_license", "--company", company.slug, "--seats", "12", "--days", "30")
    licence = License.objects.get(company=company)
    assert licence.seats == 12
    result = verify_license(licence.key)
    assert result["valid"] and result["company_id"] == company.pk and result["seats"] == 12


def test_issue_license_command_rejects_unknown_company(db):
    with pytest.raises(CommandError):
        call_command("issue_license", "--company", "nope")


def test_verify_license_command_ok_and_error(company):
    licence = issue_license(company, seats=3, days=10)
    call_command("verify_license", licence.key)
    with pytest.raises(CommandError):
        call_command("verify_license", "IPL.aaa.bbb")


def test_tampered_key_fails_signature(company):
    licence = issue_license(company, seats=3, days=10)
    prefix, body, sig = licence.key.split(".")
    tampered = f"{prefix}.{body}.{sig[:-2]}xy"
    assert verify_license(tampered)["reason"] == "bad-signature"


def test_expired_key_is_invalid(company):
    key = make_key(company.pk, 5, timezone.now() - timedelta(days=1))
    result = verify_license(key)
    assert result["valid"] is False and result["reason"] == "expired"


@pytest.mark.parametrize("key", ["", None, "garbage", "IPL.only-two", "XXX.a.b"])
def test_malformed_keys_are_invalid(key, db):
    assert verify_license(key)["valid"] is False


def test_key_does_not_verify_under_a_different_secret(company):
    licence = issue_license(company, seats=3, days=10)
    with override_settings(SECRET_KEY="a-completely-different-secret"):
        assert verify_license(licence.key)["valid"] is False
