"""Daily shared retrieval, followed by transparent personal preference ranking."""

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from backend.database import Job, MemberProfile
from backend.services.skill_vocabulary import canonical_skill

VERSION = "cohort-v1"
CATALOG_LIMIT = 5000
POOL_LIMIT = 1000
FAMILIES = {
    "backend": ("backend", "back end", "server", "api"),
    "frontend": ("frontend", "front end", "react", "web developer", "ui engineer"),
    "fullstack": ("fullstack", "full stack"),
    "data": ("data", "machine learning", "ml", "ai", "analytics"),
    "platform": ("devops", "sre", "platform", "cloud", "infrastructure"),
    "mobile": ("android", "ios", "mobile", "flutter"),
    "design": ("designer", "design", "ux"),
    "product": ("product manager", "product owner"),
}


def normalized(value: str) -> str:
    return re.sub(r"[^\w+#]+", " ", value.casefold()).strip()


def families(titles: list[str]) -> list[str]:
    found = set()
    for title in titles:
        value = f" {normalized(title)} "
        matches = {
            key
            for key, words in FAMILIES.items()
            if any(f" {word} " in value for word in words)
        }
        found.update(matches or {"general"})
    return sorted(found or {"general"})


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def eligible(job: Job, now: datetime) -> bool:
    return (
        job.can_apply_now is not False
        and (job.application_deadline is None or aware(job.application_deadline) > now)
        and job.posted_at is not None
        and now - timedelta(days=30) <= aware(job.posted_at) <= now
    )


def build_pools(jobs: list[Job]) -> dict[str, list[str]]:
    pools: dict[str, list[str]] = {key: [] for key in [*FAMILIES, "general"]}
    ordered = sorted(jobs, key=lambda j: (-aware(j.posted_at).timestamp(), j.id))
    for job in ordered:
        if len(pools["general"]) < POOL_LIMIT:
            pools["general"].append(job.id)
        for key in families([job.role_title]):
            if key != "general" and len(pools[key]) < POOL_LIMIT:
                pools[key].append(job.id)
    return pools


async def collect_pools(session: AsyncSession, now: datetime) -> tuple[dict, int, bool]:
    jobs = list(
        (
            await session.scalars(
                select(Job)
                .options(load_only(Job.id, Job.role_title, Job.posted_at))
                .where(
                    Job.posted_at >= now - timedelta(days=30),
                    Job.posted_at <= now,
                    Job.can_apply_now.is_not(False),
                    or_(
                        Job.application_deadline.is_(None),
                        Job.application_deadline > now,
                    ),
                )
                .order_by(Job.posted_at.desc(), Job.id)
                .limit(CATALOG_LIMIT + 1)
            )
        ).all()
    )
    return (
        build_pools(jobs[:CATALOG_LIMIT]),
        min(len(jobs), CATALOG_LIMIT),
        len(jobs) > CATALOG_LIMIT,
    )


def rank_job(job: Job, profile: MemberProfile) -> dict:
    """Unknown evidence earns no points. Weights apply only to configured dimensions."""
    score = 0.0
    total = 0
    reasons, unknowns = [], []
    if profile.preferred_titles:
        total += 45
        title = normalized(job.role_title)
        exact = any(normalized(t) in title for t in profile.preferred_titles)
        overlap = (
            set(families(profile.preferred_titles)) & set(families([job.role_title]))
        ) - {"general"}
        score += 45 if exact else 25 if overlap else 0
        if exact or overlap:
            reasons.append("Target role" if exact else "Related role family")
    if profile.preferred_skills:
        total += 30
        wanted = {canonical_skill(s).casefold() for s in profile.preferred_skills}
        offered = {canonical_skill(s).casefold() for s in job.skills or []}
        score += 30 * len(wanted & offered) / len(wanted)
        if wanted & offered:
            reasons.append(f"{len(wanted & offered)}/{len(wanted)} preferred skills")
        if not offered:
            unknowns.append("Skills not listed")
    if profile.preferred_locations:
        total += 15
        locations = [normalized(s) for s in profile.preferred_locations]
        location = normalized(job.location or "")
        matches = any(
            s
            and (
                s == location
                or s
                in {normalized(part) for part in re.split(r"[,/;]", job.location or "")}
            )
            for s in locations
        )
        # Remote eligibility still requires the listed location to be reviewed.
        matches = matches or (
            "remote" in locations and normalized(job.work_mode or "") == "remote"
        )
        if matches:
            score += 15
            reasons.append("Preferred location or remote mode; confirm eligibility")
        if not location:
            unknowns.append("Location not listed")
    if (
        profile.experience_min_years is not None
        or profile.experience_max_years is not None
    ):
        total += 10
        if job.experience_min_years is None:
            unknowns.append("Experience not listed")
        elif (
            profile.experience_max_years is None
            or job.experience_min_years <= profile.experience_max_years
        ) and (
            job.experience_max_years is None
            or profile.experience_min_years is None
            or job.experience_max_years >= profile.experience_min_years
        ):
            score += 10
            reasons.append("Experience range overlaps")
    if profile.salary_min is not None:
        # Salary is only comparable when currency and period are explicit.
        comparable = (
            job.salary_currency == profile.salary_currency
            and job.salary_period == "YEARLY"
        )
        if comparable and job.salary_max is not None:
            if job.salary_max < profile.salary_min:
                unknowns.append("Listed salary is below your minimum")
            else:
                reasons.append("Listed annual salary reaches your minimum")
        else:
            unknowns.append("Salary needs review")
    return {
        "id": job.id,
        "companyName": job.company_name,
        "roleTitle": job.role_title,
        "location": job.location,
        "workMode": job.work_mode,
        "postedAt": job.posted_at,
        "score": round(100 * score / total, 1) if total else None,
        "reasons": reasons,
        "unknowns": unknowns,
    }
