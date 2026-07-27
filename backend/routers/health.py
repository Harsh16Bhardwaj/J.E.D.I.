from fastapi import APIRouter

if __package__ == "routers":
    from config import get_settings
    from schemas.common import HealthResponse, ServiceInfoResponse, ServiceMetadata
else:
    from backend.config import get_settings
    from backend.schemas.common import (
        HealthResponse,
        ServiceInfoResponse,
        ServiceMetadata,
    )

router = APIRouter(tags=["service"])


@router.get("/", response_model=ServiceMetadata)
def root() -> ServiceMetadata:
    settings = get_settings()
    return ServiceMetadata(
        service=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        status="foundation",
    )


@router.get("/health/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(service="jedi-ml", status="ok")


@router.get("/health/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    return HealthResponse(service="jedi-ml", status="ready")


@router.get("/v1/info", response_model=ServiceInfoResponse)
def info() -> ServiceInfoResponse:
    settings = get_settings()
    return ServiceInfoResponse(
        service="jedi-ml",
        api_version=settings.app_version,
        capabilities=[
            "normalization-contract",
            "embedding-contract",
            "scoring-contract",
        ],
    )
