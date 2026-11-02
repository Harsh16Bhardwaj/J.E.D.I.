# Resume onboarding and job-driven learning

## Intent and constraints

Extend JEDI with resume extraction, member-specific job skill comparisons, and theoretical learning sprints. Retain Next.js frontend, FastAPI product APIs, PostgreSQL/Prisma schema ownership, current authentication and group boundaries, and existing visual tokens, typography, cards, dialogs, and navigation patterns. Shared ranking models and scores retain their existing behavior.

## Onboarding and resume extraction

Add an optional PDF upload section at the end of manual onboarding. Keep target titles, preferred locations, salary, and experience preferences manually entered. Resume-based current location and calculated work experience are separate facts, never overrides for preferences.

The backend validates file signatures, size and page limits, readability, and resume content before accepting extraction. Reject arbitrary documents with a clear invalid-resume dialog. Distinguish unreadable, encrypted, or scanned PDFs from documents positively rejected as non-resumes. Initial implementation supports text PDFs; OCR is out of scope. Validation is evidence based and cannot promise perfect classification for every possible document.

Extract summary, contact information where present, current location, education, work history, projects, explicitly stated skills, and inferred skills. Preserve provenance for inferred skills and avoid claiming unsupported expertise. Calculate work experience from dated work intervals, merging overlaps and excluding education; uncertain dates remain unknown. Separate inferred and explicit skills in storage and UI. Show extracted facts for review and permit correction before saving. Do not retain the original PDF; retain member-private extracted text and structured facts.

Implementation choice: use local PDF text extraction and conservative, testable section and skill rules first. No external AI service or credentials are required. Surface unknown fields instead of guessing; record parsing limitations. Keep extraction behind an interface so richer extraction can be added later.

## Job comparison

Parse skill requirements from existing job description text and normalized job skills, using a common canonical skill vocabulary and aliases. Distinguish required, preferred, and uncertain mentions where the source supports it. Compare against the authenticated member's saved resume evidence, never the shared group profile or other members' data. Explicit and inferred matches remain labeled separately. Present matched skills and missing skills in a job-detail dialog, with evidence where available. Inferred matches are tentative and can be corrected in the resume review.

Missing required skills with available question banks enable practice tracks. Matching skills are excluded from recommended practice. Preferred gaps remain optional recommendations. A missing skill without a question bank displays an unavailable state; never fabricate a bank or completion.

## Question bank contract and learning UI

Use the supplied schemaVersion 1 JSON unchanged: topicId, topicName, questionCount, difficultyDistribution, questions, option explanations, and answer.correctOptionId/answer.explanation. Validate unique question IDs and option IDs, valid answer references, supported difficulties, accurate counts and distribution, and nonempty prompts/explanations. Include the supplied three-question React Rendering and Keys bank as the initial real content. Do not invent 100–200-question banks.

Maintain a separate registry mapping canonical skills to topic IDs and ordering prerequisites. React maps to react-rendering. Banks are versioned application content; arbitrary member uploads of executable content are not needed.

Add a Learning navigation entry and page with job-specific recommendations and a clear empty state when no resume, selected job, gaps, or bank is available. Show topic, difficulty mix, question availability, and progress. Use a reusable sprint component that accepts a validated bank. Users choose question count within availability and sprint duration before starting. Present one question at a time, lock submitted answers, explain selected options and correct answers after submission, then advance explicitly. Use a deadline-based timer that handles inactive tabs, auto-finishes at expiry, and respects reduced motion. Results show correct, incorrect, unanswered, and explanations. Allow retry and persist member-private attempts and progress through the backend. A timed-out or abandoned attempt never marks a topic mastered automatically.

## Storage and APIs

Add member-owned resume extraction and learning attempt storage, reflected in Prisma and SQLAlchemy models. Use existing API error envelopes and auth/group access dependencies. Add authenticated extraction/review endpoints, member-specific job skill comparison, validated topic listing/detail, and learning attempt create/answer/finish endpoints. The backend owns answer validation, grading, duration and count bounds, and attempt ownership. Avoid exposing answer keys before submission through attempt APIs; explanations are returned after an answer is committed. Normal onboarding continues to work without a resume.

Prepare database schema changes and document deployment requirements. Do not execute a migration against an unapproved database. Keep personal resume evidence separate from immutable shared ranking profile initialization, which remains compatible with existing onboarding.

## Verification and delivery

Test valid and invalid PDF handling, extraction evidence and overlapping work periods, skill aliases and negated requirements, schema rejection, cross-member authorization, question grading, duplicate submissions, expiry, and saved progress. Run targeted backend and frontend tests, lint and type checks, schema validation, and a production frontend build where the local environment supports them. Inspect the onboarding, comparison dialog, and sprint UI against existing design patterns. Report any unavailable dependencies, database migration steps, and extraction limitations clearly.

## Scope choices made for review

PDF-only initial uploads; no OCR or external model calls. Local conservative extraction favors missing uncertain facts over inventing them. Resume upload is optional. The provided React bank is the only initial question bank. Tracks without content show unavailable states. Question JSON is content maintained in the repository. Progress is private per member; existing shared job rankings remain intact.
