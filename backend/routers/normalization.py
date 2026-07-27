from fastapi import APIRouter, status

if __package__ == "routers":
    from schemas.common import NotImplementedResponse
    from schemas.normalization import NormalizeRequest
else:
    from backend.schemas.common import NotImplementedResponse
    from backend.schemas.normalization import NormalizeRequest

router = APIRouter(prefix="/v1", tags=["normalization"])


@router.post(
    "/normalize",
    response_model=NotImplementedResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def normalize(_: NormalizeRequest) -> NotImplementedResponse:
    return NotImplementedResponse(
        route="/v1/normalize",
        message="Job normalization will be added in the ML integration phase.",
    )
