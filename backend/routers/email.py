"""Manual digest controls, safe delivery history, and the Vercel cron target."""

from datetime import UTC, datetime
from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.auth import CurrentUser
from backend.config import get_settings
from backend.database import (
    Batch,
    EmailConfiguration,
    EmailDelivery,
    EmailRecipient,
    ProcessingRun,
    get_session,
)
from backend.routers.batches import get_batch_or_404
from backend.schemas.email_management import (
    EmailRecipientCreate,
    EmailRecipientResponse,
    EmailRecipientUpdate,
    EmailRecipientWriteResponse,
    EmailSettingsResponse,
    EmailSettingsUpdate,
    MailEventEnqueueResponse,
    ManualEmailDispatchResponse,
    normalize_email,
)
from backend.schemas.product import EmailDeliverySummary, EmailDigestResponse
from backend.services.email import (
    EmailTransportDependency,
    delivery_summary,
    enqueue_configured_mail_events,
    enqueue_mail_events,
    queue_and_send_digest,
)
from backend.services.group_access import require_group_owner
from backend.services.mail_events import run_mail_event_worker

router = APIRouter(tags=["email"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
RECIPIENT_LIMIT = 50
CONFIGURATION_ID = "default"


def transport_configured() -> bool:
    settings = get_settings()
    return bool(settings.gmail_smtp_user and settings.gmail_smtp_app_password)


async def configuration(
    session: AsyncSession,
    *,
    lock: bool = False,
) -> EmailConfiguration:
    statement = select(EmailConfiguration).where(
        EmailConfiguration.id == CONFIGURATION_ID
    )
    if lock:
        statement = statement.with_for_update()
    item = await session.scalar(statement)
    if item is None:
        item = EmailConfiguration(id=CONFIGURATION_ID)
        session.add(item)
        await session.flush()
    return item


async def active_recipient_count(session: AsyncSession) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(EmailRecipient)
            .where(
                EmailRecipient.active.is_(True),
                EmailRecipient.deleted_at.is_(None),
            )
        )
        or 0
    )


def recipient_response(item: EmailRecipient) -> EmailRecipientResponse:
    return EmailRecipientResponse(
        id=item.id,
        email=item.email,
        display_name=item.display_name,
        group_member_id=item.group_member_id,
        active=item.active,
        deleted_at=item.deleted_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def settings_response(
    session: AsyncSession,
    item: EmailConfiguration,
) -> EmailSettingsResponse:
    return EmailSettingsResponse(
        enabled=item.enabled,
        sender_name=item.sender_name,
        send_after_ranking=item.send_after_ranking,
        transport_configured=transport_configured(),
        active_recipient_count=await active_recipient_count(session),
    )


async def recipient_or_404(
    session: AsyncSession,
    recipient_id: str,
) -> EmailRecipient:
    item = await session.get(EmailRecipient, recipient_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Email recipient not found.")
    return item


async def enforce_recipient_capacity(session: AsyncSession) -> None:
    if await active_recipient_count(session) >= RECIPIENT_LIMIT:
        raise HTTPException(
            status_code=409,
            detail="The newsletter already has 50 active recipients.",
        )


@router.get("/api/email/settings", response_model=EmailSettingsResponse)
async def get_email_settings(
    _user: CurrentUser,
    session: DatabaseSession,
) -> EmailSettingsResponse:
    return await settings_response(session, await configuration(session))


@router.patch("/api/email/settings", response_model=EmailSettingsResponse)
async def update_email_settings(
    body: EmailSettingsUpdate,
    _user: CurrentUser,
    session: DatabaseSession,
) -> EmailSettingsResponse:
    item = await configuration(session, lock=True)
    if body.enabled is True and not transport_configured():
        raise HTTPException(
            status_code=409,
            detail=(
                "Configure GMAIL_SMTP_USER and GMAIL_SMTP_APP_PASSWORD "
                "before enabling email."
            ),
        )
    if "enabled" in body.model_fields_set:
        item.enabled = bool(body.enabled)
    if "sender_name" in body.model_fields_set:
        item.sender_name = body.sender_name or item.sender_name
    if "send_after_ranking" in body.model_fields_set:
        item.send_after_ranking = bool(body.send_after_ranking)
    await session.commit()
    return await settings_response(session, item)


@router.post(
    "/api/email/manual-dispatch",
    response_model=ManualEmailDispatchResponse,
)
async def initialize_manual_email_dispatch(
    user: CurrentUser,
    session: DatabaseSession,
    transport: EmailTransportDependency,
) -> ManualEmailDispatchResponse:
    """Queue and immediately process the latest successful personalized run."""
    if not transport_configured():
        raise HTTPException(status_code=409, detail="Configure Gmail SMTP first.")
    context = await require_group_owner(session, user.id)
    latest = (
        await session.execute(
            select(ProcessingRun, Batch)
            .join(Batch, ProcessingRun.batch_id == Batch.id)
            .where(
                ProcessingRun.stage == "ranking",
                ProcessingRun.status == "SUCCEEDED",
            )
            .order_by(
                ProcessingRun.completed_at.desc(),
                ProcessingRun.created_at.desc(),
            )
            .limit(1)
        )
    ).first()
    if latest is None:
        return ManualEmailDispatchResponse(
            status="not_ready",
            ready=False,
            message="Rank a batch successfully before sending email.",
        )
    run, batch = latest
    queued = await enqueue_configured_mail_events(
        session,
        batch,
        run,
        group_id=context.group.id,
        force=True,
    )
    if queued is None or queued.eligible_recipient_count == 0:
        return ManualEmailDispatchResponse(
            status="not_ready",
            ready=False,
            message="No active onboarded member recipients are eligible.",
        )
    if session.bind is None:
        raise HTTPException(status_code=503, detail="Database worker is unavailable.")
    session_factory = async_sessionmaker(session.bind, expire_on_commit=False)
    result = await run_mail_event_worker(session_factory, transport)
    return ManualEmailDispatchResponse(
        status="processed" if result.claimed else "empty",
        ready=True,
        message=(
            f"Sent {result.sent}; failed {result.failed}; "
            f"remaining {result.remaining}."
        ),
        claimed=result.claimed,
        sent=result.sent,
        failed=result.failed,
        remaining=result.remaining,
    )


@router.post(
    "/api/batches/{batch_id}/mail-events",
    response_model=MailEventEnqueueResponse,
)
async def create_batch_mail_events(
    batch_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> MailEventEnqueueResponse:
    """Queue one personalized event for every eligible member recipient."""
    context = await require_group_owner(session, user.id)
    batch = await get_batch_or_404(session, batch_id)
    if batch.status != "RANKED":
        raise HTTPException(
            status_code=409,
            detail="Rank this batch before creating mail events.",
        )
    run = await session.scalar(
        select(ProcessingRun)
        .where(
            ProcessingRun.batch_id == batch_id,
            ProcessingRun.stage == "ranking",
            ProcessingRun.status == "SUCCEEDED",
        )
        .order_by(
            ProcessingRun.completed_at.desc(),
            ProcessingRun.created_at.desc(),
        )
    )
    if run is None:
        raise HTTPException(
            status_code=409,
            detail="No successful ranking run exists for this batch.",
        )
    result = await enqueue_mail_events(
        session,
        batch,
        run,
        group_id=context.group.id,
    )
    await session.commit()
    return MailEventEnqueueResponse(**result.__dict__)


@router.get(
    "/api/email/recipients",
    response_model=list[EmailRecipientResponse],
)
async def list_email_recipients(
    _user: CurrentUser,
    session: DatabaseSession,
    active: bool | None = None,
    include_deleted: Annotated[bool, Query(alias="includeDeleted")] = False,
) -> list[EmailRecipientResponse]:
    statement = select(EmailRecipient).order_by(
        EmailRecipient.active.desc(),
        EmailRecipient.created_at.desc(),
    )
    if active is not None:
        statement = statement.where(EmailRecipient.active.is_(active))
    if not include_deleted:
        statement = statement.where(EmailRecipient.deleted_at.is_(None))
    items = (await session.scalars(statement)).all()
    return [recipient_response(item) for item in items]


@router.post(
    "/api/email/recipients",
    response_model=EmailRecipientWriteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_email_recipient(
    body: EmailRecipientCreate,
    response: Response,
    _user: CurrentUser,
    session: DatabaseSession,
) -> EmailRecipientWriteResponse:
    await configuration(session, lock=True)
    normalized = normalize_email(body.email)
    existing = await session.scalar(
        select(EmailRecipient).where(EmailRecipient.email_normalized == normalized)
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        if existing.active and existing.deleted_at is None:
            if body.display_name != existing.display_name:
                raise HTTPException(
                    status_code=409,
                    detail="Recipient already exists; use PATCH to edit it.",
                )
            return EmailRecipientWriteResponse(
                **recipient_response(existing).model_dump(),
                replayed=True,
                reactivated=False,
            )
        await enforce_recipient_capacity(session)
        existing.email = body.email
        existing.display_name = body.display_name
        existing.active = True
        existing.deleted_at = None
        await session.commit()
        return EmailRecipientWriteResponse(
            **recipient_response(existing).model_dump(),
            replayed=False,
            reactivated=True,
        )

    await enforce_recipient_capacity(session)
    item = EmailRecipient(
        email=body.email,
        email_normalized=normalized,
        display_name=body.display_name,
    )
    session.add(item)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Recipient conflicted with a concurrent request.",
        ) from exc
    return EmailRecipientWriteResponse(
        **recipient_response(item).model_dump(),
        replayed=False,
        reactivated=False,
    )


@router.get(
    "/api/email/recipients/{recipient_id}",
    response_model=EmailRecipientResponse,
)
async def get_email_recipient(
    recipient_id: str,
    _user: CurrentUser,
    session: DatabaseSession,
) -> EmailRecipientResponse:
    return recipient_response(await recipient_or_404(session, recipient_id))


@router.patch(
    "/api/email/recipients/{recipient_id}",
    response_model=EmailRecipientResponse,
)
async def update_email_recipient(
    recipient_id: str,
    body: EmailRecipientUpdate,
    _user: CurrentUser,
    session: DatabaseSession,
) -> EmailRecipientResponse:
    await configuration(session, lock=True)
    item = await recipient_or_404(session, recipient_id)
    activating = body.active is True and (
        not item.active or item.deleted_at is not None
    )
    if activating:
        await enforce_recipient_capacity(session)
    if "email" in body.model_fields_set and body.email is not None:
        normalized = normalize_email(body.email)
        conflict = await session.scalar(
            select(EmailRecipient).where(
                EmailRecipient.email_normalized == normalized,
                EmailRecipient.id != item.id,
            )
        )
        if conflict is not None:
            raise HTTPException(
                status_code=409,
                detail="Another recipient already uses this email address.",
            )
        item.email = body.email
        item.email_normalized = normalized
    if "display_name" in body.model_fields_set:
        item.display_name = body.display_name
    if "active" in body.model_fields_set:
        item.active = bool(body.active)
        if item.active:
            item.deleted_at = None
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Recipient update conflicted with another request.",
        ) from exc
    return recipient_response(item)


@router.delete(
    "/api/email/recipients/{recipient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_email_recipient(
    recipient_id: str,
    _user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    await configuration(session, lock=True)
    item = await recipient_or_404(session, recipient_id)
    item.active = False
    item.deleted_at = datetime.now(UTC)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/batches/{batch_id}/email-digest",
    response_model=EmailDigestResponse,
)
async def send_batch_digest(
    batch_id: str,
    _user: CurrentUser,
    session: DatabaseSession,
    transport: EmailTransportDependency,
) -> EmailDigestResponse:
    batch = await get_batch_or_404(session, batch_id)
    if batch.status != "RANKED":
        raise HTTPException(
            status_code=409,
            detail="Rank this batch before sending its digest.",
        )
    run = await session.scalar(
        select(ProcessingRun)
        .where(
            ProcessingRun.batch_id == batch_id,
            ProcessingRun.stage == "ranking",
            ProcessingRun.status == "SUCCEEDED",
        )
        .order_by(ProcessingRun.completed_at.desc())
    )
    if run is None:
        raise HTTPException(
            status_code=409,
            detail="No successful ranking run exists for this batch.",
        )
    delivery = await queue_and_send_digest(
        session,
        batch,
        run,
        transport,
        manual_retry=True,
    )
    return EmailDigestResponse(
        batch_id=batch_id,
        delivery=delivery_summary(delivery),
    )


@router.get(
    "/api/batches/{batch_id}/email-deliveries",
    response_model=list[EmailDeliverySummary],
)
async def list_email_deliveries(
    batch_id: str,
    _user: CurrentUser,
    session: DatabaseSession,
) -> list[EmailDeliverySummary]:
    await get_batch_or_404(session, batch_id)
    deliveries = (
        await session.scalars(
            select(EmailDelivery)
            .where(EmailDelivery.batch_id == batch_id)
            .order_by(EmailDelivery.created_at.desc())
        )
    ).all()
    return [delivery_summary(item) for item in deliveries if item is not None]


@router.get(
    "/internal/email-deliveries/run",
    response_model=ManualEmailDispatchResponse,
)
async def run_email_cron(
    session: DatabaseSession,
    transport: EmailTransportDependency,
    authorization: Annotated[str | None, Header()] = None,
) -> ManualEmailDispatchResponse:
    expected = get_settings().cron_secret
    supplied = authorization or ""
    valid = bool(expected) and compare_digest(
        supplied.encode(),
        f"Bearer {expected}".encode(),
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron authorization.",
        )
    if session.bind is None:
        raise HTTPException(status_code=503, detail="Database worker is unavailable.")
    session_factory = async_sessionmaker(session.bind, expire_on_commit=False)
    result = await run_mail_event_worker(session_factory, transport)
    return ManualEmailDispatchResponse(
        status="processed" if result.claimed else "empty",
        ready=True,
        message=(
            f"Sent {result.sent}; failed {result.failed}; "
            f"remaining {result.remaining}."
        ),
        claimed=result.claimed,
        sent=result.sent,
        failed=result.failed,
        remaining=result.remaining,
    )
