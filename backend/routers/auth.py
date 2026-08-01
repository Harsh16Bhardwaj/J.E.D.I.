"""FastAPI URL handlers for login, logout and session inspection.

Compare this file with ``backend.auth``:

- backend.auth contains reusable authentication logic and dependencies.
- backend.routers.auth connects that logic to concrete HTTP URLs.
"""

# Standard library: Annotated lets one type carry both its Python type and
# FastAPI dependency information.
from typing import Annotated

# Framework imports:
# - APIRouter groups related routes.
# - Response is the mutable outgoing HTTP response object.
# - SQLAlchemy's func/select build SQL safely.
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Application code supplies authentication logic, configuration, database
# models/sessions, and Pydantic request/response contracts.
from backend.auth import CurrentUser, verify_password
from backend.config import get_settings
from backend.database import User, get_session
from backend.schemas.group_access import SessionUserResponse
from backend.schemas.product import LoginRequest
from backend.services.group_access import session_response, set_session_cookie

# Every route below receives the /api/auth prefix. The tag groups these endpoints
# together in FastAPI's generated /docs page.
router = APIRouter(prefix="/api/auth", tags=["authentication"])

# This alias means: "an AsyncSession produced by get_session".
# FastAPI notices Depends and injects a session whenever a route asks for
# ``session: DatabaseSession``.
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


# The decorator registers POST /api/auth/login.
# response_model filters/validates returned data as UserResponse, ensuring a
# password hash can never accidentally appear in the JSON response.
@router.post("/login", response_model=SessionUserResponse)
async def login(
    # Because LoginRequest is a Pydantic model, FastAPI reads and validates the
    # JSON body before calling this function.
    body: LoginRequest,
    # Mutating Response lets us add a cookie while still returning a model.
    response: Response,
    # FastAPI opens this through get_session; callers do not construct it.
    session: DatabaseSession,
) -> SessionUserResponse:
    """Validate credentials, attach a signed cookie and return safe user data."""

    # body.email is trimmed and case-folded. func.lower makes the database side
    # case-insensitive too. scalar returns one User or None.
    user = await session.scalar(
        select(User).where(func.lower(User.email) == body.email.strip().casefold())
    )

    # Keep one generic message for both "email missing" and "wrong password".
    # This prevents an attacker from learning which email exists.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # The helper applies the same hardened cookie attributes used by
    # invite-based registration.
    set_session_cookie(response, user)
    return await session_response(session, user)


# The default success status would be 200; logout intentionally returns 204
# because there is no response body.
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Tell the client to remove its authentication cookie."""
    settings = get_settings()

    # Cookie deletion must use matching path/security attributes so the browser
    # targets the same cookie created by login.
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )


# CurrentUser is itself a dependency alias. Before this function runs, FastAPI
# verifies the token and loads the User from the database.
@router.get("/session", response_model=SessionUserResponse)
async def get_session_user(
    user: CurrentUser,
    session: DatabaseSession,
) -> SessionUserResponse:
    """Return the safe identity represented by the current session."""
    return await session_response(session, user)
