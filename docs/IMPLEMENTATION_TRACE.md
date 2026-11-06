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
