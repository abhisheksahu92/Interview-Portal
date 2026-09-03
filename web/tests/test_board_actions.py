"""Board actions: review refresh, idempotent advance, unassigned bucket."""

import pytest
from django.urls import reverse

from jobs.models import Application, PipelineStage, StageReview


@pytest.mark.django_db
def test_board_review_post_returns_the_whole_board(
    client, owner, company, make_job, make_application
):
    """A review saved from the kanban swaps #kanban so cards change column."""
    job = make_job(company)
    application = make_application(job, "board@example.test")
    client.force_login(owner)
    response = client.post(
        reverse("web:application_review", args=[application.pk]),
        {"decision": StageReview.PASS},
        HTTP_HX_REQUEST="true",
    )
    body = response.content.decode()
    assert response.status_code == 200
    assert 'id="kanban"' in body
    # every column head is present, so counts are re-rendered
    assert body.count("ip-board__count") == len(job.stages.all())


@pytest.mark.django_db
def test_queue_review_post_returns_the_queue_form_not_the_recruiter_card(
    client, interviewer, company, make_job, make_application
):
    job = make_job(company)
    stage = job.stages.filter(kind=PipelineStage.INTERVIEW).first()
    application = make_application(job, "queue@example.test", stage=stage)
    client.force_login(interviewer)
    response = client.post(
        reverse("web:application_review", args=[application.pk]),
        {"decision": StageReview.HOLD, "ui": "queue"},
        HTTP_HX_REQUEST="true",
    )
    body = response.content.decode()
    assert response.status_code == 200
    assert "Saved." in body
    assert 'id="kanban"' not in body
    assert "application_advance" not in body
    assert reverse("web:application_advance", args=[application.pk]) not in body
    assert reverse("web:application_reject", args=[application.pk]) not in body


@pytest.mark.django_db
def test_interviewer_queue_hides_the_recruiter_board_link(
    client, interviewer, company, make_job, make_application
):
    job = make_job(company)
    stage = job.stages.filter(kind=PipelineStage.INTERVIEW).first()
    make_application(job, "q2@example.test", stage=stage)
    client.force_login(interviewer)
    response = client.get(reverse("web:interviewer_queue"))
    assert response.status_code == 200
    assert reverse("web:job_detail", args=[job.pk]) not in response.content.decode()
    assert response.context["can_open_board"] is False


@pytest.mark.django_db
def test_recruiter_queue_keeps_the_board_link(
    client, recruiter, company, make_job, make_application
):
    job = make_job(company)
    stage = job.stages.filter(kind=PipelineStage.INTERVIEW).first()
    make_application(job, "q3@example.test", stage=stage)
    client.force_login(recruiter)
    response = client.get(reverse("web:interviewer_queue"))
    assert reverse("web:job_detail", args=[job.pk]) in response.content.decode()


@pytest.mark.django_db
def test_double_clicked_advance_only_moves_one_stage(
    client, owner, company, make_job, make_application
):
    job = make_job(company)
    application = make_application(job, "race@example.test")
    first = application.current_stage
    client.force_login(owner)
    url = reverse("web:application_advance", args=[application.pk])
    payload = {"expected_stage": str(first.pk)}

    one = client.post(url, payload, HTTP_HX_REQUEST="true")
    two = client.post(url, payload, HTTP_HX_REQUEST="true")

    assert one.status_code == 200
    assert two.status_code == 200
    application.refresh_from_db()
    assert application.current_stage.order == first.order + 1
    assert "up to date" in two.content.decode()


@pytest.mark.django_db
def test_double_clicked_reject_is_idempotent(
    client, owner, company, make_job, make_application
):
    job = make_job(company)
    application = make_application(job, "race2@example.test")
    stage = application.current_stage
    client.force_login(owner)
    url = reverse("web:application_reject", args=[application.pk])
    payload = {"expected_stage": str(stage.pk)}
    client.post(url, payload, HTTP_HX_REQUEST="true")
    second = client.post(url, payload, HTTP_HX_REQUEST="true")
    application.refresh_from_db()
    assert application.status == Application.REJECTED
    assert application.current_stage_id == stage.pk
    assert "up to date" in second.content.decode()


@pytest.mark.django_db
def test_advance_without_expected_stage_still_works(
    client, owner, company, make_job, make_application
):
    """Old clients (and non-HTMX posts) that send no expected stage keep working."""
    job = make_job(company)
    application = make_application(job, "plain@example.test")
    client.force_login(owner)
    response = client.post(reverse("web:application_advance", args=[application.pk]))
    assert response.status_code == 302
    application.refresh_from_db()
    assert application.current_stage.order == 2


@pytest.mark.django_db
def test_advance_card_carries_the_expected_stage(
    client, owner, company, make_job, make_application
):
    job = make_job(company)
    application = make_application(job, "vals@example.test")
    client.force_login(owner)
    body = client.get(reverse("web:job_detail", args=[job.pk])).content.decode()
    assert f'"expected_stage": "{application.current_stage_id}"' in body
    assert "hx-disabled-elt" in body


@pytest.mark.django_db
def test_unassigned_applications_get_a_move_to_stage_picker(
    client, owner, company, make_job, make_application
):
    job = make_job(company)
    application = make_application(job, "lost@example.test")
    Application.objects.filter(pk=application.pk).update(current_stage=None)
    client.force_login(owner)
    body = client.get(reverse("web:job_detail", args=[job.pk])).content.decode()
    assert "Unassigned" in body
    assert "Move to stage" in body
    assert reverse("web:application_set_stage", args=[application.pk]) in body


@pytest.mark.django_db
def test_application_set_stage_puts_the_card_on_the_board(
    client, owner, company, make_job, make_application
):
    job = make_job(company)
    application = make_application(job, "lost2@example.test")
    Application.objects.filter(pk=application.pk).update(current_stage=None)
    target = job.stages.get(order=2)
    client.force_login(owner)
    response = client.post(
        reverse("web:application_set_stage", args=[application.pk]),
        {"stage": target.pk},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    application.refresh_from_db()
    assert application.current_stage_id == target.pk


@pytest.mark.django_db
def test_set_stage_rejects_a_stage_from_another_job(
    client, owner, company, make_job, make_application
):
    job = make_job(company)
    other = make_job(company, title="Other", status="DRAFT")
    application = make_application(job, "lost3@example.test")
    client.force_login(owner)
    response = client.post(
        reverse("web:application_set_stage", args=[application.pk]),
        {"stage": other.stages.first().pk},
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_board_url_opened_directly_redirects_to_the_job_page(
    client, owner, company, make_job
):
    job = make_job(company)
    client.force_login(owner)
    response = client.get(reverse("web:job_kanban", args=[job.pk]))
    assert response.status_code == 302
    assert response["Location"] == reverse("web:job_detail", args=[job.pk])


@pytest.mark.django_db
def test_board_url_still_serves_the_partial_to_htmx(client, owner, company, make_job):
    job = make_job(company)
    client.force_login(owner)
    response = client.get(
        reverse("web:job_kanban", args=[job.pk]), HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 200
    assert 'id="kanban"' in response.content.decode()
