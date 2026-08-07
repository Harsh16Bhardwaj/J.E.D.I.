import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.database import (
    Base,
    EmailDelivery,
    Job,
    JobPrediction,
    MemberProfile,
)
from backend.services.email import normalized_smtp_app_password
from backend.services.mail_events import (
    BatchCandidateCache,
    RankedCandidate,
    claim_mail_events,
    next_delivery_window,
    personalize_candidates,
    run_mail_event_worker,
)


class SelectiveTransport:
    def __init__(self, failing: set[str] | None = None) -> None:
        self.failing = failing or set()
        self.payloads: dict[str, dict] = {}

    async def send(self, delivery: EmailDelivery) -> str:
        assert delivery.payload_snapshot is not None
        self.payloads[delivery.recipient] = delivery.payload_snapshot
        if delivery.recipient in self.failing:
            raise RuntimeError("provider detail must remain private")
        return delivery.message_id


def candidate(index: int, *, title: str = "Backend Engineer") -> RankedCandidate:
    return RankedCandidate(
        job_id=f"job-{index:02d}",
        base_rank=index,
        base_score=max(1, 100 - index),
        company="Example",
        title=title,
        location="Remote",
        work_mode="remote",
        skills=("Python", "FastAPI"),
        experience_min_years=1,
        experience_max_years=3,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        can_apply_now=True,
        apply_url=f"https://example.test/{index}",
    )


def test_personalization_formula_top_ten_and_four_entry_lru() -> None:
    assert normalized_smtp_app_password("abcd efgh ijkl mnop") == "abcdefghijklmnop"
    profile = SimpleNamespace(
        preferred_titles=["Backend Engineer"],
        preferred_locations=["Remote"],
        preferred_skills=["Python", "FastAPI"],
        experience_min_years=0,
        experience_max_years=3,
        salary_min=None,
        salary_max=None,
        salary_currency="INR",
    )
    candidates = tuple(candidate(index) for index in range(1, 26))
    personalized = personalize_candidates(profile, candidates)
    assert len(personalized) == 10
    assert personalized[0]["jobId"] == "job-01"
    assert personalized[0]["personalizedScore"] == 97.9
    assert all(item["jobId"] != "job-26" for item in personalized)

    async def exercise_cache() -> None:
        cache = BatchCandidateCache(capacity=4)
        loads = 0

        async def loader() -> tuple[RankedCandidate, ...]:
            nonlocal loads
            loads += 1
            return (candidate(loads),)

        for index in range(4):
            await cache.get((f"batch-{index}", "run"), loader)
        await cache.get(("batch-0", "run"), loader)
        await cache.get(("batch-4", "run"), loader)
        await cache.get(("batch-1", "run"), loader)
        assert cache.hits == 1
        assert cache.misses == 6
        assert loads == 6

    asyncio.run(exercise_cache())


def test_claims_failed_before_untouched_and_sets_leases() -> None:
    async def verify() -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        now = datetime(2026, 8, 1, 18, 30, tzinfo=UTC)
        async with factory() as session:
            session.add_all(
                [
                    EmailDelivery(
                        id="untouched",
                        batch_id="batch",
                        ranking_run_id="run",
                        recipient_id="recipient-1",
                        group_member_id="member-1",
                        recipient="one@example.com",
                        template_version="personalized-top-ten-v1",
                        message_id="<one@jedi.local>",
                        status="UNTOUCHED",
                        next_attempt_at=now - timedelta(minutes=1),
                        created_at=now - timedelta(days=2),
                    ),
                    EmailDelivery(
                        id="failed",
                        batch_id="batch",
                        ranking_run_id="run",
                        recipient_id="recipient-2",
                        group_member_id="member-2",
                        recipient="two@example.com",
                        template_version="personalized-top-ten-v1",
                        message_id="<two@jedi.local>",
                        status="FAILED",
                        next_attempt_at=now - timedelta(minutes=1),
                        created_at=now - timedelta(days=1),
                    ),
                ]
            )
            await session.commit()
            claims = await claim_mail_events(session, now=now)
            assert [claim.event_id for claim in claims] == ["failed", "untouched"]
            rows = list(
                (
                    await session.scalars(
                        select(EmailDelivery).order_by(EmailDelivery.id)
                    )
                ).all()
            )
            assert all(item.status == "SENDING" for item in rows)
            assert all(item.attempts == 1 for item in rows)
            assert all(item.lease_token for item in rows)
        await engine.dispose()

    asyncio.run(verify())


def test_worker_personalizes_sends_retries_and_reuses_snapshot() -> None:
    async def verify() -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        now = datetime(2026, 8, 1, 18, 30, tzinfo=UTC)
        async with factory() as session:
            session.add_all(
                [
                    MemberProfile(
                        id="profile-a",
                        group_member_id="member-a",
                        content_hash="profile-a-v1",
                        resume_text="Python backend engineer",
                        preferred_titles=["Backend Engineer"],
                        preferred_locations=["Remote"],
                        preferred_skills=["Python", "FastAPI"],
                        experience_min_years=0,
                        experience_max_years=3,
                        salary_currency="INR",
                    ),
                    MemberProfile(
                        id="profile-b",
                        group_member_id="member-b",
                        content_hash="profile-b-v1",
                        resume_text="Frontend engineer",
                        preferred_titles=["Frontend Engineer"],
                        preferred_locations=["Bengaluru"],
                        preferred_skills=["React"],
                        experience_min_years=0,
                        experience_max_years=3,
                        salary_currency="INR",
                    ),
                ]
            )
            for index in range(1, 27):
                job = Job(
                    id=f"job-{index:02d}",
                    code=f"JOB-{index:02d}",
                    dedupe_key=f"dedupe-{index:02d}",
                    company_key="example",
                    batch_id="batch",
                    company_name="Example",
                    role_title=(
                        "Perfect Frontend Engineer"
                        if index == 26
                        else "Backend Engineer"
                    ),
                    description="Build reliable software.",
                    skills=["React"] if index == 26 else ["Python", "FastAPI"],
                    location="Bengaluru" if index == 26 else "Remote",
                    experience_min_years=1,
                    experience_max_years=3,
                    can_apply_now=True,
                    apply_url=f"https://example.test/{index}",
                )
                prediction = JobPrediction(
                    id=f"prediction-{index:02d}",
                    rank=index,
                    jedi_preference_score=max(1, 100 - index),
                    apply_preference_probability=0.9,
                    job_id=job.id,
                    batch_id="batch",
                    profile_version_id="shared-profile",
                    model_version_id="model",
                    processing_run_id="run",
                )
                session.add_all([job, prediction])
            session.add_all(
                [
                    EmailDelivery(
                        id="event-a",
                        batch_id="batch",
                        ranking_run_id="run",
                        recipient_id="recipient-a",
                        group_member_id="member-a",
                        recipient="a@example.com",
                        template_version="personalized-top-ten-v1",
                        message_id="<a@jedi.local>",
                        status="UNTOUCHED",
                        next_attempt_at=now,
                    ),
                    EmailDelivery(
                        id="event-b",
                        batch_id="batch",
                        ranking_run_id="run",
                        recipient_id="recipient-b",
                        group_member_id="member-b",
                        recipient="b@example.com",
                        template_version="personalized-top-ten-v1",
                        message_id="<b@jedi.local>",
                        status="FAILED",
                        next_attempt_at=now,
                    ),
                ]
            )
            await session.commit()

        transport = SelectiveTransport({"b@example.com"})
        result = await run_mail_event_worker(factory, transport, now=now)
        assert (result.claimed, result.sent, result.failed) == (2, 1, 1)
        assert (result.cache_hits, result.cache_misses) == (1, 1)
        rendered = transport.payloads["a@example.com"]
        assert rendered["htmlBody"].count("class='job-row'") == 10
        assert "Fit = your profile match" in rendered["htmlBody"]
        assert "1–3 yrs" in rendered["htmlBody"]
        assert "Salary not listed" in rendered["htmlBody"]
        assert "View all opportunities in JEDI" in rendered["htmlBody"]
        assert "Strongest signals" not in rendered["htmlBody"]
        assert "Profile-adjusted composite" not in rendered["htmlBody"]
        assert " / 100" not in rendered["htmlBody"]
        assert "http://localhost:3000/jobs/job-01" in rendered["htmlBody"]
        assert "https://example.test/1" not in rendered["htmlBody"]
        assert "Fit 97.9 · JEDI 99.0" in rendered["textBody"]
        async with factory() as session:
            sent = await session.get(EmailDelivery, "event-a")
            failed = await session.get(EmailDelivery, "event-b")
            assert sent and sent.status == "SENT"
            assert sent.template_version == "personalized-top-ten-v3"
            assert failed and failed.status == "FAILED"
            assert failed.error_code == "SMTP_DELIVERY_FAILED"
            assert failed.last_error == "Gmail SMTP delivery failed."
            assert failed.next_attempt_at is not None
            assert failed.next_attempt_at.replace(tzinfo=UTC) == datetime(
                2026, 8, 1, 21, 30, tzinfo=UTC
            )
            assert failed.payload_snapshot is not None
            original_snapshot = failed.payload_snapshot
            assert len(failed.personalized_jobs or []) == 10
            assert all(
                item["jobId"] != "job-26" for item in (failed.personalized_jobs or [])
            )
            profile = await session.get(MemberProfile, "profile-b")
            assert profile
            profile.preferred_titles = ["Completely Different"]
            failed.next_attempt_at = now
            await session.commit()

        retry = await run_mail_event_worker(
            factory,
            SelectiveTransport(),
            now=now + timedelta(minutes=1),
        )
        assert (retry.claimed, retry.sent, retry.failed) == (1, 1, 0)
        assert (retry.cache_hits, retry.cache_misses) == (0, 0)
        async with factory() as session:
            delivered = await session.get(EmailDelivery, "event-b")
            assert delivered and delivered.status == "SENT"
            assert delivered.payload_snapshot == original_snapshot
            assert delivered.profile_content_hash == "profile-b-v1"
        assert next_delivery_window(now) == datetime(2026, 8, 1, 21, 30, tzinfo=UTC)
        await engine.dispose()

    asyncio.run(verify())
