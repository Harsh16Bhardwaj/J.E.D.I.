# Resume onboarding and interview practice

The onboarding page keeps all manual preferences and adds an optional PDF upload.
A member reviews extracted facts and saves them independently of the group ranking
profile. Resume review appears first; saved explicit skills and exact experience
are reused for onboarding, with manual fields shown only when those facts are
missing. Inferred skills are not silently promoted to explicit skills. Job details now offer **Compare skills**. The **Learning** page recommends
available question banks for missing skills and provides a general practice library.

The library includes React Rendering and Keys, Python Fundamentals, FastAPI
Fundamentals, and SQL Fundamentals. Each bank has three questions: one easy, one
medium, and one hard, with per-option explanations.

Batch normalization and ranking use the active profile and model referenced by
the member’s group. Global active flags belonging to another group do not select
these contracts. After deploying this correction, normalize previously affected
batches again before requesting ranking.

## Runtime and deployment

Install the updated Python dependencies (`pip install -e 'backend[dev]'` in the
Python 3.12 environment), and build the frontend with Node 22 and `npm ci` / `npm run build`.
The PDF dependency is `pypdf>=6.12,<7`.

Prisma and SQLAlchemy define `ResumeEvidence` and `LearningAttempt`, linked to
`GroupMember`. The reviewed migration is
`prisma/migrations/20261102000000_resume_learning/migration.sql`. It creates only
the two new tables, indexes and ownership foreign keys; it does not rewrite or
remove existing records. It is transactional, uses a five-second lock timeout,
and enables RLS with no direct `anon` or `authenticated` table access.

Before applying it, verify the target database and migration checksums, take a
protected backup, and test restoration plus migration against a disposable
PostgreSQL copy. Inspect pending migrations and use `prisma migrate deploy`
only when the reviewed migration is the intended pending change. Never use
`prisma migrate dev`, `prisma db push`, or a reset command against production.
Existing records do not need backfilling.

Four historical scraper migrations are retained unchanged from the existing
scraper branch because they were already applied to the production database.
Their restored files reconcile migration history; they are not new scraper
features and must not be reapplied to an already-migrated database.

Keep the question JSON files in the deployed Python package. `backend/pyproject.toml`
includes `content/*.json` as package data. PDF extraction runs in a short-lived
Python subprocess with a 15-second wall-clock limit, a Unix CPU limit, and a Linux
512 MB address-space limit. Ensure the Python deployment permits subprocesses.
Original PDFs are processed in memory and are not persisted by the application.

## Extraction scope

Upload limits: a real PDF signature, up to 5 MB, 1–10 pages, no encryption. Scans
without extractable text are reported as unreadable, rather than being labeled
non-resumes. Other readable documents must pass contact and populated resume-section
checks. PDF classification is heuristic, not a guarantee that every document can
be correctly classified. See the [pypdf extraction documentation](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

The initial local extractor recognizes common English section headings, a finite
technology vocabulary, explicitly labeled current location, and month/year work
dates. It retains summary, contact details, work history, education and projects as
source-derived text. Missing fields remain unknown. Work intervals merge overlaps;
year-only dates do not yield an invented duration. Inferred skills include an
explanation and stay separate from explicit mentions. Review the extraction notes
and correct the fields before saving. Preferences are never inferred from a resume.

The skill parser recognizes aliases and common required/preferred/negated wording.
Ambiguous mentions and normalized job tags are labeled **Confirm requirement**.
Matching inferred skills are tentative. Personal evidence does not replace shared
ranking profiles or change either model's scores.

## Question banks

The initial bank is the supplied three-question `backend/content/react-rendering.json`.
No other question banks are fabricated. Missing skills without content display
**Question bank unavailable**.

To add content, place a schemaVersion 1 JSON file in `backend/content/` and register
its canonical skills in `TOPIC_SKILLS` in `backend/services/learning.py`. Restart
the API after content changes. Add tracks in prerequisite order when extending
that registry. The application validates IDs, answer references, question counts,
difficulty distribution, nonempty prompts and explanations, and 2–10 options per
question. Each attempt snapshots its questions so later content changes cannot
alter existing grading. The content file retains the exact supplied shape;
API responses hide answers and option explanations until the answer is committed
or the sprint ends.

Members choose 1–200 questions (bounded by the bank) and a duration of 30–3600
seconds; the UI offers common durations. The server owns deadlines and grading.
Submitted answers are immutable; replaying the same answer is idempotent. Expired
attempts reject answers and report unanswered questions. Results and the latest
50 attempts remain private to the member; completed attempts are practice records,
not claims of mastery. Refreshing or returning later allows an active sprint to be
resumed from history with the original deadline.

## APIs

- `POST /api/resume/extract`: multipart `file`; returns unsaved reviewable evidence.
- `GET /api/resume`, `PUT /api/resume`: member-private reviewed evidence.
- `GET /api/jobs/{jobId}/skill-gap`: matched and missing skills with source labels.
- `GET /api/learning/topics`: metadata only, no answer keys.
- `GET /api/learning/attempts`, `POST /api/learning/attempts`: history and creation.
- `GET /api/learning/attempts/{id}`: resumable state, with answer visibility rules.
- `POST /api/learning/attempts/{id}/answers`: questionId and optionId.
- `POST /api/learning/attempts/{id}/finish`: idempotent finish and results.

All routes require an authenticated group member. Attempt IDs never grant access
to another member's state. Resume and learning tables are independent of manual
onboarding and existing ranking models.

## Groq answer tutor

After each successful answer submission, a Groq explanation loads automatically
without blocking grading or the next question. Follow-up questions are available
below it. Existing answers reviewed later offer **Ask AI about this answer**
without automatically repeating provider requests. Grading remains
entirely based on the question bank. The server loads the owned attempt snapshot
and selected answer; clients cannot supply a replacement answer key. Only the
current question, selected answer and up to six recent conversation messages go
to Groq. Resumes, contact details, job profiles and other questions are excluded.
Conversations remain in the current view and are not persisted to practice history.

Set `GROQ_API_KEY` in the backend environment (locally in the untracked root `.env`,
and in Vercel's backend environment for production/preview as needed). Never use
a `NEXT_PUBLIC_` variable for the key. Redeploy after changing deployment variables.
`GROQ_MODEL` defaults to `llama-3.3-70b-versatile` and can be overridden. This uses
Groq's [Chat Completions API](https://console.groq.com/docs/api-reference).
No database migration or new dependency is required. Missing configuration or a
provider failure leaves the saved answer and built-in explanations available.
