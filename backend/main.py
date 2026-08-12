import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Vercel imports this file as ``main:app`` from the backend service root. Add
# the repository root so every deployment mode still imports one canonical
# ``backend.*`` package rather than creating duplicate module singletons under
# both ``services.*`` and ``backend.services.*`` names.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import get_settings
from backend.database import engine
from backend.errors import install_error_handlers
from backend.middleware import RequestContextMiddleware, ServicePrefixMiddleware
from backend.routers import (
    auth,
    batches,
    dashboard,
    email,
    embeddings,
    group_access,
    health,
    misc,
    models,
    normalization,
    operations,
    scoring,
    scraper,
    workflow,
    workspace,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Release pooled Neon connections cleanly on server shutdown."""
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Private job import, review, training, and ranking API for JEDI.",
    lifespan=lifespan,
)

# Starlette applies the last-added middleware first. Request context must sit
# inside CORS so even a handled database/server failure remains readable by the
# browser instead of being misreported as a network failure.
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-JEDI-TIMESTAMP",
        "X-JEDI-SIGNATURE",
        "X-JEDI-SERVICE-TOKEN",
        "X-JEDI-LEASE-TOKEN",
        "X-Request-ID",
    ],
)
app.add_middleware(ServicePrefixMiddleware)
install_error_handlers(app)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(group_access.router)
app.include_router(batches.router)
app.include_router(dashboard.router)
app.include_router(workflow.router)
app.include_router(workspace.router)
app.include_router(models.router)
app.include_router(misc.router)
app.include_router(operations.router)
app.include_router(email.router)
app.include_router(normalization.router)
app.include_router(embeddings.router)
app.include_router(scoring.router)
app.include_router(scraper.router)
