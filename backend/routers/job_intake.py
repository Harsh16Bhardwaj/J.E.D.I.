"""Member-private job preview and draft endpoints."""

from datetime import UTC
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, null, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import JobDraft, ResumeEvidenceRecord, get_session, utc_now
from backend.schemas.job_intake import (
    DraftApplicationEvent,
    DraftApplicationItem,
    DraftApplicationMove,
    DraftApplicationState,
    DraftFitReport,
    DraftFitSnapshot,
    JobDraftDetail,
    JobDraftSummary,
    JobPreview,
    LinkedJobPreview,
    LinkJobRequest,
    PasteJobRequest,
    SaveDraftFitSnapshot,
    SaveJobDraft,
)
from backend.schemas.learning import ResumeEvidence
from backend.schemas.product import ApplicationStatus
from backend.services.application_moves import validate_application_move
from backend.services.group_access import require_group_context
from backend.services.job_fit import compare_draft
from backend.services.job_intake import preview_job
from backend.services.job_links import JobLinkError, parse_job_link, preview_link
from backend.services.product import stable_hash
from backend.services.skill_vocabulary import canonical_skill, skill_key

DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
MAX_DRAFTS = 50


router = APIRouter(prefix="/api/job-drafts", tags=["job intake"])


def draft_detail(row: JobDraft) -> JobDraftDetail:
    preview = row.preview
    if "requirements" not in preview:
        preview = {
            **preview,
            "requirements": preview_job(row.description).requirements,
        }
    return JobDraftDetail(
        **preview,
        id=row.id,
        description=row.description,
        revision=row.revision,
        updated_at=row.updated_at.replace(tzinfo=UTC),
        tracked_application=row.application is not None,
    )


def draft_changed() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "JOB_DRAFT_CHANGED",
            "message": "This draft changed elsewhere. Reopen it to continue.",
        },
    )


@router.post("/preview", response_model=JobPreview)
async def preview_paste(
    body: PasteJobRequest, user: CurrentUser, session: DatabaseSession
) -> JobPreview:
    await require_group_context(session, user.id)
    return preview_job(body.description)


def job_link_http_error(error: JobLinkError) -> HTTPException:
    return HTTPException(
        error.status, detail={"code": error.code, "message": str(error)}
    )


@router.post("/preview-url", response_model=LinkedJobPreview)
async def preview_url(
    body: LinkJobRequest, user: CurrentUser, session: DatabaseSession
) -> LinkedJobPreview:
    await require_group_context(session, user.id)
    await session.rollback()
    try:
        return await preview_link(body.url)
    except JobLinkError as exc:
        raise job_link_http_error(exc) from exc


@router.get("", response_model=list[JobDraftSummary])
async def list_drafts(
    user: CurrentUser, session: DatabaseSession
) -> list[JobDraftSummary]:
    context = await require_group_context(session, user.id)
    rows = await session.execute(
        select(JobDraft.id, JobDraft.preview, JobDraft.updated_at)
        .where(JobDraft.group_member_id == context.membership.id)
        .order_by(JobDraft.updated_at.desc(), JobDraft.id)
        .limit(MAX_DRAFTS)
    )
    return [
        JobDraftSummary(
            id=row.id,
            title=row.preview["fields"]["title"],
            employer=row.preview["fields"]["employer"],
            updated_at=row.updated_at.replace(tzinfo=UTC),
        )
        for row in rows
    ]


@router.get("/applications", response_model=list[DraftApplicationItem])
async def list_draft_applications(
    user: CurrentUser, session: DatabaseSession
) -> list[DraftApplicationItem]:
    context = await require_group_context(session, user.id)
    rows = await session.scalars(
        select(JobDraft)
        .where(
            JobDraft.group_member_id == context.membership.id,
            JobDraft.application.is_not(None),
        )
        .order_by(JobDraft.updated_at.desc(), JobDraft.id)
        .limit(MAX_DRAFTS)
    )
    return [
        DraftApplicationItem(
            draft_id=row.id,
            title=row.preview["fields"]["title"],
            employer=row.preview["fields"]["employer"],
            application=DraftApplicationState.model_validate(
                {
                    **row.application,
                    "events": row.application["events"][-10:],
                }
            ),
        )
        for row in rows
        if row.application
    ]


async def lock_application_draft(
    session: AsyncSession, user_id: str, draft_id: UUID
) -> JobDraft:
    context = await require_group_context(session, user_id)
    row = await session.get(
        JobDraft, (context.membership.id, str(draft_id)), with_for_update=True
    )
    if row is None:
        raise HTTPException(404, "Job draft not found.")
    return row


@router.post("/{draft_id}/application", response_model=DraftApplicationState)
async def start_draft_application(
    draft_id: UUID, user: CurrentUser, session: DatabaseSession
) -> DraftApplicationState:
    row = await lock_application_draft(session, user.id, draft_id)
    if row.application:
        return DraftApplicationState.model_validate(row.application)
    now = utc_now()
    state = DraftApplicationState(
        status=ApplicationStatus.PREPARING,
        revision=1,
        updated_at=now,
        events=[
            DraftApplicationEvent(
                request_id=uuid4(),
                revision=1,
                from_status=ApplicationStatus.NOT_STARTED,
                to_status=ApplicationStatus.PREPARING,
                correction=False,
                created_at=now,
            )
        ],
    )
    row.application = state.model_dump(mode="json")
    await session.commit()
    return state


@router.patch("/{draft_id}/application", response_model=DraftApplicationState)
async def move_draft_application(
    draft_id: UUID,
    body: DraftApplicationMove,
    user: CurrentUser,
    session: DatabaseSession,
) -> DraftApplicationState:
    row = await lock_application_draft(session, user.id, draft_id)
    if not row.application:
        raise HTTPException(404, "Start tracking this draft first.")
    state = DraftApplicationState.model_validate(row.application)
    notes = body.notes.strip() if body.notes and body.notes.strip() else None
    for event in state.events:
        if event.request_id == body.request_id:
            if (
                event.revision != body.expected_revision + 1
                or event.to_status != body.status
                or event.correction != body.correction
                or event.notes != notes
            ):
                raise HTTPException(409, "This move ID has already been used.")
            return state
    if state.revision != body.expected_revision:
        raise HTTPException(409, "Application changed. Refresh and reopen it.")
    validate_application_move(
        state.status, body.status, correction=body.correction, notes=notes
    )
    now = utc_now()
    state.revision += 1
    state.events.append(
        DraftApplicationEvent(
            request_id=body.request_id,
            revision=state.revision,
            from_status=state.status,
            to_status=body.status,
            correction=body.correction,
            notes=notes,
            created_at=now,
        )
    )
    state.status = body.status
    state.updated_at = now
    row.application = state.model_dump(mode="json")
    await session.commit()
    return state


@router.get("/{draft_id}", response_model=JobDraftDetail)
async def get_draft(
    draft_id: UUID, user: CurrentUser, session: DatabaseSession
) -> JobDraftDetail:
    context = await require_group_context(session, user.id)
    row = await session.get(JobDraft, (context.membership.id, str(draft_id)))
    if row is None:
        raise HTTPException(404, "Job draft not found.")
    return draft_detail(row)


async def owned_draft(session: AsyncSession, owner: str, draft_id: UUID) -> JobDraft:
    draft = await session.get(JobDraft, (owner, str(draft_id)))
    if draft is None:
        raise HTTPException(404, "Job draft not found.")
    return draft


async def draft_resume(
    session: AsyncSession, draft: JobDraft
) -> ResumeEvidenceRecord | None:
    return await session.scalar(
        select(ResumeEvidenceRecord).where(
            ResumeEvidenceRecord.group_member_id == draft.group_member_id
        )
    )


def versioned_fit(
    draft: JobDraft, evidence: ResumeEvidenceRecord | None
) -> tuple[DraftFitReport, dict]:
    detail = draft_detail(draft)
    resume = ResumeEvidence.model_validate(evidence.evidence) if evidence else None
    report = compare_draft(detail, resume)
    inputs = {
        "job": detail.model_dump(
            mode="json", include={"description", "fields", "requirements", "source_url"}
        ),
        "resume": resume.model_dump(
            mode="json",
            include={"text", "explicit_skills", "inferred_skills", "experience_years"},
        )
        if resume
        else None,
    }
    if report.assessment:
        report.input_version = stable_hash(
            {
                "inputs": inputs,
                "draftRevision": draft.revision,
                "scorer": report.assessment.version,
            }
        )
    return report, inputs


@router.get("/{draft_id}/skill-fit", response_model=DraftFitReport)
async def draft_skill_fit(
    draft_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
    revision: Annotated[int, Query(ge=1)],
) -> DraftFitReport:
    context = await require_group_context(session, user.id)
    draft = await owned_draft(session, context.membership.id, draft_id)
    if draft.revision != revision:
        raise draft_changed()
    report, _ = versioned_fit(draft, await draft_resume(session, draft))
    return report


@router.get("/{draft_id}/skill-fit/saved", response_model=DraftFitSnapshot | None)
async def get_fit_snapshot(
    draft_id: UUID, user: CurrentUser, session: DatabaseSession
) -> DraftFitSnapshot | None:
    context = await require_group_context(session, user.id)
    draft = await owned_draft(session, context.membership.id, draft_id)
    return (
        DraftFitSnapshot.model_validate(draft.fit_snapshot)
        if draft.fit_snapshot
        else None
    )


@router.put("/{draft_id}/skill-fit/saved", response_model=DraftFitSnapshot)
async def save_fit_snapshot(
    draft_id: UUID,
    body: SaveDraftFitSnapshot,
    user: CurrentUser,
    session: DatabaseSession,
) -> DraftFitSnapshot:
    context = await require_group_context(session, user.id, lock=True)
    draft = await owned_draft(session, context.membership.id, draft_id)
    saved = (
        DraftFitSnapshot.model_validate(draft.fit_snapshot)
        if draft.fit_snapshot
        else None
    )
    saved_version = saved.report.input_version if saved else None
    if (
        saved
        and saved_version == body.input_version
        and saved.draft_revision == body.draft_revision
    ):
        return saved
    if saved_version != body.expected_saved_version:
        raise HTTPException(409, "The saved comparison changed. Reopen it to continue.")
    if draft.revision != body.draft_revision:
        raise draft_changed()
    evidence = await draft_resume(session, draft)
    report, inputs = versioned_fit(draft, evidence)
    if evidence is None or body.input_version != report.input_version:
        raise HTTPException(
            409, "Resume evidence or the scorer changed. Compare again before saving."
        )
    snapshot = DraftFitSnapshot(
        draft_revision=draft.revision,
        resume_reviewed_at=evidence.updated_at.replace(tzinfo=UTC),
        saved_at=utc_now(),
        title=draft.preview["fields"]["title"],
        employer=draft.preview["fields"]["employer"],
        report=report,
    )
    draft.fit_snapshot = {**snapshot.model_dump(mode="json"), "inputs": inputs}
    await session.commit()
    return snapshot


@router.delete("/{draft_id}/skill-fit/saved", status_code=204)
async def delete_fit_snapshot(
    draft_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
    input_version: Annotated[
        str, Query(alias="inputVersion", pattern=r"^[0-9a-f]{64}$")
    ],
) -> None:
    context = await require_group_context(session, user.id, lock=True)
    draft = await owned_draft(session, context.membership.id, draft_id)
    if draft.fit_snapshot:
        saved = DraftFitSnapshot.model_validate(draft.fit_snapshot)
        if saved.report.input_version != input_version:
            raise HTTPException(
                409, "The saved comparison changed. Reopen it to continue."
            )
        await session.execute(
            update(JobDraft)
            .where(
                JobDraft.group_member_id == draft.group_member_id,
                JobDraft.id == draft.id,
            )
            .values(fit_snapshot=null(), updated_at=JobDraft.updated_at)
        )
        await session.commit()


@router.put("/{draft_id}", response_model=JobDraftDetail)
async def save_draft(
    draft_id: UUID, body: SaveJobDraft, user: CurrentUser, session: DatabaseSession
) -> JobDraftDetail:
    context = await require_group_context(session, user.id, lock=True)
    owner = context.membership.id
    row = await session.get(JobDraft, (owner, str(draft_id)))
    source_url = body.source_url or None
    if source_url:
        try:
            source_url = parse_job_link(source_url).url
        except JobLinkError as exc:
            raise job_link_http_error(exc) from exc
    elif (
        row
        and row.description == body.description
        and "source_url" not in body.model_fields_set
    ):
        source_url = row.preview.get("source_url")
    fields = body.fields.model_dump(mode="json")
    for field in ("required_skills", "preferred_skills", "mentioned_skills"):
        canonical = (canonical_skill(name) for name in fields[field])
        fields[field] = list({skill_key(name): name for name in canonical}.values())
    if row is not None:
        if (
            row.description == body.description
            and row.preview["fields"] == fields
            and row.preview.get("source_url") == source_url
        ):
            return draft_detail(row)
        if row.revision != body.revision:
            raise draft_changed()
    else:
        if body.revision != 0:
            raise HTTPException(404, "Job draft not found.")
        count = await session.scalar(
            select(func.count())
            .select_from(JobDraft)
            .where(JobDraft.group_member_id == owner)
        )
        if count is not None and count >= MAX_DRAFTS:
            raise HTTPException(409, "Delete an existing draft before saving another.")
        row = JobDraft(id=str(draft_id), group_member_id=owner, revision=0)
        session.add(row)
    if row.description != body.description or "requirements" not in row.preview:
        extracted = preview_job(body.description).model_dump(mode="json")
    else:
        extracted = row.preview
    row.description = body.description
    row.preview = {**extracted, "fields": fields, "source_url": source_url}
    row.revision += 1
    await session.commit()
    await session.refresh(row)
    return draft_detail(row)


@router.delete("/{draft_id}", status_code=204)
async def delete_draft(
    draft_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
    revision: Annotated[int, Query(ge=1)],
) -> None:
    context = await require_group_context(session, user.id, lock=True)
    row = await session.get(JobDraft, (context.membership.id, str(draft_id)))
    if row is None:
        return
    if row.revision != revision:
        raise draft_changed()
    await session.delete(row)
    await session.commit()
