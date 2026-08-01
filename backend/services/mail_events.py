"""Personalized mail-event scoring, bounded claiming, caching, and delivery."""

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from html import escape
from secrets import token_urlsafe
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.database import (
    EmailDelivery,
    Job,
    JobPrediction,
    MemberProfile,
)
from backend.services.email import EmailTransport
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
) -> dict:
    if not jobs:
        raise NonRetryableMailEventError(
            "RANKINGS_MISSING",
            "No ranked candidates were available for this event.",
        )
    subject = f"Your JEDI top {len(jobs)} jobs"
    text_lines = [subject, ""]
    html_rows: list[str] = []
    for index, item in enumerate(jobs, start=1):
        context = " · ".join(
            value for value in (item["location"], item["workMode"]) if value
        )
        reasons = ", ".join(item["reasons"])
        text_lines.extend(
            [
                f"{index}. {item['title']} — {item['company']}",
                (
                    f"Personal fit: {item['personalizedScore']:.1f} · "
                    f"JEDI score: {item['baseScore']:.1f}"
                    + (f" · {context}" if context else "")
                ),
                reasons,
                item["applyUrl"],
                "",
            ]
        )
        html_rows.append(
            "<li style='margin:0 0 20px'>"
            f"<strong>#{index} {escape(item['title'])}</strong>"
            f" — {escape(item['company'])}<br>"
            f"Personal fit: {item['personalizedScore']:.1f} · "
            f"JEDI score: {item['baseScore']:.1f}"
            + (f" · {escape(context)}" if context else "")
            + f"<br><span>{escape(reasons)}</span><br>"
            f"<a href='{escape(item['applyUrl'], quote=True)}'>Apply</a></li>"
        )
    return {
        "subject": subject,
        "textBody": "\n".join(text_lines),
        "htmlBody": (
            "<html><body style='background:#090909;color:#f5f5ef;"
            "font-family:Arial,sans-serif;padding:24px'>"
            f"<h1 style='color:#d7ff3f'>{escape(subject)}</h1>"
            f"<ol>{''.join(html_rows)}</ol></body></html>"
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
) -> list[MailEventClaim]:
    claimed_at = now or datetime.now(UTC)
    priority = case(
        (EmailDelivery.status == "FAILED", 0),
        (EmailDelivery.status == "SENDING", 1),
        else_=2,
    )
    events = list(
        (
            await session.scalars(
                select(EmailDelivery)
                .where(
                    EmailDelivery.recipient_id.is_not(None),
                    EmailDelivery.group_member_id.is_not(None),
                    EmailDelivery.attempts < MAX_AUTOMATIC_ATTEMPTS,
                    or_(
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
                    ),
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
        claims.append(MailEventClaim(event.id, lease_token))
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
    if retryable and event.attempts < MAX_AUTOMATIC_ATTEMPTS:
        event.next_attempt_at = next_delivery_window(now)
    else:
        event.attempts = MAX_AUTOMATIC_ATTEMPTS
        event.next_attempt_at = None
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
                event.payload_snapshot = render_personalized_snapshot(
                    event, personalized
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
        await session.commit()
        return "sent"


async def run_mail_event_worker(
    session_factory: async_sessionmaker[AsyncSession],
    transport: EmailTransport,
    *,
    now: datetime | None = None,
    limit: int = CLAIM_LIMIT,
    concurrency: int = SEND_CONCURRENCY,
) -> MailWorkerResult:
    async with session_factory() as session:
        claims = await claim_mail_events(session, now=now, limit=limit)
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
                    EmailDelivery.attempts < MAX_AUTOMATIC_ATTEMPTS,
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
