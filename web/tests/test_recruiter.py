import pytest
from django.urls import reverse

from jobs.models import Application, PipelineStage, StageReview


@pytest.mark.django_db
def test_dashboard_renders_kpis_and_jobs(client, owner, company, make_job):
    make_job(company, title="Backend Engineer")
    client.force_login(owner)
    response = client.get(reverse("web:dashboard"))
    assert response.status_code == 200
    assert b"Backend Engineer" in response.content
    assert b"Avg fit score" in response.content
    assert response.context["kpis"]["open_jobs"] == 1


@pytest.mark.django_db
def test_kanban_shows_stage_columns_and_cards(client, owner, company, make_job, make_application):
    job = make_job(company)
    make_application(job, "a@example.test")
    client.force_login(owner)
    response = client.get(reverse("web:job_detail", args=[job.pk]))
    assert response.status_code == 200
    assert b"Screening" in response.content
    assert b"a@example.test" in response.content
    assert b">71<" in response.content  # ai_fit_score badge


@pytest.mark.django_db
def test_kanban_is_isolated_between_companies(
    client, owner, other_owner, company, other_company, make_job, make_application
):
    mine = make_job(company, title="Mine")
    theirs = make_job(other_company, title="Theirs")
    make_application(theirs, "secret@example.test")
    client.force_login(owner)

    board = client.get(reverse("web:job_detail", args=[mine.pk]))
    assert b"secret@example.test" not in board.content
    assert client.get(reverse("web:job_detail", args=[theirs.pk])).status_code == 404


@pytest.mark.django_db
def test_htmx_advance_moves_application_to_next_stage(
    client, owner, company, make_job, make_application
):
    job = make_job(company)
    application = make_application(job, "b@example.test")
    first = application.current_stage
    client.force_login(owner)
    response = client.post(
        reverse("web:application_advance", args=[application.pk]),
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    application.refresh_from_db()
    assert application.current_stage.order == first.order + 1


@pytest.mark.django_db
def test_reject_marks_application_rejected(client, owner, company, make_job, make_application):
    job = make_job(company)
    application = make_application(job, "c@example.test")
    client.force_login(owner)
    client.post(reverse("web:application_reject", args=[application.pk]))
    application.refresh_from_db()
    assert application.status == Application.REJECTED


@pytest.mark.django_db
def test_cannot_advance_another_companys_application(
    client, owner, other_company, make_job, make_application
):
    job = make_job(other_company)
    application = make_application(job, "d@example.test")
    client.force_login(owner)
    response = client.post(reverse("web:application_advance", args=[application.pk]))
    assert response.status_code == 404
    application.refresh_from_db()
    assert application.current_stage == job.first_stage


@pytest.mark.django_db
def test_review_form_creates_review_and_can_advance(
    client, owner, company, make_job, make_application
):
    job = make_job(company)
    application = make_application(job, "e@example.test")
    client.force_login(owner)
    response = client.post(
        reverse("web:application_review", args=[application.pk]),
        {"decision": StageReview.PASS, "rating": "4", "feedback": "Strong"},
    )
    assert response.status_code == 302
    review = StageReview.objects.get(application=application)
    assert review.decision == StageReview.PASS
    assert review.rating == 4
    application.refresh_from_db()
    assert application.current_stage.order == 2


@pytest.mark.django_db
def test_job_create_seeds_pipeline(client, owner, company):
    client.force_login(owner)
    response = client.post(
        reverse("web:job_create"),
        {
            "title": "SRE",
            "location": "Pune",
            "employment_type": "FULL_TIME",
            "status": "OPEN",
            "description": "d",
            "requirements": "r",
        },
    )
    assert response.status_code == 302
    job = company.jobs.get(title="SRE")
    assert job.stages.count() == len(job.DEFAULT_STAGES)


@pytest.mark.django_db
def test_owner_invite_creates_inactive_placeholder_user(client, owner, company):
    from core.models import Membership

    client.force_login(owner)
    response = client.post(
        reverse("web:settings_members"),
        {"email": "new.hire@acme.test", "role": Membership.INTERVIEWER},
        follow=True,
    )
    assert response.status_code == 200
    membership = Membership.objects.get(company=company, user__email="new.hire@acme.test")
    assert membership.role == Membership.INTERVIEWER
    assert membership.user.is_active is False


@pytest.mark.django_db
def test_skills_are_scoped_to_company(client, owner, other_company, company):
    from jobs.models import Skill

    Skill.objects.create(company=other_company, name="Kubernetes")
    client.force_login(owner)
    client.post(reverse("web:settings_skills"), {"name": "Django"})
    response = client.get(reverse("web:settings_skills"))
    assert b"Django" in response.content
    assert b"Kubernetes" not in response.content
    assert Skill.objects.filter(company=company, name="Django").exists()


@pytest.mark.django_db
def test_interviewer_queue_only_lists_interview_stages(
    client, interviewer, company, make_job, make_application
):
    job = make_job(company)
    screening = job.stages.get(order=1)
    l1 = job.stages.filter(kind=PipelineStage.INTERVIEW).first()
    make_application(job, "screen@example.test", stage=screening)
    make_application(job, "interview@example.test", stage=l1)
    client.force_login(interviewer)
    response = client.get(reverse("web:interviewer_queue"))
    assert response.status_code == 200
    assert b"interview@example.test" in response.content
    assert b"screen@example.test" not in response.content


@pytest.mark.django_db
def test_interviewer_cannot_open_recruiter_pages(client, interviewer, company, make_job):
    job = make_job(company)
    client.force_login(interviewer)
    assert client.get(reverse("web:dashboard")).status_code == 403
    assert client.get(reverse("web:job_create")).status_code == 403
    assert client.get(reverse("web:settings_members")).status_code == 403
    assert client.get(reverse("web:job_detail", args=[job.pk])).status_code == 403
