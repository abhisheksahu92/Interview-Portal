import base64
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from partners.licensing import (
    LICENSE_PUBLIC_KEY,
    LicenseSigningUnavailable,
    generate_keypair,
    issue_license,
    make_key,
    verify_license,
)
from partners.models import License

#: A throwaway signing keypair used for tests, so the vendor's real private key
#: never has to exist in the repo or the test environment.
TEST_PRIVATE_KEY, TEST_PUBLIC_KEY = generate_keypair()

signing = override_settings(LICENSE_SIGNING_KEY=TEST_PRIVATE_KEY)


@pytest.fixture(autouse=True)
def _test_signing_key():
    """Every test in this module issues keys with the throwaway keypair."""
    with signing:
        yield


def test_issue_license_command_persists_and_verifies(company, capsys):
    call_command("issue_license", "--company", company.slug, "--seats", "12", "--days", "30")
    licence = License.objects.get(company=company)
    assert licence.seats == 12
    assert licence.key.startswith("IPL2.")
    result = verify_license(licence.key)
    assert result["valid"] and result["company_id"] == company.pk and result["seats"] == 12


def test_issue_license_command_rejects_unknown_company(db):
    with pytest.raises(CommandError):
        call_command("issue_license", "--company", "nope")


def test_verify_license_command_ok_and_error(company):
    licence = issue_license(company, seats=3, days=10)
    call_command("verify_license", licence.key)
    with pytest.raises(CommandError):
        call_command("verify_license", "IPL2.aaa.bbb")


def test_tampered_key_fails_signature(company):
    licence = issue_license(company, seats=3, days=10)
    prefix, body, sig = licence.key.split(".")
    tampered = f"{prefix}.{body}.{sig[:-2]}xy"
    assert verify_license(tampered)["reason"] == "bad-signature"


def test_tampered_payload_fails_signature(company):
    """Bumping the seat count in the payload invalidates the signature."""
    licence = issue_license(company, seats=3, days=10)
    prefix, _body, sig = licence.key.split(".")
    forged_payload = f"{company.pk}|9999|{int((timezone.now() + timedelta(days=10)).timestamp())}|SELF_HOSTED"
    forged_body = (
        base64.urlsafe_b64encode(forged_payload.encode()).decode().rstrip("=")
    )
    assert verify_license(f"{prefix}.{forged_body}.{sig}")["reason"] == "bad-signature"


def test_expired_key_is_invalid(company):
    key = make_key(company.pk, 5, timezone.now() - timedelta(days=1))
    result = verify_license(key)
    assert result["valid"] is False and result["reason"] == "expired"


@pytest.mark.parametrize("key", ["", None, "garbage", "IPL2.only-two", "XXX.a.b"])
def test_malformed_keys_are_invalid(key, db):
    assert verify_license(key)["valid"] is False


def test_old_hmac_prefix_is_rejected(db):
    assert verify_license("IPL.abc.def")["valid"] is False


def test_key_verifies_under_a_different_secret_key(company):
    """SECRET_KEY has nothing to do with licence keys any more, so a key still
    verifies across installs with different Django secrets."""
    licence = issue_license(company, seats=3, days=10)
    with override_settings(SECRET_KEY="a-completely-different-secret"):
        assert verify_license(licence.key)["valid"] is True


def test_key_from_another_signing_key_is_rejected(company):
    """A self-hosted customer cannot forge keys with a keypair of their own."""
    other_private, _other_public = generate_keypair()
    with override_settings(LICENSE_SIGNING_KEY=other_private):
        forged = make_key(company.pk, 500, timezone.now() + timedelta(days=3650))
    # Verify with only the embedded vendor public key available.
    with override_settings(LICENSE_SIGNING_KEY=""):
        assert verify_license(forged)["reason"] == "bad-signature"


def test_verification_works_offline_with_the_embedded_public_key(company):
    """No private key present (a customer install) — verification still runs."""
    licence = issue_license(company, seats=3, days=10)
    with override_settings(LICENSE_SIGNING_KEY=""):
        # Signed by the test keypair, so the embedded key rejects it...
        assert verify_license(licence.key)["reason"] == "bad-signature"
        # ...but the embedded public key itself is well-formed and usable.
        assert len(base64.b64decode(LICENSE_PUBLIC_KEY)) == 32


def test_signing_without_a_private_key_raises(company):
    with override_settings(LICENSE_SIGNING_KEY=""):
        with pytest.raises(LicenseSigningUnavailable):
            make_key(company.pk, 5, timezone.now() + timedelta(days=1))


def test_signing_with_a_malformed_private_key_raises(company):
    with override_settings(LICENSE_SIGNING_KEY="not-base64-and-not-32-bytes"):
        with pytest.raises(LicenseSigningUnavailable):
            make_key(company.pk, 5, timezone.now() + timedelta(days=1))


def test_generate_license_keypair_command(db, capsys):
    call_command("generate_license_keypair")
    out = capsys.readouterr().out
    assert "LICENSE_PUBLIC_KEY" in out and "LICENSE_SIGNING_KEY=" in out


def test_generate_license_keypair_command_can_withhold_private_key(db, capsys):
    public = call_command("generate_license_keypair", "--quiet-private")
    out = capsys.readouterr().out
    assert "LICENSE_SIGNING_KEY=" not in out
    assert len(base64.b64decode(public)) == 32
