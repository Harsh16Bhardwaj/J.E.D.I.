# ruff: noqa: F401, F811

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from backend.config import get_settings
from backend.services import password_reset
from backend.services.email import GmailSmtpTransport
from backend.tests.test_product_api import login, product_client

FORGOT = "/api/auth/forgot-password"
RESET = "/api/auth/reset-password"


@pytest.fixture
def mailbox(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "password_reset_origin", "https://jedi.example.test")
    monkeypatch.setattr(settings, "gmail_smtp_user", "sender@example.test")
    monkeypatch.setattr(settings, "gmail_smtp_app_password", "test-password")
    messages = []

    async def send(_transport, recipient, subject, body, message_id):
        messages.append((recipient, subject, body))
        return message_id

    monkeypatch.setattr(GmailSmtpTransport, "send_message", send)
    return messages


def reset_token(message):
    url = urlsplit(message[2].splitlines()[2])
    assert url.netloc == "jedi.example.test"
    assert url.path == "/reset-password"
    assert not url.query
    return parse_qs(url.fragment)["token"][0]


def reset_body(token):
    return {
        "token": token,
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
    token = reset_token(mailbox[0])
    assert token not in issued.text

    mismatch = {**reset_body(token), "confirmPassword": "different password"}
    assert product_client.post(RESET, json=mismatch).status_code == 422
    assert product_client.post(RESET, json=reset_body(token)).status_code == 204
    assert product_client.post(RESET, json=reset_body(token)).status_code == 400
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
    first = reset_token(mailbox[0])
    now += timedelta(minutes=6)
    assert product_client.post(FORGOT, json=email).status_code == 202
    replacement = reset_token(mailbox[1])
    assert product_client.post(RESET, json=reset_body(first)).status_code == 400
    now += timedelta(minutes=31)
    assert product_client.post(RESET, json=reset_body(replacement)).status_code == 400
    login(product_client)
