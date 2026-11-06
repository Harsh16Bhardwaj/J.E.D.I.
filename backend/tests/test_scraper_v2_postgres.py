import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.auth import create_session_token
from backend.config import get_settings
from backend.database import (
    Batch,
    Group,
    GroupMember,
    ProfileVersion,
    ScrapeAttempt,
    ScrapeCandidate,
    ScrapeProviderUse,
    ScrapeRun,
    ScrapeSource,
    SourceDiscoveryAttempt,
    SourceDiscoveryRun,
    User,
    get_session,
)
from backend.main import app
from backend.routers import scraper
from backend.tests.test_scraper_api import scraper_job


def test_scraper_v2_postgres_models_match_deployed_migration() -> None:
    direct_url = get_settings().direct_database_url
    if not direct_url or "USER:PASSWORD@HOST" in direct_url:
        pytest.skip("DIRECT_DATABASE_URL is not configured for PostgreSQL testing.")

    async def verify() -> None:
        suffix = uuid4().hex
        sqlalchemy_url = direct_url.replace("postgresql://", "postgresql+psycopg://", 1)
        engine = create_async_engine(sqlalchemy_url, pool_pre_ping=True)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        source_id = f"scraper-v2-source-{suffix}"
        discovery_id = f"scraper-v2-discovery-{suffix}"
        run_id = f"scraper-v2-run-{suffix}"
        try:
            async with sessions() as session:
                group_id = await session.scalar(select(Group.id).limit(1))
                if group_id is None:
                    pytest.skip("No JEDI group exists for the integration check.")
                session.add(
                    ScrapeSource(
                        id=source_id,
                        group_id=group_id,
                        source_key=f"jsonld:{suffix}",
                        name="Scraper V2 Integration",
                        ats_type="jsonld",
                        domain_hint="example.invalid",
                        board_token="https://example.invalid/careers",
                        discovered=True,
                        health_status="HEALTHY",
                        eligible_yield=1,
                        response_cache=[],
                    )
                )
                session.add(
                    SourceDiscoveryRun(
                        id=discovery_id,
                        group_id=group_id,
                        status="COMPLETED",
                        config_version="jedi-site-scraper-v2",
                        config_hash=suffix,
                        total_hints=1,
                        processed_hints=1,
                        detected_sources=1,
                        activated_sources=1,
                        completed_at=datetime.now(UTC),
                    )
                )
                await session.flush()
                session.add(
                    SourceDiscoveryAttempt(
                        run_id=discovery_id,
                        step_key="company:0:example.invalid",
                        company_name="Scraper V2 Integration",
                        company_domain="example.invalid",
                        status="SUCCEEDED",
                        detected_count=1,
                        activated_count=1,
                    )
                )
                session.add(
                    ScrapeRun(
                        id=run_id,
                        group_id=group_id,
                        status="CANCELLED",
                        config_version="jedi-site-scraper-v2",
                        config_hash=suffix,
                        completed_at=datetime.now(UTC),
                    )
                )
                await session.flush()
                attempt = ScrapeAttempt(
                    run_id=run_id,
                    step_key=f"poll:jsonld:{suffix}",
                    source_key=f"jsonld:{suffix}",
                    provider="jsonld",
                    status="SUCCEEDED",
                    checkpoint={"page": 1},
                    free_request_count=1,
                )
                session.add(attempt)
                session.add(
                    ScrapeCandidate(
                        run_id=run_id,
                        source_key=f"jsonld:{suffix}",
                        source_provider="jsonld",
                        ats_type="jsonld",
                        source_url="https://example.invalid/jobs/1",
                        canonical_url="https://example.invalid/jobs/1",
                        company_name="Scraper V2 Integration",
                        role_title="Backend Engineer",
                        geography_eligibility="ELIGIBLE",
                        source_quality_valid=True,
                        freshness_tier="VERIFIED_RECENT",
                        quality_score=90,
                        review_group="RECOMMENDED",
                        extracted_facts={"skills": ["Python"]},
                        evidence_spans=[{"field": "skills", "text": "Python"}],
                        extraction_version="jedi-scraper-taxonomy-v1",
                        payload={"companyName": "Scraper V2 Integration"},
                        schema_valid=True,
                        selected=True,
                    )
                )
                session.add(
                    ScrapeProviderUse(
                        run_id=run_id,
                        candidate_url="https://example.invalid/jobs/1",
                        provider="brightdata-unlocker",
                        units=1,
                        reason="integration check",
                    )
                )
                await session.commit()

                stored = await session.get(ScrapeSource, source_id)
                assert stored is not None
                assert stored.health_status == "HEALTHY"
                assert stored.eligible_yield == 1
        finally:
            async with sessions() as session:
                await session.execute(delete(ScrapeRun).where(ScrapeRun.id == run_id))
                await session.execute(
                    delete(SourceDiscoveryRun).where(
                        SourceDiscoveryRun.id == discovery_id
                    )
                )
                await session.execute(
                    delete(ScrapeSource).where(ScrapeSource.id == source_id)
                )
                await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_browser_and_worker_serialize_import_checkpoints(monkeypatch) -> None:
    database_url = os.getenv("JEDI_TEST_SCRAPER_DATABASE_URL")
    if not database_url:
        pytest.skip("Set JEDI_TEST_SCRAPER_DATABASE_URL to a dedicated local test DB.")
    url = make_url(database_url)
    assert url.get_backend_name() == "postgresql"
    assert url.host in {"127.0.0.1", "localhost", "::1"}

    async def verify() -> None:
        engine = create_async_engine(url.set(drivername="postgresql+psycopg"))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        suffix = uuid4().hex
        user_id = f"scraper-race-user-{suffix}"
        group_id = f"scraper-race-group-{suffix}"
        profile_id = f"scraper-race-profile-{suffix}"
        run_id = f"scraper-race-run-{suffix}"
        batch_key = f"scraper-{run_id}"
        settings = get_settings()

        async def test_session() -> AsyncIterator[AsyncSession]:
            async with sessions() as session:
                yield session

        ingest_started, finish_ingest = asyncio.Event(), asyncio.Event()
        normalize_started, finish_normalization = asyncio.Event(), asyncio.Event()
        ingest, normalize = (
            scraper._ingest_scraper_selection,
            scraper.normalize_batch_service,
        )
        ingest_calls = normalization_calls = 0

        async def gated_ingest(*args, **kwargs):
            nonlocal ingest_calls
            ingest_calls += 1
            ingest_started.set()
            await finish_ingest.wait()
            return await ingest(*args, **kwargs)

        async def gated_normalization(*args, **kwargs):
            nonlocal normalization_calls
            normalization_calls += 1
            normalize_started.set()
            await finish_normalization.wait()
            return await normalize(*args, **kwargs)

        monkeypatch.setattr(scraper, "_ingest_scraper_selection", gated_ingest)
        monkeypatch.setattr(scraper, "normalize_batch_service", gated_normalization)
        monkeypatch.setitem(app.dependency_overrides, get_session, test_session)

        try:
            async with sessions() as session:
                assert not await session.scalar(
                    select(ScrapeRun.id)
                    .where(ScrapeRun.status.in_(scraper.IMPORT_CHECKPOINTS))
                    .limit(1)
                ), "Use a test database with no queued scraper imports."
                owner = User(
                    id=user_id,
                    email=f"{suffix}@example.invalid",
                    password_hash="unused",
                )
                session.add(owner)
                await session.flush()
                session.add(Group(id=group_id, owner_id=user_id))
                await session.flush()
                session.add(GroupMember(group_id=group_id, user_id=user_id))
                if not await session.scalar(
                    select(ProfileVersion.id).where(ProfileVersion.active.is_(True))
                ):
                    session.add(
                        ProfileVersion(
                            id=profile_id,
                            content_hash=suffix,
                            resume_text="Python backend engineer",
                            active=True,
                        )
                    )
                session.add(
                    ScrapeRun(
                        id=run_id,
                        group_id=group_id,
                        status="REVIEW_READY",
                        config_version="scraper-race-test",
                        config_hash=suffix,
                        selected_count=1,
                    )
                )
                await session.flush()
                source_url = f"https://jobs.example.invalid/{suffix}"
                session.add(
                    ScrapeCandidate(
                        run_id=run_id,
                        source_key="test",
                        source_provider="test",
                        source_url=source_url,
                        canonical_url=source_url,
                        company_name="Example Labs",
                        role_title="Backend Engineer",
                        schema_valid=True,
                        source_quality_valid=True,
                        selected=True,
                        review_group="RECOMMENDED",
                        payload={**scraper_job(), "applyUrl": source_url},
                    )
                )
                await session.commit()
                cookie = create_session_token(owner)

            transport = httpx.ASGITransport(app=app)
            path = f"/api/scraper/runs/{run_id}"
            worker_path = "/api/scraper/internal/import-tick"
            async with (
                httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                    cookies={settings.session_cookie_name: cookie},
                ) as browser,
                httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                    headers={"X-JEDI-SERVICE-TOKEN": settings.ml_service_secret},
                ) as worker,
            ):
                queued = await browser.post(f"{path}/queue-import", json={})
                assert queued.status_code == 202, queued.text
                async with asyncio.TaskGroup() as tasks:
                    worker_claim = tasks.create_task(worker.post(worker_path))
                    await asyncio.wait_for(ingest_started.wait(), timeout=5)
                    browser_retry = await asyncio.wait_for(
                        browser.post(f"{path}/advance-import"), timeout=5
                    )
                    assert browser_retry.status_code == 200, browser_retry.text
                    assert browser_retry.json()["status"] == "IMPORTING"
                    assert browser_retry.json()["importedBatchId"] is None
                    finish_ingest.set()
                linked = worker_claim.result()
                assert linked.status_code == 200, linked.text
                assert linked.json()["status"] == "NORMALIZING"
                batch_id = linked.json()["importedBatchId"]
                assert batch_id

                async with asyncio.TaskGroup() as tasks:
                    browser_claim = tasks.create_task(
                        browser.post(f"{path}/advance-import")
                    )
                    await asyncio.wait_for(normalize_started.wait(), timeout=5)
                    worker_retry = await asyncio.wait_for(
                        worker.post(worker_path), timeout=5
                    )
                    assert worker_retry.status_code == 200, worker_retry.text
                    assert worker_retry.json() is None
                    finish_normalization.set()
                done = browser_claim.result()
                assert done.status_code == 200, done.text
                assert done.json()["status"] == "IMPORTED", done.text
                assert done.json()["importedBatchId"] == batch_id
                assert (await worker.post(worker_path)).json() is None
                batch = await browser.get(f"/api/batches/{batch_id}")
                assert batch.status_code == 200, batch.text
                assert batch.json()["preparedCount"] == 1
                assert batch.json()["batch"]["rankedAt"] is None

            assert (ingest_calls, normalization_calls) == (1, 1)
            async with sessions() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(Batch)
                        .where(Batch.external_batch_id == batch_key)
                    )
                    == 1
                )
        finally:
            async with sessions() as session:
                await session.execute(delete(Group).where(Group.id == group_id))
                await session.execute(delete(User).where(User.id == user_id))
                await session.execute(
                    delete(Batch).where(Batch.external_batch_id == batch_key)
                )
                await session.execute(
                    delete(ProfileVersion).where(ProfileVersion.id == profile_id)
                )
                await session.commit()
            await engine.dispose()

    asyncio.run(verify())
