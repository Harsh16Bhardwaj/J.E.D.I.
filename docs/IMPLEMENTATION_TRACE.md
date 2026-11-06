# Implementation trace

Each entry ships in the commit it describes. Use `git log -- docs/IMPLEMENTATION_TRACE.md` to find the matching commits.

## Protect group member emails and dispatch controls

**Working**

- The directory returns names and neutral placeholders. Members can update their own display name, and their own email remains available through their session.
- The API requires the group owner for email settings, recipients, event history, and manual sends, including legacy batch digest routes. Member navigation and direct page access hide dispatch controls.
- The browser clears the old refresh cache and excludes email administration responses from new persisted cache entries.

**Verified**

- 17 group and email backend tests, including anonymous, owner, and member access checks, plus 31 frontend tests and TypeScript checking.

**Open**

- Apply the display-name migration before deploying. Browser role-switch validation and member-specific newsletter preferences remain open.
- Application transition protection, private draft tracking, broader fit scoring, and unattended scraper execution remain on the roadmap.

## Protect application stage changes

**Working**

- The board, job detail, and quick-start flows send an expected stage and a retry ID. The board and job detail also send the record timestamp they opened.
- Repeating the same request returns the original event. A stale snapshot or reused ID with different contents returns a conflict.
- Backward moves and reopening require a reason in the updated UI and are recorded as corrections. The Not started filter displays planning records.

**Verified**

- Nine targeted application and member backend tests, 31 frontend tests, type checking, and targeted lint.

**Open**

- Older API callers can still submit the legacy move payload. Private drafts are not yet linked into the board, and milestone-triggered transition suggestions remain open.

## Add workflow guides and chapter progress

**Working**

- The feature catalog provides routes, audiences, prerequisites, and steps for intake, resume comparison, application moves, scraper recovery, and email dispatch.
- Each workflow links to its guide. The tutorial shows owner chapters only to owners and includes a sample posting for intake.
- Device-local chapter progress is tracked independently. A completed legacy field guide still counts as core completion.

**Verified**

- 32 frontend tests, including chapter compatibility, plus TypeScript checking and targeted lint.

**Open**

- Chapter progress is device-local. Account sync and rollout metrics remain open.

## Add resume retention controls and documented fit scoring

**Working**

- Members can preview pasted resume text, save reviewed evidence, and delete their own saved evidence. Resume and skill-gap responses stay out of browser refresh storage.
- Draft comparison reports a versioned documented-fit score when required evidence can be evaluated. When a role-wide minimum is listed and resume years are available, required skills contribute 80 points and total years contribute 20. Otherwise, a score without a listed minimum uses direct required-skill evidence alone.
- Required findings needing review and unknown experience against a listed minimum hold the score. The report flags a reviewed total below the minimum separately.

**Verified**

- 21 resume, learning, and draft-fit backend tests and 32 frontend tests. Tests cover text preview, cross-member deletion isolation, scoring weights, and uncertainty.

**Open**

- Seniority and domain alignment, versioned report snapshots, calibration fixtures, and DOCX intake remain open.
- Private drafts on the application board and automatic milestone moves remain open.
- Broader employer-site coverage and unattended scraper execution remain open.

## Track private job drafts in Applications

**Working**

- A saved private draft can start a Preparing application. Its card links back to the saved description, reviewed requirements, and current resume comparison.
- Draft applications share the stage and correction rules used by the main pipeline. Moves use a revision and request ID. Retries preserve history, and a backward move or reopening requires a reason.
- Only the draft owner can read or move its application. Deleting the draft removes its application and history.

**Verified**

- 15 targeted intake, fit, and application API tests plus 32 frontend tests. The new API test covers duplicate starts and moves, stale revisions, required correction notes, member isolation, and deletion.
- TypeScript, lint for the changed files, and Prisma schema validation passed. Repository-wide Ruff still flags fixture imports in the existing learning API tests.

**Open**

- Apply the private draft application migration before deploying. Unified filters, saved fit reports, and confirmed milestone moves remain open.

## Preview and review Word resumes

**Working**

- A DOCX upload follows the same private preview and explicit save flow as PDF and pasted text. The app discards the uploaded file after extraction.
- The isolated worker reads bounded Word body text. It rejects malformed, macro-enabled, and oversized packages and blocks XML declarations that could define entities. Worker JSON uses portable encoding for non-ASCII resume text.

**Verified**

- 29 resume and learning tests. The new tests cover Word and text evidence parity, malformed ZIPs, macro-enabled files, XML entities, decompression limits, and a private API preview followed by an explicit save.
- Repository-wide backend Ruff, targeted frontend ESLint, TypeScript, and the production frontend build passed.

**Open**

- DOCX reads body text, including table paragraphs. Header and footer text, images, and complex Word layouts can still require pasted text or manual review.
- Fit report snapshots, seniority and domain alignment, and calibration against labeled examples remain open.

## Advance applications from confirmed milestones

**Working**

- From Preparing, members can confirm that they submitted a shared-catalog application and record the Applied stage and submission timestamp.
- Confirming a screening, assessment, or interview can move the application to the corresponding forward stage. Saving a round alone leaves the stage as it was.
- The stage and milestone commit together. Replaying the request returns the saved milestone, and a stale or backward move leaves both records unchanged.

**Verified**

- Eight targeted application tests, including milestone-only saves, a confirmed move, retries, stale state, backward moves, and member isolation. Backend Ruff, targeted frontend ESLint, and TypeScript passed.
- The 23-migration chain and six PostgreSQL integration and concurrency checks passed on an isolated local database.

**Open**

- Confirmed milestones are available for applications from the shared catalog. Private draft milestones, provider-inferred suggestions, and resume version filters remain open.

## Advance approved scraper imports outside the browser

**Working**

- An internal worker can advance one already-approved import checkpoint through `POST /api/scraper/internal/import-tick` with the configured `X-JEDI-SERVICE-TOKEN`. An owner session alone cannot call the worker.
- Each call processes the oldest available import or normalization checkpoint. PostgreSQL skips runs locked by another worker or browser request. The same checkpoint code and batch key handle both entry points.
- The worker returns the run ID, current status, and linked batch ID, or `null` when the queue is empty. Collection and ranking remain separate owner actions.

**Verified**

- All 14 scraper API tests passed, including worker authorization, the owner approval boundary, and ingest and normalization after owner logout. Backend Ruff passed.

**Open**

- Connect a scheduler or worker service to the internal endpoint to run imports unattended in a deployment. The browser still advances checkpoints when open.
- Background collection and discovery, live employer coverage, and a timed PostgreSQL race test for browser and worker requests remain open.

## Save a private baseline for resume fit

**Working**

- Each private draft can keep one saved fit comparison. It preserves the inputs and scored findings from the reviewed draft and resume, with the draft revision, resume review date, and scorer version.
- Members can revisit the saved result after editing the draft or resume, compare again, and explicitly replace or delete the baseline. The API checks the live inputs and the expected baseline before replacing it.
- Deleting a draft or the underlying resume evidence removes its saved comparison. Raw saved inputs remain server-side and responses stay out of browser refresh storage.

**Verified**

- 10 intake and fit tests, including immutable findings after resume edits, replay, stale replacement and deletion, cross-member isolation, and resume deletion.
- 184 backend tests passed, including the PostgreSQL checks. All 24 migrations were applied to the isolated test database. The 32 frontend tests, frontend production build, and lint passed.

**Open**

- Apply the fit snapshot migration before deploying. Per-draft comparison history, seniority and domain alignment, and score calibration remain open.

## Read current SmartRecruiters postings and expand employer coverage

**Working**

- Private intake accepts public SmartRecruiters posting links and resolves the numeric ID through the fixed provider API. Closed or internal postings have the same paste fallback as other unavailable links.
- Single-job intake and batch collection both read the provider's nested job description and qualifications. The batch adapter requests public listings explicitly. [SmartRecruiters Posting API](https://developers.smartrecruiters.com/docs/endpoints)
- Experian and Coface are available as seeded boards. The roadmap lists the supported single-job URL shapes.

**Verified**

- 35 job-link and scraper service tests, including public and internal posting handling, qualification extraction, and the batch adapter's experience range. TypeScript and lint passed.
- Live public API previews returned readable descriptions and extracted requirements from one ServiceNow, Experian, and Coface posting.

**Open**

- Employer coverage beyond the four supported single-job URL providers, scheduler deployment for approved imports, and unattended source discovery and collection remain open.
- Fit calibration and seniority/domain alignment, synchronized guide progress, and shared filters across catalog and private applications remain open.

## Verify SmartRecruiters public pagination and branch readiness

**Working**

- The pagination regression test parses query parameters by name. It verifies the saved offset and public-only destination on each page, regardless of parameter order.

**Verified**

- 186 backend tests passed, including the PostgreSQL integration and concurrency tests. The isolated database used all 24 migrations.
- All 32 frontend tests, the production build, backend Ruff, frontend lint, and Prisma schema validation passed.

**Open**

- Apply the new migrations in the target deployment and connect the scraper import scheduler. Live browser verification against the target deployment, additional provider coverage, and the remaining fit and application roadmap items are pending.

## Verify competing scraper import requests on PostgreSQL

**Working**

- The race regression test holds the worker's ingestion claim while the owner API checks the same run, then holds the owner's normalization claim while the worker checks the queue. Both competing requests return within the test deadline. The run creates one batch and performs normalization once.

**Verified**

- 16 scraper API and PostgreSQL tests passed on the migrated local database. The new race test uses the real API endpoints and PostgreSQL row locks. Backend Ruff passed.
- To run the race test, set `JEDI_TEST_SCRAPER_DATABASE_URL` to a dedicated migrated loopback PostgreSQL database with an empty scraper import queue, then run `pytest backend/tests/test_scraper_v2_postgres.py`.

**Open**

- Connect the scheduler and verify an approved import completes in the target deployment after the owner closes the browser. The local race test uses API requests and does not exercise that deployed path.

## Recover passwords with an emailed code

**Working**

- Forgot password emails a single-use, 16-character recovery code to the registered address. Members enter it in JEDI and choose their own new password. Codes expire in 15 minutes, and each account can request one every five minutes.
- Recovery no longer needs a frontend origin setting. Previously issued reset links work until their original expiry, and a completed reset revokes older sessions. Auth validation errors omit submitted values.

**Verified**

- 18 recovery and group API tests cover code formatting, address binding, expiry, replacement, one-time use, session revocation, and compatibility with previously issued links.
- The recovery smoke test passed against isolated PostgreSQL with stub mail delivery. Backend Ruff, 32 frontend tests, targeted lint, and the production build passed.

**Open**

- The configured hosted Supabase database lacks the existing password-reset migration. Apply it to the approved target before testing live delivery. Gmail delivery was exercised through a stub.

## Restore live password recovery for the local app

**Working**

- The configured Supabase database now has the password-reset table, session version column, and member display name column required by the current auth flow. The two existing additive migrations were recorded in Prisma.
- The local backend on port 8000 now serves the recovery-code flow. The older backend process returned the obsolete recovery-origin error.

**Verified**

- Both the application and migration connections reached the database containing the requested account. Gmail authenticated and accepted the requested recovery message.
- The local readiness endpoint returned 200, and a probe using a reserved nonexistent address returned the generic 202 recovery-code response.

**Open**

- The account holder still needs to enter the code and choose a password. Inbox delivery and the account holder's completed reset require their verification.
