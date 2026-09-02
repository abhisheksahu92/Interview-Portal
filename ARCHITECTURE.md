# Interview Portal v2 — Architecture Spec (shared by all agents)

Goal: turn the old single-company Django demo into a multi-tenant, configurable hiring SaaS
for small IT services / staffing firms, with AI-assisted screening.

## Stack
- Django 5.x, Python 3.12, Django REST Framework, HTMX + Bootstrap 5 (CDN) for UI, django-environ for settings.
- DB: PostgreSQL in prod (DATABASE_URL); SQLite fallback for local dev/tests.
- Anthropic Python SDK for AI features (agent working on it must load the `claude-api` skill).
- pytest + pytest-django, ruff, GitHub Actions CI.

## Apps (each agent owns ONLY its app directory unless told otherwise)
- `core/`        — Company (tenant), CustomUser (email login), Membership(user, company, role: OWNER/RECRUITER/INTERVIEWER), TenantMiddleware (request.company), base templates, auth views. [Foundation agent]
- `jobs/`        — domain models + services only, no UI. Job (FK company), PipelineStage (per job, ordered, configurable: e.g. Screening, L1, L2, HR, Offer), Application (candidate x job, current_stage), StageReview (application, stage, reviewer, decision, feedback), CandidateProfile (user, resume, experience, notice period, skills M2M). Skill is a per-company model, NOT hardcoded choices.
- `assessments/` — Skill-tagged QuestionBank/Question (MCQ + free text), Assessment (per job stage, time limit, pass mark), Attempt (application, answers JSON, score), AI: generate questions from a job description, grade free-text answers, summarize a resume against job requirements (Claude API; key via ANTHROPIC_API_KEY; must degrade gracefully when key missing).
- `api/`         — DRF viewsets/serializers for everything above, token auth, OpenAPI schema (drf-spectacular), scoped by request.company.
- `billing/`     — Plan (FREE/PRO, max_open_jobs) + Subscription (per company, Stripe ids/status), Stripe checkout/portal/webhooks, `manage.py provision_subscriptions`, and a `pre_save` signal on `jobs.Job` enforcing the open-job limit for companies that have a Subscription row. Depends on core + jobs; jobs never imports billing.
- `web/`         — **the canonical server-rendered UI** (all job/skill/stage/pipeline screens live here; `jobs/` is domain-only and ships no views or templates). HTMX/Bootstrap 5 templates + views: recruiter dashboard (pipeline kanban), candidate portal (apply, take assessment, track status), interviewer review screens, company settings (stages, skills, members).

## Shared-file rules
- `interview_portal/settings.py`, root `urls.py`, `requirements.txt`, `pyproject.toml` are written ONCE by the foundation agent, which pre-registers all five apps and includes all five url modules (`core.urls`, `jobs.urls`, `assessments.urls`, `api.urls`, `web.urls`) with stub urlpatterns.
- Later agents may only APPEND lines to requirements.txt and must NOT reorder/rewrite shared files.
- Cross-app imports: jobs -> core; assessments -> jobs, core; api/web -> all. Never import web/api from domain apps.
- Every app ships migrations and tests. `python manage.py check` and `pytest` must pass before an agent finishes.
- All secrets from env only. Never commit .env, sqlite DBs, or media.

## Legacy
Old apps `candidate/`, `employee/`, `empadmin/`, `dashboard/`, old `jobs/` and old templates/static are deleted by the foundation agent. Old `db.sqlite3`, `media/`, `.env`, and leaked Dockerfile token are removed.

## Pinned model contract (agents build against this; jobs agent implements it verbatim)

### jobs/models.py
- Skill(company FK related_name="skills", name CharField(80)); unique (company, name).
- Job(company FK related_name="jobs", title, location, description TextField, requirements TextField,
  employment_type choices FULL_TIME/CONTRACT/INTERN, status choices DRAFT/OPEN/CLOSED default DRAFT,
  skills M2M Skill blank, created_by FK core.User null, created_at, closes_at DateField null).
- PipelineStage(job FK related_name="stages", name CharField(80), order PositiveInteger,
  kind choices SCREENING/ASSESSMENT/INTERVIEW/HR/OFFER, requires_assessment bool default False);
  unique (job, order); ordering ["order"]. Job.save() on create seeds default stages:
  Screening(SCREENING), Assessment(ASSESSMENT, requires_assessment=True), L1 Interview, L2 Interview, HR, Offer.
- CandidateProfile(user OneToOne core.User related_name="candidate_profile", phone, date_of_birth null,
  experience_years Decimal(4,1), notice_period_days PositiveInteger default 0, resume FileField upload_to="resumes/" blank,
  headline CharField(200) blank, skills M2M Skill blank).
- Application(job FK related_name="applications", candidate FK CandidateProfile related_name="applications",
  current_stage FK PipelineStage null, status choices ACTIVE/REJECTED/HIRED/WITHDRAWN default ACTIVE,
  ai_summary TextField blank, ai_fit_score PositiveSmallInteger null, created_at, updated_at); unique (job, candidate).
  Methods: advance() -> moves to next stage or marks HIRED at last stage; reject(); property company -> job.company.
- StageReview(application FK related_name="reviews", stage FK PipelineStage, reviewer FK core.User,
  decision choices PASS/FAIL/HOLD, rating PositiveSmallInteger 1-5 null, feedback TextField blank, created_at);
  unique (application, stage, reviewer).

### assessments/models.py
- Question(company FK, skill FK jobs.Skill null, kind choices MCQ/TEXT, text TextField, options JSONField list default list,
  correct_option PositiveSmallInteger null, difficulty choices EASY/MEDIUM/HARD, source choices MANUAL/AI, created_at).
- Assessment(job FK jobs.Job related_name="assessments", stage FK jobs.PipelineStage null, title, questions M2M Question,
  time_limit_minutes PositiveInteger default 30, pass_mark_percent PositiveSmallInteger default 60, is_active bool).
- Attempt(assessment FK, application FK jobs.Application related_name="attempts", started_at, submitted_at null,
  answers JSONField dict {question_id: answer} default dict, score_percent Decimal(5,2) null, passed bool null,
  ai_feedback TextField blank). Method grade() scores MCQs locally and TEXT answers via assessments.ai when key present.

### assessments/ai.py (service module, all functions must work without ANTHROPIC_API_KEY by returning None/[] and logging)
- generate_questions(job, skill, n=5, kind="MCQ") -> list[Question] (saved, source=AI)
- grade_text_answer(question, answer) -> int 0-100 | None
- summarize_fit(application) -> sets application.ai_summary / ai_fit_score
