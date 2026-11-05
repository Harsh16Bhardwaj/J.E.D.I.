# JEDI product roadmap

## 1. Stabilize the scraper and protect member emails

- Implement the P0 fixes and acceptance tests in the [scraper audit](SCRAPER_RELIABILITY_AUDIT.md), then address source inventory and health checks. Verify the full owner workflow from collection through partial import and ranking handoff.
- Fix the confirmed roster disclosure in [GET /api/group](../backend/routers/group_access.py#L511). It returns each member's email to any group member, and the [Group screen](../frontend/src/app/settings/group/page.tsx#L139) renders it. Use a names-only roster contract. Add a member-supplied display name with a neutral placeholder for missing names. Avoid deriving the name from the address.
- Treat the group owner as the admin for shared email operations, matching the current [email endpoints](../backend/routers/email.py). Keep addresses in owner-only recipient views and restrict group send operations server-side. Preserve members' access to their own account and email preferences. Verify owner, member, and signed-out responses and rendered columns. Inspect related exports, event responses, and cached responses for address exposure. Test against a stub transport.

## 2. Let a member bring a single job

Implemented the private paste and URL preview paths. URL intake accepts individual Greenhouse, Lever, and Ashby posting links and sends requests only to their fixed public API endpoints. Other sources can use the paste path.

- Start with pasted descriptions. Add URL intake for the existing ATS adapters where they support individual postings, then structured `JobPosting` data and a bounded HTML fallback. Keep drafts private by default. Use the same extractor for URL and paste and show an editable preview before saving.
- Extract title, employer, location and work mode, minimum and preferred experience, responsibilities, education and credentials, work authorization, compensation when stated, and required versus preferred skills. Retain source spans and distinguish absent, ambiguous, and conflicting information. Surface expired, blocked, unsupported, and incomplete pages with a paste fallback. Prioritize popular hosts from observed demand and publish a tested support matrix.
- Gate URL fetching on public HTTP(S) destinations, including every redirect and resolved address. Bound response size, redirects, fetch time, and retries. Treat fetched text as untrusted data. Maintain fixtures for supported ATS pages, stale listings, generic templates, and snippets that contradict the structured metadata.

## 3. Extend Compare Skills into a resume fit report

The private draft now has a first resume evidence view. It shows explicit, inferred, and missing evidence for reviewed skills, including clear alternatives and skill-specific experience that still needs confirmation.

- Build on [the current comparison](../frontend/src/components/skill-gap.tsx) and [resume evidence parser](../backend/services/resume.py). Reuse the bounded PDF flow, then add plain-text input and validated DOCX if needed. Show extracted evidence for review. Document ownership, retention, and deletion for resume files, evidence, and comparisons. Test cross-member access.
- Introduce a versioned skill vocabulary with separate alias and relationship tables. Map React, React.js, and ReactJS to one stable ID. Keep React Native separate. Treat supervised and unsupervised learning as narrower concepts under machine learning. Supported child evidence can contribute to a broad requirement with an explanation. A broad mention alone leaves a specific child requirement unverified. Replace rules that conflate a tool with a discipline, such as mapping PyTorch directly to Machine Learning as an alias.
- Normalize Unicode, whitespace, casing, and known variants while preserving meaningful punctuation in skills like C++, C#, and .NET. Track explicit, inferred, and ambiguous evidence separately. Test aliases, negation, alternatives, mandatory and optional language, role-specific years, mixed resume layouts, and ambiguous abbreviations. If semantic retrieval is added, use it to suggest candidates for verification against source text.
- Show skill, relevant experience, seniority, and domain alignment with a requirement-by-requirement breakdown. Separate evidenced matches, evidence needing clarification, requirements with no resume evidence, and confirmed gaps. Flag unmet hard requirements separately and show insufficient evidence when a score would be misleading. Keep this assessment separate from the shared job ranker. Version the scorer, snapshot both inputs, and evaluate extraction precision and recall, alias false positives, and scoring consistency on a hand-labeled fixture set before rollout.
- Offer a next action for each gap. Clarify an existing achievement, confirm a missing fact, or link an actual learning gap to a practice sprint. Keep edits grounded in the user's experience. Jobright's public product provides examples of a multi-dimensional fit view and a reviewable resume improvement flow. [Resume matcher](https://jobright.ai/tools/resume-job-matcher) · [Job match](https://jobright.ai/ai-job-match)

## 4. Improve application management

- Reuse the existing [application enum and event history](../prisma/schema.prisma#L745) and [pipeline board](../frontend/src/app/applications/page.tsx). Separate optional tags from status. Add a shared transition policy, explicit undo or correction events, and clear terminal states. Add filters for saved and active roles, next actions, deadlines, and the resume version used.
- Make confirmed actions drive moves. A recorded submission can move Preparing to Applied, and a confirmed interview can create an event and move to Interview. Keep inferred changes as suggestions until accepted. Use idempotent events and expected-stage checks so retries or stale tabs cannot overwrite a newer decision. Validate old records, duplicate events, rejected transitions, and member privacy.
- Connect private job drafts and fit reports to the pipeline with a Save to Applications action. Allow the user to revisit the source snapshot, compare a revised resume, and see the history of their decisions from one place. [Jobright tracker](https://jobright.ai/tools/job-tracker)

## Release framework for new features

Use a small feature entry alongside the existing [navigation](../frontend/src/lib/navigation.ts) and [tutorial](../frontend/src/app/tutorial/page.tsx) for each shipped workflow. Record its ID, route, audience, prerequisite, rollout flag if needed, tutorial chapter, and support or recovery link. Migrate the current browser-local tutorial completion bit to versioned chapter progress while recognizing completion of the existing guide. Teach each feature at its entry point with a safe sample and a path back to the full tutorial.

Each release entry should carry its user outcome, owner or member permission, explicit pending and failure states, API contract, data migration and recovery plan, acceptance tests, and the metric used to judge rollout. Ship the first entries for scraper recovery and job intake, then use the same format for comparison, practice, and the application pipeline.
