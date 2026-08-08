"""Shared helpers for group-aware sessions, invitations, and onboarding."""

import hashlib
import hmac
import secrets
import string
from dataclasses import dataclass

from fastapi import HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import create_session_token
from backend.config import get_settings
from backend.database import (
    Group,
    GroupMember,
    MemberProfile,
    ModelVersion,
    ProfileVersion,
    User,
)
from backend.schemas.group_access import (
    GroupSummary,
    MemberProfileInput,
    MemberProfileResponse,
    OnboardingState,
    SessionUserResponse,
    SharedModelSummary,
    SharedProfileSummary,
)
from backend.services.product import clean_text, stable_hash

INVITE_ALPHABET = string.ascii_uppercase + string.digits
INVITE_LENGTH = 5
SUGGESTED_TITLES = [
    "Backend Engineer",
    "Software Engineer",
    "Full-Stack Engineer",
    "ML Engineer",
    "AI Engineer",
    "Data Engineer",
    "Platform Engineer",
    "Cloud Engineer",
    "DevOps Engineer",
    "Graduate Software Engineer",
    "Software Engineer Intern",
]
SUGGESTED_LOCATIONS = [
    "Remote",
    "Bengaluru",
    "Gurgaon/NCR",
    "Hyderabad",
    "Pune",
    "Mumbai",
    "Chennai",
    "India",
]
SUGGESTED_SKILLS = [
    "Python",
    "FastAPI",
    "PostgreSQL",
    "SQL",
    "JavaScript",
    "TypeScript",
    "React",
    "Next.js",
    "Docker",
    "AWS",
    "Git",
    "Machine Learning",
]


@dataclass(frozen=True)
class GroupContext:
    membership: GroupMember
    group: Group


def generate_invite_code() -> str:
    reserved_code = get_settings().owner_registration_code.strip().upper()
    for _ in range(100):
        candidate = "".join(
            secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH)
        )
        if not reserved_code or not hmac.compare_digest(candidate, reserved_code):
            return candidate
    raise RuntimeError("Unable to generate a non-reserved invitation code.")


def is_owner_registration_code(code: str) -> bool:
    reserved_code = get_settings().owner_registration_code.strip().upper()
    normalized = code.strip().upper()
    return bool(reserved_code) and hmac.compare_digest(normalized, reserved_code)


def invitation_hash(code: str) -> str:
    """Use a keyed digest so a leaked database cannot reveal short codes."""
    normalized = code.strip().upper()
    return hmac.new(
        get_settings().session_secret.encode(),
        normalized.encode(),
        hashlib.sha256,
    ).hexdigest()


def set_session_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=create_session_token(user),
        max_age=settings.session_days * 24 * 60 * 60,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )


async def group_context(
    session: AsyncSession,
    user_id: str,
    *,
    lock: bool = False,
) -> GroupContext | None:
    statement = select(GroupMember).where(GroupMember.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    membership = await session.scalar(statement)
    if membership is None:
        return None
    group = await session.get(Group, membership.group_id, with_for_update=lock)
    if group is None:
        return None
    return GroupContext(membership=membership, group=group)


async def require_group_context(
    session: AsyncSession,
    user_id: str,
    *,
    lock: bool = False,
) -> GroupContext:
    context = await group_context(session, user_id, lock=lock)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "GROUP_MEMBERSHIP_REQUIRED",
                "message": "This account is not connected to the JEDI group.",
            },
        )
    return context


async def require_group_owner(
    session: AsyncSession,
    user_id: str,
    *,
    lock: bool = False,
) -> GroupContext:
    context = await require_group_context(session, user_id, lock=lock)
    if context.group.owner_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "GROUP_OWNER_REQUIRED",
                "message": "Only the group owner can modify shared training data.",
            },
        )
    return context


async def session_response(
    session: AsyncSession,
    user: User,
) -> SessionUserResponse:
    context = await group_context(session, user.id)
    return SessionUserResponse(
        id=user.id,
        email=user.email,
        group=(
            GroupSummary(id=context.group.id, name=context.group.name)
            if context
            else None
        ),
        is_group_owner=bool(context and context.group.owner_id == user.id),
        onboarding_complete=bool(
            context and context.membership.onboarding_completed_at is not None
        ),
    )


def normalize_list(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = clean_text(value)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def normalized_member_profile(body: MemberProfileInput) -> dict:
    data = {
        "resume_text": clean_text(body.resume_text),
        "preferred_titles": normalize_list(body.preferred_titles),
        "preferred_locations": normalize_list(body.preferred_locations),
        "preferred_skills": normalize_list(body.preferred_skills),
        "experience_min_years": body.experience_min_years,
        "experience_max_years": body.experience_max_years,
        "salary_min": body.salary_min,
        "salary_max": body.salary_max,
        "salary_currency": (
            clean_text(body.salary_currency).upper() if body.salary_currency else None
        ),
    }
    return {**data, "content_hash": stable_hash(data)}


def member_profile_response(profile: MemberProfile) -> MemberProfileResponse:
    return MemberProfileResponse(
        id=profile.id,
        content_hash=profile.content_hash,
        resume_text=profile.resume_text,
        preferred_titles=profile.preferred_titles,
        preferred_locations=profile.preferred_locations,
        preferred_skills=profile.preferred_skills,
        experience_min_years=profile.experience_min_years,
        experience_max_years=profile.experience_max_years,
        salary_min=(
            float(profile.salary_min) if profile.salary_min is not None else None
        ),
        salary_max=(
            float(profile.salary_max) if profile.salary_max is not None else None
        ),
        salary_currency=profile.salary_currency,
        updated_at=profile.updated_at,
    )


async def onboarding_state(
    session: AsyncSession,
    context: GroupContext,
) -> OnboardingState:
    profile = (
        await session.get(ProfileVersion, context.group.active_profile_version_id)
        if context.group.active_profile_version_id
        else None
    )
    model = (
        await session.get(ModelVersion, context.group.active_model_version_id)
        if context.group.active_model_version_id
        else None
    )
    member_profile = await session.scalar(
        select(MemberProfile).where(
            MemberProfile.group_member_id == context.membership.id
        )
    )
    return OnboardingState(
        group=GroupSummary(id=context.group.id, name=context.group.name),
        onboarding_complete=context.membership.onboarding_completed_at is not None,
        shared_profile=(
            SharedProfileSummary(
                id=profile.id,
                resume_preview=profile.resume_text[:160],
                preferred_titles=profile.preferred_titles,
                preferred_locations=profile.preferred_locations,
                preferred_skills=profile.preferred_skills,
            )
            if profile
            else None
        ),
        shared_model=(
            SharedModelSummary(
                id=model.id,
                name=model.name,
                feature_schema_version=model.feature_schema_version,
            )
            if model
            else None
        ),
        member_profile=(
            member_profile_response(member_profile) if member_profile else None
        ),
        suggested_titles=SUGGESTED_TITLES,
        suggested_locations=SUGGESTED_LOCATIONS,
        suggested_skills=SUGGESTED_SKILLS,
    )
