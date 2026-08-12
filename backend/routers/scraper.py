"""Owner-only manual scraper orchestration and staged import endpoints."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.config import get_settings
from backend.database import (
    Batch,
    ScrapeAttempt,
    ScrapeCandidate,
    ScrapeProviderUse,
    ScrapeRun,
    ScrapeSource,
    SourceDiscoveryAttempt,
    SourceDiscoveryRun,
    get_session,
    new_id,
)
from backend.schemas.scraper import (
    ScrapeAttemptPage,
    ScrapeAttemptResponse,
    ScrapeBulkSelectionRequest,
    ScrapeCandidateDetail,
    ScrapeCandidatePage,
    ScrapeCandidateResponse,
    ScrapeImportRequest,
    ScrapeImportResponse,
    ScraperConfigSummary,
    ScrapeRunDetail,
    ScrapeRunPage,
    ScrapeRunStats,
    ScrapeRunSummary,
    ScrapeSelectionRequest,
    ScrapeSourceCreateRequest,
    ScrapeSourceResponse,
    ScrapeSourceUpdateRequest,
    SourceDiscoveryAttemptResponse,
    SourceDiscoveryRunDetail,
    SourceDiscoveryRunResponse,
)
from backend.services.batch_ingestion import batch_response, ingest_batch
from backend.services.group_access import require_group_owner
from backend.services.normalization import normalize_batch_service
from backend.services.scraper import (
    FetchResult,
    SourceSpec,
    assess_candidate,
    bright_data_setting_configured,
    canonical_candidate_url,
    discover_company_sources,
    fetch_source_jobs,
    infer_source_from_url,
    load_scraper_config,
    parse_datetime,
    seeded_source_specs,
    source_identity_consistent,
    validate_candidate,
)

router = APIRouter(prefix="/api/scraper", tags=["scraper"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
ACTIVE_STATUSES = {
    "CREATED",
    "RUNNING",
    "REVIEW_READY",
    "IMPORTING",
    "NORMALIZING",
    "NORMALIZATION_FAILED",
}
CANCELLABLE_STATUSES = {
    "CREATED",
    "RUNNING",
    "REVIEW_READY",
    "NORMALIZATION_FAILED",
}


def source_response(item: ScrapeSource) -> ScrapeSourceResponse:
    return ScrapeSourceResponse(
        id=item.id,
        source_key=item.source_key,
        name=item.name,
        ats_type=item.ats_type,
        domain_hint=item.domain_hint,
        board_token=item.board_token,
        active=item.active,
        last_seen_at=item.last_seen_at,
        created_at=item.created_at,
        health_status=item.health_status,
        last_success_at=item.last_success_at,
        last_failure_at=item.last_failure_at,
        consecutive_failures=item.consecutive_failures,
        consecutive_zero_yield=item.consecutive_zero_yield,
        response_time_ms=item.response_time_ms,
        jobs_scanned=item.jobs_scanned,
        eligible_yield=item.eligible_yield,
        duplicate_yield=item.duplicate_yield,
        cooldown_until=item.cooldown_until,
    )


async def sync_seed_sources(session: AsyncSession, group_id: str) -> list[ScrapeSource]:
    config = load_scraper_config()
    existing = {
        item.source_key: item
        for item in (
            await session.scalars(
                select(ScrapeSource).where(ScrapeSource.group_id == group_id)
            )
        ).all()
    }
    for source in seeded_source_specs(config):
        item = existing.get(source.source_key)
        if item is None:
            item = ScrapeSource(
                id=new_id(),
                group_id=group_id,
                source_key=source.source_key,
                name=source.name,
                ats_type=source.ats_type,
                domain_hint=source.domain_hint,
                board_token=source.board_token,
                discovered=False,
                active=True,
            )
            session.add(item)
            existing[item.source_key] = item
        elif not item.discovered:
            item.name = source.name
            item.domain_hint = source.domain_hint
            item.board_token = source.board_token
    await session.flush()
    return list(existing.values())


def run_summary(item: ScrapeRun) -> ScrapeRunSummary:
    provider_reason = item.provider_usage_reason or (
        "Direct ATS requests succeeded; no blocked detail page required Web Unlocker."
        if item.bright_data_used == 0
        else "Web Unlocker handled blocked or incomplete ATS detail pages."
    )
    return ScrapeRunSummary(
        id=item.id,
        status=item.status,
        config_version=item.config_version,
        target_job_count=item.target_job_count,
        bright_data_limit=item.bright_data_limit,
        bright_data_used=item.bright_data_used,
        free_request_count=item.free_request_count,
        bright_data_fallback_count=item.bright_data_fallback_count,
        provider_usage_reason=provider_reason,
        normalization_status=(
            item.status
            if item.status in {"NORMALIZING", "NORMALIZATION_FAILED", "IMPORTED"}
            else None
        ),
        discovered_count=item.discovered_count,
        valid_count=item.valid_count,
        selected_count=item.selected_count,
        failed_source_count=item.failed_source_count,
        source_count=item.source_count,
        processed_source_count=item.processed_source_count,
        stopped_early=item.stopped_early,
        imported_batch_id=item.imported_batch_id,
        error_message=item.error_message,
        created_at=item.created_at,
        updated_at=item.updated_at,
        completed_at=item.completed_at,
    )


def attempt_response(item: ScrapeAttempt) -> ScrapeAttemptResponse:
    return ScrapeAttemptResponse(
        id=item.id,
        step_key=item.step_key,
        source_key=item.source_key,
        provider=item.provider,
        status=item.status,
        attempt_count=item.attempt_count,
        discovered_count=item.discovered_count,
        valid_count=item.valid_count,
        bright_data_used=item.bright_data_used,
        error_message=item.error_message,
        checkpoint=item.checkpoint,
        response_time_ms=item.response_time_ms,
        free_request_count=item.free_request_count,
    )


def candidate_response(item: ScrapeCandidate) -> ScrapeCandidateResponse:
    return ScrapeCandidateResponse(
        id=item.id,
        source_key=item.source_key,
        source_provider=item.source_provider,
        ats_type=item.ats_type,
        source_url=item.source_url,
        company_name=item.company_name,
        role_title=item.role_title,
        location=item.location,
        experience_min_years=item.experience_min_years,
        experience_max_years=item.experience_max_years,
        posted_at=item.posted_at,
        geography_eligibility=item.geography_eligibility,
        source_quality_valid=item.source_quality_valid,
        quality_failures=item.quality_failures or [],
        description_length=item.description_length,
        date_evidence=item.date_evidence,
        schema_valid=item.schema_valid,
        selected=item.selected,
        validation_errors=item.validation_errors,
        freshness_tier=item.freshness_tier,
        quality_score=item.quality_score,
        review_group=item.review_group,
        extracted_facts=item.extracted_facts,
        extraction_version=item.extraction_version,
    )


def discovery_summary(item: SourceDiscoveryRun) -> SourceDiscoveryRunResponse:
    return SourceDiscoveryRunResponse(
        id=item.id,
        status=item.status,
        total_hints=item.total_hints,
        processed_hints=item.processed_hints,
        detected_sources=item.detected_sources,
        activated_sources=item.activated_sources,
        failed_hints=item.failed_hints,
        error_message=item.error_message,
        created_at=item.created_at,
        updated_at=item.updated_at,
        completed_at=item.completed_at,
    )


def discovery_attempt_response(
    item: SourceDiscoveryAttempt,
) -> SourceDiscoveryAttemptResponse:
    return SourceDiscoveryAttemptResponse(
        id=item.id,
        company_name=item.company_name,
        company_domain=item.company_domain,
        status=item.status,
        attempt_count=item.attempt_count,
        detected_count=item.detected_count,
        activated_count=item.activated_count,
        response_time_ms=item.response_time_ms,
        error_message=item.error_message,
    )


async def owned_run(
    session: AsyncSession, user_id: str, run_id: str, *, lock: bool = False
) -> ScrapeRun:
    context = await require_group_owner(session, user_id, lock=lock)
    statement = select(ScrapeRun).where(
        ScrapeRun.id == run_id, ScrapeRun.group_id == context.group.id
    )
    if lock:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    item = await session.scalar(statement)
    if item is None:
        raise HTTPException(status_code=404, detail="Scraper run not found.")
    return item


async def run_detail(session: AsyncSession, item: ScrapeRun) -> ScrapeRunDetail:
    attempts = (
        await session.scalars(
            select(ScrapeAttempt)
            .where(ScrapeAttempt.run_id == item.id)
            .order_by(ScrapeAttempt.created_at, ScrapeAttempt.step_key)
        )
    ).all()
    candidates = (
        await session.scalars(
            select(ScrapeCandidate)
            .where(ScrapeCandidate.run_id == item.id)
            .order_by(
                ScrapeCandidate.schema_valid.desc(),
                ScrapeCandidate.posted_at.desc(),
                ScrapeCandidate.company_name,
            )
        )
    ).all()
    return ScrapeRunDetail(
        **run_summary(item).model_dump(),
        attempts=[attempt_response(row) for row in attempts],
        candidates=[candidate_response(row) for row in candidates],
    )


async def refresh_counts(session: AsyncSession, item: ScrapeRun) -> None:
    item.discovered_count = (
        await session.scalar(
            select(func.count())
            .select_from(ScrapeCandidate)
            .where(ScrapeCandidate.run_id == item.id)
        )
        or 0
    )
    item.valid_count = (
        await session.scalar(
            select(func.count())
            .select_from(ScrapeCandidate)
            .where(
                ScrapeCandidate.run_id == item.id,
                ScrapeCandidate.schema_valid.is_(True),
                ScrapeCandidate.source_quality_valid.is_(True),
                ScrapeCandidate.review_group.in_(["RECOMMENDED", "NEEDS_REVIEW"]),
            )
        )
        or 0
    )
    item.selected_count = (
        await session.scalar(
            select(func.count())
            .select_from(ScrapeCandidate)
            .where(
                ScrapeCandidate.run_id == item.id,
                ScrapeCandidate.schema_valid.is_(True),
                ScrapeCandidate.source_quality_valid.is_(True),
                ScrapeCandidate.review_group.in_(["RECOMMENDED", "NEEDS_REVIEW"]),
                ScrapeCandidate.selected.is_(True),
            )
        )
        or 0
    )
    item.failed_source_count = (
        await session.scalar(
            select(func.count())
            .select_from(ScrapeAttempt)
            .where(
                ScrapeAttempt.run_id == item.id,
                ScrapeAttempt.status == "FAILED",
            )
        )
        or 0
    )
    item.source_count = (
        await session.scalar(
            select(func.count())
            .select_from(ScrapeAttempt)
            .where(ScrapeAttempt.run_id == item.id)
        )
        or 0
    )
    item.processed_source_count = (
        await session.scalar(
            select(func.count())
            .select_from(ScrapeAttempt)
            .where(
                ScrapeAttempt.run_id == item.id,
                ScrapeAttempt.status.in_(["SUCCEEDED", "FAILED"]),
            )
        )
        or 0
    )


async def refresh_selected_count(session: AsyncSession, item: ScrapeRun) -> None:
    """Refresh only the counter affected by candidate selection."""
    item.selected_count = (
        await session.scalar(
            select(func.count())
            .select_from(ScrapeCandidate)
            .where(
                ScrapeCandidate.run_id == item.id,
                ScrapeCandidate.schema_valid.is_(True),
                ScrapeCandidate.source_quality_valid.is_(True),
                ScrapeCandidate.review_group.in_(["RECOMMENDED", "NEEDS_REVIEW"]),
                ScrapeCandidate.selected.is_(True),
            )
        )
        or 0
    )


async def finish_if_ready(session: AsyncSession, item: ScrapeRun) -> None:
    remaining = (
        await session.scalar(
            select(func.count())
            .select_from(ScrapeAttempt)
            .where(
                ScrapeAttempt.run_id == item.id,
                ScrapeAttempt.status.in_(["PENDING", "RUNNING"]),
            )
        )
        or 0
    )
    if remaining == 0:
        item.status = "REVIEW_READY" if item.discovered_count else "FAILED"
        item.stopped_early = False
        if item.status == "REVIEW_READY":
            await reclassify_run_candidates(session, item)
            await refresh_counts(session, item)
        if item.status == "FAILED":
            item.error_message = (
                "No candidates were collected from the configured sources."
            )
            item.completed_at = datetime.now(UTC)


@router.get("/config", response_model=ScraperConfigSummary)
async def scraper_config(
    user: CurrentUser, session: DatabaseSession
) -> ScraperConfigSummary:
    await require_group_owner(session, user.id)
    config = load_scraper_config()
    settings = get_settings()
    return ScraperConfigSummary(
        version=config.version,
        lookback_days=config.lookback_days,
        review_lookback_days=config.review_lookback_days,
        target_job_count=config.target_job_count,
        bright_data_limit=config.bright_data_limit,
        ats_types=list(config.ats_types),
        title_aliases=list(config.title_aliases),
        company_hint_count=len(config.company_hints),
        seeded_source_count=len(config.seed_sources),
        bright_data_configured=bool(
            bright_data_setting_configured(settings.bright_data_api_key)
            and bright_data_setting_configured(settings.bright_data_unlocker_zone)
        ),
        unlocker_configured=bool(
            bright_data_setting_configured(settings.bright_data_api_key)
            and bright_data_setting_configured(settings.bright_data_unlocker_zone)
        ),
        concurrent_sources=config.concurrent_sources,
        max_candidates_per_company=config.max_candidates_per_company,
        minimum_description_characters=config.minimum_description_characters,
    )


@router.get("/sources", response_model=list[ScrapeSourceResponse])
async def list_sources(
    user: CurrentUser, session: DatabaseSession
) -> list[ScrapeSourceResponse]:
    context = await require_group_owner(session, user.id)
    await sync_seed_sources(session, context.group.id)
    await session.commit()
    items = (
        await session.scalars(
            select(ScrapeSource)
            .where(ScrapeSource.group_id == context.group.id)
            .order_by(ScrapeSource.ats_type, ScrapeSource.name)
        )
    ).all()
    return [source_response(item) for item in items]


@router.post("/sources", response_model=ScrapeSourceResponse, status_code=201)
async def add_source(
    body: ScrapeSourceCreateRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> ScrapeSourceResponse:
    context = await require_group_owner(session, user.id, lock=True)
    try:
        source = infer_source_from_url(body.url, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    item = await session.scalar(
        select(ScrapeSource).where(
            ScrapeSource.group_id == context.group.id,
            ScrapeSource.source_key == source.source_key,
        )
    )
    if item is None:
        item = ScrapeSource(
            id=new_id(),
            group_id=context.group.id,
            source_key=source.source_key,
            name=source.name,
            ats_type=source.ats_type,
            domain_hint=source.domain_hint,
            board_token=source.board_token,
            discovered=False,
            active=True,
        )
        session.add(item)
    else:
        item.name = source.name
        item.domain_hint = source.domain_hint
        item.board_token = source.board_token
        item.active = True
    await session.commit()
    await session.refresh(item)
    return source_response(item)


async def owned_source(
    session: AsyncSession, user_id: str, source_id: str, *, lock: bool = False
) -> ScrapeSource:
    context = await require_group_owner(session, user_id, lock=lock)
    statement = select(ScrapeSource).where(
        ScrapeSource.id == source_id, ScrapeSource.group_id == context.group.id
    )
    if lock:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    item = await session.scalar(statement)
    if item is None:
        raise HTTPException(status_code=404, detail="Scraper source not found.")
    return item


@router.patch("/sources/{source_id}", response_model=ScrapeSourceResponse)
async def update_source(
    source_id: str,
    body: ScrapeSourceUpdateRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> ScrapeSourceResponse:
    item = await owned_source(session, user.id, source_id, lock=True)
    item.active = body.active
    await session.commit()
    await session.refresh(item)
    return source_response(item)


@router.post("/sources/{source_id}/clear-cooldown", response_model=ScrapeSourceResponse)
async def clear_source_cooldown(
    source_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeSourceResponse:
    item = await owned_source(session, user.id, source_id, lock=True)
    item.cooldown_until = None
    item.consecutive_failures = 0
    item.consecutive_zero_yield = 0
    item.health_status = "UNKNOWN"
    await session.commit()
    await session.refresh(item)
    return source_response(item)


@router.post("/sources/{source_id}/revalidate", response_model=ScrapeSourceResponse)
async def revalidate_source(
    source_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeSourceResponse:
    item = await owned_source(session, user.id, source_id, lock=True)
    config = replace(load_scraper_config(), bright_data_limit=0)
    source = SourceSpec(
        source_key=item.source_key,
        name=item.name,
        ats_type=item.ats_type,
        domain_hint=item.domain_hint,
        board_token=item.board_token,
        discovered=item.discovered,
    )
    started = perf_counter()
    now = datetime.now(UTC)
    try:
        result = await fetch_source_jobs(source, config, allow_unlocker=False)
        healthy = bool(result.jobs) and source_identity_consistent(
            item.name, source, result.jobs
        )
        if not healthy:
            raise RuntimeError("Source identity or direct vacancy validation failed.")
        item.health_status = "HEALTHY"
        item.last_success_at = now
        item.consecutive_failures = 0
        item.cooldown_until = None
        item.jobs_scanned = len(result.jobs)
    except Exception as exc:
        item.health_status = "FAILING"
        item.last_failure_at = now
        item.consecutive_failures += 1
        if item.consecutive_failures >= 3:
            item.health_status = "COOLDOWN"
            item.cooldown_until = now + timedelta(hours=24)
        item.response_time_ms = int((perf_counter() - started) * 1000)
        await session.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        item.response_time_ms = int((perf_counter() - started) * 1000)
    await session.commit()
    await session.refresh(item)
    return source_response(item)


async def owned_discovery_run(
    session: AsyncSession, user_id: str, run_id: str, *, lock: bool = False
) -> SourceDiscoveryRun:
    context = await require_group_owner(session, user_id, lock=lock)
    statement = select(SourceDiscoveryRun).where(
        SourceDiscoveryRun.id == run_id,
        SourceDiscoveryRun.group_id == context.group.id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )
    item = await session.scalar(statement)
    if item is None:
        raise HTTPException(status_code=404, detail="Source refresh run not found.")
    return item


async def discovery_detail(
    session: AsyncSession, item: SourceDiscoveryRun
) -> SourceDiscoveryRunDetail:
    attempts = (
        await session.scalars(
            select(SourceDiscoveryAttempt)
            .where(SourceDiscoveryAttempt.run_id == item.id)
            .order_by(SourceDiscoveryAttempt.created_at)
        )
    ).all()
    return SourceDiscoveryRunDetail(
        **discovery_summary(item).model_dump(),
        attempts=[discovery_attempt_response(row) for row in attempts],
    )


@router.post(
    "/source-refresh", response_model=SourceDiscoveryRunResponse, status_code=201
)
async def create_source_refresh(
    user: CurrentUser, session: DatabaseSession
) -> SourceDiscoveryRunResponse:
    context = await require_group_owner(session, user.id, lock=True)
    active = await session.scalar(
        select(SourceDiscoveryRun).where(
            SourceDiscoveryRun.group_id == context.group.id,
            SourceDiscoveryRun.status.in_(["CREATED", "RUNNING"]),
        )
    )
    if active:
        raise HTTPException(
            status_code=409,
            detail={"code": "SOURCE_REFRESH_ACTIVE", "runId": active.id},
        )
    config = load_scraper_config()
    item = SourceDiscoveryRun(
        id=new_id(),
        group_id=context.group.id,
        status="CREATED",
        config_version=config.version,
        config_hash=config.content_hash,
        total_hints=len(config.company_hints),
    )
    session.add(item)
    await session.flush()
    session.add_all(
        SourceDiscoveryAttempt(
            id=new_id(),
            run_id=item.id,
            step_key=f"company:{index}:{hint['domain'].casefold()}",
            company_name=hint["name"],
            company_domain=hint["domain"],
            status="PENDING",
        )
        for index, hint in enumerate(config.company_hints)
    )
    await session.commit()
    await session.refresh(item)
    return discovery_summary(item)


@router.get("/source-refresh", response_model=SourceDiscoveryRunResponse | None)
async def latest_source_refresh(
    user: CurrentUser, session: DatabaseSession
) -> SourceDiscoveryRunResponse | None:
    context = await require_group_owner(session, user.id)
    item = await session.scalar(
        select(SourceDiscoveryRun)
        .where(SourceDiscoveryRun.group_id == context.group.id)
        .order_by(SourceDiscoveryRun.created_at.desc())
    )
    return discovery_summary(item) if item else None


@router.get("/source-refresh/{run_id}", response_model=SourceDiscoveryRunDetail)
async def get_source_refresh(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> SourceDiscoveryRunDetail:
    return await discovery_detail(
        session, await owned_discovery_run(session, user.id, run_id)
    )


@router.post(
    "/source-refresh/{run_id}/advance", response_model=SourceDiscoveryRunResponse
)
async def advance_source_refresh(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> SourceDiscoveryRunResponse:
    item = await owned_discovery_run(session, user.id, run_id, lock=True)
    if item.status not in {"CREATED", "RUNNING"}:
        return discovery_summary(item)
    config = load_scraper_config()
    now = datetime.now(UTC)
    await session.execute(
        update(SourceDiscoveryAttempt)
        .where(
            SourceDiscoveryAttempt.run_id == item.id,
            SourceDiscoveryAttempt.status == "RUNNING",
            SourceDiscoveryAttempt.lease_expires_at < now,
        )
        .values(status="PENDING", lease_expires_at=None)
    )
    attempt = await session.scalar(
        select(SourceDiscoveryAttempt)
        .where(
            SourceDiscoveryAttempt.run_id == item.id,
            SourceDiscoveryAttempt.status == "PENDING",
        )
        .order_by(SourceDiscoveryAttempt.created_at)
        .with_for_update(skip_locked=True)
    )
    if attempt is None:
        item.status = (
            "FAILED"
            if not item.processed_hints
            or (item.failed_hints >= item.total_hints and item.total_hints > 0)
            else "COMPLETED"
        )
        item.completed_at = now
        await session.commit()
        return discovery_summary(item)
    item.status = "RUNNING"
    attempt.status = "RUNNING"
    attempt.attempt_count += 1
    attempt.lease_expires_at = now + timedelta(seconds=config.lease_seconds)
    await session.commit()
    started = perf_counter()
    validated_sources: list[tuple[SourceSpec, FetchResult]] = []
    discovery_error: Exception | None = None
    try:
        detected = await discover_company_sources(
            attempt.company_name, attempt.company_domain, config
        )
        for raw in detected.jobs:
            source = SourceSpec(**raw)
            validation = await fetch_source_jobs(
                source, replace(config, bright_data_limit=0), allow_unlocker=False
            )
            if not validation.jobs or not source_identity_consistent(
                attempt.company_name, source, validation.jobs
            ):
                continue
            if not any(
                str(job.get("applyUrl") or "").startswith(("http://", "https://"))
                for job in validation.jobs
            ):
                continue
            validated_sources.append((source, validation))
    except Exception as exc:
        discovery_error = exc

    # Re-acquire and refresh the run lock after the network work. Cancellation
    # may have committed while discovery was in flight; never overwrite it with
    # a stale RUNNING object from this session's identity map.
    item = await owned_discovery_run(session, user.id, run_id, lock=True)
    attempt = await session.scalar(
        select(SourceDiscoveryAttempt)
        .where(SourceDiscoveryAttempt.id == attempt.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if attempt is None:
        raise HTTPException(
            status_code=409, detail="Source refresh attempt disappeared."
        )
    if item.status == "CANCELLED" or attempt.status != "RUNNING":
        attempt.lease_expires_at = None
        await session.commit()
        return discovery_summary(item)

    attempt.detected_count = len(detected.jobs) if discovery_error is None else 0
    activated = 0
    if discovery_error is None:
        for source, validation in validated_sources:
            stored = await session.scalar(
                select(ScrapeSource).where(
                    ScrapeSource.group_id == item.group_id,
                    ScrapeSource.source_key == source.source_key,
                )
            )
            if stored is None:
                stored = ScrapeSource(
                    id=new_id(),
                    group_id=item.group_id,
                    source_key=source.source_key,
                    name=attempt.company_name,
                    ats_type=source.ats_type,
                    domain_hint=source.domain_hint,
                    board_token=source.board_token,
                    discovered=True,
                )
                session.add(stored)
            stored.active = True
            stored.health_status = "HEALTHY"
            stored.last_success_at = now
            stored.last_seen_at = now
            stored.jobs_scanned = len(validation.jobs)
            stored.response_cache = validation.jobs
            activated += 1
        attempt.activated_count = activated
        attempt.status = "SUCCEEDED"
        attempt.error_message = None
        item.detected_sources += attempt.detected_count
        item.activated_sources += activated
    else:
        attempt.status = "FAILED"
        attempt.error_message = str(discovery_error)[:500]
        item.failed_hints += 1
    attempt.response_time_ms = int((perf_counter() - started) * 1000)
    attempt.lease_expires_at = None
    item.processed_hints += 1
    remaining = await session.scalar(
        select(func.count())
        .select_from(SourceDiscoveryAttempt)
        .where(
            SourceDiscoveryAttempt.run_id == item.id,
            SourceDiscoveryAttempt.status.in_(["PENDING", "RUNNING"]),
        )
    )
    if not remaining:
        item.status = (
            "FAILED"
            if item.failed_hints >= item.total_hints and item.total_hints > 0
            else "COMPLETED"
        )
        item.completed_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(item)
    return discovery_summary(item)


@router.post(
    "/source-refresh/{run_id}/cancel", response_model=SourceDiscoveryRunResponse
)
async def cancel_source_refresh(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> SourceDiscoveryRunResponse:
    item = await owned_discovery_run(session, user.id, run_id, lock=True)
    if item.status == "CANCELLED":
        await session.execute(
            update(SourceDiscoveryAttempt)
            .where(
                SourceDiscoveryAttempt.run_id == item.id,
                SourceDiscoveryAttempt.status == "RUNNING",
            )
            .values(status="PENDING", lease_expires_at=None)
        )
        await session.commit()
        return discovery_summary(item)
    if item.status not in {"CREATED", "RUNNING"}:
        raise HTTPException(status_code=409, detail="Source refresh is not active.")
    item.status = "CANCELLED"
    item.completed_at = datetime.now(UTC)
    await session.execute(
        update(SourceDiscoveryAttempt)
        .where(
            SourceDiscoveryAttempt.run_id == item.id,
            SourceDiscoveryAttempt.status == "RUNNING",
        )
        .values(status="PENDING", lease_expires_at=None)
    )
    await session.commit()
    return discovery_summary(item)


@router.get("/runs", response_model=ScrapeRunPage)
async def list_runs(
    user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=50)] = 20,
) -> ScrapeRunPage:
    context = await require_group_owner(session, user.id)
    where = ScrapeRun.group_id == context.group.id
    total = (
        await session.scalar(select(func.count()).select_from(ScrapeRun).where(where))
        or 0
    )
    items = (
        await session.scalars(
            select(ScrapeRun)
            .where(where)
            .order_by(ScrapeRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return ScrapeRunPage(
        items=[run_summary(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/runs", response_model=ScrapeRunSummary, status_code=201)
async def create_run(user: CurrentUser, session: DatabaseSession) -> ScrapeRunSummary:
    context = await require_group_owner(session, user.id, lock=True)
    config = load_scraper_config()
    await session.execute(
        delete(ScrapeRun).where(
            ScrapeRun.group_id == context.group.id,
            ScrapeRun.status.in_(["IMPORTED", "FAILED", "CANCELLED"]),
            ScrapeRun.created_at
            < datetime.now(UTC) - timedelta(days=config.retention_days),
        )
    )
    active = await session.scalar(
        select(ScrapeRun)
        .where(
            ScrapeRun.group_id == context.group.id,
            ScrapeRun.status.in_(ACTIVE_STATUSES),
        )
        .order_by(ScrapeRun.created_at.desc())
    )
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SCRAPER_RUN_ACTIVE",
                "message": "Resume or cancel the existing scraper run first.",
                "runId": active.id,
            },
        )
    item = ScrapeRun(
        id=new_id(),
        group_id=context.group.id,
        status="CREATED",
        config_version=config.version,
        config_hash=config.content_hash,
        target_job_count=config.target_job_count,
        bright_data_limit=config.bright_data_limit,
    )
    session.add(item)
    # Flush the parent before source synchronization or attempt inserts trigger
    # an autoflush; PostgreSQL enforces the run foreign key immediately.
    await session.flush()
    await sync_seed_sources(session, context.group.id)
    cached = (
        await session.scalars(
            select(ScrapeSource)
            .where(
                ScrapeSource.group_id == context.group.id,
                ScrapeSource.active.is_(True),
                ScrapeSource.ats_type.in_(config.ats_types),
                or_(
                    ScrapeSource.cooldown_until.is_(None),
                    ScrapeSource.cooldown_until <= datetime.now(UTC),
                ),
            )
            .order_by(ScrapeSource.eligible_yield.desc(), ScrapeSource.ats_type)
        )
    ).all()
    attempts = [
        ScrapeAttempt(
            id=new_id(),
            run_id=item.id,
            step_key=f"poll:{source.source_key}",
            source_key=source.source_key,
            provider=source.ats_type,
            status="PENDING",
        )
        for source in cached
    ]
    session.add_all(attempts)
    item.source_count = len(attempts)
    await session.commit()
    await session.refresh(item)
    return run_summary(item)


@router.get("/runs/{run_id}", response_model=ScrapeRunSummary)
async def get_run(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeRunSummary:
    return run_summary(await owned_run(session, user.id, run_id))


@router.get("/runs/{run_id}/attempts", response_model=ScrapeAttemptPage)
async def list_run_attempts(
    run_id: str,
    user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 25,
) -> ScrapeAttemptPage:
    run = await owned_run(session, user.id, run_id)
    where = ScrapeAttempt.run_id == run.id
    total = (
        await session.scalar(
            select(func.count()).select_from(ScrapeAttempt).where(where)
        )
        or 0
    )
    items = (
        await session.scalars(
            select(ScrapeAttempt)
            .where(where)
            .order_by(ScrapeAttempt.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return ScrapeAttemptPage(
        items=[attempt_response(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/runs/{run_id}/candidates", response_model=ScrapeCandidatePage)
async def list_run_candidates(
    run_id: str,
    user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
    review_group: Annotated[str | None, Query(alias="reviewGroup")] = None,
) -> ScrapeCandidatePage:
    run = await owned_run(session, user.id, run_id)
    where = [ScrapeCandidate.run_id == run.id]
    if review_group:
        where.append(ScrapeCandidate.review_group == review_group.upper())
    total = (
        await session.scalar(
            select(func.count()).select_from(ScrapeCandidate).where(*where)
        )
        or 0
    )
    items = (
        await session.scalars(
            select(ScrapeCandidate)
            .where(*where)
            .order_by(
                case(
                    (ScrapeCandidate.review_group == "RECOMMENDED", 0),
                    (ScrapeCandidate.review_group == "NEEDS_REVIEW", 1),
                    else_=2,
                ),
                ScrapeCandidate.quality_score.desc(),
                ScrapeCandidate.posted_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return ScrapeCandidatePage(
        items=[candidate_response(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/runs/{run_id}/candidates/{candidate_id}", response_model=ScrapeCandidateDetail
)
async def get_run_candidate(
    run_id: str, candidate_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeCandidateDetail:
    run = await owned_run(session, user.id, run_id)
    item = await session.scalar(
        select(ScrapeCandidate).where(
            ScrapeCandidate.run_id == run.id, ScrapeCandidate.id == candidate_id
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Scraper candidate not found.")
    return ScrapeCandidateDetail(
        **candidate_response(item).model_dump(),
        payload=item.payload,
        evidence_spans=item.evidence_spans or [],
    )


@router.get("/runs/{run_id}/stats", response_model=ScrapeRunStats)
async def get_run_stats(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeRunStats:
    run = await owned_run(session, user.id, run_id)
    candidates = (
        await session.scalars(
            select(ScrapeCandidate).where(ScrapeCandidate.run_id == run.id)
        )
    ).all()
    by_ats: dict[str, dict[str, int]] = {}
    reasons: dict[str, int] = {}
    for candidate in candidates:
        bucket = by_ats.setdefault(
            candidate.ats_type, {"recommended": 0, "needsReview": 0, "rejected": 0}
        )
        key = {"RECOMMENDED": "recommended", "NEEDS_REVIEW": "needsReview"}.get(
            candidate.review_group, "rejected"
        )
        bucket[key] += 1
        for reason in candidate.quality_failures or []:
            reasons[str(reason)] = reasons.get(str(reason), 0) + 1
    return ScrapeRunStats(by_ats=by_ats, by_rejection_reason=reasons)


async def stage_jobs(
    session: AsyncSession,
    run: ScrapeRun,
    attempt: ScrapeAttempt,
    jobs: list[dict],
) -> tuple[int, int]:
    config = load_scraper_config()
    valid_added = 0
    duplicate_count = 0
    current_valid = (
        await session.scalar(
            select(func.count())
            .select_from(ScrapeCandidate)
            .where(
                ScrapeCandidate.run_id == run.id,
                ScrapeCandidate.schema_valid.is_(True),
                ScrapeCandidate.source_quality_valid.is_(True),
                ScrapeCandidate.review_group.in_(["RECOMMENDED", "NEEDS_REVIEW"]),
            )
        )
        or 0
    )
    company_counts: dict[str, int] = {}
    existing_companies = (
        await session.scalars(
            select(ScrapeCandidate.company_name).where(
                ScrapeCandidate.run_id == run.id,
                ScrapeCandidate.selected.is_(True),
            )
        )
    ).all()
    for company in existing_companies:
        key = str(company).casefold()
        company_counts[key] = company_counts.get(key, 0) + 1
    for job in jobs:
        title_value = str(job.get("roleTitle") or "").casefold()
        if not any(alias in title_value for alias in config.title_aliases):
            continue
        assessment = assess_candidate(job, config)
        payload = {key: value for key, value in job.items() if not key.startswith("__")}
        try:
            canonical = canonical_candidate_url(payload)
        except ValueError:
            continue
        if await session.scalar(
            select(ScrapeCandidate.id).where(
                ScrapeCandidate.run_id == run.id,
                ScrapeCandidate.canonical_url == canonical,
            )
        ):
            duplicate_count += 1
            continue
        duplicate_description = await session.scalar(
            select(ScrapeCandidate.id).where(
                ScrapeCandidate.run_id == run.id,
                ScrapeCandidate.description_fingerprint
                == assessment.description_fingerprint,
            )
        )
        valid, errors = validate_candidate(payload)
        posted_at = parse_datetime(payload.get("postedAt"))
        repeated_timestamp = False
        if posted_at is not None:
            timestamp_count = (
                await session.scalar(
                    select(func.count())
                    .select_from(ScrapeCandidate)
                    .where(
                        ScrapeCandidate.run_id == run.id,
                        ScrapeCandidate.source_key == attempt.source_key,
                        ScrapeCandidate.posted_at == posted_at,
                    )
                )
                or 0
            )
            repeated_timestamp = timestamp_count >= 10
        company_name = str(payload.get("companyName") or "Unknown")
        company_key = company_name.casefold()
        failures = list(assessment.quality_failures)
        review_group = assessment.review_group
        if duplicate_description:
            failures.append("DUPLICATE_DESCRIPTION")
            review_group = "REJECTED"
            duplicate_count += 1
        if repeated_timestamp:
            failures.append("SUSPICIOUS_TIMESTAMP_REUSE")
            if review_group == "RECOMMENDED":
                review_group = "NEEDS_REVIEW"
        if (
            review_group == "RECOMMENDED"
            and company_counts.get(company_key, 0) >= config.max_candidates_per_company
        ):
            failures.append("COMPANY_SELECTION_CAP")
            review_group = "NEEDS_REVIEW"
        if (
            review_group == "RECOMMENDED"
            and current_valid + valid_added >= run.target_job_count
        ):
            failures.append("RUN_TARGET_REACHED")
            review_group = "NEEDS_REVIEW"
        selectable = (
            valid
            and assessment.source_quality_valid
            and review_group == "RECOMMENDED"
        )
        session.add(
            ScrapeCandidate(
                id=new_id(),
                run_id=run.id,
                source_key=attempt.source_key,
                source_provider=attempt.provider,
                ats_type=attempt.provider,
                source_url=str(payload.get("applyUrl") or ""),
                canonical_url=canonical,
                company_name=company_name,
                role_title=str(payload.get("roleTitle") or "Unknown"),
                location=payload.get("location"),
                experience_min_years=payload.get("experienceMinYears"),
                experience_max_years=payload.get("experienceMaxYears"),
                posted_at=posted_at,
                geography_eligibility=assessment.geography_eligibility,
                source_quality_valid=assessment.source_quality_valid,
                quality_failures=failures,
                description_length=len(str(payload.get("description") or "")),
                date_evidence=assessment.date_evidence,
                freshness_tier=assessment.freshness_tier,
                quality_score=assessment.quality_score,
                review_group=review_group,
                extracted_facts=assessment.extracted_facts,
                evidence_spans=list(assessment.evidence_spans),
                extraction_version=assessment.extraction_version,
                description_fingerprint=assessment.description_fingerprint,
                payload=payload,
                schema_valid=valid,
                selected=selectable,
                validation_errors=errors or None,
            )
        )
        if selectable:
            valid_added += 1
            company_counts[company_key] = company_counts.get(company_key, 0) + 1
    return valid_added, duplicate_count


async def reclassify_run_candidates(
    session: AsyncSession, run: ScrapeRun
) -> None:
    """Apply the current import-vs-review policy to an existing run.

    This makes policy changes usable for a run that was already collecting when
    the service reloaded. Owner selections are preserved when the candidate is
    still importable; only recommendations are selected automatically.
    """
    config = load_scraper_config()
    rows = list(
        (
            await session.scalars(
                select(ScrapeCandidate)
                .where(ScrapeCandidate.run_id == run.id)
                .order_by(
                    ScrapeCandidate.quality_score.desc(),
                    ScrapeCandidate.created_at,
                )
            )
        ).all()
    )
    company_auto_counts: dict[str, int] = {}
    operational_failures = {
        "DUPLICATE_DESCRIPTION",
        "SUSPICIOUS_TIMESTAMP_REUSE",
        "COMPANY_SELECTION_CAP",
        "RUN_TARGET_REACHED",
    }
    for candidate in rows:
        payload = dict(candidate.payload or {})
        assessment = assess_candidate(payload, config)
        valid, errors = validate_candidate(payload)
        failures = list(assessment.quality_failures)
        for failure in candidate.quality_failures or []:
            if failure in operational_failures and failure not in failures:
                failures.append(failure)

        review_group = assessment.review_group
        source_quality_valid = assessment.source_quality_valid
        if "DUPLICATE_DESCRIPTION" in failures:
            review_group = "REJECTED"
            source_quality_valid = False
        elif (
            operational_failures.intersection(failures)
            and review_group == "RECOMMENDED"
        ):
            review_group = "NEEDS_REVIEW"

        company_key = candidate.company_name.casefold()
        auto_selected = review_group == "RECOMMENDED"
        if (
            auto_selected
            and company_auto_counts.get(company_key, 0)
            >= config.max_candidates_per_company
        ):
            if "COMPANY_SELECTION_CAP" not in failures:
                failures.append("COMPANY_SELECTION_CAP")
            review_group = "NEEDS_REVIEW"
            auto_selected = False
        if auto_selected:
            company_auto_counts[company_key] = (
                company_auto_counts.get(company_key, 0) + 1
            )

        importable = valid and source_quality_valid and review_group != "REJECTED"
        candidate.payload = payload
        candidate.experience_min_years = payload.get("experienceMinYears")
        candidate.experience_max_years = payload.get("experienceMaxYears")
        candidate.geography_eligibility = assessment.geography_eligibility
        candidate.source_quality_valid = source_quality_valid
        candidate.quality_failures = failures
        candidate.date_evidence = assessment.date_evidence
        candidate.freshness_tier = assessment.freshness_tier
        candidate.quality_score = assessment.quality_score
        candidate.review_group = review_group
        candidate.extracted_facts = assessment.extracted_facts
        candidate.evidence_spans = list(assessment.evidence_spans)
        candidate.extraction_version = assessment.extraction_version
        candidate.schema_valid = valid
        candidate.validation_errors = errors or None
        candidate.selected = importable and (candidate.selected or auto_selected)


@router.post("/runs/{run_id}/advance", response_model=ScrapeRunSummary)
async def advance_run(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeRunSummary:
    run = await owned_run(session, user.id, run_id, lock=True)
    if run.status not in {"CREATED", "RUNNING"}:
        return run_summary(run)
    now = datetime.now(UTC)
    await session.execute(
        update(ScrapeAttempt)
        .where(
            ScrapeAttempt.run_id == run.id,
            ScrapeAttempt.status == "RUNNING",
            ScrapeAttempt.lease_expires_at < now,
        )
        .values(status="PENDING", lease_expires_at=None)
    )
    config = load_scraper_config()
    running_attempts = (
        await session.scalar(
            select(func.count())
            .select_from(ScrapeAttempt)
            .where(
                ScrapeAttempt.run_id == run.id,
                ScrapeAttempt.status == "RUNNING",
            )
        )
        or 0
    )
    if running_attempts >= config.concurrent_sources:
        return run_summary(run)
    pending_attempts = list(
        (
            await session.scalars(
                select(ScrapeAttempt)
                .where(
                    ScrapeAttempt.run_id == run.id,
                    ScrapeAttempt.status == "PENDING",
                )
                .order_by(ScrapeAttempt.created_at, ScrapeAttempt.step_key)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    completed_by_provider = dict(
        (
            await session.execute(
                select(ScrapeAttempt.provider, func.count())
                .where(
                    ScrapeAttempt.run_id == run.id,
                    ScrapeAttempt.status == "SUCCEEDED",
                )
                .group_by(ScrapeAttempt.provider)
            )
        ).all()
    )
    source_health = {
        source.source_key: source
        for source in (
            await session.scalars(
                select(ScrapeSource).where(ScrapeSource.group_id == run.group_id)
            )
        ).all()
    }
    attempt = min(
        pending_attempts,
        key=lambda row: (
            completed_by_provider.get(row.provider, 0),
            config.ats_types.index(row.provider)
            if row.provider in config.ats_types
            else -1,
            -(
                source_health.get(row.source_key).eligible_yield
                if source_health.get(row.source_key)
                else 0
            ),
            row.step_key,
        ),
        default=None,
    )
    if attempt is None:
        await refresh_counts(session, run)
        await finish_if_ready(session, run)
        await session.commit()
        return run_summary(run)
    if (
        attempt.provider.startswith("brightdata")
        and run.bright_data_used >= run.bright_data_limit
    ):
        attempt.status = "FAILED"
        attempt.error_message = "Bright Data per-run limit reached."
        await refresh_counts(session, run)
        await session.commit()
        return run_summary(run)
    run.status = "RUNNING"
    attempt.status = "RUNNING"
    attempt.attempt_count += 1
    attempt.lease_expires_at = now + timedelta(seconds=config.lease_seconds)
    await session.commit()

    stored = source_health.get(attempt.source_key)
    started = perf_counter()
    result: FetchResult | None = None
    fetch_error: Exception | None = None
    try:
        if stored is None:
            raise RuntimeError("The cached ATS source no longer exists.")
        source = SourceSpec(
            source_key=stored.source_key,
            name=stored.name,
            ats_type=stored.ats_type,
            domain_hint=stored.domain_hint,
            board_token=stored.board_token,
            discovered=stored.discovered,
        )
        remaining_units = max(0, run.bright_data_limit - run.bright_data_used)
        source_config = replace(
            config,
            bright_data_limit=remaining_units // config.concurrent_sources,
        )
        result = await fetch_source_jobs(
            source,
            source_config,
            checkpoint=attempt.checkpoint,
            etag=stored.etag,
            last_modified=stored.last_modified,
            cached_jobs=stored.response_cache,
        )
    except Exception as exc:
        fetch_error = exc

    # The source request runs without a database transaction. Re-lock and
    # refresh persisted state before applying its result so a Cancel request
    # that completed during the fetch always wins.
    run = await owned_run(session, user.id, run_id, lock=True)
    attempt = await session.scalar(
        select(ScrapeAttempt)
        .where(ScrapeAttempt.id == attempt.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if attempt is None:
        raise HTTPException(status_code=409, detail="Scraper attempt disappeared.")
    if run.status not in {"CREATED", "RUNNING"} or attempt.status != "RUNNING":
        attempt.lease_expires_at = None
        await session.commit()
        return run_summary(run)

    stored = await session.scalar(
        select(ScrapeSource)
        .where(
            ScrapeSource.group_id == run.group_id,
            ScrapeSource.source_key == attempt.source_key,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if fetch_error is None and result is not None:
        attempt.discovered_count += len(result.jobs)
        attempt.bright_data_used += result.bright_data_used
        attempt.free_request_count += result.free_requests
        run.bright_data_used += result.bright_data_used
        run.bright_data_fallback_count += result.bright_data_used
        run.free_request_count += result.free_requests
        valid_added, duplicates = await stage_jobs(session, run, attempt, result.jobs)
        attempt.valid_count += valid_added
        stored.last_seen_at = now
        stored.last_success_at = now
        stored.last_failure_at = None
        stored.health_status = "HEALTHY"
        stored.consecutive_failures = 0
        stored.jobs_scanned = len(result.jobs)
        stored.eligible_yield = valid_added
        stored.duplicate_yield = duplicates
        stored.consecutive_zero_yield = (
            0 if valid_added else stored.consecutive_zero_yield + 1
        )
        stored.cooldown_until = (
            now + timedelta(hours=24) if stored.consecutive_zero_yield >= 3 else None
        )
        if stored.cooldown_until:
            stored.health_status = "COOLDOWN"
        stored.etag = result.etag or stored.etag
        stored.last_modified = result.last_modified or stored.last_modified
        merged_cache: dict[str, dict] = {}
        for cached_job in [*(stored.response_cache or []), *result.jobs]:
            try:
                merged_cache[canonical_candidate_url(cached_job)] = cached_job
            except ValueError:
                continue
        stored.response_cache = list(merged_cache.values())[-1000:]
        stored.last_checkpoint = result.next_checkpoint
        attempt.checkpoint = result.next_checkpoint
        for use in result.provider_uses:
            session.add(
                ScrapeProviderUse(
                    id=new_id(),
                    run_id=run.id,
                    attempt_id=attempt.id,
                    candidate_url=str(use["candidateUrl"]),
                    provider=str(use["provider"]),
                    units=int(use.get("units", 1)),
                    reason=str(use["reason"]),
                )
            )
        attempt.status = "PENDING" if result.next_checkpoint else "SUCCEEDED"
        attempt.error_message = None
    else:
        attempt.status = "FAILED"
        attempt.error_message = str(fetch_error or "Source returned no result.")[:500]
        if stored is not None:
            stored.health_status = "FAILING"
            stored.last_failure_at = now
            stored.consecutive_failures += 1
            if stored.consecutive_failures >= 3:
                stored.cooldown_until = now + timedelta(hours=24)
                stored.health_status = "COOLDOWN"
    attempt.lease_expires_at = None
    attempt.response_time_ms = int((perf_counter() - started) * 1000)
    if stored is not None:
        stored.response_time_ms = attempt.response_time_ms
    await session.flush()
    await refresh_counts(session, run)
    await finish_if_ready(session, run)
    await session.commit()
    await session.refresh(run)
    return run_summary(run)


@router.post("/runs/{run_id}/retry-failed", response_model=ScrapeRunSummary)
async def retry_failed(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeRunSummary:
    run = await owned_run(session, user.id, run_id, lock=True)
    if run.status not in {"REVIEW_READY", "FAILED", "RUNNING"}:
        raise HTTPException(status_code=409, detail="This run cannot retry sources.")
    await session.execute(
        update(ScrapeAttempt)
        .where(
            ScrapeAttempt.run_id == run.id,
            ScrapeAttempt.status == "FAILED",
        )
        .values(status="PENDING", error_message=None, lease_expires_at=None)
    )
    run.status = "RUNNING"
    run.stopped_early = False
    run.error_message = None
    await refresh_counts(session, run)
    await session.commit()
    return run_summary(run)


@router.post("/runs/{run_id}/stop-and-review", response_model=ScrapeRunSummary)
async def stop_and_review(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeRunSummary:
    run = await owned_run(session, user.id, run_id, lock=True)
    if run.status == "REVIEW_READY":
        return run_summary(run)
    if run.status not in {"CREATED", "RUNNING"}:
        raise HTTPException(
            status_code=409, detail="This run cannot be stopped for review."
        )
    run.status = "REVIEW_READY"
    run.stopped_early = True
    run.error_message = None
    await session.execute(
        update(ScrapeAttempt)
        .where(
            ScrapeAttempt.run_id == run.id,
            ScrapeAttempt.status == "RUNNING",
        )
        .values(status="PENDING", lease_expires_at=None)
    )
    await reclassify_run_candidates(session, run)
    await refresh_counts(session, run)
    await session.commit()
    return run_summary(run)


@router.post("/runs/{run_id}/resume", response_model=ScrapeRunSummary)
async def resume_run(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeRunSummary:
    run = await owned_run(session, user.id, run_id, lock=True)
    if run.status in {"CREATED", "RUNNING"}:
        return run_summary(run)
    if run.status != "REVIEW_READY":
        raise HTTPException(
            status_code=409, detail="This run cannot resume collection."
        )
    remaining = (
        await session.scalar(
            select(func.count())
            .select_from(ScrapeAttempt)
            .where(
                ScrapeAttempt.run_id == run.id,
                ScrapeAttempt.status == "PENDING",
            )
        )
        or 0
    )
    if not remaining:
        raise HTTPException(
            status_code=409,
            detail="Every configured source has already been processed.",
        )
    run.status = "RUNNING"
    run.stopped_early = False
    run.error_message = None
    await session.commit()
    return run_summary(run)


@router.patch("/runs/{run_id}/selection", response_model=ScrapeRunSummary)
async def update_selection(
    run_id: str,
    body: ScrapeSelectionRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> ScrapeRunSummary:
    run = await owned_run(session, user.id, run_id, lock=True)
    if run.status != "REVIEW_READY":
        raise HTTPException(
            status_code=409, detail="Candidates are not ready for review."
        )
    await session.execute(
        update(ScrapeCandidate)
        .where(
            ScrapeCandidate.run_id == run.id,
            ScrapeCandidate.id.in_(body.candidate_ids),
            ScrapeCandidate.schema_valid.is_(True),
            ScrapeCandidate.source_quality_valid.is_(True),
            ScrapeCandidate.review_group.in_(["RECOMMENDED", "NEEDS_REVIEW"]),
        )
        .values(selected=body.selected)
    )
    await refresh_selected_count(session, run)
    await session.commit()
    return run_summary(run)


@router.patch("/runs/{run_id}/selection/all", response_model=ScrapeRunSummary)
async def update_all_selection(
    run_id: str,
    body: ScrapeBulkSelectionRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> ScrapeRunSummary:
    run = await owned_run(session, user.id, run_id, lock=True)
    if run.status != "REVIEW_READY":
        raise HTTPException(
            status_code=409, detail="Candidates are not ready for review."
        )
    where = [ScrapeCandidate.run_id == run.id]
    if body.selected:
        where.extend(
            [
                ScrapeCandidate.schema_valid.is_(True),
                ScrapeCandidate.source_quality_valid.is_(True),
                ScrapeCandidate.review_group.in_(["RECOMMENDED", "NEEDS_REVIEW"]),
            ]
        )
    if body.review_group:
        where.append(ScrapeCandidate.review_group == body.review_group)
    await session.execute(
        update(ScrapeCandidate).where(*where).values(selected=body.selected)
    )
    await refresh_selected_count(session, run)
    await session.commit()
    return run_summary(run)


@router.post("/runs/{run_id}/cancel", response_model=ScrapeRunSummary)
async def cancel_run(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeRunSummary:
    run = await owned_run(session, user.id, run_id, lock=True)
    if run.status == "CANCELLED":
        await session.execute(
            update(ScrapeAttempt)
            .where(
                ScrapeAttempt.run_id == run.id,
                ScrapeAttempt.status == "RUNNING",
            )
            .values(status="PENDING", lease_expires_at=None)
        )
        await session.commit()
        return run_summary(run)
    if run.status not in CANCELLABLE_STATUSES:
        raise HTTPException(status_code=409, detail="This run cannot be cancelled.")
    run.status = "CANCELLED"
    run.completed_at = datetime.now(UTC)
    await session.execute(
        update(ScrapeAttempt)
        .where(
            ScrapeAttempt.run_id == run.id,
            ScrapeAttempt.status == "RUNNING",
        )
        .values(status="PENDING", lease_expires_at=None)
    )
    await session.commit()
    return run_summary(run)


@router.post("/runs/{run_id}/import", response_model=ScrapeImportResponse)
async def import_run(
    run_id: str,
    body: ScrapeImportRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> ScrapeImportResponse:
    run = await owned_run(session, user.id, run_id, lock=True)
    if run.status == "IMPORTED" and run.imported_batch_id:
        imported = await session.get(Batch, run.imported_batch_id)
        if imported is None:
            raise HTTPException(
                status_code=409, detail="The imported batch is missing."
            )
        return ScrapeImportResponse(
            run=run_summary(run),
            batch=batch_response(imported, replayed=True),
            normalization={"status": "NORMALIZED", "replayed": True},
        )
    if run.status == "NORMALIZATION_FAILED" and run.imported_batch_id:
        return await _resume_scraper_normalization(session, run)
    if run.status not in {"REVIEW_READY", "IMPORTING"}:
        raise HTTPException(status_code=409, detail="This run is not ready to import.")
    if (
        run.status == "REVIEW_READY"
        and (
            run.failed_source_count
            or run.processed_source_count < run.source_count
        )
        and not body.confirm_partial
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PARTIAL_CONFIRMATION_REQUIRED",
                "message": (
                    "Confirm the unfinished or failed sources before importing "
                    "partial results."
                ),
            },
        )
    selected = (
        await session.scalars(
            select(ScrapeCandidate).where(
                ScrapeCandidate.run_id == run.id,
                ScrapeCandidate.schema_valid.is_(True),
                ScrapeCandidate.source_quality_valid.is_(True),
                ScrapeCandidate.review_group.in_(["RECOMMENDED", "NEEDS_REVIEW"]),
                ScrapeCandidate.selected.is_(True),
            )
        )
    ).all()
    if not selected:
        raise HTTPException(status_code=422, detail="Select at least one valid job.")
    envelope = {
        "externalBatchId": f"scraper-{run.id}",
        "schemaVersion": "jedi-import-v1",
        "promptVersion": "jedi-site-scraper-v2",
        "generatedAt": run.created_at.isoformat(),
        "jobs": [candidate.payload for candidate in selected],
    }
    if run.status == "REVIEW_READY":
        run.status = "IMPORTING"
        run.error_message = None
        await session.commit()
    try:
        batch = await ingest_batch(session, envelope)
    except Exception as exc:
        await session.rollback()
        run = await session.get(ScrapeRun, run_id)
        if run:
            run.status = "REVIEW_READY"
            run.error_message = "Import did not complete. It is safe to retry."
            await session.commit()
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SCRAPER_IMPORT_RETRYABLE",
                "message": "Import did not complete. It is safe to retry.",
            },
        ) from exc
    run = await session.get(ScrapeRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=500, detail="Scraper run disappeared after import."
        )
    run.imported_batch_id = batch.batch_id
    run.status = "NORMALIZING"
    await session.commit()
    return await _resume_scraper_normalization(session, run, batch_response_value=batch)


async def _resume_scraper_normalization(
    session: AsyncSession,
    run: ScrapeRun,
    *,
    batch_response_value=None,
) -> ScrapeImportResponse:
    if not run.imported_batch_id:
        raise HTTPException(status_code=409, detail="The imported batch is missing.")
    imported = await session.get(Batch, run.imported_batch_id)
    if imported is None:
        raise HTTPException(status_code=409, detail="The imported batch is missing.")
    run.status = "NORMALIZING"
    run.error_message = None
    await session.commit()
    try:
        normalized = await normalize_batch_service(
            session,
            imported.id,
            apply_inr_policy=True,
            trigger="SCRAPER",
        )
    except Exception as exc:
        await session.rollback()
        run = await session.get(ScrapeRun, run.id)
        if run:
            run.status = "NORMALIZATION_FAILED"
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            run.error_message = str(detail)[:500]
            await session.commit()
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SCRAPER_NORMALIZATION_RETRYABLE",
                "message": "Normalization was interrupted. Retry normalization.",
            },
        ) from exc
    run = await session.get(ScrapeRun, run.id)
    if run is None:
        raise HTTPException(
            status_code=500, detail="Scraper run disappeared after normalization."
        )
    run.status = "IMPORTED"
    run.completed_at = datetime.now(UTC)
    await session.commit()
    return ScrapeImportResponse(
        run=run_summary(run),
        batch=batch_response(
            imported,
            replayed=(
                batch_response_value.replayed
                if batch_response_value is not None
                else True
            ),
        ),
        normalization=normalized.model_dump(mode="json", by_alias=True),
    )


@router.post("/runs/{run_id}/retry-normalization", response_model=ScrapeImportResponse)
async def retry_normalization(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeImportResponse:
    run = await owned_run(session, user.id, run_id, lock=True)
    if run.status not in {"NORMALIZATION_FAILED", "NORMALIZING"}:
        raise HTTPException(
            status_code=409, detail="This run has no failed normalization to retry."
        )
    return await _resume_scraper_normalization(session, run)
