"""Manual digest controls, safe delivery history, and the Vercel cron target."""

from datetime import UTC, datetime
from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.auth import CurrentUser
from backend.config import get_settings
from backend.database import (
    Batch,
    EmailConfiguration,
    EmailDelivery,
    EmailDeliveryAttempt,
    EmailRecipient,
    GroupMember,
    MemberProfile,
    ProcessingRun,
    get_session,
)
from backend.routers.batches import get_batch_or_404
from backend.schemas.email_management import (
    EmailEventActionResponse,
    EmailEventAttemptResponse,
    EmailEventPage,
    EmailEventResponse,
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


def email_event_response(
    event: EmailDelivery,
    batch: Batch | None,
    run: ProcessingRun | None,
    attempts: list[EmailDeliveryAttempt] | None = None,
) -> EmailEventResponse:
    retryable_status = event.status in {"FAILED", "BLOCKED", "CANCELLED"}
    return EmailEventResponse(
        id=event.id,
        status=event.status,
        recipient=event.recipient,
        recipient_display_name=event.recipient_display_name,
        group_member_id=event.group_member_id,
        batch_id=event.batch_id,
        batch_name=batch.external_batch_id if batch else None,
        batch_display_name=batch.display_name if batch else None,
        ranking_run_id=event.ranking_run_id,
        model_version_id=run.model_version_id if run else None,
        attempts=event.attempts,
        retry_cycle=event.retry_cycle,
        retry_cycle_attempts=event.retry_cycle_attempts,
        personalized_job_count=len(event.personalized_jobs or []),
        error_code=event.error_code,
        last_error=event.last_error,
        next_attempt_at=event.next_attempt_at,
        sent_at=event.sent_at,
        created_at=event.created_at,
        updated_at=event.updated_at,
        can_send=(
            event.status in {"UNTOUCHED", "FAILED"}
            and event.retry_cycle_attempts < 4
        ),
        can_cancel=event.status in {"UNTOUCHED", "FAILED", "BLOCKED"},
        can_requeue=retryable_status and event.error_code != "SUPERSEDED_BY_RERANK",
        attempt_history=[
            EmailEventAttemptResponse(
                id=item.id,
                attempt_number=item.attempt_number,
                retry_cycle=item.retry_cycle,
                trigger=item.trigger,
                status=item.status,
                started_at=item.started_at,
                completed_at=item.completed_at,
                provider_message_id=item.provider_message_id,
                error_code=item.error_code,
                safe_error_message=item.safe_error_message,
            )
            for item in attempts or []
        ],
    )


async def owned_event_or_404(
    session: AsyncSession,
    event_id: str,
    group_id: str,
    *,
    lock: bool = False,
) -> tuple[EmailDelivery, Batch | None, ProcessingRun | None]:
    statement = (
        select(EmailDelivery, Batch, ProcessingRun)
        .join(GroupMember, GroupMember.id == EmailDelivery.group_member_id)
        .outerjoin(Batch, Batch.id == EmailDelivery.batch_id)
        .outerjoin(ProcessingRun, ProcessingRun.id == EmailDelivery.ranking_run_id)
        .where(EmailDelivery.id == event_id, GroupMember.group_id == group_id)
    )
    if lock:
        statement = statement.with_for_update()
    row = (await session.execute(statement)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Email event not found.")
    return row


async def event_action_response(
    session: AsyncSession,
    event_id: str,
    group_id: str,
    message: str,
) -> EmailEventActionResponse:
    event, batch, run = await owned_event_or_404(session, event_id, group_id)
    attempts = list(
        (
            await session.scalars(
                select(EmailDeliveryAttempt)
                .where(EmailDeliveryAttempt.email_delivery_id == event.id)
                .order_by(EmailDeliveryAttempt.started_at.desc())
            )
        ).all()
    )
    return EmailEventActionResponse(
        event=email_event_response(event, batch, run, attempts),
        message=message,
    )


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
            f"Sent {result.sent}; failed {result.failed}; remaining {result.remaining}."
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


@router.get("/api/email/events", response_model=EmailEventPage)
async def list_email_events(
    user: CurrentUser,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=10, le=100)] = 25,
    event_status: Annotated[str | None, Query(alias="status")] = None,
    batch_id: Annotated[str | None, Query(alias="batchId")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> EmailEventPage:
    """Return the owner-only, member-scoped delivery ledger."""
    context = await require_group_owner(session, user.id)
    base_filters = [GroupMember.group_id == context.group.id]
    filters = list(base_filters)
    if event_status:
        if event_status not in {
            "UNTOUCHED",
            "SENDING",
            "SENT",
            "FAILED",
            "BLOCKED",
            "CANCELLED",
        }:
            raise HTTPException(status_code=422, detail="Unknown email event status.")
        filters.append(EmailDelivery.status == event_status)
    if batch_id:
        filters.append(EmailDelivery.batch_id == batch_id)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                EmailDelivery.recipient.ilike(pattern),
                EmailDelivery.recipient_display_name.ilike(pattern),
                Batch.external_batch_id.ilike(pattern),
                Batch.display_name.ilike(pattern),
            )
        )
    count_statement = (
        select(func.count())
        .select_from(EmailDelivery)
        .join(GroupMember, GroupMember.id == EmailDelivery.group_member_id)
        .outerjoin(Batch, Batch.id == EmailDelivery.batch_id)
        .where(*filters)
    )
    total = int(await session.scalar(count_statement) or 0)
    rows = (
        await session.execute(
            select(EmailDelivery, Batch, ProcessingRun)
            .join(GroupMember, GroupMember.id == EmailDelivery.group_member_id)
            .outerjoin(Batch, Batch.id == EmailDelivery.batch_id)
            .outerjoin(ProcessingRun, ProcessingRun.id == EmailDelivery.ranking_run_id)
            .where(*filters)
            .order_by(EmailDelivery.created_at.desc(), EmailDelivery.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    event_ids = [event.id for event, _batch, _run in rows]
    attempts_by_event: dict[str, list[EmailDeliveryAttempt]] = {
        event_id: [] for event_id in event_ids
    }
    if event_ids:
        for attempt in (
            await session.scalars(
                select(EmailDeliveryAttempt)
                .where(EmailDeliveryAttempt.email_delivery_id.in_(event_ids))
                .order_by(EmailDeliveryAttempt.started_at.desc())
            )
        ).all():
            attempts_by_event[attempt.email_delivery_id].append(attempt)
    counts = {
        status_name: int(count)
        for status_name, count in (
            await session.execute(
                select(EmailDelivery.status, func.count())
                .join(GroupMember, GroupMember.id == EmailDelivery.group_member_id)
                .where(*base_filters)
                .group_by(EmailDelivery.status)
            )
        ).all()
    }
    return EmailEventPage(
        items=[
            email_event_response(event, batch, run, attempts_by_event[event.id])
            for event, batch, run in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=max(1, (total + page_size - 1) // page_size),
        status_counts=counts,
    )


@router.post(
    "/api/email/events/{event_id}/send", response_model=EmailEventActionResponse
)
async def send_email_event(
    event_id: str,
    user: CurrentUser,
    session: DatabaseSession,
    transport: EmailTransportDependency,
) -> EmailEventActionResponse:
    if not transport_configured():
        raise HTTPException(status_code=409, detail="Configure Gmail SMTP first.")
    context = await require_group_owner(session, user.id)
    event, _batch, _run = await owned_event_or_404(session, event_id, context.group.id)
    if event.status not in {"UNTOUCHED", "FAILED"}:
        raise HTTPException(
            status_code=409,
            detail="Only queued or failed events can be sent manually.",
        )
    if session.bind is None:
        raise HTTPException(status_code=503, detail="Database worker is unavailable.")
    target_event_id = event.id
    owner_group_id = context.group.id
    actor_member_id = context.membership.id
    worker = await run_mail_event_worker(
        async_sessionmaker(session.bind, expire_on_commit=False),
        transport,
        limit=1,
        concurrency=1,
        event_ids=[target_event_id],
        trigger="MANUAL",
        requested_by_group_member_id=actor_member_id,
    )
    if worker.claimed != 1:
        raise HTTPException(
            status_code=409,
            detail="The event changed or must be requeued before another send.",
        )
    await session.rollback()
    return await event_action_response(
        session,
        target_event_id,
        owner_group_id,
        "Email sent." if worker.sent else "The send failed; review its safe error.",
    )


@router.post(
    "/api/email/events/{event_id}/cancel", response_model=EmailEventActionResponse
)
async def cancel_email_event(
    event_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> EmailEventActionResponse:
    context = await require_group_owner(session, user.id)
    event, _batch, _run = await owned_event_or_404(
        session, event_id, context.group.id, lock=True
    )
    if event.status in {"SENT", "SENDING"}:
        raise HTTPException(
            status_code=409, detail="This event can no longer be cancelled."
        )
    event.status = "CANCELLED"
    event.error_code = "MANUALLY_CANCELLED"
    event.last_error = "An owner cancelled this delivery."
    event.next_attempt_at = None
    await session.commit()
    return await event_action_response(
        session, event.id, context.group.id, "Event cancelled."
    )


@router.post(
    "/api/email/events/{event_id}/requeue", response_model=EmailEventActionResponse
)
async def requeue_email_event(
    event_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> EmailEventActionResponse:
    context = await require_group_owner(session, user.id)
    event, _batch, _run = await owned_event_or_404(
        session, event_id, context.group.id, lock=True
    )
    if (
        event.status in {"SENT", "SENDING"}
        or event.error_code == "SUPERSEDED_BY_RERANK"
    ):
        raise HTTPException(status_code=409, detail="This event cannot be requeued.")
    recipient = (
        await session.get(EmailRecipient, event.recipient_id)
        if event.recipient_id
        else None
    )
    profile = await session.scalar(
        select(MemberProfile).where(
            MemberProfile.group_member_id == event.group_member_id
        )
    )
    if recipient is None or not recipient.active or recipient.deleted_at is not None:
        event.status = "CANCELLED"
        event.error_code = "RECIPIENT_DISABLED"
        event.last_error = "Enable this member's recipient before requeueing."
        await session.commit()
        raise HTTPException(status_code=409, detail=event.last_error)
    if profile is None:
        event.status = "BLOCKED"
        event.error_code = "PROFILE_MISSING"
        event.last_error = "Complete this member's profile before requeueing."
        await session.commit()
        raise HTTPException(status_code=409, detail=event.last_error)
    event.status = "UNTOUCHED"
    event.retry_cycle += 1
    event.retry_cycle_attempts = 0
    event.error_code = None
    event.last_error = None
    event.lease_token = None
    event.lease_expires_at = None
    event.next_attempt_at = datetime.now(UTC)
    await session.commit()
    return await event_action_response(
        session, event.id, context.group.id, "Event requeued."
    )


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
    config = await configuration(session)
    if not config.enabled or not config.send_after_ranking:
        return ManualEmailDispatchResponse(
            status="empty",
            ready=False,
            message=(
                "Automatic email delivery is disabled; queued events were preserved."
            ),
        )
    if not transport_configured():
        return ManualEmailDispatchResponse(
            status="not_ready",
            ready=False,
            message="Gmail SMTP is not configured; queued events were preserved.",
        )
    if session.bind is None:
        raise HTTPException(status_code=503, detail="Database worker is unavailable.")
    session_factory = async_sessionmaker(session.bind, expire_on_commit=False)
    result = await run_mail_event_worker(session_factory, transport)
    return ManualEmailDispatchResponse(
        status="processed" if result.claimed else "empty",
        ready=True,
        message=(
            f"Sent {result.sent}; failed {result.failed}; remaining {result.remaining}."
        ),
        claimed=result.claimed,
        sent=result.sent,
        failed=result.failed,
        remaining=result.remaining,
    )
