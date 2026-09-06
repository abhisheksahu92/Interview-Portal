"""The analytics snippet must never load for candidates or anonymous visitors."""

import pytest
from django.test import RequestFactory

from core.context_processors import analytics
from core.models import User


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="recruiter@acme.test", password="pw12345678")


@pytest.mark.django_db
def test_key_is_exposed_to_a_signed_in_user(rf, settings, user):
    settings.POSTHOG_KEY = "phc_test"
    request = rf.get("/")
    request.user = user

    assert analytics(request)["posthog_key"] == "phc_test"


@pytest.mark.django_db
def test_key_is_withheld_from_anonymous_visitors(rf, settings):
    """Careers pages, assessments and offer signing are all anonymous."""
    from django.contrib.auth.models import AnonymousUser

    settings.POSTHOG_KEY = "phc_test"
    request = rf.get("/")
    request.user = AnonymousUser()

    assert analytics(request)["posthog_key"] == ""


@pytest.mark.django_db
def test_nothing_is_exposed_when_unconfigured(rf, settings, user):
    settings.POSTHOG_KEY = ""
    request = rf.get("/")
    request.user = user

    assert analytics(request)["posthog_key"] == ""


@pytest.mark.django_db
def test_snippet_is_absent_from_a_rendered_anonymous_page(client, settings):
    settings.POSTHOG_KEY = "phc_test"

    body = client.get("/accounts/login/").content

    assert b"posthog.init" not in body
