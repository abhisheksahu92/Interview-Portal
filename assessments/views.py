"""Recruiter question bank / assessment builder plus candidate attempt views."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from assessments import ai, services
from assessments.forms import AssessmentForm, GenerateQuestionsForm, QuestionForm
from assessments.models import Assessment, Attempt, Question
from core.models import Membership
from core.permissions import for_company, role_required

STAFF_ROLES = (Membership.OWNER, Membership.RECRUITER)


def _company(request):
    company = getattr(request, "company", None)
    if company is None:
        raise PermissionDenied("No company selected.")
    return company


def _company_questions(request):
    return for_company(Question.objects.select_related("skill"), _company(request))


def _get_job(request, job_id):
    from jobs.models import Job

    return get_object_or_404(for_company(Job.objects.all(), _company(request)), pk=job_id)


def _get_assessment(request, pk):
    company = _company(request)
    return get_object_or_404(
        Assessment.objects.select_related("job", "stage").filter(job__company=company),
        pk=pk,
    )


# --- Question bank --------------------------------------------------------
@login_required
@role_required(*STAFF_ROLES)
def question_list(request):
    questions = _company_questions(request)
    kind = request.GET.get("kind")
    if kind in {Question.MCQ, Question.TEXT}:
        questions = questions.filter(kind=kind)
    skill_id = request.GET.get("skill")
    if skill_id:
        questions = questions.filter(skill_id=skill_id)
    return render(
        request,
        "assessments/question_list.html",
        {
            "questions": questions,
            "skills": _company(request).skills.all(),
            "generate_form": GenerateQuestionsForm(company=_company(request)),
            "kind": kind or "",
            "skill_id": skill_id or "",
        },
    )


@login_required
@role_required(*STAFF_ROLES)
def question_create(request):
    company = _company(request)
    form = QuestionForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Question added to the bank.")
        return redirect("assessments:question_list")
    return render(
        request, "assessments/question_form.html", {"form": form, "question": None}
    )


@login_required
@role_required(*STAFF_ROLES)
def question_edit(request, pk):
    question = get_object_or_404(_company_questions(request), pk=pk)
    form = QuestionForm(request.POST or None, instance=question, company=question.company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Question updated.")
        return redirect("assessments:question_list")
    return render(
        request, "assessments/question_form.html", {"form": form, "question": question}
    )


@login_required
@role_required(*STAFF_ROLES)
@require_POST
def question_delete(request, pk):
    question = get_object_or_404(_company_questions(request), pk=pk)
    question.delete()
    messages.success(request, "Question deleted.")
    return redirect("assessments:question_list")


@login_required
@role_required(*STAFF_ROLES)
@require_POST
def question_generate(request):
    """HTMX-friendly: generate AI questions and return the rows partial."""
    company = _company(request)
    form = GenerateQuestionsForm(request.POST, company=company)
    created, error = [], ""
    if form.is_valid():
        created = ai.generate_questions(
            form.cleaned_data["job"],
            form.cleaned_data.get("skill"),
            n=form.cleaned_data["n"],
            kind=form.cleaned_data["kind"],
        )
        if not created:
            error = (
                "No questions were generated. Check that ANTHROPIC_API_KEY is "
                "configured, then try again."
            )
    else:
        error = "Please correct the generation options and try again."
    return render(
        request,
        "assessments/partials/generated_questions.html",
        {"created": created, "error": error},
    )


# --- Assessment builder ---------------------------------------------------
@login_required
@role_required(*STAFF_ROLES)
def job_assessments(request, job_id):
    job = _get_job(request, job_id)
    return render(
        request,
        "assessments/assessment_list.html",
        {"job": job, "assessments": job.assessments.select_related("stage")},
    )


@login_required
@role_required(*STAFF_ROLES)
def assessment_create(request, job_id):
    job = _get_job(request, job_id)
    form = AssessmentForm(request.POST or None, job=job)
    if request.method == "POST" and form.is_valid():
        assessment = form.save()
        messages.success(request, "Assessment saved.")
        return redirect("assessments:job_assessments", job_id=assessment.job_id)
    return render(
        request,
        "assessments/assessment_form.html",
        {"form": form, "job": job, "assessment": None},
    )


@login_required
@role_required(*STAFF_ROLES)
def assessment_edit(request, pk):
    assessment = _get_assessment(request, pk)
    form = AssessmentForm(request.POST or None, instance=assessment, job=assessment.job)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Assessment updated.")
        return redirect("assessments:job_assessments", job_id=assessment.job_id)
    return render(
        request,
        "assessments/assessment_form.html",
        {"form": form, "job": assessment.job, "assessment": assessment},
    )


@login_required
@role_required(*STAFF_ROLES)
def assessment_attempts(request, pk):
    assessment = _get_assessment(request, pk)
    return render(
        request,
        "assessments/attempt_list.html",
        {
            "assessment": assessment,
            "attempts": assessment.attempts.select_related(
                "application", "application__candidate", "application__candidate__user"
            ),
        },
    )


# --- Candidate views ------------------------------------------------------
def _candidate_application(request, application_id):
    from jobs.models import Application

    application = get_object_or_404(
        Application.objects.select_related("job", "candidate", "candidate__user"),
        pk=application_id,
    )
    if application.candidate.user_id != request.user.id:
        raise PermissionDenied("This application belongs to another candidate.")
    return application


def _candidate_attempt(request, pk):
    attempt = get_object_or_404(
        Attempt.objects.select_related(
            "assessment", "application", "application__candidate"
        ),
        pk=pk,
    )
    if attempt.application.candidate.user_id != request.user.id:
        raise PermissionDenied("This attempt belongs to another candidate.")
    return attempt


@login_required
def take_assessment(request, application_id, assessment_id):
    """Start (or resume) an attempt and show the questions."""
    application = _candidate_application(request, application_id)
    assessment = get_object_or_404(
        Assessment.objects.prefetch_related("questions"), pk=assessment_id
    )
    try:
        attempt = services.start_attempt(assessment, application)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        existing = Attempt.objects.filter(
            assessment=assessment, application=application
        ).first()
        if existing is not None:
            return redirect("assessments:attempt_result", pk=existing.pk)
        return redirect("/")
    return render(
        request,
        "assessments/take_assessment.html",
        {
            "attempt": attempt,
            "assessment": assessment,
            "questions": assessment.questions.all(),
        },
    )


@login_required
@require_POST
def submit_attempt(request, pk):
    attempt = _candidate_attempt(request, pk)
    answers = {}
    for question in attempt.assessment.questions.all():
        value = request.POST.get(f"q{question.pk}")
        if value not in (None, ""):
            answers[str(question.pk)] = value
    try:
        services.submit_attempt(attempt, answers)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Assessment submitted.")
    return redirect("assessments:attempt_result", pk=attempt.pk)


@login_required
def attempt_result(request, pk):
    attempt = _candidate_attempt(request, pk)
    return render(request, "assessments/attempt_result.html", {"attempt": attempt})


def urls_help():  # pragma: no cover - convenience for templates/tests
    return reverse("assessments:question_list")
