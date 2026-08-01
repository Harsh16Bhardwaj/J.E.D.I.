"""Database-to-runtime adapter shared by embedded execution and /v1/score."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Batch, Job, ModelVersion, PreparedJob, ProcessingRun
from backend.schemas.modeling import PreparedJobV2
from backend.schemas.scoring import ScoreResponse
from backend.services.model_runtime import ModelRuntimeError, model_runtime
from backend.services.product import stable_hash


@dataclass(frozen=True)
class ScoringContext:
    batch: Batch
    run: ProcessingRun
    model: ModelVersion
    prepared: list[PreparedJobV2]
    input_hash: str


async def load_scoring_context(
    session: AsyncSession,
    *,
    batch_id: str,
    processing_run_id: str,
    model_version_id: str,
) -> ScoringContext:
    batch = await session.get(Batch, batch_id)
    run = await session.get(ProcessingRun, processing_run_id)
    model = await session.get(ModelVersion, model_version_id)
    if batch is None or run is None or model is None:
        raise HTTPException(
            status_code=404, detail="Batch, run, or model was not found."
        )
    if (
        run.batch_id != batch.id
        or run.stage != "ranking"
        or run.model_version_id != model.id
        or run.profile_version_id is None
        or run.feature_schema_version != "prepared-job-v2"
        or model.feature_schema_version != "prepared-job-v2"
    ):
        raise HTTPException(
            status_code=409,
            detail="The ranking run's pinned contracts are incompatible.",
        )
    rows = list(
        (
            await session.scalars(
                select(PreparedJob)
                .join(Job, PreparedJob.job_id == Job.id)
                .where(
                    Job.batch_id == batch.id,
                    PreparedJob.profile_version_id == run.profile_version_id,
                    PreparedJob.feature_schema_version == run.feature_schema_version,
                )
                .order_by(PreparedJob.job_id)
            )
        ).all()
    )
    if len(rows) != batch.job_count or batch.job_count > 500:
        raise HTTPException(
            status_code=422,
            detail="Prepared jobs do not cover a supported complete batch.",
        )
    prepared: list[PreparedJobV2] = []
    payload_hashes: list[str] = []
    for row in rows:
        if stable_hash(row.payload) != row.payload_hash:
            raise HTTPException(
                status_code=409, detail="A prepared job payload checksum is invalid."
            )
        try:
            value = PreparedJobV2.model_validate(row.payload)
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail="A prepared job does not match prepared-job-v2."
            ) from exc
        if value.job_id != row.job_id:
            raise HTTPException(
                status_code=409, detail="A prepared job identifier is inconsistent."
            )
        prepared.append(value)
        payload_hashes.append(row.payload_hash)
    input_hash = hashlib.sha256(
        json.dumps(payload_hashes, separators=(",", ":")).encode()
    ).hexdigest()
    return ScoringContext(
        batch=batch, run=run, model=model, prepared=prepared, input_hash=input_hash
    )


def _manifest_value(model: ModelVersion, name: str) -> str | None:
    value = (model.artifact_manifest or {}).get(name)
    return str(value) if value else None


async def score_context(context: ScoringContext) -> ScoreResponse:
    try:
        return await asyncio.to_thread(
            model_runtime.score,
            context.prepared,
            batch_id=context.batch.id,
            processing_run_id=context.run.id,
            model_version_id=context.model.id,
            expected_artifact_hash=_manifest_value(context.model, "artifactHash"),
            expected_bundle_version=_manifest_value(context.model, "modelVersion"),
        )
    except ModelRuntimeError:
        raise
