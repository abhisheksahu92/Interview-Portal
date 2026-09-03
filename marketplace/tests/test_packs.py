import pytest
from django.urls import reverse

from assessments.models import Question
from jobs.models import Skill
from marketplace.models import PackPurchase, QuestionPack
from marketplace.services import BillingNotConfigured, create_order, install_pack


def test_seed_packs_are_present_with_ten_questions_each(db):
    packs = QuestionPack.objects.filter(published=True)
    assert {p.slug for p in packs} >= {"python-fundamentals", "django-essentials", "core-java"}
    assert all(p.question_count == 10 for p in packs)


def test_seed_packs_command_is_idempotent(db):
    from django.core.management import call_command

    call_command("seed_packs")
    call_command("seed_packs")
    assert QuestionPack.objects.filter(slug="core-java").count() == 1


def test_pack_preview_hides_the_answer_key(free_pack):
    preview = free_pack.preview(3)
    assert len(preview) == 3
    assert all("correct_option" not in row for row in preview)


def test_install_pack_copies_questions_with_marketplace_source(company, free_pack):
    purchase = install_pack(company, free_pack)
    questions = Question.objects.filter(company=company)
    assert questions.count() == 10 == purchase.questions_created
    assert all(q.source == Question.MARKETPLACE for q in questions)


def test_install_pack_creates_or_reuses_the_skill(company, free_pack):
    existing = Skill.objects.create(company=company, name="Python")
    install_pack(company, free_pack)
    assert Skill.objects.filter(company=company, name__iexact="Python").count() == 1
    assert Question.objects.filter(company=company).first().skill_id == existing.pk


def test_install_pack_is_scoped_to_one_company(company, other_company, free_pack):
    install_pack(company, free_pack)
    assert Question.objects.filter(company=other_company).count() == 0


def test_install_pack_is_idempotent(company, free_pack):
    install_pack(company, free_pack)
    install_pack(company, free_pack)
    assert PackPurchase.objects.filter(company=company).count() == 1
    assert Question.objects.filter(company=company).count() == 10


def test_text_questions_keep_no_options(company, paid_pack):
    install_pack(company, paid_pack)
    text_questions = Question.objects.filter(company=company, kind=Question.TEXT)
    assert text_questions.exists()
    assert all(q.options == [] and q.correct_option is None for q in text_questions)


def test_free_pack_installs_from_the_view(client, owner, company, free_pack):
    client.force_login(owner)
    response = client.post(
        reverse("marketplace:pack_install", args=[free_pack.slug]), follow=True
    )
    assert response.status_code == 200
    assert Question.objects.filter(company=company).count() == 10


def test_paid_pack_without_billing_shows_not_configured(client, owner, company, paid_pack):
    client.force_login(owner)
    response = client.post(
        reverse("marketplace:pack_install", args=[paid_pack.slug]), follow=True
    )
    assert b"Billing is not configured" in response.content
    assert not PackPurchase.objects.filter(company=company).exists()


def test_create_order_raises_when_no_gateway_is_configured(company, paid_pack):
    with pytest.raises(BillingNotConfigured):
        create_order(company, paid_pack)


def test_storefront_marks_installed_packs(client, owner, company, free_pack):
    install_pack(company, free_pack)
    client.force_login(owner)
    response = client.get(reverse("marketplace:index"))
    assert free_pack.pk in response.context["installed_ids"]
    assert b"Installed" in response.content


def test_pack_detail_and_purchases_pages_render(client, owner, company, free_pack):
    install_pack(company, free_pack)
    client.force_login(owner)
    assert client.get(reverse("marketplace:pack_detail", args=[free_pack.slug])).status_code == 200
    response = client.get(reverse("marketplace:purchases"))
    assert response.status_code == 200
    assert b"Python Fundamentals" in response.content


def test_unpublished_packs_are_hidden(client, owner, db):
    pack = QuestionPack.objects.create(title="Secret", skill_name="Go", published=False)
    client.force_login(owner)
    assert client.get(reverse("marketplace:pack_detail", args=[pack.slug])).status_code == 404
