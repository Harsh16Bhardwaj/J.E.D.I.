# Implementation trace

## Fix local dashboard session loop and theme startup

- Root cause: the local frontend was changed from localhost to a 127.0.0.1 API URL. Strict session cookies cannot cross those sites. Local development now proxies `/svc/ml` through Next to the IPv4 API, preserving the browser origin and cookie site. Production routing is unchanged.
- Theme persistence now uses a hydration-safe external store, avoiding startup writes that replaced the saved selection. Toasts consume the same theme context.
- Verified using an isolated Edge browser context with an existing user's signed session: actual API session HTTP 200, dashboard retained after reload, no page runtime errors. This checks session transport and the route guard; the user's password was not used or changed.
- Windows API readiness is HTTP 200 using `backend/run_local.py`. The earlier localhost/IPv6 diagnosis was unverified; changing browser hosts introduced the cookie problem corrected here.

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

## Restore and speed up the live scraper workspace

**Working**

- The configured database now has the existing provider-retry, draft, resume, private-application, and fit-snapshot migrations. Scraper attempts and stats, along with private draft applications, returned 200 after migration.
- Source inventory and source administration read metadata without downloading the provider response cache. Collection loads cached jobs for the relevant Greenhouse source only. Candidate staging uses one comparison query per provider response and keeps duplicate and repeated-timestamp checks.
- Board checks release database locks before provider I/O, stop waiting after 25 seconds, and discard a result when the source changes in the meantime. Reachable boards with zero jobs report healthy.
- Candidate review loads 25 rows at a time. The UI shows loading, empty, and retry states for candidate and attempt requests. Readiness checks the schema versions required by this build.

**Verified**

- The hosted source inventory held about 42 MB of uncompressed provider cache. Before the projection change, the inventory took 14â€“18 seconds in completed probes and timed out in a concurrent probe.
- A fresh browser session on localhost showed Source Health in 3.6 seconds and Candidate Review in 5.8 seconds. Pagination, candidate evidence, source reload, and filtering produced zero API errors.
- 190 backend tests passed with isolated PostgreSQL, along with 32 frontend tests, targeted lint, TypeScript, and the production build.

**Open**

- The browser check used the existing cancelled run for read-only review. A fresh collection and import against live employer boards were outside this verification.


## Separate the shared ranking experience into Legacy

**Working**

- Original dashboard, ranked catalog, and public landing implementation are preserved under `/legacy/dashboard`, `/legacy/jobs`, and `/legacy/landing`. Existing dashboard/catalog entry points remain compatible during transition.
- Sidebar groups the shared leaderboard, owner profile, model tools, and training data under Legacy. Existing score cards explicitly identify legacy preference scores. Personal resume, intake, and application tools remain in the main workspace.
- No database or account changes.

**Verified**

- Frontend unit suite and TypeScript validation recorded with this commit.

**Open**

- Replace the dashboard entry with personal preferences and batch recommendations after researching the retrieval architecture.
- Redesign the public landing and verify desktop/mobile behavior.

## Personal daily briefing and shared retrieval pools

**Working**

- Daily Feed now uses each member's private preferences. Edits preserve resume text and leave legacy group-model settings and email subscriptions untouched. Catalog and job-detail scores identify their legacy meaning.
- A daily authenticated server endpoint publishes role-family job pools atomically. It handles replay and overlapping PostgreSQL workers, preserves previous results on failure, and exposes cold-start, empty, stale, and failed-refresh states.
- The scheduler declaration runs at 01:00 UTC. This prepares recommendations from existing catalog jobs; it does not schedule employer scraping or send mail. Pool limits, score weights, and missing evidence are disclosed.
- PostgreSQL transactions use UTC, including on hosts with another default timezone. This fixes a real browser-tested case where freshly written jobs appeared future-dated after being read from timestamp columns. Existing timestamps are not rewritten.
- Industry research, current limitations, and the deployment checklist are in `docs/PERSONAL_RECOMMENDATIONS.md`.

**Verified**

- All 204 backend tests passed against isolated local PostgreSQL, including concurrent worker exclusion, replay, member isolation, alias normalization, stale fallback, and a non-UTC PostgreSQL regression.
- All 35 frontend unit tests passed. Prisma validation, Ruff, frontend lint, TypeScript, and the production build passed. A targeted recommendation rerun covers the final query projections.
- Authenticated browser verification saved personal preferences, showed a matching job and its score explanation, and retained preferences after reload. Fifteen existing workspace pages loaded at mobile width with no page errors, failed API responses, or horizontal overflow. These are navigation checks, not exhaustive mutation tests for every feature.
- Applied the new additive migration to isolated PostgreSQL only. No hosted account or data changes.

**Open**

- Deploy the migration and code to the intended production environment, configure `CRON_SECRET`, and observe an actual scheduled run. Current localhost preview still uses its existing backend configuration; isolated browser QA used a separate API on port 8107.
- Cohorts are deterministic role buckets. Learned clustering, queued retrieval beyond the current bounds, richer role vocabulary, and authorization/location constraints need the evaluation stages in the architecture document.

## JEDI personal-edition visual refresh

**Working**

- New public landing with an original SVG sentinel, jade lighting, orbital motion, scroll reveals, an interactive role example, and a readable field-guide dialog. Public copy explains personal preferences and resume evidence without presenting the legacy model's metrics as personal accuracy claims.
- Motion can be paused and follows the system reduced-motion preference. Hydration uses a stable server snapshot; static landing content remains visible when JavaScript is disabled.
- Shared dialogs now have a stronger backdrop, clearer headings and actions, bounded mobile height, internal scrolling, and initial focus at the top of the content. Sidebar content can scroll on shorter screens.
- Existing authentication and invite access remain in place. The field guide is explanatory and does not record legal consent or imply third-party sponsorship.

**Verified**

- Browser checks at 320, 390, 768, and 1440 pixels passed dialog bounds, initial scroll position, keyboard focus containment, Escape dismissal, focus restoration, and horizontal-overflow checks.
- Desktop/mobile visual review, role-example switching, motion pause, and reduced-motion reload passed with zero browser page errors. Fixed a reduced-motion hydration mismatch found during this verification.
- Frontend lint and TypeScript passed. The production build and the 35 frontend unit tests passed for the refreshed application.
- Earlier personal-feed verification covered 204 backend tests and navigation across 15 existing workspace pages. No production migration, deployment, mail send, or employer scrape was part of this UI verification.

**Open**

- Production rollout of the personal feed remains subject to the deployment checklist in `docs/PERSONAL_RECOMMENDATIONS.md`.
- Real-device animation performance, assistive-technology review, and broader usability testing remain follow-ups. Browser navigation checks do not establish exhaustive coverage of every existing workflow.

## Minimal workspace, page launcher, and illustrated sign-in

**Working**

- Replaced boxed navigation with a quieter sidebar, original signal mark, one active destination, collapsible Legacy controls, and a compact responsive page header. Fixed simultaneous Jobs/Resume fit active states with longest-path matching.
- Added a Go to page launcher with Ctrl/Cmd+K, query filtering, arrow navigation, Enter selection, and Escape dismissal. It uses the same owner/member destination filtering as the sidebar and leaves other open dialogs' shortcuts intact.
- Added original orbit/path SVGs, short page-entry and hover motion, illustrated application empty state, and compact mobile feed summaries. Reduced-motion overrides apply to all new animations.
- Refreshed sign-in while preserving its authentication flow; added password visibility and associated validation messages. Removed implementation details from its introductory copy.
- Corrected the global border reset's CSS layer so transparent borders and component border colors work as intended. Follow-up priorities are in `docs/UI_ROADMAP.md`.

**Verified**

- 37 frontend unit tests passed, including specific-route active states, query matching, and owner/member navigation filtering. Frontend lint, TypeScript, and production build passed.
- Controlled browser fixtures verified the dashboard, mobile drawer at 320/390/768px, command search/navigation, member permission filtering, owner-only shortcuts, password visibility, and reduced motion. Desktop and mobile screenshots were inspected. No real account writes were used for this UI check.

**Open**

- Continue with resume evidence hierarchy, application transitions, and data-backed source analytics in the UI roadmap. Automated visual baselines and assistive-technology/device performance review remain pending.
- Personal-feed production migration and scheduler activation remain the separate rollout work documented above. This UI pass changes no backend data or authentication policy.

## Restore the original identity and simplify browsing

- Restored the earlier landing layout, original logo, and sign-in presentation. Updated the landing copy to distinguish Daily Feed from the Legacy ranking.
- Removed the dashboard hero and oversized summary cards. The shortlist, update time, and preference controls now take priority.
- Moved search, sorting, bookmarks, and results into one Jobs toolbar. Secondary filters collapse with an active count. Existing URL filters, including custom minimum scores, still work.
- Verified 37 frontend tests, lint, TypeScript, and mobile browser checks with fixture data for the logo, preferences dialog, and job filters. The personal-feed database migration remains pending on the configured local connection.

## Simplify the application pipeline

- Replaced the wide seven-column board with responsive stage groups. Empty stages are omitted, and a selected stage gets its own results view.
- Consolidated search, stage, deadline, and sorting controls. Added clear-filter actions and accurate matching-result counts.
- Shortened the page heading and privacy copy, tightened application cards, and made status choices readable. Search follows URL navigation through a keyed form input.
- Checked correction-reason requirements and saved move payloads with controlled browser fixtures. Filtering, clearing, and widths of 320, 390, and 768 pixels passed without page overflow. Desktop rendering was visually inspected.
- Frontend lint, TypeScript, 37 unit tests, and the production build passed. Browser mutation checks used fixtures.

## Restore the pre-redesign baseline and offer sidebar choices

- Restored the landing, shared dashboard, Jobs, Applications, sidebar structure, mobile navigation, route headings, and dialogs from the pre-redesign baseline at 6f07c19.
- Kept the personal feed at /dashboard/personal, linked from the dashboard and navigation. Its preferences and private scoring remain available.
- Added four sidebar previews on /dashboard: Original, Minimal, Indigo, and Paper. Preview updates the sidebar immediately. Keep saves one choice in this browser and collapses the picker; Discard restores the saved choice. Change style reopens the picker.
- Applied the additive 20261107000000_daily_recommendations migration to the configured Supabase database and generated its first daily pool. Verified the real authenticated recommendations endpoint returned HTTP 200, READY, and 12 jobs.
- Frontend lint, TypeScript, 37 unit tests, and the production build passed. Controlled browser checks passed all four previews, save/reload persistence, discard, and mobile navigation.
- Sidebar selection currently persists per browser. Production scheduler deployment verification remains separate from this manually generated daily pool.

## Refine the approved dark card dashboard

- Used the user's screenshot as the visual reference: original boxed sidebar and logo, dark cards, lime score rings and salary values, purple company names, and compact tags.
- Cleaned Markdown markers from description previews while preserving technical skill names. Posting age now uses the supplied posting date; a batch-date fallback is explicitly labelled Imported.
- Tightened card headers on small screens and kept the appearance picker collapsed until opened. Hover emphasizes the existing card border.
- Added a regression test for Markdown previews and skill punctuation. All 38 frontend tests passed, along with lint and TypeScript. Desktop and 320/390/768px browser checks used fixture data, and the rendered dashboard was visually inspected.

## Apply the selected Paper theme sitewide

- Made Paper the global theme, with warm backgrounds, cream cards, dark text, forest-green preference signals, muted violet accents, and stronger error colors.
- Removed the sidebar preview controls after the user's selection. Shared color tokens now cover workspace pages, inputs, popovers, dialogs, native controls, and toast notifications.
- Adapted the existing landing palette, model code blocks, chart colors, and scraper checkboxes. The landing uses a hydration-safe reduced-motion check.
- All 38 frontend tests, lint, TypeScript, and the production build passed. Browser fixtures verified landing, login, both dashboards, preference dialogs, dense job cards, and 320/390/768px layouts, including a dark operating-system preference.
- Desktop landing and job-card rendering were visually inspected. Broader assistive-technology and real-device review remain follow-ups.

## Minimal sidebar and admin-only collection tools

- Moved Scraper and Batches into an Admin navigation group, visible only to the group owner. Admin maps to the existing isGroupOwner authorization model.
- Simplified sidebar rows, section labels, branding scale, tutorial indicator, and footer directly in the component. Removed sidebar-specific stylesheet overrides and collapsed Legacy tools.
- Added a direct-page guard for /scraper and /batches, including nested routes. Added an owner dependency to every /api/batches endpoint; existing scraper ownership checks continue to apply.
- Member dashboards, including Legacy, no longer request batch inventory or display import/operations controls. Normal job browsing and private application tools retain their entry points.
- 39 frontend tests passed. Backend group/access tests passed (16), and the product API suite passed (32). Frontend build, TypeScript, lint, and targeted backend Ruff passed.
- Browser fixtures verified owner Admin navigation, absence of member admin links, direct-route denial, zero member batch requests, and mobile overflow checks. The rendered sidebar was visually inspected.

## Restore the local API and extend the newspaper public pages

- Found no API process listening on localhost:8000. Started the existing FastAPI development entry point as a hidden background process using the configured database. Live and ready checks returned HTTP 200; a credentialed browser readiness request also returned 200.
- Replaced the login's solid accent panel and technical intro with a Paper newspaper cover, serif headline, restrained rules, and an original SVG desk engraving.
- Added The Daily Signal masthead and an illustrated lead figure to the existing landing layout. Updated stale shared/private workspace copy.
- Preserved the login request, validation, password-reset link, and invitation entry points. The mobile layout reduces the cover to a compact masthead.
- All 39 frontend tests, lint, TypeScript, and the production build passed. Browser checks covered API connectivity, login fields, landing, reduced motion, and 320/390/768/1440px layouts. Login and landing screenshots were visually inspected.
- The API runs as a local development process. Hosted deployment and machine-startup service configuration are separate operations.

## Give the feeds and job intake clearer hierarchy and recovery states

- Removed The Daily Signal wording from the public pages, login, sidebar, and settings copy.
- Added an illustrated career-desk header to the shared dashboard and distinct numbered cards, score rings, and expandable review notes to the personal feed.
- Separated Jobs listings with stronger borders, paper shadows, larger gaps, employer identities, score rings, and shaded action footers. Grouped the intake action beside the result tabs.
- Reworked Bring a Job into link and paste modes with an explicit bring/review/compare sequence. Showed extracted role and skill summaries before optional field edits.
- Added actual elapsed time, bounded 15-second preview requests, cancel controls, preserved input on cancellation/error, retry actions, and an unsupported-link paste fallback. Successful extraction scrolls to the review, respecting reduced motion.
- All 39 frontend tests, lint, TypeScript, and the production build passed. Scripted browser fixtures verified unsupported URL handling, paste fallback, processing, cancellation, retained input, edited save payloads, and four pages at 320/390/768/1440px. Personal-feed, Jobs, and intake renders were visually inspected.
- Preview-state verification used controlled API responses. Live employer fetching remains a separate verification step.

## Remove dashboard clutter and give each job surface its own layout (2026-11-11)

- Removed Career Desk branding from the dashboard, landing, login, and legacy landing. Removed the dashboard's extra navigation row, illustrated greeting hero, repeated section eyebrows, slogan, and duplicate navigation actions. Kept the existing Paper palette and JEDI logo.
- Rebuilt shared feed cards around employer, role, location, compensation, and a compact preference score. Removed repeated extracted-description prose. Three columns fit desktop widths from 1280px; skeletons have a smaller footprint.
- Replaced personal feed cards with a numbered evidence shortlist, plain numeric scores, expandable unknowns, and a contextual preferences column. Added a score-distribution graphic calculated only from displayed recommendations, including a separate unscored count.
- Added a real application-stage distribution with stable stage colors and readable counts. Corrected the total label to Tracked, reduced empty action-panel space, and collapsed secondary shared rankings.
- Rebuilt Jobs as compact catalog rows with distinct action footers. Search and sorting stay visible; extra filters expand on demand and open for active URL filters. Preserved arbitrary deep-linked minimum scores, bookmark/viewed actions, application preparation, and pagination.
- Simplified shared page headers to a title and expandable Help containing the existing description and guide links. Shortened Applications, Batches, Learning, and Guide titles; reduced onboarding and job-detail headers; removed technical route labels from Settings cards; shortened intake headings while preserving its processing/recovery workflow.
- Verified: all 39 frontend unit tests; lint; TypeScript; production build; git diff whitespace check. Local API readiness returned HTTP 200. No database changes or credential changes were made.
- Browser checks used controlled API responses: populated dashboard/personal feed/Jobs/intake at 320/390/768/1440px; histogram boundaries at 60 and 80 plus null-score handling; custom minimum-score URL, search, and clear; preference dialog; unsupported URL fallback, preview cancellation, preserved input, and edited draft save payload.
- Additional browser audit covered 22 public/workspace routes at 320/1440px with API failures, no runtime errors, and no removed branding. Verified retry-to-empty recovery, preference-setup entry, owner Admin navigation, member direct-route denial, and zero member batch requests. Dashboard, personal feed, and Jobs screenshots were visually inspected.
- Remaining verification: authenticated end-to-end checks against real account data, live employer extraction, real-device and assistive-technology review. Browser fixtures establish rendering and interaction behavior, not live data correctness.

## Fix stalled dashboard reads and add selectable site themes (2026-11-11)

- Reproduced a real-data dashboard read that stalled while PostgreSQL reported ClientWrite for job/prediction queries. The route selected full Batch rows, repeating rawEnvelope/validationReport for each job, and joined every historical prediction before deduplicating in Python.
- Limited batch/state/application columns to the dashboard contract with raiseload protection. Selected the latest prediction per job using a SQL window, fetched feed scores only for candidate jobs, and limited the leaderboard to ten rows in SQL. Preserved day/week/overall selection, visibility filters, deterministic ties, and latest-job fallback.
- Removed the same repeated batch payload from the Jobs and Applications list queries. Added a regression assertion that dashboard SQL omits batch envelopes and validation reports and selects latest predictions with a window function.
- Read-only checks against the configured database returned 25 jobs: initial optimized read 3.2s; subsequent daily read 2.19s (38,464 response bytes) and overall read 1.56s (25 jobs plus ten leaders, 54,512 bytes). These measured the route handler with an existing database user, not an authenticated browser page load. No data, credentials, or schema were changed.
- Dashboard reads now have a 20-second deadline, an explicit retry action through the existing error state, and a 60-second refresh interval instead of ten seconds. Consolidated duplicate local API development processes and confirmed readiness HTTP 200.
- Added a native top-right workspace Theme select: Paper (default), Studio, Midnight, and Forest. Browser-local selection persists across reloads and navigation. Shared palette tokens now cover custom job cards, evidence rows, filters, intake feedback, public surfaces, native controls, and toast appearance. Kept the existing page structure and original logo.
- Verified: 39 frontend tests; all 32 product API tests; frontend lint and TypeScript; targeted backend Ruff; production build. Browser fixtures checked four themes across dashboard/personal/Jobs/intake at 320/1440px, persistence, filters, intake processing/recovery, and preference dialogs. Midnight dashboard and Forest personal-feed screenshots were visually inspected.
- A browser test held the dashboard response beyond 20 seconds, verified the timeout replaced loading, and verified manual Retry recovered to a valid empty response. API authentication was not bypassed or changed.
- Remaining: measure the user's authenticated browser page load and refine visual hierarchy further from review of the selectable themes. Broader real-device and assistive-technology verification remains outstanding.

## Replace flat themes with researched color systems (2026-11-11)

- Reviewed the official Vercel Geist color system, Atlassian color roles/accents, Linear design-refresh notes, and Slack's published brand palette. Recorded the sources, adaptations, and exact token combinations in docs/DESIGN_PALETTES.md. Theme names and JEDI branding remain independent of those products.
- Replaced Paper/Studio/Midnight/Forest with Workspace, Editorial, Spectrum, and Carbon. Workspace defaults to plum navigation with neutral white content; Editorial retains a warm reading surface with cobalt/sage accents; Spectrum pairs violet actions with blue/teal/magenta categories; Carbon uses neutral charcoal with lavender, blue, mint, and amber.
- Centralized the complete palettes in frontend/src/styles/themes.css. Added independent action, information, success, review, destructive, identity, and sidebar roles rather than applying a single tint to every component. Adapted native sidebar text, selected states, focus rings, and footer colors for contrasting navigation surfaces.
- Added deterministic six-family decorative employer initials. Employer labels stay neutral, compensation uses success color when available, missing compensation stays muted, match evidence gets green emphasis, review notes use amber, and unseen status uses information color rather than error red. Score distribution and application stages have distinct readable series colors.
- Added current-palette swatches beside the top-right selector. Valid choices persist; old or invalid stored theme values migrate to Workspace. Updated toast dark mode to follow Carbon.
- Verified all 39 frontend tests, lint, TypeScript, production build, and whitespace checks. Checked 18 text/foreground pairs per theme against 4.5:1: minimums Workspace 4.65, Editorial 4.93, Spectrum 4.93, Carbon 7.04. This checks selected tokens, not the entire site's accessibility.
- Controlled browser checks covered four themes on populated dashboard, personal feed, Jobs, and intake at 320/1440px; 390/768px base route checks; persistence; migration of all four former themes and an invalid stored value; preference dialogs; distinct histogram series; search/minimum-score filters; intake recovery and edited save payloads. Owner/member Admin navigation and direct-route guards also passed.
- Visually inspected desktop dashboard, personal feed, and Jobs renders across the palette set. An intermediate chart-color comparison bug was caught in screenshot review and replaced with explicit per-band color tokens; browser checks now assert three distinct series colors.
- Remaining verification: real-device/assistive-technology review, visual review with real account content, and full contrast coverage of every component/state. No backend behavior or stored account data changed in this commit.
