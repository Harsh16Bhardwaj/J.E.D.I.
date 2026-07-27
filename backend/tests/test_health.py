import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_service_metadata() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "foundation"
    assert response.json()["docs_url"] == "/docs"


def test_live_health() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"service": "jedi-ml", "status": "ok"}


def test_ready_health() -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"service": "jedi-ml", "status": "ready"}


def test_openapi_document_is_exposed() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "JEDI ML Service"
    assert "/v1/score" in response.json()["paths"]


@pytest.mark.parametrize(
    ("route", "payload", "message"),
    [
        (
            "/v1/normalize",
            {
                "schema_version": "foundation-v1",
                "source_name": "foundation-source",
                "jobs": [{"title": "Foundation test job"}],
            },
            "Job normalization will be added in the ML integration phase.",
        ),
        (
            "/v1/embed",
            {"texts": ["Foundation test job."]},
            "Semantic embeddings will be added in the ML integration phase.",
        ),
        (
            "/v1/score",
            {
                "batch_id": "batch-foundation",
                "profile_version_id": "profile-foundation",
                "candidates": [
                    {
                        "canonical_job_id": "job-foundation",
                        "feature_snapshot": {},
                        "description": "Foundation test job.",
                    }
                ],
            },
            "Model inference will be added in the ML integration phase.",
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
