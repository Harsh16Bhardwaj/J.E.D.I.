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
