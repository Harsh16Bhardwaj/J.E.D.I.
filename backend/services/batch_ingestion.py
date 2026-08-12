"""One canonical batch-ingestion transaction shared by uploads and scraper runs."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Batch, Job, new_id
from backend.schemas.product import (
    BatchCreateResponse,
    ImportEnvelope,
    IncomingJob,
    ValidationIssue,
)
from backend.services.product import clean_job, remove_duplicates, stable_hash

job_adapter = TypeAdapter(IncomingJob)
MAX_JOB_AGE = timedelta(days=30)
MAX_POSTED_AT_CLOCK_SKEW = timedelta(days=1)

FRIENDLY_ATTRIBUTES = (
    "Agile",
    "Bright",
    "Bold",
    "Calm",
    "Candid",
    "Clever",
    "Curious",
    "Focused",
    "Golden",
    "Keen",
    "Lucid",
    "Nimble",
    "Quick",
    "Sharp",
    "Steady",
    "Swift",
)
FRIENDLY_SUBJECTS = (
    "Beacon",
    "Comet",
    "Falcon",
    "Fox",
    "Harbor",
    "Horizon",
    "Lantern",
    "Meteor",
    "Owl",
    "Panda",
    "Raven",
    "River",
    "Robin",
    "Summit",
    "Voyager",
    "Wolf",
)


def clean_current_job(job: IncomingJob) -> dict[str, Any]:
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


async def available_friendly_batch_name(session: AsyncSession) -> str:
    for _ in range(20):
        candidate = (
            f"{secrets.choice(FRIENDLY_ATTRIBUTES)} "
            f"{secrets.choice(FRIENDLY_SUBJECTS)} {secrets.randbelow(100):02d}"
        )
        if (
            await session.scalar(
                select(Batch.id).where(Batch.display_name == candidate)
            )
            is None
        ):
            return candidate
    raise HTTPException(status_code=503, detail="A batch name could not be allocated.")


def batch_response(batch: Batch, *, replayed: bool) -> BatchCreateResponse:
    return BatchCreateResponse(
        batch_id=batch.id,
        status=batch.status,
        received_count=batch.received_count,
        valid_count=batch.valid_count,
        duplicate_count=batch.duplicate_count,
        job_count=batch.job_count,
        replayed=replayed,
        validation_report=[
            ValidationIssue.model_validate(item)
            for item in (batch.validation_report or [])
        ],
    )


async def ingest_batch(
    session: AsyncSession,
    raw_body: dict[str, Any],
) -> BatchCreateResponse:
    """Validate, deduplicate and commit exactly one import envelope."""
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
        return batch_response(replay, replayed=True)
    if (
        await session.scalar(
            select(Batch.id).where(
                Batch.external_batch_id == envelope.external_batch_id
            )
        )
        is not None
    ):
        raise HTTPException(
            status_code=409,
            detail="externalBatchId already exists with different content.",
        )

    issues: list[ValidationIssue] = []
    cleaned_jobs: list[dict[str, Any]] = []
    for index, raw_job in enumerate(envelope.jobs):
        try:
            cleaned_jobs.append(clean_current_job(job_adapter.validate_python(raw_job)))
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
                    item.model_dump(mode="json", by_alias=True) for item in issues
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
            item.model_dump(mode="json", by_alias=True) for item in issues
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
            return batch_response(concurrent, replayed=True)
        raise HTTPException(
            status_code=409,
            detail="A concurrent import stored one of these unique jobs.",
        ) from exc
    return batch_response(batch, replayed=False)
