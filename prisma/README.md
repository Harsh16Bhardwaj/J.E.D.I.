# Database schema in plain English

Prisma owns the PostgreSQL schema and migrations. FastAPI accesses the resulting
tables through the matching SQLAlchemy models in `backend/database.py`; the
frontend never connects to PostgreSQL directly.

## Core data flow

```text
User -> GroupMember
          |
          +-> private JobState / JobAnnotation / Application
          |                                  |
JSON -> Batch -> shared Job -> PreparedJob   +-> events / milestones
                           |          |
                           +----------+-> owner-approved TrainingExample
                           |
                           +-> shared JobPrediction
```

## Main models

| Model | Purpose |
| --- | --- |
| `User` | One invited account with an email and Argon2 password hash |
| `GroupMember` | The identity used to own one member's private job activity |
| `Batch` | One uploaded JSON envelope plus validation/dedupe counts |
| `Job` | One unique retained job owned by its first batch |
| `ProfileVersion` | Versioned resume and explicit preferences |
| `PreparedJob` | Versioned `prepared-job-v1` inference payload |
| `JobAnnotation` | One member's binary target and nine manual fit labels |
| `TrainingExample` | Owner-approved prepared payload plus label provenance |
| `ModelVersion` | Versioned ranking artifact manifest |
| `JobPrediction` | Real model score, probability, components, and rank |
| `JobState` | One member's viewed timestamp, relevance and review state |
| `Application` | One member's private application plan and current stage |
| `ApplicationEvent` | Append-only status history belonging to that application |
| `ApplicationMilestone` | Private screening, assessment and interview rounds |
| `ProcessingRun` | Idempotent normalization/ranking attempt |

Every schema field has an inline explanation beside it.

## Deliberate boundaries

- There is no source registry or scraper state.
- There is no duplicate review queue.
- A `Job` belongs to the batch that first introduced it.
- Batches, jobs, prepared features and predictions are shared by the v1 group.
- Viewed state, annotations, applications, events and milestones are keyed by
  `GroupMember`, so one member's activity never changes another member's queue.
- The group owner alone promotes personal annotations into shared training data.
- Duplicate candidates are fetched by indexed `companyKey` or canonical URL.
- `PreparedJob` contains only job/profile-derived inference inputs.
- Annotation labels never enter a prepared inference payload.
- Re-adding a job to training updates the same job/schema snapshot.
- Ranking requests store a pending run; they do not create fake predictions.

## Migration safety

Formatting and validation do not contact PostgreSQL:

```powershell
npm run db:format
npm run db:validate
```

Do not create or execute a migration until `.env` contains an approved
development PostgreSQL URL. Production uses `prisma migrate deploy`, never
`prisma db push`.
