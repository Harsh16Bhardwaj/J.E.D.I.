"""Service-authenticated scoring contract for localhost and future workers."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import ServiceToken
from backend.database import get_session
from backend.schemas.scoring import ScoreRequest, ScoreResponse
from backend.services.model_runtime import ModelRuntimeError
from backend.services.model_scoring import load_scoring_context, score_context

router = APIRouter(prefix="/v1", tags=["scoring"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


@router.post("/score", response_model=ScoreResponse)
async def score(
    body: ScoreRequest,
    _service: ServiceToken,
    session: DatabaseSession,
) -> ScoreResponse:
    context = await load_scoring_context(
        session,
        batch_id=body.batch_id,
        processing_run_id=body.processing_run_id,
        model_version_id=body.model_version_id,
    )
    try:
        return await score_context(context)
    except ModelRuntimeError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
                if exc.retryable
                else status.HTTP_409_CONFLICT
            ),
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
