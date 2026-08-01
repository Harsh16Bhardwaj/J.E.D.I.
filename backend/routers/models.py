"""Immutable model registry plus embedded deployment compatibility gates."""

import asyncio
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.config import get_settings
from backend.database import (
    ModelDeployment,
    ModelEndpointCheck,
    ModelInvocation,
    ModelVersion,
    ProcessingRun,
    get_session,
)
from backend.schemas.product import (
    ModelCreate,
    ModelDetail,
    ModelSummary,
    ModelWriteResponse,
)
from backend.schemas.scoring import ModelOperationResponse
from backend.services.group_access import group_context, require_group_owner
from backend.services.model_runtime import ModelRuntimeError, model_runtime
from backend.services.product import clean_text, stable_hash

router = APIRouter(prefix="/api/models", tags=["models"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


def model_detail(model: ModelVersion) -> ModelDetail:
    return ModelDetail(
        id=model.id,
        name=model.name,
        content_hash=model.content_hash,
        artifact_manifest=model.artifact_manifest,
        feature_schema_version=model.feature_schema_version,
        metrics=model.metrics,
        active=model.active,
        created_at=model.created_at,
    )


async def get_model_or_404(
    session: AsyncSession,
    model_id: str,
) -> ModelVersion:
    model = await session.get(ModelVersion, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model version not found.")
    return model


@router.post(
    "",
    response_model=ModelWriteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_model(
    body: ModelCreate,
    response: Response,
    user: CurrentUser,
    session: DatabaseSession,
) -> ModelWriteResponse:
    if user:
        await require_group_owner(session, user.id)
    normalized = {
        "name": clean_text(body.name),
        "artifact_manifest": body.artifact_manifest,
        "feature_schema_version": clean_text(body.feature_schema_version),
        "request_contract_version": clean_text(
            str(body.artifact_manifest.get("requestContractVersion", "jedi-ranking-v1"))
        ),
        "metrics": body.metrics,
    }
    content_hash = stable_hash(normalized)
    replay = await session.scalar(
        select(ModelVersion).where(ModelVersion.content_hash == content_hash)
    )
    if replay:
        response.status_code = status.HTTP_200_OK
        return ModelWriteResponse(**model_detail(replay).model_dump(), replayed=True)
    same_name = await session.scalar(
        select(ModelVersion).where(ModelVersion.name == normalized["name"])
    )
    if same_name:
        raise HTTPException(
            status_code=409,
            detail="Model name already exists with different metadata.",
        )
    model = ModelVersion(content_hash=content_hash, active=False, **normalized)
    session.add(model)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Model metadata conflicted with a concurrent request.",
        ) from exc
    return ModelWriteResponse(**model_detail(model).model_dump(), replayed=False)


@router.get("", response_model=list[ModelSummary])
async def list_models(
    _user: CurrentUser,
    session: DatabaseSession,
) -> list[ModelSummary]:
    models = (
        await session.scalars(
            select(ModelVersion).order_by(ModelVersion.created_at.desc())
        )
    ).all()
    return [
        ModelSummary.model_validate(model_detail(model).model_dump())
        for model in models
    ]


@router.post("/runtime/register", response_model=ModelWriteResponse)
async def register_embedded_model(
    response: Response,
    user: CurrentUser,
    session: DatabaseSession,
) -> ModelWriteResponse:
    """Register the checked-in immutable bundle as an inactive candidate."""
    await require_group_owner(session, user.id)
    try:
        bundle, _, _ = await asyncio.wait_for(
            asyncio.to_thread(model_runtime.load),
            timeout=get_settings().model_load_timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=503, detail="Model loading timed out.") from exc
    except ModelRuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    manifest = bundle.manifest
    existing = await session.scalar(
        select(ModelVersion).where(
            ModelVersion.content_hash == manifest["artifactHash"]
        )
    )
    if existing:
        response.status_code = status.HTTP_200_OK
        return ModelWriteResponse(**model_detail(existing).model_dump(), replayed=True)
    same_name = await session.scalar(
        select(ModelVersion).where(ModelVersion.name == manifest["modelVersion"])
    )
    if same_name:
        raise HTTPException(
            status_code=409,
            detail="Bundle name already belongs to a different artifact.",
        )
    model = ModelVersion(
        name=manifest["modelVersion"],
        content_hash=manifest["artifactHash"],
        description=(
            "Leakage-safe Ridge preference scores stacked into conservative XGBoost."
        ),
        model_family="ridge_xgboost_stacked",
        artifact_manifest=manifest,
        feature_schema_version=manifest["featureSchemaVersion"],
        request_contract_version=manifest["requestContractVersion"],
        tags=["embedded", "production-candidate", "leakage-safe"],
        training_metadata=manifest.get("training"),
        evaluation_metadata={
            "evaluation": manifest.get("metrics", {}).get("evaluation")
        },
        metrics=manifest.get("metrics"),
        active=False,
    )
    session.add(model)
    await session.commit()
    response.status_code = status.HTTP_201_CREATED
    return ModelWriteResponse(**model_detail(model).model_dump(), replayed=False)


@router.post("/runtime/warmup", response_model=ModelOperationResponse)
async def warmup_model_runtime(
    user: CurrentUser,
    session: DatabaseSession,
) -> ModelOperationResponse:
    await require_group_owner(session, user.id)
    try:
        runtime = await asyncio.wait_for(
            asyncio.to_thread(model_runtime.warmup),
            timeout=get_settings().model_load_timeout_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=503, detail="Model loading timed out.") from exc
    except ModelRuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return ModelOperationResponse(status="READY", runtime=runtime)


@router.get("/runtime/metrics", response_model=dict[str, object])
async def model_runtime_metrics(
    user: CurrentUser,
    session: DatabaseSession,
) -> dict[str, object]:
    """Return a compact owner-only release and incident dashboard."""
    await require_group_owner(session, user.id)
    now = datetime.now(UTC)
    runs = list(
        (
            await session.scalars(
                select(ProcessingRun)
                .where(ProcessingRun.stage == "ranking")
                .order_by(ProcessingRun.created_at.desc())
                .limit(20)
            )
        ).all()
    )
    run_ids = [run.id for run in runs]
    invocations = (
        list(
            (
                await session.scalars(
                    select(ModelInvocation).where(
                        ModelInvocation.processing_run_id.in_(run_ids)
                    )
                )
            ).all()
        )
        if run_ids
        else []
    )
    totals = sorted(
        float(invocation.timings_ms.get("total", 0))
        for invocation in invocations
        if invocation.status == "SUCCEEDED" and invocation.timings_ms
    )
    p95 = totals[max(int(len(totals) * 0.95 + 0.999) - 1, 0)] if totals else None
    failures = sum(run.status == "FAILED" for run in runs)
    cold = [item for item in invocations if item.cold_start is not None]
    stale = sum(
        run.status == "RUNNING"
        and run.lease_expires_at is not None
        and run.lease_expires_at.replace(tzinfo=run.lease_expires_at.tzinfo or UTC)
        <= now
        for run in runs
    )
    latest_success = next((run for run in runs if run.status == "SUCCEEDED"), None)
    return {
        "sampleSize": len(runs),
        "successCount": sum(run.status == "SUCCEEDED" for run in runs),
        "failureCount": failures,
        "failureRate": failures / len(runs) if runs else 0.0,
        "staleCount": stale,
        "coldStartRate": (
            sum(bool(item.cold_start) for item in cold) / len(cold) if cold else 0.0
        ),
        "p95ExecutionMs": p95,
        "latestSuccessfulRankingAgeSeconds": (
            (
                now
                - latest_success.completed_at.replace(
                    tzinfo=latest_success.completed_at.tzinfo or UTC
                )
            ).total_seconds()
            if latest_success and latest_success.completed_at
            else None
        ),
        "runtime": model_runtime.health().model_dump(mode="json", by_alias=True),
        "warnings": [
            message
            for condition, message in (
                (
                    failures > 0 and len(runs) >= 20 and failures / len(runs) > 0.10,
                    "FAILURE_RATE_HIGH",
                ),
                (stale > 0, "STALE_RUN_PRESENT"),
                (p95 is not None and p95 > 120_000, "P95_EXECUTION_HIGH"),
            )
            if condition
        ],
    }


@router.post("/{model_id}/deployment-check", response_model=ModelOperationResponse)
async def check_model_deployment(
    model_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> ModelOperationResponse:
    await require_group_owner(session, user.id)
    model = await get_model_or_404(session, model_id)
    started = datetime.now(UTC)
    runtime_error: ModelRuntimeError | None = None
    try:
        runtime = await asyncio.wait_for(
            asyncio.to_thread(model_runtime.warmup),
            timeout=get_settings().model_load_timeout_seconds,
        )
    except TimeoutError:
        runtime_error = ModelRuntimeError(
            "MODEL_LOAD_TIMEOUT", "Model loading timed out"
        )
        runtime = model_runtime.health()
    except ModelRuntimeError as exc:
        runtime_error = exc
        runtime = model_runtime.health()
    manifest = model.artifact_manifest or {}
    matches = bool(
        runtime.ready
        and runtime.artifact_hash == manifest.get("artifactHash")
        and runtime.model_version == manifest.get("modelVersion")
        and runtime.feature_schema_version == model.feature_schema_version
        and runtime.request_contract_version == model.request_contract_version
        and runtime.response_contract_version == manifest.get("responseContractVersion")
    )
    deployment = await session.scalar(
        select(ModelDeployment).where(ModelDeployment.model_version_id == model.id)
    )
    if deployment is None:
        deployment = ModelDeployment(
            model_version_id=model.id,
            kind="EMBEDDED",
            artifact_location="model_bundles/jedi-ranking-v1",
            timeout_seconds=240,
        )
        session.add(deployment)
        await session.flush()
    latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    deployment.health_verified_at = datetime.now(UTC)
    deployment.last_health_status = "READY" if matches else "FAILED"
    deployment.last_health_latency_ms = latency_ms
    deployment.last_health_error_code = (
        None
        if matches
        else (runtime_error.code if runtime_error else "MODEL_CONTRACT_MISMATCH")
    )
    check = ModelEndpointCheck(
        model_version_id=model.id,
        deployment_id=deployment.id,
        status=deployment.last_health_status,
        latency_ms=latency_ms,
        http_status=200 if matches else 503,
        error_code=deployment.last_health_error_code,
        health_url_snapshot=None,
        returned_feature_schema_version=runtime.feature_schema_version,
        returned_request_contract_version=runtime.request_contract_version,
        returned_response_contract_version=runtime.response_contract_version,
        returned_artifact_hash=runtime.artifact_hash,
        cold_start=runtime.cold_start,
        model_load_ms=int(runtime.model_load_ms)
        if runtime.model_load_ms is not None
        else None,
        smoke_test_ms=int(runtime.smoke_test_ms)
        if runtime.smoke_test_ms is not None
        else None,
    )
    session.add(check)
    await session.commit()
    result = ModelOperationResponse(
        status="READY" if matches else "FAILED",
        model_version_id=model.id,
        deployment_id=deployment.id,
        check_id=check.id,
        runtime=runtime,
    )
    if not matches:
        raise HTTPException(
            status_code=409,
            detail=result.model_dump(mode="json", by_alias=True),
        )
    return result


@router.get("/{model_id}/deployment", response_model=ModelOperationResponse)
async def get_model_deployment(
    model_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> ModelOperationResponse:
    await require_group_owner(session, user.id)
    model = await get_model_or_404(session, model_id)
    deployment = await session.scalar(
        select(ModelDeployment).where(ModelDeployment.model_version_id == model.id)
    )
    check = await session.scalar(
        select(ModelEndpointCheck)
        .where(ModelEndpointCheck.model_version_id == model.id)
        .order_by(ModelEndpointCheck.checked_at.desc())
    )
    return ModelOperationResponse(
        status=(
            "READY"
            if deployment and deployment.last_health_status == "READY"
            else "FAILED"
        ),
        model_version_id=model.id,
        deployment_id=deployment.id if deployment else None,
        check_id=check.id if check else None,
        runtime=model_runtime.health(),
        details=(
            {
                "configured": True,
                "kind": deployment.kind,
                "artifactLocation": deployment.artifact_location,
                "deployedRevision": deployment.deployed_revision,
                "timeoutSeconds": deployment.timeout_seconds,
                "lastHealthStatus": deployment.last_health_status,
                "lastHealthLatencyMs": deployment.last_health_latency_ms,
                "lastHealthErrorCode": deployment.last_health_error_code,
                "healthVerifiedAt": deployment.health_verified_at.isoformat()
                if deployment.health_verified_at
                else None,
                "returnedArtifactHash": check.returned_artifact_hash if check else None,
                "coldStart": check.cold_start if check else None,
                "modelLoadMs": check.model_load_ms if check else None,
                "smokeTestMs": check.smoke_test_ms if check else None,
            }
            if deployment
            else {"configured": False, "kind": "EMBEDDED"}
        ),
    )


@router.get("/{model_id}", response_model=ModelDetail)
async def get_model(
    model_id: str,
    _user: CurrentUser,
    session: DatabaseSession,
) -> ModelDetail:
    return model_detail(await get_model_or_404(session, model_id))


@router.post("/{model_id}/activate", response_model=ModelDetail)
async def activate_model(
    model_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> ModelDetail:
    model = await get_model_or_404(session, model_id)
    if user:
        await require_group_owner(session, user.id)
    if model.feature_schema_version == "prepared-job-v2":
        artifact_hash = (model.artifact_manifest or {}).get("artifactHash")
        compatible_check = await session.scalar(
            select(ModelEndpointCheck)
            .where(
                ModelEndpointCheck.model_version_id == model.id,
                ModelEndpointCheck.status == "READY",
                ModelEndpointCheck.returned_artifact_hash == artifact_hash,
                ModelEndpointCheck.returned_feature_schema_version
                == model.feature_schema_version,
                ModelEndpointCheck.returned_request_contract_version
                == model.request_contract_version,
            )
            .order_by(ModelEndpointCheck.checked_at.desc())
        )
        if compatible_check is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Run a successful deployment check for this exact artifact "
                    "before activation."
                ),
            )
    await session.execute(update(ModelVersion).values(active=False))
    model.active = True
    context = await group_context(session, user.id, lock=True) if user else None
    if context:
        context.group.active_model_version_id = model.id
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Another model activation completed concurrently.",
        ) from exc
    return model_detail(model)
