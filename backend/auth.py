"""Reusable authentication building blocks.

This file is *not* a FastAPI router. It does not define URLs.
Instead, it contains the lower-level functions that route handlers reuse:

1. Hash and verify passwords.
2. Create and decode signed session tokens.
3. Resolve the currently logged-in database user.
4. Protect internal worker routes with a separate service secret.
"""

# Standard-library tools for timestamps, safe secret comparison and type hints.
from datetime import UTC, datetime, timedelta
from getpass import getpass
from hmac import compare_digest
from typing import Annotated

# Third-party packages:
# - jwt signs and verifies the session token.
# - FastAPI classes describe dependencies and HTTP errors.
# - pwdlib performs slow, one-way password hashing.
# - SQLAlchemy executes the database query for the current user.
import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import (
    APIKeyCookie,
    APIKeyHeader,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import User, get_session

# PasswordHash.recommended() selects pwdlib's recommended secure hasher.
# The result is reusable; creating it does not hash a password yet.
password_hash = PasswordHash.recommended()

# These security scheme objects tell FastAPI how credentials can arrive.
# auto_error=False is important: a missing value becomes None instead of causing
# an immediate error. get_current_user can therefore try Bearer auth *or* cookie
# auth and produce one consistent error if neither exists.
bearer_scheme = HTTPBearer(auto_error=False)
cookie_scheme = APIKeyCookie(name="jedi_session", auto_error=False)

# Internal workers do not log in as the private user. They send a dedicated
# X-JEDI-SERVICE-TOKEN header, documented separately in OpenAPI.
service_token_scheme = APIKeyHeader(
    name="X-JEDI-SERVICE-TOKEN",
    scheme_name="JEDI service token",
    description="Worker-only secret. User sessions do not authorize internal routes.",
    auto_error=False,
)


def hash_password(password: str) -> str:
    """Turn plaintext into a one-way encoded hash suitable for the database.

    Salting and algorithm parameters are embedded in the returned string.
    The original password cannot be recovered from it.
    """
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    """Check plaintext against a stored hash without decrypting anything."""
    try:
        # pwdlib reads the algorithm/salt parameters from ``encoded``.
        return password_hash.verify(password, encoded)
    except (ValueError, TypeError):
        # A malformed/old database value should behave like a wrong password,
        # not crash the login endpoint or reveal internal details.
        return False


def create_session_token(user: User) -> str:
    """Create a signed JWT that identifies one authenticated User."""
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            # ``sub`` ("subject") is the stable database user ID.
            "sub": user.id,
            # Keeping the email in the token lets us detect account changes.
            "email": user.email,
            # ``iat`` records when the token was issued.
            "iat": now,
            # ``exp`` makes the token invalid after the configured lifetime.
            "exp": now + timedelta(days=settings.session_days),
        },
        # The server secret creates the signature. Never send this secret to a
        # browser or store it in source control.
        settings.session_secret,
        algorithm="HS256",
    )


def decode_session_token(token: str) -> dict:
    """Verify a JWT's signature/lifetime and return its claims dictionary."""
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.session_secret,
            # Explicitly allow only the algorithm used during creation.
            algorithms=["HS256"],
            # Reject even correctly signed tokens missing essential claims.
            options={"require": ["sub", "exp", "iat"]},
        )
    except jwt.PyJWTError as exc:
        # HTTPException stops the request and becomes the standard 401 JSON
        # envelope installed by backend.errors.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session.",
        ) from exc


def _bearer_token(authorization: str | None) -> str | None:
    """Parse a raw ``Authorization: Bearer ...`` value.

    The current dependency uses FastAPI's HTTPBearer object instead. This helper
    is retained as a small standalone parser for callers that only have a raw
    header string.
    """
    if not authorization:
        return None
    # partition always returns three strings and splits only at the first space.
    scheme, _, credentials = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not credentials:
        return None
    return credentials


async def get_current_user(
    # FastAPI supplies the live Request object automatically.
    request: Request,
    # Depends(get_session) opens a database session for this request and closes
    # it afterward. Annotated preserves AsyncSession as the Python type.
    session: Annotated[AsyncSession, Depends(get_session)],
    # Security(...) extracts an optional Authorization Bearer token and adds the
    # scheme to generated OpenAPI documentation.
    bearer: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer_scheme)
    ] = None,
    # This dependency extracts the optional jedi_session cookie.
    cookie_token: Annotated[str | None, Security(cookie_scheme)] = None,
) -> User:
    """Authenticate the request and return the current database User."""
    settings = get_settings()

    # Prefer an explicit Bearer token (useful for scripts), otherwise use the
    # browser/Postman cookie. request.cookies is a final defensive fallback.
    token = (
        (bearer.credentials if bearer else None)
        or cookie_token
        or request.cookies.get(settings.session_cookie_name)
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    # Signature and expiry are checked before trusting any token data.
    payload = decode_session_token(token)

    # A valid token is not enough by itself: the user must still exist.
    user = await session.scalar(select(User).where(User.id == payload["sub"]))
    token_email = str(payload.get("email", "")).casefold()

    # Comparing the token email with the current database email invalidates
    # sessions if the identity was removed or materially changed.
    if user is None or user.email.casefold() != token_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session user no longer exists.",
        )
    return user


# This is a reusable FastAPI dependency *type alias*.
# A route parameter written as ``user: CurrentUser`` causes FastAPI to call
# get_current_user first. If it succeeds, the parameter receives a User object.
CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_service_token(
    # Security reads X-JEDI-SERVICE-TOKEN according to service_token_scheme.
    token: Annotated[str | None, Security(service_token_scheme)] = None,
) -> None:
    """Authorize an internal worker using a dedicated constant-time secret."""
    expected = get_settings().ml_service_secret
    supplied = token or ""

    # compare_digest avoids timing differences that could leak how much of a
    # secret was correct. Encoding makes both operands the same bytes type.
    if not compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token.",
        )


# Internal routes declare ``_service: ServiceToken``. The return value is None;
# successful dependency execution itself is the authorization proof.
ServiceToken = Annotated[None, Depends(require_service_token)]


# This block runs only for ``python -m backend.auth``. Importing backend.auth
# from FastAPI does not execute it.
if __name__ == "__main__":
    # getpass hides typed characters so plaintext does not appear on screen.
    first = getpass("Password: ")
    second = getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords do not match.")
    # This utility prints a hash, never the plaintext password.
    print(hash_password(first))
