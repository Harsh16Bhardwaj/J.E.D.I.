# ruff: noqa: F401, F811

from uuid import uuid4

from backend.tests.test_product_api import create_test_job, login, product_client


def test_stage_move_replay_stale_guard_and_terminal_correction(product_client):
    login(product_client)
    _, job_id = create_test_job(product_client)
    path = f"/api/jobs/{job_id}/application-events"
    preparing = {
        "applicationStatus": "PREPARING",
        "expectedStatus": "NOT_STARTED",
        "requestId": str(uuid4()),
    }
    first = product_client.post(path, json=preparing)
    assert first.status_code == 201, first.text
    assert product_client.post(path, json=preparing).json()["id"] == first.json()["id"]
    assert (
        product_client.post(
            path, json={**preparing, "applicationStatus": "APPLIED"}
        ).status_code
        == 409
    )
    assert (
        product_client.post(
            path, json={**preparing, "requestId": str(uuid4())}
        ).status_code
        == 409
    )

    closed = product_client.post(
        path,
        json={
            "applicationStatus": "WITHDRAWN",
            "expectedStatus": "PREPARING",
            "requestId": str(uuid4()),
        },
    )
    assert closed.status_code == 201, closed.text
    reopen = {
        "applicationStatus": "PREPARING",
        "expectedStatus": "WITHDRAWN",
        "requestId": str(uuid4()),
    }
    assert product_client.post(path, json=reopen).status_code == 409
    assert (
        product_client.post(path, json={**reopen, "correction": True}).status_code
        == 422
    )
    corrected = product_client.post(
        path,
        json={
            **reopen,
            "correction": True,
            "notes": "Withdrawal was recorded in error.",
        },
    )
    assert corrected.status_code == 201, corrected.text
    assert corrected.json()["eventType"] == "CORRECTION"
    assert len(product_client.get(path).json()) == 3

    application = product_client.get(f"/api/jobs/{job_id}/application").json()
    assert application["status"] == "PREPARING"
    assert application["closedAt"] is None
    stale = product_client.post(
        path,
        json={
            "applicationStatus": "APPLIED",
            "expectedStatus": "PREPARING",
            "expectedUpdatedAt": "2000-01-01T00:00:00Z",
            "requestId": str(uuid4()),
        },
    )
    assert stale.status_code == 409
