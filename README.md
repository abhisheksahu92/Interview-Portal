# Interview Portal v2

Multi-tenant hiring platform for small IT services / staffing firms, with AI-assisted screening.
Django 5 + DRF + HTMX/Bootstrap 5. See `ARCHITECTURE.md` for the full design.

## Features
- **Multi-tenant** — every company is a tenant; `TenantMiddleware` puts the active
  company on `request.company` and all queries/permissions are scoped to it.
  Users can belong to several companies and switch between them.
- **Roles** — OWNER / RECRUITER / INTERVIEWER memberships, plus external candidates.
- **Configurable pipelines** — each job gets default stages (Screening, Assessment,
  L1, L2, HR, Offer) that recruiters can rename, reorder, add to or delete.
- **Recruiter workspace** — KPI dashboard, drag-free kanban board per job with
  HTMX advance/reject/review actions, member and skill settings.
- **Interviewer queue** — every interview/HR-stage application awaiting your review,
  with inline PASS/FAIL/HOLD + rating + feedback (a PASS advances, a FAIL rejects).
- **Candidate portal** — browse/search open roles, apply, edit a profile with resume
  upload, and track each application's stage progress.
- **Assessments** — skill-tagged question bank (MCQ + free text), per-stage timed
  assessments with pass marks, candidate attempts with automatic MCQ grading.
- **AI (Claude)** — generate screening questions from a job description, grade
  free-text answers, and summarize a resume against the job into an
  `ai_summary` + `ai_fit_score` (fired automatically on every new application).
  All AI degrades gracefully: with no `ANTHROPIC_API_KEY` it logs and no-ops.
- **Team invitations** — owners invite teammates by email with a role; a signed
  token link (7-day expiry) creates the membership on accept.
- **Billing** — STARTER/GROWTH/AGENCY tiers in INR, 14-day full-featured trial,
  Razorpay + Stripe checkout and webhooks, metered AI/WhatsApp/video usage,
  GST invoices with PDFs, dunning and per-hire placement fees.
- **Interview scheduling** — interviewer availability, Google/Outlook calendar
  sync, candidate self-service booking links with `.ics` invites.
- **Client portal** — branded tokenised shortlists for the staffing firm's own
  clients, with feedback capture.
- **Notifications** — email + WhatsApp Business Cloud + SMS stub behind one
  `notifications.send(...)` entrypoint, with per-event channel preferences.
- **Talent CRM** — sourced talent profiles, bulk resume import with AI
  extraction, full-text search, one-click "add to job".
- **Video screening** — one-way recorded answers (MediaRecorder/WebM), metered
  video minutes, recruiter playback with AI summaries.
- **Careers site** — public branded careers page per company (`/careers/<slug>/`),
  JobPosting JSON-LD and an Indeed XML feed.
- **Analytics** — time-to-hire, funnel, source effectiveness, interviewer
  consistency, offer acceptance and pass rates, with CSV export.
- **Offers** — templated offer letters, PDF, click-to-sign with an audit trail.
- **Partners** — resellers with referral tracking and commissions, white-label
  branding, Ed25519-signed self-hosted licence keys.
- **Marketplace** — paid question packs and an opt-in cross-company talent pool.
- **REST API** — DRF viewsets for everything, token auth (checked before session
  auth, so anonymous calls get `401`), OpenAPI schema + Swagger UI.

## Apps
| App | Responsibility |
| --- | --- |
| `core` | Company (tenant), User (email login), Membership/roles, TenantMiddleware, auth + base templates |
| `jobs` | Domain only: jobs, configurable pipeline stages, applications, stage reviews, candidate profiles, transition services |
| `assessments` | Question banks, assessments, attempts, Claude-powered generation/grading, recruiter + candidate screens |
| `api` | DRF viewsets, token auth, OpenAPI schema (drf-spectacular) |
| `billing` | Plans, per-company subscriptions, Stripe checkout/portal/webhooks, open-job plan limits |
| `web` | **Canonical server-rendered UI**: landing, recruiter dashboard/kanban, candidate portal, interviewer reviews, company settings |
| `scheduling` | Interviewer availability, calendar OAuth, interviews, candidate self-booking pages, `.ics` invites |
| `clients` | Clients of a staffing firm, tokenised client portal, candidate submissions and client feedback |
| `notifications` | Channel adapters (email / WhatsApp / SMS stub), event template registry, per-company preferences, outbox with retry |
| `talent` | Talent CRM: sourced profiles, bulk resume import, search and "add to job" |
| `video` | One-way video screening: question library, screens, invites, uploads, playback and AI summaries |
| `careers` | Public careers site per company, job-board distribution adapters, Indeed XML feed, JSON-LD |
| `analytics` | Read-time hiring metrics, charts and CSV export (owner-only) |
| `offers` | Offer templates, rendered offer letters + PDF, click-to-sign with audit trail |
| `partners` | Resellers, referrals, commission ledger, white-label branding, self-hosted licence keys |
| `marketplace` | Paid question packs and the opt-in cross-company verified talent pool |
| `integrations` | Signed outbound webhooks with retries, HRMS/background-check connectors, per-company API keys |

## Quick start
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                    # DEBUG=True, SQLite by default
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo    # demo company, jobs, questions, applications
.venv/bin/python manage.py runserver
```
Then open http://127.0.0.1:8000/.

`seed_demo` is idempotent (safe to re-run) and creates the **Demo Staffing** company
with 3 skills, 2 open jobs and their pipelines, 3 manual questions, one assessment on
job 1's Assessment stage, 3 applicants spread across stages and one review.

### Demo logins — password `demo1234` for all
| Email | Role |
| --- | --- |
| `owner@demo.test` | OWNER — dashboard, jobs, members, skills |
| `recruiter@demo.test` | RECRUITER — dashboard, jobs, question bank |
| `interviewer@demo.test` | INTERVIEWER — review queue only |
| `candidate@demo.test` | Candidate — portal, browse and apply |
| `asha@demo.test`, `ben@demo.test`, `chen@demo.test` | Candidates with live applications |

Create your own tenant instead at `/accounts/signup/company/`, or a candidate account
at `/accounts/signup/`.

## Key URLs
| Path | What |
| --- | --- |
| `/` | Landing page (redirects logged-in users to their home) |
| `/accounts/login/` | Email + password login (emails are case-insensitive) |
| `/accounts/signup/` | Candidate signup |
| `/accounts/signup/company/` | Company (tenant) signup |
| `/accounts/logout/` | GET shows a confirm page; POST signs out |
| `/dashboard/` | Recruiter/owner dashboard |
| `/workspace/jobs/<id>/` | Job pipeline kanban |
| `/queue/` | Interviewer review queue |
| `/portal/` | Candidate portal |
| `/openings/` | Public job board |
| `/assessments/questions/` | Question bank |
| `/api/v1/` | REST API root |
| `/api/docs/` | Swagger UI (schema at `/api/schema/`) |
| `/billing/` | Plan, usage and upgrade |
| `/billing/webhook/` | Stripe webhook endpoint (POST, no auth, signature-verified) |
| `/billing/razorpay/webhook/` | Razorpay webhook endpoint (POST, no auth, signature-verified) |
| `/billing/invoices/<id>/` | GST invoice PDF download |
| `/scheduling/` | Interviews and availability |
| `/scheduling/book/<token>/` | Candidate self-service booking page (no login) |
| `/clients/` | Clients and submissions |
| `/clients/portal/<token>/` | Client portal shortlist (no login) |
| `/notifications/` | Per-event channel preferences and test send |
| `/notifications/outbox/` | Outbound message log with resend |
| `/talent/` | Talent CRM search, import and profiles |
| `/video/` | Video screens, question library and invites |
| `/video/take/<token>/` | Candidate recorder (no login) |
| `/careers/<slug>/` | Public careers site; `/careers/feeds/indeed.xml` is the job feed |
| `/analytics/` | Hiring metrics dashboard (owner-only), CSV at `/analytics/export/<slug>.csv` |
| `/offers/` | Offers and templates; `/offers/sign/<token>/` is the candidate signing page |
| `/partners/` | White-label and reseller settings, licence-key verification |
| `/partners/<code>/dashboard/` | Reseller dashboard (token login); `?ref=CODE` via `/partners/r/<code>/` |
| `/marketplace/` | Question packs and the verified talent pool |
| `/integrations/` | Webhooks (owner-only); delivery log, connectors and API keys under it |
| `/api/v1/exports/hires.csv` | Streaming hires export for payroll (`?from=&to=`) |
| `/settings/members/` | Members and invitations |
| `/healthz/` | Liveness probe (`ok`, no auth, no DB) |
| `/admin/` | Django admin |

API clients authenticate with `POST /api/v1/auth/token/` (email + password) and then
send `Authorization: Token <key>`.

## Environment variables
Copy `.env.example` to `.env`; everything is read from the environment.

| Var | Default | Notes |
| --- | --- | --- |
| `SECRET_KEY` | insecure dev value | **must** be set in production |
| `DEBUG` | `False` | `True` locally; also selects non-manifest static storage |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | comma-separated |
| `DATABASE_URL` | `sqlite:///db_v2.sqlite3` | e.g. `postgres://user:pass@db:5432/interview_portal` |
| `ANTHROPIC_API_KEY` | empty | enables the Claude features; unset = AI disabled |
| `EMAIL_BACKEND` / `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `EMAIL_USE_TLS` / `DEFAULT_FROM_EMAIL` | console backend | outbound mail |
| `EMAIL_FILE_PATH` | `BASE_DIR/sent_emails` | directory for `django.core.mail.backends.filebased.EmailBackend` |
| `MEDIA_ROOT` | `BASE_DIR/media` | on-disk root for uploads when no S3/R2 bucket is set |
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_PRICE_ID_PRO` | empty | enable Stripe billing; unset = plan/usage shown, upgrade disabled |
| `CSRF_TRUSTED_ORIGINS` | empty | **required in production**, comma-separated, scheme included (`https://app.example.com`) |
| `SECURE_SSL_REDIRECT` | on when `DEBUG=False` | turn off behind a plain-HTTP host |
| `SECURE_HSTS_SECONDS` | `31536000` outside DEBUG | start lower on a custom apex domain |
| `CONN_MAX_AGE` | `60` outside DEBUG/tests | persistent DB connections; must stay `0` under pytest |
| `LOG_LEVEL` / `DJANGO_LOG_LEVEL` | `INFO` | logging goes to stdout |
| `AWS_STORAGE_BUCKET_NAME` / `AWS_S3_REGION_NAME` / `AWS_S3_ENDPOINT_URL` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | empty | set the bucket to move media (resumes) to S3/Cloudflare R2 |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `interview_portal` / `interview` / `interview` | used by the compose `db` service |
| `SITE_URL` | `http://127.0.0.1:8000` | absolute base URL used in emails, `.ics` invites, careers pages and share links |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / `RAZORPAY_WEBHOOK_SECRET` | empty | enable INR checkout + webhooks; unset = Razorpay buttons hidden |
| `COMPANY_GSTIN` / `COMPANY_STATE_CODE` | empty | printed on invoices; the state code drives CGST/SGST vs IGST |
| `WHATSAPP_TOKEN` / `WHATSAPP_PHONE_ID` / `WHATSAPP_VERIFY_TOKEN` | empty | WhatsApp Business Cloud channel; unset = email only |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | empty | Google Calendar sync for interviewers |
| `MS_OAUTH_CLIENT_ID` / `MS_OAUTH_CLIENT_SECRET` | empty | Outlook Calendar sync |
| `VIDEO_TRANSCRIBE_URL` / `VIDEO_TRANSCRIBE_API_KEY` | empty | transcription adapter for video answers; unset = transcript stays blank |
| `ESIGN_API_BASE` / `ESIGN_ACCOUNT_ID` / `ESIGN_API_KEY` | empty | external e-sign provider; unset = built-in click-to-sign |
| `LINKEDIN_JOBS_TOKEN` / `NAUKRI_API_KEY` | empty | job-board distribution; unset = "connect account" prompt (the Indeed feed needs no key) |
| `INTEGRATIONS_ENCRYPTION_KEY` | empty | optional override: urlsafe-base64 Fernet key encrypting connector credentials. Blank derives one from `SECRET_KEY` — set it explicitly if you ever rotate `SECRET_KEY` |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | empty / `gemini-2.5-flash` | fallback model provider for screening, grading, résumé extraction and video review when `ANTHROPIC_API_KEY` is unset; either key turns the AI features on |
| `SENTRY_DSN` / `SENTRY_ENVIRONMENT` | empty | error tracking; off when blank, never sends PII or request bodies |
| `POSTHOG_PROJECT_KEY` / `POSTHOG_HOST` | empty / EU | product analytics for signed-in workspace users only; the `phc_` project key, never a personal `phx_` key |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`, `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | empty | optional opportunity-network sources; the adapters skip themselves when blank |
| `LICENSE_SIGNING_KEY` | empty | **vendor only** — base64 Ed25519 private key used by `issue_license`; see [Self-hosted licence keys](#self-hosted-licence-keys) |

## Tests and checks
```bash
.venv/bin/ruff check .
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/pytest                                  # full suite (~930 tests)
.venv/bin/python manage.py spectacular --file /dev/null   # schema must be warning-free
```
The suite runs in parallel by default: `addopts = "-q -n auto"` in
`pyproject.toml` fans it out across every CPU with **pytest-xdist**, and
pytest-django gives each worker its own SQLite test database
(`test_<name>_gwN`), so the workers never contend for one file. That takes the
full run from roughly 8½ minutes to under 3½. To debug one test, turn the
fan-out off:

```bash
.venv/bin/pytest video/tests/test_upload_validation.py -n0 -p no:randomly -x
```

Tests run on SQLite and never need `collectstatic`; static files are served by
WhiteNoise, with manifest hashing enabled only outside `DEBUG`/tests
(`python manage.py collectstatic` before a production deploy). Nothing in the
suite touches the network: every external service (Razorpay, Stripe, WhatsApp,
calendars, job boards, transcription, e-sign) sits behind an adapter in
`<app>/gateway.py` that is mocked.

## Invitations

Owners invite teammates from `/settings/members/`: pick an email + role, and the
app stores an `Invitation` with a random token that expires after 7 days and
mails a link to `/accounts/invite/<token>/`. Accepting creates the `Membership`
(signing up first if the invitee has no account). Pending invitations can be
resent or revoked from the same page. With the default console email backend the
link is printed to the server log, which is enough for local testing.

## Pricing tiers

Seeded by a data migration (`billing/migrations/0006_seed_tiers.py`) from
`billing.services.PLAN_SPECS`, so the code is the single source of truth. Yearly
is priced at 10× monthly (two months free). Every new company starts on a
**14-day trial with the AGENCY feature set** and no card.

| | Free (legacy) | Starter | Growth | Agency |
| --- | --- | --- | --- | --- |
| Monthly (INR) | ₹0 | **₹999 per recruiter seat** | ₹4,999 flat | ₹12,999 flat |
| Yearly (INR) | ₹0 | ₹9,990 / seat | ₹49,990 | ₹1,29,990 |
| Success fee per hire | — | ₹4,999 | ₹2,999 | ₹0 |
| Open jobs | 1 | 3 | 25 | 200 |
| Seats | 2 | 3 | 10 | 50 |
| AI screens included / month | 0 | 50 | 500 | 2,000 |
| AI overage | ₹5 per screen beyond the allowance | ₹5 | ₹5 | ₹5 |
| Analytics | — | ✓ | ✓ | ✓ |
| Scheduling, careers page, offers, WhatsApp, contracting | — | — | ✓ | ✓ |
| Client portal, video screening, API, talent pool, marketplace, white-label, integrations, exchange | — | — | — | ✓ |

`Plan.pricing_model` is `SEAT` (STARTER — `price_monthly_inr × seats_used`) or
`FLAT` (GROWTH/AGENCY). **FREE is legacy only**: it stays for existing and
cancelled subscriptions, but a new company is provisioned on STARTER and trials
into the AGENCY entitlements for 14 days. `manage.py expire_trials` then moves it
to STARTER with a **7-day grace window** (`Subscription.grace_until`) during
which `billing.limits.can_open_job` does not enforce plan limits.

Gating is centralised: `billing.entitlements.has_feature(company, "video")` and
the `@require_feature("video")` decorator/mixin, with
`billing.entitlements.plan_for(company)` returning the *effective* plan (the
trial's AGENCY set while the trial is live, the billed plan after).

Metered usage lives in `billing.usage`: `consume(company, kind, qty=1)` records
a `UsageRecord`, and crossing `usage.warn_threshold` (0.8) fires a
`usage_warning` notification. Kinds are `AI_SCREEN`, `WHATSAPP_MSG` and
`VIDEO_MINUTE`. AI screening past `plan.ai_included` is **billed, not blocked**:
the record is flagged `overage` and an `AI_OVERAGE` charge for the period is kept
in step on the ledger. Set `Subscription.hard_cap` to refuse instead
(`QuotaExceeded`); the other kinds still raise past their quota.

## Billing

`billing/` meters **open jobs** per company:

- `Plan` rows (`FREE`, `max_open_jobs=1`; `PRO`, `max_open_jobs=25`) are seeded by
  a data migration.
- Each company gets a `Subscription` lazily (first visit to `/billing/`, a Stripe
  checkout, or `manage.py provision_subscriptions`).
- A `pre_save` signal on `jobs.Job` raises `ValidationError` when a save would push
  the company past its open-job limit. Companies with **no** `Subscription` row are
  never metered, so fixtures and imports predating billing keep working. The web
  job form catches the error and shows an upgrade link.

Stripe env vars (all optional — without them `/billing/` still shows plan and
usage, only upgrade/portal buttons are disabled):

| Var | Where to find it |
| --- | --- |
| `STRIPE_SECRET_KEY` | Stripe dashboard → Developers → API keys (`sk_test_...`) |
| `STRIPE_PUBLISHABLE_KEY` | same page (`pk_test_...`) |
| `STRIPE_PRICE_ID_PRO` | Products → your Pro price (`price_...`), recurring monthly |
| `STRIPE_WEBHOOK_SECRET` | Developers → Webhooks → your endpoint (`whsec_...`) |

Webhook URL: **`https://<your-domain>/billing/webhook/`** — subscribe to
`checkout.session.completed`, `customer.subscription.updated` and
`customer.subscription.deleted`. Requests are signature-verified with
`STRIPE_WEBHOOK_SECRET`; the endpoint is CSRF-exempt and unauthenticated by design.

Test-mode setup:

```bash
stripe login
stripe listen --forward-to localhost:8000/billing/webhook/   # prints whsec_...
# put that value in .env as STRIPE_WEBHOOK_SECRET, restart runserver
```
Then upgrade from `/billing/` and pay with the test card `4242 4242 4242 4242`,
any future expiry and any CVC.

Give every existing company a billing record after deploying billing:

```bash
.venv/bin/python manage.py provision_subscriptions
```
(the container entrypoint runs this automatically after `migrate`).

### Razorpay (INR)

Razorpay is the default gateway when `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET`
are set; `/billing/` falls back to Stripe and then to a read-only plan page.

| Var | Where to find it |
| --- | --- |
| `RAZORPAY_KEY_ID` | Razorpay dashboard → Account & Settings → API keys (`rzp_test_...`) |
| `RAZORPAY_KEY_SECRET` | shown once when the key is generated |
| `RAZORPAY_WEBHOOK_SECRET` | Settings → Webhooks → your endpoint's secret |

Webhook URL: **`https://<your-domain>/billing/razorpay/webhook/`** — subscribe to
`subscription.activated`, `subscription.charged`, `subscription.halted`,
`subscription.cancelled`, `payment.captured`, `payment.failed` and `order.paid`.
The body's HMAC-SHA256 signature is verified against `RAZORPAY_WEBHOOK_SECRET`.

### Webhook idempotency

Both gateways retry deliveries and let you replay events from their dashboards,
so **every event is claimed before it is applied**. `billing.webhooks` writes a
`ProcessedWebhookEvent(provider, event_id)` row — unique together — and a repeat
delivery is logged and dropped instead of issuing a second invoice, placement
fee or reseller commission.

- Stripe: the event's own `event.id`.
- Razorpay: the `X-Razorpay-Event-Id` delivery header when present.
- Neither: `sha256` of the raw request body, which still catches a verbatim replay.

### GST invoicing

`billing.invoicing` issues an `Invoice` on every successful payment:

- **Numbering** is sequential per Indian financial year — `IP/2026-27/0001`,
  rolling over on 1 April. Numbers come from an `InvoiceCounter(fy, last_seq)`
  row locked with `SELECT ... FOR UPDATE` inside `transaction.atomic()`, so two
  simultaneous payments cannot mint the same number and a deleted invoice never
  frees its number for reuse. (SQLite has no row locks but serialises writers
  with a database-level write lock, giving the same guarantee.)
  `invoicing.peek_number()` looks without consuming.
- **Tax** is split by place of supply: equal CGST/SGST halves when the
  customer's state code matches `COMPANY_STATE_CODE`, otherwise IGST, at
  `Invoice.GST_RATE` (18%).
- **PDFs** are rendered from `billing/templates/billing/invoice_pdf.html` with
  xhtml2pdf and stored on `Invoice.pdf`; a rendering failure is logged and never
  blocks the payment. Download at `/billing/invoices/<id>/`.

### Dunning and placement fees

A `PAST_DUE` subscription gets three reminder emails over seven days
(`DunningReminder` rows keep it idempotent) and is then downgraded to FREE —
`manage.py run_dunning`, one of the [periodic tasks](#periodic-tasks). Marking an
application HIRED creates a `PlacementFee` for **every** hire whose plan carries
a success fee (`plan.success_fee_inr`, or the legacy `per_hire_fee_inr`
override), once per application.

### The monthly bill

`billing.invoicing.build_monthly_invoice(company, year, month)` assembles one
invoice per company per calendar month from four sources, stored on
`Invoice.line_items` as `[{kind, label, qty, unit_inr, total_inr}]`:

| Line kind | Where it comes from |
| --- | --- |
| `SUBSCRIPTION` | the plan fee — `seats_used × ₹999` on STARTER, flat elsewhere |
| `SUCCESS_FEE` | one line per `PlacementFee` raised that month (marked INVOICED) |
| `AI_OVERAGE` | AI screens beyond `plan.ai_included`, at `plan.ai_overage_inr` |
| anything else | `BillingCharge` rows pushed in by other apps (BGV, platform fees) |

GST is added with the same `invoicing.gst_split` as one-off invoices, and the
invoice is numbered from the FY counter. The call is **idempotent** — a second
call for the same period returns the invoice already issued (enforced by a
unique `(company, period_start)` constraint) — and returns `None` when the month
has nothing billable.

`manage.py bill_month [--company <id|name>] [--year Y --month M] [--pdf]` runs it
for every metered company; re-running it is a no-op.
`billing.invoicing.projected_bill(company)` returns the same lines for the
running month without writing anything, and drives the "This month so far" card
on `/billing/`.

Any app that needs to put money on a tenant's next bill calls the ledger through
a late import rather than touching billing models:

```python
from billing import ledger

ledger.add_charge(company, ledger.BGV, "BGV — Priya Sharma", 499, ref=f"bgv:{check.pk}")
ledger.add_charge(company, ledger.PLATFORM_FEE, "Exchange platform fee", 1200, ref=f"deal:{deal.pk}")
```

`ref` is an idempotency key scoped to `(company, kind)`: repeating a call updates
the pending charge instead of double-charging, and is ignored once the charge has
been invoiced. `occurred_at` (default now) decides which month picks it up.

## Interview scheduling

`scheduling/` at `/scheduling/`. Interviewers publish weekly
`InterviewerAvailability` windows in their own timezone; entering an INTERVIEW or
HR stage auto-creates a **PROPOSED** `Interview` and mails the candidate a
booking link at `/scheduling/book/<token>/`, which shows computed free slots and
handles reschedule/cancel without a login. Confirmations carry an `.ics`
attachment (also at `/scheduling/interviews/<id>/ics/`).

Calendar sync is env-gated per provider: set `GOOGLE_OAUTH_CLIENT_ID` /
`GOOGLE_OAUTH_CLIENT_SECRET` (and/or `MS_OAUTH_CLIENT_ID` /
`MS_OAUTH_CLIENT_SECRET`) and connect from `/scheduling/availability/`; without
keys the UI says so and scheduling stays manual. Reminder emails 24 h before an
interview come from `manage.py send_interview_reminders`. Feature-gated on
`scheduling` (Growth and up).

## Client portal

`clients/` at `/clients/`. A staffing firm records its own `Client` rows,
attaches an optional `client` to a `Job`, and submits shortlisted candidates. A
`ClientAccess` token gives the client a branded, read-only portal at
`/clients/portal/<token>/` — resume view, AI summary and a feedback form that
sets each `Submission` to SHORTLISTED / REJECTED / INTERVIEW_REQUESTED. Tokens
expire and can be revoked or resent. No keys needed. Feature-gated on
`client_portal` (Agency).

## Notifications

`notifications/` — one entrypoint, `notifications.send(event, recipient, context,
company)`, used by every other app. Channels: email (always), WhatsApp Business
Cloud (`WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID`, and `WHATSAPP_VERIFY_TOKEN` for
the `/notifications/whatsapp/webhook/` handshake) and an SMS stub. WhatsApp sends
consume `WHATSAPP_MSG` usage.

Owners choose channels per event at `/notifications/`; every send is
recorded as an `OutboundMessage` visible at `/notifications/outbox/`, and
failures are retried by `manage.py retry_failed`. Recipients can opt out via
`/notifications/unsubscribe/<token>/`.

## Talent CRM

`talent/` at `/talent/`. Sourced `TalentProfile` rows (unique per company +
email) with resumes, parsed text, skills and tags. Bulk import accepts a zip or
several files at `/talent/import/`, extracts text with
`assessments.resume.extract_text`, pulls name/email/skills with Claude when
`ANTHROPIC_API_KEY` is set (consuming AI credits), and dedupes on email/phone.
Search uses Postgres full-text when available and a LIKE fallback on SQLite.
"Add to job" creates a real `Application`; CSV export at `/talent/export/`.

## Video screening

`video/` at `/video/`. Build a `VideoQuestion` library (think time + answer
time), attach questions to a `VideoScreen` on a job stage, and invite candidates;
each invite is a tokenised recorder page at `/video/take/<token>/` that records
WebM with the MediaRecorder API and posts one answer per question.

Uploads are treated as hostile input: 200 MB cap, and the container is
**sniffed** (`1A 45 DF A3` for WebM, `ftyp` at offset 4 for MP4, mirroring
`jobs/validators.py`) so a file that lies about its type is rejected with
`415`. The billed duration never comes from the client either — `video.validators`
reads the real duration from an MP4 `mvhd` box when that is cheap and otherwise
clamps the reported seconds to `question.answer_seconds + 5`, then consumes that
many `VIDEO_MINUTE` units. Playback for recruiters is range-request streaming at
`/video/responses/<id>/stream/`.

Transcription is env-gated (`VIDEO_TRANSCRIBE_URL`, `VIDEO_TRANSCRIBE_API_KEY`);
without it responses still play and `transcript`/`ai_summary` stay empty.
`manage.py process_video_responses` transcribes and summarises the backlog, and
`manage.py expire_video_invites` closes invites past their deadline.
Feature-gated on `video` (Agency).

## Careers site

`careers/`. Each company gets a `CareersSite` (slug, headline, about, brand
colour, logo, optional custom domain) published at `/careers/<slug>/` — or served
by `Host` header for a custom domain — listing OPEN jobs and reusing the standard
apply flow. Job pages carry `JobPosting` JSON-LD, and there is a sitemap per site
plus a real Indeed XML feed at `/careers/feeds/indeed.xml`. LinkedIn and Naukri
distribution are adapters: with `LINKEDIN_JOBS_TOKEN` / `NAUKRI_API_KEY` unset the
board shows a "connect account" prompt. Uses `SITE_URL` for absolute links.
Feature-gated on `careers_page` (Growth and up).

## Analytics

`analytics/` at `/analytics/` — owner-only, computed at read time (no ETL):
time-to-hire, funnel by stage, source effectiveness, interviewer consistency
(rating variance), offer acceptance and assessment pass rates, filtered by date
range and job. Charts use Chart.js from a CDN; every metric is available as JSON
(`/analytics/metrics/<slug>.json`) and CSV (`/analytics/export/<slug>.csv`).
Feature-gated on `analytics` (Starter and up).

## Offers

`offers/` at `/offers/`. `OfferTemplate` bodies use `{{placeholders}}`; an
`Offer` renders salary, joining date and expiry into stored HTML plus a PDF. The
candidate signs at `/offers/sign/<token>/` — built-in click-to-sign that records
the typed name, IP and timestamp — and accepting marks the application HIRED
(which is what triggers a `PlacementFee`). `manage.py expire_offers` moves past
`expires_at` offers to EXPIRED. An external e-sign provider can be wired with
`ESIGN_API_BASE` / `ESIGN_ACCOUNT_ID` / `ESIGN_API_KEY`. Feature-gated on
`offers` (Growth and up).

## Partners, resellers and white-label

`partners/` at `/partners/`. A `Reseller` has a code and a commission
percentage; `/partners/r/<CODE>/` (or any signup with `?ref=CODE`) drops a
30-day cookie, and the resulting company signup creates a `Referral`.
`manage.py compute_commissions` turns paid invoices into `CommissionLedger`
entries — idempotent per invoice number — and resellers see their own numbers at
`/partners/<code>/dashboard/` with a token link.

`WhiteLabel` (brand name, logo, primary colour, custom domain, hide
"powered by") is applied through a context processor, so an Agency-plan customer
can rebrand the whole UI. Feature-gated on `white_label`.

### Self-hosted licence keys

A self-hosted install needs to check its own licence **offline**, and it also
possesses `SECRET_KEY` — so licence keys are signed with **Ed25519**, not an
HMAC over `SECRET_KEY`. The vendor holds the private key; every install ships
only the public half, embedded as `partners.licensing.LICENSE_PUBLIC_KEY`. A
customer therefore cannot forge a key, and a key issued by the vendor verifies
identically on every install.

Key format: `IPL2.<payload-b64>.<signature-b64>`, payload
`<company_id>|<seats>|<expiry-epoch>|<kind>`.

```bash
# Vendor, once: generate a keypair. Put the public key in partners/licensing.py
# and the private key in your secrets manager — never in the repo.
.venv/bin/python manage.py generate_license_keypair

# Vendor, per customer (needs LICENSE_SIGNING_KEY in the environment):
LICENSE_SIGNING_KEY=<base64-private-key> \
  .venv/bin/python manage.py issue_license --company acme --seats 25 --days 365

# Anywhere, no key and no network needed:
.venv/bin/python manage.py verify_license 'IPL2.…'
```

`LICENSE_SIGNING_KEY` is base64 of the raw 32 private-key bytes and is read
**only** by `issue_license`; leave it unset on customer installs. Without it
signing raises `LicenseSigningUnavailable` (the command exits with a clear
error) while `verify_license` keeps working. `verify_license(key)` returns
`{"valid", "reason", "company_id", "seats", "expires_at", "kind"}` and never
raises — a malformed key is simply invalid. Owners can paste a key into
`/partners/license/verify/`.

To rotate the signing key: generate a new pair, ship the new public key, and
re-issue outstanding licences before the old ones expire.

## Marketplace

`marketplace/` at `/marketplace/`. `QuestionPack` rows (title, skill, price in
INR, questions JSON) are purchased through the Razorpay keys above; a
`PackPurchase` copies the questions into the buyer's own question bank with
`source=MARKETPLACE`. The verified candidate pool at `/marketplace/pool/` is
opt-in per candidate (`CandidateProfile.share_in_pool`) and searches candidates
who have passed an assessment across companies — gated on
`talent_pool_search` (Agency).

## Integrations (Agency)

`integrations/` at `/integrations/`, owner-only and gated on the `integrations`
feature flag. Three things live here: outbound webhooks, HRMS/background-check
connectors, and per-company API keys.

### Outbound webhooks

Create an endpoint at **Integrations ▸ Webhooks**, tick the events you want (or
none, which means *all* events), and we POST a signed JSON body to it. Events:

| Event | Fires when |
| --- | --- |
| `application.created` | a candidate applies |
| `application.stage_changed` | an application moves to another pipeline stage |
| `application.rejected` | an application is rejected |
| `application.hired` | an application reaches HIRED |
| `offer.accepted` | a candidate signs an offer |
| `interview.confirmed` | an interview becomes CONFIRMED |
| `assessment.submitted` | a candidate submits an assessment attempt |

The body is always the same envelope:

```json
{
  "event": "application.hired",
  "occurred_at": "2026-04-01T10:15:00+00:00",
  "company": "acme-staffing",
  "data": { "id": 42, "status": "HIRED", "job": {"id": 3, "title": "Python Developer"}, "candidate": {"email": "asha@example.com"} }
}
```

and carries four headers:

| Header | Meaning |
| --- | --- |
| `X-IP-Event` | the event name |
| `X-IP-Delivery-Id` | delivery row id — use it to make your handler idempotent |
| `X-IP-Timestamp` | unix seconds |
| `X-IP-Signature` | hex HMAC-SHA256 of `"<timestamp>.<raw body>"`, keyed by the webhook secret |

Verify it against the **raw** body, before any JSON parsing or re-serialising:

```python
import hashlib
import hmac
import time

MAX_AGE_SECONDS = 300


def verify(secret: str, request_body: bytes, headers) -> bool:
    timestamp = headers["X-IP-Timestamp"]
    signature = headers["X-IP-Signature"]
    if abs(time.time() - float(timestamp)) > MAX_AGE_SECONDS:
        return False  # replay
    expected = hmac.new(
        secret.encode(), timestamp.encode() + b"." + request_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

The same check ships as `integrations.verify_signature(secret, timestamp, body,
signature, max_age_seconds=None)` if you are running the platform yourself.

**Delivery and retries.** The first attempt is synchronous, with a 5-second
timeout, so a slow or dead receiver never blocks the hiring action that produced
the event. Anything that does not return 2xx is retried by
`manage.py deliver_webhooks` (part of `run_periodic`) after **1 m, 5 m, 30 m,
2 h, 12 h** — five attempts in total, after which the delivery is marked FAILED.
The delivery log at `/integrations/deliveries/` shows every attempt, its
response code and next retry time, with a **Redeliver** button that resets the
counter and tries immediately. **Send test event** on a webhook posts a
synthetic `{"test": true}` payload so you can wire up your receiver before any
real event exists.

Rotating the secret takes effect on the next delivery — update your receiver
first.

### Connectors

Per-company adapters at `/integrations/connectors/`. Settings (`api_key`,
subdomain/domain/data centre, …) are stored **encrypted at rest** with Fernet:
the key comes from `INTEGRATIONS_ENCRYPTION_KEY`, or is derived from
`SECRET_KEY` with HKDF-SHA256 when that is blank. Secrets are write-only in the
UI — the form shows a mask, and submitting the field blank keeps the stored
value.

| Connector | Kind | Needs | Does |
| --- | --- | --- | --- |
| Keka HRMS | `KEKA` | `api_key`, `subdomain` | `POST /employees` on hire |
| Zoho People | `ZOHO_PEOPLE` | `api_key` (OAuth token), `data_center` | `insertRecord` into the employee form |
| greytHR | `GREYTHR` | `api_key`, `domain` | `POST /employee/v2/employees` |
| Background check | `BACKGROUND_CHECK` | `api_key`, `base_url` | `POST /v1/checks` for a candidate |

An adapter with missing credentials reports itself *not configured* and performs
no I/O; **Test connection** returns either that state or the vendor's response.
When an application reaches HIRED, every **active** HRMS connector receives a
`push_hire` with the new-employee record, and each result — ok, skipped or
error — is logged as a `ConnectorRun`. A vendor being down never blocks the
hire.

### API keys

`/integrations/api-keys/` issues one token **per company**, not per person: the
key belongs to a service account `api@<slug>.local` holding a RECRUITER
membership and an unusable password, so it cannot be used to sign in and a
departing employee never breaks the customer's integration. Issuing again
rotates; the plaintext key is shown exactly once. Individual users can still
mint a personal token with `POST /api/v1/auth/token/`.

```bash
curl -H "Authorization: Token <key>" -H "X-Company: acme-staffing" \
     https://app.example.com/api/v1/interviews/
```

`X-Company` picks the tenant (token clients have no session); it is validated
against the caller's memberships.

### Phase-3 API endpoints

All of these require the `api` feature — without it they return 403 with a clear
upgrade message — and are scoped to the resolved company.

| Endpoint | Methods |
| --- | --- |
| `/api/v1/interviews/` | list, retrieve |
| `/api/v1/offers/` | list, retrieve, **POST** (creates a DRAFT — sending stays a human action) |
| `/api/v1/submissions/` | list, retrieve |
| `/api/v1/video-invites/` | list, retrieve (candidate tokens are never exposed) |
| `/api/v1/talent/` | list, retrieve, POST |
| `/api/v1/webhooks/` | full CRUD, plus `POST /{id}/test/`; the secret is returned only on create |
| `/api/v1/exports/hires.csv?from=&to=` | streaming CSV for payroll |

The hires export streams one row per HIRED application in the window
(`from`/`to` are inclusive `YYYY-MM-DD` dates against the application's last
update) with the accepted offer's salary and joining date:

```bash
curl -H "Authorization: Token <key>" -H "X-Company: acme-staffing" \
     "https://app.example.com/api/v1/exports/hires.csv?from=2026-04-01&to=2026-04-30" \
     -o hires.csv
```

Columns: `application_id, candidate_name, candidate_email, candidate_phone,
job_title, job_location, employment_type, client, hired_on, offer_status,
salary, currency, joining_date`.

## Opportunity network

Three apps added in Phase 5 turn the platform into a two-sided network without
scraping anyone who forbids it.

**`sources/`** aggregates public postings: Hacker News hiring threads, Remotive,
Arbeitnow, RemoteOK, Jobicy, Himalayas, WeWorkRemotely, Freelancer.com and ~40
verified company boards on Greenhouse, Lever, Ashby and SmartRecruiters. Reddit
and Adzuna adapters activate when their keys are set. LinkedIn, Upwork, Naukri
and Wellfound are deliberately absent — their terms prohibit it and Upwork's
feed is gone — so those enter only through the seeker's paste form or
bookmarklet. Every lead stores a snippet and a link, never the full posting,
and a contact email only when the poster wrote it. Add a company board in the
admin as a `Source` of kind ATS with `{"slug": "<board-slug>"}`.

```bash
.venv/bin/python manage.py fetch_sources                 # every enabled source
.venv/bin/python manage.py fetch_sources --only hn --only greenhouse-stripe
.venv/bin/python manage.py fetch_sources --no-llm   # first bulk import: keyword tagging only
```

Skill tagging calls the model in batches of 20 and is the slow part of a first
import (thousands of leads means an hour of calls and rate-limit backoff), so
seed with `--no-llm` and let the periodic run tag the trickle of new leads.

**`seeker/`** is the candidate-side workspace at `/portal/opportunities/`: a
feed ranked by skill overlap (falls back to recency for a new profile), a saved
list with bulk apply / open-and-track / draft-emails, AI-drafted outreach, and
a mailbox page. Mail leaves **only** from the seeker's own Gmail (OAuth,
`gmail.send` scope, needs `GOOGLE_OAUTH_*`) or SMTP app password, never from
`DEFAULT_FROM_EMAIL`, so one careless user cannot damage the platform's sending
reputation. One recipient per message, 25 per bulk action, 10 sends a month on
the free tier (`SeekerProfile.is_pro` lifts it; payment wiring is a stub).

**`board/`** is the public cross-tenant job board at `/jobs/board/` with
search, JSON-LD `JobPosting`, `sitemap.xml`, `feed.xml` and one-click apply for
signed-in candidates. Every published careers site is listed unless the tenant
turns off "List on the network" in Careers settings.

## Periodic tasks

Ten maintenance commands keep subscriptions, reminders, offers, video
processing, webhook deliveries and the opportunity-network fetch moving. Run them all with **one** entry point, which executes them in
dependency order and logs a failure instead of letting it stop the rest:

```bash
.venv/bin/python manage.py run_periodic          # all of them
.venv/bin/python manage.py run_periodic --list   # show what would run
.venv/bin/python manage.py run_periodic --only run_dunning
.venv/bin/python manage.py run_periodic --skip compute_commissions
```

| Order | Command | What it does |
| --- | --- | --- |
| 1 | `expire_trials` | Ends 14-day trials and drops companies to their billed plan |
| 2 | `run_dunning` | Sends the 3 past-due reminders over 7 days, then downgrades |
| 3 | `send_interview_reminders` | 24 h interview reminder emails with `.ics` |
| 4 | `expire_offers` | Marks offers past `expires_at` as EXPIRED |
| 5 | `retry_failed` | Retries failed outbound notifications |
| 6 | `process_video_responses` | Transcribes + AI-summarises uploaded answers |
| 7 | `compute_commissions` | Turns paid invoices into reseller commission entries |
| 8 | `expire_video_invites` | Closes video invites past their deadline |
| 9 | `deliver_webhooks` | Retries due webhook deliveries (1 m, 5 m, 30 m, 2 h, 12 h) |
| 10 | `fetch_sources` | pulls new postings from every enabled source, tags skills, expires stale leads (`--only hn` runs one) |

Every command is idempotent, so a missed or repeated run is harmless. Quarter-hourly
is a good cadence:

```cron
*/15 * * * * cd /app && /app/.venv/bin/python manage.py run_periodic >> /var/log/run_periodic.log 2>&1
```

**Fly.io** — the app image already has the code, so schedule a machine instead of
adding a worker process. Either use a Fly scheduled machine:

```bash
fly machine run . --schedule hourly --command "python manage.py run_periodic"
```

or, for finer control, add a second process group to `fly.toml` that loops
(Fly has no built-in cron granularity below hourly):

```toml
[processes]
  app  = "/app/scripts/entrypoint.sh gunicorn"
  cron = "sh -c 'while true; do python manage.py run_periodic; sleep 900; done'"
```

Keep `min_machines_running = 1` for whichever group runs the loop, and note that
`SKIP_MIGRATE=1` applies to it too — migrations run once per deploy from
`release_command`.

**Railway** — add a second service from the same repo with
`startCommand: python manage.py run_periodic` and a cron schedule of
`*/15 * * * *` under the service's *Settings → Cron Schedule*. Railway runs the
container to completion on each tick, so the command must exit (it does).

## Resume parsing and AI re-scoring

`assessments/resume.py` extracts plain text from an uploaded resume (PDF via
`pypdf`, DOCX via `python-docx`, plain text otherwise), caps it at 12k characters
and caches it on the candidate profile, re-parsing only when the file changes.
Both parsers are imported lazily, so a deployment without them still runs — it
just gets less text. The text feeds `assessments.ai.summarize_fit`, which writes
`Application.ai_summary` and `ai_fit_score` when a candidate applies.

Applications created while `ANTHROPIC_API_KEY` was unset have no score. Backfill
them (or re-score after a prompt change):

```bash
.venv/bin/python manage.py rescore_applications --missing-only --all
.venv/bin/python manage.py rescore_applications --company demo-staffing
.venv/bin/python manage.py rescore_applications --job 1
```

## Production checklist

1. `SECRET_KEY` set to a long random value, `DEBUG=False`.
2. `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` (with scheme) point at the real domain.
3. `DATABASE_URL` points at managed Postgres; `CONN_MAX_AGE` left at the default `60`.
4. Object storage configured (`AWS_STORAGE_BUCKET_NAME` + keys) — otherwise resumes
   are lost on every deploy on Fly/Railway.
5. TLS terminated at the edge; `SECURE_SSL_REDIRECT` on (`/healthz/` is exempt).
6. `python manage.py check --deploy` is clean (see below).
7. `migrate` and `provision_subscriptions` run on release; `collectstatic` at build.
8. Stripe live keys + a webhook pointed at `/billing/webhook/`, or leave billing
   in display-only mode.
9. `ANTHROPIC_API_KEY` set if AI screening should be on.
10. A superuser exists (`manage.py createsuperuser`) and `/healthz/` returns `ok`.

`DEBUG=0 SECRET_KEY=<real key> ALLOWED_HOSTS=example.com python manage.py check --deploy`
reports **no warnings**. (Using a short placeholder key raises `security.W009`,
which is about the placeholder, not the configuration.)

## Deployment

The image is a two-stage `python:3.12-slim` build: deps are compiled into a
virtualenv in the builder stage, the runtime stage carries only `libpq5` +
`curl`, runs as the non-root user `app` (uid 10001), runs `collectstatic` at
build time (with a throwaway `SECRET_KEY`, `DEBUG=False`, so manifest hashing
is exercised in CI rather than at boot) and has a `HEALTHCHECK` on `/healthz/`.

`scripts/entrypoint.sh` is the entrypoint: it waits for the database, runs
`migrate`, runs `provision_subscriptions`, optionally runs `seed_demo`
(`SEED_DEMO=1`), then execs gunicorn.
Passing any argument other than `gunicorn` runs that command instead
(`docker compose run --rm web python manage.py createsuperuser`).

| Var | Purpose |
| --- | --- |
| `SEED_DEMO=1` | load demo data after migrating (idempotent) |
| `SKIP_MIGRATE=1` | skip migrations (set on Fly, whose `release_command` migrates) |
| `DB_WAIT_TIMEOUT` | seconds to wait for the DB, default `60` |
| `PORT` | gunicorn bind port, default `8000` |
| `GUNICORN_WORKERS` / `GUNICORN_THREADS` / `GUNICORN_TIMEOUT` | `3` / `2` / `60` |

See the **Production checklist** above before the first deploy; the biggest item
is S3/R2 media storage, since uploaded resumes on local disk are lost on every
deploy on Fly and Railway.

### Local Docker

```bash
cp .env.example .env
# set DATABASE_URL=postgres://interview:interview@db:5432/interview_portal
docker compose up --build
docker compose exec web python manage.py seed_demo   # optional demo data
```
PostgreSQL 16 (healthchecked) plus the app on http://localhost:8000/. Uploads
live on the `media` volume, DB data on `pgdata`.

### Single-host production (docker compose)

```bash
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml up -d --build
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml logs -f web
```
The overlay forces `DEBUG=False`, raises the worker count, sets
`restart: always`, caps log files and binds the app to `127.0.0.1:8000` so a
host reverse proxy (nginx/Caddy/Traefik) terminates TLS in front of it. Point
`ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` at your real domain in `.env`.

### Render + Neon + Cloudflare (recommended)

`render.yaml` is a blueprint for three services from the same image: the web
service, a `run_periodic` cron every 10 minutes, and `bill_month` monthly.
Skipping the cron services means trials never expire, dunning never runs,
reminders are never sent and no invoice is ever raised.

Use the **Starter** plan, not Free: free instances sleep after 15 minutes of
idleness, which breaks server-side assessment timers and drops gateway
webhooks.

1. **Neon** — create the project, then copy the *pooled* connection string
   (the one containing `-pooler`) into `DATABASE_URL`. The direct string
   exhausts connections once several gunicorn workers are running. Create a
   separate Neon branch for staging; never point staging at the main branch.
2. **Cloudflare R2** — create a bucket, then set `AWS_STORAGE_BUCKET_NAME`,
   `AWS_S3_REGION_NAME=auto`, `AWS_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com`
   and the R2 access key pair. Keep the bucket private: resumes are served
   through signed URLs. Add a CORS rule allowing `PUT` from your domain, or
   browser video uploads fail. Render's own disk is wiped on every deploy, so
   this is not optional.
3. **Cloudflare DNS** — proxied `CNAME` to the Render host, SSL mode *Full
   (strict)*. Django already trusts `X-Forwarded-Proto`, so no extra setting
   is needed. Do not enable Cloudflare caching on `/` — authenticated pages
   would be served to the wrong tenant.
4. **Render** — create the blueprint, then paste every `sync: false` secret
   into the dashboard, plus the shared env group used by the cron jobs.
5. **Razorpay** — register the webhook at
   `https://<your-domain>/billing/webhooks/razorpay/` and put its signing
   secret in `RAZORPAY_WEBHOOK_SECRET`. Without it payments are taken but
   never recorded against a subscription.

The blueprint runs `check_deploy` before every deploy, which refuses to start
on a misconfiguration that would otherwise fail silently, such as SQLite in
production, a console email backend or a missing media bucket:

```bash
python manage.py check_deploy              # blocks on real problems
python manage.py check_deploy --warn-only  # report without failing
```

Environment templates for the three environments live in `envs/`. Copy the one
you need and fill it in; the real files are gitignored.

```bash
cp envs/.env.local.example .env
```

### Fly.io

`fly.toml` is checked in: region `bom`, `release_command` runs migrations
before new machines take traffic, `http_service` health-checks `/healthz/`,
`force_https` on.

```bash
fly launch --no-deploy --copy-config --name interview-portal --region bom
fly postgres create --name interview-portal-db --region bom
fly postgres attach interview-portal-db          # injects DATABASE_URL
fly secrets set SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(50))')"
fly secrets set ANTHROPIC_API_KEY=sk-ant-...     # optional; unset = AI disabled
fly deploy
fly ssh console -C "python manage.py createsuperuser"
```
If you pick a different app name, update `app`, `ALLOWED_HOSTS` and
`CSRF_TRUSTED_ORIGINS` in `fly.toml`. Resume uploads need object storage — set
the S3/R2 vars (see the env table) as secrets, or (single machine only)
uncomment the `[[mounts]]` block and `fly volumes create media`.

### Railway

`railway.json` builds from the `Dockerfile` and starts via the entrypoint, with
the health check on `/healthz/`.

```bash
railway login
railway init                     # or `railway link` to an existing project
railway add --database postgres   # injects DATABASE_URL
railway variables --set SECRET_KEY=... --set DEBUG=False \
  --set ALLOWED_HOSTS=<service>.up.railway.app \
  --set CSRF_TRUSTED_ORIGINS=https://<service>.up.railway.app
railway up
```
Use the private `*.railway.internal` Postgres URL to avoid egress charges.
Railway's filesystem is ephemeral, so configure S3/R2 media storage.

### CI/CD

`.github/workflows/ci.yml` lints and tests every branch.
`.github/workflows/deploy.yml` runs on pushes to `main`: ruff, `check --deploy`,
`makemigrations --check`, pytest and `collectstatic`, then `flyctl deploy`. The
deploy job is **skipped** unless the `FLY_API_TOKEN` repository secret exists,
so the workflow is safe to merge before you have a Fly account:

```bash
fly tokens create deploy -x 999999h     # paste into Settings > Secrets > FLY_API_TOKEN
```

Legacy v1 code lives in `legacy/` and is excluded from lint/tests. Do not import from it.

## Accounts, sessions and errors

- **Emails are the username and are case-insensitive.** They are stored lower-cased
  (`UserManager.create_user`, `User.save`, the signup forms and `Invitation`), a
  data migration lowers pre-existing rows (collisions are skipped and logged), and
  `core.backends.CaseInsensitiveEmailBackend` matches legacy mixed-case rows.
- **Logout is POST-only.** `GET /accounts/logout/` renders a confirmation page;
  every "Sign out" control in the UI posts a form.
- **The active workspace sticks.** `User.last_company` records the last tenant a
  user had active; `TenantMiddleware` falls back to it before the first membership,
  so a re-login lands back in the same workspace. Switching companies and accepting
  an invitation update it.
- **HTMX**: `base.html` puts `hx-headers='{"X-CSRFToken": ...}'` on `<body>`, so bare
  `hx-post` buttons need no per-element token. `core.middleware.HtmxRedirectMiddleware`
  turns a login redirect on an `HX-Request` into `204` + `HX-Redirect`, so an expired
  session sends the browser to the login page instead of swapping a login form into a
  fragment.
- **Error pages**: branded `400/403/404` templates extend `base.html`;
  `500.html` is deliberately standalone (no context processors, no DB, no manifest).

## Background verification (BGV)

Resold background checks, feature flag `bgv` (GROWTH and AGENCY). The app lives in
`bgv/` and is mounted at `/bgv/`.

**Packages** (`bgv.models.CheckPackage`, seeded by `bgv/migrations/0002_seed_packages.py`):

| Package | Checks | Price | Vendor cost | Margin |
|---|---|---|---|---|
| Basic | identity, address | ₹799 | ₹499 | ₹300 |
| Standard | + employment, education | ₹1,499 | ₹999 | ₹500 |
| Comprehensive | + criminal | ₹2,999 | ₹1,999 | ₹1,000 |

**The flow** — the ordering is the product:

1. A recruiter opens a candidate's application and picks a package
   (`bgv:order_create`, takes an `application_id`). The order snapshots both the
   price *and* the vendor cost, so a later re-price never restates history.
2. The order sits in `CONSENT_PENDING` and the candidate is emailed a tokenised
   consent link (`bgv:consent`, `core.tokens.TokenMixin`, 14-day expiry).
   **Nothing is billed yet** — cancelling here is free.
3. The candidate reads what will be checked, ticks a box and types their name.
   Consent records the name, timestamp and IP.
4. On consent, and only then, the company is charged via
   `billing.ledger.add_charge(company, ledger.BGV, …, ref="bgv:<order id>")`.
   The ref is an idempotency key: a double-submitted form bills once.
5. The order is submitted to the provider adapter; results land per check
   (`CLEAR` / `DISCREPANCY` / `UNABLE`) and completion generates a PDF report
   (xhtml2pdf) available from the order page.

**Providers.** `bgv/gateway.py` follows the house adapter contract. With
`BGV_API_KEY` blank — the default and every test — `MockProvider` is used: it
accepts submissions and advances an order one step per poll, so
`manage.py bgv_poll` walks orders `SUBMITTED → IN_PROGRESS → COMPLETED` with all
checks clear and the whole flow is demoable with no vendor account. Add
`bgv_poll` to `run_periodic` in production. `AuthBridgeLikeProvider` is the shape
a real vendor takes and deliberately raises `NotConfigured` for every call until
someone writes it against a real contract.

**Webhook.** `POST /bgv/webhook/` is csrf-exempt and verifies an HMAC-SHA256 of
the raw body (header `X-BGV-Signature`) against `BGV_API_KEY`; a bad or missing
signature is a flat `400`, and an install with no key rejects every webhook.

**Margin** (price − vendor cost) is platform-staff information: `/bgv/admin-margin/`
is `is_staff`-only and tenant screens never render `provider_cost_inr`.

**Candidate screen integration.** This app ships
`bgv/templates/bgv/partials/candidate_checks.html` rather than editing `web/`.
Include it from the candidate detail page with:

```django
{% include "bgv/partials/candidate_checks.html" with bgv_orders=candidate.verification_orders.all application=application %}
```

## Salary benchmarks

Read-time compensation benchmarks built from accepted offers (`benchmarks/`,
mounted at `/benchmarks/`, gated on the `analytics` feature and an
OWNER/RECRUITER role). Nothing is stored: `benchmarks.metrics` derives every
number from `offers.Offer` rows in `ACCEPTED` status — the only pay figure on the
platform someone actually agreed to.

- **Annualisation**: an offer is read in the period its job quotes; `MONTH` × 12,
  `YEAR` as-is. Non-INR offers are dropped rather than converted.
- **Percentiles**: p25/median/p75 by linear interpolation between ranks (the
  numpy "linear" definition) — for `n` sorted values, index `p*(n-1)`.
- **k-anonymity**: any cell computed from fewer than `MIN_N` (default 5,
  settable with `BENCHMARKS_MIN_N`) offers is returned with `n` but no numbers,
  so one tenant's pay cannot be read out of an aggregate. The public teaser at
  `/benchmarks/public/` raises the bar to 20 and publishes medians only.
- **Experience bands**: 0-2, 3-5, 6-9, 10+ from `CandidateProfile.experience_years`.
  **City** is the text before the first comma of `Job.location`.

`salary_bands(skill, city, experience_band, period_months)` returns one row per
skill; `company_vs_market(company)` puts a tenant's own median next to the market
median per skill (own numbers are never suppressed — they are its own data; the
market column is). The report page offers a Chart.js spread chart (analytics
dataviz palette, `analytics/_viz_style.html`), a CSV export and a branded
"Quarterly Compensation Snapshot" PDF.

Seed publishable data with:

```bash
python manage.py benchmarks_seed_demo          # ~48 accepted offers, 3 skills, 2 cities, 2 companies
```

It is idempotent and creates a second company so market cells are never one
tenant's data.
