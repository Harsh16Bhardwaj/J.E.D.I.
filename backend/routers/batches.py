"""Batch ingestion, review reads, filters, and guarded deletion."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.encoders import jsonable_encoder
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import (
    Application,
    Batch,
    Job,
    JobAnnotation,
    JobPrediction,
    JobState,
    ModelVersion,
    PreparedJob,
    ProcessingRun,
    TrainingExample,
    get_session,
    new_id,
)
from backend.schemas.product import (
    ActionAvailability,
    AnnotationResponse,
    BatchCreateResponse,
    BatchDetail,
    BatchMetricBucket,
    BatchMetricsResponse,
    BatchPage,
    BatchSummary,
    ImportEnvelope,
    IncomingJob,
    JobResponse,
    RelevanceLabel,
    ValidationIssue,
)
from backend.services.group_access import require_group_context
from backend.services.product import clean_job, remove_duplicates, stable_hash

router = APIRouter(prefix="/api/batches", tags=["batches"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
job_adapter = TypeAdapter(IncomingJob)

ANNOTATION_FIELDS = (
    "apply_label",
    "role_title_fit",
    "role_family_fit",
    "seniority_fit",
    "location_fit",
    "work_mode_fit",
    "experience_fit",
    "skills_fit",
    "salary_fit",
    "overall_preference",
)

FRIENDLY_ATTRIBUTES = (
    "Agile", "Bright", "Bold", "Brave", "Calm", "Candid", "Capable", "Clever",
    "Curious", "Daring", "Earnest", "Eager", "Focused", "Gallant", "Gentle",
    "Golden", "Grounded", "Happy", "Hardy", "Helpful", "Honest", "Keen", "Kind",
    "Lively", "Loyal", "Lucid", "Mighty", "Nimble", "Noble", "Patient", "Plucky",
    "Polished", "Quick", "Radiant", "Ready", "Resolute", "Sharp", "Steady",
    "Stellar", "Sunny", "Swift", "Thoughtful", "True", "Valiant", "Vibrant",
    "Warm", "Wise", "Witty", "Zesty", "Zealous",
)
FRIENDLY_SUBJECTS = (
    "Badger", "Beacon", "Bear", "Bee", "Bison", "Comet", "Condor", "Crane",
    "Dolphin", "Eagle", "Falcon", "Finch", "Fox", "Gazelle", "Harbor", "Heron",
    "Horizon", "Jaguar", "Kestrel", "Koala", "Lantern", "Leopard", "Lion", "Lynx",
    "Maple", "Meadow", "Meteor", "Narwhal", "Orca", "Otter", "Owl", "Panda",
    "Panther", "Pine", "Puffin", "Quill", "Raven", "River", "Robin", "Sequoia",
    "Sparrow", "Summit", "Swan", "Tiger", "Toucan", "Voyager", "Willow", "Wolf",
    "Wren", "Yak",
)
MAX_JOB_AGE = timedelta(days=30)
MAX_POSTED_AT_CLOCK_SKEW = timedelta(days=1)


def friendly_batch_name() -> str:
    """Return one of 250,000 friendly names; database uniqueness is authoritative."""
    return (
        f"{secrets.choice(FRIENDLY_ATTRIBUTES)} "
        f"{secrets.choice(FRIENDLY_SUBJECTS)} {secrets.randbelow(100):02d}"
    )


async def available_friendly_batch_name(session: AsyncSession) -> str:
    for _ in range(20):
        candidate = friendly_batch_name()
        exists = await session.scalar(
            select(Batch.id).where(Batch.display_name == candidate)
        )
        if exists is None:
            return candidate
    raise HTTPException(
        status_code=503,
        detail="A friendly batch name could not be allocated. Please retry.",
    )


def clean_current_job(job: IncomingJob) -> dict:
    """Reject unverifiable, stale, or implausibly future job postings."""
    if job.posted_at is None:
        raise ValueError(
            "postedAt is required to enforce the 30-day job freshness limit"
        )
    posted_at = job.posted_at
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    if posted_at < now - MAX_JOB_AGE:
        raise ValueError("postedAt is older than JEDI's 30-day import limit")
    if posted_at > now + MAX_POSTED_AT_CLOCK_SKEW:
        raise ValueError("postedAt cannot be more than one day in the future")
    return clean_job(job)


def batch_summary(batch: Batch) -> BatchSummary:
    return BatchSummary(
        id=batch.id,
        display_name=batch.display_name,
        external_batch_id=batch.external_batch_id,
        schema_version=batch.schema_version,
        prompt_version=batch.prompt_version,
        generated_at=batch.generated_at,
        status=batch.status,
        received_count=batch.received_count,
        valid_count=batch.valid_count,
        duplicate_count=batch.duplicate_count,
        job_count=batch.job_count,
        created_at=batch.created_at,
        ranked_at=batch.ranked_at,
    )


def annotation_complete(annotation: JobAnnotation | None) -> bool:
    return annotation is not None and all(
        getattr(annotation, field) is not None for field in ANNOTATION_FIELDS
    )


def annotation_response(
    job_id: str,
    state: JobState | None,
    annotation: JobAnnotation | None,
) -> AnnotationResponse | None:
    if state is None and annotation is None:
        return None
    return AnnotationResponse(
        job_id=job_id,
        relevance_label=state.relevance_label if state else None,
        apply_label=annotation.apply_label if annotation else None,
        complete=annotation_complete(annotation),
    )


def job_response(
    job: Job,
    state: JobState | None,
    annotation: JobAnnotation | None,
) -> JobResponse:
    return JobResponse(
        id=job.id,
        code=job.code,
        company_name=job.company_name,
        role_title=job.role_title,
        role_family=job.role_family,
        seniority=job.seniority,
        location=job.location,
        work_mode=job.work_mode,
        employment_type=job.employment_type,
        description=job.description,
        skills=job.skills,
        experience_min_years=job.experience_min_years,
        experience_max_years=job.experience_max_years,
        salary_min=float(job.salary_min) if job.salary_min is not None else None,
        salary_max=float(job.salary_max) if job.salary_max is not None else None,
        salary_currency=job.salary_currency,
        posted_at=job.posted_at,
        application_deadline=job.application_deadline,
        can_apply_now=job.can_apply_now,
        apply_url=job.apply_url,
        annotation=annotation_response(job.id, state, annotation),
    )


async def get_batch_or_404(session: AsyncSession, batch_id: str) -> Batch:
    batch = await session.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return batch


@router.post("", response_model=BatchCreateResponse, status_code=201)
async def create_batch(
    request: Request,
    _user: CurrentUser,
    session: DatabaseSession,
) -> BatchCreateResponse:
    """Authenticate first, then parse, deduplicate, and persist one upload."""
    try:
        raw_body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Body must be valid JSON.") from exc
    try:
        envelope = ImportEnvelope.model_validate(raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=exc.errors(include_context=False)
        ) from exc

    canonical_envelope = envelope.model_dump(mode="json", by_alias=True)
    content_hash = stable_hash(canonical_envelope)
    replay = await session.scalar(
        select(Batch).where(Batch.content_hash == content_hash)
    )
    if replay is not None:
        return BatchCreateResponse(
            batch_id=replay.id,
            status=replay.status,
            received_count=replay.received_count,
            valid_count=replay.valid_count,
            duplicate_count=replay.duplicate_count,
            job_count=replay.job_count,
            replayed=True,
            validation_report=[
                ValidationIssue.model_validate(item)
                for item in (replay.validation_report or [])
            ],
        )
    reused_id = await session.scalar(
        select(Batch).where(Batch.external_batch_id == envelope.external_batch_id)
    )
    if reused_id is not None:
        raise HTTPException(
            status_code=409,
            detail="externalBatchId already exists with different content.",
        )

    issues: list[ValidationIssue] = []
    cleaned_jobs: list[dict] = []
    for index, raw_job in enumerate(envelope.jobs):
        try:
            cleaned_jobs.append(
                clean_current_job(job_adapter.validate_python(raw_job))
            )
        except (ValidationError, ValueError) as exc:
            errors = (
                exc.errors(include_context=False)
                if isinstance(exc, ValidationError)
                else [{"type": "value_error", "msg": str(exc)}]
            )
            issues.append(ValidationIssue(source_index=index, errors=errors))

    company_keys = {item["company_key"] for item in cleaned_jobs}
    apply_urls = {item["apply_url"] for item in cleaned_jobs}
    candidates: list[Job] = []
    if company_keys or apply_urls:
        candidates = list(
            (
                await session.scalars(
                    select(Job).where(
                        or_(
                            Job.company_key.in_(company_keys),
                            Job.apply_url.in_(apply_urls),
                        )
                    )
                )
            ).all()
        )
    accepted, duplicate_count = remove_duplicates(cleaned_jobs, candidates)
    if not accepted:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No valid unique jobs remain; nothing was created.",
                "validCount": len(cleaned_jobs),
                "duplicateCount": duplicate_count,
                "validationReport": [
                    issue.model_dump(mode="json", by_alias=True) for issue in issues
                ],
            },
        )

    batch = Batch(
        id=new_id(),
        display_name=await available_friendly_batch_name(session),
        external_batch_id=envelope.external_batch_id,
        content_hash=content_hash,
        schema_version=envelope.schema_version,
        prompt_version=envelope.prompt_version,
        generated_at=envelope.generated_at,
        raw_envelope=jsonable_encoder(raw_body),
        status="READY",
        received_count=len(envelope.jobs),
        valid_count=len(cleaned_jobs),
        duplicate_count=duplicate_count,
        job_count=len(accepted),
        validation_report=[
            issue.model_dump(mode="json", by_alias=True) for issue in issues
        ],
    )
    session.add(batch)
    session.add_all(Job(batch_id=batch.id, **item) for item in accepted)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        concurrent = await session.scalar(
            select(Batch).where(Batch.content_hash == content_hash)
        )
        if concurrent is not None:
            return BatchCreateResponse(
                batch_id=concurrent.id,
                status=concurrent.status,
                received_count=concurrent.received_count,
                valid_count=concurrent.valid_count,
                duplicate_count=concurrent.duplicate_count,
                job_count=concurrent.job_count,
                replayed=True,
                validation_report=[],
            )
        raise HTTPException(
            status_code=409,
            detail="A concurrent import stored one of these unique jobs.",
        ) from exc
    return BatchCreateResponse(
        batch_id=batch.id,
        status=batch.status,
        received_count=batch.received_count,
        valid_count=batch.valid_count,
        duplicate_count=batch.duplicate_count,
        job_count=batch.job_count,
        replayed=False,
        validation_report=issues,
    )


async def list_batches_query(
    session: AsyncSession,
    only_unranked: bool,
    page: int,
    page_size: int,
) -> BatchPage:
    statement = select(Batch).order_by(Batch.created_at.desc())
    count_statement = select(func.count()).select_from(Batch)
    if only_unranked:
        statement = statement.where(Batch.ranked_at.is_(None))
        count_statement = count_statement.where(Batch.ranked_at.is_(None))
    total = await session.scalar(count_statement) or 0
    batches = (
        await session.scalars(statement.offset((page - 1) * page_size).limit(page_size))
    ).all()
    return BatchPage(
        items=[batch_summary(batch) for batch in batches],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("", response_model=BatchPage)
async def list_unranked_batches(
    _user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
) -> BatchPage:
    return await list_batches_query(session, True, page, page_size)


@router.get("/all", response_model=BatchPage)
async def list_all_batches(
    _user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
) -> BatchPage:
    return await list_batches_query(session, False, page, page_size)


@router.get("/{batch_id}/metrics", response_model=BatchMetricsResponse)
async def get_batch_metrics(
    batch_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> BatchMetricsResponse:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    batch = await get_batch_or_404(session, batch_id)
    latest_run = await session.scalar(
        select(ProcessingRun)
        .where(
            ProcessingRun.batch_id == batch_id,
            ProcessingRun.stage == "ranking",
            ProcessingRun.status == "SUCCEEDED",
        )
        .order_by(
            ProcessingRun.completed_at.desc().nullslast(),
            ProcessingRun.created_at.desc(),
        )
    )
    predictions = (
        (
            await session.scalars(
                select(JobPrediction).where(
                    JobPrediction.processing_run_id == latest_run.id
                )
            )
        ).all()
        if latest_run
        else []
    )
    states = (
        await session.scalars(
            select(JobState)
            .join(Job, Job.id == JobState.job_id)
            .where(
                Job.batch_id == batch_id,
                JobState.group_member_id == member_id,
            )
        )
    ).all()
    applications = (
        await session.scalars(
            select(Application)
            .join(Job, Job.id == Application.job_id)
            .where(
                Job.batch_id == batch_id,
                Application.group_member_id == member_id,
            )
        )
    ).all()

    scores = [float(item.ranking_score) for item in predictions]
    probabilities = [float(item.apply_preference_probability) for item in predictions]
    top_scores = sorted(scores, reverse=True)[:25]
    applied_statuses = {
        "APPLIED",
        "SCREENING",
        "ASSESSMENT",
        "INTERVIEW",
        "OFFER",
        "ACCEPTED",
        "REJECTED",
        "WITHDRAWN",
    }
    applied_count = sum(item.status in applied_statuses for item in applications)

    def average(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    score_buckets = [
        BatchMetricBucket(label="Below 50", count=sum(score < 50 for score in scores)),
        BatchMetricBucket(
            label="50–59", count=sum(50 <= score < 60 for score in scores)
        ),
        BatchMetricBucket(
            label="60–74", count=sum(60 <= score < 75 for score in scores)
        ),
        BatchMetricBucket(label="75+", count=sum(score >= 75 for score in scores)),
    ]
    component_values: dict[str, list[float]] = {}
    for prediction in predictions:
        for name, value in (prediction.component_scores or {}).items():
            if isinstance(value, int | float):
                component_values.setdefault(name, []).append(float(value))

    return BatchMetricsResponse(
        batch_id=batch.id,
        job_count=batch.job_count,
        ranked_count=len(predictions),
        average_score=average(scores),
        top_25_average_score=average(top_scores),
        average_apply_probability=average(probabilities),
        recommended_count=sum(
            item.apply_recommendation is True for item in predictions
        ),
        applied_count=applied_count,
        application_rate=(
            round(applied_count / batch.job_count, 4) if batch.job_count else 0
        ),
        viewed_count=sum(item.viewed_at is not None for item in states),
        bookmarked_count=sum(item.review_status == "SAVED" for item in states),
        score_buckets=score_buckets,
        component_averages={
            name: value
            for name, values in component_values.items()
            if (value := average(values)) is not None
        },
    )


@router.get("/{batch_id}", response_model=BatchDetail)
async def get_batch(
    batch_id: str,
    user: CurrentUser,
    session: DatabaseSession,
    annotation: Literal["all", "unannotated", "complete", "yes", "no"] = "all",
    relevance_label: Annotated[
        RelevanceLabel | None, Query(alias="relevanceLabel")
    ] = None,
    search: str | None = None,
) -> BatchDetail:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    batch = await get_batch_or_404(session, batch_id)
    statement = (
        select(Job, JobState, JobAnnotation)
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
        .where(Job.batch_id == batch_id)
        .order_by(Job.created_at, Job.id)
    )
    if relevance_label is not None:
        statement = statement.where(JobState.relevance_label == relevance_label.value)
    if search and search.strip():
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(Job.company_name.ilike(term), Job.role_title.ilike(term))
        )
    rows = (await session.execute(statement)).all()

    def matches(row: tuple[Job, JobState | None, JobAnnotation | None]) -> bool:
        _job, _state, item = row
        if annotation == "unannotated":
            return item is None
        if annotation == "complete":
            return annotation_complete(item)
        if annotation == "yes":
            return item is not None and item.apply_label is True
        if annotation == "no":
            return item is not None and item.apply_label is False
        return True

    visible_rows = [row for row in rows if matches(row)]
    annotation_count = await session.scalar(
        select(func.count())
        .select_from(JobAnnotation)
        .join(Job)
        .where(
            Job.batch_id == batch_id,
            JobAnnotation.group_member_id == member_id,
        )
    )
    training_count = await session.scalar(
        select(func.count())
        .select_from(TrainingExample)
        .where(TrainingExample.batch_id == batch_id)
    )
    prediction_count = await session.scalar(
        select(func.count())
        .select_from(JobPrediction)
        .where(JobPrediction.batch_id == batch_id)
    )
    active_model = (
        await session.get(ModelVersion, context.group.active_model_version_id)
        if context.group.active_model_version_id
        else None
    )
    prepared_filters = [Job.batch_id == batch_id]
    if context.group.active_profile_version_id:
        prepared_filters.append(
            PreparedJob.profile_version_id == context.group.active_profile_version_id
        )
    if active_model is not None:
        prepared_filters.append(
            PreparedJob.feature_schema_version == active_model.feature_schema_version
        )
    prepared_count = await session.scalar(
        select(func.count())
        .select_from(PreparedJob)
        .join(Job)
        .where(*prepared_filters)
    )
    normalization_complete = (
        batch.job_count > 0 and (prepared_count or 0) == batch.job_count
    )
    complete_count = sum(annotation_complete(item) for _, _, item in rows)
    actions = ActionAvailability(
        can_delete=not any(
            (annotation_count or 0, training_count or 0, prediction_count or 0)
        ),
        can_normalize=(
            not normalization_complete
            and batch.status in {"READY", "FAILED", "NORMALIZED", "RANKED"}
        ),
        can_annotate=True,
        can_add_to_training=(
            context.group.owner_id == user.id
            and bool(complete_count and prepared_count)
        ),
        can_process_ranks=batch.status in {"NORMALIZED", "RANKED"}
        and (prepared_count or 0) == batch.job_count,
    )
    return BatchDetail(
        batch=batch_summary(batch),
        actions=actions,
        prepared_count=prepared_count or 0,
        normalization_complete=normalization_complete,
        manual_annotation_count=annotation_count or 0,
        jobs=[job_response(*row) for row in visible_rows],
    )


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_batch(
    batch_id: str,
    _user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    await get_batch_or_404(session, batch_id)
    training_count = await session.scalar(
        select(func.count())
        .select_from(TrainingExample)
        .where(TrainingExample.batch_id == batch_id)
    )
    prediction_count = await session.scalar(
        select(func.count())
        .select_from(JobPrediction)
        .where(JobPrediction.batch_id == batch_id)
    )
    protected = (training_count or 0) + (prediction_count or 0)
    annotated = (
        await session.scalar(
            select(func.count())
            .select_from(JobAnnotation)
            .join(Job)
            .where(Job.batch_id == batch_id)
        )
        or 0
    )
    if protected or annotated:
        raise HTTPException(
            status_code=409,
            detail=(
                "Batch has annotations, training rows, or rankings and "
                "cannot be deleted."
            ),
        )
    await session.execute(delete(Batch).where(Batch.id == batch_id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
