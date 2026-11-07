"""Member-owned preferences and an idempotent, daily server retrieval batch."""

import asyncio
from datetime import timedelta
from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from backend.auth import CurrentUser
from backend.config import get_settings
from backend.database import (
    Job,
    MemberProfile,
    RecommendationBatch,
    get_session,
    utc_now,
)
from backend.schemas.group_access import MemberProfileInput
from backend.services.group_access import (
    normalized_member_profile,
    require_group_context,
)
from backend.services.recommendations import (
    VERSION,
    aware,
    collect_pools,
    eligible,
    families,
    rank_job,
)

router = APIRouter(tags=["personal recommendations"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


def preference_response(profile: MemberProfile | None) -> dict:
    if profile is None:
        return {
            "preferredTitles": [],
            "preferredLocations": [],
            "preferredSkills": [],
            "experienceMinYears": None,
            "experienceMaxYears": None,
            "salaryMin": None,
            "salaryMax": None,
            "salaryCurrency": "INR",
        }
    return {
        "preferredTitles": profile.preferred_titles,
        "preferredLocations": profile.preferred_locations,
        "preferredSkills": profile.preferred_skills,
        "experienceMinYears": profile.experience_min_years,
        "experienceMaxYears": profile.experience_max_years,
        "salaryMin": profile.salary_min,
        "salaryMax": profile.salary_max,
        "salaryCurrency": profile.salary_currency,
    }


@router.get("/api/preferences")
async def get_preferences(
    user: CurrentUser, session: DatabaseSession, response: Response
) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    context = await require_group_context(session, user.id)
    profile = await session.scalar(
        select(MemberProfile).where(
            MemberProfile.group_member_id == context.membership.id
        )
    )
    return preference_response(profile)


@router.put("/api/preferences")
async def save_preferences(
    body: MemberProfileInput, user: CurrentUser, session: DatabaseSession
) -> dict:
    context = await require_group_context(session, user.id, lock=True)
    profile = await session.scalar(
        select(MemberProfile).where(
            MemberProfile.group_member_id == context.membership.id
        )
    )
    for values in (
        body.preferred_titles,
        body.preferred_locations,
        body.preferred_skills,
    ):
        if any(not value.strip() or len(value) > 120 for value in values):
            raise HTTPException(
                422, "Preferences must contain nonempty values of up to 120 characters."
            )
    # Preserve resume evidence and email preferences.
    body.resume_text = profile.resume_text if profile else None
    data = normalized_member_profile(body)
    if profile is None:
        profile = MemberProfile(group_member_id=context.membership.id, **data)
        session.add(profile)
    else:
        for key, value in data.items():
            setattr(profile, key, value)
    await session.commit()
    return preference_response(profile)


@router.get("/api/recommendations")
async def recommendations(
    user: CurrentUser, session: DatabaseSession, response: Response
) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    context = await require_group_context(session, user.id)
    profile = await session.scalar(
        select(MemberProfile).where(
            MemberProfile.group_member_id == context.membership.id
        )
    )
    base = {
        "jobs": [],
        "generatedAt": None,
        "cohorts": [],
        "catalogCount": 0,
        "candidateCount": 0,
        "truncated": False,
        "version": VERSION,
        "latestAttempt": None,
    }
    if profile is None or not (profile.preferred_titles or profile.preferred_skills):
        return {**base, "status": "NEEDS_PREFERENCES"}
    try:
        latest = await session.scalar(
            select(RecommendationBatch)
            .where(RecommendationBatch.id.startswith(VERSION + "/"))
            .order_by(RecommendationBatch.created_at.desc())
            .limit(1)
        )
    except ProgrammingError as exc:
        await session.rollback()
        raise HTTPException(
            503,
            detail={
                "code": "RECOMMENDATIONS_SETUP_REQUIRED",
                "message": (
                    "Personal feed setup is pending. "
                    "The server needs the daily recommendations migration."
                ),
            },
        ) from exc
    if latest:
        base["latestAttempt"] = {
            "status": latest.status,
            "at": latest.created_at,
            "errorCode": latest.error_code,
        }
    batch = await session.scalar(
        select(RecommendationBatch)
        .where(
            RecommendationBatch.status == "READY",
            RecommendationBatch.id.startswith(VERSION + "/"),
        )
        .order_by(RecommendationBatch.completed_at.desc())
        .limit(1)
    )
    if batch is None:
        return {**base, "status": "WAITING_FOR_BATCH"}
    cohorts = families(profile.preferred_titles)
    ids = sorted({job_id for key in cohorts for job_id in batch.pools.get(key, [])})
    # Unmapped roles use the general pool, independent of the legacy model.
    fallback = not ids
    if fallback:
        ids = batch.pools.get("general", [])
    now = utc_now()
    jobs = (
        list(
            (
                await session.scalars(
                    select(Job)
                    .options(
                        load_only(
                            Job.id,
                            Job.company_name,
                            Job.role_title,
                            Job.location,
                            Job.work_mode,
                            Job.skills,
                            Job.posted_at,
                            Job.can_apply_now,
                            Job.application_deadline,
                            Job.experience_min_years,
                            Job.experience_max_years,
                            Job.salary_min,
                            Job.salary_max,
                            Job.salary_currency,
                            Job.salary_period,
                        )
                    )
                    .where(Job.id.in_(ids))
                )
            ).all()
        )
        if ids
        else []
    )
    ranked = [rank_job(job, profile) for job in jobs if eligible(job, now)]
    ranked.sort(
        key=lambda item: (
            -(item["score"] or 0),
            -aware(item["postedAt"]).timestamp(),
            item["id"],
        )
    )
    stale = aware(batch.completed_at) < now - timedelta(hours=36)
    return {
        **base,
        "status": "STALE" if stale else "READY" if ranked else "EMPTY",
        "jobs": ranked[:25],
        "cohorts": cohorts,
        "fallback": fallback,
        "generatedAt": batch.completed_at,
        "catalogCount": batch.catalog_count,
        "candidateCount": len(ranked),
        "truncated": batch.truncated,
        "poolLimit": 1000,
    }


@router.get("/internal/recommendations/run")
async def run_daily(
    session: DatabaseSession,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    secret = get_settings().cron_secret
    if not secret or not compare_digest(
        (authorization or "").encode(), f"Bearer {secret}".encode()
    ):
        raise HTTPException(401, "Scheduler authentication required.")
    now = utc_now()
    batch_id = f"{VERSION}/{now.date().isoformat()}"
    # Transaction lock releases on disconnect, including pooled connections.
    if session.bind.dialect.name == "postgresql":
        locked = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(734201107)")
        )
        if not locked:
            return {"status": "BUSY"}
    existing = await session.get(RecommendationBatch, batch_id)
    if existing and existing.status == "READY":
        return {"status": "READY", "id": batch_id, "replayed": True}
    try:
        async with asyncio.timeout(90):
            pools, count, truncated = await collect_pools(session, now)
            batch = existing or RecommendationBatch(id=batch_id, created_at=now)
            batch.status, batch.pools = "READY", pools
            batch.catalog_count, batch.truncated = count, truncated
            batch.completed_at, batch.error_code = utc_now(), None
            session.add(batch)
            await session.commit()
    except Exception as exc:
        await session.rollback()
        # A failed publication never replaces the previous completed snapshot.
        # Reacquire serialization after rollback before recording failure.
        if session.bind.dialect.name == "postgresql":
            if not await session.scalar(
                text("SELECT pg_try_advisory_xact_lock(734201107)")
            ):
                raise HTTPException(
                    503, "Daily retrieval interrupted. Retry safely."
                ) from exc
        failed = await session.get(RecommendationBatch, batch_id)
        if failed is None or failed.status != "READY":
            failed = failed or RecommendationBatch(id=batch_id, created_at=now)
            failed.status = "FAILED"
            failed.error_code = (
                "TIMEOUT" if isinstance(exc, TimeoutError) else "RETRIEVAL_FAILED"
            )
            session.add(failed)
            await session.commit()
        raise HTTPException(
            503, "Daily retrieval failed. Previous results remain available."
        ) from exc
    return {
        "status": "READY",
        "id": batch_id,
        "replayed": False,
        "catalogCount": count,
        "truncated": truncated,
    }
