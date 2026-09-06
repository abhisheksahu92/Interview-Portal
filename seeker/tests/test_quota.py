"""Ten free sends a month, counted, and the wall that shows when they run out."""

import pytest
from django.urls import reverse

from seeker import services
from seeker.models import MAX_BULK_SENDS, SavedItem
from seeker.services import QuotaExceeded

pytestmark = pytest.mark.django_db


def test_free_plan_starts_with_ten(seeker):
    assert seeker.sends_left() == 10
    services.check_quota(seeker, 10)


def test_quota_refuses_one_over(seeker):
    services.record_send(seeker, 10)
    assert seeker.sends_left() == 0
    with pytest.raises(QuotaExceeded):
        services.check_quota(seeker, 1)


def test_counter_rolls_over_next_month(seeker):
    services.record_send(seeker, 10)
    seeker.month_key = "2001-01"
    seeker.save(update_fields=["month_key"])
    assert seeker.sends_left() == 10


def test_pro_has_no_cap(seeker):
    seeker.is_pro = True
    seeker.save(update_fields=["is_pro"])
    services.record_send(seeker, 500)
    assert seeker.sends_left() is None
    services.check_quota(seeker, MAX_BULK_SENDS)


def test_bulk_is_capped_even_for_pro(seeker):
    seeker.is_pro = True
    with pytest.raises(QuotaExceeded):
        services.check_quota(seeker, MAX_BULK_SENDS + 1)


def test_over_quota_draft_returns_402_with_upgrade_cta(client, seeker_user, seeker, make_lead):
    services.record_send(seeker, 10)
    item = SavedItem.objects.create(seeker=seeker, lead=make_lead())
    client.force_login(seeker_user)
    response = client.post(reverse("seeker:bulk"), {"action": "draft", "item": [item.pk]})
    assert response.status_code == 402
    assert reverse("seeker:upgrade").encode() in response.content
