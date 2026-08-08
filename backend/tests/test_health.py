import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.config import Settings
from backend.main import app
from backend.routers.health import check_readiness

client = TestClient(app)


def test_service_metadata() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["docs_url"] == "/docs"


def test_live_health() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"service": "jedi-ml", "status": "ok"}


def test_vercel_service_prefix_reaches_the_same_routes() -> None:
    response = client.get("/svc/ml/health/live")

    assert response.status_code == 200
    assert response.json() == {"service": "jedi-ml", "status": "ok"}


def test_ready_health() -> None:
    app.dependency_overrides[check_readiness] = lambda: True
    try:
        response = client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(check_readiness, None)

    assert response.status_code == 200
    assert response.json() == {"service": "jedi-ml", "status": "ready"}


def test_ready_health_hides_database_failures() -> None:
    app.dependency_overrides[check_readiness] = lambda: False
    try:
        response = client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(check_readiness, None)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert response.json()["error"]["message"] == "Service is not ready."


def test_production_settings_reject_unsafe_values() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql://USER:PASSWORD@HOST/database",
            cors_origins="http://localhost:3000",
            session_secret="short",
            ml_service_secret="short",
            session_cookie_secure=False,
        )

    safe = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql://owner:strong@database.internal/jedi",
        cors_origins="https://jedi.example.net",
        session_secret="s" * 64,
        ml_service_secret="m" * 64,
        session_cookie_secure=True,
    )
    assert safe.app_env == "production"

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql://owner:strong@database.internal/jedi",
            cors_origins="https://jedi.example.net",
            session_secret="s" * 64,
            owner_registration_code="TOO-SHORT",
            ml_service_secret="m" * 64,
            session_cookie_secure=True,
        )

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql://owner:strong@database.internal/jedi",
            cors_origins="https://jedi.example.net",
            session_secret="s" * 64,
            ml_service_secret="m" * 64,
            session_cookie_secure=True,
            gmail_smtp_user="sender@example.net",
            cron_secret="c" * 64,
        )

    email_safe = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql://owner:strong@database.internal/jedi",
        cors_origins="https://jedi.example.net",
        session_secret="s" * 64,
        ml_service_secret="m" * 64,
        session_cookie_secure=True,
        gmail_smtp_user="sender@example.net",
        gmail_smtp_app_password="app-password",
        cron_secret="c" * 64,
    )
    assert email_safe.gmail_smtp_user == "sender@example.net"


def test_request_ids_and_private_response_headers() -> None:
    response = client.get(
        "/api/auth/session",
        headers={"X-Request-ID": "test-request-123"},
    )

    assert response.status_code == 401
    assert response.headers["x-request-id"] == "test-request-123"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_openapi_document_is_exposed() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "JEDI ML Service"
    assert "/v1/score" in response.json()["paths"]
    schemes = response.json()["components"]["securitySchemes"]
    assert "HTTPBearer" in schemes
    assert "APIKeyCookie" in schemes
    assert "JEDI service token" in schemes


@pytest.mark.parametrize(
    ("route", "payload", "message"),
    [
        (
            "/v1/embed",
            {"texts": ["Foundation test job."]},
            "Semantic embeddings will be added in the ML integration phase.",
        ),
    ],
)
def test_ml_routes_are_intentional_placeholders(
    route: str,
    payload: dict[str, object],
    message: str,
) -> None:
    response = client.post(route, json=payload)

    assert response.status_code == 501
    assert response.json() == {
        "status": "not_implemented",
        "route": route,
        "message": message,
    }


def test_scoring_route_requires_service_authentication() -> None:
    response = client.post(
        "/v1/score",
        json={
            "batchId": "batch-foundation",
            "processingRunId": "run-foundation",
            "modelVersionId": "model-foundation",
        },
    )
    assert response.status_code == 401
