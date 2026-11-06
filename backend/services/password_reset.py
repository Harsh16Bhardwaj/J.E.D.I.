"""Short-lived, single-use recovery credentials for registered JEDI users."""

import asyncio
import logging
from base64 import b32encode
from datetime import UTC, timedelta
from email.utils import make_msgid
from hashlib import sha256
from secrets import token_bytes

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from backend.auth import hash_password
from backend.config import Settings, get_settings
from backend.database import PasswordReset, User, utc_now
from backend.services.email import GmailSmtpTransport

RESET_LIFETIME = timedelta(minutes=15)
RESET_COOLDOWN = timedelta(minutes=5)
logger = logging.getLogger(__name__)


def mail_configured(settings: Settings) -> bool:
    return bool(
        settings.gmail_smtp_user.strip() and settings.gmail_smtp_app_password.strip()
    )


def token_digest(token: str) -> str:
    return sha256(token.encode()).hexdigest()


async def issue_reset(session: AsyncSession, email: str) -> tuple[str, str] | None:
    user = await session.scalar(
        select(User).where(func.lower(User.email) == email).with_for_update()
    )
    if user is None:
        return None
    now = utc_now()
    reset = await session.get(PasswordReset, user.id)
    if reset and reset.requested_at.replace(tzinfo=UTC) + RESET_COOLDOWN > now:
        return None
    # A 16-character code carries 80 bits of randomness.
    code = b32encode(token_bytes(10)).decode("ascii")
    if reset is None:
        reset = PasswordReset(user_id=user.id)
        session.add(reset)
    reset.token_hash = token_digest(code)
    reset.requested_at = now
    reset.expires_at = now + RESET_LIFETIME
    await session.commit()
    return user.email, code


async def consume_reset(
    session: AsyncSession, token: str, password: str, *, email: str | None = None
) -> str | None:
    digest = token_digest(token)
    user_id = await session.scalar(
        select(PasswordReset.user_id).where(PasswordReset.token_hash == digest)
    )
    if user_id is None:
        return None
    # Issue and consume always lock the user first, then inspect the reset row.
    user = await session.get(User, user_id, with_for_update=True)
    if user is None or (email is not None and user.email.casefold() != email):
        return None
    reset = await session.get(PasswordReset, user.id, populate_existing=True)
    if (
        reset is None
        or reset.token_hash != digest
        or reset.expires_at.replace(tzinfo=UTC) <= utc_now()
    ):
        return None
    user.password_hash = await run_in_threadpool(hash_password, password)
    user.session_version += 1
    reset.token_hash = None
    await session.commit()
    return user.email


async def send_recovery_mail(recipient: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not mail_configured(settings):
        return
    try:
        async with asyncio.timeout(25):
            await GmailSmtpTransport(settings).send_message(
                recipient, subject, body, make_msgid(domain="jedi")
            )
    except Exception as exc:
        logger.warning("recovery_email_failed error_type=%s", type(exc).__name__)
