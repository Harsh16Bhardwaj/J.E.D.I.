# Database schema in plain English

The schema separates raw evidence, durable jobs, predictions, and user actions.
That separation prevents a new source import or model version from overwriting
history.

## Core flow

```text
SourceDefinition
      │
      ▼
ImportBatch ──► JobObservation
                     │
                     ▼
                CanonicalJob
                  │      │
                  │      └──► JobState ──► JobEvent
                  │
                  └──► JobPrediction
                         ▲       ▲
                         │       │
                 ProfileVersion  ModelVersion
```

## What each model represents

| Model | Meaning |
| --- | --- |
| `SourceDefinition` | One approved job source and its allowed domains |
| `ImportBatch` | One JSON discovery envelope for a time window |
| `JobObservation` | One raw sighting of a job on one source |
| `DedupEvaluation` | The rule-by-rule comparison used to detect duplicates |
| `CanonicalJob` | The durable job produced after observations are merged |
| `ProfileVersion` | An immutable resume and preference snapshot |
| `ModelVersion` | An immutable registered model bundle |
| `JobPrediction` | A versioned ranking result for one job in one batch |
| `JobState` | The current personal label and application status |
| `JobEvent` | Append-only history of changes to a job |
| `ProcessingRun` | A retryable attempt to execute one pipeline stage |
| `EmailDelivery` | A durable top-job digest delivery attempt |

## Why both observations and canonical jobs exist

The same real job can appear on LinkedIn, a company careers page, and another
job board. Each appearance remains a `JobObservation`, while deduplication links
them to one `CanonicalJob`. This preserves source evidence without showing the
same opportunity repeatedly.

## Why predictions are separate

Predictions depend on a batch, profile version, preference model, and semantic
model. Storing those references with every result makes old rankings
reproducible and allows a model rollback without rewriting job data.

## Why state and events are separate

`JobState` makes the current dashboard fast to read. `JobEvent` retains the
history needed for audits and future preference learning.

The inline trailing `///` text in `schema.prisma` is official Prisma
documentation-comment syntax. Prisma attaches it to the corresponding field or
enum value for tooling.
