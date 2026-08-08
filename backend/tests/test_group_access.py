import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.auth import hash_password
from backend.config import get_settings
from backend.database import (
    Base,
    EmailRecipient,
    Group,
    GroupInvitation,
    GroupMember,
    MemberProfile,
    ModelVersion,
    ProfileVersion,
    User,
    get_session,
)
from backend.main import app
from backend.routers.group_access import registration_database_error
from backend.services import group_access as group_access_service
from backend.services.group_access import invitation_hash


@pytest.fixture
def group_client() -> Iterator[tuple[TestClient, async_sessionmaker[AsyncSession]]]:
    settings = get_settings()
    original_secret = settings.session_secret
    original_owner_code = settings.owner_registration_code
    settings.session_secret = "test-session-secret-that-is-longer-than-32-bytes"
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def setup() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            owner = User(
                id="owner-1",
                email="owner@example.com",
                password_hash=hash_password("correct horse"),
            )
            profile = ProfileVersion(
                id="profile-1",
                content_hash="profile-hash",
                resume_text="Python backend engineer",
                preferred_titles=["Backend Engineer"],
                preferred_locations=["Remote"],
                preferred_skills=["Python", "FastAPI"],
                active=True,
            )
            model = ModelVersion(
                id="model-1",
                name="jedi-owner-model",
                content_hash="model-hash",
                artifact_manifest={},
                feature_schema_version="prepared-job-v1",
                active=True,
            )
            session.add_all([owner, profile, model])
            await session.flush()
            group = Group(
                id="group-1",
                name="JEDI",
                owner_id=owner.id,
                active_profile_version_id=profile.id,
                active_model_version_id=model.id,
            )
            session.add(group)
            await session.flush()
            session.add(
                GroupMember(
                    id="member-owner",
                    group_id=group.id,
                    user_id=owner.id,
                    onboarding_completed_at=datetime.now(UTC),
                )
            )
            await session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    asyncio.run(setup())
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client, session_factory
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())
    settings.session_secret = original_secret
    settings.owner_registration_code = original_owner_code


def login_owner(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct horse"},
    )
    assert response.status_code == 200
    return response.json()


def create_invite(client: TestClient) -> dict:
    response = client.post("/api/invitations")
    assert response.status_code == 201
    return response.json()


def test_group_routes_require_authentication(group_client) -> None:
    client, _ = group_client
    for method, path in (
        ("get", "/api/group"),
        ("get", "/api/invitations"),
        ("post", "/api/invitations"),
        ("get", "/api/onboarding"),
        ("post", "/api/onboarding"),
    ):
        response = getattr(client, method)(path)
        assert response.status_code == 401


def test_session_and_invitation_lifecycle(group_client) -> None:
    client, _ = group_client
    session = login_owner(client)
    assert session["group"] == {"id": "group-1", "name": "JEDI"}
    assert session["isGroupOwner"] is True
    assert session["onboardingComplete"] is True

    first = create_invite(client)
    assert len(first["code"]) == 5
    assert first["code"].isalnum() and first["code"] == first["code"].upper()
    second = create_invite(client)
    items = client.get("/api/invitations").json()
    assert all("code" not in item for item in items)
    assert next(item for item in items if item["id"] == first["id"])["revokedAt"]
    assert (
        next(item for item in items if item["id"] == second["id"])["revokedAt"] is None
    )

    revoked = client.delete(f"/api/invitations/{second['id']}")
    assert revoked.status_code == 204


def test_reusable_invite_registers_members_and_rejects_owner_actions(
    group_client,
) -> None:
    client, _ = group_client
    login_owner(client)
    invitation = create_invite(client)
    client.post("/api/auth/logout")

    first = client.post(
        "/api/auth/register",
        json={
            "inviteCode": invitation["code"].lower(),
            "email": "first@example.com",
            "password": "first-password",
        },
    )
    assert first.status_code == 201
    assert first.json()["onboardingComplete"] is False
    assert first.json()["isGroupOwner"] is False
    assert client.post("/api/invitations").status_code == 403
    client.post("/api/auth/logout")

    second = client.post(
        "/api/auth/register",
        json={
            "inviteCode": invitation["code"],
            "email": "second@example.com",
            "password": "second-password",
        },
    )
    assert second.status_code == 201
    duplicate = client.post(
        "/api/auth/register",
        json={
            "inviteCode": invitation["code"],
            "email": "second@example.com",
            "password": "different-password",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "EMAIL_EXISTS"


def test_revoked_expired_and_unknown_invites_have_stable_errors(
    group_client,
) -> None:
    client, session_factory = group_client
    login_owner(client)
    revoked = create_invite(client)
    assert client.delete(f"/api/invitations/{revoked['id']}").status_code == 204
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/register",
        json={
            "inviteCode": revoked["code"],
            "email": "a@example.com",
            "password": "password-a",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVITE_REVOKED"

    login_owner(client)
    expired = create_invite(client)

    async def expire() -> None:
        async with session_factory() as session:
            item = await session.get(GroupInvitation, expired["id"])
            assert item
            item.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()

    asyncio.run(expire())
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/register",
        json={
            "inviteCode": expired["code"],
            "email": "b@example.com",
            "password": "password-b",
        },
    )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "INVITE_EXPIRED"
    unknown = client.post(
        "/api/auth/register",
        json={
            "inviteCode": "ZZZZZ",
            "email": "c@example.com",
            "password": "password-c",
        },
    )
    assert unknown.status_code == 401
    assert unknown.json()["error"]["code"] == "INVITE_INVALID"


def test_onboarding_saves_profile_and_newsletter_recipient(group_client) -> None:
    client, session_factory = group_client
    login_owner(client)
    code = create_invite(client)["code"]
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/register",
            json={
                "inviteCode": code,
                "email": "friend@example.com",
                "password": "friend-password",
            },
        ).status_code
        == 201
    )

    state = client.get("/api/onboarding")
    assert state.status_code == 200
    assert state.json()["sharedProfile"]["id"] == "profile-1"
    assert state.json()["sharedModel"]["id"] == "model-1"
    invalid = client.post(
        "/api/onboarding",
        json={
            "resumeText": "Python engineer",
            "preferredTitles": [],
            "preferredLocations": [],
            "preferredSkills": [],
            "experienceMinYears": 3,
            "experienceMaxYears": 1,
        },
    )
    assert invalid.status_code == 422

    payload = {
        "resumeText": "  Python   API engineer  ",
        "preferredTitles": ["Backend Engineer", "backend engineer"],
        "preferredLocations": ["Remote"],
        "preferredSkills": ["Python", "FastAPI"],
        "experienceMinYears": 0,
        "experienceMaxYears": 2,
        "salaryMin": 800000,
        "salaryMax": 4000000,
        "salaryCurrency": "inr",
    }
    completed = client.post("/api/onboarding", json=payload)
    assert completed.status_code == 200
    assert completed.json()["rankingMode"] == "SHARED_GROUP_PROFILE"
    assert completed.json()["initializedSharedProfile"] is False
    assert completed.json()["sharedProfile"]["id"] == "profile-1"
    assert completed.json()["memberProfile"]["preferredTitles"] == ["Backend Engineer"]
    assert client.get("/api/auth/session").json()["onboardingComplete"] is True
    assert client.post("/api/onboarding", json=payload).json()["replayed"] is True

    async def counts() -> tuple[int, int, bool]:
        async with session_factory() as session:
            profiles = await session.scalar(
                select(func.count()).select_from(MemberProfile)
            )
            recipients = await session.scalar(
                select(func.count()).select_from(EmailRecipient)
            )
            linked_member = await session.scalar(select(EmailRecipient.group_member_id))
            registered_member = await session.scalar(
                select(GroupMember.id)
                .join(User, GroupMember.user_id == User.id)
                .where(User.email == "friend@example.com")
            )
            return (
                int(profiles or 0),
                int(recipients or 0),
                linked_member == registered_member,
            )

    assert asyncio.run(counts()) == (1, 1, True)


def test_group_member_limit_blocks_registration(group_client) -> None:
    client, session_factory = group_client
    login_owner(client)
    code = create_invite(client)["code"]

    async def fill_group() -> None:
        async with session_factory() as session:
            for index in range(49):
                user = User(
                    id=f"filler-{index}",
                    email=f"filler-{index}@example.com",
                    password_hash="unused",
                )
                session.add(user)
                await session.flush()
                session.add(GroupMember(group_id="group-1", user_id=user.id))
            await session.commit()

    asyncio.run(fill_group())
    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/register",
        json={
            "inviteCode": code,
            "email": "late@example.com",
            "password": "late-password",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GROUP_FULL"


def test_invitation_hash_never_matches_plaintext(group_client) -> None:
    client, session_factory = group_client
    login_owner(client)
    invitation = create_invite(client)

    async def stored_hash() -> str:
        async with session_factory() as session:
            item = await session.get(GroupInvitation, invitation["id"])
            assert item
            return item.code_hash

    saved = asyncio.run(stored_hash())
    assert saved == invitation_hash(invitation["code"])
    assert saved != invitation["code"]


def test_reserved_code_claims_the_only_group_owner(group_client) -> None:
    client, session_factory = group_client
    settings = get_settings()
    settings.owner_registration_code = "JEDIOWNER2026"

    async def clear_existing_owner() -> None:
        async with session_factory() as session:
            await session.execute(delete(GroupMember))
            await session.execute(delete(Group))
            await session.execute(delete(User))
            await session.execute(delete(ProfileVersion))
            await session.commit()

    asyncio.run(clear_existing_owner())
    claimed = client.post(
        "/api/auth/register",
        json={
            "inviteCode": "jediowner2026",
            "email": "new-owner@example.com",
            "password": "owner-password",
        },
    )
    assert claimed.status_code == 201
    assert claimed.json()["isGroupOwner"] is True
    assert claimed.json()["onboardingComplete"] is False

    onboarding = client.post(
        "/api/onboarding",
        json={
            "resumeText": "Python API owner",
            "preferredTitles": ["Backend Engineer"],
            "preferredLocations": ["Remote"],
            "preferredSkills": ["Python", "FastAPI"],
            "experienceMinYears": 0,
            "experienceMaxYears": 2,
            "salaryMin": 800000,
            "salaryMax": 4000000,
            "salaryCurrency": "INR",
        },
    )
    assert onboarding.status_code == 200
    assert onboarding.json()["initializedSharedProfile"] is True
    assert onboarding.json()["sharedProfile"] is not None
    assert onboarding.json()["replayed"] is False

    replay = client.post(
        "/api/auth/register",
        json={
            "inviteCode": "JEDIOWNER2026",
            "email": "second-owner@example.com",
            "password": "owner-password",
        },
    )
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "OWNER_ALREADY_CLAIMED"

    async def owner_counts() -> tuple[int, int, int, int, bool]:
        async with session_factory() as session:
            group = await session.scalar(select(Group))
            active_profile = await session.scalar(
                select(ProfileVersion).where(ProfileVersion.active.is_(True))
            )
            return (
                int(await session.scalar(select(func.count()).select_from(User)) or 0),
                int(await session.scalar(select(func.count()).select_from(Group)) or 0),
                int(
                    await session.scalar(select(func.count()).select_from(GroupMember))
                    or 0
                ),
                int(
                    await session.scalar(
                        select(func.count()).select_from(ProfileVersion)
                    )
                    or 0
                ),
                bool(
                    group
                    and active_profile
                    and group.active_profile_version_id == active_profile.id
                ),
            )

    assert asyncio.run(owner_counts()) == (1, 1, 1, 1, True)


def test_random_invitation_skips_a_reserved_five_character_code(
    group_client,
    monkeypatch,
) -> None:
    get_settings().owner_registration_code = "ABCDE"
    characters = iter("ABCDEFGHIJ")
    monkeypatch.setattr(
        group_access_service.secrets,
        "choice",
        lambda _alphabet: next(characters),
    )
    assert group_access_service.generate_invite_code() == "FGHIJ"


def test_long_owner_code_reports_missing_deployment_configuration(
    group_client,
) -> None:
    client, _ = group_client
    get_settings().owner_registration_code = ""
    response = client.post(
        "/api/auth/register",
        json={
            "inviteCode": "JEDIOWNER2026",
            "email": "owner@example.com",
            "password": "owner-password",
        },
    )
    assert response.status_code == 503
    assert (
        response.json()["error"]["code"]
        == "OWNER_REGISTRATION_NOT_CONFIGURED"
    )
    assert response.json()["error"]["requestId"]


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (
            OperationalError(
                "connect",
                {},
                Exception("password authentication failed for user postgres"),
            ),
            "DATABASE_AUTH_FAILED",
        ),
        (
            OperationalError(
                "connect",
                {},
                Exception("project has exceeded the data transfer quota"),
            ),
            "DATABASE_QUOTA_EXCEEDED",
        ),
        (
            OperationalError(
                "connect",
                {},
                Exception("getaddrinfo failed"),
            ),
            "DATABASE_HOST_UNREACHABLE",
        ),
        (
            ProgrammingError(
                "select",
                {},
                Exception('relation "GroupInvitation" does not exist'),
            ),
            "DATABASE_MIGRATION_REQUIRED",
        ),
        (
            OperationalError("connect", {}, Exception("connection timed out")),
            "DATABASE_UNAVAILABLE",
        ),
    ],
)
def test_registration_database_errors_are_specific(
    exception,
    expected_code: str,
) -> None:
    error = registration_database_error(exception)
    assert error.status_code == 503
    assert error.detail["code"] == expected_code
    assert "postgres" not in error.detail["message"].casefold()
