# JEDI Backend Interview Questions and Answers

These answers are written in first person so you can practice saying them.
Adjust the wording to sound natural. Do not claim that model inference or live
email deployment is complete when it is not.

## 1. Project explanation

### 1. What is JEDI?

JEDI is my private job-discovery and application-management system. It accepts
structured job batches, removes duplicates, normalizes jobs into model-ready
features, stores my labels, queues ranking work, tracks applications and can
send a durable top-ten email digest.

### 2. Why did you build it?

Job discovery was fragmented and repetitive. I wanted a low-overhead workflow
where I could paste one structured batch, automatically remove jobs I had
already seen, rank the useful ones and preserve feedback for future models.

### 3. Describe the architecture.

The frontend is Next.js, while FastAPI owns product APIs and database access.
Prisma owns PostgreSQL migrations, SQLAlchemy is the Python ORM, Pydantic defines
HTTP contracts, Neon hosts PostgreSQL, and internal worker routes define the
future model-execution boundary.

### 4. Why separate Next.js and FastAPI?

Next.js is convenient for the dashboard and interaction layer. Python is a
better fit for the existing ML workflow. Keeping FastAPI as the only product API
also avoids duplicating business rules between TypeScript and Python.

### 5. Walk me through the main workflow.

I authenticate, import JSON, validate jobs independently, normalize only the
fields required for deduplication, compare likely candidates, store retained
jobs, normalize them for an active profile, annotate them, optionally add them
to training data, queue ranking and finally persist ranked results.

## 2. FastAPI fundamentals

### 6. What is `APIRouter`?

`APIRouter` groups related endpoints. For example, the authentication router
adds `/api/auth` as a common prefix. `main.py` includes that router in the final
FastAPI application.

### 7. What does a route decorator do?

`@router.post("/login")` registers the function below it as the handler for a
POST request at that path. The decorator also carries response model, status
code and OpenAPI metadata.

### 8. What is dependency injection in FastAPI?

A route declares values it needs, such as `CurrentUser` or `DatabaseSession`.
FastAPI runs the associated dependency functions first and passes their results
into the route. This centralizes authentication and session lifecycle logic.

### 9. What does `Annotated` do?

It preserves the normal Python type while attaching FastAPI metadata. For
example, `Annotated[AsyncSession, Depends(get_session)]` means the value behaves
like an `AsyncSession`, but FastAPI must create it using `get_session`.

### 10. Why use `async def`?

Database and SMTP operations spend time waiting for I/O. Async functions allow
the event loop to serve other work during those waits instead of blocking one
thread for the entire operation.

### 11. What is the difference between middleware and dependencies?

Middleware surrounds almost every request globally and is useful for request
IDs, logging and security headers. Dependencies are selected by routes and can
return useful values such as a user or database session.

### 12. What is a lifespan function?

It is an async context manager tied to application startup and shutdown. JEDI
uses its shutdown side to dispose SQLAlchemy's pooled database connections.

### 13. What does `response_model` provide?

It documents, validates, serializes and filters the outgoing response. The login
route returns `UserResponse`, so a password hash cannot accidentally appear even
if a larger object were returned.

## 3. Pydantic and data contracts

### 14. Why use Pydantic schemas?

They turn untrusted JSON into validated Python objects. They enforce required
fields, ranges, enums and custom cross-field rules before business logic runs.

### 15. Why are database models and API schemas separate?

Database models describe persistence, relationships and SQL types. API schemas
describe what clients may send or receive. Separating them prevents internal or
sensitive columns from becoming part of the public contract.

### 16. How does JEDI convert snake_case to camelCase?

The shared `ApiModel` uses an alias generator. Python code can use
`profile_version_id`, while API clients receive and submit
`profileVersionId`.

### 17. Give an example of custom validation.

Profile and job schemas reject a minimum experience or salary above its maximum.
Ranking requests reject duplicate jobs, duplicate ranks and ranks that are not
contiguous starting from one.

### 18. Why does batch ingestion validate jobs individually?

A single malformed job should not waste the other useful jobs in a batch. The
route records validation issues, skips invalid items, and creates the batch if
at least one valid unique job remains.

## 4. Authentication and security

### 19. How are passwords stored?

Passwords are never stored directly. `pwdlib` generates a salted one-way Argon2
hash. Login verifies submitted plaintext against the encoded hash.

### 20. Hashing versus encryption?

Encryption is reversible with a key. Password hashing is deliberately one-way
and computationally expensive. The server verifies a guess; it does not recover
the original password.

### 21. How does login work?

The route normalizes the email, loads the user, verifies the password, creates a
signed JWT and sends it in an HTTP-only cookie. Later dependencies verify the
token and reload the user from the database.

### 22. Why use an HTTP-only cookie?

Browser JavaScript cannot read it, reducing token theft through XSS. `SameSite`
is strict, and production requires the secure flag so the cookie travels only
over HTTPS.

### 23. Why reload the user after validating the JWT?

A valid token may outlive a deleted or changed account. Reloading the user makes
database state authoritative and allows removed users to lose access.

### 24. Why is the login error intentionally generic?

“Invalid email or password” does not reveal whether an email exists. More
specific messages would help attackers enumerate accounts.

### 25. How are internal workers authenticated?

They use a separate `X-JEDI-SERVICE-TOKEN`, not a user cookie. The secret is
compared with `compare_digest` to avoid timing differences.

### 26. What security information is deliberately not logged?

Request bodies, cookies, authorization headers, recipients, email bodies and
credentials are excluded. Logs contain method, path, status, duration and a
request ID.

## 5. Database and transactions

### 27. Why Prisma and SQLAlchemy together?

Prisma is the schema and migration authority shared with the monorepo.
SQLAlchemy provides async Python runtime access. Both map the same PostgreSQL
tables, and integration tests detect contract drift.

### 28. What is a transaction?

A transaction groups database operations into one atomic unit. If application
state updates but event insertion fails, the whole operation rolls back so the
database does not contain half a change.

### 29. What does `commit` do?

It makes the transaction's writes durable and visible to other transactions.
Before commit, the session may contain changes only within its own transaction.

### 30. What is idempotency?

It means retrying the same operation does not create unintended duplicates.
JEDI uses content hashes, idempotency keys and unique constraints for batch
replays, profile/model creation, training rows and ranking callbacks.

### 31. Why are database constraints still needed after application checks?

Two requests can pass an application check at the same time. A unique
constraint is the final atomic authority that prevents both writes from
succeeding.

### 32. What does `SELECT ... FOR UPDATE` solve?

It locks the selected row until the transaction finishes. JEDI locks a batch
while queuing ranking so two concurrent requests cannot create conflicting
runs.

### 33. What is `SKIP LOCKED`?

When workers compete for queued work, one worker locks a row. `SKIP LOCKED`
tells another worker to skip that row rather than wait, allowing safe parallel
processing.

### 34. Why do you test against both SQLite and PostgreSQL?

SQLite gives fast isolated route tests. PostgreSQL tests are still required for
arrays, JSONB, enums, partial indexes and row-locking behavior that SQLite
cannot reproduce.

## 6. Deduplication and normalization

### 35. How does deterministic deduplication work?

Company match is mandatory. Exact canonical application URL or dedupe key is an
immediate duplicate. Otherwise I evaluate role, location, work mode, employment
type, experience, salary and description; five positive signals means duplicate.

### 36. Why not compare every incoming job with the entire database?

That would become increasingly expensive. I retrieve candidates using indexed
company keys and canonical URLs, then perform detailed comparisons on that
smaller set.

### 37. Why canonicalize URLs?

The same job may include different UTM or referral parameters. Removing tracking
parameters, fragments and duplicate slashes lets equivalent URLs match.

### 38. Why are ingestion cleanup and model normalization separate?

Deduplication needs stable identity fields but should preserve useful source
information. Model normalization is profile-dependent and versioned, so it runs
later and produces separate `PreparedJob` rows.

### 39. What is a feature-schema version?

It names the exact structure expected by a model. A model trained on one feature
contract must not silently receive another. Processing runs therefore pin the
schema version.

## 7. Ranking and worker reliability

### 40. Why does ranking use a processing run?

A run records one attempt with its batch, profile, model, feature schema,
status, timing and errors. This makes retries and historical results auditable.

### 41. What does version pinning solve?

Without pinning, a worker could claim work after the active profile or model
changed and produce results with inconsistent inputs. The run stores the exact
versions selected when it was queued.

### 42. How do worker leases work?

A worker atomically claims the oldest queued run, receives a random lease token
and has five minutes. Heartbeats extend the lease. If it expires, another worker
can reclaim the run, up to three attempts.

### 43. How are ranking callbacks validated?

The callback must match the run's profile/model, use jobs from the batch, provide
unique contiguous ranks, stay within score ranges and occur in a valid workflow
state.

### 44. Can JEDI rank jobs using the real model today?

The storage, queue, worker and callback contracts are implemented, but the real
model worker and `/v1/score` implementation are deferred. For now, authenticated
manual rankings can exercise the complete persistence workflow.

## 8. Email reliability

### 45. Why store an email delivery row before sending?

SMTP is an unreliable external side effect. Persisting intent first means failed
or interrupted sends remain visible and retryable.

### 46. Is email exactly once?

No SMTP system can guarantee exactly once after an ambiguous network timeout.
JEDI provides practical at-least-once behavior using stable message IDs,
database uniqueness, leases and delivery history.

### 47. What happens when SMTP fails after ranking?

Ranking remains committed. The email delivery becomes FAILED with a safe error
and retry time. Email failure never rolls back valid model results.

### 48. How do you prevent HTML injection in the digest?

Job-controlled company, title, location, highlights and URLs are escaped before
being inserted into the HTML template.

## 9. Operations and deployment

### 49. Liveness versus readiness?

Liveness asks whether the Python process is running. Readiness asks whether it
can serve real traffic, including database and migration availability.

### 50. How does `/svc/ml` routing work?

Vercel forwards the public prefixed path. ASGI middleware removes `/svc/ml`
before route matching while preserving `root_path`, so the same route functions
work locally and in production.

### 51. Why use request IDs?

The client can report one identifier, and logs can locate that exact request
without exposing request content. JEDI preserves a valid incoming ID or
generates one.

### 52. What production work remains?

I need to rotate the exposed development database credential, make readiness
check the latest migration, verify the Vercel preview and real Gmail SMTP, add
the commands package to setuptools, and implement/deploy the real model worker.

## 10. Testing and design questions

### 53. What is your most important backend test?

The PostgreSQL concurrency test is especially valuable because it proves two
workers cannot claim the same run and two email senders cannot claim the same
delivery. A SQLite unit test cannot prove that.

### 54. How do you test a failed application event?

The test forces transaction failure and verifies neither the event nor the new
application status persists. That confirms atomic rollback.

### 55. What would you refactor next?

I would move infrastructure modules into `backend/core`, keep CLI tools in
`backend/commands`, split the large product schema by domain, and keep public
imports stable during the transition.

### 56. What trade-off did you make for a private tool?

I chose simple single-user email/password authentication and automatic duplicate
discarding. That reduces operational overhead, while database constraints,
secure password hashing and signed sessions still protect the workflow.

### 57. Why not use an LLM for deduplication?

Deduplication needs to be cheap, reproducible and explainable. Deterministic
normalization and signals avoid latency, cost and inconsistent decisions.

### 58. What would you monitor in production?

I would monitor readiness failures, request latency and error rate, queued and
expired processing runs, email retry counts, batch validation/rejection rates
and ranking callback failures.

## 11. Short project pitch

> I built JEDI as a private job-intelligence backend using FastAPI, PostgreSQL,
> SQLAlchemy and Prisma. It accepts structured job batches, performs indexed
> deterministic deduplication, generates versioned model-ready features, stores
> manual labels with training provenance, and manages ranking through
> lease-controlled worker runs. I also designed durable top-ten email delivery
> where SMTP failure cannot roll back valid rankings. The API and concurrency
> foundation are implemented; real model execution is the next separate phase.
