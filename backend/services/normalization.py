"""Shared, idempotent batch normalization for uploads and scraper imports."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Batch, Job, PreparedJob, ProcessingRun, ProfileVersion
from backend.schemas.product import BatchNormalizationResponse
from backend.services.fx import FX_POLICY_VERSION, normalize_job_salary_to_inr
from backend.services.product import prepare_job, stable_hash


async def normalize_batch_service(
    session: AsyncSession,
    batch_id: str,
    *,
    apply_inr_policy: bool = False,
    trigger: str = "USER",
) -> BatchNormalizationResponse:
    batch = await session.scalar(
        select(Batch).where(Batch.id == batch_id).with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    # NORMALIZING is recoverable: a browser/server interruption may leave the
    # durable scraper lifecycle at this checkpoint before the idempotent retry.
    if batch.status not in {
        "READY",
        "FAILED",
        "NORMALIZING",
        "NORMALIZED",
        "RANKED",
    }:
        raise HTTPException(
            status_code=409, detail=f"Batch in {batch.status} cannot be normalized."
        )
    profile = await session.scalar(
        select(ProfileVersion)
        .where(ProfileVersion.active.is_(True))
        .order_by(ProfileVersion.created_at.desc())
    )
    if profile is None:
        raise HTTPException(
            status_code=409,
            detail="Create and activate a ProfileVersion before normalization.",
        )
    policy = FX_POLICY_VERSION if apply_inr_policy else "legacy-v1"
    jobs = list(
        (
            await session.scalars(
                select(Job).where(Job.batch_id == batch_id).order_by(Job.id)
            )
        ).all()
    )
    idempotency_key = f"normalize:{batch_id}:{profile.id}:prepared-job-v2:{policy}"
    run = await session.scalar(
        select(ProcessingRun).where(ProcessingRun.idempotency_key == idempotency_key)
    )
    if run and run.status == "SUCCEEDED":
        return BatchNormalizationResponse(
            batch_id=batch_id,
            status="NORMALIZED",
            prepared_count=len(jobs),
            profile_version_id=profile.id,
            feature_schema_version="prepared-job-v2",
            replayed=True,
        )
    if run is None:
        run = ProcessingRun(
            batch_id=batch_id,
            idempotency_key=idempotency_key,
            status="RUNNING",
            stage="normalization",
            phase="BUILDING_FEATURES",
            attempt=1,
            trigger=trigger,
            profile_version_id=profile.id,
            feature_schema_version="prepared-job-v2",
            normalization_policy_version=policy,
            started_at=datetime.now(UTC),
        )
        session.add(run)
    else:
        run.status = "RUNNING"
        run.attempt += 1
        run.phase = "BUILDING_FEATURES"
        run.error_code = None
        run.error_message = None
        run.started_at = datetime.now(UTC)
        run.completed_at = None
    batch.status = "NORMALIZING"
    await session.commit()
    try:
        for job in jobs:
            if apply_inr_policy:
                await normalize_job_salary_to_inr(job)
            payload = prepare_job(
                job, profile, feature_reference_at=batch.generated_at
            ).model_dump(mode="json", by_alias=True)
            existing = await session.scalar(
                select(PreparedJob).where(
                    PreparedJob.job_id == job.id,
                    PreparedJob.profile_version_id == profile.id,
                    PreparedJob.feature_schema_version == "prepared-job-v2",
                )
            )
            if existing is None:
                session.add(
                    PreparedJob(
                        job_id=job.id,
                        profile_version_id=profile.id,
                        feature_schema_version="prepared-job-v2",
                        normalization_policy_version=policy,
                        payload_hash=stable_hash(payload),
                        payload=payload,
                    )
                )
            else:
                existing.normalization_policy_version = policy
                existing.payload_hash = stable_hash(payload)
                existing.payload = payload
        batch.status = "NORMALIZED"
        run.status = "SUCCEEDED"
        run.phase = "COMPLETED"
        run.completed_at = datetime.now(UTC)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        failed_batch = await session.get(Batch, batch_id)
        failed_run = await session.scalar(
            select(ProcessingRun).where(
                ProcessingRun.idempotency_key == idempotency_key
            )
        )
        if failed_batch:
            failed_batch.status = "FAILED"
        if failed_run:
            failed_run.status = "FAILED"
            failed_run.phase = "FAILED"
            failed_run.retryable = True
            failed_run.error_code = "NORMALIZATION_FAILED"
            failed_run.error_message = "Normalization failed."
            failed_run.completed_at = datetime.now(UTC)
        await session.commit()
        raise HTTPException(
            status_code=500,
            detail="Normalization failed; the batch can be retried.",
        ) from exc
    return BatchNormalizationResponse(
        batch_id=batch_id,
        status="NORMALIZED",
        prepared_count=len(jobs),
        profile_version_id=profile.id,
        feature_schema_version="prepared-job-v2",
        replayed=False,
    )
