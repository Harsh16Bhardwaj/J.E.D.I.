"""Local command for creating or updating JEDI's private login.

This module is deliberately *outside* the router:

- It is executed from a trusted terminal with ``npm run user:bootstrap``.
- It does not expose an HTTP registration endpoint.
- It can create the first User row before anyone is able to log in.
"""

# Standard library:
# - asyncio starts the async database workflow from a normal command-line process.
# - getpass reads a password without echoing it in the terminal.
import asyncio
from getpass import getpass

# SQLAlchemy's select constructs the database lookup.
from sqlalchemy import select

# Application imports:
# - hash_password is the exact hasher that the login route verifies.
# - SessionFactory creates sessions; engine owns pooled connections.
# - clean_text normalizes Unicode, trimming and whitespace.
from backend.auth import hash_password
from backend.database import (
    Group,
    GroupMember,
    ModelVersion,
    ProfileVersion,
    SessionFactory,
    User,
    engine,
    utc_now,
)
from backend.services.product import clean_text


async def upsert_user(email: str, password: str) -> tuple[str, bool]:
    """Create a private user or replace the password hash for an existing email."""

    # casefold is a Unicode-aware lowercase operation. Login performs compatible
    # normalization, so letter casing does not create a second identity.
    normalized_email = clean_text(email).casefold()

    # This is intentionally lightweight validation for a private tool.
    if "@" not in normalized_email:
        raise ValueError("Enter a valid email address.")

    # Four characters is the current project rule, although a substantially
    # longer unique password is strongly recommended.
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters.")

    # ``async with`` guarantees the session is closed, even if an error occurs.
    async with SessionFactory() as session:
        # scalar returns the matching User object or None.
        user = await session.scalar(select(User).where(User.email == normalized_email))
        created = user is None

        if created:
            # Only the generated hash enters the ORM object/database.
            user = User(email=normalized_email, password_hash=hash_password(password))
            session.add(user)
            await session.flush()
        else:
            # Same email means password rotation, not a duplicate account.
            user.password_hash = hash_password(password)

        # A freshly migrated empty database has no owner to backfill. In that
        # case this trusted bootstrap command creates the default shared group
        # and marks its first user as already onboarded.
        membership = await session.scalar(
            select(GroupMember).where(GroupMember.user_id == user.id)
        )
        if membership is None:
            group = await session.scalar(select(Group).order_by(Group.created_at))
            if group is None:
                profile_id = await session.scalar(
                    select(ProfileVersion.id)
                    .where(ProfileVersion.active.is_(True))
                    .order_by(ProfileVersion.created_at.desc())
                )
                model_id = await session.scalar(
                    select(ModelVersion.id)
                    .where(ModelVersion.active.is_(True))
                    .order_by(ModelVersion.created_at.desc())
                )
                group = Group(
                    name="JEDI",
                    owner_id=user.id,
                    active_profile_version_id=profile_id,
                    active_model_version_id=model_id,
                )
                session.add(group)
                await session.flush()
            session.add(
                GroupMember(
                    group_id=group.id,
                    user_id=user.id,
                    onboarding_completed_at=(
                        utc_now() if group.owner_id == user.id else None
                    ),
                )
            )

        # commit makes the insert/update durable in PostgreSQL.
        await session.commit()

        # The caller prints the ID and whether this was creation or rotation.
        return user.id, created


async def main() -> None:
    """Prompt locally so neither plaintext passwords nor hashes enter shell history."""

    # Email is not secret, so ordinary input is appropriate.
    email = input("Private JEDI email: ")

    # Both password reads are hidden. The values live only in process memory.
    password = getpass("Password (4+ characters): ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        # SystemExit ends the CLI with a readable message and no traceback.
        raise SystemExit("Passwords do not match.")

    try:
        user_id, created = await upsert_user(email, password)
    except ValueError as error:
        # Convert expected input problems into short terminal messages.
        raise SystemExit(str(error)) from error
    finally:
        # A short-lived CLI should release its pooled database connections.
        await engine.dispose()

    action = "created" if created else "updated"
    print(f"Private user {action}: {user_id}")


# This guard distinguishes running the file from importing it in tests.
if __name__ == "__main__":
    # asyncio.run creates an event loop, runs main, then closes the loop.
    asyncio.run(main())
