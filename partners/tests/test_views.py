import pytest
from django.urls import reverse

from core.models import Membership, User
from partners.models import Reseller, WhiteLabel


def test_settings_requires_owner(client, company):
    user = User.objects.create_user(email="rec@partners.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.RECRUITER)
    client.force_login(user)
    assert client.get(reverse("partners:settings")).status_code == 403


def test_branding_tab_is_gated_by_the_white_label_feature(client, owner, expired_trial):
    client.force_login(owner)
    response = client.get(reverse("partners:settings"))
    assert response.context["can_white_label"] is False
    assert b"not included in your plan" in response.content


def test_owner_on_pro_plan_can_save_branding(client, owner, pro):
    client.force_login(owner)
    response = client.post(
        reverse("partners:settings"),
        {"form": "branding", "brand_name": "Acme Hire", "primary_color": "#00aa88"},
        follow=True,
    )
    assert response.status_code == 200
    assert WhiteLabel.objects.get(company=pro).brand_name == "Acme Hire"


def test_partners_tab_only_lists_resellers_for_staff(client, owner, company):
    Reseller.objects.create(name="Partner One", code="p1")
    client.force_login(owner)
    response = client.get(reverse("partners:settings"), {"tab": "partners"})
    assert list(response.context["resellers"]) == []

    owner.is_staff = True
    owner.save()
    response = client.get(reverse("partners:settings"), {"tab": "partners"})
    assert len(response.context["resellers"]) == 1


def test_reseller_dashboard_requires_the_token(client, db):
    reseller = Reseller.objects.create(name="Partner One", code="p1")
    url = reverse("partners:reseller_dashboard", args=[reseller.code])
    assert client.get(url).status_code == 403
    assert client.get(url, {"t": "wrong"}).status_code == 403
    assert client.get(url, {"t": reseller.token}).status_code == 200


def test_reseller_dashboard_shows_referrals_and_commissions(client, db, company):
    from partners.models import Referral
    from partners.services import record_commission

    reseller = Reseller.objects.create(name="Partner One", code="p1", commission_pct=10)
    Referral.objects.create(reseller=reseller, company=company)
    record_commission(company, 10000, "IP/2026-27/0007")
    response = client.get(
        reverse("partners:reseller_dashboard", args=[reseller.code]), {"t": reseller.token}
    )
    assert response.context["totals"]["earned"] == pytest.approx(1000, abs=0.01)
    assert b"IP/2026-27/0007" in response.content


def test_verify_license_view_reports_invalid_key(client, owner):
    client.force_login(owner)
    response = client.post(reverse("partners:verify_license"), {"key": "IPL2.a.b"}, follow=True)
    assert b"not valid" in response.content
