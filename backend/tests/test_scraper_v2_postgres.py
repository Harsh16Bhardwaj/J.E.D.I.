import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config import get_settings
from backend.database import (
    Group,
    ScrapeAttempt,
    ScrapeCandidate,
    ScrapeProviderUse,
    ScrapeRun,
    ScrapeSource,
    SourceDiscoveryAttempt,
    SourceDiscoveryRun,
)


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
