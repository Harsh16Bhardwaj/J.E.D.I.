"""Idempotent top-ten digest rendering, leasing, and Gmail SMTP delivery."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from hashlib import sha256
from html import escape
from secrets import token_urlsafe
from typing import Annotated, Protocol

import aiosmtplib
from fastapi import Depends
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.database import (
    Batch,
    EmailConfiguration,
    EmailDelivery,
    EmailRecipient,
    GroupMember,
    Job,
    JobPrediction,
    MemberProfile,
    ProcessingRun,
    User,
)
from backend.schemas.email_management import normalize_email
from backend.schemas.product import EmailDeliverySummary

TEMPLATE_VERSION = "top-ten-v1"
PERSONALIZED_TEMPLATE_VERSION = "personalized-top-ten-v3"
DELIVERY_LEASE = timedelta(minutes=5)
RETRY_DELAYS = (timedelta(minutes=15), timedelta(hours=2), timedelta(days=1))


@dataclass(frozen=True)
class MailEventEnqueueResult:
    batch_id: str
    ranking_run_id: str
    created_count: int
    existing_count: int
    eligible_recipient_count: int
    skipped_recipient_count: int


class EmailTransport(Protocol):
    async def send(self, delivery: EmailDelivery) -> str: ...


class MailTransportError(RuntimeError):
    """Safe transport failure that can be persisted without provider secrets."""

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def normalized_smtp_app_password(value: str) -> str:
    """Accept Google's grouped app-password display without sending its spaces."""
    return "".join(value.split())


class GmailSmtpTransport:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, delivery: EmailDelivery) -> str:
        payload = delivery.payload_snapshot
        message = EmailMessage()
        message["From"] = (
            f"{self.settings.email_from_name} <{self.settings.gmail_smtp_user}>"
        )
        message["To"] = delivery.recipient
        message["Subject"] = payload["subject"]
        message["Message-ID"] = delivery.message_id
        message.set_content(payload["textBody"])
        message.add_alternative(payload["htmlBody"], subtype="html")
        try:
            await aiosmtplib.send(
                message,
                hostname="smtp.gmail.com",
                port=587,
                start_tls=True,
                username=self.settings.gmail_smtp_user.strip(),
                password=normalized_smtp_app_password(
                    self.settings.gmail_smtp_app_password
                ),
                timeout=20,
            )
        except aiosmtplib.SMTPAuthenticationError as exc:
            raise MailTransportError(
                "SMTP_AUTHENTICATION_FAILED",
                "Gmail rejected the configured SMTP credentials.",
                retryable=False,
            ) from exc
        return delivery.message_id


def get_email_transport() -> EmailTransport:
    return GmailSmtpTransport(get_settings())


EmailTransportDependency = Annotated[EmailTransport, Depends(get_email_transport)]


def delivery_summary(delivery: EmailDelivery | None) -> EmailDeliverySummary | None:
    if delivery is None:
        return None
    return EmailDeliverySummary(
        id=delivery.id,
        ranking_run_id=delivery.ranking_run_id,
        status=delivery.status,
        attempts=delivery.attempts,
        error_code=delivery.error_code,
        last_error=delivery.last_error,
        sent_at=delivery.sent_at,
        created_at=delivery.created_at,
        updated_at=delivery.updated_at,
    )


def _message_id(
    batch_id: str,
    recipient: str,
    ranking_run_id: str | None = None,
) -> str:
    source = ranking_run_id or "legacy"
    digest = sha256(f"{batch_id}:{source}:{recipient.casefold()}".encode()).hexdigest()
    return f"<{digest[:40]}@jedi.local>"


async def enqueue_mail_events(
    session: AsyncSession,
    batch: Batch,
    run: ProcessingRun,
    *,
    group_id: str | None = None,
) -> MailEventEnqueueResult:
    """Reconcile one auditable event for every member of the ranking group."""
    if run.batch_id != batch.id or run.status != "SUCCEEDED":
        raise ValueError("Mail events require a successful run for this batch.")

    filters = [] if group_id is None else [GroupMember.group_id == group_id]
    member_rows = list(
        (
            await session.execute(
                select(GroupMember, User, MemberProfile)
                .join(User, User.id == GroupMember.user_id)
                .outerjoin(
                    MemberProfile, MemberProfile.group_member_id == GroupMember.id
                )
                .where(*filters)
                .order_by(GroupMember.joined_at, GroupMember.id)
            )
        ).all()
    )
    member_ids = [member.id for member, _user, _profile in member_rows]
    normalized_emails = [
        normalize_email(user.email) for _member, user, _profile in member_rows
    ]
    recipients = (
        list(
            (
                await session.scalars(
                    select(EmailRecipient).where(
                        or_(
                            EmailRecipient.group_member_id.in_(member_ids),
                            EmailRecipient.email_normalized.in_(normalized_emails),
                        )
                    )
                )
            ).all()
        )
        if member_ids
        else []
    )
    recipients_by_member = {
        item.group_member_id: item for item in recipients if item.group_member_id
    }
    recipients_by_email = {item.email_normalized: item for item in recipients}
    existing_events = (
        {
            item.group_member_id: item
            for item in (
                await session.scalars(
                    select(EmailDelivery).where(
                        EmailDelivery.batch_id == batch.id,
                        EmailDelivery.ranking_run_id == run.id,
                        EmailDelivery.group_member_id.in_(member_ids),
                    )
                )
            ).all()
            if item.group_member_id
        }
        if member_ids
        else {}
    )

    # A rerank supersedes only unsent events; accepted mail remains immutable history.
    old_events = (
        (
            await session.scalars(
                select(EmailDelivery).where(
                    EmailDelivery.batch_id == batch.id,
                    EmailDelivery.ranking_run_id != run.id,
                    EmailDelivery.group_member_id.in_(member_ids),
                    EmailDelivery.status.in_(["UNTOUCHED", "FAILED", "BLOCKED"]),
                )
            )
        ).all()
        if member_ids
        else []
    )
    for event in old_events:
        event.status = "CANCELLED"
        event.error_code = "SUPERSEDED_BY_RERANK"
        event.last_error = "A newer successful ranking replaced this unsent event."
        event.next_attempt_at = None

    created_count = 0
    eligible_count = 0
    skipped_count = 0
    now = datetime.now(UTC)
    for member, user, profile in member_rows:
        normalized = normalize_email(user.email)
        recipient = recipients_by_member.get(member.id) or recipients_by_email.get(
            normalized
        )
        if recipient is None:
            recipient = EmailRecipient(
                email=user.email,
                email_normalized=normalized,
                group_member_id=member.id,
                active=True,
            )
            session.add(recipient)
            await session.flush()
        elif recipient.group_member_id is None:
            recipient.group_member_id = member.id
        is_active = recipient.active and recipient.deleted_at is None
        if not is_active:
            event_status, error_code, error_message = (
                "CANCELLED",
                "RECIPIENT_DISABLED",
                "This member's recipient is paused.",
            )
            skipped_count += 1
        elif profile is None:
            event_status, error_code, error_message = (
                "BLOCKED",
                "PROFILE_MISSING",
                "Complete this member's profile before sending.",
            )
            skipped_count += 1
        else:
            event_status, error_code, error_message = "UNTOUCHED", None, None
            eligible_count += 1

        event = existing_events.get(member.id)
        if event is None:
            event = EmailDelivery(
                batch_id=batch.id,
                ranking_run_id=run.id,
                recipient_id=recipient.id,
                group_member_id=member.id,
                recipient=normalized,
                recipient_display_name=recipient.display_name,
                template_version=PERSONALIZED_TEMPLATE_VERSION,
                message_id=_message_id(batch.id, normalized, run.id),
                status=event_status,
                error_code=error_code,
                last_error=error_message,
                next_attempt_at=now if event_status == "UNTOUCHED" else None,
            )
            session.add(event)
            created_count += 1
        elif event.status not in {"SENT", "SENDING"}:
            event.recipient_id = recipient.id
            event.recipient = normalized
            event.recipient_display_name = recipient.display_name
            event.status = event_status
            event.error_code = error_code
            event.last_error = error_message
            event.next_attempt_at = now if event_status == "UNTOUCHED" else None
    await session.flush()
    return MailEventEnqueueResult(
        batch_id=batch.id,
        ranking_run_id=run.id,
        created_count=created_count,
        existing_count=len(member_rows) - created_count,
        eligible_recipient_count=eligible_count,
        skipped_recipient_count=skipped_count,
    )


async def enqueue_configured_mail_events(
    session: AsyncSession,
    batch: Batch,
    run: ProcessingRun,
    *,
    group_id: str | None = None,
    force: bool = False,
) -> MailEventEnqueueResult | None:
    """Always create member events; configuration controls dispatch, not audit."""
    if await session.get(EmailConfiguration, "default") is None:
        session.add(EmailConfiguration(id="default"))
    result = await enqueue_mail_events(
        session,
        batch,
        run,
        group_id=group_id,
    )
    await session.commit()
    return result


def _highlights(scores: dict | None) -> list[str]:
    if not scores:
        return []
    numeric = [
        (str(name), float(value))
        for name, value in scores.items()
        if isinstance(value, (int, float))
    ]
    numeric.sort(key=lambda item: (-item[1], item[0]))
    return [
        f"{name.replace('_', ' ').title()}: {value:g}" for name, value in numeric[:3]
    ]


async def _render_snapshot(
    session: AsyncSession,
    batch: Batch,
    run: ProcessingRun,
) -> dict:
    rows = (
        await session.execute(
            select(JobPrediction, Job)
            .join(Job, JobPrediction.job_id == Job.id)
            .where(JobPrediction.processing_run_id == run.id)
            .order_by(JobPrediction.rank)
            .limit(10)
        )
    ).all()
    if not rows:
        raise ValueError("A digest requires stored ranking results.")

    jobs = [
        {
            "jobId": job.id,
            "rank": prediction.rank,
            "score": prediction.jedi_preference_score,
            "company": job.company_name,
            "title": job.role_title,
            "location": job.location,
            "workMode": job.work_mode,
            "applyUrl": job.apply_url,
            "highlights": _highlights(prediction.component_scores),
        }
        for prediction, job in rows
    ]
    subject = f"JEDI top {len(jobs)} jobs — {batch.generated_at:%Y-%m-%d}"
    text_lines = [subject, ""]
    html_rows: list[str] = []
    for item in jobs:
        context = " · ".join(
            value for value in (item["location"], item["workMode"]) if value
        )
        highlights = ", ".join(item["highlights"]) or "No component highlights"
        text_lines.extend(
            [
                f"{item['rank']}. {item['title']} — {item['company']}",
                f"Score: {item['score']:.1f}" + (f" · {context}" if context else ""),
                highlights,
                item["applyUrl"],
                "",
            ]
        )
        html_rows.append(
            "<li style='margin:0 0 20px'>"
            f"<strong>#{item['rank']} {escape(item['title'])}</strong>"
            f"  {escape(item['company'])}<br>"
            f"Score: {item['score']:.1f}"
            + (f" · {escape(context)}" if context else "")
            + f"<br><span>{escape(highlights)}</span><br>"
            f"<a href='{escape(item['applyUrl'], quote=True)}'>Apply</a></li>"
        )
    html_body = (
        "<html><body style='background:#090909;color:#f5f5ef;"
        "font-family:Arial,sans-serif;padding:24px'>"
        f"<h1 style='color:#d7ff3f'>{escape(subject)}</h1>"
        f"<ol>{''.join(html_rows)}</ol></body></html>"
    )
    return {
        "subject": subject,
        "textBody": "\n".join(text_lines),
        "htmlBody": html_body,
        "rankingRunId": run.id,
        "templateVersion": TEMPLATE_VERSION,
        "jobs": jobs,
    }


async def queue_digest(
    session: AsyncSession,
    batch: Batch,
    run: ProcessingRun,
    *,
    manual_retry: bool = False,
) -> EmailDelivery | None:
    settings = get_settings()
    if not settings.email_enabled:
        return None
    recipient = settings.digest_to_email.strip().casefold()
    snapshot = await _render_snapshot(session, batch, run)
    delivery = await session.scalar(
        select(EmailDelivery).where(
            EmailDelivery.batch_id == batch.id,
            EmailDelivery.recipient == recipient,
        )
    )
    if delivery is not None and delivery.status == "SENT":
        return delivery
    if delivery is None:
        delivery = EmailDelivery(
            batch_id=batch.id,
            recipient=recipient,
            ranking_run_id=run.id,
            template_version=TEMPLATE_VERSION,
            message_id=_message_id(batch.id, recipient, run.id),
            payload_snapshot=snapshot,
            status="UNTOUCHED",
            next_attempt_at=datetime.now(UTC),
        )
        session.add(delivery)
    else:
        delivery.ranking_run_id = run.id
        delivery.template_version = TEMPLATE_VERSION
        delivery.payload_snapshot = snapshot
        delivery.status = "UNTOUCHED"
        delivery.next_attempt_at = datetime.now(UTC)
        delivery.error_code = None
        delivery.last_error = None
        if manual_retry:
            delivery.attempts = 0
    await session.flush()
    return delivery


async def send_delivery(
    session: AsyncSession,
    delivery_id: str,
    transport: EmailTransport,
) -> EmailDelivery:
    now = datetime.now(UTC)
    delivery = await session.scalar(
        select(EmailDelivery).where(EmailDelivery.id == delivery_id).with_for_update()
    )
    if delivery is None:
        raise LookupError("Email delivery not found.")
    if delivery.status == "SENT" or delivery.attempts >= 3:
        return delivery
    if (
        delivery.status == "SENDING"
        and delivery.lease_expires_at
        and (
            delivery.lease_expires_at.replace(tzinfo=UTC)
            if delivery.lease_expires_at.tzinfo is None
            else delivery.lease_expires_at
        )
        > now
    ):
        return delivery

    lease_token = token_urlsafe(32)
    delivery.status = "SENDING"
    delivery.lease_token = lease_token
    delivery.lease_expires_at = now + DELIVERY_LEASE
    delivery.attempts += 1
    await session.commit()
    try:
        provider_id = await transport.send(delivery)
    except Exception:
        await session.rollback()
        delivery = await session.get(EmailDelivery, delivery_id)
        if delivery and delivery.lease_token == lease_token:
            delivery.status = "FAILED"
            delivery.error_code = "SMTP_DELIVERY_FAILED"
            delivery.last_error = "Gmail SMTP delivery failed."
            delivery.lease_token = None
            delivery.lease_expires_at = None
            delay = RETRY_DELAYS[min(delivery.attempts - 1, 2)]
            delivery.next_attempt_at = datetime.now(UTC) + delay
            await session.commit()
        return delivery

    delivery = await session.get(EmailDelivery, delivery_id)
    if delivery and delivery.lease_token == lease_token:
        delivery.status = "SENT"
        delivery.provider_message_id = provider_id
        delivery.sent_at = datetime.now(UTC)
        delivery.error_code = None
        delivery.last_error = None
        delivery.lease_token = None
        delivery.lease_expires_at = None
        delivery.next_attempt_at = None
        await session.commit()
    return delivery


async def queue_and_send_digest(
    session: AsyncSession,
    batch: Batch,
    run: ProcessingRun,
    transport: EmailTransport,
    *,
    manual_retry: bool = False,
) -> EmailDelivery | None:
    delivery = await queue_digest(
        session,
        batch,
        run,
        manual_retry=manual_retry,
    )
    if delivery is None:
        return None
    await session.commit()
    return await send_delivery(session, delivery.id, transport)


async def send_oldest_due(
    session: AsyncSession,
    transport: EmailTransport,
) -> EmailDelivery | None:
    now = datetime.now(UTC)
    delivery = await session.scalar(
        select(EmailDelivery)
        .where(
            EmailDelivery.attempts < 3,
            or_(
                and_(
                    EmailDelivery.status.in_(["UNTOUCHED", "FAILED"]),
                    or_(
                        EmailDelivery.next_attempt_at.is_(None),
                        EmailDelivery.next_attempt_at <= now,
                    ),
                ),
                and_(
                    EmailDelivery.status == "SENDING",
                    EmailDelivery.lease_expires_at <= now,
                ),
            ),
        )
        .order_by(EmailDelivery.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if delivery is None:
        return None
    delivery_id = delivery.id
    await session.commit()
    return await send_delivery(session, delivery_id, transport)
