"""Member-private job preview and draft endpoints."""

from datetime import UTC
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.database import JobDraft, get_session
from backend.schemas.job_intake import (
    JobDraftDetail,
    JobDraftSummary,
    JobPreview,
    LinkedJobPreview,
    LinkJobRequest,
    PasteJobRequest,
    SaveJobDraft,
)
from backend.services.group_access import require_group_context
from backend.services.job_intake import preview_job
from backend.services.job_links import JobLinkError, parse_job_link, preview_link
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
    )


def draft_changed() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "JOB_DRAFT_CHANGED",
            "message": "This draft changed elsewhere. Reopen it before editing.",
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


@router.get("/{draft_id}", response_model=JobDraftDetail)
async def get_draft(
    draft_id: UUID, user: CurrentUser, session: DatabaseSession
) -> JobDraftDetail:
    context = await require_group_context(session, user.id)
    row = await session.get(JobDraft, (context.membership.id, str(draft_id)))
    if row is None:
        raise HTTPException(404, "Job draft not found.")
    return draft_detail(row)


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
