# Interview Portal v2 — Architecture Spec (shared by all agents)

Goal: turn the old single-company Django demo into a multi-tenant, configurable hiring SaaS
for small IT services / staffing firms, with AI-assisted screening.

## Stack
- Django 5.x, Python 3.12, Django REST Framework, HTMX + Bootstrap 5 (CDN) for UI, django-environ for settings.
- DB: PostgreSQL in prod (DATABASE_URL); SQLite fallback for local dev/tests.
- Anthropic Python SDK for AI features (agent working on it must load the `claude-api` skill).
- pytest + pytest-django (parallel via pytest-xdist, `-n auto` in pyproject addopts), ruff, GitHub Actions CI.
- Scheduled work: one `manage.py run_periodic` entry point runs every maintenance command in order, logging failures.

## Apps (each agent owns ONLY its app directory unless told otherwise)
- `core/`        — Company (tenant), CustomUser (email login), Membership(user, company, role: OWNER/RECRUITER/INTERVIEWER), TenantMiddleware (request.company), base templates, auth views. [Foundation agent]
- `jobs/`        — domain models + services only, no UI. Job (FK company), PipelineStage (per job, ordered, configurable: e.g. Screening, L1, L2, HR, Offer), Application (candidate x job, current_stage), StageReview (application, stage, reviewer, decision, feedback), CandidateProfile (user, resume, experience, notice period, skills M2M). Skill is a per-company model, NOT hardcoded choices.
- `assessments/` — Skill-tagged QuestionBank/Question (MCQ + free text), Assessment (per job stage, time limit, pass mark), Attempt (application, answers JSON, score), AI: generate questions from a job description, grade free-text answers, summarize a resume against job requirements (Claude API; key via ANTHROPIC_API_KEY; must degrade gracefully when key missing).
- `api/`         — DRF viewsets/serializers for everything above, token auth, OpenAPI schema (drf-spectacular), scoped by request.company.
- `billing/`     — Plan (FREE/PRO, max_open_jobs) + Subscription (per company, Stripe ids/status), Stripe checkout/portal/webhooks, `manage.py provision_subscriptions`, and a `pre_save` signal on `jobs.Job` enforcing the open-job limit for companies that have a Subscription row. Depends on core + jobs; jobs never imports billing.
- `web/`         — **the canonical server-rendered UI** (all job/skill/stage/pipeline screens live here; `jobs/` is domain-only and ships no views or templates). HTMX/Bootstrap 5 templates + views: recruiter dashboard (pipeline kanban), candidate portal (apply, take assessment, track status), interviewer review screens, company settings (stages, skills, members).
- `scheduling/`  — interviewer availability, calendar OAuth adapters, Interview rows, candidate self-booking pages, `.ics` invites. [Phase 3]
- `clients/`     — clients of a staffing firm, tokenised client portal, Submission + client feedback. [Phase 3]
- `notifications/` — channel adapters (email / WhatsApp Cloud / SMS stub), event template registry, preferences, OutboundMessage with retry; the single `notifications.send(...)` entrypoint. [Phase 3]
- `talent/`      — talent CRM: TalentProfile, bulk resume import, search, "add to job". [Phase 3]
- `video/`       — one-way video screening: VideoQuestion/VideoScreen/VideoInvite/VideoResponse, recorder + playback, upload sniffing and metered minutes. [Phase 3]
- `careers/`     — public careers site per company, JobDistribution adapters, Indeed XML feed, JSON-LD. [Phase 3]
- `analytics/`   — read-time hiring metrics, charts, CSV export (owner-only). [Phase 3]
- `offers/`      — OfferTemplate/Offer, rendered letter + PDF, click-to-sign audit trail. [Phase 3]
- `partners/`    — Reseller/Referral/CommissionLedger, WhiteLabel, Ed25519-signed self-hosted License keys. [Phase 3]
- `marketplace/` — paid QuestionPack + PackPurchase, opt-in cross-company verified talent pool. [Phase 3]

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

## Phase 3 — Monetization (contracts for parallel agents)

New apps, each owned by one agent. All models with a tenant get `company FK` and are scoped with `for_company`.
Every external service (Razorpay, WhatsApp, video storage, job boards, e-sign) is behind an adapter in `<app>/gateway.py`
that reads env keys, returns a clear "not configured" state when keys are missing, and is mocked in tests. Never call networks in tests.

### billing/ (overhaul)
- Plan gains: code STARTER/GROWTH/AGENCY (keep FREE for legacy/trial), price_monthly_inr, price_yearly_inr, max_seats, ai_credits_monthly,
  features JSON (scheduling, careers_page, client_portal, whatsapp, video, api). Data migration seeds 3 tiers (1499/4999/12999 INR monthly; yearly = 10x).
- Subscription gains: provider choices STRIPE/RAZORPAY, interval MONTHLY/YEARLY, trial_ends_at (14-day full-featured trial on company creation),
  seats_used property, gstin CharField blank, billing_address JSON.
- UsageRecord(company, kind AI_SCREEN/WHATSAPP_MSG/VIDEO_MINUTE, quantity, period_start); helper `billing.usage.consume(company, kind, qty=1)` raises `QuotaExceeded` past plan quota; `usage.warn_threshold=0.8` triggers a notification via notifications app.
- InvoiceCounter(fy unique, last_seq): invoice numbers are allocated by locking this row (`select_for_update` in `transaction.atomic()`), never by scanning
  existing numbers — two concurrent payments must not mint the same number.
- ProcessedWebhookEvent(provider, event_id unique together, event_type, received_at): every Stripe/Razorpay event is claimed before it is applied, so a
  replay cannot create a second Invoice / PlacementFee / commission. Stripe uses `event.id`; Razorpay the `X-Razorpay-Event-Id` header, else a body hash.
- Invoice(company, number sequential per FY like IP/2026-27/0001, amount, gst_rate 18, cgst/sgst/igst split by state code, gstin, pdf FileField, issued_at, paid_at, provider_ref). PDF via reportlab or weasyprint-free HTML→PDF (xhtml2pdf) — pin whatever you use.
- Razorpay gateway: create subscription/order, verify webhook signature, handle payment.captured/subscription.charged/failed. Dunning: PAST_DUE → 3 reminder emails over 7 days then downgrade.
- PlacementFee(company, application, amount, status) auto-created on HIRED when plan has per_hire_fee set.
- `billing.entitlements.has_feature(company, "client_portal")` used by every gated app; `require_feature(name)` decorator/mixin.

### scheduling/
- InterviewerAvailability(user, weekday, start, end, timezone), CalendarConnection(user, provider GOOGLE/OUTLOOK, tokens JSON, enabled) — OAuth adapters env-gated.
- Interview(application, stage, interviewers M2M, scheduled_start, scheduled_end, timezone, location_or_link, status PROPOSED/CONFIRMED/RESCHEDULED/CANCELLED/COMPLETED, booking_token).
- Candidate self-service booking page at /schedule/<token>/ showing computed free slots; reschedule/cancel links; .ics attachments in emails; auto-create Interview proposal when application enters an INTERVIEW/HR stage.

### clients/ (client portal for staffing firms)
- Client(company, name, contact_email, logo), ClientAccess(client, email, token, expires_at), Job gets optional `client FK` (add in jobs/ via migration — clients agent may add ONLY this field + migration to jobs/).
- Submission(application, client, note, status SUBMITTED/SHORTLISTED/REJECTED/INTERVIEW_REQUESTED, client_feedback, decided_at).
- Portal at /client/<token>/: branded read-only shortlist with resume view, AI summary, feedback form. Gated by feature client_portal.

### notifications/
- Channel adapters: email (existing), WhatsApp Business Cloud API (env WHATSAPP_TOKEN/PHONE_ID), SMS stub. Template registry keyed by event (application_received, stage_advanced, interview_scheduled, reminder_24h, assessment_result, offer_sent, usage_warning, payment_failed).
- NotificationPreference(company, event, channels JSON), OutboundMessage(company, recipient, channel, event, payload, status, provider_ref, sent_at) with retry.
- `notifications.send(event, recipient_user_or_phone, context, company)` — the single entrypoint other apps call (jobs/emails.py should delegate here; notifications agent may edit jobs/emails.py only).
- Consumes WHATSAPP_MSG usage via billing.usage.consume.

### talent/
- TalentProfile(company, email, name, phone, resume, resume_text, skills M2M, source, tags JSON, last_contacted, linked_candidate FK CandidateProfile null), unique (company, email).
- Bulk import: zip/multiple files upload → background-safe sync parse via assessments.resume.extract_text; AI extraction of name/email/skills via assessments.ai when key present; dedupe by email/phone.
- Full-text search (Postgres search vector when on Postgres, LIKE fallback), filters by skill/experience/tags; "Add to job" creates an Application.

### video/
- VideoQuestion(company, text, think_seconds, answer_seconds), VideoScreen(job, stage, questions M2M, deadline_days), VideoResponse(application, screen, question, file FileField/S3 key, duration, transcript, ai_summary, status).
- Candidate recorder page using MediaRecorder API (webm), upload in chunks or single POST, size cap, container magic-byte sniffing (webm `1A 45 DF A3`,
  mp4 `ftyp` at offset 4) mirroring jobs/validators.py, and a server-side duration cap of `question.answer_seconds + 5` (client duration is never trusted); recruiter review page with playback + AI summary (assessments.ai style; transcript via env-gated adapter, otherwise blank). Consumes VIDEO_MINUTE usage.

### careers/
- CareersSite(company OneToOne, slug, custom_domain, headline, about, brand_color, logo, published). Public page at /careers/<slug>/ (and by Host header for custom domains) listing OPEN jobs with apply flow reusing web apply.
- JobDistribution(job, board LINKEDIN/INDEED/NAUKRI, status, external_id, posted_at): adapters env-gated (Indeed XML feed generation is real: /careers/feeds/indeed.xml; others stubbed with clear "connect account" UI). SEO: JobPosting JSON-LD on job pages.

### analytics/
- Materialized-on-read metrics service: time_to_hire, funnel by stage, source effectiveness, interviewer consistency (rating variance), offer acceptance, assessment pass rates; date range + job filters; CSV export. Dashboard page with charts (Chart.js via cdnjs, load the `dataviz` skill). Owner-only.

### offers/
- OfferTemplate(company, name, body_html with {{placeholders}}), Offer(application, template, salary, currency INR, joining_date, expires_at, body_rendered, pdf, status DRAFT/SENT/VIEWED/ACCEPTED/DECLINED/EXPIRED, sign_token, signed_name, signed_ip, signed_at). Built-in click-to-sign with audit trail; optional external e-sign adapter env-gated. Accepting marks application HIRED.

### partners/
- Reseller(name, code, commission_pct, contact), Referral(reseller, company, signed_up_at, first_payment_at), CommissionLedger entries computed from Invoices paid. Signup accepts ?ref=CODE (cookie 30 days). Reseller dashboard at /partners/<code>/ via token login.
- WhiteLabel(company OneToOne, brand_name, logo, primary_color, custom_domain, hide_powered_by) applied via context processor in base.html when present (partners agent may edit base.html brand block ONLY).
- License(company, kind SELF_HOSTED, key, seats, expires_at) + `manage.py issue_license` / `verify_license` / `generate_license_keypair`.
  Keys are **Ed25519**-signed (`IPL2.<payload>.<sig>`), never HMAC over SECRET_KEY — a self-hosted customer holds SECRET_KEY and must not be able to
  forge keys. The private key comes from env `LICENSE_SIGNING_KEY` (base64 raw 32 bytes) and is used only by `issue_license`; the public key is embedded
  as `partners.licensing.LICENSE_PUBLIC_KEY` so `verify_license` works offline on every install.

### marketplace/
- QuestionPack(title, skill_name, description, price_inr, questions JSON, published, author), PackPurchase(company, pack, invoice FK null, purchased_at); purchase copies questions into the company's Question bank (source=MARKETPLACE — add choice in assessments/ is allowed for marketplace agent, one line). Verified candidate pool: opt-in flag on CandidateProfile `share_in_pool` (marketplace agent may add this field + migration to jobs/), cross-company search of candidates who passed any assessment, gated by feature `talent_pool_search`.

### Shared wiring (foundation agent only)
INSTALLED_APPS + root urls for all 10 apps; sidebar links: Schedule, Clients, Talent, Video, Careers, Analytics, Offers, Marketplace, plus Settings ▸ Notifications, Branding, Partners; pyproject testpaths; requirements pins: razorpay, xhtml2pdf, google-api-python-client, google-auth-oauthlib, msal, icalendar, python-dateutil, requests. New feature agents may only APPEND to requirements.txt.
