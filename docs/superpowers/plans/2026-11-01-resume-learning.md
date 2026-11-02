# Resume and Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add validated resume onboarding and private job-driven learning sprints.
**Architecture:** Next.js consumes authenticated FastAPI endpoints. Dedicated member resume and attempt records avoid changing shared ranking profile semantics.
**Tech Stack:** Next.js, React, FastAPI, SQLAlchemy, Prisma, PostgreSQL, pypdf.
**Spec:** docs/superpowers/specs/2026-11-01-resume-learning-design.md

## Global Constraints

Preserve existing design tokens and manual onboarding. PDF-only initial uploads; no OCR or external model calls. Do not execute database migrations. Supplied schemaVersion 1 is the content contract. Member evidence and attempts are private.

## Review Focus

- Negated job skills must not become required learning tracks.
- Overlapping work dates must not double count experience.
- Malformed and encrypted PDF input must produce safe, distinct errors.
- Attempt ownership and concurrent submissions must preserve committed answers.
- Expired attempts must not accept answers or claim mastery.

### Task 1: Extraction and content contracts

Files: backend/schemas/learning.py, backend/services/resume.py, backend/services/learning.py, backend/content/react-rendering.json, backend/tests/test_learning.py.
Interfaces: extract_resume(data: bytes) -> ResumeEvidence; compare_skills(description, skills, evidence) -> dict; load_banks() -> dict[str, QuestionBank].
- [x] Write tests for PDF validation, evidence separation, overlapping periods, aliases and negation, bank counts and answer references; run and observe missing implementation failures.
- [x] Implement bounded local extraction, canonical vocabulary, conservative inference and validated supplied React bank.
- [x] Run targeted pytest; expect pass.

### Task 2: Persistence and authenticated APIs

Files: backend/database.py, prisma/schema.prisma, backend/routers/learning.py, backend/main.py, backend/tests/test_learning_api.py.
Interfaces: GET/PUT /api/resume, POST /api/resume/extract, GET /api/jobs/{id}/skill-gap, GET /api/learning/topics, POST/GET /api/learning/attempts, GET /api/learning/attempts/{id}, POST .../{id}/answers and .../{id}/finish.
- [x] Add failing API tests using existing SQLite group fixture for auth, evidence save, attempts, answer secrecy, replay, expiry and ownership.
- [x] Implement ResumeEvidenceRecord and LearningAttempt mappings and Prisma definitions without running migrations. Use row locks for attempts. Snapshot question banks for stable grading.
- [x] Run backend tests; expect pass.

### Task 3: Existing-design frontend

Files: frontend/src/lib/learning.ts, frontend/src/lib/learning.test.ts, frontend/src/components/resume-upload.tsx, frontend/src/components/skill-gap.tsx, frontend/src/components/learning-sprint.tsx, frontend/src/app/learning/page.tsx, onboarding/page.tsx, jobs/[jobId]/page.tsx, lib/navigation.ts.
Interfaces: typed ResumeEvidence, SkillGap and SprintAttempt mirror camelCase API fields; apiRequest supports FormData.
- [x] Add failing tests for navigation, timer and sprint bounds; run frontend tests.
- [x] Implement reviewable resume upload at onboarding end and learning page, comparison dialog and reusable deadline-based sprint with results and retry. Preserve tokens and accessible form/dialog patterns.
- [x] Run frontend tests, typecheck and lint; expect pass.

### Task 4: Integration and review

Files: README.md and deployment notes.
- [x] Document table creation/deployment and PDF/parser limitations, question bank addition and APIs.
- [x] Run backend suite/lint, frontend suite/lint/typecheck/build and Prisma validate where supported.
- [x] Request fresh final review, resolve important findings with regression tests, and report verified behavior and environment limitations.

## Execution ledger

Native execution in current checkout on codex/resume-learning. User approved full design; continue without an additional approval gate. No automatic commits or migration execution.


## Execution record

- Tasks 1–3 complete: local PDF extraction, reviewed member evidence, skill comparisons, versioned bank snapshots, timed server-graded attempts, and existing-design UI are connected.
- Task 4: independent review completed. Required/optional clause bleed, common negation forms, partially parseable work dates, and negated resume evidence were reproduced and fixed with regression tests.
- Browser QA: synthetic resume accepted and saved; a readable non-resume PDF displayed the rejection dialog; quiz answers locked and explanations appeared; finish recorded correct/incorrect/unanswered results; job comparison reflected saved private evidence.
- Browser QA additionally found two integration issues: existing-member onboarding redirect and PUT preflight rejection. Both were reproduced in tests and corrected.
- Ruling: execute natively on codex/resume-learning in the existing checkout, without automatic commits — keeps the user's reviewable workspace intact.
- Ruling: no database migration generated or executed — repository policy requires an approved PostgreSQL development URL, which is not configured. SQLAlchemy/Prisma definitions and deployment steps are provided.
- Final review declined live PostgreSQL concurrency and deployed PDF classification accuracy; those require the deployment environment and representative real resumes. Local SQLite API ownership, immutable answers, deadline behavior, PDF fixtures and UI flow were verified. No minor review findings deferred.

Final verification: backend pytest 97 passed / 5 PostgreSQL tests skipped; frontend tests 25 passed; backend Ruff, frontend ESLint, TypeScript, Prisma static validation, production build and git diff whitespace check passed. Existing dependency deprecation warnings remain. No remote database was contacted for schema validation.
