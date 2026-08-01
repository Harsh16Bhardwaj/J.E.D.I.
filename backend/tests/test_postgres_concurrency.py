import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config import get_settings
from backend.database import (
    Batch,
    EmailDelivery,
    EmailRecipient,
    Job,
    JobPrediction,
    ModelVersion,
    PreparedJob,
    ProcessingRun,
    ProfileVersion,
)
from backend.routers.email import create_email_recipient
from backend.routers.models import activate_model
from backend.routers.operations import claim_processing_run
from backend.routers.workflow import queue_ranking
from backend.routers.workspace import activate_profile
from backend.schemas.email_management import EmailRecipientCreate
from backend.services.email import send_oldest_due


class BlockingEmailTransport:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def send(self, delivery: EmailDelivery) -> str:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return delivery.message_id


def test_postgres_concurrency_invariants() -> None:
    direct_url = get_settings().direct_database_url
    if not direct_url or "USER:PASSWORD@HOST" in direct_url:
        pytest.skip("DIRECT_DATABASE_URL is not configured for PostgreSQL testing.")

    async def verify() -> None:
        suffix = uuid4().hex
        profile_ids = [f"concurrency-profile-{suffix}-{index}" for index in range(2)]
        model_ids = [f"concurrency-model-{suffix}-{index}" for index in range(2)]
        batch_id = f"concurrency-batch-{suffix}"
        job_id = f"concurrency-job-{suffix}"
        sqlalchemy_url = direct_url.replace("postgresql://", "postgresql+psycopg://", 1)
        database_engine = create_async_engine(
            sqlalchemy_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=0,
        )
        session_factory = async_sessionmaker(database_engine, expire_on_commit=False)
        old_profile_ids: list[str] = []
        old_model_ids: list[str] = []

        try:
            async with session_factory() as session:
                old_profile_ids = list(
                    (
                        await session.scalars(
                            select(ProfileVersion.id).where(
                                ProfileVersion.active.is_(True)
                            )
                        )
                    ).all()
                )
                old_model_ids = list(
                    (
                        await session.scalars(
                            select(ModelVersion.id).where(ModelVersion.active.is_(True))
                        )
                    ).all()
                )
                session.add_all(
                    [
                        ProfileVersion(
                            id=profile_id,
                            content_hash=f"{profile_id}-hash",
                            resume_text="Concurrency test profile",
                            preferred_titles=[],
                            preferred_locations=[],
                            preferred_skills=[],
                            active=False,
                        )
                        for profile_id in profile_ids
                    ]
                    + [
                        ModelVersion(
                            id=model_id,
                            name=model_id,
                            content_hash=f"{model_id}-hash",
                            artifact_manifest={"test": True},
                            feature_schema_version="prepared-job-v1",
                            active=False,
                        )
                        for model_id in model_ids
                    ]
                )
                await session.commit()

            async def activate_profile_once(profile_id: str) -> None:
                async with session_factory() as session:
                    await activate_profile(profile_id, None, session)

            await asyncio.gather(
                *(activate_profile_once(profile_id) for profile_id in profile_ids)
            )
            async with session_factory() as session:
                active_profiles = list(
                    (
                        await session.scalars(
                            select(ProfileVersion).where(
                                ProfileVersion.active.is_(True)
                            )
                        )
                    ).all()
                )
                assert len(active_profiles) == 1
                active_profile_id = active_profiles[0].id

            async def activate_model_once(model_id: str) -> None:
                async with session_factory() as session:
                    await activate_model(model_id, None, session)

            await asyncio.gather(
                *(activate_model_once(model_id) for model_id in model_ids)
            )
            async with session_factory() as session:
                active_models = list(
                    (
                        await session.scalars(
                            select(ModelVersion).where(ModelVersion.active.is_(True))
                        )
                    ).all()
                )
                assert len(active_models) == 1
                active_model_id = active_models[0].id
                session.add(
                    Batch(
                        id=batch_id,
                        external_batch_id=batch_id,
                        content_hash=f"{batch_id}-hash",
                        schema_version="integration-v1",
                        generated_at=datetime.now(UTC),
                        raw_envelope={"test": "concurrency"},
                        status="NORMALIZED",
                        received_count=1,
                        valid_count=1,
                        job_count=1,
                    )
                )
                session.add(
                    Job(
                        id=job_id,
                        code=f"CONCURRENCY-{suffix}",
                        dedupe_key=f"concurrency-dedupe-{suffix}",
                        company_key="concurrency",
                        batch_id=batch_id,
                        company_name="Concurrency Inc",
                        role_title="Backend Engineer",
                        description="Exercise PostgreSQL row locks.",
                        skills=["Python"],
                        apply_url="https://example.invalid/concurrency",
                    )
                )
                session.add(
                    PreparedJob(
                        feature_schema_version="prepared-job-v1",
                        payload_hash=f"payload-{suffix}",
                        payload={"company_name": "Concurrency Inc"},
                        job_id=job_id,
                        profile_version_id=active_profile_id,
                    )
                )
                await session.commit()

            async def queue_once():
                async with session_factory() as session:
                    return await queue_ranking(batch_id, None, session)

            queued = await asyncio.gather(queue_once(), queue_once())
            assert queued[0].processing_run_id == queued[1].processing_run_id
            run_id = queued[0].processing_run_id

            async def claim_once():
                async with session_factory() as session:
                    return await claim_processing_run(None, session)

            claims = await asyncio.gather(claim_once(), claim_once())
            successful_claims = [
                claim for claim in claims if not isinstance(claim, Response)
            ]
            empty_claims = [
                claim
                for claim in claims
                if isinstance(claim, Response) and claim.status_code == 204
            ]
            assert len(successful_claims) == 1
            assert len(empty_claims) == 1

            async with session_factory() as session:
                run = await session.get(ProcessingRun, run_id)
                batch = await session.get(Batch, batch_id)
                assert run is not None and batch is not None
                run.status = "SUCCEEDED"
                run.completed_at = datetime.now(UTC)
                run.lease_token = None
                run.lease_expires_at = None
                batch.status = "RANKED"
                batch.ranked_at = datetime.now(UTC)
                session.add(
                    JobPrediction(
                        rank=1,
                        jedi_preference_score=95,
                        apply_preference_probability=0.95,
                        component_scores={"skills": 5},
                        job_id=job_id,
                        batch_id=batch_id,
                        profile_version_id=active_profile_id,
                        model_version_id=active_model_id,
                        processing_run_id=run_id,
                    )
                )
                session.add(
                    EmailDelivery(
                        batch_id=batch_id,
                        recipient="concurrency@example.invalid",
                        ranking_run_id=run_id,
                        template_version="top-ten-v1",
                        message_id=f"<{suffix}@jedi.local>",
                        status="PENDING",
                        payload_snapshot={
                            "subject": "Concurrency",
                            "textBody": "Test",
                            "htmlBody": "<p>Test</p>",
                            "jobs": [job_id],
                        },
                    )
                )
                await session.commit()

            transport = BlockingEmailTransport()

            async def send_once():
                async with session_factory() as session:
                    return await send_oldest_due(session, transport)

            first_sender = asyncio.create_task(send_once())
            await asyncio.wait_for(transport.started.wait(), timeout=10)
            second_result = await send_once()
            transport.release.set()
            first_result = await first_sender
            assert transport.calls == 1
            assert second_result is None
            assert first_result is not None
            assert first_result.status == "SENT"
        finally:
            async with session_factory() as session:
                await session.execute(
                    delete(EmailDelivery).where(EmailDelivery.batch_id == batch_id)
                )
                await session.execute(
                    delete(JobPrediction).where(JobPrediction.batch_id == batch_id)
                )
                await session.execute(
                    delete(ProcessingRun).where(ProcessingRun.batch_id == batch_id)
                )
                await session.execute(
                    delete(PreparedJob).where(PreparedJob.job_id == job_id)
                )
                await session.execute(delete(Job).where(Job.id == job_id))
                await session.execute(delete(Batch).where(Batch.id == batch_id))
                await session.execute(
                    delete(ModelVersion).where(ModelVersion.id.in_(model_ids))
                )
                await session.execute(
                    delete(ProfileVersion).where(ProfileVersion.id.in_(profile_ids))
                )
                if old_profile_ids:
                    await session.execute(
                        update(ProfileVersion)
                        .where(ProfileVersion.id.in_(old_profile_ids))
                        .values(active=True)
                    )
                if old_model_ids:
                    await session.execute(
                        update(ModelVersion)
                        .where(ModelVersion.id.in_(old_model_ids))
                        .values(active=True)
                    )
                await session.commit()
            await database_engine.dispose()

    asyncio.run(verify())


def test_recipient_limit_is_serialized_on_postgres() -> None:
    direct_url = get_settings().direct_database_url
    if not direct_url or "USER:PASSWORD@HOST" in direct_url:
        pytest.skip("DIRECT_DATABASE_URL is not configured for PostgreSQL testing.")

    async def verify() -> None:
        suffix = uuid4().hex
        prefix = f"limit-{suffix}-"
        sqlalchemy_url = direct_url.replace("postgresql://", "postgresql+psycopg://", 1)
        database_engine = create_async_engine(sqlalchemy_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(database_engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                existing = await session.scalar(
                    select(func.count())
                    .select_from(EmailRecipient)
                    .where(
                        EmailRecipient.active.is_(True),
                        EmailRecipient.deleted_at.is_(None),
                    )
                )
                if existing:
                    pytest.skip(
                        "Recipient concurrency test requires an empty private list."
                    )
                session.add_all(
                    EmailRecipient(
                        email=f"{prefix}{index}@example.invalid",
                        email_normalized=f"{prefix}{index}@example.invalid",
                    )
                    for index in range(49)
                )
                await session.commit()

            async def add_last(index: int):
                async with session_factory() as session:
                    return await create_email_recipient(
                        EmailRecipientCreate(
                            email=f"{prefix}candidate-{index}@example.invalid"
                        ),
                        Response(),
                        None,
                        session,
                    )

            results = await asyncio.gather(
                add_last(1), add_last(2), return_exceptions=True
            )
            assert sum(not isinstance(item, Exception) for item in results) == 1
            conflict = next(item for item in results if isinstance(item, HTTPException))
            assert conflict.status_code == 409
        finally:
            async with session_factory() as session:
                await session.execute(
                    delete(EmailRecipient).where(
                        EmailRecipient.email.like(f"{prefix}%")
                    )
                )
                await session.commit()
            await database_engine.dispose()

    asyncio.run(verify())
