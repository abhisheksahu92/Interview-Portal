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
def test_pro_plan_grants_every_feature(company):
    pro = Plan.objects.get(code=Plan.PRO)
    assert pro.features == dict.fromkeys(FEATURES, True)
    _set_plan(company, pro)
    assert all(has_feature(company, name) for name in FEATURES)


@pytest.mark.django_db
def test_canceled_subscription_loses_paid_features(company):
    pro = Plan.objects.get(code=Plan.PRO)
    _set_plan(company, pro, status=Subscription.CANCELED)
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

    _set_plan(company, Plan.objects.get(code=Plan.PRO))
    assert view(request) == "ok"
