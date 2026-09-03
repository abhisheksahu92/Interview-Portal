"""The expire_offers management command."""

import pytest
from django.core.management import call_command
from django.utils import timezone

from offers.models import Offer, OfferEvent


@pytest.fixture
def offers(draft_offer, application, recruiter):
    past = timezone.now() - timezone.timedelta(days=1)
    future = timezone.now() + timezone.timedelta(days=3)
    stale = Offer.objects.create(
        application=application, salary=1, expires_at=past, status=Offer.SENT,
        created_by=recruiter,
    )
    viewed = Offer.objects.create(
        application=application, salary=2, expires_at=past, status=Offer.VIEWED,
        created_by=recruiter,
    )
    accepted = Offer.objects.create(
        application=application, salary=3, expires_at=past, status=Offer.ACCEPTED,
    )
    fresh = Offer.objects.create(
        application=application, salary=4, expires_at=future, status=Offer.SENT,
    )
    return stale, viewed, accepted, fresh


@pytest.mark.django_db
def test_expire_offers_only_touches_open_past_expiry_offers(offers, capsys):
    stale, viewed, accepted, fresh = offers
    call_command("expire_offers")
    out = capsys.readouterr().out
    assert "Expired 2 offer(s)." in out

    for offer in (stale, viewed):
        offer.refresh_from_db()
        assert offer.status == Offer.EXPIRED
        assert offer.events.filter(kind=OfferEvent.EXPIRED).exists()

    accepted.refresh_from_db()
    fresh.refresh_from_db()
    assert accepted.status == Offer.ACCEPTED
    assert fresh.status == Offer.SENT


@pytest.mark.django_db
def test_expire_offers_dry_run_changes_nothing(offers, capsys):
    stale = offers[0]
    call_command("expire_offers", "--dry-run")
    assert "2 offer(s) would be expired." in capsys.readouterr().out
    stale.refresh_from_db()
    assert stale.status == Offer.SENT


@pytest.mark.django_db
def test_expire_offers_is_idempotent(offers):
    call_command("expire_offers")
    call_command("expire_offers")
    assert Offer.objects.filter(status=Offer.EXPIRED).count() == 2
