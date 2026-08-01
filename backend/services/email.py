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
from sqlalchemy import and_, func, or_, select
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
)
from backend.schemas.product import EmailDeliverySummary

TEMPLATE_VERSION = "top-ten-v1"
PERSONALIZED_TEMPLATE_VERSION = "personalized-top-ten-v1"
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
        await aiosmtplib.send(
            message,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=self.settings.gmail_smtp_user,
            password=self.settings.gmail_smtp_app_password,
            timeout=20,
        )
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
    """Create one untouched event per active onboarded member, idempotently."""
    if run.batch_id != batch.id or run.status != "SUCCEEDED":
        raise ValueError("Mail events require a successful run for this batch.")

    active_total = (
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
    recipient_filters = [
        EmailRecipient.active.is_(True),
        EmailRecipient.deleted_at.is_(None),
    ]
    if group_id is not None:
        recipient_filters.append(GroupMember.group_id == group_id)
    recipients = list(
        (
            await session.execute(
                select(EmailRecipient, GroupMember)
                .join(
                    GroupMember,
                    EmailRecipient.group_member_id == GroupMember.id,
                )
                .join(
                    MemberProfile,
                    MemberProfile.group_member_id == GroupMember.id,
                )
                .where(*recipient_filters)
                .order_by(EmailRecipient.created_at, EmailRecipient.id)
            )
        ).all()
    )
    recipient_ids = [recipient.id for recipient, _member in recipients]
    existing_ids: set[str] = set()
    if recipient_ids:
        existing_ids = set(
            (
                await session.scalars(
                    select(EmailDelivery.recipient_id).where(
                        EmailDelivery.batch_id == batch.id,
                        EmailDelivery.ranking_run_id == run.id,
                        EmailDelivery.recipient_id.in_(recipient_ids),
                    )
                )
            ).all()
        )

    created_count = 0
    for recipient, member in recipients:
        if recipient.id in existing_ids:
            continue
        session.add(
            EmailDelivery(
                batch_id=batch.id,
                ranking_run_id=run.id,
                recipient_id=recipient.id,
                group_member_id=member.id,
                recipient=recipient.email_normalized,
                recipient_display_name=recipient.display_name,
                template_version=PERSONALIZED_TEMPLATE_VERSION,
                message_id=_message_id(batch.id, recipient.email_normalized, run.id),
                payload_snapshot=None,
                personalized_jobs=None,
                profile_content_hash=None,
                status="UNTOUCHED",
                next_attempt_at=datetime.now(UTC),
            )
        )
        created_count += 1
    await session.flush()
    eligible_count = len(recipients)
    return MailEventEnqueueResult(
        batch_id=batch.id,
        ranking_run_id=run.id,
        created_count=created_count,
        existing_count=eligible_count - created_count,
        eligible_recipient_count=eligible_count,
        skipped_recipient_count=max(0, int(active_total) - eligible_count),
    )


async def enqueue_configured_mail_events(
    session: AsyncSession,
    batch: Batch,
    run: ProcessingRun,
    *,
    group_id: str | None = None,
    force: bool = False,
) -> MailEventEnqueueResult | None:
    """Queue personalized member events when newsletter delivery is enabled."""
    configuration = await session.get(EmailConfiguration, "default")
    if configuration is None:
        return None
    if not force and (
        not configuration.enabled or not configuration.send_after_ranking
    ):
        return None
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
            f" — {escape(item['company'])}<br>"
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
