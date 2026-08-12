from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_local_frontend_preflight_is_allowed() -> None:
    response = client.options(
        "/v1/score",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "content-type,x-jedi-timestamp,x-jedi-signature"
            ),
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "http://localhost:3000"
    )
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_unlisted_origin_is_not_allowed() -> None:
    response = client.options(
        "/v1/score",
        headers={
            "Origin": "https://not-approved.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_local_ip_frontend_preflight_is_allowed() -> None:
    response = client.options(
        "/api/scraper/config",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "http://127.0.0.1:3000"
    )
