import pytest

from assessments.models import Assessment, Question
from core.models import Company, Membership, User
from jobs.models import Application, CandidateProfile, Job, Skill


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme Staffing")


@pytest.fixture
def other_company(db):
    return Company.objects.create(name="Globex")


@pytest.fixture
def recruiter(db, company):
    user = User.objects.create_user(email="rec@acme.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.RECRUITER)
    return user


@pytest.fixture
def interviewer(db, company):
    user = User.objects.create_user(email="int@acme.test", password="pw12345678")
    Membership.objects.create(user=user, company=company, role=Membership.INTERVIEWER)
    return user


@pytest.fixture
def other_recruiter(db, other_company):
    user = User.objects.create_user(email="rec@globex.test", password="pw12345678")
    Membership.objects.create(user=user, company=other_company, role=Membership.RECRUITER)
    return user


@pytest.fixture
def skill(company):
    return Skill.objects.create(company=company, name="Python")


@pytest.fixture
def job(company, skill):
    job = Job.objects.create(
        company=company,
        title="Backend Engineer",
        description="Build APIs.",
        requirements="3 years Python.",
        status=Job.OPEN,
    )
    job.skills.add(skill)
    return job


@pytest.fixture
def candidate(db, skill):
    user = User.objects.create_user(
        email="cand@x.test", password="pw12345678", is_candidate=True
    )
    profile = CandidateProfile.objects.create(
        user=user, headline="Python dev", experience_years=4
    )
    profile.skills.add(skill)
    return profile


@pytest.fixture
def application(job, candidate):
    stages = list(job.stages.order_by("order"))
    return Application.objects.create(
        job=job, candidate=candidate, current_stage=stages[1]
    )


@pytest.fixture
def mcq_questions(company, skill):
    return [
        Question.objects.create(
            company=company,
            skill=skill,
            kind=Question.MCQ,
            text=f"Question {i}?",
            options=["a", "b", "c", "d"],
            correct_option=1,
        )
        for i in range(4)
    ]


@pytest.fixture
def assessment(job, mcq_questions):
    stage = job.stages.order_by("order")[1]
    obj = Assessment.objects.create(
        job=job, stage=stage, title="Python screen", pass_mark_percent=60
    )
    obj.questions.set(mcq_questions)
    return obj
