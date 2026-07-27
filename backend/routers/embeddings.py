from fastapi import APIRouter, status

if __package__ == "routers":
    from schemas.common import NotImplementedResponse
    from schemas.embeddings import EmbedRequest
else:
    from backend.schemas.common import NotImplementedResponse
    from backend.schemas.embeddings import EmbedRequest

router = APIRouter(prefix="/v1", tags=["embeddings"])


@router.post(
    "/embed",
    response_model=NotImplementedResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def embed(_: EmbedRequest) -> NotImplementedResponse:
    return NotImplementedResponse(
        route="/v1/embed",
        message="Semantic embeddings will be added in the ML integration phase.",
    )
