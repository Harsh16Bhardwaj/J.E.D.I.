# JEDI

JEDI is a private job-discovery and application command center. The repository
contains a Next.js dashboard, a small FastAPI service boundary, the Prisma
database schema, and the existing machine-learning work.

## Why `package.json` is at the root

This is an npm workspace. The root `package.json` is intentionally the control
panel for JavaScript tooling:

- it installs root tools such as Prisma;
- it installs the `frontend` workspace;
- it exposes one set of commands for starting and checking the project.

The frontend still has its own `frontend/package.json` because it is the actual
Next.js application. Python remains independent in `backend/pyproject.toml`;
npm does not manage Python packages.

## Repository structure

```text
JEDI/
├── frontend/        Next.js dashboard
├── backend/         FastAPI service
├── prisma/          Database schema and schema guide
├── ML/              Datasets, notebooks, results, and ML tools
├── archive/         Previous vanilla screener
├── package.json     npm workspace commands
├── package-lock.json
├── prisma.config.ts
├── vercel.json
└── .env.example
```

The old root `.venv` is retained only for historical notebooks. The backend
uses `backend/.venv`.

## Requirements

- Node.js 22
- npm 11
- Python 3.12

Verify them:

```powershell
node --version
npm --version
python --version
```

## First-time setup

Run these commands from `D:\ML\JEDI`:

```powershell
Copy-Item .env.example .env
npm install
npm run setup:api
npm run db:generate
```

The copied `.env` contains safe placeholders for local foundation checks.
`npm install` installs both root dependencies and the `frontend` workspace.
`setup:api` creates `backend/.venv` and installs only the FastAPI foundation
dependencies.

The ignored local `.env` contains non-live PostgreSQL placeholders so Prisma can
format, validate, and generate. Replace them only when a real Neon development
database is ready.

## Start both servers

The easiest command is:

```powershell
npm run dev
```

It starts:

- Next.js on `http://localhost:3000`
- FastAPI on `http://localhost:8000`

Press `Ctrl+C` once to stop both.

### Start the servers separately

Terminal 1:

```powershell
npm run dev:web
```

Terminal 2:

```powershell
npm run dev:api
```

## Useful URLs

| URL | Purpose |
| --- | --- |
| `http://localhost:3000` | JEDI dashboard |
| `http://localhost:3000/api/health` | Next.js health check |
| `http://localhost:8000` | FastAPI service metadata |
| `http://localhost:8000/docs` | Interactive FastAPI documentation |
| `http://localhost:8000/health/live` | FastAPI process health |
| `http://localhost:8000/health/ready` | FastAPI foundation readiness |

Quick PowerShell checks:

```powershell
Invoke-RestMethod http://localhost:3000/api/health
Invoke-RestMethod http://localhost:8000/health/live
```

## Validation commands

```powershell
npm run lint
npm run typecheck
npm run test
npm run build
```

Run every foundation check in sequence:

```powershell
npm run check
```

Database-only checks:

```powershell
npm run db:format
npm run db:validate
npm run db:generate
```

Do not run `npm run db:migrate` until `.env` points to an approved Neon
development branch. Production deployments use `npm run db:deploy`; never use
`prisma db push` as the production workflow.

## Understanding the database

Every field in [prisma/schema.prisma](prisma/schema.prisma) has an inline
description explaining why it exists. [prisma/README.md](prisma/README.md)
explains the model relationships in plain English.

## Common setup problems

### `backend/.venv` or Python packages are missing

```powershell
npm run setup:api
```

### Prisma Client is missing

```powershell
npm run db:generate
```

### Port 3000 or 8000 is already occupied

Stop the earlier development process with `Ctrl+C`, then run `npm run dev`
again.

### Dependencies appear inconsistent

Keep `package-lock.json`, remove only the generated `node_modules` directory,
then run:

```powershell
npm ci
```

## Current scope

The repository currently provides foundation routes and contracts. It does not
yet implement authentication, database CRUD, deduplication, embeddings, model
inference, scoring, email delivery, or application automation.
