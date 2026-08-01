# JEDI embedded model runbook

## Production contract

JEDI ranks by identifiers, not browser-supplied job text. The browser queues a
durable `ProcessingRun`, then calls its authenticated execute route. FastAPI
loads the prepared rows from PostgreSQL and calls the embedded scoring service
directly. `/v1/score` exposes the same service contract for service-authenticated
localhost tests or a future remote worker; the embedded executor never calls
back into its own Vercel deployment over HTTP.

The checked-in `jedi-ranking-v1` bundle contains a leakage-safe Ridge
multi-output preference pipeline stacked into conservative XGBoost. XGBoost's
decision threshold is 0.60. Ordering is apply gate, then JEDI preference score,
then apply probability, then stable job ID. All batch jobs are persisted; the UI
shows 25.

## Local setup and first run

```powershell
npm.cmd run setup:api
npm.cmd run db:deploy
npm.cmd run model:smoke
npm.cmd run model:benchmark
npm.cmd run dev
```

In Model settings, use **Register embedded bundle**, **Check deployment**, then
**Activate version**. Import a batch, normalize it, and choose **Rank this
batch**. The frontend performs queue then execute while retaining the last
successful result on screen.

Useful direct probes:

```powershell
Invoke-RestMethod http://localhost:8000/health/model/live
Invoke-RestMethod http://localhost:8000/health/model/ready
```

`POST /v1/score` requires `X-JEDI-SERVICE-TOKEN` and a body containing only
`batchId`, `processingRunId`, and `modelVersionId`.

## Release gates

Run these before every preview deployment:

```powershell
npm.cmd run db:validate
npm.cmd run model:smoke
npm.cmd run model:benchmark
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run test:api
npm.cmd run build
```

The production Python dependency closure plus model/source files must stay
below 450 MB. Benchmark 1, 25, 100, and 500 rows. Do not activate when cold
loading exceeds 30 seconds or warm p95 execution exceeds 120 seconds. Preview
must also verify a 500-row run, database region proximity, the 240-second
application deadline, and the 300-second Vercel function maximum.

## Failure handling

- `QUEUED` and `RUNNING` calls are idempotent. A concurrent execute call reports
  the existing active state.
- A transient inference error receives one inline retry. Every attempted model
  call has a `ModelInvocation` audit record.
- A schema, dependency, checksum, golden-output, or contract mismatch is
  permanent. Renormalize or restore the exact artifact; do not retry blindly.
- A Vercel interruption leaves a lease. Once expired, history derives `STALE`;
  manual retry closes it as `INVOCATION_INTERRUPTED` and creates a linked run.
- Prediction rows, the successful invocation, and run/batch success are one
  transaction. Partial rankings cannot become visible.
- A rerank failure leaves the previous successful predictions and `rankedAt`
  intact.

## Operations and quality monitoring

Inspect `ProcessingRun` and `ModelInvocation` for queue delay, attempt count,
phase, cold start, feature/Ridge/XGBoost/validation/database timing, input/output
count, artifact hash, and safe error code. Alert on contract/checksum mismatch,
three readiness failures, any stale lease, output-count mismatch, cold load over
30 seconds, p95 execution over 120 seconds, or more than 10 percent failures in
the latest 20 runs.

Quality is calculated per immutable model version only after sufficient labels:
Precision@25, Recall@25, NDCG@25, average precision, ROC-AUC, Brier score,
recommendation rate, save/dismiss/application conversion, missingness, unseen
categories, and subgroup drift. Small samples should be shown as insufficient,
not as alerts.

## Retraining and rollback

Production requests never retrain the model. Continue collecting annotations,
application outcomes, prepared payload hash, profile version, and prediction
context. Around 300 genuinely new labeled jobs, export the approved examples,
create an immutable dataset snapshot, and rebuild through the shared
`build_model_features()` code.

```powershell
npm.cmd run model:export
npm.cmd run model:smoke
npm.cmd run model:benchmark
```

Evaluate with grouped leakage-safe validation and a recent time split. Block
promotion on leakage, feature/contract drift, golden mismatch, material runtime
regression, or more than a two-point regression in Precision@25, NDCG@25, or
average precision unless the product tradeoff is explicitly accepted. Register
the candidate inactive, score recent batches in shadow, run deployment check,
then activate manually. Rollback is activation of the retained prior model;
historical predictions never change.

Move inference to a persistent container worker if the bundle exceeds 450 MB,
cold load exceeds 30 seconds, warm p95 exceeds 120 seconds, batches exceed 500,
CPU/memory throttling persists, or unattended automatic retries become a
requirement.
