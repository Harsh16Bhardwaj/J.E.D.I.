import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from backend.config import get_settings
from backend.database import Batch, Job, MemberProfile, RecommendationBatch, utc_now
from backend.routers import recommendations as routes
from backend.services.recommendations import build_pools, eligible, families, rank_job
from backend.tests.test_group_access import group_client, login_owner  # noqa: F401


def job(job_id="react", **overrides):
    values = dict(
        id=job_id,
        role_title="Frontend Engineer",
        company_name="Example",
        location="London",
        skills=["React.js"],
        posted_at=utc_now(),
        can_apply_now=True,
    )
    return Job(**(values | overrides))


def profile(**overrides):
    return MemberProfile(
        **(
            dict(
                preferred_titles=["Frontend Engineer"],
                preferred_skills=["ReactJS"],
                preferred_locations=[],
            )
            | overrides
        )
    )


def test_cohorts_are_deterministic_and_preserve_unknown_roles():
    assert families(["Front-end Engineer", "Backend Developer"]) == [
        "backend",
        "frontend",
    ]
    assert families(["Nurse", "React Developer"]) == ["frontend", "general"]
    assert families(["Retail Manager"]) == ["general"]
    assert families(["MAIL coordinator"]) == ["general"]


def test_alias_skills_and_personal_ordering():
    frontend = job()
    backend = job("python", role_title="Backend Engineer", skills=["Python"])
    alice = profile()
    bob = profile(preferred_titles=["Backend Engineer"], preferred_skills=["Python"])
    assert rank_job(frontend, alice)["score"] == 100
    assert rank_job(backend, alice)["score"] == 0
    assert rank_job(backend, bob)["score"] == 100


def test_unknown_evidence_never_earns_full_points():
    result = rank_job(
        job(skills=[], experience_min_years=None), profile(experience_max_years=2)
    )
    assert result["score"] < 100
    assert result["unknowns"] == ["Skills not listed", "Experience not listed"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"posted_at": None},
        {"posted_at": utc_now() - timedelta(days=31)},
        {"posted_at": utc_now() + timedelta(days=1)},
        {"can_apply_now": False},
        {"application_deadline": utc_now() - timedelta(minutes=1)},
    ],
)
def test_expired_closed_undated_future_jobs_are_excluded(overrides):
    assert not eligible(job(**overrides), utc_now())


def test_pools_are_repeatable_and_contain_only_job_ids():
    now = utc_now()
    jobs = [job("b", posted_at=now), job("a", posted_at=now)]
    assert build_pools(jobs) == build_pools(list(reversed(jobs)))
    assert build_pools(jobs)["frontend"] == ["a", "b"]


def test_personal_preferences_cannot_read_or_overwrite_other_members(group_client):  # noqa: F811
    from backend.auth import get_current_user
    from backend.database import GroupMember, User
    from backend.main import app

    client, factory = group_client
    login_owner(client)
    client.put("/api/preferences", json={"preferredTitles": ["Owner private role"]})
    other = User(id="other-user", email="other@example.test", password_hash="unused")

    async def seed():
        async with factory() as session:
            session.add(other)
            await session.flush()
            session.add(
                GroupMember(id="other-member", user_id=other.id, group_id="group-1")
            )
            await session.commit()

    asyncio.run(seed())
    app.dependency_overrides[get_current_user] = lambda: other
    assert client.get("/api/preferences").json()["preferredTitles"] == []
    client.put("/api/preferences", json={"preferredTitles": ["Designer"]})
    assert client.get("/api/preferences").json()["preferredTitles"] == ["Designer"]
    del app.dependency_overrides[get_current_user]
    assert client.get("/api/preferences").json()["preferredTitles"] == [
        "Owner private role"
    ]


def test_private_preferences_and_unconfigured_feed(group_client):  # noqa: F811
    client, factory = group_client
    assert client.get("/api/preferences").status_code == 401
    assert client.get("/api/recommendations").status_code == 401
    login_owner(client)
    assert client.get("/api/recommendations").json()["status"] == "NEEDS_PREFERENCES"
    assert (
        client.put("/api/preferences", json={"preferredTitles": ["   "]}).status_code
        == 422
    )
    assert (
        client.put(
            "/api/preferences",
            json={
                "preferredTitles": ["Frontend Engineer"],
                "preferredSkills": ["React"],
            },
        ).status_code
        == 200
    )
    assert client.get("/api/recommendations").json()["status"] == "WAITING_FOR_BATCH"
    assert "resumeText" not in client.get("/api/preferences").json()

    async def check():
        async with factory() as session:
            saved = await session.scalar(select(MemberProfile))
            assert saved.group_member_id == "member-owner"
            saved.resume_text = "PRIVATE ORIGINAL RESUME"
            await session.commit()

    asyncio.run(check())
    client.put(
        "/api/preferences",
        json={"preferredTitles": ["Data Engineer"], "resumeText": "overwrite attempt"},
    )

    async def verify():
        async with factory() as session:
            assert (
                await session.scalar(select(MemberProfile))
            ).resume_text == "PRIVATE ORIGINAL RESUME"

    asyncio.run(verify())


def test_daily_batch_replay_and_latest_complete_fallback(group_client, monkeypatch):  # noqa: F811
    client, factory = group_client
    monkeypatch.setattr(get_settings(), "cron_secret", "test-cron")
    assert client.get("/internal/recommendations/run").status_code == 401
    headers = {"Authorization": "Bearer test-cron"}
    now = utc_now()

    async def seed():
        async with factory() as session:
            session.add(
                Batch(
                    id="batch",
                    external_batch_id="daily",
                    content_hash="test-hash",
                    schema_version="1",
                    generated_at=now,
                    received_count=1,
                    job_count=1,
                    duplicate_count=0,
                    raw_envelope={},
                )
            )
            await session.flush()
            session.add(
                job(
                    batch_id="batch",
                    code="JOB-1",
                    dedupe_key="daily",
                    company_key="example",
                    description="React engineer",
                    apply_url="https://example.com/jobs/1",
                )
            )
            await session.commit()

    asyncio.run(seed())
    assert (
        client.get("/internal/recommendations/run", headers=headers).json()["replayed"]
        is False
    )
    assert (
        client.get("/internal/recommendations/run", headers=headers).json()["replayed"]
        is True
    )
    login_owner(client)
    client.put(
        "/api/preferences",
        json={"preferredTitles": ["Frontend Engineer"], "preferredSkills": ["ReactJS"]},
    )
    feed = client.get("/api/recommendations")
    assert "no-store" in feed.headers["cache-control"]
    assert feed.json()["status"] == "READY"
    assert feed.json()["jobs"][0]["score"] == 100

    async def age():
        async with factory() as session:
            batch = await session.scalar(select(RecommendationBatch))
            batch.completed_at = now - timedelta(hours=40)
            # Keep this generation while the next daily retry fails.
            batch.id = "cohort-v1/previous"
            await session.commit()

    asyncio.run(age())

    async def fail(*args):
        raise TimeoutError()

    monkeypatch.setattr(routes, "collect_pools", fail)
    assert (
        client.get("/internal/recommendations/run", headers=headers).status_code == 503
    )
    feed = client.get("/api/recommendations").json()
    assert feed["status"] == "STALE"
    assert feed["jobs"][0]["id"] == "react"
    assert feed["latestAttempt"]["errorCode"] == "TIMEOUT"


def test_postgres_daily_batch_serializes_workers(monkeypatch):
    import os
    from uuid import uuid4

    from fastapi import Response
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    url = os.getenv("JEDI_TEST_SCRAPER_DATABASE_URL")
    if not url:
        pytest.skip("Dedicated PostgreSQL test database required.")
    version = f"qa-{uuid4().hex}"
    monkeypatch.setattr(routes, "VERSION", version)
    monkeypatch.setattr(get_settings(), "cron_secret", "test-cron")

    async def verify():
        engine = create_async_engine(
            url.replace("postgresql://", "postgresql+psycopg://")
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        started, release = asyncio.Event(), asyncio.Event()

        async def collect(*args):
            started.set()
            await release.wait()
            return {"general": []}, 0, False

        monkeypatch.setattr(routes, "collect_pools", collect)

        async def run():
            async with sessions() as session:
                return await routes.run_daily(session, Response(), "Bearer test-cron")

        try:
            first = asyncio.create_task(run())
            await asyncio.wait_for(started.wait(), 10)
            try:
                assert (await run())["status"] == "BUSY"
            finally:
                release.set()
            assert (await first)["replayed"] is False
            assert (await run())["replayed"] is True
        finally:
            release.set()
            async with sessions() as session:
                await session.execute(
                    delete(RecommendationBatch).where(
                        RecommendationBatch.id.startswith(version)
                    )
                )
                await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_postgres_app_transactions_keep_naive_timestamps_in_utc():
    import os

    from sqlalchemy import event, text
    from sqlalchemy.ext.asyncio import create_async_engine

    from backend.database import use_utc_transaction

    url = os.getenv("JEDI_TEST_SCRAPER_DATABASE_URL")
    if not url:
        pytest.skip("Dedicated PostgreSQL test database required.")

    async def verify():
        engine = create_async_engine(
            url.replace("postgresql://", "postgresql+psycopg://"),
            connect_args={"options": "-c timezone=Asia/Kolkata"},
        )
        event.listen(engine.sync_engine, "begin", use_utc_transaction)
        try:
            async with engine.connect() as connection:
                for _ in range(2):
                    assert await connection.scalar(text("SHOW TIME ZONE")) == "UTC"
                    now = utc_now()
                    value = await connection.scalar(
                        text("SELECT CAST(CAST(:now AS timestamptz) AS timestamp)"),
                        {"now": now},
                    )
                    assert value == now.replace(tzinfo=None)
                    await connection.commit()
        finally:
            await engine.dispose()

    asyncio.run(verify())
