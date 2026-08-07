"""Personalized mail-event scoring, bounded claiming, caching, and delivery."""

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from html import escape
from secrets import token_urlsafe
from urllib.parse import quote
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import get_settings
from backend.database import (
    EmailDelivery,
    EmailDeliveryAttempt,
    Job,
    JobPrediction,
    MemberProfile,
)
from backend.services.email import (
    PERSONALIZED_TEMPLATE_VERSION,
    EmailTransport,
    MailTransportError,
)
from backend.services.product import (
    comparison_text,
    dice,
    overlap_ratio,
    preference_range_match,
)

IST = ZoneInfo("Asia/Kolkata")
MAIL_EVENT_LEASE = timedelta(minutes=5)
MAX_AUTOMATIC_ATTEMPTS = 4
CLAIM_LIMIT = 25
SEND_CONCURRENCY = 5
CACHE_CAPACITY = 4


@dataclass(frozen=True)
class RankedCandidate:
    job_id: str
    base_rank: int
    base_score: float
    company: str
    title: str
    location: str | None
    work_mode: str | None
    skills: tuple[str, ...]
    experience_min_years: float | None
    experience_max_years: float | None
    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str | None
    can_apply_now: bool | None
    apply_url: str


@dataclass(frozen=True)
class MailEventClaim:
    event_id: str
    lease_token: str
    attempt_id: str | None = None


@dataclass(frozen=True)
class MailWorkerResult:
    claimed: int
    sent: int
    failed: int
    skipped: int
    remaining: int
    cache_hits: int
    cache_misses: int


class NonRetryableMailEventError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BatchCandidateCache:
    """Invocation-local four-entry LRU of immutable top-25 candidate sets."""

    def __init__(self, capacity: int = CACHE_CAPACITY) -> None:
        self.capacity = capacity
        self.hits = 0
        self.misses = 0
        self._items: OrderedDict[tuple[str, str], tuple[RankedCandidate, ...]] = (
            OrderedDict()
        )
        self._lock = asyncio.Lock()

    async def get(
        self,
        key: tuple[str, str],
        loader: Callable[[], Awaitable[tuple[RankedCandidate, ...]]],
    ) -> tuple[RankedCandidate, ...]:
        async with self._lock:
            cached = self._items.get(key)
            if cached is not None:
                self.hits += 1
                self._items.move_to_end(key)
                return cached
            self.misses += 1
            value = await loader()
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)
            return value


async def load_ranked_candidates(
    session: AsyncSession,
    batch_id: str,
    ranking_run_id: str,
) -> tuple[RankedCandidate, ...]:
    rows = (
        await session.execute(
            select(JobPrediction, Job)
            .join(Job, JobPrediction.job_id == Job.id)
            .where(
                JobPrediction.batch_id == batch_id,
                JobPrediction.processing_run_id == ranking_run_id,
            )
            .order_by(JobPrediction.rank, Job.id)
            .limit(25)
        )
    ).all()
    return tuple(
        RankedCandidate(
            job_id=job.id,
            base_rank=prediction.rank,
            base_score=float(prediction.jedi_preference_score),
            company=job.company_name,
            title=job.role_title,
            location=job.location,
            work_mode=job.work_mode,
            skills=tuple(job.skills or []),
            experience_min_years=job.experience_min_years,
            experience_max_years=job.experience_max_years,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            can_apply_now=job.can_apply_now,
            apply_url=job.apply_url,
        )
        for prediction, job in rows
    )


def _binary_signal(value: bool | None) -> float:
    return 50.0 if value is None else (100.0 if value else 0.0)


def _title_signal(candidate: RankedCandidate, profile: MemberProfile) -> float:
    if not candidate.title or not profile.preferred_titles:
        return 50.0
    return 100.0 * max(
        dice(candidate.title, preferred) for preferred in profile.preferred_titles
    )


def _skill_signal(candidate: RankedCandidate, profile: MemberProfile) -> float:
    if not candidate.skills or not profile.preferred_skills:
        return 50.0
    return 100.0 * overlap_ratio(candidate.skills, profile.preferred_skills)


def _location_signal(candidate: RankedCandidate, profile: MemberProfile) -> float:
    location = comparison_text(candidate.location)
    preferences = [comparison_text(item) for item in profile.preferred_locations]
    preferences = [item for item in preferences if item]
    if not location or not preferences:
        return 50.0
    return (
        100.0
        if any(item in location or location in item for item in preferences)
        else 0.0
    )


def _experience_signal(
    candidate: RankedCandidate,
    profile: MemberProfile,
) -> float:
    return _binary_signal(
        preference_range_match(
            candidate.experience_min_years,
            candidate.experience_max_years,
            profile.experience_min_years,
            profile.experience_max_years,
        )
    )


def _salary_signal(candidate: RankedCandidate, profile: MemberProfile) -> float:
    matched = preference_range_match(
        candidate.salary_min,
        candidate.salary_max,
        profile.salary_min,
        profile.salary_max,
    )
    if matched is None:
        return 50.0
    if (
        candidate.salary_currency
        and profile.salary_currency
        and candidate.salary_currency.casefold() != profile.salary_currency.casefold()
    ):
        return 0.0
    return _binary_signal(matched)


def _format_experience(candidate: RankedCandidate) -> str:
    minimum = candidate.experience_min_years
    maximum = candidate.experience_max_years
    if minimum is None and maximum is None:
        return "Experience not listed"
    if minimum is not None and maximum is not None:
        if minimum == maximum:
            return f"{minimum:g} yrs"
        return f"{minimum:g}–{maximum:g} yrs"
    if minimum is not None:
        return f"{minimum:g}+ yrs"
    return f"Up to {maximum:g} yrs"


def _compact_money(value: Decimal, currency: str | None) -> str:
    amount = float(value)
    code = (currency or "").upper()
    symbol = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(code, code)
    if code == "INR" and abs(amount) >= 100_000:
        number, suffix = amount / 100_000, "L"
    elif abs(amount) >= 1_000_000:
        number, suffix = amount / 1_000_000, "M"
    elif abs(amount) >= 1_000:
        number, suffix = amount / 1_000, "k"
    else:
        number, suffix = amount, ""
    compact = f"{number:.1f}".rstrip("0").rstrip(".")
    spacer = " " if symbol and len(symbol) > 1 else ""
    return f"{symbol}{spacer}{compact}{suffix}".strip()


def _format_salary(candidate: RankedCandidate) -> str:
    minimum = candidate.salary_min
    maximum = candidate.salary_max
    if minimum is None and maximum is None:
        return "Salary not listed"
    if minimum is not None and maximum is not None:
        left = _compact_money(minimum, candidate.salary_currency)
        right = _compact_money(maximum, candidate.salary_currency)
        return left if left == right else f"{left}–{right}"
    value = _compact_money(minimum or maximum, candidate.salary_currency)
    return f"{value}+" if minimum is not None else f"Up to {value}"


def personalize_candidates(
    profile: MemberProfile,
    candidates: tuple[RankedCandidate, ...],
) -> list[dict]:
    personalized: list[dict] = []
    for candidate in candidates:
        signals = {
            "model": max(0.0, min(100.0, candidate.base_score)),
            "title": _title_signal(candidate, profile),
            "skills": _skill_signal(candidate, profile),
            "location": _location_signal(candidate, profile),
            "experience": _experience_signal(candidate, profile),
            "salary": _salary_signal(candidate, profile),
            "eligibility": _binary_signal(candidate.can_apply_now),
        }
        score = (
            0.60 * signals["model"]
            + 0.15 * signals["title"]
            + 0.10 * signals["skills"]
            + 0.06 * signals["location"]
            + 0.05 * signals["experience"]
            + 0.03 * signals["salary"]
            + 0.01 * signals["eligibility"]
        )
        strongest = sorted(
            ((name, value) for name, value in signals.items() if name != "model"),
            key=lambda item: (-item[1], item[0]),
        )[:3]
        personalized.append(
            {
                "jobId": candidate.job_id,
                "baseRank": candidate.base_rank,
                "baseScore": round(candidate.base_score, 2),
                "personalizedScore": round(score, 2),
                "company": candidate.company,
                "title": candidate.title,
                "location": candidate.location,
                "workMode": candidate.work_mode,
                "experienceText": _format_experience(candidate),
                "salaryText": _format_salary(candidate),
                "applyUrl": candidate.apply_url,
                "reasons": [
                    f"{name.title()} fit {value:.0f}%" for name, value in strongest
                ],
            }
        )
    personalized.sort(
        key=lambda item: (
            -item["personalizedScore"],
            item["baseRank"],
            item["jobId"],
        )
    )
    return personalized[:10]


def render_personalized_snapshot(
    event: EmailDelivery,
    jobs: list[dict],
    app_base_url: str,
) -> dict:
    if not jobs:
        raise NonRetryableMailEventError(
            "RANKINGS_MISSING",
            "No ranked candidates were available for this event.",
        )
    app_base = app_base_url.rstrip("/")
    rankings_url = (
        f"{app_base}/batches/{quote(event.batch_id or '', safe='')}?tab=rankings"
    )
    if event.ranking_run_id:
        rankings_url += f"&runId={quote(event.ranking_run_id, safe='')}"
    subject = f"Your JEDI shortlist: {len(jobs)} matched opportunities"
    text_lines = [
        subject,
        "",
        "Fresh roles for your profile.",
        "Fit = your profile match. JEDI = overall opportunity score.",
        "",
    ]
    html_rows: list[str] = []
    for index, item in enumerate(jobs, start=1):
        context = " · ".join(
            str(value) for value in (item["location"], item["workMode"]) if value
        ) or "Location and work mode not listed"
        details = f"{item['experienceText']} · {item['salaryText']}"
        job_url = f"{app_base}/jobs/{quote(item['jobId'], safe='')}"
        text_lines.extend(
            [
                f"{index}. {item['title']} — {item['company']}",
                f"{context} · {details}",
                f"Fit {item['personalizedScore']:.1f} · JEDI {item['baseScore']:.1f}",
                f"Open in JEDI: {job_url}",
                "",
            ]
        )
        html_rows.append(
            "<table role='presentation' width='100%' cellspacing='0' cellpadding='0' "
            "class='job-row' style='margin:0 0 8px;border:1px solid #dfe3e8;"
            "border-radius:9px;background:#ffffff;border-collapse:separate'>"
            "<tr>"
            "<td width='34' valign='top' style='padding:12px 0 12px 12px;"
            "font:700 13px Arial,sans-serif;color:#668d20'>"
            f"#{index}</td>"
            "<td valign='top' style='padding:11px 8px 11px 8px'>"
            f"<a href='{escape(job_url, quote=True)}' class='job-title' "
            "style='display:block;max-height:40px;overflow:hidden;font:700 16px "
            "Arial,sans-serif;line-height:20px;color:#111827;text-decoration:none'>"
            f"{escape(str(item['title']))}</a>"
            "<div class='job-company' style='margin-top:3px;overflow:hidden;"
            "white-space:nowrap;text-overflow:ellipsis;font:600 12px Arial,sans-serif;"
            f"color:#374151'>{escape(str(item['company']))}</div>"
            "<div class='job-context' style='margin-top:3px;overflow:hidden;"
            "white-space:nowrap;text-overflow:ellipsis;font:400 11px Arial,sans-serif;"
            f"color:#6b7280'>{escape(context)}</div>"
            "<div class='job-details' style='margin-top:4px;overflow:hidden;"
            "white-space:nowrap;text-overflow:ellipsis;font:400 11px Arial,sans-serif;"
            f"color:#6b7280'>{escape(details)} &nbsp;&middot;&nbsp; "
            f"JEDI {item['baseScore']:.1f}</div></td>"
            "<td width='66' valign='middle' align='right' "
            "style='padding:10px 12px 10px 4px'>"
            "<div class='fit-score' style='font:700 22px Arial,sans-serif;"
            f"line-height:24px;color:#365314'>{item['personalizedScore']:.1f}</div>"
            "<div style='font:700 9px Arial,sans-serif;letter-spacing:1px;"
            "color:#668d20;text-transform:uppercase'>Fit</div>"
            f"<a href='{escape(job_url, quote=True)}' style='display:inline-block;"
            "margin-top:9px;font:700 11px Arial,sans-serif;color:#374151;"
            "text-decoration:none'>View &rarr;</a>"
            "</td></tr></table>"
        )
    text_lines.extend(["View all opportunities in JEDI:", rankings_url])
    preferences_url = f"{app_base}/settings/email"
    pause_url = f"{preferences_url}?intent=pause"
    unsubscribe_url = f"{preferences_url}?intent=unsubscribe"
    return {
        "subject": subject,
        "textBody": "\n".join(text_lines),
        "htmlBody": (
            "<!doctype html><html><head><meta name='viewport' "
            "content='width=device-width,initial-scale=1'>"
            "<style>@media (prefers-color-scheme:dark){body,.email-page{"
            "background:#111318!important}.email-shell,.email-header{"
            "background:#181b21!important}.job-row{background:#20242b!important;"
            "border-color:#343a43!important}.job-title,.job-company{"
            "color:#f3f4f6!important}.job-context,.job-details,.email-muted{"
            "color:#aeb6c2!important}.fit-score{color:#b7dd79!important}}</style>"
            "</head><body style='margin:0;padding:0;background:#f3f4f6'>"
            "<div style='display:none;max-height:0;overflow:hidden;color:transparent'>"
            "Fresh matched opportunities from JEDI.</div>"
            "<table role='presentation' width='100%' cellspacing='0' cellpadding='0' "
            "class='email-page' style='background:#f3f4f6'><tr><td align='center' "
            "style='padding:16px 8px'>"
            "<table role='presentation' width='100%' cellspacing='0' cellpadding='0' "
            "class='email-shell' style='max-width:600px;background:#f9fafb;"
            "border:1px solid #dfe3e8;border-radius:12px;border-collapse:separate;"
            "overflow:hidden'>"
            "<tr><td class='email-header' style='padding:15px 16px 13px;"
            "background:#ffffff'>"
            f"<a href='{escape(app_base, quote=True)}' style='color:#668d20;"
            "text-decoration:none;font:700 10px Arial,sans-serif;letter-spacing:1.5px'>"
            "JEDI JOB INTELLIGENCE</a>"
            "<h1 style='margin:5px 0 2px;font:700 20px Arial,sans-serif;"
            f"line-height:25px;color:#111827'>Top {len(jobs)} matched "
            "opportunities</h1>"
            "<p class='email-muted' style='margin:0;font:400 12px Arial,sans-serif;"
            "line-height:18px;color:#6b7280'>Fresh roles for your profile.</p>"
            "</td></tr>"
            "<tr><td class='email-muted' style='padding:8px 16px;border-top:1px "
            "solid #e5e7eb;border-bottom:1px solid #e5e7eb;font:400 11px "
            "Arial,sans-serif;line-height:16px;color:#6b7280'>"
            "Fit = your profile match &nbsp;&middot;&nbsp; JEDI = overall "
            "opportunity score."
            "</td></tr><tr><td style='padding:12px 12px 4px'>"
            f"{''.join(html_rows)}"
            "<table role='presentation' width='100%' cellspacing='0' cellpadding='0'>"
            "<tr><td align='center' style='padding:8px 4px 14px'>"
            f"<a href='{escape(rankings_url, quote=True)}' style='display:inline-block;"
            "padding:10px 16px;border-radius:7px;background:#1f2937;color:#ffffff;"
            "font:700 12px Arial,sans-serif;text-decoration:none'>"
            "View all opportunities in JEDI &rarr;</a>"
            "</td></tr></table></td></tr>"
            "<tr><td class='email-muted' style='padding:11px 16px 13px;border-top:1px "
            "solid #e5e7eb;text-align:center;font:400 10px Arial,sans-serif;"
            "line-height:16px;color:#6b7280'>Recommendations enabled "
            "&nbsp;&middot;&nbsp; "
            f"<a href='{escape(preferences_url, quote=True)}' style='color:#4b5563'>"
            "View preferences</a> &nbsp;&middot;&nbsp; "
            f"<a href='{escape(pause_url, quote=True)}' style='color:#4b5563'>"
            "Pause alerts</a> &nbsp;&middot;&nbsp; "
            f"<a href='{escape(unsubscribe_url, quote=True)}' style='color:#4b5563'>"
            "Unsubscribe</a></td></tr>"
            "</table></td></tr></table></body></html>"
        ),
        "batchId": event.batch_id,
        "rankingRunId": event.ranking_run_id,
        "templateVersion": event.template_version,
        "jobs": jobs,
    }


def next_delivery_window(now: datetime) -> datetime:
    aware = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    local = aware.astimezone(IST)
    for hour in (0, 3):
        candidate = datetime.combine(local.date(), time(hour), tzinfo=IST)
        if candidate > local:
            return candidate.astimezone(UTC)
    tomorrow = local.date() + timedelta(days=1)
    return datetime.combine(tomorrow, time(0), tzinfo=IST).astimezone(UTC)


async def claim_mail_events(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = CLAIM_LIMIT,
    event_ids: list[str] | None = None,
    trigger: str = "CRON",
    requested_by_group_member_id: str | None = None,
) -> list[MailEventClaim]:
    claimed_at = now or datetime.now(UTC)
    priority = case(
        (EmailDelivery.status == "FAILED", 0),
        (EmailDelivery.status == "SENDING", 1),
        else_=2,
    )
    delivery_filter = (
        and_(
            EmailDelivery.id.in_(event_ids),
            EmailDelivery.status.in_(["UNTOUCHED", "FAILED"]),
        )
        if event_ids is not None
        else or_(
            and_(
                EmailDelivery.status.in_(["UNTOUCHED", "FAILED"]),
                or_(
                    EmailDelivery.next_attempt_at.is_(None),
                    EmailDelivery.next_attempt_at <= claimed_at,
                ),
            ),
            and_(
                EmailDelivery.status == "SENDING",
                EmailDelivery.lease_expires_at <= claimed_at,
            ),
        )
    )
    events = list(
        (
            await session.scalars(
                select(EmailDelivery)
                .where(
                    EmailDelivery.recipient_id.is_not(None),
                    EmailDelivery.group_member_id.is_not(None),
                    EmailDelivery.retry_cycle_attempts < MAX_AUTOMATIC_ATTEMPTS,
                    EmailDelivery.status.in_(["UNTOUCHED", "FAILED", "SENDING"]),
                    delivery_filter,
                )
                .order_by(
                    priority,
                    EmailDelivery.next_attempt_at,
                    EmailDelivery.created_at,
                    EmailDelivery.id,
                )
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        ).all()
    )
    claims: list[MailEventClaim] = []
    for event in events:
        lease_token = token_urlsafe(32)
        event.status = "SENDING"
        event.lease_token = lease_token
        event.lease_expires_at = claimed_at + MAIL_EVENT_LEASE
        event.attempts += 1
        event.retry_cycle_attempts += 1
        attempt = EmailDeliveryAttempt(
            email_delivery_id=event.id,
            attempt_number=event.attempts,
            retry_cycle=event.retry_cycle,
            trigger=trigger,
            status="SENDING",
            requested_by_group_member_id=requested_by_group_member_id,
            started_at=claimed_at,
        )
        session.add(attempt)
        await session.flush()
        claims.append(MailEventClaim(event.id, lease_token, attempt.id))
    await session.commit()
    return claims


async def _mark_failed(
    session: AsyncSession,
    event_id: str,
    lease_token: str,
    *,
    error_code: str,
    message: str,
    retryable: bool,
    now: datetime,
    attempt_id: str | None = None,
) -> bool:
    await session.rollback()
    event = await session.get(EmailDelivery, event_id)
    if event is None or event.lease_token != lease_token:
        return False
    event.status = "FAILED"
    event.error_code = error_code
    event.last_error = message
    event.lease_token = None
    event.lease_expires_at = None
    if retryable and event.retry_cycle_attempts < MAX_AUTOMATIC_ATTEMPTS:
        event.next_attempt_at = next_delivery_window(now)
    else:
        event.next_attempt_at = None
    if attempt_id:
        attempt = await session.get(EmailDeliveryAttempt, attempt_id)
        if attempt is not None:
            attempt.status = "FAILED"
            attempt.completed_at = now
            attempt.error_code = error_code
            attempt.safe_error_message = message
    await session.commit()
    return True


async def process_mail_event(
    session_factory: async_sessionmaker[AsyncSession],
    transport: EmailTransport,
    cache: BatchCandidateCache,
    claim: MailEventClaim,
    *,
    now: datetime | None = None,
) -> str:
    attempted_at = now or datetime.now(UTC)
    async with session_factory() as session:
        event = await session.get(EmailDelivery, claim.event_id)
        if event is None or event.lease_token != claim.lease_token:
            return "skipped"
        try:
            # Upgrade only undelivered snapshots; sent content remains immutable.
            if event.template_version != PERSONALIZED_TEMPLATE_VERSION:
                event.template_version = PERSONALIZED_TEMPLATE_VERSION
                event.payload_snapshot = None
                event.personalized_jobs = None
                event.profile_content_hash = None
            if event.payload_snapshot is None:
                if not event.group_member_id:
                    raise NonRetryableMailEventError(
                        "PROFILE_MISSING", "Mail event has no member profile owner."
                    )
                profile = await session.scalar(
                    select(MemberProfile).where(
                        MemberProfile.group_member_id == event.group_member_id
                    )
                )
                if profile is None:
                    raise NonRetryableMailEventError(
                        "PROFILE_MISSING", "Member profile is unavailable."
                    )
                if not event.batch_id or not event.ranking_run_id:
                    raise NonRetryableMailEventError(
                        "RANKINGS_MISSING", "Pinned batch rankings are unavailable."
                    )
                key = (event.batch_id, event.ranking_run_id)

                async def loader() -> tuple[RankedCandidate, ...]:
                    return await load_ranked_candidates(session, *key)

                candidates = await cache.get(key, loader)
                if not candidates:
                    raise NonRetryableMailEventError(
                        "RANKINGS_MISSING", "Pinned ranking run has no predictions."
                    )
                personalized = personalize_candidates(profile, candidates)
                event.personalized_jobs = personalized
                event.profile_content_hash = profile.content_hash
                allowed_origins = get_settings().allowed_origins
                event.payload_snapshot = render_personalized_snapshot(
                    event,
                    personalized,
                    allowed_origins[0] if allowed_origins else "http://localhost:3000",
                )
                await session.commit()
            provider_id = await transport.send(event)
        except NonRetryableMailEventError as exc:
            await _mark_failed(
                session,
                event.id,
                claim.lease_token,
                error_code=exc.code,
                message=str(exc),
                retryable=False,
                now=attempted_at,
                attempt_id=claim.attempt_id,
            )
            return "failed"
        except MailTransportError as exc:
            await _mark_failed(
                session,
                event.id,
                claim.lease_token,
                error_code=exc.code,
                message=str(exc),
                retryable=exc.retryable,
                now=attempted_at,
                attempt_id=claim.attempt_id,
            )
            return "failed"
        except Exception:
            await _mark_failed(
                session,
                event.id,
                claim.lease_token,
                error_code="SMTP_DELIVERY_FAILED",
                message="Gmail SMTP delivery failed.",
                retryable=True,
                now=attempted_at,
                attempt_id=claim.attempt_id,
            )
            return "failed"

        await session.rollback()
        event = await session.get(EmailDelivery, claim.event_id)
        if event is None or event.lease_token != claim.lease_token:
            return "skipped"
        event.status = "SENT"
        event.provider_message_id = provider_id
        event.sent_at = attempted_at
        event.error_code = None
        event.last_error = None
        event.lease_token = None
        event.lease_expires_at = None
        event.next_attempt_at = None
        if claim.attempt_id:
            attempt = await session.get(EmailDeliveryAttempt, claim.attempt_id)
            if attempt is not None:
                attempt.status = "SENT"
                attempt.completed_at = attempted_at
                attempt.provider_message_id = provider_id
        await session.commit()
        return "sent"


async def run_mail_event_worker(
    session_factory: async_sessionmaker[AsyncSession],
    transport: EmailTransport,
    *,
    now: datetime | None = None,
    limit: int = CLAIM_LIMIT,
    concurrency: int = SEND_CONCURRENCY,
    event_ids: list[str] | None = None,
    trigger: str = "CRON",
    requested_by_group_member_id: str | None = None,
) -> MailWorkerResult:
    async with session_factory() as session:
        claims = await claim_mail_events(
            session,
            now=now,
            limit=limit,
            event_ids=event_ids,
            trigger=trigger,
            requested_by_group_member_id=requested_by_group_member_id,
        )
    cache = BatchCandidateCache()
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(claim: MailEventClaim) -> str:
        async with semaphore:
            return await process_mail_event(
                session_factory,
                transport,
                cache,
                claim,
                now=now,
            )

    outcomes = await asyncio.gather(*(bounded(claim) for claim in claims))
    async with session_factory() as session:
        remaining = (
            await session.scalar(
                select(func.count())
                .select_from(EmailDelivery)
                .where(
                    EmailDelivery.status.in_(["UNTOUCHED", "FAILED", "SENDING"]),
                    EmailDelivery.retry_cycle_attempts < MAX_AUTOMATIC_ATTEMPTS,
                )
            )
            or 0
        )
    return MailWorkerResult(
        claimed=len(claims),
        sent=outcomes.count("sent"),
        failed=outcomes.count("failed"),
        skipped=outcomes.count("skipped"),
        remaining=int(remaining),
        cache_hits=cache.hits,
        cache_misses=cache.misses,
    )
