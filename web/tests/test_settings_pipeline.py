"""Stage and skill management: edit, reorder, guarded delete, sticky forms."""

import pytest
from django.urls import reverse

from jobs.models import PipelineStage, Skill


@pytest.mark.django_db
def test_stage_edit_renames_and_changes_kind(client, owner, company, make_job):
    job = make_job(company)
    stage = job.stages.get(order=1)
    client.force_login(owner)
    response = client.post(
        reverse("web:stage_edit", args=[stage.pk]),
        {
            "name": "Phone screen",
            "order": stage.order,
            "kind": PipelineStage.INTERVIEW,
            "requires_assessment": "on",
        },
    )
    assert response.status_code == 302
    stage.refresh_from_db()
    assert stage.name == "Phone screen"
    assert stage.kind == PipelineStage.INTERVIEW
    assert stage.requires_assessment is True


@pytest.mark.django_db
def test_stage_edit_form_keeps_input_on_duplicate_order(client, owner, company, make_job):
    job = make_job(company)
    stage = job.stages.get(order=1)
    client.force_login(owner)
    response = client.post(
        reverse("web:stage_edit", args=[stage.pk]),
        {"name": "Clash", "order": 2, "kind": PipelineStage.SCREENING},
    )
    assert response.status_code == 200
    form = response.context["edit_form"]
    assert "order" in form.errors
    assert form.data["name"] == "Clash"
    assert b"Clash" in response.content
    stage.refresh_from_db()
    assert stage.order == 1


@pytest.mark.django_db
def test_stage_add_form_keeps_input_on_duplicate_order(client, owner, company, make_job):
    job = make_job(company)
    client.force_login(owner)
    response = client.post(
        reverse("web:settings_stages", args=[job.pk]),
        {"name": "Extra", "order": 1, "kind": PipelineStage.INTERVIEW},
    )
    assert response.status_code == 200  # no redirect: input is preserved
    assert "order" in response.context["form"].errors
    assert b"Extra" in response.content
    assert not job.stages.filter(name="Extra").exists()


@pytest.mark.django_db
def test_stage_add_defaults_to_the_next_order(client, owner, company, make_job):
    job = make_job(company)
    client.force_login(owner)
    response = client.get(reverse("web:settings_stages", args=[job.pk]))
    expected = job.stages.count() + 1
    assert response.context["form"].fields["order"].initial == expected


@pytest.mark.django_db
def test_stage_move_up_and_down_swaps_order(client, owner, company, make_job):
    job = make_job(company)
    first, second = job.stages.get(order=1), job.stages.get(order=2)
    client.force_login(owner)

    client.post(reverse("web:stage_move", args=[second.pk, "up"]))
    first.refresh_from_db()
    second.refresh_from_db()
    assert (second.order, first.order) == (1, 2)

    client.post(reverse("web:stage_move", args=[second.pk, "down"]))
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.order, second.order) == (1, 2)


@pytest.mark.django_db
def test_stage_move_at_the_edge_is_a_no_op(client, owner, company, make_job):
    job = make_job(company)
    first = job.stages.get(order=1)
    client.force_login(owner)
    client.post(reverse("web:stage_move", args=[first.pk, "up"]))
    first.refresh_from_db()
    assert first.order == 1


@pytest.mark.django_db
def test_stage_delete_refused_while_applications_sit_on_it(
    client, owner, company, make_job, make_application
):
    job = make_job(company)
    stage = job.stages.get(order=1)
    make_application(job, "onstage@example.test", stage=stage)
    client.force_login(owner)
    response = client.post(reverse("web:stage_delete", args=[stage.pk]), follow=True)
    assert job.stages.filter(pk=stage.pk).exists()
    body = response.content.decode()
    assert "cannot be deleted" in body
    assert "1 application(s) sit on it" in body


@pytest.mark.django_db
def test_stage_delete_refused_while_an_assessment_points_at_it(
    client, owner, company, make_job
):
    from assessments.models import Assessment

    job = make_job(company)
    stage = job.stages.get(order=2)
    Assessment.objects.create(job=job, stage=stage, title="Screen")
    client.force_login(owner)
    response = client.post(reverse("web:stage_delete", args=[stage.pk]), follow=True)
    assert job.stages.filter(pk=stage.pk).exists()
    assert "assessment(s) use it" in response.content.decode()


@pytest.mark.django_db
def test_stage_delete_can_move_applications_to_the_previous_stage(
    client, owner, company, make_job, make_application
):
    job = make_job(company)
    previous, stage = job.stages.get(order=1), job.stages.get(order=2)
    application = make_application(job, "moved@example.test", stage=stage)
    client.force_login(owner)
    response = client.post(
        reverse("web:stage_delete", args=[stage.pk]),
        {"move_applications": "1"},
        follow=True,
    )
    assert not job.stages.filter(pk=stage.pk).exists()
    application.refresh_from_db()
    assert application.current_stage_id == previous.pk
    assert "moved to" in response.content.decode()


@pytest.mark.django_db
def test_empty_stage_deletes_cleanly(client, owner, company, make_job):
    job = make_job(company)
    stage = job.stages.get(order=3)
    client.force_login(owner)
    client.post(reverse("web:stage_delete", args=[stage.pk]))
    assert not job.stages.filter(pk=stage.pk).exists()


@pytest.mark.django_db
def test_stage_delete_button_asks_for_confirmation(client, owner, company, make_job):
    job = make_job(company)
    client.force_login(owner)
    body = client.get(reverse("web:settings_stages", args=[job.pk])).content.decode()
    assert "hx-confirm=" in body
    assert "confirm(" in body
    assert reverse("web:stage_move", args=[job.stages.get(order=1).pk, "down"]) in body


@pytest.mark.django_db
def test_stages_are_scoped_to_the_active_company(
    client, owner, other_company, make_job
):
    job = make_job(other_company)
    stage = job.stages.first()
    client.force_login(owner)
    assert client.get(reverse("web:stage_edit", args=[stage.pk])).status_code == 404
    assert client.post(reverse("web:stage_delete", args=[stage.pk])).status_code == 404
    assert (
        client.post(reverse("web:stage_move", args=[stage.pk, "up"])).status_code == 404
    )


@pytest.mark.django_db
def test_skill_edit_renames(client, owner, company):
    skill = Skill.objects.create(company=company, name="Djngo")
    client.force_login(owner)
    response = client.post(reverse("web:skill_edit", args=[skill.pk]), {"name": "Django"})
    assert response.status_code == 302
    skill.refresh_from_db()
    assert skill.name == "Django"


@pytest.mark.django_db
def test_skill_form_keeps_input_on_duplicate_name(client, owner, company):
    Skill.objects.create(company=company, name="Django")
    client.force_login(owner)
    response = client.post(reverse("web:settings_skills"), {"name": "django"})
    assert response.status_code == 200
    form = response.context["form"]
    assert "already exists" in str(form.errors["name"])
    assert form.data["name"] == "django"
    assert Skill.objects.filter(company=company).count() == 1


@pytest.mark.django_db
def test_skill_edit_keeps_input_on_duplicate_name(client, owner, company):
    Skill.objects.create(company=company, name="Django")
    other = Skill.objects.create(company=company, name="Flask")
    client.force_login(owner)
    response = client.post(reverse("web:skill_edit", args=[other.pk]), {"name": "Django"})
    assert response.status_code == 200
    assert "name" in response.context["edit_form"].errors
    other.refresh_from_db()
    assert other.name == "Flask"


@pytest.mark.django_db
def test_skill_rename_to_its_own_name_is_allowed(client, owner, company):
    skill = Skill.objects.create(company=company, name="Django")
    client.force_login(owner)
    response = client.post(reverse("web:skill_edit", args=[skill.pk]), {"name": "Django"})
    assert response.status_code == 302


@pytest.mark.django_db
def test_skill_delete_button_asks_for_confirmation(client, owner, company):
    Skill.objects.create(company=company, name="Django")
    client.force_login(owner)
    body = client.get(reverse("web:settings_skills")).content.decode()
    assert "hx-confirm=" in body
    assert "confirm(" in body


@pytest.mark.django_db
def test_skills_are_scoped_on_edit(client, owner, other_company):
    skill = Skill.objects.create(company=other_company, name="Rust")
    client.force_login(owner)
    assert client.get(reverse("web:skill_edit", args=[skill.pk])).status_code == 404
