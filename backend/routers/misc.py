"""One-time imports and dense training-data maintenance tools."""

import csv
import json
from datetime import UTC, datetime
from io import StringIO
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import (
    Batch,
    Job,
    JobAnnotation,
    JobState,
    PreparedJob,
    ProfileVersion,
    TrainingExample,
    get_session,
    new_id,
)
from backend.routers.batches import ANNOTATION_FIELDS, batch_summary, get_batch_or_404
from backend.schemas.product import (
    AnnotationEditorResponse,
    AnnotationEditorRow,
    AnnotationInput,
    CsvTrainingImportResponse,
    IncomingJob,
)
from backend.services.group_access import require_group_context, require_group_owner
from backend.services.product import (
    clean_job,
    make_code,
    prepare_job,
    remove_duplicates,
    stable_hash,
)

router = APIRouter(prefix="/api/misc", tags=["misc"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]

LABEL_COLUMNS = {
    "applied",
    "apply_label",
    "role_title_preference_score",
    "role_title_fit",
    "role_family_preference_score",
    "role_family_fit",
    "seniority_profile_fit_score",
    "seniority_fit",
    "location_profile_fit_score",
    "location_fit",
    "work_mode_fit_score",
    "work_mode_fit",
    "experience_profile_fit_score",
    "experience_fit",
    "skills_profile_fit_score",
    "skills_fit",
    "salary_profile_fit_score",
    "salary_fit",
    "overall_preference_score",
    "overall_preference",
}
FRONTIER_EXCLUDED = {
    "apply_url",
    "company_name",
    "company_name_standard",
    "evaluation_group",
    "near_duplicate_key",
    "preference_reason",
    "role_title_standard",
    "row_id",
    "scraped_at",
    "source_platform",
    "source_type",
    *LABEL_COLUMNS,
}


def _value(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _number(row: dict[str, str], *names: str) -> float | None:
    value = _value(row, *names)
    return float(value) if value is not None else None


def _boolean(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.casefold()
    if normalized in {"true", "yes", "1", "y"}:
        return True
    if normalized in {"false", "no", "0", "n"}:
        return False
    # Legacy exports use values such as "Unknown" for optional booleans.
    # Treat those as missing so the row remains editable instead of discarding it.
    return None


def _json_value(value: str) -> Any:
    if not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        try:
            return float(value) if "." in value else int(value)
        except ValueError:
            return value


def _skills(row: dict[str, str]) -> list[str]:
    raw = _value(row, "skills_array", "skills", "skills_or_requirements")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]


def _date(row: dict[str, str]) -> datetime | None:
    raw = _value(row, "posted_at", "scraped_at")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.strptime(raw, "%d-%m-%Y")
    return parsed.replace(tzinfo=parsed.tzinfo or UTC)


def _incoming(row: dict[str, str]) -> IncomingJob:
    salary_min = _number(row, "salary_min")
    salary_max = _number(row, "salary_max")
    apply_url = _value(row, "apply_url", "applyUrl")
    if not apply_url:
        identity = {
            "company": _value(row, "company_name", "companyName"),
            "role": _value(row, "role_title", "roleTitle"),
            "row": _value(row, "row_id"),
        }
        apply_url = f"https://training.invalid/import/{stable_hash(identity)[:24]}"
    return IncomingJob(
        company_name=_value(row, "company_name", "companyName"),
        role_title=_value(row, "role_title", "roleTitle"),
        role_family=_value(row, "role_family", "role_family_standard"),
        seniority=_value(row, "seniority", "seniority_standard"),
        location=_value(row, "location", "location_bucket"),
        work_mode=_value(row, "work_mode", "work_mode_standard"),
        employment_type=_value(row, "employment_type", "employment_type_standard"),
        description=_value(row, "description", "enhanced_context_text"),
        skills=_skills(row),
        experience_min_years=_number(row, "experience_min_years"),
        experience_max_years=_number(row, "experience_max_years"),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=_value(row, "salary_currency")
        or ("INR" if salary_min or salary_max else None),
        salary_period=_value(row, "salary_period", "salaryPeriod")
        or ("YEARLY" if salary_min is not None or salary_max is not None else None),
        posted_at=_date(row),
        can_apply_now=_boolean(_value(row, "can_apply_now", "canApplyNow")),
        apply_url=apply_url,
    )


def _annotation(row: dict[str, str]) -> AnnotationInput | None:
    values = {
        "apply_label": _boolean(_value(row, "apply_label", "applied")),
        "role_title_fit": _number(row, "role_title_fit", "role_title_preference_score"),
        "role_family_fit": _number(
            row, "role_family_fit", "role_family_preference_score"
        ),
        "seniority_fit": _number(row, "seniority_fit", "seniority_profile_fit_score"),
        "location_fit": _number(row, "location_fit", "location_profile_fit_score"),
        "work_mode_fit": _number(row, "work_mode_fit", "work_mode_fit_score"),
        "experience_fit": _number(
            row, "experience_fit", "experience_profile_fit_score"
        ),
        "skills_fit": _number(row, "skills_fit", "skills_profile_fit_score"),
        "salary_fit": _number(row, "salary_fit", "salary_profile_fit_score"),
        "overall_preference": _number(
            row, "overall_preference", "overall_preference_score"
        ),
    }
    supplied = {key: value for key, value in values.items() if value is not None}
    return AnnotationInput(**supplied) if supplied else None


def _complete(annotation: AnnotationInput | JobAnnotation | None) -> bool:
    return annotation is not None and all(
        getattr(annotation, field) is not None for field in ANNOTATION_FIELDS
    )


@router.post(
    "/training-data/import-csv",
    response_model=CsvTrainingImportResponse,
    status_code=201,
)
async def import_training_csv(
    user: CurrentUser,
    session: DatabaseSession,
    file: Annotated[UploadFile, File(description="UTF-8 CSV with job columns")],
) -> CsvTrainingImportResponse:
    context = await require_group_owner(session, user.id)
    member_id = context.membership.id
    if not (file.filename or "").casefold().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Upload a .csv file.")
    try:
        text = (await file.read()).decode("utf-8-sig")
        rows = list(csv.DictReader(StringIO(text)))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise HTTPException(
            status_code=422, detail="CSV must be valid UTF-8 with a header row."
        ) from exc
    if not rows:
        raise HTTPException(status_code=422, detail="CSV contains no data rows.")
    content_hash = stable_hash({"source": "csv-training-import", "rows": rows})
    frontier = "enhanced_title_skill_text" in rows[0]
    replay = await session.scalar(
        select(Batch).where(Batch.content_hash == content_hash)
    )
    if replay:
        count = (
            await session.scalar(
                select(func.count())
                .select_from(TrainingExample)
                .where(TrainingExample.batch_id == replay.id)
            )
            or 0
        )
        return CsvTrainingImportResponse(
            batch_id=replay.id,
            received_count=replay.received_count,
            imported_count=replay.job_count,
            duplicate_count=replay.duplicate_count,
            invalid_count=replay.received_count - replay.valid_count,
            training_example_count=count,
            feature_schema_version=replay.schema_version,
            replayed=True,
            validation_report=replay.validation_report or [],
        )
    profile = await session.scalar(
        select(ProfileVersion).where(ProfileVersion.active.is_(True))
    )
    if profile is None:
        raise HTTPException(
            status_code=409, detail="Activate a profile before importing training data."
        )

    parsed: list[tuple[dict[str, Any], dict[str, str], AnnotationInput | None]] = []
    issues: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        try:
            cleaned = clean_job(_incoming(row))
            if frontier:
                cleaned["dedupe_key"] = stable_hash(
                    {
                        "import": content_hash,
                        "row": index,
                        "base": cleaned["dedupe_key"],
                    }
                )
                cleaned["code"] = make_code(
                    cleaned["company_name"],
                    cleaned["role_title"],
                    cleaned["dedupe_key"],
                )
            parsed.append((cleaned, row, _annotation(row)))
        except (ValueError, TypeError, ValidationError) as exc:
            issues.append({"row": index + 2, "message": str(exc)[:500]})
    company_keys = {item[0]["company_key"] for item in parsed}
    urls = {item[0]["apply_url"] for item in parsed}
    candidates = (
        list(
            (
                await session.scalars(
                    select(Job).where(
                        or_(Job.company_key.in_(company_keys), Job.apply_url.in_(urls))
                    )
                )
            ).all()
        )
        if parsed and not frontier
        else []
    )
    if frontier:
        accepted, duplicates = [item[0] for item in parsed], 0
    else:
        accepted, duplicates = remove_duplicates(
            (item[0] for item in parsed), candidates
        )
    if not accepted:
        raise HTTPException(
            status_code=422,
            detail="No valid unique jobs remain after validation and deduplication.",
        )
    source_by_key = {item[0]["dedupe_key"]: item for item in parsed}
    schema_version = "jedi-frontier-v1" if frontier else "prepared-job-v2"
    batch = Batch(
        id=new_id(),
        external_batch_id=f"csv-{content_hash[:20]}",
        content_hash=content_hash,
        schema_version=schema_version,
        prompt_version="manual-csv-import",
        generated_at=datetime.now(UTC),
        raw_envelope={"filename": file.filename, "rows": rows},
        status="NORMALIZED",
        received_count=len(rows),
        valid_count=len(parsed),
        duplicate_count=duplicates,
        job_count=len(accepted),
        validation_report=issues,
    )
    session.add(batch)
    training_count = 0
    for cleaned in accepted:
        _, row, annotation_input = source_by_key[cleaned["dedupe_key"]]
        job = Job(id=new_id(), batch_id=batch.id, **cleaned)
        session.add(job)
        if frontier:
            payload = {
                key: _json_value(value)
                for key, value in row.items()
                if key not in FRONTIER_EXCLUDED
            }
            payload["_evaluationGroup"] = (
                row.get("near_duplicate_key") or cleaned["dedupe_key"]
            )
        else:
            payload = prepare_job(
                job, profile, feature_reference_at=batch.generated_at
            ).model_dump(mode="json", by_alias=True)
        payload_hash = stable_hash(payload)
        session.add(
            PreparedJob(
                job_id=job.id,
                profile_version_id=profile.id,
                feature_schema_version=schema_version,
                payload_hash=payload_hash,
                payload=payload,
            )
        )
        if annotation_input:
            values = {
                field: getattr(annotation_input, field) for field in ANNOTATION_FIELDS
            }
            session.add(
                JobAnnotation(
                    group_member_id=member_id,
                    job_id=job.id,
                    **values,
                )
            )
            if _complete(annotation_input):
                session.add(
                    TrainingExample(
                        job_id=job.id,
                        batch_id=batch.id,
                        profile_version_id=profile.id,
                        feature_schema_version=schema_version,
                        payload_hash=payload_hash,
                        feature_payload=payload,
                        annotated_by_group_member_id=member_id,
                        **values,
                    )
                )
                training_count += 1
    await session.commit()
    return CsvTrainingImportResponse(
        batch_id=batch.id,
        received_count=len(rows),
        imported_count=len(accepted),
        duplicate_count=duplicates,
        invalid_count=len(issues),
        training_example_count=training_count,
        feature_schema_version=schema_version,
        replayed=False,
        validation_report=issues,
    )


@router.get(
    "/batches/{batch_id}/annotation-editor", response_model=AnnotationEditorResponse
)
async def annotation_editor(
    batch_id: str, user: CurrentUser, session: DatabaseSession
) -> AnnotationEditorResponse:
    context = await require_group_context(session, user.id)
    member_id = context.membership.id
    batch = await get_batch_or_404(session, batch_id)
    result = (
        await session.execute(
            select(Job, JobState, JobAnnotation)
            .outerjoin(
                JobState,
                and_(
                    JobState.job_id == Job.id,
                    JobState.group_member_id == member_id,
                ),
            )
            .outerjoin(
                JobAnnotation,
                and_(
                    JobAnnotation.job_id == Job.id,
                    JobAnnotation.group_member_id == member_id,
                ),
            )
            .where(Job.batch_id == batch_id)
            .order_by(Job.company_name, Job.role_title)
        )
    ).all()
    prepared_ids = set(
        (
            await session.scalars(
                select(PreparedJob.job_id).join(Job).where(Job.batch_id == batch_id)
            )
        ).all()
    )
    training_ids = set(
        (
            await session.scalars(
                select(TrainingExample.job_id).where(
                    TrainingExample.batch_id == batch_id
                )
            )
        ).all()
    )
    rows = [
        AnnotationEditorRow(
            job_id=job.id,
            code=job.code,
            company_name=job.company_name,
            role_title=job.role_title,
            role_family=job.role_family,
            seniority=job.seniority,
            location=job.location,
            work_mode=job.work_mode,
            employment_type=job.employment_type,
            apply_url=job.apply_url,
            relevance_label=state.relevance_label if state else None,
            **{
                field: getattr(annotation, field) if annotation else None
                for field in ANNOTATION_FIELDS
            },
            complete=_complete(annotation),
            prepared=job.id in prepared_ids,
            in_training=job.id in training_ids,
        )
        for job, state, annotation in result
    ]
    return AnnotationEditorResponse(
        batch=batch_summary(batch),
        rows=rows,
        complete_count=sum(row.complete for row in rows),
        prepared_count=len(prepared_ids),
        training_count=len(training_ids),
    )
