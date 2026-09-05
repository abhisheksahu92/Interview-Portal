"""The deploy gate must actually block a misconfigured production boot."""

import pytest
from django.core.management import CommandError, call_command

PROD = dict(
    DEBUG=False,
    SECRET_KEY="x" * 50,
    ALLOWED_HOSTS=["app.example.com"],
    SITE_URL="https://app.example.com",
    AWS_STORAGE_BUCKET_NAME="media",
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    RAZORPAY_KEY_ID="k",
    RAZORPAY_KEY_SECRET="s",
    RAZORPAY_WEBHOOK_SECRET="w",
    COMPANY_GSTIN="27AAAAA0000A1Z5",
    COMPANY_STATE_CODE="27",
    ANTHROPIC_API_KEY="a",
    INTEGRATIONS_ENCRYPTION_KEY="e",
    # The test suite itself runs on SQLite, which is a deploy blocker; a
    # realistic production check needs a real database engine configured.
    DATABASES={"default": {"ENGINE": "django.db.backends.postgresql"}},
)


def test_complete_configuration_passes(settings, capsys):
    for key, value in PROD.items():
        setattr(settings, key, value)
    call_command("check_deploy")
    assert "looks complete" in capsys.readouterr().out


@pytest.mark.parametrize(
    "key,value",
    [
        ("DEBUG", True),
        ("SECRET_KEY", ""),
        ("AWS_STORAGE_BUCKET_NAME", ""),
        ("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"),
        ("EMAIL_BACKEND", "smtp"),
    ],
)
def test_blocking_problems_fail_the_deploy(settings, key, value):
    for k, v in PROD.items():
        setattr(settings, k, v)
    setattr(settings, key, value)
    with pytest.raises(CommandError):
        call_command("check_deploy")


def test_missing_payment_keys_warn_but_do_not_block(settings, capsys):
    """A blank gateway key disables billing silently, so it must be reported."""
    for k, v in PROD.items():
        setattr(settings, k, v)
    settings.RAZORPAY_KEY_SECRET = ""
    call_command("check_deploy")
    assert "RAZORPAY_KEY_SECRET" in capsys.readouterr().out


def test_warn_only_never_raises(settings):
    for k, v in PROD.items():
        setattr(settings, k, v)
    settings.DEBUG = True
    call_command("check_deploy", warn_only=True)
