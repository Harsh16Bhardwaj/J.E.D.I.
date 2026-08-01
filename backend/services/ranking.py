"""Shared validated and idempotent ranking persistence."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import (
    Batch,
    Job,
    JobPrediction,
    ModelVersion,
    ProcessingRun,
    ProfileVersion,
)
from backend.schemas.product import RankingsRequest


async def persist_rankings(
    session: AsyncSession,
    batch: Batch,
    run: ProcessingRun,
    body: RankingsRequest,
) -> int:
    """Validate ranking ownership and upsert one worker/manual delivery."""
    if (
        run.batch_id != batch.id
        or run.profile_version_id != body.profile_version_id
        or run.model_version_id != body.model_version_id
    ):
        raise HTTPException(
            status_code=409,
            detail="Ranking versions do not match the queued processing run.",
        )
    profile = await session.get(ProfileVersion, body.profile_version_id)
    model = await session.get(ModelVersion, body.model_version_id)
    if profile is None or model is None:
        raise HTTPException(
            status_code=422,
            detail="profileVersionId or modelVersionId does not exist.",
        )
    if model.feature_schema_version != run.feature_schema_version:
        raise HTTPException(
            status_code=409,
            detail="Model and processing-run feature schemas do not match.",
        )
    job_ids = {item.job_id for item in body.rankings}
    existing_job_ids = set(
        (
            await session.scalars(
                select(Job.id).where(
                    Job.batch_id == batch.id,
                )
            )
        ).all()
    )
    if len(body.rankings) != batch.job_count or existing_job_ids != job_ids:
        raise HTTPException(
            status_code=422,
            detail="Rankings must cover the batch's exact complete job set.",
        )
    if model.feature_schema_version == "prepared-job-v2" and any(
        item.ranking_score is None
        or item.apply_threshold is None
        or item.model_apply_decision is None
        or item.apply_recommendation is None
        for item in body.rankings
    ):
        raise HTTPException(
            status_code=422,
            detail="V2 rankings require score, threshold, and model decision fields.",
        )

    for item in body.rankings:
        prediction = await session.scalar(
            select(JobPrediction).where(
                JobPrediction.job_id == item.job_id,
                JobPrediction.processing_run_id == run.id,
            )
        )
        values = {
            "rank": item.rank,
            "jedi_preference_score": item.jedi_preference_score,
            "apply_preference_probability": item.apply_preference_probability,
            "component_scores": item.component_scores,
            "ranking_score": (
                item.ranking_score
                if item.ranking_score is not None
                else item.jedi_preference_score
            ),
            "ranking_strategy": item.ranking_strategy,
            "apply_threshold": item.apply_threshold,
            "model_apply_decision": item.model_apply_decision,
            "apply_recommendation": item.apply_recommendation,
            "output_schema_version": item.output_schema_version,
        }
        if prediction is None:
            session.add(
                JobPrediction(
                    job_id=item.job_id,
                    batch_id=batch.id,
                    profile_version_id=profile.id,
                    model_version_id=model.id,
                    processing_run_id=run.id,
                    **values,
                )
            )
        else:
            for field, value in values.items():
                setattr(prediction, field, value)

    batch.status = "RANKED"
    batch.ranked_at = datetime.now(UTC)
    await session.flush()
    return len(body.rankings)


async def ranking_delivery_exists(
    session: AsyncSession,
    processing_run_id: str,
    body: RankingsRequest,
) -> bool:
    """Recognize an exact retry after a successful callback cleared its lease."""
    predictions = list(
        (
            await session.scalars(
                select(JobPrediction).where(
                    JobPrediction.processing_run_id == processing_run_id,
                )
            )
        ).all()
    )
    if len(predictions) != len(body.rankings):
        return False
    stored = {item.job_id: item for item in predictions}
    for item in body.rankings:
        prediction = stored.get(item.job_id)
        if prediction is None:
            return False
        if (
            prediction.rank != item.rank
            or prediction.jedi_preference_score != item.jedi_preference_score
            or prediction.apply_preference_probability
            != item.apply_preference_probability
            or prediction.component_scores != item.component_scores
            or prediction.ranking_score
            != (
                item.ranking_score
                if item.ranking_score is not None
                else item.jedi_preference_score
            )
            or prediction.ranking_strategy != item.ranking_strategy
            or prediction.apply_threshold != item.apply_threshold
            or prediction.model_apply_decision != item.model_apply_decision
            or prediction.apply_recommendation != item.apply_recommendation
            or prediction.output_schema_version != item.output_schema_version
        ):
            return False
    return True
