# Mission: Operate the JEDI model safely in production

## Why
Deploy JEDI confidently, understand what is running, and diagnose model-serving
failures without treating deployment, loading, registration, and activation as
one opaque step.

## Success looks like
- Explain the difference between a model bundle, manifest, registry row, deployment check, and active version.
- Verify that Vercel packaged the exact model artifacts and that the runtime loaded them.
- Register, check, activate, test, and roll back an immutable JEDI model version.

## Constraints
- The frontend and FastAPI backend deploy together as Vercel Services.
- Model artifacts must remain immutable and checksum-verified.
- Lessons should use the real JEDI repository and production workflow.

## Out of scope
- Retraining or changing ranking behavior during deployment lessons.
- Building a separate persistent inference platform unless Vercel limits require it.
