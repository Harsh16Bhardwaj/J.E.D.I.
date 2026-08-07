import logging
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.middleware import RequestContextMiddleware


def test_vercel_entrypoint_uses_one_model_runtime_singleton() -> None:
    backend_root = Path(__file__).parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import main; "
                "assert main.health.model_runtime is main.models.model_runtime; "
                "assert main.health.model_runtime is main.operations.model_runtime"
            ),
        ],
        cwd=backend_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_unhandled_errors_are_generic_and_do_not_log_secrets(
    caplog,
) -> None:
    secret = "secret-that-must-not-appear"
    test_app = FastAPI()
    test_app.add_middleware(RequestContextMiddleware)

    @test_app.get("/api/explode")
    async def explode() -> None:
        raise RuntimeError(secret)

    with caplog.at_level(logging.INFO, logger="jedi.requests"):
        response = TestClient(test_app, raise_server_exceptions=False).get(
            "/api/explode"
        )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["error"]["requestId"] == response.headers["x-request-id"]
    assert secret not in caplog.text
    assert secret not in response.text
