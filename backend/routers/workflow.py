"""Normalization, annotations, training data, and ranking lifecycle routes."""

import csv
import json
from datetime import UTC, datetime
from io import StringIO
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import (
    Batch,
    Job,
    JobAnnotation,
    JobPrediction,
    JobState,
    ModelVersion,
    PreparedJob,
    ProcessingRun,
    ProfileVersion,
    TrainingExample,
    get_session,
)
from backend.routers.batches import ANNOTATION_FIELDS, get_batch_or_404
from backend.schemas.product import (
    AnnotationInput,
    AnnotationResponse,
    BatchAnnotationsRequest,
    BatchNormalizationResponse,
    RankingQueueResponse,
    RankingResponse,
    RankingSaveResponse,
    RankingsRequest,
    TrainingExamplesRequest,
    TrainingExamplesResponse,
    TrainingSelection,
)
from backend.services.email import enqueue_configured_mail_events
from backend.services.group_access import require_group_context, require_group_owner
from backend.services.product import prepare_job, stable_hash
from backend.services.ranking import persist_rankings

router = APIRouter(tags=["workflow"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


def annotation_complete(annotation: JobAnnotation) -> bool:
    return all(getattr(annotation, field) is not None for field in ANNOTATION_FIELDS)


async def save_annotation(
    session: AsyncSession,
    job: Job,
    body: AnnotationInput,
    member_id: str,
) -> AnnotationResponse:
    annotation = await session.scalar(
        select(JobAnnotation).where(
            JobAnnotation.group_member_id == member_id,
            JobAnnotation.job_id == job.id,
        )
    )
    if annotation is None:
        annotation = JobAnnotation(group_member_id=member_id, job_id=job.id)
        session.add(annotation)
    fields_set = body.model_fields_set
    for field in ANNOTATION_FIELDS:
        if field in fields_set:
            setattr(annotation, field, getattr(body, field))
    state = await session.scalar(
        select(JobState).where(
            JobState.group_member_id == member_id, JobState.job_id == job.id
        )
    )
    if "relevance_label" in fields_set:
        if state is None:
            state = JobState(group_member_id=member_id, job_id=job.id)
            session.add(state)
        state.relevance_label = (
            body.relevance_label.value if body.relevance_label is not None else None
        )
    await session.flush()
    return AnnotationResponse(
        job_id=job.id,
        relevance_label=state.relevance_label if state else None,
        apply_label=annotation.apply_label,
        complete=annotation_complete(annotation),
    )


@router.post(
    "/api/batches/{batch_id}/normalize",
    response_model=BatchNormalizationResponse,
)
async def normalize_batch(
    batch_id: str,
    _user: CurrentUser,
    session: DatabaseSession,
) -> BatchNormalizationResponse:
    batch = await session.scalar(
        select(Batch).where(Batch.id == batch_id).with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    if batch.status not in {"READY", "FAILED", "NORMALIZED", "RANKED"}:
        raise HTTPException(
            status_code=409,
            detail=f"Batch in {batch.status} cannot be normalized.",
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
    jobs = list(
        (
            await session.scalars(
                select(Job).where(Job.batch_id == batch_id).order_by(Job.id)
            )
        ).all()
    )
    idempotency_key = f"normalize:{batch_id}:{profile.id}:prepared-job-v2"
    run = await session.scalar(
        select(ProcessingRun).where(ProcessingRun.idempotency_key == idempotency_key)
    )
    if run and run.status == "SUCCEEDED":
        prepared_count = len(
            (
                await session.scalars(
                    select(PreparedJob)
                    .join(Job)
                    .where(
                        Job.batch_id == batch_id,
                        PreparedJob.profile_version_id == profile.id,
                        PreparedJob.feature_schema_version == "prepared-job-v2",
                    )
                )
            ).all()
        )
        return BatchNormalizationResponse(
            batch_id=batch_id,
            status="NORMALIZED",
            prepared_count=prepared_count,
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
            profile_version_id=profile.id,
            feature_schema_version="prepared-job-v2",
            started_at=datetime.now(UTC),
        )
        session.add(run)
    else:
        run.status = "RUNNING"
        run.attempt += 1
        run.profile_version_id = profile.id
        run.feature_schema_version = "prepared-job-v2"
        run.phase = "BUILDING_FEATURES"
        run.error_code = None
        run.error_message = None
        run.started_at = datetime.now(UTC)
        run.completed_at = None
    batch.status = "NORMALIZING"
    await session.commit()

    try:
        for job in jobs:
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
                        payload_hash=stable_hash(payload),
                        payload=payload,
                    )
                )
            else:
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
            failed_run.retryable = False
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
        status=batch.status,
        prepared_count=len(jobs),
        profile_version_id=profile.id,
        feature_schema_version="prepared-job-v2",
        replayed=False,
    )


@router.patch("/api/jobs/{job_id}/annotation", response_model=AnnotationResponse)
async def annotate_job(
    job_id: str,
    body: AnnotationInput,
    user: CurrentUser,
    session: DatabaseSession,
) -> AnnotationResponse:
    context = await require_group_context(session, user.id)
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    result = await save_annotation(session, job, body, context.membership.id)
    await session.commit()
    return result


@router.patch(
    "/api/batches/{batch_id}/annotations",
    response_model=list[AnnotationResponse],
)
async def annotate_batch(
    batch_id: str,
    body: BatchAnnotationsRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> list[AnnotationResponse]:
    context = await require_group_context(session, user.id)
    await get_batch_or_404(session, batch_id)
    job_ids = [item.job_id for item in body.annotations if item.job_id]
    jobs = {
        job.id: job
        for job in (
            await session.scalars(
                select(Job).where(Job.batch_id == batch_id, Job.id.in_(job_ids))
            )
        ).all()
    }
    missing = sorted(set(job_ids) - jobs.keys())
    if missing:
        raise HTTPException(
            status_code=404,
            detail={"message": "Jobs do not belong to this batch.", "jobIds": missing},
        )
    results = [
        await save_annotation(session, jobs[item.job_id], item, context.membership.id)
        for item in body.annotations
        if item.job_id
    ]
    await session.commit()
    return results


@router.post(
    "/api/batches/{batch_id}/training-examples",
    response_model=TrainingExamplesResponse,
)
async def add_training_examples(
    batch_id: str,
    body: TrainingExamplesRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> TrainingExamplesResponse:
    context = await require_group_owner(session, user.id)
    member_id = context.membership.id
    await get_batch_or_404(session, batch_id)
    rows = (
        await session.execute(
            select(Job, PreparedJob, JobAnnotation)
            .join(PreparedJob, PreparedJob.job_id == Job.id)
            .join(
                JobAnnotation,
                (JobAnnotation.job_id == Job.id)
                & (JobAnnotation.group_member_id == member_id),
            )
            .where(Job.batch_id == batch_id)
            .order_by(PreparedJob.updated_at.desc())
        )
    ).all()
    selected: dict[str, tuple[Job, PreparedJob, JobAnnotation]] = {}
    for job, prepared, annotation in rows:
        if job.id in selected or not annotation_complete(annotation):
            continue
        if (
            body.selection == TrainingSelection.YES_ONLY
            and annotation.apply_label is not True
        ):
            continue
        if (
            body.selection == TrainingSelection.NO_ONLY
            and annotation.apply_label is not False
        ):
            continue
        selected[job.id] = (job, prepared, annotation)

    for job, prepared, annotation in selected.values():
        example = await session.scalar(
            select(TrainingExample).where(
                TrainingExample.job_id == job.id,
                TrainingExample.profile_version_id == prepared.profile_version_id,
                TrainingExample.feature_schema_version
                == prepared.feature_schema_version,
            )
        )
        values = {
            "batch_id": batch_id,
            "profile_version_id": prepared.profile_version_id,
            "payload_hash": prepared.payload_hash,
            "feature_payload": prepared.payload,
            "annotated_by_group_member_id": member_id,
            "apply_label": annotation.apply_label,
            **{
                field: getattr(annotation, field)
                for field in ANNOTATION_FIELDS
                if field != "apply_label"
            },
        }
        if example is None:
            session.add(
                TrainingExample(
                    job_id=job.id,
                    feature_schema_version=prepared.feature_schema_version,
                    **values,
                )
            )
        else:
            for field, value in values.items():
                setattr(example, field, value)
    await session.commit()
    return TrainingExamplesResponse(
        batch_id=batch_id,
        selection=body.selection,
        added_or_updated_count=len(selected),
    )


@router.get(
    "/api/training-examples/export.csv",
    response_class=Response,
    responses={
        200: {
            "content": {
                "text/csv": {
                    "schema": {"type": "string"},
                }
            }
        }
    },
)
async def export_training_examples(
    user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    await require_group_owner(session, user.id)
    examples = list(
        (
            await session.scalars(
                select(TrainingExample).order_by(TrainingExample.created_at)
            )
        ).all()
    )
    feature_fields = sorted(
        {key for example in examples for key in example.feature_payload}
    )
    label_fields = [field for field in ANNOTATION_FIELDS if field != "apply_label"] + [
        "apply_label"
    ]
    output = StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "job_id",
            "batch_id",
            "profile_version_id",
            "feature_schema_version",
            "payload_hash",
            *feature_fields,
            *label_fields,
        ],
    )
    writer.writeheader()
    for example in examples:
        row = {
            "job_id": example.job_id,
            "batch_id": example.batch_id,
            "profile_version_id": example.profile_version_id,
            "feature_schema_version": example.feature_schema_version,
            "payload_hash": example.payload_hash,
            **{
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in example.feature_payload.items()
            },
            **{field: getattr(example, field) for field in label_fields},
        }
        writer.writerow(row)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="jedi-training-examples.csv"'
        },
    )


@router.post(
    "/api/batches/{batch_id}/rank",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RankingQueueResponse,
)
async def queue_ranking(
    batch_id: str,
    _user: CurrentUser,
    session: DatabaseSession,
) -> RankingQueueResponse:
    batch = await session.scalar(
        select(Batch).where(Batch.id == batch_id).with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    if batch.status not in {"NORMALIZED", "RANK_PENDING", "RANKED"}:
        raise HTTPException(
            status_code=409,
            detail="Normalize this batch before requesting ranking.",
        )
    profile = await session.scalar(
        select(ProfileVersion).where(ProfileVersion.active.is_(True))
    )
    model = await session.scalar(
        select(ModelVersion).where(ModelVersion.active.is_(True))
    )
    if profile is None or model is None:
        raise HTTPException(
            status_code=409,
            detail="Activate both a profile and model before ranking.",
        )
    prepared_count = await session.scalar(
        select(func.count())
        .select_from(PreparedJob)
        .join(Job, PreparedJob.job_id == Job.id)
        .where(
            Job.batch_id == batch_id,
            PreparedJob.profile_version_id == profile.id,
            PreparedJob.feature_schema_version == model.feature_schema_version,
        )
    )
    if (prepared_count or 0) != batch.job_count:
        raise HTTPException(
            status_code=409,
            detail=(
                "Normalize every job with the active profile and model "
                "feature schema before ranking."
            ),
        )
    existing = await session.scalar(
        select(ProcessingRun).where(
            ProcessingRun.batch_id == batch_id,
            ProcessingRun.stage == "ranking",
            ProcessingRun.status.in_(["QUEUED", "RUNNING"]),
        )
    )
    if existing is not None and (
        existing.profile_version_id != profile.id
        or existing.model_version_id != model.id
        or existing.feature_schema_version != model.feature_schema_version
    ):
        raise HTTPException(
            status_code=409,
            detail="A ranking run is already queued with different versions.",
        )
    if existing is None:
        existing = ProcessingRun(
            batch_id=batch_id,
            idempotency_key=f"rank:{batch_id}:{uuid4().hex}",
            status="QUEUED",
            stage="ranking",
            phase="QUEUED",
            profile_version_id=profile.id,
            model_version_id=model.id,
            feature_schema_version=model.feature_schema_version,
        )
        session.add(existing)
    batch.status = "RANK_PENDING"
    await session.commit()
    return RankingQueueResponse(
        batch_id=batch_id,
        status=batch.status,
        processing_run_id=existing.id,
        pending_execution=True,
    )


@router.post(
    "/api/batches/{batch_id}/rankings",
    response_model=RankingSaveResponse,
)
async def save_rankings(
    batch_id: str,
    body: RankingsRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> RankingSaveResponse:
    context = await require_group_context(session, user.id)
    batch = await get_batch_or_404(session, batch_id)
    queued_run = await session.scalar(
        select(ProcessingRun)
        .where(
            ProcessingRun.batch_id == batch_id,
            ProcessingRun.stage == "ranking",
            ProcessingRun.status.in_(["QUEUED", "RUNNING"]),
            ProcessingRun.profile_version_id == body.profile_version_id,
            ProcessingRun.model_version_id == body.model_version_id,
        )
        .order_by(ProcessingRun.created_at.desc())
    )
    if queued_run is None:
        raise HTTPException(
            status_code=409,
            detail="No matching queued ranking run exists for this batch.",
        )
    ranking_count = await persist_rankings(session, batch, queued_run, body)
    queued_run.status = "SUCCEEDED"
    queued_run.phase = "COMPLETED"
    queued_run.retryable = None
    queued_run.completed_at = datetime.now(UTC)
    queued_run.lease_token = None
    queued_run.lease_expires_at = None
    await session.commit()
    await enqueue_configured_mail_events(
        session,
        batch,
        queued_run,
        group_id=context.group.id,
    )
    return RankingSaveResponse(
        batch_id=batch_id,
        status=batch.status,
        ranking_count=ranking_count,
        email_delivery=None,
    )


@router.get(
    "/api/batches/{batch_id}/rankings",
    response_model=list[RankingResponse],
)
async def get_rankings(
    batch_id: str,
    _user: CurrentUser,
    session: DatabaseSession,
    run_id: Annotated[str | None, Query(alias="runId")] = None,
) -> list[RankingResponse]:
    await get_batch_or_404(session, batch_id)
    if run_id:
        run = await session.get(ProcessingRun, run_id)
        if (
            run is None
            or run.batch_id != batch_id
            or run.stage != "ranking"
            or run.status != "SUCCEEDED"
        ):
            raise HTTPException(
                status_code=404,
                detail="Successful ranking run not found for this batch.",
            )
    else:
        run = await session.scalar(
            select(ProcessingRun)
            .where(
                ProcessingRun.batch_id == batch_id,
                ProcessingRun.stage == "ranking",
                ProcessingRun.status == "SUCCEEDED",
            )
            .order_by(ProcessingRun.completed_at.desc())
        )
    if run is None:
        return []
    predictions = (
        await session.scalars(
            select(JobPrediction)
            .where(JobPrediction.processing_run_id == run.id)
            .order_by(JobPrediction.rank)
        )
    ).all()
    return [
        RankingResponse(
            job_id=item.job_id,
            rank=item.rank,
            jedi_preference_score=item.jedi_preference_score,
            apply_preference_probability=item.apply_preference_probability,
            component_scores=item.component_scores,
            ranking_score=item.ranking_score,
            ranking_strategy=item.ranking_strategy,
            apply_threshold=item.apply_threshold,
            model_apply_decision=item.model_apply_decision,
            apply_recommendation=item.apply_recommendation,
            output_schema_version=item.output_schema_version,
            profile_version_id=item.profile_version_id,
            model_version_id=item.model_version_id,
            processing_run_id=item.processing_run_id,
        )
        for item in predictions
    ]
