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

| | Free | Starter | Growth | Agency |
| --- | --- | --- | --- | --- |
| Monthly (INR) | ₹0 | ₹1,499 | ₹4,999 | ₹12,999 |
| Yearly (INR) | ₹0 | ₹14,990 | ₹49,990 | ₹1,29,990 |
| Open jobs | 1 | 3 | 25 | 200 |
| Seats | 2 | 3 | 10 | 50 |
| AI credits / month | 0 | 50 | 500 | 2,000 |
| Analytics | — | ✓ | ✓ | ✓ |
| Scheduling, careers page, offers, WhatsApp | — | — | ✓ | ✓ |
| Client portal, video screening, API, talent pool, marketplace, white-label | — | — | — | ✓ |

Gating is centralised: `billing.entitlements.has_feature(company, "video")` and
the `@require_feature("video")` decorator/mixin, with
`billing.entitlements.plan_for(company)` returning the *effective* plan (the
trial's AGENCY set while the trial is live, the billed plan after).

Metered usage lives in `billing.usage`: `consume(company, kind, qty=1)` records
a `UsageRecord` and raises `QuotaExceeded` past the plan's allowance, and
crossing `usage.warn_threshold` (0.8) fires a `usage_warning` notification.
Kinds are `AI_SCREEN`, `WHATSAPP_MSG` and `VIDEO_MINUTE`.

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
application HIRED creates a `PlacementFee` when the plan carries a per-hire fee.

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

## Periodic tasks

Eight maintenance commands keep subscriptions, reminders, offers and video
processing moving. Run them all with **one** entry point, which executes them in
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
