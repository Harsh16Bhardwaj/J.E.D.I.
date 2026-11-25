"""Owner-only manual scraper orchestration and staged import endpoints."""

import asyncio
import logging
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from backend.auth import CurrentUser, ServiceToken
from backend.config import get_settings
from backend.database import (
    Batch,
    Group,
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
    ScrapeBoardStats,
    ScrapeBulkSelectionRequest,
    ScrapeCandidateDetail,
    ScrapeCandidatePage,
    ScrapeCandidateResponse,
    ScrapeImportRequest,
    ScrapeImportResponse,
    ScrapeImportTick,
    ScraperConfigSummary,
    ScrapeRunDetail,
    ScrapeRunPage,
    ScrapeRunStats,
    ScrapeRunSummary,
    ScrapeSelectionRequest,
    ScrapeSourceCreateRequest,
    ScrapeSourceResponse,
    ScrapeSourceRunOutcome,
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
    provider_retry_at,
    seeded_source_specs,
    source_identity_consistent,
    validate_candidate,
)

logger = logging.getLogger(__name__)
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
IMPORT_CHECKPOINTS = ("IMPORTING", "NORMALIZING")


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
            await session.scalars(source_metadata(group_id))
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


def source_metadata(group_id: str):
    return (
        select(ScrapeSource)
        .options(defer(ScrapeSource.response_cache, raiseload=True))
        .where(ScrapeSource.group_id == group_id)
    )


def run_summary(
    item: ScrapeRun, *, next_retry_at: datetime | None = None
) -> ScrapeRunSummary:
    provider_reason = item.provider_usage_reason or (
        "Direct ATS requests succeeded; no blocked detail page required Web Unlocker."
        if item.bright_data_used == 0
        else "Web Unlocker handled blocked or incomplete ATS detail pages."
    )
    return ScrapeRunSummary(
        next_retry_at=next_retry_at.replace(tzinfo=UTC) if next_retry_at else None,
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
    items = (
        await session.scalars(
            source_metadata(context.group.id)
            .order_by(ScrapeSource.ats_type, ScrapeSource.name)
        )
    ).all()
    existing_keys = {item.source_key for item in items}
    if any(
        source.source_key not in existing_keys
        for source in seeded_source_specs(load_scraper_config())
    ):
        # Serialize seed creation with run creation and source edits.
        await require_group_owner(session, user.id, lock=True)
        items = await sync_seed_sources(session, context.group.id)
        await session.commit()
        items.sort(key=lambda item: (item.ats_type, item.name))
    ranked = (
        select(
            ScrapeAttempt.source_key,
            ScrapeAttempt.run_id,
            ScrapeAttempt.status,
            ScrapeAttempt.updated_at,
            ScrapeAttempt.discovered_count,
            ScrapeAttempt.valid_count,
            ScrapeAttempt.error_message,
            func.row_number()
            .over(
                partition_by=ScrapeAttempt.source_key,
                order_by=(ScrapeAttempt.updated_at.desc(), ScrapeAttempt.id.desc()),
            )
            .label("position"),
        )
        .join(ScrapeRun, ScrapeRun.id == ScrapeAttempt.run_id)
        .where(
            ScrapeRun.group_id == context.group.id,
            ScrapeAttempt.status.in_(["SUCCEEDED", "FAILED"]),
        )
        .subquery()
    )
    history: dict[str, list[ScrapeSourceRunOutcome]] = {}
    for row in await session.execute(
        select(ranked).where(ranked.c.position <= 10).order_by(ranked.c.position)
    ):
        history.setdefault(row.source_key, []).append(
            ScrapeSourceRunOutcome(
                run_id=row.run_id,
                status=row.status,
                finished_at=row.updated_at,
                jobs_seen=row.discovered_count,
                importable_staged=row.valid_count,
                error_message=row.error_message,
            )
        )
    responses = [source_response(item) for item in items]
    for response in responses:
        response.recent_runs = history.get(response.source_key, [])
    return responses


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
        source_metadata(context.group.id).where(
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
    return source_response(item)


async def owned_source(
    session: AsyncSession, user_id: str, source_id: str, *, lock: bool = False
) -> ScrapeSource:
    context = await require_group_owner(session, user_id, lock=lock)
    statement = source_metadata(context.group.id).where(ScrapeSource.id == source_id)
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
    return source_response(item)


@router.post("/sources/{source_id}/revalidate", response_model=ScrapeSourceResponse)
async def revalidate_source(
    source_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeSourceResponse:
    item = await owned_source(session, user.id, source_id)
    revision = item.updated_at
    config = replace(load_scraper_config(), bright_data_limit=0)
    source = SourceSpec(
        source_key=item.source_key,
        name=item.name,
        ats_type=item.ats_type,
        domain_hint=item.domain_hint,
        board_token=item.board_token,
        discovered=item.discovered,
    )
    await session.commit()
    started = perf_counter()
    error = None
    job_count = 0
    try:
        async with asyncio.timeout(25):
            result = await fetch_source_jobs(source, config, allow_unlocker=False)
        if result.jobs and not source_identity_consistent(
            source.name, source, result.jobs
        ):
            raise RuntimeError("Source identity or direct vacancy validation failed.")
        job_count = len(result.jobs)
    except TimeoutError:
        error = "The employer board did not respond in time."
    except Exception as exc:
        error = str(exc)[:500] or "Could not validate the employer board."

    elapsed = int((perf_counter() - started) * 1000)
    item = await owned_source(session, user.id, source_id, lock=True)
    if item.updated_at != revision:
        raise HTTPException(409, "The source changed during the check. Try again.")
    now = datetime.now(UTC)
    if error is None:
        item.health_status = "HEALTHY"
        item.last_success_at = now
        item.consecutive_failures = 0
        item.cooldown_until = None
        item.jobs_scanned = job_count
    else:
        item.health_status = "FAILING"
        item.last_failure_at = now
        item.consecutive_failures += 1
        if item.consecutive_failures >= 3:
            item.health_status = "COOLDOWN"
            item.cooldown_until = now + timedelta(hours=24)
    item.response_time_ms = elapsed
    await session.commit()
    if error is not None:
        raise HTTPException(status_code=422, detail=error)
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
    claim_number = attempt.attempt_count
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
    if (
        item.status != "RUNNING"
        or attempt.status != "RUNNING"
        or attempt.attempt_count != claim_number
    ):
        return discovery_summary(item)

    attempt.detected_count = len(detected.jobs) if discovery_error is None else 0
    activated = 0
    if discovery_error is None:
        for source, validation in validated_sources:
            stored = await session.scalar(
                source_metadata(item.group_id).where(
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
            source_metadata(context.group.id)
            .where(
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
    run = await owned_run(session, user.id, run_id)
    next_retry_at = None
    if run.status in {"CREATED", "RUNNING"}:
        next_retry_at = await session.scalar(
            select(ScrapeAttempt.retry_at)
            .where(
                ScrapeAttempt.run_id == run.id,
                ScrapeAttempt.status == "PENDING",
            )
            .order_by(ScrapeAttempt.retry_at.asc().nulls_first())
            .limit(1)
        )
        if next_retry_at and next_retry_at.replace(tzinfo=UTC) <= datetime.now(UTC):
            next_retry_at = None
    return run_summary(run, next_retry_at=next_retry_at)


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
            .options(
                defer(ScrapeCandidate.payload, raiseload=True),
                defer(ScrapeCandidate.evidence_spans, raiseload=True),
            )
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
    boards = {
        attempt.source_key: ScrapeBoardStats(
            source_key=attempt.source_key,
            name=name or attempt.source_key,
            ats_type=attempt.provider,
            status=attempt.status,
            jobs_seen=attempt.discovered_count,
            direct_requests=attempt.free_request_count,
            bright_data_used=attempt.bright_data_used,
            error_message=attempt.error_message,
            retry_at=attempt.retry_at.replace(tzinfo=UTC) if attempt.retry_at else None,
            retry_count=attempt.retry_count,
        )
        for attempt, name in await session.execute(
            select(ScrapeAttempt, ScrapeSource.name)
            .outerjoin(
                ScrapeSource,
                (ScrapeSource.group_id == run.group_id)
                & (ScrapeSource.source_key == ScrapeAttempt.source_key),
            )
            .where(ScrapeAttempt.run_id == run.id)
        )
    }
    candidates = await session.execute(
        select(
            ScrapeCandidate.source_key,
            ScrapeCandidate.ats_type,
            ScrapeCandidate.review_group,
            ScrapeCandidate.schema_valid,
            ScrapeCandidate.source_quality_valid,
            ScrapeCandidate.selected,
            ScrapeCandidate.quality_failures,
        ).where(ScrapeCandidate.run_id == run.id)
    )
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
        board = boards.get(candidate.source_key)
        if board is not None:
            board.unique_candidates += 1
            if (
                key != "rejected"
                and candidate.schema_valid
                and candidate.source_quality_valid
            ):
                board.importable += 1
                board.selected += int(candidate.selected)
        for reason in candidate.quality_failures or []:
            reasons[str(reason)] = reasons.get(str(reason), 0) + 1
    imported_jobs = None
    if run.imported_batch_id:
        imported_jobs = await session.scalar(
            select(Batch.job_count).where(Batch.id == run.imported_batch_id)
        )
    return ScrapeRunStats(
        by_ats=by_ats,
        by_rejection_reason=reasons,
        by_board=sorted(
            boards.values(),
            key=lambda board: (
                -board.importable,
                board.name.casefold(),
                board.source_key,
            ),
        ),
        imported_jobs=imported_jobs,
    )


async def stage_jobs(
    session: AsyncSession,
    run: ScrapeRun,
    attempt: ScrapeAttempt,
    jobs: list[dict],
) -> tuple[int, int]:
    config = load_scraper_config()
    valid_added = 0
    duplicate_count = 0
    # The caller holds the run lock. Read the existing comparison keys once
    # and update the same indexes as new candidates are staged.
    existing = (
        await session.execute(
            select(
                ScrapeCandidate.canonical_url,
                ScrapeCandidate.description_fingerprint,
                ScrapeCandidate.source_key,
                ScrapeCandidate.posted_at,
                ScrapeCandidate.company_name,
                ScrapeCandidate.selected,
                ScrapeCandidate.schema_valid,
                ScrapeCandidate.source_quality_valid,
                ScrapeCandidate.review_group,
            ).where(ScrapeCandidate.run_id == run.id)
        )
    ).all()
    canonical_urls = {row.canonical_url for row in existing}
    descriptions = {row.description_fingerprint for row in existing}
    timestamps = Counter(
        parse_datetime(row.posted_at) for row in existing
        if row.source_key == attempt.source_key and row.posted_at is not None
    )
    company_counts = Counter(
        row.company_name.casefold() for row in existing if row.selected
    )
    current_valid = sum(
        row.schema_valid and row.source_quality_valid
        and row.review_group in {"RECOMMENDED", "NEEDS_REVIEW"}
        for row in existing
    )
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
        if canonical in canonical_urls:
            duplicate_count += 1
            continue
        duplicate_description = assessment.description_fingerprint in descriptions
        valid, errors = validate_candidate(payload)
        posted_at = parse_datetime(payload.get("postedAt"))
        repeated_timestamp = posted_at is not None and timestamps[posted_at] >= 10
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
        canonical_urls.add(canonical)
        descriptions.add(assessment.description_fingerprint)
        if posted_at is not None:
            timestamps[posted_at] += 1
        if selectable:
            valid_added += 1
            company_counts[company_key] += 1
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
                    or_(
                        ScrapeAttempt.retry_at.is_(None),
                        ScrapeAttempt.retry_at <= now,
                    ),
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
            await session.scalars(source_metadata(run.group_id))
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
    stored = source_health.get(attempt.source_key)
    cached_jobs = None
    if (
        stored
        and stored.ats_type == "greenhouse"
        and (stored.etag or stored.last_modified)
    ):
        cached_jobs = await session.scalar(
            select(ScrapeSource.response_cache).where(ScrapeSource.id == stored.id)
        )
    run.status = "RUNNING"
    attempt.status = "RUNNING"
    attempt.attempt_count += 1
    claim_number = attempt.attempt_count
    attempt.retry_at = None
    attempt.error_message = None
    attempt.lease_expires_at = now + timedelta(seconds=config.lease_seconds)
    await session.commit()

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
            cached_jobs=cached_jobs,
            allow_unlocker=attempt.retry_count == 0,
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
    if (
        run.status != "RUNNING"
        or attempt.status != "RUNNING"
        or attempt.attempt_count != claim_number
    ):
        return run_summary(run)

    stored = await session.scalar(
        source_metadata(run.group_id)
        .where(ScrapeSource.source_key == attempt.source_key)
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
        if stored.ats_type == "greenhouse":
            existing_cache = await session.scalar(
                select(ScrapeSource.response_cache).where(ScrapeSource.id == stored.id)
            )
            merged_cache: dict[str, dict] = {}
            for cached_job in [*(existing_cache or []), *result.jobs]:
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
        attempt.retry_count = 0
    else:
        failed_at = datetime.now(UTC)
        retry_at = provider_retry_at(fetch_error, failed_at, attempt.retry_count)
        retrying = retry_at is not None and attempt.retry_count < config.max_retries
        provider_cooldown = (
            retry_at is not None
            and isinstance(fetch_error, httpx.HTTPStatusError)
            and (
                fetch_error.response.status_code == 429
                or "Retry-After" in fetch_error.response.headers
            )
        )
        attempt.status = "PENDING" if retrying else "FAILED"
        attempt.error_message = str(fetch_error or "Source returned no result.")[:500]
        attempt.retry_at = retry_at if retrying or provider_cooldown else None
        if retrying:
            attempt.retry_count += 1
        if stored is not None:
            stored.last_failure_at = failed_at
            if not retrying:
                stored.health_status = "FAILING"
                stored.consecutive_failures += 1
                if stored.consecutive_failures >= 3:
                    stored.cooldown_until = failed_at + timedelta(hours=24)
                    stored.health_status = "COOLDOWN"
            if provider_cooldown and retry_at is not None:
                if stored.cooldown_until is None or retry_at > (
                    stored.cooldown_until.replace(tzinfo=UTC)
                ):
                    stored.cooldown_until = retry_at
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
        .values(
            status="PENDING",
            error_message=None,
            lease_expires_at=None,
            retry_count=0,
        )
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


async def _lock_import_run(
    session: AsyncSession, run: ScrapeRun
) -> ScrapeRun | None:
    return await session.scalar(
        select(ScrapeRun)
        .where(ScrapeRun.id == run.id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )


def _importable_selection(run_id: str):
    return select(ScrapeCandidate.payload).where(
        ScrapeCandidate.run_id == run_id,
        ScrapeCandidate.schema_valid.is_(True),
        ScrapeCandidate.source_quality_valid.is_(True),
        ScrapeCandidate.review_group.in_(["RECOMMENDED", "NEEDS_REVIEW"]),
        ScrapeCandidate.selected.is_(True),
    )


async def _queue_import(
    session: AsyncSession, run: ScrapeRun, *, confirm_partial: bool
) -> ScrapeRun:
    locked = await _lock_import_run(session, run)
    if locked is None:
        if run.status in {"REVIEW_READY", "NORMALIZATION_FAILED"}:
            raise HTTPException(409, "The run is being updated. Try again shortly.")
        return run
    run = locked
    if run.status == "REVIEW_READY":
        if (
            run.failed_source_count or run.processed_source_count < run.source_count
        ) and not confirm_partial:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PARTIAL_CONFIRMATION_REQUIRED",
                    "message": "Confirm unfinished or failed sources before importing.",
                },
            )
        if await session.scalar(_importable_selection(run.id).limit(1)) is None:
            raise HTTPException(422, "Select at least one valid job.")
        run.status = "IMPORTING"
    elif run.status == "NORMALIZATION_FAILED":
        run.status = "NORMALIZING"
    elif run.status not in (*IMPORT_CHECKPOINTS, "IMPORTED"):
        raise HTTPException(status_code=409, detail="This run is not ready to import.")
    run.error_message = None
    await session.commit()
    return run


async def _ingest_scraper_selection(session: AsyncSession, run: ScrapeRun) -> None:
    external_id = f"scraper-{run.id}"
    batch_id = await session.scalar(
        select(Batch.id).where(Batch.external_batch_id == external_id)
    )
    # Older deployments could commit the batch before linking it to the run.
    if batch_id is None:
        selected = (
            await session.scalars(
                _importable_selection(run.id).order_by(ScrapeCandidate.id)
            )
        ).all()
        if not selected:
            raise HTTPException(422, "Select at least one valid job.")
        batch = await ingest_batch(
            session,
            {
                "externalBatchId": external_id,
                "schemaVersion": "jedi-import-v1",
                "promptVersion": "jedi-site-scraper-v2",
                "generatedAt": run.created_at.isoformat(),
                "jobs": list(selected),
            },
            commit=False,
        )
        batch_id = batch.batch_id
    run.imported_batch_id = batch_id
    run.status = "NORMALIZING"


async def _advance_import(
    session: AsyncSession, run: ScrapeRun
) -> tuple[ScrapeRun, dict | None, Exception | None]:
    locked = await _lock_import_run(session, run)
    if locked is None or locked.status not in IMPORT_CHECKPOINTS:
        return locked or run, None, None
    return await _advance_locked_import(session, locked)


async def _advance_locked_import(
    session: AsyncSession, run: ScrapeRun
) -> tuple[ScrapeRun, dict | None, Exception | None]:
    ingesting = run.status == "IMPORTING"
    normalization = None
    error = None
    # The outer transaction holds only this run's lock. Each stage and its
    # checkpoint commit together, and a disconnected worker loses its lock.
    try:
        async with session.begin_nested():
            async with asyncio.timeout(45):
                if ingesting:
                    await _ingest_scraper_selection(session, run)
                else:
                    if not run.imported_batch_id:
                        raise HTTPException(409, "The imported batch is missing.")
                    group = await session.get(Group, run.group_id)
                    if group is None:
                        raise HTTPException(409, "The scraper group is unavailable.")
                    if not group.active_profile_version_id:
                        raise HTTPException(
                            409,
                            (
                                "Create and activate a ProfileVersion "
                                "before normalization."
                            ),
                        )
                    normalized = await normalize_batch_service(
                        session,
                        run.imported_batch_id,
                        profile_version_id=group.active_profile_version_id,
                        apply_inr_policy=True,
                        trigger="SCRAPER",
                        commit=False,
                    )
                    normalization = normalized.model_dump(mode="json", by_alias=True)
                    run.status = "IMPORTED"
                    run.completed_at = datetime.now(UTC)
                await session.flush()
    except Exception as exc:
        error = exc
        await session.refresh(run)
        run.status = "REVIEW_READY" if ingesting else "NORMALIZATION_FAILED"
        if isinstance(exc, HTTPException):
            detail = exc.detail
            run.error_message = (
                detail.get("message", "Import could not complete.")
                if isinstance(detail, dict)
                else str(detail)
            )[:500]
        elif isinstance(exc, TimeoutError):
            run.error_message = "This step timed out. You can safely retry."
        else:
            logger.exception("Scraper import step failed for run %s", run.id)
            run.error_message = "This step could not complete. You can safely retry."
    await session.commit()
    return run, normalization, error


@router.post("/internal/import-tick", response_model=ScrapeImportTick | None)
async def run_scraper_import_tick(
    _service: ServiceToken, session: DatabaseSession
) -> ScrapeImportTick | None:
    run = await session.scalar(
        select(ScrapeRun)
        .where(ScrapeRun.status.in_(IMPORT_CHECKPOINTS))
        .order_by(ScrapeRun.updated_at, ScrapeRun.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if run is None:
        return None
    run, _, _ = await _advance_locked_import(session, run)
    return ScrapeImportTick(
        run_id=run.id, status=run.status, imported_batch_id=run.imported_batch_id
    )


@router.post(
    "/runs/{run_id}/queue-import",
    response_model=ScrapeRunSummary,
    status_code=202,
)
async def queue_scraper_import(
    run_id: str, body: ScrapeImportRequest, user: CurrentUser, session: DatabaseSession
) -> ScrapeRunSummary:
    run = await owned_run(session, user.id, run_id)
    run = await _queue_import(session, run, confirm_partial=body.confirm_partial)
    return run_summary(run)


@router.post("/runs/{run_id}/advance-import", response_model=ScrapeRunSummary)
async def advance_scraper_import(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeRunSummary:
    run = await owned_run(session, user.id, run_id)
    run, _, _ = await _advance_import(session, run)
    return run_summary(run)


async def _complete_legacy_import(
    session: AsyncSession, run: ScrapeRun
) -> ScrapeImportResponse:
    replayed = run.imported_batch_id is not None or await session.scalar(
        select(Batch.id).where(Batch.external_batch_id == f"scraper-{run.id}")
    ) is not None
    normalization = None
    for _ in range(2):
        if run.status not in IMPORT_CHECKPOINTS:
            break
        previous_status = run.status
        run, normalization, error = await _advance_import(session, run)
        if error:
            if isinstance(error, HTTPException):
                raise error
            raise HTTPException(503, run.error_message) from error
        if run.status == previous_status:
            break
    if run.status != "IMPORTED" or not run.imported_batch_id:
        raise HTTPException(409, "Import is still in progress. Check the run status.")
    imported = await session.get(Batch, run.imported_batch_id)
    if imported is None:
        raise HTTPException(409, "The imported batch is missing.")
    return ScrapeImportResponse(
        run=run_summary(run),
        batch=batch_response(imported, replayed=replayed),
        normalization=normalization or {"status": "NORMALIZED", "replayed": True},
    )


@router.post("/runs/{run_id}/import", response_model=ScrapeImportResponse)
async def import_run(
    run_id: str, body: ScrapeImportRequest, user: CurrentUser, session: DatabaseSession
) -> ScrapeImportResponse:
    run = await owned_run(session, user.id, run_id)
    run = await _queue_import(session, run, confirm_partial=body.confirm_partial)
    return await _complete_legacy_import(session, run)


@router.post("/runs/{run_id}/retry-normalization", response_model=ScrapeImportResponse)
async def retry_normalization(
    run_id: str, user: CurrentUser, session: DatabaseSession
) -> ScrapeImportResponse:
    run = await owned_run(session, user.id, run_id)
    if run.status not in {"NORMALIZATION_FAILED", "NORMALIZING", "IMPORTED"}:
        raise HTTPException(409, "This run has no normalization to retry.")
    run = await _queue_import(session, run, confirm_partial=False)
    return await _complete_legacy_import(session, run)
