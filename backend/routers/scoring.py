from fastapi import APIRouter, status

if __package__ == "routers":
    from schemas.common import NotImplementedResponse
    from schemas.scoring import ScoreRequest
else:
    from backend.schemas.common import NotImplementedResponse
    from backend.schemas.scoring import ScoreRequest

router = APIRouter(prefix="/v1", tags=["scoring"])


@router.post(
    "/score",
    response_model=NotImplementedResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def score(_: ScoreRequest) -> NotImplementedResponse:
    return NotImplementedResponse(
        route="/v1/score",
        message="Model inference will be added in the ML integration phase.",
    )
