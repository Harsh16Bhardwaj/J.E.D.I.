"""Today's operational jobs and score leaderboards."""

from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import (
    Application,
    Batch,
    Job,
    JobPrediction,
    JobState,
    get_session,
)
from backend.schemas.dashboard import DashboardFeed, DashboardJob, LeaderboardPeriod
from backend.services.group_access import require_group_context

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
JEDI_TIMEZONE = ZoneInfo("Asia/Kolkata")


def _boundaries() -> tuple[datetime, datetime, datetime]:
    local_now = datetime.now(JEDI_TIMEZONE)
    today = datetime.combine(local_now.date(), time.min, tzinfo=JEDI_TIMEZONE)
    return (
        today.astimezone(UTC),
        (today + timedelta(days=1)).astimezone(UTC),
        (today - timedelta(days=6)).astimezone(UTC),
    )


def _visibility(fresh: bool, not_applied: bool) -> list:
    conditions = []
    if fresh:
        conditions.append(JobState.viewed_at.is_(None))
    if not_applied:
        conditions.append(
            or_(
                Application.job_id.is_(None),
                Application.status.in_(["NOT_STARTED", "PREPARING"]),
            )
        )
    return conditions


def _job(
    job: Job,
    batch: Batch,
    state: JobState | None,
    application: Application | None,
    prediction: JobPrediction | None,
) -> DashboardJob:
    return DashboardJob(
        id=job.id,
        code=job.code,
        company_name=job.company_name,
        role_title=job.role_title,
        seniority=job.seniority,
        location=job.location,
        work_mode=job.work_mode,
        employment_type=job.employment_type,
        description=job.description,
        salary_min=float(job.salary_min) if job.salary_min is not None else None,
        salary_max=float(job.salary_max) if job.salary_max is not None else None,
        salary_currency=job.salary_currency,
        posted_at=job.posted_at,
        apply_url=job.apply_url,
        batch_id=batch.id,
        batch_name=batch.external_batch_id,
        review_status=state.review_status if state else "NEW",
        application_status=application.status if application else "NOT_STARTED",
        rank=prediction.rank if prediction else None,
        jedi_preference_score=(
            prediction.jedi_preference_score if prediction else None
        ),
        ranking_score=prediction.ranking_score if prediction else None,
        apply_preference_probability=(
            prediction.apply_preference_probability if prediction else None
        ),
        apply_recommendation=(prediction.apply_recommendation if prediction else None),
        ranked_at=prediction.created_at if prediction else None,
    )


@router.get("", response_model=DashboardFeed)
async def dashboard_feed(
    user: CurrentUser,
    session: DatabaseSession,
    leaderboard_period: Annotated[
        LeaderboardPeriod, Query(alias="leaderboardPeriod")
    ] = LeaderboardPeriod.DAILY,
    fresh: bool = False,
    not_applied: Annotated[bool, Query(alias="notApplied")] = False,
) -> DashboardFeed:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    today_start, tomorrow_start, week_start = _boundaries()
    visibility = _visibility(fresh, not_applied)
    feed_query = (
        select(Job, Batch, JobState, Application)
        .join(Batch, Batch.id == Job.batch_id)
        .outerjoin(
            JobState,
            and_(
                JobState.job_id == Job.id,
                JobState.group_member_id == member_id,
            ),
        )
        .outerjoin(
            Application,
            and_(
                Application.job_id == Job.id,
                Application.group_member_id == member_id,
            ),
        )
        .where(
            or_(
                Batch.prompt_version.is_(None),
                Batch.prompt_version != "manual-csv-import",
            ),
            *visibility,
        )
    )
    today_rows = (
        await session.execute(
            feed_query.where(
                Batch.generated_at >= today_start,
                Batch.generated_at < tomorrow_start,
            )
            .order_by(Batch.generated_at.desc(), Job.created_at.desc())
            .limit(25)
        )
    ).all()
    job_feed_scope = "today"
    if not today_rows:
        today_rows = (
            await session.execute(
                feed_query.order_by(Batch.generated_at.desc(), Job.created_at.desc())
                .limit(25)
            )
        ).all()
        job_feed_scope = "latest"
    today_ids = [job.id for job, *_ in today_rows]
    latest_today: dict[str, JobPrediction] = {}
    if today_ids:
        predictions = (
            await session.scalars(
                select(JobPrediction)
                .where(JobPrediction.job_id.in_(today_ids))
                .order_by(JobPrediction.created_at.desc())
            )
        ).all()
        for prediction in predictions:
            latest_today.setdefault(prediction.job_id, prediction)

    ranking_query = (
        select(JobPrediction, Job, Batch, JobState, Application)
        .join(Job, Job.id == JobPrediction.job_id)
        .join(Batch, Batch.id == JobPrediction.batch_id)
        .outerjoin(
            JobState,
            and_(
                JobState.job_id == Job.id,
                JobState.group_member_id == member_id,
            ),
        )
        .outerjoin(
            Application,
            and_(
                Application.job_id == Job.id,
                Application.group_member_id == member_id,
            ),
        )
        .where(*visibility)
        .order_by(JobPrediction.created_at.desc())
    )
    if leaderboard_period == LeaderboardPeriod.DAILY:
        ranking_query = ranking_query.where(
            JobPrediction.created_at >= today_start,
            JobPrediction.created_at < tomorrow_start,
        )
    elif leaderboard_period == LeaderboardPeriod.WEEKLY:
        ranking_query = ranking_query.where(JobPrediction.created_at >= week_start)
    ranked_rows = (await session.execute(ranking_query)).all()
    latest_ranked: dict[
        str, tuple[JobPrediction, Job, Batch, JobState | None, Application | None]
    ] = {}
    for prediction, job, batch, state, application in ranked_rows:
        latest_ranked.setdefault(job.id, (prediction, job, batch, state, application))
    leaders = sorted(
        latest_ranked.values(),
        key=lambda row: (
            row[0].ranking_score,
            row[0].apply_preference_probability,
        ),
        reverse=True,
    )[:10]
    return DashboardFeed(
        today_jobs=[
            _job(job, batch, state, application, latest_today.get(job.id))
            for job, batch, state, application in today_rows
        ],
        job_feed_scope=job_feed_scope,
        leaderboard=[
            _job(job, batch, state, application, prediction)
            for prediction, job, batch, state, application in leaders
        ],
        leaderboard_period=leaderboard_period,
        fresh=fresh,
        not_applied=not_applied,
        generated_at=datetime.now(UTC),
    )
