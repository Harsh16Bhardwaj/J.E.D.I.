"""Invite-only registration and shared-group onboarding routes."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser, hash_password
from backend.database import (
    EmailConfiguration,
    EmailRecipient,
    Group,
    GroupInvitation,
    GroupMember,
    MemberProfile,
    User,
    get_session,
    utc_now,
)
from backend.schemas.email_management import normalize_email
from backend.schemas.group_access import (
    GroupMemberSummary,
    GroupSettingsResponse,
    InvitationCreated,
    InvitationSummary,
    MemberProfileInput,
    OnboardingResult,
    OnboardingState,
    RegisterRequest,
    SessionUserResponse,
)
from backend.services.group_access import (
    generate_invite_code,
    invitation_hash,
    normalized_member_profile,
    onboarding_state,
    require_group_context,
    session_response,
    set_session_cookie,
)

router = APIRouter(tags=["group access"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
GROUP_MEMBER_LIMIT = 50
EMAIL_CONFIGURATION_ID = "default"


def invitation_summary(item: GroupInvitation) -> InvitationSummary:
    return InvitationSummary(
        id=item.id,
        expires_at=item.expires_at,
        revoked_at=item.revoked_at,
        usage_count=item.usage_count,
        created_at=item.created_at,
    )


def require_owner(user: User, group: Group) -> None:
    if group.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "GROUP_OWNER_REQUIRED",
                "message": "Only the group owner can manage invitation codes.",
            },
        )


@router.post(
    "/api/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    user: CurrentUser,
    session: DatabaseSession,
) -> InvitationCreated:
    context = await require_group_context(session, user.id, lock=True)
    require_owner(user, context.group)
    now = utc_now()
    await session.execute(
        update(GroupInvitation)
        .where(
            GroupInvitation.group_id == context.group.id,
            GroupInvitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )

    code = ""
    code_hash = ""
    for _ in range(10):
        code = generate_invite_code()
        code_hash = invitation_hash(code)
        if not await session.scalar(
            select(GroupInvitation.id).where(GroupInvitation.code_hash == code_hash)
        ):
            break
    else:
        raise HTTPException(
            status_code=503,
            detail="A unique invitation code could not be generated.",
        )

    item = GroupInvitation(
        group_id=context.group.id,
        code_hash=code_hash,
        expires_at=now + timedelta(days=7),
    )
    session.add(item)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Invitation creation conflicted with another request; retry.",
        ) from exc
    return InvitationCreated(**invitation_summary(item).model_dump(), code=code)


@router.get("/api/invitations", response_model=list[InvitationSummary])
async def list_invitations(
    user: CurrentUser,
    session: DatabaseSession,
) -> list[InvitationSummary]:
    context = await require_group_context(session, user.id)
    require_owner(user, context.group)
    items = (
        await session.scalars(
            select(GroupInvitation)
            .where(GroupInvitation.group_id == context.group.id)
            .order_by(GroupInvitation.created_at.desc())
        )
    ).all()
    return [invitation_summary(item) for item in items]


@router.delete(
    "/api/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invitation(
    invitation_id: str,
    user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    context = await require_group_context(session, user.id)
    require_owner(user, context.group)
    item = await session.get(GroupInvitation, invitation_id)
    if item is None or item.group_id != context.group.id:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    if item.revoked_at is None:
        item.revoked_at = utc_now()
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/auth/register",
    response_model=SessionUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    response: Response,
    session: DatabaseSession,
) -> SessionUserResponse:
    item = await session.scalar(
        select(GroupInvitation)
        .where(GroupInvitation.code_hash == invitation_hash(body.invite_code))
        .with_for_update()
    )
    if item is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVITE_INVALID", "message": "Invitation code is invalid."},
        )
    now = datetime.now(UTC)
    if item.revoked_at is not None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "INVITE_REVOKED",
                "message": "Invitation code was revoked.",
            },
        )
    expires_at = item.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise HTTPException(
            status_code=410,
            detail={"code": "INVITE_EXPIRED", "message": "Invitation code expired."},
        )

    group = await session.get(Group, item.group_id, with_for_update=True)
    if group is None:
        raise HTTPException(
            status_code=409,
            detail="Invitation group no longer exists.",
        )
    member_count = (
        await session.scalar(
            select(func.count())
            .select_from(GroupMember)
            .where(GroupMember.group_id == group.id)
        )
        or 0
    )
    if member_count >= GROUP_MEMBER_LIMIT:
        raise HTTPException(
            status_code=409,
            detail={"code": "GROUP_FULL", "message": "The JEDI group is full."},
        )
    existing = await session.scalar(
        select(User).where(func.lower(User.email) == body.email)
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "EMAIL_EXISTS",
                "message": "An account already uses this email.",
            },
        )

    user = User(email=body.email, password_hash=hash_password(body.password))
    session.add(user)
    try:
        await session.flush()
        session.add(GroupMember(group_id=group.id, user_id=user.id))
        item.usage_count += 1
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Registration conflicted with another request; retry.",
        ) from exc
    set_session_cookie(response, user)
    return await session_response(session, user)


@router.get("/api/onboarding", response_model=OnboardingState)
async def get_onboarding(
    user: CurrentUser,
    session: DatabaseSession,
) -> OnboardingState:
    return await onboarding_state(
        session,
        await require_group_context(session, user.id),
    )


@router.post("/api/onboarding", response_model=OnboardingResult)
async def complete_onboarding(
    body: MemberProfileInput,
    user: CurrentUser,
    session: DatabaseSession,
) -> OnboardingResult:
    context = await require_group_context(session, user.id, lock=True)
    normalized = normalized_member_profile(body)
    profile = await session.scalar(
        select(MemberProfile).where(
            MemberProfile.group_member_id == context.membership.id
        )
    )
    replayed = bool(profile and profile.content_hash == normalized["content_hash"])
    if profile is None:
        profile = MemberProfile(
            group_member_id=context.membership.id,
            **normalized,
        )
        session.add(profile)
    elif not replayed:
        for key, value in normalized.items():
            setattr(profile, key, value)

    configuration = await session.scalar(
        select(EmailConfiguration)
        .where(EmailConfiguration.id == EMAIL_CONFIGURATION_ID)
        .with_for_update()
    )
    if configuration is None:
        configuration = EmailConfiguration(id=EMAIL_CONFIGURATION_ID)
        session.add(configuration)
        await session.flush()
    normalized_email = normalize_email(user.email)
    recipient = await session.scalar(
        select(EmailRecipient).where(
            EmailRecipient.email_normalized == normalized_email
        )
    )
    if recipient is None:
        recipient_count = (
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
        if recipient_count >= GROUP_MEMBER_LIMIT:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "RECIPIENT_LIMIT_REACHED",
                    "message": "The newsletter already has 50 active recipients.",
                },
            )
        session.add(
            EmailRecipient(
                configuration_id=configuration.id,
                email=user.email,
                email_normalized=normalized_email,
                group_member_id=context.membership.id,
            )
        )
    else:
        recipient.email = user.email
        recipient.group_member_id = context.membership.id
        recipient.active = True
        recipient.deleted_at = None

    context.membership.onboarding_completed_at = utc_now()
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Onboarding conflicted with another request; retry.",
        ) from exc
    state = await onboarding_state(session, context)
    return OnboardingResult(**state.model_dump(), replayed=replayed)


@router.get("/api/group", response_model=GroupSettingsResponse)
async def get_group_settings(
    user: CurrentUser,
    session: DatabaseSession,
) -> GroupSettingsResponse:
    context = await require_group_context(session, user.id)
    rows = (
        await session.execute(
            select(GroupMember, User)
            .join(User, User.id == GroupMember.user_id)
            .where(GroupMember.group_id == context.group.id)
            .order_by(GroupMember.joined_at.asc(), User.email.asc())
        )
    ).all()
    state = await onboarding_state(session, context)
    return GroupSettingsResponse(
        group=state.group,
        is_group_owner=context.group.owner_id == user.id,
        member_count=len(rows),
        members=[
            GroupMemberSummary(
                id=membership.id,
                email=member.email,
                onboarding_complete=membership.onboarding_completed_at is not None,
                joined_at=membership.joined_at,
                is_owner=member.id == context.group.owner_id,
            )
            for membership, member in rows
        ],
        shared_profile=state.shared_profile,
        shared_model=state.shared_model,
    )
