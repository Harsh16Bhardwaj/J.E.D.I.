"""Profile, global job review, and application-tracking routes."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.auth import CurrentUser
from backend.database import (
    Application,
    ApplicationMilestone,
    Batch,
    Job,
    JobAnnotation,
    JobEvent,
    JobPrediction,
    JobState,
    ProcessingRun,
    ProfileVersion,
    get_session,
    utc_now,
)
from backend.routers.batches import (
    annotation_complete,
    batch_summary,
    job_response,
)
from backend.schemas.product import (
    AnnotationFilter,
    ApplicationActionItem,
    ApplicationDueFilter,
    ApplicationEventCreate,
    ApplicationListItem,
    ApplicationMilestoneCreate,
    ApplicationMilestonePatch,
    ApplicationMilestoneResponse,
    ApplicationMilestoneStatus,
    ApplicationPage,
    ApplicationPatch,
    ApplicationResponse,
    ApplicationSort,
    ApplicationStatus,
    ApplicationSummary,
    JobAnnotationDetail,
    JobDetail,
    JobEventResponse,
    JobListItem,
    JobPage,
    JobSort,
    JobStatePatch,
    JobStateResponse,
    LatestPrediction,
    PredictionSummary,
    ProfileCreate,
    ProfileDetail,
    ProfileSummary,
    ProfileWriteResponse,
    RelevanceLabel,
    ReviewStatus,
)
from backend.services.group_access import group_context, require_group_context
from backend.services.product import clean_text, stable_hash

router = APIRouter(tags=["workspace"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


def normalize_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = clean_text(value)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            normalized.append(cleaned)
            seen.add(key)
    return normalized


def profile_detail(profile: ProfileVersion) -> ProfileDetail:
    return ProfileDetail(
        id=profile.id,
        active=profile.active,
        resume_preview=profile.resume_text[:160],
        content_hash=profile.content_hash,
        resume_text=profile.resume_text,
        preferred_titles=profile.preferred_titles,
        preferred_locations=profile.preferred_locations,
        preferred_skills=profile.preferred_skills,
        experience_min_years=profile.experience_min_years,
        experience_max_years=profile.experience_max_years,
        salary_min=(
            float(profile.salary_min) if profile.salary_min is not None else None
        ),
        salary_max=(
            float(profile.salary_max) if profile.salary_max is not None else None
        ),
        salary_currency=profile.salary_currency,
        created_at=profile.created_at,
    )


def profile_summary(profile: ProfileVersion) -> ProfileSummary:
    detail = profile_detail(profile)
    return ProfileSummary.model_validate(detail.model_dump())


async def get_profile_or_404(session: AsyncSession, profile_id: str) -> ProfileVersion:
    profile = await session.get(ProfileVersion, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return profile


async def get_job_or_404(session: AsyncSession, job_id: str) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


def state_response(
    state: JobState | None,
    job_id: str,
    application: Application | None = None,
) -> JobStateResponse | None:
    if state is None:
        return None
    return JobStateResponse(
        job_id=job_id,
        relevance_label=state.relevance_label,
        review_status=state.review_status,
        application_status=application.status if application else "NOT_STARTED",
        viewed_at=state.viewed_at,
        notes=state.notes,
        updated_at=state.updated_at,
    )


def list_item(
    job: Job,
    batch: Batch,
    state: JobState | None,
    annotation: JobAnnotation | None,
    application: Application | None = None,
    prediction: JobPrediction | None = None,
) -> JobListItem:
    return JobListItem(
        id=job.id,
        code=job.code,
        company_name=job.company_name,
        role_title=job.role_title,
        location=job.location,
        work_mode=job.work_mode,
        salary_min=float(job.salary_min) if job.salary_min is not None else None,
        salary_max=float(job.salary_max) if job.salary_max is not None else None,
        salary_currency=job.salary_currency,
        salary_period=job.salary_period,
        batch_created_at=batch.created_at,
        created_at=job.created_at,
        relevance_label=state.relevance_label if state else None,
        review_status=state.review_status if state else "NEW",
        application_status=application.status if application else "NOT_STARTED",
        annotation_complete=annotation_complete(annotation),
        latest_prediction=(
            LatestPrediction(
                rank=prediction.rank,
                jedi_preference_score=prediction.jedi_preference_score,
                apply_preference_probability=prediction.apply_preference_probability,
                ranking_score=prediction.ranking_score,
                ranking_strategy=prediction.ranking_strategy,
                apply_recommendation=prediction.apply_recommendation,
                processing_run_id=prediction.processing_run_id,
                ranked_at=prediction.created_at,
            )
            if prediction
            else None
        ),
    )


def application_response(
    application: Application | None, job_id: str
) -> ApplicationResponse:
    return ApplicationResponse(
        job_id=job_id,
        status=application.status if application else "NOT_STARTED",
        applied_at=application.applied_at if application else None,
        target_apply_by=application.target_apply_by if application else None,
        next_action=application.next_action if application else None,
        next_action_due_at=(application.next_action_due_at if application else None),
        portal_url=application.portal_url if application else None,
        reference_code=application.reference_code if application else None,
        notes=application.notes if application else None,
        closed_at=application.closed_at if application else None,
        created_at=application.created_at if application else None,
        updated_at=application.updated_at if application else None,
    )


def milestone_response(
    milestone: ApplicationMilestone,
    job_id: str,
) -> ApplicationMilestoneResponse:
    return ApplicationMilestoneResponse(
        id=milestone.id,
        job_id=job_id,
        type=milestone.type,
        title=milestone.title,
        status=milestone.status,
        scheduled_at=milestone.scheduled_at,
        completed_at=milestone.completed_at,
        notes=milestone.notes,
        created_at=milestone.created_at,
        updated_at=milestone.updated_at,
    )


def annotation_detail(
    annotation: JobAnnotation | None,
) -> JobAnnotationDetail | None:
    if annotation is None:
        return None
    return JobAnnotationDetail(
        apply_label=annotation.apply_label,
        role_title_fit=annotation.role_title_fit,
        role_family_fit=annotation.role_family_fit,
        seniority_fit=annotation.seniority_fit,
        location_fit=annotation.location_fit,
        work_mode_fit=annotation.work_mode_fit,
        experience_fit=annotation.experience_fit,
        skills_fit=annotation.skills_fit,
        salary_fit=annotation.salary_fit,
        overall_preference=annotation.overall_preference,
        complete=annotation_complete(annotation),
    )


def event_response(event: JobEvent, job_id: str) -> JobEventResponse:
    return JobEventResponse(
        id=event.id,
        job_id=job_id,
        event_type=event.event_type,
        previous_status=event.previous_status,
        new_status=event.new_status,
        notes=event.notes,
        event_at=event.event_at,
        created_at=event.created_at,
    )


def apply_job_filters(
    statement,
    *,
    search: str | None,
    batch_id: str | None,
    relevance_label: RelevanceLabel | None,
    review_status: ReviewStatus | None,
    application_status: ApplicationStatus | None,
    viewed: bool | None = None,
    applied: bool | None = None,
    minimum_score: float | None = None,
    prediction=None,
    annotation_filter: AnnotationFilter = AnnotationFilter.ALL,
):
    if search and search.strip():
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(Job.company_name.ilike(term), Job.role_title.ilike(term))
        )
    if batch_id:
        statement = statement.where(Job.batch_id == batch_id)
    if relevance_label:
        statement = statement.where(JobState.relevance_label == relevance_label.value)
    if review_status:
        condition = JobState.review_status == review_status.value
        if review_status == ReviewStatus.NEW:
            condition = or_(JobState.job_id.is_(None), condition)
        statement = statement.where(condition)
    if application_status:
        condition = Application.status == application_status.value
        if application_status == ApplicationStatus.NOT_STARTED:
            condition = or_(Application.job_id.is_(None), condition)
        statement = statement.where(condition)
    if viewed is not None:
        statement = statement.where(
            JobState.viewed_at.is_not(None) if viewed else JobState.viewed_at.is_(None)
        )
    if applied is not None:
        not_applied = or_(
            Application.job_id.is_(None),
            Application.status.in_(["NOT_STARTED", "PREPARING"]),
        )
        statement = statement.where(~not_applied if applied else not_applied)
    if minimum_score is not None:
        statement = statement.where(prediction.ranking_score >= minimum_score)
    complete = and_(
        JobAnnotation.apply_label.is_not(None),
        JobAnnotation.role_title_fit.is_not(None),
        JobAnnotation.role_family_fit.is_not(None),
        JobAnnotation.seniority_fit.is_not(None),
        JobAnnotation.location_fit.is_not(None),
        JobAnnotation.work_mode_fit.is_not(None),
        JobAnnotation.experience_fit.is_not(None),
        JobAnnotation.skills_fit.is_not(None),
        JobAnnotation.salary_fit.is_not(None),
        JobAnnotation.overall_preference.is_not(None),
    )
    if annotation_filter == AnnotationFilter.COMPLETE:
        statement = statement.where(complete)
    elif annotation_filter == AnnotationFilter.INCOMPLETE:
        statement = statement.where(or_(JobAnnotation.job_id.is_(None), ~complete))
    return statement


def latest_prediction_alias():
    ranked = (
        select(
            JobPrediction.id.label("prediction_id"),
            JobPrediction.job_id.label("job_id"),
            func.row_number()
            .over(
                partition_by=JobPrediction.job_id,
                order_by=(JobPrediction.created_at.desc(), JobPrediction.id.desc()),
            )
            .label("position"),
        )
        .join(ProcessingRun, ProcessingRun.id == JobPrediction.processing_run_id)
        .where(ProcessingRun.status == "SUCCEEDED")
        .subquery()
    )
    prediction = aliased(JobPrediction)
    return ranked, prediction


def utc_day_bounds() -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


@router.post(
    "/api/profiles",
    response_model=ProfileWriteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    body: ProfileCreate,
    response: Response,
    _user: CurrentUser,
    session: DatabaseSession,
) -> ProfileWriteResponse:
    normalized = {
        "resume_text": clean_text(body.resume_text),
        "preferred_titles": normalize_list(body.preferred_titles),
        "preferred_locations": normalize_list(body.preferred_locations),
        "preferred_skills": normalize_list(body.preferred_skills),
        "experience_min_years": body.experience_min_years,
        "experience_max_years": body.experience_max_years,
        "salary_min": body.salary_min,
        "salary_max": body.salary_max,
        "salary_currency": (
            clean_text(body.salary_currency).upper() if body.salary_currency else None
        ),
    }
    content_hash = stable_hash(normalized)
    existing = await session.scalar(
        select(ProfileVersion).where(ProfileVersion.content_hash == content_hash)
    )
    if existing:
        response.status_code = status.HTTP_200_OK
        return ProfileWriteResponse(
            **profile_detail(existing).model_dump(), replayed=True
        )

    profile = ProfileVersion(
        content_hash=content_hash,
        active=False,
        **normalized,
    )
    session.add(profile)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        concurrent = await session.scalar(
            select(ProfileVersion).where(ProfileVersion.content_hash == content_hash)
        )
        if concurrent:
            response.status_code = status.HTTP_200_OK
            return ProfileWriteResponse(
                **profile_detail(concurrent).model_dump(), replayed=True
            )
        raise HTTPException(
            status_code=409, detail="Profile could not be created."
        ) from exc
    return ProfileWriteResponse(**profile_detail(profile).model_dump(), replayed=False)


@router.get("/api/profiles", response_model=list[ProfileSummary])
async def list_profiles(
    _user: CurrentUser, session: DatabaseSession
) -> list[ProfileSummary]:
    profiles = (
        await session.scalars(
            select(ProfileVersion).order_by(ProfileVersion.created_at.desc())
        )
    ).all()
    return [profile_summary(profile) for profile in profiles]


@router.get("/api/profiles/active", response_model=ProfileDetail)
async def get_active_profile(
    _user: CurrentUser,
    session: DatabaseSession,
) -> ProfileDetail:
    profile = await session.scalar(
        select(ProfileVersion)
        .where(ProfileVersion.active.is_(True))
        .order_by(ProfileVersion.created_at.desc())
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="No active profile exists.")
    return profile_detail(profile)


@router.get("/api/profiles/{profile_id}", response_model=ProfileDetail)
async def get_profile(
    profile_id: str,
    _user: CurrentUser,
    session: DatabaseSession,
) -> ProfileDetail:
    return profile_detail(await get_profile_or_404(session, profile_id))


@router.post("/api/profiles/{profile_id}/activate", response_model=ProfileDetail)
async def activate_profile(
    profile_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> ProfileDetail:
    profile = await get_profile_or_404(session, profile_id)
    await session.execute(update(ProfileVersion).values(active=False))
    profile.active = True
    context = await group_context(session, user.id, lock=True) if user else None
    if context:
        context.group.active_profile_version_id = profile.id
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Another profile activation completed concurrently.",
        ) from exc
    return profile_detail(profile)


@router.get("/api/jobs", response_model=JobPage)
async def list_jobs(
    user: CurrentUser,
    session: DatabaseSession,
    search: str | None = None,
    batch_id: Annotated[str | None, Query(alias="batchId")] = None,
    relevance_label: Annotated[
        RelevanceLabel | None, Query(alias="relevanceLabel")
    ] = None,
    review_status: Annotated[ReviewStatus | None, Query(alias="reviewStatus")] = None,
    application_status: Annotated[
        ApplicationStatus | None, Query(alias="applicationStatus")
    ] = None,
    viewed: bool | None = None,
    applied: bool | None = None,
    minimum_score: Annotated[
        float | None, Query(alias="minScore", ge=0, le=100)
    ] = None,
    sort: JobSort = JobSort.RECENT,
    annotation: AnnotationFilter = AnnotationFilter.ALL,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
) -> JobPage:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    ranked, prediction = latest_prediction_alias()
    joins = (
        select(Job, Batch, JobState, JobAnnotation, Application, prediction)
        .join(Batch, Batch.id == Job.batch_id)
        .outerjoin(
            JobState,
            and_(JobState.job_id == Job.id, JobState.group_member_id == member_id),
        )
        .outerjoin(
            JobAnnotation,
            and_(
                JobAnnotation.job_id == Job.id,
                JobAnnotation.group_member_id == member_id,
            ),
        )
        .outerjoin(
            Application,
            and_(
                Application.job_id == Job.id,
                Application.group_member_id == member_id,
            ),
        )
        .outerjoin(ranked, and_(ranked.c.job_id == Job.id, ranked.c.position == 1))
        .outerjoin(prediction, prediction.id == ranked.c.prediction_id)
    )
    count = (
        select(func.count())
        .select_from(Job)
        .outerjoin(
            JobState,
            and_(JobState.job_id == Job.id, JobState.group_member_id == member_id),
        )
        .outerjoin(
            JobAnnotation,
            and_(
                JobAnnotation.job_id == Job.id,
                JobAnnotation.group_member_id == member_id,
            ),
        )
        .outerjoin(
            Application,
            and_(
                Application.job_id == Job.id,
                Application.group_member_id == member_id,
            ),
        )
        .outerjoin(ranked, and_(ranked.c.job_id == Job.id, ranked.c.position == 1))
        .outerjoin(prediction, prediction.id == ranked.c.prediction_id)
    )
    filters = {
        "search": search,
        "batch_id": batch_id,
        "relevance_label": relevance_label,
        "review_status": review_status,
        "application_status": application_status,
        "viewed": viewed,
        "applied": applied,
        "minimum_score": minimum_score,
        "prediction": prediction,
        "annotation_filter": annotation,
    }
    joins = apply_job_filters(joins, **filters)
    count = apply_job_filters(count, **filters)
    total = await session.scalar(count) or 0
    ordering = (Job.created_at.desc(), Job.id.desc())
    if sort == JobSort.SCORE:
        ordering = (
            prediction.ranking_score.desc().nullslast(),
            prediction.apply_preference_probability.desc().nullslast(),
            Job.id.desc(),
        )
    rows = (
        await session.execute(
            joins.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return JobPage(
        items=[list_item(*row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/api/jobs/{job_id}", response_model=JobDetail)
async def get_job(
    job_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> JobDetail:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    job = await get_job_or_404(session, job_id)
    batch = await session.get(Batch, job.batch_id)
    state = await session.scalar(
        select(JobState).where(
            JobState.group_member_id == member_id, JobState.job_id == job.id
        )
    )
    application = await session.scalar(
        select(Application).where(
            Application.group_member_id == member_id, Application.job_id == job.id
        )
    )
    annotation = await session.scalar(
        select(JobAnnotation).where(
            JobAnnotation.group_member_id == member_id,
            JobAnnotation.job_id == job.id,
        )
    )
    milestones = (
        await session.scalars(
            select(ApplicationMilestone)
            .where(
                ApplicationMilestone.application_id
                == (application.id if application else "")
            )
            .order_by(
                ApplicationMilestone.scheduled_at.asc().nullslast(),
                ApplicationMilestone.created_at.asc(),
            )
        )
    ).all()
    predictions = (
        await session.scalars(
            select(JobPrediction)
            .where(JobPrediction.job_id == job.id)
            .order_by(JobPrediction.created_at.desc())
        )
    ).all()
    events = (
        await session.scalars(
            select(JobEvent)
            .where(JobEvent.application_id == (application.id if application else ""))
            .order_by(JobEvent.event_at.desc(), JobEvent.created_at.desc())
        )
    ).all()
    if batch is None:
        raise HTTPException(status_code=500, detail="Job has no owning batch.")
    return JobDetail(
        job=job_response(job, state, annotation),
        batch=batch_summary(batch),
        state=state_response(state, job.id, application),
        annotation=annotation_detail(annotation),
        application=application_response(application, job.id),
        milestones=[milestone_response(item, job.id) for item in milestones],
        predictions=[
            PredictionSummary(
                id=item.id,
                rank=item.rank,
                jedi_preference_score=item.jedi_preference_score,
                apply_preference_probability=item.apply_preference_probability,
                component_scores=item.component_scores,
                ranking_score=item.ranking_score,
                ranking_strategy=item.ranking_strategy,
                apply_threshold=item.apply_threshold,
                model_apply_decision=item.model_apply_decision,
                apply_recommendation=item.apply_recommendation,
                output_schema_version=item.output_schema_version,
                profile_version_id=item.profile_version_id,
                model_version_id=item.model_version_id,
                processing_run_id=item.processing_run_id,
                created_at=item.created_at,
            )
            for item in predictions
        ],
        events=[event_response(item, job.id) for item in events],
    )


@router.patch("/api/jobs/{job_id}/state", response_model=JobStateResponse)
async def update_job_state(
    job_id: str,
    body: JobStatePatch,
    user: CurrentUser,
    session: DatabaseSession,
) -> JobStateResponse:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    await get_job_or_404(session, job_id)
    state = await session.scalar(
        select(JobState).where(
            JobState.group_member_id == member_id, JobState.job_id == job_id
        )
    )
    if state is None:
        state = JobState(group_member_id=member_id, job_id=job_id)
        session.add(state)
    if "relevance_label" in body.model_fields_set:
        state.relevance_label = (
            body.relevance_label.value if body.relevance_label else None
        )
    if "review_status" in body.model_fields_set and body.review_status:
        state.review_status = body.review_status.value
        if body.review_status != ReviewStatus.NEW and state.viewed_at is None:
            state.viewed_at = utc_now()
    if "notes" in body.model_fields_set:
        state.notes = body.notes.strip() if body.notes else None
    await session.flush()
    application = await session.scalar(
        select(Application).where(
            Application.group_member_id == member_id, Application.job_id == job_id
        )
    )
    result = state_response(state, job_id, application)
    await session.commit()
    if result is None:  # pragma: no cover - state is created above
        raise HTTPException(status_code=500, detail="Job state was not saved.")
    return result


@router.post("/api/jobs/{job_id}/view", response_model=JobStateResponse)
async def mark_job_viewed(
    job_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> JobStateResponse:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    await get_job_or_404(session, job_id)
    state = await session.scalar(
        select(JobState).where(
            JobState.group_member_id == member_id, JobState.job_id == job_id
        )
    )
    if state is None:
        state = JobState(
            group_member_id=member_id,
            job_id=job_id,
            review_status="VIEWED",
            viewed_at=utc_now(),
        )
        session.add(state)
    elif state.viewed_at is None:
        state.viewed_at = utc_now()
        if state.review_status == "NEW":
            state.review_status = "VIEWED"
    application = await session.scalar(
        select(Application).where(
            Application.group_member_id == member_id, Application.job_id == job_id
        )
    )
    await session.flush()
    result = state_response(state, job_id, application)
    await session.commit()
    if result is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Viewed state was not saved.")
    return result


@router.get("/api/jobs/{job_id}/application", response_model=ApplicationResponse)
async def get_application(
    job_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> ApplicationResponse:
    context = await require_group_context(session, user.id)
    await get_job_or_404(session, job_id)
    application = await session.scalar(
        select(Application).where(
            Application.group_member_id == context.membership.id,
            Application.job_id == job_id,
        )
    )
    return application_response(application, job_id)


def _same_instant(left: datetime, right: datetime) -> bool:
    def aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    return aware(left) == aware(right)


@router.patch("/api/jobs/{job_id}/application", response_model=ApplicationResponse)
async def update_application(
    job_id: str,
    body: ApplicationPatch,
    user: CurrentUser,
    session: DatabaseSession,
) -> ApplicationResponse:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    await get_job_or_404(session, job_id)
    application = await session.scalar(
        select(Application)
        .where(
            Application.group_member_id == member_id,
            Application.job_id == job_id,
        )
        .with_for_update()
    )
    if (
        application
        and body.expected_updated_at
        and not _same_instant(application.updated_at, body.expected_updated_at)
    ):
        raise HTTPException(
            status_code=409,
            detail="Application changed after it was loaded. Refresh and retry.",
        )
    if application is None:
        application = Application(group_member_id=member_id, job_id=job_id)
        session.add(application)

    text_fields = {"next_action", "portal_url", "reference_code", "notes"}
    for field in body.model_fields_set - {"expected_updated_at"}:
        value = getattr(body, field)
        if field in text_fields:
            value = value.strip() if value and value.strip() else None
        setattr(application, field, value)
    if application.next_action_due_at and not application.next_action:
        raise HTTPException(
            status_code=422,
            detail="nextActionDueAt requires a non-empty nextAction.",
        )
    await session.flush()
    result = application_response(application, job_id)
    await session.commit()
    return result


@router.get("/api/applications", response_model=ApplicationPage)
async def list_applications(
    user: CurrentUser,
    session: DatabaseSession,
    search: str | None = None,
    application_status: Annotated[
        ApplicationStatus | None, Query(alias="applicationStatus")
    ] = None,
    due: ApplicationDueFilter = ApplicationDueFilter.ALL,
    sort: ApplicationSort = ApplicationSort.UPDATED,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
) -> ApplicationPage:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    ranked, prediction = latest_prediction_alias()
    statement = (
        select(Job, Batch, JobState, JobAnnotation, Application, prediction)
        .join(Batch, Batch.id == Job.batch_id)
        .outerjoin(
            JobState,
            and_(JobState.job_id == Job.id, JobState.group_member_id == member_id),
        )
        .outerjoin(
            JobAnnotation,
            and_(
                JobAnnotation.job_id == Job.id,
                JobAnnotation.group_member_id == member_id,
            ),
        )
        .outerjoin(
            Application,
            and_(
                Application.job_id == Job.id,
                Application.group_member_id == member_id,
            ),
        )
        .outerjoin(ranked, and_(ranked.c.job_id == Job.id, ranked.c.position == 1))
        .outerjoin(prediction, prediction.id == ranked.c.prediction_id)
    )
    count = (
        select(func.count())
        .select_from(Job)
        .outerjoin(
            Application,
            and_(
                Application.job_id == Job.id,
                Application.group_member_id == member_id,
            ),
        )
    )
    if application_status:
        condition = Application.status == application_status.value
    else:
        # A saved plan is tracked even before a stage transition is recorded.
        condition = Application.job_id.is_not(None)
    statement = statement.where(condition)
    count = count.where(condition)
    if search and search.strip():
        term = f"%{search.strip()}%"
        search_condition = or_(Job.company_name.ilike(term), Job.role_title.ilike(term))
        statement = statement.where(search_condition)
        count = count.where(search_condition)
    now = datetime.now(UTC)
    today_start, tomorrow_start = utc_day_bounds()
    due_condition = None
    if due == ApplicationDueFilter.OVERDUE:
        due_condition = Application.next_action_due_at < now
    elif due == ApplicationDueFilter.TODAY:
        due_condition = and_(
            Application.next_action_due_at >= today_start,
            Application.next_action_due_at < tomorrow_start,
        )
    elif due == ApplicationDueFilter.WEEK:
        due_condition = and_(
            Application.next_action_due_at >= now,
            Application.next_action_due_at < now + timedelta(days=7),
        )
    elif due == ApplicationDueFilter.NONE:
        due_condition = Application.next_action_due_at.is_(None)
    if due_condition is not None:
        statement = statement.where(due_condition)
        count = count.where(due_condition)
    total = await session.scalar(count) or 0
    filtered_base = (
        select(Application.status, func.count())
        .join(Job, Job.id == Application.job_id)
        .where(Application.group_member_id == member_id)
    )
    if search and search.strip():
        filtered_base = filtered_base.where(search_condition)
    if due_condition is not None:
        filtered_base = filtered_base.where(due_condition)
    status_rows = (
        await session.execute(filtered_base.group_by(Application.status))
    ).all()
    status_counts = {name: count for name, count in status_rows}
    overdue_statement = (
        select(func.count())
        .select_from(Application)
        .join(Job, Job.id == Application.job_id)
        .where(
            Application.group_member_id == member_id,
            Application.next_action_due_at < now,
        )
    )
    if search and search.strip():
        overdue_statement = overdue_statement.where(search_condition)
    overdue_count = await session.scalar(overdue_statement) or 0
    ordering = (Application.updated_at.desc(), Job.id.desc())
    if sort == ApplicationSort.NEXT_ACTION:
        ordering = (
            Application.next_action_due_at.asc().nullslast(),
            Application.updated_at.desc(),
            Job.id.desc(),
        )
    rows = (
        await session.execute(
            statement.order_by(*ordering)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    latest_events: dict[str, JobEvent] = {}
    application_jobs = {
        application.id: job.id
        for job, _, _, _, application, _ in rows
        if application
    }
    if application_jobs:
        events = (
            await session.scalars(
                select(JobEvent)
                .where(JobEvent.application_id.in_(application_jobs))
                .order_by(
                    JobEvent.application_id,
                    JobEvent.event_at.desc(),
                    JobEvent.created_at.desc(),
                )
            )
        ).all()
        for event in events:
            latest_events.setdefault(application_jobs[event.application_id], event)
    return ApplicationPage(
        items=[
            ApplicationListItem(
                job=list_item(
                    job, batch, state, annotation, application, prediction
                ),
                notes=application.notes,
                application=application_response(application, job.id),
                latest_event=(
                    event_response(latest_events[job.id], job.id)
                    if job.id in latest_events
                    else None
                ),
            )
            for job, batch, state, annotation, application, prediction in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        status_counts=status_counts,
        overdue_count=overdue_count,
    )


@router.get("/api/applications/summary", response_model=ApplicationSummary)
async def application_summary(
    user: CurrentUser,
    session: DatabaseSession,
) -> ApplicationSummary:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    now = datetime.now(UTC)
    today_start, tomorrow_start = utc_day_bounds()
    status_rows = (
        await session.execute(
            select(Application.status, func.count())
            .where(
                Application.group_member_id == member_id,
            )
            .group_by(Application.status)
        )
    ).all()
    overdue_count = (
        await session.scalar(
            select(func.count())
            .select_from(Application)
            .where(
                Application.group_member_id == member_id,
                Application.next_action_due_at < now,
            )
        )
        or 0
    )
    due_today_count = (
        await session.scalar(
            select(func.count())
            .select_from(Application)
            .where(
                Application.group_member_id == member_id,
                Application.next_action_due_at >= today_start,
                Application.next_action_due_at < tomorrow_start,
            )
        )
        or 0
    )
    action_rows = (
        await session.execute(
            select(Application, Job)
            .join(Job, Job.id == Application.job_id)
            .where(
                Application.group_member_id == member_id,
                Application.next_action.is_not(None),
                Application.next_action_due_at.is_not(None),
            )
            .order_by(Application.next_action_due_at.asc(), Job.id.asc())
            .limit(5)
        )
    ).all()
    return ApplicationSummary(
        status_counts={name: count for name, count in status_rows},
        overdue_count=overdue_count,
        due_today_count=due_today_count,
        nearest_actions=[
            ApplicationActionItem(
                job_id=job.id,
                company_name=job.company_name,
                role_title=job.role_title,
                application_status=application.status,
                next_action=application.next_action,
                next_action_due_at=application.next_action_due_at,
                application_updated_at=application.updated_at,
            )
            for application, job in action_rows
        ],
    )


@router.post(
    "/api/jobs/{job_id}/application-events",
    response_model=JobEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application_event(
    job_id: str,
    body: ApplicationEventCreate,
    user: CurrentUser,
    session: DatabaseSession,
) -> JobEventResponse:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    await get_job_or_404(session, job_id)
    application = await session.scalar(
        select(Application)
        .where(
            Application.group_member_id == member_id,
            Application.job_id == job_id,
        )
        .with_for_update()
    )
    if application is None:
        application = Application(group_member_id=member_id, job_id=job_id)
        session.add(application)
        await session.flush()
    previous_status = application.status
    event_at = body.event_at or utc_now()
    application.status = body.application_status.value
    if (
        body.application_status == ApplicationStatus.APPLIED
        and not application.applied_at
    ):
        application.applied_at = event_at
    terminal = {
        ApplicationStatus.ACCEPTED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    }
    application.closed_at = event_at if body.application_status in terminal else None
    event = JobEvent(
        application_id=application.id,
        event_type=body.application_status.value,
        previous_status=previous_status,
        new_status=body.application_status.value,
        event_at=event_at,
        notes=body.notes.strip() if body.notes else None,
    )
    session.add(event)
    try:
        await session.flush()
        result = event_response(event, job_id)
        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail="Application event was not saved; no state changed.",
        ) from exc
    return result


@router.post(
    "/api/jobs/{job_id}/application-milestones",
    response_model=ApplicationMilestoneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application_milestone(
    job_id: str,
    body: ApplicationMilestoneCreate,
    user: CurrentUser,
    session: DatabaseSession,
) -> ApplicationMilestoneResponse:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    await get_job_or_404(session, job_id)
    application = await session.scalar(
        select(Application).where(
            Application.group_member_id == member_id,
            Application.job_id == job_id,
        )
    )
    if application is None:
        application = Application(group_member_id=member_id, job_id=job_id)
        session.add(application)
        await session.flush()
    milestone = ApplicationMilestone(
        application_id=application.id,
        type=body.type.value,
        title=body.title.strip(),
        scheduled_at=body.scheduled_at,
        notes=body.notes.strip() if body.notes else None,
    )
    session.add(milestone)
    await session.flush()
    result = milestone_response(milestone, job_id)
    await session.commit()
    return result


@router.patch(
    "/api/jobs/{job_id}/application-milestones/{milestone_id}",
    response_model=ApplicationMilestoneResponse,
)
async def update_application_milestone(
    job_id: str,
    milestone_id: str,
    body: ApplicationMilestonePatch,
    user: CurrentUser,
    session: DatabaseSession,
) -> ApplicationMilestoneResponse:
    context = await require_group_context(session, user.id)
    application = await session.scalar(
        select(Application).where(
            Application.group_member_id == context.membership.id,
            Application.job_id == job_id,
        )
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application milestone not found.")
    await get_job_or_404(session, job_id)
    milestone = await session.scalar(
        select(ApplicationMilestone)
        .where(
            ApplicationMilestone.id == milestone_id,
            ApplicationMilestone.application_id == application.id,
        )
        .with_for_update()
    )
    if milestone is None:
        raise HTTPException(status_code=404, detail="Application milestone not found.")
    for field in body.model_fields_set:
        value = getattr(body, field)
        if field in {"type", "status"} and value is not None:
            value = value.value
        if field in {"title", "notes"}:
            value = value.strip() if value and value.strip() else None
        setattr(milestone, field, value)
    if "status" in body.model_fields_set:
        milestone.completed_at = (
            utc_now() if body.status == ApplicationMilestoneStatus.COMPLETED else None
        )
    await session.flush()
    result = milestone_response(milestone, job_id)
    await session.commit()
    return result


@router.get(
    "/api/jobs/{job_id}/application-events",
    response_model=list[JobEventResponse],
)
async def list_application_events(
    job_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> list[JobEventResponse]:
    context = await require_group_context(session, user.id)
    await get_job_or_404(session, job_id)
    application = await session.scalar(
        select(Application).where(
            Application.group_member_id == context.membership.id,
            Application.job_id == job_id,
        )
    )
    if application is None:
        return []
    events = (
        await session.scalars(
            select(JobEvent)
            .where(JobEvent.application_id == application.id)
            .order_by(JobEvent.event_at.desc(), JobEvent.created_at.desc())
        )
    ).all()
    return [event_response(event, job_id) for event in events]
