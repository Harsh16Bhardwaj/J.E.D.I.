# JEDI

JEDI is an invite-only group job-discovery and application command center. Next.js renders
the dashboard, FastAPI owns every product API and database call, Prisma defines
and migrates PostgreSQL, and `ML/` preserves the ranking experiments.

## Repository structure

```text
JEDI/
├── frontend/        Next.js dashboard; no direct database access
├── backend/         FastAPI, SQLAlchemy, auth, batch workflow, ML boundary
├── prisma/          PostgreSQL schema and future migrations
├── ML/              Datasets, notebooks, results, and future model bundles
├── archive/         Previous vanilla screener
├── package.json     npm workspace and repository commands
├── prisma.config.ts Prisma migration configuration
└── vercel.json      Frontend and Python service routing
```

The root `package.json` is the npm workspace control panel. Python dependencies
remain independent in `backend/pyproject.toml`.

## Requirements and setup

- Node.js 22
- npm 11
- Python 3.12
- A PostgreSQL/Neon development URL before any migration or database API test

From `D:\ML\JEDI`:

```powershell
Copy-Item .env.example .env
npm install
npm run setup:api
npm run db:validate
```

Replace `DATABASE_URL` and `DIRECT_DATABASE_URL` only when an approved
development database is ready. Do not run a migration against the placeholder.

### Create the first group owner

Set `OWNER_REGISTRATION_CODE` to a private, static value containing at least 12
letters and numbers. It must be configured on the backend before its first
startup. The owner enters that code on `/register`; the backend atomically
creates the first user, the JEDI group, and its owner membership.

When that first owner completes onboarding, the submitted member profile also
becomes the initial active immutable shared profile. Later member onboarding
remains private and never replaces the profile used for group normalization.

The owner code is not stored in PostgreSQL and is never returned by the API.
Ordinary member invitations are exactly five characters, so a 12+ character
owner code can never be emitted by their random generator. After the first group
has been created, the reserved code permanently returns `OWNER_ALREADY_CLAIMED`.

The trusted interactive fallback remains available:

```powershell
npm run user:bootstrap
```

Both paths normalize the email and store only an Argon2 password hash. Login
sets an HTTP-only signed cookie. There is intentionally no password-reset flow.

## Start the servers

Start both:

```powershell
npm run dev
```

Or use separate terminals:

```powershell
npm run dev:web
```

```powershell
npm run dev:api
```

Useful local URLs:

| URL | Purpose |
| --- | --- |
| `http://localhost:3000` | Next.js dashboard |
| `http://localhost:3000/api/health` | Frontend health |
| `http://localhost:8000` | FastAPI metadata |
| `http://localhost:8000/docs` | Interactive API documentation |
| `http://localhost:8000/health/live` | Python process health |
| `http://localhost:8000/health/ready` | Database and migration readiness |
| `http://localhost:8000/api/auth/login` | Private login |
| `http://localhost:8000/api/batches` | Batch ingestion and active list |
| `http://localhost:3000/scraper` | Owner-only manual ATS scraper |

On the configured Vercel service, Python paths are available under `/svc/ml`;
for example `/svc/ml/api/batches`.

### Manual scraper setup

The owner-only `/scraper` workspace ships with employer-direct Greenhouse,
Lever, Ashby, Workable, and SmartRecruiters boards. V2 also detects Recruitee,
Personio XML, selected public Workday career sites, and employer `JobPosting`
JSON-LD pages. The manual **Refresh sources** run follows career links from the
configured company registry, validates employer identity and direct vacancies,
and activates only healthy unique boards. These direct sources do not require
Bright Data.

Collection targets 60 trustworthy jobs, automatically selecting only verified
postings from the last 14 days. Updated or uncertain evidence up to 30 days old
is retained for owner review, while stale, closed, non-India, senior, incomplete,
or duplicated postings are rejected. `backend/scraper_taxonomy.toml` versions
the deterministic skills, experience, employment, education, authorization,
and compensation extraction rules; evidence spans remain attached to each
candidate for audit.

Bright Data is optional and fallback-only. Direct ATS polling never uses SERP;
Web Unlocker is used only when a shortlisted detail page is blocked or lacks a
required description/date and its separate zone is configured:

```text
BRIGHT_DATA_API_KEY=...
BRIGHT_DATA_SERP_ZONE=...
BRIGHT_DATA_UNLOCKER_ZONE=...
```

Leaving either zone blank is supported. `BRIGHT_DATA_SERP_ZONE` is retained for
deployment compatibility but is not used by the scraper workflow. An API key
without an Unlocker zone cannot spend Bright Data credits and does not prevent
seeded ATS runs.

Approved scraper jobs are imported and automatically normalized with audited
annual INR compensation when a supported FBIL reference rate is available.
Ranking and email remain separate explicit actions.

Keep those values in deployment environment variables; do not add them to
`backend/scraper.toml` or PostgreSQL. Before using the scraper in an existing
environment, apply the committed migration with `npm.cmd run db:deploy`. Never
use `prisma db push` for JEDI deployments.

## Try the API

PowerShell keeps the session cookie in a web session:

```powershell
$jedi = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$login = @{
  email = "you@example.com"
  password = "your-password"
} | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/auth/login `
  -WebSession $jedi `
  -ContentType "application/json" `
  -Body $login
```

Import one JSON file without any application-level body or job-count limit:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/batches `
  -WebSession $jedi `
  -ContentType "application/json" `
  -Body (Get-Content -Raw .\sample-batch.json)
```

Use `http://localhost:8000/docs` to exercise the remaining routes. Browser
requests use the login cookie; scripts may send that same token as
`Authorization: Bearer <token>`.

List endpoints use a consistent page envelope:

```json
{
  "items": [],
  "page": 1,
  "pageSize": 50,
  "total": 0
}
```

Errors use `error.code`, `error.message`, and the response `requestId`, making
individual endpoint assertions stable without matching internal exceptions.

## Implemented Python routes

Authentication:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/session`

Group access:

- `POST /api/invitations`
- `GET /api/invitations`
- `DELETE /api/invitations/{invitationId}`
- `GET /api/onboarding`
- `POST /api/onboarding`
- `GET /api/group`

Batch ingestion and review:

- `POST /api/batches`
- `GET /api/batches`
- `GET /api/batches/all`
- `GET /api/batches/{batchId}`
- `DELETE /api/batches/{batchId}`

Workflow:

- `POST /api/batches/{batchId}/normalize`
- `PATCH /api/jobs/{jobId}/annotation`
- `PATCH /api/batches/{batchId}/annotations`
- `POST /api/jobs/{jobId}/view`
- `PATCH /api/jobs/{jobId}/state`
- `GET|PATCH /api/jobs/{jobId}/application`
- `POST|GET /api/jobs/{jobId}/application-events`
- `POST /api/jobs/{jobId}/application-milestones`
- `PATCH /api/jobs/{jobId}/application-milestones/{milestoneId}`
- `GET /api/applications`
- `GET /api/applications/summary`
- `POST /api/batches/{batchId}/training-examples`
- `GET /api/training-examples/export.csv`
- `POST /api/batches/{batchId}/rank`
- `POST /api/batches/{batchId}/rankings`
- `GET /api/batches/{batchId}/rankings`
- `GET /api/batches/{batchId}/processing-runs`
- `POST /api/batches/{batchId}/email-digest`
- `GET /api/batches/{batchId}/email-deliveries`
- `POST /api/email/manual-dispatch` (initialized; ranked-batch selection pending)

Jobs and rankings are shared by the v1 group. Viewed state, review status,
annotations, application planning, events and milestones are private to the
authenticated member. Training import, export and annotation promotion remain
group-owner operations because they change the shared model dataset.

Model metadata:

- `POST /api/models`
- `GET /api/models`
- `GET /api/models/{modelId}`
- `POST /api/models/{modelId}/activate`

Internal worker control (requires `X-JEDI-SERVICE-TOKEN`):

- `POST /internal/processing-runs/claim`
- `POST /internal/processing-runs/{runId}/heartbeat`
- `POST /internal/processing-runs/{runId}/fail`
- `POST /internal/batches/{batchId}/rankings`
- `GET /internal/email-deliveries/run` (`CRON_SECRET` Bearer authentication)

Email is off by default. To enable the top-ten digest, set `EMAIL_ENABLED=true`
and provide the Gmail SMTP user, Gmail app password, recipient, sender name, and
an independent 32-character-or-longer `CRON_SECRET`. Ranking success is never
rolled back when SMTP delivery fails; delivery history records the safe failure
and the 12:00 AM IST cron retries eligible rows.

`POST /api/batches/{batchId}/rank` intentionally queues pending execution and
does not invent scores. Real model results are accepted by the rankings route.
Embedding and direct scoring routes remain explicit `501` placeholders.

## Validation

Targeted checks:

```powershell
npm run db:validate
npm run test:api
npm run lint:api
npm run lint
npm run typecheck
```

Run the production frontend build once after integrated changes:

```powershell
npm run build
```

No database migration is created or executed without an approved PostgreSQL URL.
Use `npm run db:migrate` only for development migrations and
`npm run db:deploy` in production. Never use `prisma db push` for production.
