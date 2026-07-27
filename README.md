# JEDI

JEDI is a private job-discovery command center. This foundation separates the
web product, the ML service boundary, the database contract, and the existing
modeling evidence without implementing product behavior prematurely.

## Repository map

| Path | Purpose |
| --- | --- |
| `frontend/` | Next.js 16 App Router dashboard |
| `backend/` | FastAPI foundation and future ML-facing endpoints |
| `ML/` | Datasets, notebooks, evaluation results, tools, and future bundles |
| `prisma/` | PostgreSQL schema and future migrations |
| `archive/legacy-screener/` | Previous vanilla screener retained for reference |

The historical root `.venv` remains available for notebook work. The backend
uses its own isolated `backend/.venv`.

## Local development

Copy `.env.example` to `.env` and replace the placeholders when connecting to
Neon. The checked-out local `.env` is ignored and contains non-live values so
Prisma can format, validate, and generate without contacting a database.

```powershell
pnpm install
pnpm db:generate
pnpm dev:web
```

In a second terminal:

```powershell
backend\.venv\Scripts\python -m uvicorn backend.main:app --reload --port 8000
```

Local URLs:

- Web application: `http://localhost:3000`
- Frontend health: `http://localhost:3000/api/health`
- FastAPI service: `http://localhost:8000`
- FastAPI docs: `http://localhost:8000/docs`
- FastAPI live health: `http://localhost:8000/health/live`

## Production routing

A Vercel project will expose:

- `https://<project>.vercel.app/api/health`
- `https://<project>.vercel.app/svc/ml/`
- `https://<project>.vercel.app/svc/ml/health/live`
- `https://<project>.vercel.app/svc/ml/v1/normalize`
- `https://<project>.vercel.app/svc/ml/v1/embed`
- `https://<project>.vercel.app/svc/ml/v1/score`

## Database workflow

Prisma 7 reads database URLs from `prisma.config.ts`. Use the pooled Neon URL at
application runtime and the direct URL for migrations.

```powershell
pnpm db:format
pnpm db:validate
pnpm db:generate
```

No initial migration is included because this foundation does not contain live
database credentials. When a real PostgreSQL database is supplied, create a
development migration deliberately. Production must use `pnpm db:deploy`;
never use `db push` as a deployment workflow.

## Scope boundary

This phase intentionally contains no authentication, database CRUD,
deduplication, embeddings, model inference, scoring, email delivery, or job
application automation. The routes and schema establish stable contracts for
those later phases.
