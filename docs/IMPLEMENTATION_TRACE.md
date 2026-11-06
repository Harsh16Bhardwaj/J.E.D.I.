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
