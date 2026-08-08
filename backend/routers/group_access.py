"""Invite-only registration and shared-group onboarding routes."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser, hash_password
from backend.config import get_settings
from backend.database import (
    EmailConfiguration,
    EmailRecipient,
    Group,
    GroupInvitation,
    GroupMember,
    MemberProfile,
    ProfileVersion,
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
    is_owner_registration_code,
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
OWNER_CLAIM_LOCK_ID = 7_403_321_026


def registration_database_error(exception: SQLAlchemyError) -> HTTPException:
    """Convert provider failures into specific errors without exposing secrets."""
    message = str(getattr(exception, "orig", exception)).casefold()
    if (
        "password authentication failed" in message
        or "authentication failed" in message
    ):
        code = "DATABASE_AUTH_FAILED"
        detail = "The backend database credentials were rejected."
    elif "data transfer quota" in message or "quota" in message:
        code = "DATABASE_QUOTA_EXCEEDED"
        detail = "The configured database has exceeded its provider quota."
    elif any(
        fragment in message
        for fragment in (
            "could not translate host name",
            "getaddrinfo failed",
            "name or service not known",
            "network is unreachable",
            "nodename nor servname provided",
        )
    ):
        code = "DATABASE_HOST_UNREACHABLE"
        detail = "The backend could not resolve the configured database host."
    elif (
        "does not exist" in message
        and any(
            relation in message
            for relation in (
                'relation "groupinvitation"',
                'relation "group"',
                'relation "user"',
            )
        )
    ):
        code = "DATABASE_MIGRATION_REQUIRED"
        detail = "The database is reachable but the registration tables are missing."
    else:
        code = "DATABASE_UNAVAILABLE"
        detail = "The backend could not reach the registration database."
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": code, "message": detail},
    )


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
    if len(body.invite_code) > 5 and not get_settings().owner_registration_code:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "OWNER_REGISTRATION_NOT_CONFIGURED",
                "message": (
                    "Owner registration is not configured on the deployed backend."
                ),
            },
        )
    try:
        return await register_account(body, response, session)
    except SQLAlchemyError as exc:
        try:
            await session.rollback()
        except SQLAlchemyError:
            pass
        raise registration_database_error(exc) from exc


async def register_account(
    body: RegisterRequest,
    response: Response,
    session: AsyncSession,
) -> SessionUserResponse:
    if is_owner_registration_code(body.invite_code):
        return await register_first_owner(body, response, session)

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


async def register_first_owner(
    body: RegisterRequest,
    response: Response,
    session: AsyncSession,
) -> SessionUserResponse:
    """Atomically let the reserved code create the one initial group owner."""
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": OWNER_CLAIM_LOCK_ID},
        )

    if await session.scalar(select(Group.id).limit(1)) is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "OWNER_ALREADY_CLAIMED",
                "message": "The JEDI group already has an owner.",
            },
        )
    if await session.scalar(
        select(User.id).where(func.lower(User.email) == body.email)
    ) is not None:
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
        group = Group(name="JEDI", owner_id=user.id)
        session.add(group)
        await session.flush()
        session.add(GroupMember(group_id=group.id, user_id=user.id))
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "OWNER_ALREADY_CLAIMED",
                "message": "The JEDI group already has an owner.",
            },
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

    initialized_shared_profile = False
    if (
        context.group.owner_id == user.id
        and context.group.active_profile_version_id is None
    ):
        shared_profile = await session.scalar(
            select(ProfileVersion).where(
                ProfileVersion.content_hash == normalized["content_hash"]
            )
        )
        if shared_profile is None:
            shared_profile = ProfileVersion(active=False, **normalized)
            session.add(shared_profile)
            await session.flush()
        await session.execute(
            update(ProfileVersion)
            .where(ProfileVersion.id != shared_profile.id)
            .values(active=False)
        )
        shared_profile.active = True
        context.group.active_profile_version_id = shared_profile.id
        initialized_shared_profile = True

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
    return OnboardingResult(
        **state.model_dump(),
        replayed=replayed and not initialized_shared_profile,
        initialized_shared_profile=initialized_shared_profile,
        message=(
            "Your profile was saved and activated as the shared ranking profile."
            if initialized_shared_profile
            else (
                "Your profile is saved for future personalization. "
                "JEDI v1 currently uses the group ranking profile."
            )
        ),
    )


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
