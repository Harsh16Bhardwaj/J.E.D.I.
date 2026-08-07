import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

if __package__ == "routers":
    from config import get_settings
    from database import engine
    from schemas.common import HealthResponse, ServiceInfoResponse, ServiceMetadata
    from schemas.scoring import ModelRuntimeHealth
    from services.model_runtime import ModelRuntimeError, model_runtime
else:
    from backend.config import get_settings
    from backend.database import engine
    from backend.schemas.common import (
        HealthResponse,
        ServiceInfoResponse,
        ServiceMetadata,
    )
    from backend.schemas.scoring import ModelRuntimeHealth
    from backend.services.model_runtime import ModelRuntimeError, model_runtime

router = APIRouter(tags=["service"])
EXPECTED_MIGRATION = "20260802000000_email_event_control"


async def check_readiness() -> bool:
    """Verify both database access and the migration required by this build."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            migration_applied = await connection.scalar(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM "_prisma_migrations"
                      WHERE migration_name = :migration
                        AND finished_at IS NOT NULL
                        AND rolled_back_at IS NULL
                    )
                    """
                ),
                {"migration": EXPECTED_MIGRATION},
            )
        return bool(migration_applied)
    except SQLAlchemyError:
        return False


@router.get("/", response_model=ServiceMetadata)
def root() -> ServiceMetadata:
    settings = get_settings()
    return ServiceMetadata(
        service=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        status="ok",
    )


@router.get("/health/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(service="jedi-ml", status="ok")


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    responses={503: {"description": "Database or migration unavailable."}},
)
async def ready(
    is_ready: Annotated[bool, Depends(check_readiness)],
) -> HealthResponse:
    if not is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service is not ready.",
        )
    return HealthResponse(service="jedi-ml", status="ready")


@router.get("/health/model/live", response_model=ModelRuntimeHealth)
def model_live() -> ModelRuntimeHealth:
    """Report runtime state without claiming model readiness."""
    return model_runtime.health()


@router.get(
    "/health/model/ready",
    response_model=ModelRuntimeHealth,
    responses={503: {"description": "Model bundle is incompatible or unavailable."}},
)
async def model_ready() -> ModelRuntimeHealth:
    """Verify checksums, pinned dependencies, contracts, and golden output."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(model_runtime.warmup),
            timeout=get_settings().model_load_timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MODEL_LOAD_TIMEOUT", "message": "Model loading timed out"},
        ) from exc
    except ModelRuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.get("/v1/info", response_model=ServiceInfoResponse)
def info() -> ServiceInfoResponse:
    settings = get_settings()
    return ServiceInfoResponse(
        service="jedi-ml",
        api_version=settings.app_version,
        capabilities=[
            "batch-ingestion",
            "deterministic-deduplication",
            "annotations",
            "training-export",
            "ranking-lifecycle",
            "embedded-model-inference",
            "model-health-and-warmup",
            "embedding-contract",
            "invite-registration",
            "shared-group-onboarding",
        ],
    )
