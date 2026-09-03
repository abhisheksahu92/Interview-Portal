import pytest

from billing.entitlements import (
    FEATURES,
    FeatureNotAvailable,
    has_feature,
    require_feature,
)
from billing.models import Plan, Subscription


def _set_plan(company, plan, status=Subscription.ACTIVE):
    """Put ``company`` on ``plan`` whether or not it already has a subscription."""
    Subscription.objects.update_or_create(
        company=company, defaults={"plan": plan, "status": status}
    )
    company.refresh_from_db()
    return company


def test_free_plan_has_no_features(company):
    assert has_feature(company, "client_portal") is False


def test_no_company_has_no_features(db):
    assert has_feature(None, "client_portal") is False


@pytest.mark.django_db
def test_agency_plan_grants_every_feature(company):
    agency = Plan.objects.get(code=Plan.AGENCY)
    assert agency.features == dict.fromkeys(FEATURES, True)
    _set_plan(company, agency)
    assert all(has_feature(company, name) for name in FEATURES)


@pytest.mark.django_db
def test_legacy_pro_plan_maps_to_growth_features(company):
    pro = Plan.objects.get(code=Plan.PRO)
    growth = Plan.objects.get(code=Plan.GROWTH)
    assert pro.features == growth.features
    _set_plan(company, pro)
    assert has_feature(company, "scheduling") is True
    assert has_feature(company, "client_portal") is False


@pytest.mark.django_db
def test_canceled_subscription_loses_paid_features(company):
    agency = Plan.objects.get(code=Plan.AGENCY)
    _set_plan(company, agency, status=Subscription.CANCELED)
    assert has_feature(company, "video") is False


@pytest.mark.django_db
def test_require_feature_decorator_blocks_and_allows(company, rf):
    @require_feature("video")
    def view(request):
        return "ok"

    request = rf.get("/")
    request.company = company
    with pytest.raises(FeatureNotAvailable):
        view(request)

    _set_plan(company, Plan.objects.get(code=Plan.AGENCY))
    assert view(request) == "ok"
