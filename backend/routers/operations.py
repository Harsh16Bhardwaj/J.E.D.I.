"""Embedded execution, user-visible history, retry, and worker lease routes."""

import asyncio
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from secrets import token_urlsafe
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser, ServiceToken
from backend.config import get_settings
from backend.database import (
    Batch,
    Job,
    ModelInvocation,
    ModelVersion,
    PreparedJob,
    ProcessingRun,
    get_session,
)
from backend.routers.batches import get_batch_or_404
from backend.schemas.product import (
    ModelInvocationResponse,
    ProcessingRunResponse,
    RankingExecutionResponse,
    RankingItem,
    RankingRetryResponse,
    RankingSaveResponse,
    RankingsRequest,
    WorkerClaimResponse,
    WorkerFailureRequest,
    WorkerFailureResponse,
    WorkerHeartbeatResponse,
    WorkerPreparedJob,
)
from backend.services.email import enqueue_configured_mail_events
from backend.services.group_access import require_group_context
from backend.services.model_runtime import ModelRuntimeError, model_runtime
from backend.services.model_scoring import load_scoring_context, score_context
from backend.services.ranking import persist_rankings, ranking_delivery_exists

router = APIRouter(tags=["processing"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
LeaseToken = Annotated[str | None, Header(alias="X-JEDI-LEASE-TOKEN")]
LEASE_DURATION = timedelta(minutes=5)
MAX_ATTEMPTS = 3
INLINE_ATTEMPTS = 2


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _require_active_lease(
    run: ProcessingRun,
    supplied_token: str | None,
    now: datetime,
) -> None:
    expires_at = _aware(run.lease_expires_at)
    token_matches = compare_digest(
        (supplied_token or "").encode(),
        (run.lease_token or "").encode(),
    )
    if (
        run.status != "RUNNING"
        or not run.lease_token
        or not token_matches
        or expires_at is None
        or expires_at <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The processing lease is missing, expired, or no longer active.",
        )


def _invocation_response(
    invocation: ModelInvocation | None,
) -> ModelInvocationResponse | None:
    if invocation is None:
        return None
    return ModelInvocationResponse(
        id=invocation.id,
        attempt=invocation.attempt,
        status=invocation.status,
        artifact_hash=invocation.artifact_hash,
        input_count=invocation.input_count,
        output_count=invocation.output_count,
        cold_start=invocation.cold_start,
        timings_ms=invocation.timings_ms,
        error_code=invocation.error_code,
        raw_response=invocation.raw_response,
        started_at=invocation.started_at,
        completed_at=invocation.completed_at,
    )


def _effective_status(run: ProcessingRun, now: datetime) -> str:
    expires_at = _aware(run.lease_expires_at)
    if run.status == "RUNNING" and expires_at is not None and expires_at <= now:
        return "STALE"
    return run.status


async def _batch_has_success(
    session: AsyncSession, batch_id: str, exclude_id: str
) -> bool:
    successful = await session.scalar(
        select(ProcessingRun.id).where(
            ProcessingRun.batch_id == batch_id,
            ProcessingRun.stage == "ranking",
            ProcessingRun.status == "SUCCEEDED",
            ProcessingRun.id != exclude_id,
        )
    )
    return successful is not None


async def _record_failed_invocation(
    session: AsyncSession,
    *,
    context,
    attempt: int,
    error: ModelRuntimeError,
    started_at: datetime,
) -> None:
    health = model_runtime.health()
    manifest = context.model.artifact_manifest or {}
    session.add(
        ModelInvocation(
            processing_run_id=context.run.id,
            model_version_id=context.model.id,
            attempt=attempt,
            status="FAILED",
            request_contract_version="score-request-v1",
            response_contract_version="score-response-v1",
            feature_schema_version="prepared-job-v2",
            artifact_hash=str(
                manifest.get("artifactHash") or health.artifact_hash or "unknown"
            ),
            input_hash=context.input_hash,
            input_count=len(context.prepared),
            output_count=0,
            raw_response=None,
            cold_start=health.cold_start,
            timings_ms=None,
            error_code=error.code,
            error_message=str(error)[:500],
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
    )


@router.get(
    "/api/batches/{batch_id}/processing-runs",
    response_model=list[ProcessingRunResponse],
)
async def list_processing_runs(
    batch_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> list[ProcessingRunResponse]:
    await get_batch_or_404(session, batch_id)
    context = await require_group_context(session, user.id)
    is_owner = context.group.owner_id == user.id
    runs = (
        await session.scalars(
            select(ProcessingRun)
            .where(ProcessingRun.batch_id == batch_id)
            .order_by(ProcessingRun.created_at.desc())
        )
    ).all()
    model_ids = {run.model_version_id for run in runs if run.model_version_id}
    model_names = dict(
        (
            await session.execute(
                select(ModelVersion.id, ModelVersion.name).where(
                    ModelVersion.id.in_(model_ids)
                )
            )
        ).all()
    ) if model_ids else {}
    now = datetime.now(UTC)
    output: list[ProcessingRunResponse] = []
    for run in runs:
        invocation = await session.scalar(
            select(ModelInvocation)
            .where(ModelInvocation.processing_run_id == run.id)
            .order_by(ModelInvocation.attempt.desc())
        )
        effective = _effective_status(run, now)
        output.append(
            ProcessingRunResponse(
                id=run.id,
                stage=run.stage,
                status=run.status,
                effective_status=effective,
                phase=run.phase,
                attempt=run.attempt,
                retryable=True if effective == "STALE" else run.retryable,
                trigger=run.trigger,
                retry_of_run_id=run.retry_of_run_id,
                profile_version_id=run.profile_version_id,
                model_version_id=run.model_version_id,
                model_name=model_names.get(run.model_version_id),
                feature_schema_version=run.feature_schema_version,
                error_code=run.error_code,
                error_message=run.error_message,
                started_at=run.started_at,
                heartbeat_at=run.heartbeat_at,
                completed_at=run.completed_at,
                created_at=run.created_at,
                invocation=(
                    _invocation_response(invocation)
                    if is_owner
                    else (
                        _invocation_response(invocation).model_copy(
                            update={"raw_response": None}
                        )
                        if invocation
                        else None
                    )
                ),
            )
        )
    return output


@router.post(
    "/api/processing-runs/{run_id}/execute",
    response_model=RankingExecutionResponse,
)
async def execute_processing_run(
    run_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> RankingExecutionResponse:
    """Claim and execute one durable embedded inference run idempotently."""
    group_context = await require_group_context(session, user.id)
    now = datetime.now(UTC)
    run = await session.scalar(
        select(ProcessingRun).where(ProcessingRun.id == run_id).with_for_update()
    )
    if run is None or run.stage != "ranking":
        raise HTTPException(status_code=404, detail="Ranking run not found.")
    batch = await get_batch_or_404(session, run.batch_id)
    if run.status == "SUCCEEDED":
        latest = await session.scalar(
            select(ModelInvocation)
            .where(
                ModelInvocation.processing_run_id == run.id,
                ModelInvocation.status == "SUCCEEDED",
            )
            .order_by(ModelInvocation.attempt.desc())
        )
        return RankingExecutionResponse(
            batch_id=batch.id,
            status=run.status,
            processing_run_id=run.id,
            ranking_count=latest.output_count if latest else batch.job_count,
            cold_start=bool(latest and latest.cold_start),
            timings_ms=(latest.timings_ms or {}) if latest else {},
        )
    if run.status == "RUNNING":
        if _effective_status(run, now) == "STALE":
            raise HTTPException(
                status_code=409, detail="The run lease expired; create a retry run."
            )
        return RankingExecutionResponse(
            batch_id=batch.id,
            status="RUNNING",
            processing_run_id=run.id,
            ranking_count=0,
            cold_start=False,
            timings_ms={},
        )
    if run.status != "QUEUED":
        raise HTTPException(status_code=409, detail="Only queued runs can be executed.")
    if run.profile_version_id is None or run.model_version_id is None:
        raise HTTPException(
            status_code=409, detail="The ranking run is missing version pins."
        )

    run.status = "RUNNING"
    run.phase = "LOADING_MODEL"
    run.started_at = run.started_at or now
    run.heartbeat_at = now
    run.lease_token = token_urlsafe(32)
    run.lease_expires_at = now + LEASE_DURATION
    run.retryable = None
    run.error_code = None
    run.error_message = None
    batch.status = "RANKING"
    await session.commit()

    try:
        context = await load_scoring_context(
            session,
            batch_id=batch.id,
            processing_run_id=run.id,
            model_version_id=run.model_version_id,
        )
    except HTTPException:
        run = await session.get(ProcessingRun, run_id)
        batch = await session.get(Batch, batch.id)
        if run:
            run.status = "FAILED"
            run.phase = "FAILED"
            run.retryable = False
            run.error_code = "SCORING_CONTEXT_INVALID"
            run.error_message = (
                "Prepared rows or pinned model contracts are incompatible."
            )
            run.completed_at = datetime.now(UTC)
            run.lease_token = None
            run.lease_expires_at = None
        if batch:
            batch.status = (
                "RANKED"
                if await _batch_has_success(session, batch.id, run_id)
                else "FAILED"
            )
        await session.commit()
        raise

    response = None
    last_error: ModelRuntimeError | None = None
    for inline_index in range(INLINE_ATTEMPTS):
        attempt = run.attempt + 1
        started_at = datetime.now(UTC)
        run.attempt = attempt
        run.phase = (
            "LOADING_MODEL" if model_runtime.health().state != "READY" else "SCORING"
        )
        run.heartbeat_at = started_at
        run.lease_expires_at = started_at + LEASE_DURATION
        await session.commit()
        try:
            response = await asyncio.wait_for(
                score_context(context),
                timeout=get_settings().model_execution_timeout_seconds,
            )
            break
        except TimeoutError:
            last_error = ModelRuntimeError(
                "INFERENCE_TIMEOUT",
                "Inference exceeded its application deadline",
                retryable=True,
            )
        except ModelRuntimeError as exc:
            last_error = exc
        await _record_failed_invocation(
            session,
            context=context,
            attempt=attempt,
            error=last_error,
            started_at=started_at,
        )
        await session.commit()
        if not last_error.retryable or inline_index + 1 >= INLINE_ATTEMPTS:
            break

    if response is None:
        assert last_error is not None
        run = await session.get(ProcessingRun, run_id)
        batch = await session.get(Batch, context.batch.id)
        if run:
            run.status = "FAILED"
            run.phase = "FAILED"
            run.retryable = last_error.retryable
            run.error_code = last_error.code
            run.error_message = str(last_error)[:500]
            run.completed_at = datetime.now(UTC)
            run.lease_token = None
            run.lease_expires_at = None
        if batch:
            batch.status = (
                "RANKED"
                if await _batch_has_success(session, batch.id, run_id)
                else "FAILED"
            )
        await session.commit()
        raise HTTPException(
            status_code=503 if last_error.retryable else 409,
            detail={"code": last_error.code, "message": str(last_error)},
        )

    run = await session.get(ProcessingRun, run_id)
    batch = await session.get(Batch, context.batch.id)
    assert run is not None and batch is not None
    run.phase = "PERSISTING"
    rankings = RankingsRequest(
        profile_version_id=run.profile_version_id,
        model_version_id=run.model_version_id,
        rankings=[
            RankingItem(
                job_id=item.job_id,
                rank=item.rank,
                jedi_preference_score=item.jedi_preference_score,
                apply_preference_probability=item.apply_probability,
                component_scores=item.component_scores,
                ranking_score=item.ranking_score,
                ranking_strategy=response.ranking_strategy,
                apply_threshold=response.decision_threshold,
                model_apply_decision=item.model_apply_decision,
                apply_recommendation=item.apply_recommendation,
                output_schema_version=response.response_contract_version,
            )
            for item in response.results
        ],
    )
    try:
        persistence_started = perf_counter()
        ranking_count = await persist_rankings(session, batch, run, rankings)
        persistence_ms = (perf_counter() - persistence_started) * 1000.0
        invocation_timings = {
            **response.timings_ms.model_dump(by_alias=True),
            "database": persistence_ms,
        }
        completed_at = datetime.now(UTC)
        session.add(
            ModelInvocation(
                processing_run_id=run.id,
                model_version_id=run.model_version_id,
                attempt=run.attempt,
                status="SUCCEEDED",
                request_contract_version="score-request-v1",
                response_contract_version=response.response_contract_version,
                feature_schema_version=response.feature_schema_version,
                artifact_hash=response.artifact_hash,
                input_hash=context.input_hash,
                input_count=len(context.prepared),
                output_count=len(response.results),
                raw_response=response.model_dump(mode="json", by_alias=True),
                cold_start=response.cold_start,
                timings_ms=invocation_timings,
                started_at=started_at,
                completed_at=completed_at,
            )
        )
        run.status = "SUCCEEDED"
        run.phase = "COMPLETED"
        run.retryable = None
        run.completed_at = completed_at
        run.heartbeat_at = completed_at
        run.lease_token = None
        run.lease_expires_at = None
        await session.commit()
    except Exception as exc:
        await session.rollback()
        run = await session.get(ProcessingRun, run_id)
        batch = await session.get(Batch, context.batch.id)
        if run:
            session.add(
                ModelInvocation(
                    processing_run_id=run.id,
                    model_version_id=run.model_version_id,
                    attempt=run.attempt,
                    status="FAILED",
                    request_contract_version="score-request-v1",
                    response_contract_version=response.response_contract_version,
                    feature_schema_version=response.feature_schema_version,
                    artifact_hash=response.artifact_hash,
                    input_hash=context.input_hash,
                    input_count=len(context.prepared),
                    output_count=len(response.results),
                    raw_response=response.model_dump(mode="json", by_alias=True),
                    cold_start=response.cold_start,
                    timings_ms=response.timings_ms.model_dump(by_alias=True),
                    error_code="PERSISTENCE_FAILED",
                    error_message="The complete model output could not be persisted.",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                )
            )
            run.status = "FAILED"
            run.phase = "FAILED"
            run.retryable = True
            run.error_code = "PERSISTENCE_FAILED"
            run.error_message = "The complete model output could not be persisted."
            run.completed_at = datetime.now(UTC)
            run.lease_token = None
            run.lease_expires_at = None
        if batch:
            batch.status = (
                "RANKED"
                if await _batch_has_success(session, batch.id, run_id)
                else "FAILED"
            )
        await session.commit()
        raise HTTPException(
            status_code=503,
            detail="Model output persistence failed.",
        ) from exc

    await enqueue_configured_mail_events(
        session,
        batch,
        run,
        group_id=group_context.group.id,
    )
    return RankingExecutionResponse(
        batch_id=batch.id,
        status=run.status,
        processing_run_id=run.id,
        ranking_count=ranking_count,
        cold_start=response.cold_start,
        timings_ms=invocation_timings,
    )


@router.post(
    "/api/processing-runs/{run_id}/retry",
    response_model=RankingRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_processing_run(
    run_id: str,
    _user: CurrentUser,
    session: DatabaseSession,
) -> RankingRetryResponse:
    now = datetime.now(UTC)
    run = await session.scalar(
        select(ProcessingRun).where(ProcessingRun.id == run_id).with_for_update()
    )
    if run is None or run.stage != "ranking":
        raise HTTPException(status_code=404, detail="Ranking run not found.")
    batch = await get_batch_or_404(session, run.batch_id)
    if _effective_status(run, now) == "STALE":
        run.status = "FAILED"
        run.phase = "FAILED"
        run.retryable = False
        run.phase = "FAILED"
        run.retryable = True
        run.error_code = "INVOCATION_INTERRUPTED"
        run.error_message = "The platform invocation ended before completing the run."
        run.completed_at = now
        run.lease_token = None
        run.lease_expires_at = None
    if run.status != "FAILED" or run.retryable is False:
        raise HTTPException(status_code=409, detail="This run is not retryable.")
    existing = await session.scalar(
        select(ProcessingRun).where(
            ProcessingRun.retry_of_run_id == run.id,
            ProcessingRun.status.in_(["QUEUED", "RUNNING"]),
        )
    )
    replacement = existing or ProcessingRun(
        batch_id=run.batch_id,
        idempotency_key=f"retry:{run.id}:{uuid4().hex}",
        status="QUEUED",
        stage="ranking",
        phase="QUEUED",
        attempt=0,
        retryable=None,
        trigger="MANUAL_RETRY",
        retry_of_run_id=run.id,
        profile_version_id=run.profile_version_id,
        model_version_id=run.model_version_id,
        feature_schema_version=run.feature_schema_version,
    )
    if existing is None:
        session.add(replacement)
    batch.status = "RANK_PENDING"
    await session.commit()
    return RankingRetryResponse(
        batch_id=batch.id,
        status=batch.status,
        processing_run_id=replacement.id,
        pending_execution=True,
        retry_of_run_id=run.id,
    )


@router.post(
    "/internal/processing-runs/claim",
    response_model=WorkerClaimResponse,
    responses={204: {"description": "No ranking work is currently claimable."}},
)
async def claim_processing_run(
    _service: ServiceToken,
    session: DatabaseSession,
) -> WorkerClaimResponse | Response:
    now = datetime.now(UTC)
    exhausted = list(
        (
            await session.scalars(
                select(ProcessingRun)
                .where(
                    ProcessingRun.stage == "ranking",
                    ProcessingRun.status == "RUNNING",
                    ProcessingRun.attempt >= MAX_ATTEMPTS,
                    ProcessingRun.lease_expires_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    for run in exhausted:
        run.status = "FAILED"
        run.error_code = "RETRY_EXHAUSTED"
        run.error_message = "Worker lease expired after the maximum attempts."
        run.completed_at = now
        run.lease_token = None
        run.lease_expires_at = None
        batch = await session.get(Batch, run.batch_id)
        if batch:
            batch.status = "NORMALIZED"

    for _ in range(10):
        run = await session.scalar(
            select(ProcessingRun)
            .where(
                ProcessingRun.stage == "ranking",
                ProcessingRun.attempt < MAX_ATTEMPTS,
                or_(
                    ProcessingRun.status == "QUEUED",
                    and_(
                        ProcessingRun.status == "RUNNING",
                        ProcessingRun.lease_expires_at <= now,
                    ),
                ),
            )
            .order_by(ProcessingRun.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if run is None:
            await session.commit()
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        if (
            run.profile_version_id is None
            or run.model_version_id is None
            or run.feature_schema_version is None
        ):
            run.status = "FAILED"
            run.phase = "FAILED"
            run.retryable = False
            run.error_code = "RUN_VERSION_MISSING"
            run.error_message = "The ranking run has incomplete version pins."
            run.completed_at = now
            batch = await session.get(Batch, run.batch_id)
            if batch:
                batch.status = "NORMALIZED"
            await session.flush()
            continue

        prepared_jobs = list(
            (
                await session.scalars(
                    select(PreparedJob)
                    .join(Job, PreparedJob.job_id == Job.id)
                    .where(
                        Job.batch_id == run.batch_id,
                        PreparedJob.profile_version_id == run.profile_version_id,
                        PreparedJob.feature_schema_version
                        == run.feature_schema_version,
                    )
                    .order_by(PreparedJob.job_id)
                )
            ).all()
        )
        batch = await session.get(Batch, run.batch_id)
        if batch is None or len(prepared_jobs) != batch.job_count:
            run.status = "FAILED"
            run.phase = "FAILED"
            run.retryable = False
            run.error_code = "PREPARED_JOBS_INCOMPLETE"
            run.error_message = "Prepared jobs do not cover the complete batch."
            run.completed_at = now
            if batch:
                batch.status = "NORMALIZED"
            await session.flush()
            continue
        lease_token = token_urlsafe(32)
        lease_expires_at = now + LEASE_DURATION
        run.status = "RUNNING"
        run.phase = "SCORING"
        run.attempt += 1
        run.lease_token = lease_token
        run.lease_expires_at = lease_expires_at
        run.heartbeat_at = now
        run.error_code = None
        run.error_message = None
        run.started_at = run.started_at or now
        run.completed_at = None
        batch.status = "RANKING"
        await session.commit()
        return WorkerClaimResponse(
            run_id=run.id,
            batch_id=run.batch_id,
            profile_version_id=run.profile_version_id,
            model_version_id=run.model_version_id,
            feature_schema_version=run.feature_schema_version,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            jobs=[
                WorkerPreparedJob(job_id=item.job_id, payload=item.payload)
                for item in prepared_jobs
            ],
        )

    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/internal/processing-runs/{run_id}/heartbeat",
    response_model=WorkerHeartbeatResponse,
)
async def heartbeat_processing_run(
    run_id: str,
    _service: ServiceToken,
    session: DatabaseSession,
    lease_token: LeaseToken = None,
) -> WorkerHeartbeatResponse:
    run = await session.get(ProcessingRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Processing run not found.")
    now = datetime.now(UTC)
    _require_active_lease(run, lease_token, now)
    run.heartbeat_at = now
    run.lease_expires_at = now + LEASE_DURATION
    await session.commit()
    return WorkerHeartbeatResponse(
        run_id=run.id,
        lease_expires_at=run.lease_expires_at,
    )


@router.post(
    "/internal/processing-runs/{run_id}/fail",
    response_model=WorkerFailureResponse,
)
async def fail_processing_run(
    run_id: str,
    body: WorkerFailureRequest,
    _service: ServiceToken,
    session: DatabaseSession,
    lease_token: LeaseToken = None,
) -> WorkerFailureResponse:
    run = await session.get(ProcessingRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Processing run not found.")
    now = datetime.now(UTC)
    _require_active_lease(run, lease_token, now)
    run.status = "FAILED"
    run.phase = "FAILED"
    run.retryable = True
    run.error_code = body.error_code
    run.error_message = " ".join(body.error_message.split())[:500]
    run.completed_at = now
    run.lease_token = None
    run.lease_expires_at = None
    batch = await session.get(Batch, run.batch_id)
    if batch:
        batch.status = "NORMALIZED"
    await session.commit()
    return WorkerFailureResponse(
        run_id=run.id,
        status=run.status,
        batch_status=batch.status if batch else "NORMALIZED",
    )


@router.post(
    "/internal/batches/{batch_id}/rankings",
    response_model=RankingSaveResponse,
)
async def save_internal_rankings(
    batch_id: str,
    body: RankingsRequest,
    _service: ServiceToken,
    session: DatabaseSession,
    lease_token: LeaseToken = None,
) -> RankingSaveResponse:
    batch = await get_batch_or_404(session, batch_id)
    if batch.status == "RANKED":
        completed_run = await session.scalar(
            select(ProcessingRun)
            .where(
                ProcessingRun.batch_id == batch_id,
                ProcessingRun.stage == "ranking",
                ProcessingRun.status == "SUCCEEDED",
                ProcessingRun.profile_version_id == body.profile_version_id,
                ProcessingRun.model_version_id == body.model_version_id,
            )
            .order_by(ProcessingRun.completed_at.desc())
        )
        if completed_run and await ranking_delivery_exists(
            session, completed_run.id, body
        ):
            await enqueue_configured_mail_events(
                session,
                batch,
                completed_run,
            )
            return RankingSaveResponse(
                batch_id=batch_id,
                status="RANKED",
                ranking_count=len(body.rankings),
                email_delivery=None,
            )

    run = await session.scalar(
        select(ProcessingRun)
        .where(
            ProcessingRun.batch_id == batch_id,
            ProcessingRun.stage == "ranking",
            ProcessingRun.status == "RUNNING",
        )
        .order_by(ProcessingRun.created_at.desc())
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active ranking lease exists for this batch.",
        )
    now = datetime.now(UTC)
    _require_active_lease(run, lease_token, now)
    ranking_count = await persist_rankings(session, batch, run, body)
    run.status = "SUCCEEDED"
    run.phase = "COMPLETED"
    run.retryable = None
    run.completed_at = now
    run.lease_token = None
    run.lease_expires_at = None
    await session.commit()
    await enqueue_configured_mail_events(session, batch, run)
    return RankingSaveResponse(
        batch_id=batch_id,
        status=batch.status,
        ranking_count=ranking_count,
        email_delivery=None,
    )
