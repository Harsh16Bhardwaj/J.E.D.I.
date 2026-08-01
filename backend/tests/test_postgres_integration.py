import asyncio
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config import get_settings
from backend.database import (
    Application,
    ApplicationMilestone,
    Batch,
    EmailCampaign,
    EmailCampaignRun,
    EmailConfiguration,
    EmailDelivery,
    EmailRecipient,
    Group,
    GroupMember,
    Job,
    JobAnnotation,
    JobEvent,
    JobState,
    ModelDeployment,
    ModelEndpointCheck,
    ModelVersion,
    ProcessingRun,
    User,
)


def test_prisma_and_sqlalchemy_contract_on_neon() -> None:
    direct_url = get_settings().direct_database_url
    if not direct_url or "USER:PASSWORD@HOST" in direct_url:
        pytest.skip("DIRECT_DATABASE_URL is not configured for PostgreSQL testing.")

    async def verify() -> None:
        sqlalchemy_url = direct_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )
        database_engine = create_async_engine(sqlalchemy_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(database_engine, expire_on_commit=False)
        suffix = uuid4().hex
        async with session_factory() as session:
            transaction = await session.begin()
            try:
                batch = Batch(
                    id=f"test-batch-{suffix}",
                    external_batch_id=f"integration-{suffix}",
                    content_hash=f"content-{suffix}",
                    schema_version="integration-v1",
                    generated_at=datetime.now(UTC),
                    raw_envelope={"source": "integration", "jobs": 1},
                    status="READY",
                )
                job = Job(
                    id=f"test-job-{suffix}",
                    code=f"TEST-{suffix}",
                    dedupe_key=f"dedupe-{suffix}",
                    company_key="integration-company",
                    batch_id=batch.id,
                    company_name="Integration Company",
                    role_title="Backend Engineer",
                    description="Validate PostgreSQL-specific mappings.",
                    skills=["Python", "PostgreSQL"],
                    apply_url=f"https://example.invalid/jobs/{suffix}",
                )
                session.add_all([batch, job])
                await session.flush()

                loaded = await session.scalar(
                    select(Job)
                    .join(Batch, Job.batch_id == Batch.id)
                    .where(Batch.raw_envelope["source"].astext == "integration")
                )
                assert loaded is not None
                assert loaded.skills == ["Python", "PostgreSQL"]
                assert loaded.batch_id == batch.id
                assert batch.status == "READY"

                migration_count = await session.scalar(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM "_prisma_migrations"
                        WHERE migration_name = '20260729000000_initial'
                          AND finished_at IS NOT NULL
                        """
                    )
                )
                assert migration_count == 1

                session.add(
                    Batch(
                        id=f"duplicate-batch-{suffix}",
                        external_batch_id=f"other-{suffix}",
                        content_hash=batch.content_hash,
                        schema_version="integration-v1",
                        generated_at=batch.generated_at,
                        raw_envelope={},
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.flush()
            finally:
                await transaction.rollback()
                await database_engine.dispose()

    asyncio.run(verify())


def test_newsletter_and_model_deployment_contract_on_neon() -> None:
    direct_url = get_settings().direct_database_url
    if not direct_url or "USER:PASSWORD@HOST" in direct_url:
        pytest.skip("DIRECT_DATABASE_URL is not configured for PostgreSQL testing.")

    async def verify() -> None:
        sqlalchemy_url = direct_url.replace("postgresql://", "postgresql+psycopg://", 1)
        database_engine = create_async_engine(sqlalchemy_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(database_engine, expire_on_commit=False)
        suffix = uuid4().hex
        async with session_factory() as session:
            transaction = await session.begin()
            try:
                configuration = await session.get(EmailConfiguration, "default")
                assert configuration is not None
                assert configuration.sender_name == "JEDI Daily Dispatch"

                batch = Batch(
                    id=f"campaign-batch-{suffix}",
                    external_batch_id=f"campaign-{suffix}",
                    content_hash=f"campaign-content-{suffix}",
                    schema_version="integration-v1",
                    generated_at=datetime.now(UTC),
                    raw_envelope={"test": "newsletter-model-contract"},
                    status="RANKED",
                )
                model = ModelVersion(
                    id=f"campaign-model-{suffix}",
                    name=f"campaign-model-{suffix}",
                    content_hash=f"campaign-model-hash-{suffix}",
                    description="Structured registry integration test",
                    model_family="stacked-ranking-model",
                    artifact_manifest={"bundle": "test.joblib"},
                    feature_schema_version="prepared-job-v1",
                    request_contract_version="jedi-ranking-v1",
                    tags=["top-25", "integration"],
                    training_metadata={"datasetVersion": "test-v1"},
                    evaluation_metadata={"splitStrategy": "grouped-k-fold"},
                )
                run = ProcessingRun(
                    id=f"campaign-run-{suffix}",
                    batch_id=batch.id,
                    idempotency_key=f"campaign-run-key-{suffix}",
                    status="SUCCEEDED",
                    stage="campaign-integration",
                )
                deployment = ModelDeployment(
                    id=f"campaign-deployment-{suffix}",
                    model_version_id=model.id,
                    endpoint_url="https://model.example.invalid/v1/rank",
                    health_url="https://model.example.invalid/health/ready",
                    timeout_seconds=120,
                )
                check = ModelEndpointCheck(
                    id=f"campaign-check-{suffix}",
                    model_version_id=model.id,
                    deployment_id=deployment.id,
                    status="READY",
                    latency_ms=42,
                    http_status=200,
                    health_url_snapshot=deployment.health_url,
                    returned_feature_schema_version="prepared-job-v1",
                    returned_request_contract_version="jedi-ranking-v1",
                )
                recipient = EmailRecipient(
                    id=f"campaign-recipient-{suffix}",
                    email="Person@Example.com",
                    email_normalized=f"person-{suffix}@example.com",
                    display_name="Person",
                )
                campaign = EmailCampaign(
                    id=f"campaign-{suffix}",
                    campaign_date=date(2026, 8, 1),
                    status="PENDING",
                    scheduled_at=datetime.now(UTC),
                    payload_snapshot={"jobs": [{"rank": 1}]},
                    selected_job_count=1,
                    recipient_count=1,
                )
                campaign_run = EmailCampaignRun(
                    campaign_id=campaign.id,
                    processing_run_id=run.id,
                )
                delivery = EmailDelivery(
                    id=f"campaign-delivery-{suffix}",
                    campaign_id=campaign.id,
                    recipient_id=recipient.id,
                    recipient=recipient.email,
                    recipient_display_name=recipient.display_name,
                    template_version="daily-top-10-v1",
                    message_id=f"<{suffix}@jedi.local>",
                    payload_snapshot={"subject": "JEDI Daily Dispatch"},
                )
                # These mappings intentionally do not define ORM relationships;
                # production services use ids directly. Flush parent rows before
                # their foreign-key children so the test mirrors that service flow.
                session.add_all([batch, model, recipient, campaign])
                await session.flush()
                session.add_all([run, deployment])
                await session.flush()
                session.add_all([check, campaign_run, delivery])
                await session.flush()

                loaded = await session.scalar(
                    select(EmailDelivery).where(
                        EmailDelivery.campaign_id == campaign.id
                    )
                )
                assert loaded is not None
                assert loaded.batch_id is None
                assert model.tags == ["top-25", "integration"]
                assert campaign.payload_snapshot == {"jobs": [{"rank": 1}]}

                migration_count = await session.scalar(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM "_prisma_migrations"
                        WHERE migration_name =
                          '20260731000000_newsletter_model_deployments'
                          AND finished_at IS NOT NULL
                        """
                    )
                )
                assert migration_count == 1
            finally:
                await transaction.rollback()
                await database_engine.dispose()

    asyncio.run(verify())


def test_member_activity_isolated_by_postgres_constraints() -> None:
    """The same shared job can hold independent private rows for two members."""
    direct_url = get_settings().direct_database_url
    if not direct_url or "USER:PASSWORD@HOST" in direct_url:
        pytest.skip("DIRECT_DATABASE_URL is not configured for PostgreSQL testing.")

    async def verify() -> None:
        sqlalchemy_url = direct_url.replace("postgresql://", "postgresql+psycopg://", 1)
        database_engine = create_async_engine(sqlalchemy_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(database_engine, expire_on_commit=False)
        suffix = uuid4().hex
        async with session_factory() as session:
            transaction = await session.begin()
            try:
                owner = User(
                    id=f"private-owner-{suffix}",
                    email=f"owner-{suffix}@example.invalid",
                    password_hash="test-only-hash",
                )
                friend = User(
                    id=f"private-friend-{suffix}",
                    email=f"friend-{suffix}@example.invalid",
                    password_hash="test-only-hash",
                )
                session.add_all([owner, friend])
                await session.flush()
                group = Group(
                    id=f"private-group-{suffix}",
                    name="Private activity integration",
                    owner_id=owner.id,
                )
                session.add(group)
                await session.flush()
                owner_member = GroupMember(
                    id=f"private-owner-member-{suffix}",
                    group_id=group.id,
                    user_id=owner.id,
                )
                friend_member = GroupMember(
                    id=f"private-friend-member-{suffix}",
                    group_id=group.id,
                    user_id=friend.id,
                )
                batch = Batch(
                    id=f"private-batch-{suffix}",
                    external_batch_id=f"private-{suffix}",
                    content_hash=f"private-content-{suffix}",
                    schema_version="integration-v1",
                    generated_at=datetime.now(UTC),
                    raw_envelope={"test": "member-private-activity"},
                    status="READY",
                )
                session.add_all([owner_member, friend_member, batch])
                await session.flush()
                job = Job(
                    id=f"private-job-{suffix}",
                    code=f"PRIVATE-{suffix}",
                    dedupe_key=f"private-dedupe-{suffix}",
                    company_key="private-company",
                    batch_id=batch.id,
                    company_name="Private Company",
                    role_title="Backend Engineer",
                    description="One shared job with two private user workflows.",
                    apply_url=f"https://example.invalid/private/{suffix}",
                )
                session.add(job)
                await session.flush()

                owner_application = Application(
                    id=f"private-owner-application-{suffix}",
                    group_member_id=owner_member.id,
                    job_id=job.id,
                    status="APPLIED",
                )
                friend_application = Application(
                    id=f"private-friend-application-{suffix}",
                    group_member_id=friend_member.id,
                    job_id=job.id,
                    status="PREPARING",
                )
                session.add_all(
                    [
                        JobState(
                            group_member_id=owner_member.id,
                            job_id=job.id,
                            review_status="VIEWED",
                            viewed_at=datetime.now(UTC),
                        ),
                        JobState(
                            group_member_id=friend_member.id,
                            job_id=job.id,
                            review_status="SAVED",
                        ),
                        JobAnnotation(
                            group_member_id=owner_member.id,
                            job_id=job.id,
                            apply_label=True,
                        ),
                        JobAnnotation(
                            group_member_id=friend_member.id,
                            job_id=job.id,
                            apply_label=False,
                        ),
                        owner_application,
                        friend_application,
                    ]
                )
                await session.flush()
                session.add_all(
                    [
                        JobEvent(
                            application_id=owner_application.id,
                            event_type="APPLIED",
                            previous_status="NOT_STARTED",
                            new_status="APPLIED",
                        ),
                        ApplicationMilestone(
                            application_id=friend_application.id,
                            type="INTERVIEW",
                            title="Friend-only interview",
                        ),
                    ]
                )
                await session.flush()

                states = (
                    await session.scalars(
                        select(JobState).where(JobState.job_id == job.id)
                    )
                ).all()
                applications = (
                    await session.scalars(
                        select(Application).where(Application.job_id == job.id)
                    )
                ).all()
                assert {item.group_member_id for item in states} == {
                    owner_member.id,
                    friend_member.id,
                }
                assert {item.status for item in applications} == {
                    "APPLIED",
                    "PREPARING",
                }

                with pytest.raises(IntegrityError):
                    await session.execute(
                        insert(JobState).values(
                            groupMemberId=owner_member.id,
                            jobId=job.id,
                            reviewStatus="DISMISSED",
                            updatedAt=datetime.now(UTC),
                        )
                    )
            finally:
                await transaction.rollback()
                await database_engine.dispose()

    asyncio.run(verify())
