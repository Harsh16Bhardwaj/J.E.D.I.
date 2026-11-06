# ruff: noqa: F401, F811

import asyncio
import re
from contextlib import aclosing
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

import pytest

from backend.config import get_settings
from backend.database import PasswordReset, get_session
from backend.services import password_reset
from backend.services.email import GmailSmtpTransport
from backend.tests.test_product_api import login, product_client

FORGOT = "/api/auth/forgot-password"
RESET = "/api/auth/reset-password"


@pytest.fixture
def mailbox(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "gmail_smtp_user", "sender@example.test")
    monkeypatch.setattr(settings, "gmail_smtp_app_password", "test-password")
    messages = []

    async def send(_transport, recipient, subject, body, message_id):
        messages.append((recipient, subject, body))
        return message_id

    monkeypatch.setattr(GmailSmtpTransport, "send_message", send)
    return messages


def recovery_code(message):
    body = message[2]
    assert "https://" not in body and "http://" not in body
    code = body.splitlines()[2]
    assert re.fullmatch(r"[A-Z2-7]{4}(?:-[A-Z2-7]{4}){3}", code)
    return code


def reset_body(code):
    return {
        "email": "owner@example.com",
        "code": code,
        "password": "new correct horse",
        "confirmPassword": "new correct horse",
    }


def test_reset_email_changes_password_and_revokes_old_sessions(product_client, mailbox):
    login(product_client)
    old_cookie = product_client.cookies.get(get_settings().session_cookie_name)
    missing = product_client.post(FORGOT, json={"email": "missing@example.test"})
    issued = product_client.post(
        FORGOT,
        json={"email": "OWNER@example.com"},
        headers={"Host": "untrusted.example.test"},
    )
    assert missing.status_code == issued.status_code == 202
    assert missing.json() == issued.json()
    assert (
        product_client.post(FORGOT, json={"email": "owner@example.com"}).json()
        == issued.json()
    )
    assert len(mailbox) == 1
    assert mailbox[0][0] == "owner@example.com"
    code = recovery_code(mailbox[0])
    assert code not in issued.text
    assert code.replace("-", "") not in issued.text

    mismatch = {**reset_body(code), "confirmPassword": "different password"}
    validation = product_client.post(RESET, json=mismatch)
    assert validation.status_code == 422
    assert code not in validation.text
    assert mismatch["password"] not in validation.text
    wrong_email = {**reset_body(code), "email": "friend@example.com"}
    assert product_client.post(RESET, json=wrong_email).status_code == 400
    normalized = reset_body(code.replace("-", " ").lower())
    assert product_client.post(RESET, json=normalized).status_code == 204
    assert product_client.post(RESET, json=reset_body(code)).status_code == 400
    assert len(mailbox) == 2
    assert "password was changed" in mailbox[1][1]
    assert (
        product_client.get(
            "/api/auth/session", headers={"Authorization": f"Bearer {old_cookie}"}
        ).status_code
        == 401
    )
    old_login = product_client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct horse"},
    )
    assert old_login.status_code == 401
    new_login = product_client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "new correct horse"},
    )
    assert new_login.status_code == 200


def test_reset_expiry_and_replacement(product_client, mailbox, monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr(password_reset, "utc_now", lambda: now)
    email = {"email": "owner@example.com"}
    assert product_client.post(FORGOT, json=email).status_code == 202
    first = recovery_code(mailbox[0])
    now += timedelta(minutes=6)
    assert product_client.post(FORGOT, json=email).status_code == 202
    replacement = recovery_code(mailbox[1])
    assert product_client.post(RESET, json=reset_body(first)).status_code == 400
    now += timedelta(minutes=15)
    assert product_client.post(RESET, json=reset_body(replacement)).status_code == 400
    login(product_client)


def test_previously_issued_reset_link_remains_usable(product_client, mailbox):
    token = token_urlsafe(32)
    now = datetime.now(UTC)

    async def store_previous_token():
        session_provider = product_client.app.dependency_overrides[get_session]
        async with aclosing(session_provider()) as sessions:
            session = await anext(sessions)
            session.add(
                PasswordReset(
                    user_id="user-1",
                    token_hash=password_reset.token_digest(token),
                    requested_at=now,
                    expires_at=now + timedelta(minutes=30),
                )
            )
            await session.commit()

    asyncio.run(store_previous_token())
    body = {
        "token": token,
        "password": "new correct horse",
        "confirmPassword": "new correct horse",
    }
    assert product_client.post(RESET, json=body).status_code == 204
    assert product_client.post(RESET, json=body).status_code == 400
    assert len(mailbox) == 1
    assert "password was changed" in mailbox[0][1]
