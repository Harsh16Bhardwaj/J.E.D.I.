# ruff: noqa: F401, F811

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from threading import Event
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.routers import scraper as scraper_router
from backend.services.scraper import FetchResult, SourceSpec
from backend.tests.test_product_api import login, product_client  # noqa: F811


def scraper_job(index: int = 1) -> dict:
    return {
        "companyName": "Example Labs",
        "roleTitle": "Backend Engineer",
        "roleFamily": "backend",
        "seniority": None,
        "location": "Remote - India",
        "workMode": "remote",
        "employmentType": "full-time",
        "description": (
            "Build production Python APIs and reliable backend services. "
            "Own tests, observability, deployment, documentation, "
            "and incident response. "
            "Collaborate with product and engineering teammates in India. "
        )
        * 3
        + f" Vacancy identifier {index}.",
        "skills": ["python"],
        "experienceMinYears": 1,
        "experienceMaxYears": 3,
        "salaryMin": None,
        "salaryMax": None,
        "salaryCurrency": None,
        "salaryPeriod": None,
        "postedAt": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "applicationDeadline": None,
        "canApplyNow": True,
        "applyUrl": f"https://jobs.example.test/backend-{index}",
        "__dateEvidence": "JSON_LD_DATE_POSTED",
    }


async def fake_fetch(_source, _config, **_kwargs) -> FetchResult:
    return FetchResult(jobs=[scraper_job()], bright_data_used=0)


def configure_test_sources(monkeypatch, **changes):
    seeds = (
        {
            "name": "Example Labs",
            "ats_type": "greenhouse",
            "domain_hint": "boards.greenhouse.io",
            "board_token": "example",
        },
        {
            "name": "Example Lever",
            "ats_type": "lever",
            "domain_hint": "jobs.lever.co",
            "board_token": "example-lever",
        },
    )
    config = replace(
        scraper_router.load_scraper_config(), seed_sources=seeds, **changes
    )
    monkeypatch.setattr(scraper_router, "load_scraper_config", lambda: config)
    monkeypatch.setattr(
        scraper_router,
        "get_settings",
        lambda: SimpleNamespace(
            bright_data_api_key="test-key",
            bright_data_serp_zone="test-serp",
            bright_data_unlocker_zone="",
        ),
    )
    return config


def advance_to_review(client: TestClient, run_id: str) -> dict:
    detail: dict = {}
    for _ in range(20):
        response = client.post(f"/api/scraper/runs/{run_id}/advance")
        assert response.status_code == 200, response.text
        detail = response.json()
        if detail["status"] in {"REVIEW_READY", "FAILED"}:
            return detail
    raise AssertionError("scraper run did not reach review")


def test_scraper_owner_workflow_imports_normalizes_without_ranking(
    product_client: TestClient, monkeypatch
) -> None:
    assert product_client.get("/api/scraper/config").status_code == 401
    login(product_client)
    configure_test_sources(monkeypatch)
    config = product_client.get("/api/scraper/config")
    assert config.status_code == 200
    assert config.json()["targetJobCount"] == 60

    monkeypatch.setattr(scraper_router, "fetch_source_jobs", fake_fetch)

    created = product_client.post("/api/scraper/runs")
    assert created.status_code == 201
    run_id = created.json()["id"]
    detail = advance_to_review(product_client, run_id)
    assert detail["status"] == "REVIEW_READY"
    assert detail["validCount"] == 1
    stats = product_client.get(f"/api/scraper/runs/{run_id}/stats").json()
    assert {board["name"] for board in stats["byBoard"]} == {
        "Example Labs",
        "Example Lever",
    }
    assert sum(board["jobsSeen"] for board in stats["byBoard"]) == 2
    assert sum(board["uniqueCandidates"] for board in stats["byBoard"]) == 1
    assert sum(board["importable"] for board in stats["byBoard"]) == 1
    assert stats["importedJobs"] is None
    candidates = product_client.get(
        f"/api/scraper/runs/{run_id}/candidates?page=1&pageSize=100"
    ).json()["items"]
    candidate_id = next(item["id"] for item in candidates if item["schemaValid"])

    deselected = product_client.patch(
        f"/api/scraper/runs/{run_id}/selection",
        json={"candidateIds": [candidate_id], "selected": False},
    )
    assert deselected.status_code == 200
    assert deselected.json()["selectedCount"] == 0
    selected = product_client.patch(
        f"/api/scraper/runs/{run_id}/selection",
        json={"candidateIds": [candidate_id], "selected": True},
    )
    assert selected.json()["selectedCount"] == 1

    imported = product_client.post(
        f"/api/scraper/runs/{run_id}/import", json={"confirmPartial": False}
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["run"]["status"] == "IMPORTED"
    assert body["batch"]["jobCount"] == 1
    stats = product_client.get(f"/api/scraper/runs/{run_id}/stats").json()
    assert stats["importedJobs"] == 1
    batch = product_client.get(f"/api/batches/{body['batch']['batchId']}").json()
    assert batch["batch"]["status"] == "NORMALIZED"
    assert batch["preparedCount"] == 1
    assert batch["batch"]["rankedAt"] is None
    replayed = product_client.post(
        f"/api/scraper/runs/{run_id}/import", json={"confirmPartial": False}
    )
    assert replayed.status_code == 200
    assert replayed.json()["batch"]["replayed"] is True
    assert replayed.json()["batch"]["batchId"] == body["batch"]["batchId"]


def test_import_worker_advances_only_owner_approved_runs(
    product_client: TestClient, monkeypatch
) -> None:
    login(product_client)
    configure_test_sources(monkeypatch)
    monkeypatch.setattr(scraper_router, "fetch_source_jobs", fake_fetch)
    run_id = product_client.post("/api/scraper/runs").json()["id"]
    assert advance_to_review(product_client, run_id)["status"] == "REVIEW_READY"
    worker = "/api/scraper/internal/import-tick"
    token = {"X-JEDI-SERVICE-TOKEN": get_settings().ml_service_secret}
    assert product_client.post(worker).status_code == 401
    assert product_client.post(worker, headers=token).json() is None
    run = f"/api/scraper/runs/{run_id}"
    assert product_client.post(f"{run}/queue-import", json={}).status_code == 202
    assert product_client.post("/api/auth/logout").status_code == 204

    linked = product_client.post(worker, headers=token)
    assert linked.status_code == 200, linked.text
    checkpoint = linked.json()
    assert checkpoint["runId"] == run_id
    assert checkpoint["status"] == "NORMALIZING"
    assert checkpoint["importedBatchId"]
    done = product_client.post(worker, headers=token)
    assert done.json() == {**checkpoint, "status": "IMPORTED"}
    assert product_client.post(worker, headers=token).json() is None

    login(product_client)
    batch = product_client.get(f"/api/batches/{checkpoint['importedBatchId']}").json()
    assert batch["batch"]["status"] == "NORMALIZED"
    assert batch["batch"]["rankedAt"] is None


def test_scraper_import_resumes_at_batch_checkpoint_after_normalization_failure(
    product_client: TestClient, monkeypatch
) -> None:
    login(product_client)
    configure_test_sources(monkeypatch)
    monkeypatch.setattr(scraper_router, "fetch_source_jobs", fake_fetch)
    run_id = product_client.post("/api/scraper/runs").json()["id"]
    assert advance_to_review(product_client, run_id)["status"] == "REVIEW_READY"
    path = f"/api/scraper/runs/{run_id}"
    queued = product_client.post(f"{path}/queue-import", json={})
    assert queued.status_code == 202, queued.text
    assert queued.json()["status"] == "IMPORTING"
    assert queued.json()["importedBatchId"] is None
    assert product_client.patch(
        f"{path}/selection/all", json={"selected": False}
    ).status_code == 409

    ingest = scraper_router.ingest_batch

    async def fail_before_linking(*args, **kwargs):
        await ingest(*args, **kwargs)
        raise TimeoutError

    monkeypatch.setattr(scraper_router, "ingest_batch", fail_before_linking)
    failed_ingest = product_client.post(f"{path}/advance-import")
    assert failed_ingest.status_code == 200, failed_ingest.text
    assert failed_ingest.json()["status"] == "REVIEW_READY"
    assert failed_ingest.json()["importedBatchId"] is None
    assert product_client.get("/api/batches").json()["items"] == []
    monkeypatch.setattr(scraper_router, "ingest_batch", ingest)
    assert product_client.post(f"{path}/queue-import", json={}).status_code == 202

    step = product_client.post(f"{path}/advance-import")
    assert step.status_code == 200, step.text
    assert step.json()["status"] == "NORMALIZING"
    batch_id = step.json()["importedBatchId"]
    assert product_client.get(path).json()["importedBatchId"] == batch_id

    normalize = scraper_router.normalize_batch_service

    async def fail_after_writing(*args, **kwargs):
        await normalize(*args, **kwargs)
        raise TimeoutError

    monkeypatch.setattr(scraper_router, "normalize_batch_service", fail_after_writing)
    failed = product_client.post(f"{path}/advance-import")
    assert failed.status_code == 200, failed.text
    assert failed.json()["status"] == "NORMALIZATION_FAILED"
    assert failed.json()["importedBatchId"] == batch_id
    assert "timed out" in failed.json()["errorMessage"]
    batch = product_client.get(f"/api/batches/{batch_id}").json()
    assert batch["preparedCount"] == 0
    assert batch["batch"]["status"] == "READY"

    monkeypatch.setattr(scraper_router, "normalize_batch_service", normalize)
    assert product_client.post(f"{path}/queue-import", json={}).json()["status"] == (
        "NORMALIZING"
    )
    assert product_client.post(f"{path}/advance-import").json()["status"] == "IMPORTED"
    assert product_client.post(f"{path}/advance-import").json()["importedBatchId"] == (
        batch_id
    )
    batch = product_client.get(f"/api/batches/{batch_id}").json()
    assert batch["preparedCount"] == 1
    assert batch["batch"]["status"] == "NORMALIZED"


def test_scraper_partial_run_requires_confirmation(
    product_client: TestClient, monkeypatch
) -> None:
    login(product_client)
    configure_test_sources(monkeypatch)

    async def partial_fetch(source, config, **kwargs) -> FetchResult:
        if source.ats_type == "lever":
            raise RuntimeError("provider unavailable")
        return await fake_fetch(source, config, **kwargs)

    monkeypatch.setattr(scraper_router, "fetch_source_jobs", partial_fetch)
    run_id = product_client.post("/api/scraper/runs").json()["id"]
    detail = advance_to_review(product_client, run_id)
    assert detail["failedSourceCount"] == 1
    stats = product_client.get(f"/api/scraper/runs/{run_id}/stats").json()
    failed = next(board for board in stats["byBoard"] if board["atsType"] == "lever")
    assert failed["status"] == "FAILED"
    assert failed["errorMessage"] == "provider unavailable"
    assert failed["jobsSeen"] == 0
    sources = product_client.get("/api/scraper/sources").json()
    lever = next(source for source in sources if source["atsType"] == "lever")
    assert [
        (outcome["runId"], outcome["status"], outcome["errorMessage"])
        for outcome in lever["recentRuns"]
    ] == [(run_id, "FAILED", "provider unavailable")]

    blocked = product_client.post(
        f"/api/scraper/runs/{run_id}/import", json={"confirmPartial": False}
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "PARTIAL_CONFIRMATION_REQUIRED"
    approved = product_client.post(
        f"/api/scraper/runs/{run_id}/import", json={"confirmPartial": True}
    )
    assert approved.status_code == 200


def test_scraper_retries_failed_sources(
    product_client: TestClient, monkeypatch
) -> None:
    login(product_client)
    configure_test_sources(monkeypatch)
    attempts = {"lever": 0}

    async def flaky_fetch(source, config, **kwargs) -> FetchResult:
        if source.ats_type == "lever" and attempts["lever"] == 0:
            attempts["lever"] += 1
            raise RuntimeError("temporary provider failure")
        return await fake_fetch(source, config, **kwargs)

    monkeypatch.setattr(scraper_router, "fetch_source_jobs", flaky_fetch)
    run_id = product_client.post("/api/scraper/runs").json()["id"]
    first = advance_to_review(product_client, run_id)
    assert first["failedSourceCount"] == 1

    retried = product_client.post(f"/api/scraper/runs/{run_id}/retry-failed")
    assert retried.status_code == 200
    finished = advance_to_review(product_client, run_id)
    assert finished["failedSourceCount"] == 0
    assert attempts["lever"] == 1


@pytest.mark.parametrize("recovers", [True, False])
def test_scraper_defers_rate_limited_board_and_caps_automatic_retries(
    product_client: TestClient, monkeypatch, recovers: bool
) -> None:
    login(product_client)
    configure_test_sources(monkeypatch, concurrent_sources=1, max_retries=2)
    now = datetime.now(UTC)
    calls = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)

    async def rate_limited_fetch(source, _config, **kwargs) -> FetchResult:
        calls.append((source.ats_type, kwargs["allow_unlocker"]))
        if source.ats_type == "greenhouse":
            if recovers and len(calls) == 4:
                return FetchResult(jobs=[scraper_job(2)])
            request = httpx.Request("GET", "https://boards.greenhouse.io/example")
            retry_after = (
                format_datetime(now + timedelta(seconds=60), usegmt=True)
                if recovers
                else "60"
            )
            response = httpx.Response(
                429, request=request, headers={"Retry-After": retry_after}
            )
            response.raise_for_status()
        return FetchResult(jobs=[scraper_job()])

    monkeypatch.setattr(scraper_router, "datetime", Clock)
    monkeypatch.setattr(scraper_router, "fetch_source_jobs", rate_limited_fetch)
    run_id = product_client.post("/api/scraper/runs").json()["id"]
    path = f"/api/scraper/runs/{run_id}"

    def advance() -> dict:
        response = product_client.post(f"{path}/advance")
        assert response.status_code == 200, response.text
        return response.json()

    assert advance()["failedSourceCount"] == 0
    assert advance()["processedSourceCount"] == 1
    assert calls == [("greenhouse", True), ("lever", True)]
    summary = product_client.get(path).json()
    assert datetime.fromisoformat(summary["nextRetryAt"]) >= now + timedelta(seconds=59)
    assert advance()["status"] == "RUNNING"
    assert len(calls) == 2

    now += timedelta(seconds=61)
    assert advance()["failedSourceCount"] == 0
    assert calls[-1] == ("greenhouse", False)
    stats = product_client.get(f"{path}/stats").json()
    board = next(row for row in stats["byBoard"] if row["atsType"] == "greenhouse")
    assert board["status"] == "PENDING"
    assert board["retryCount"] == 2
    assert board["retryAt"]

    now += timedelta(seconds=61)
    finished = advance()
    assert finished["status"] == "REVIEW_READY"
    assert finished["failedSourceCount"] == (0 if recovers else 1)
    if recovers:
        stats = product_client.get(f"{path}/stats").json()
        board = next(row for row in stats["byBoard"] if row["atsType"] == "greenhouse")
        assert board["status"] == "SUCCEEDED"
        assert board["retryAt"] is None
        assert board["retryCount"] == 0
    assert calls == [
        ("greenhouse", True),
        ("lever", True),
        ("greenhouse", False),
        ("greenhouse", False),
    ]


def test_scraper_can_stop_review_select_soft_mismatch_and_resume(
    product_client: TestClient, monkeypatch
) -> None:
    login(product_client)
    configure_test_sources(monkeypatch)

    async def reviewable_fetch(source, _config, **_kwargs) -> FetchResult:
        job = scraper_job(1 if source.ats_type == "greenhouse" else 2)
        job["roleTitle"] = "Senior Backend Engineer"
        job["location"] = "Remote - United States"
        job["experienceMinYears"] = 7
        job["experienceMaxYears"] = 9
        return FetchResult(jobs=[job])

    monkeypatch.setattr(scraper_router, "fetch_source_jobs", reviewable_fetch)
    run_id = product_client.post("/api/scraper/runs").json()["id"]
    running = product_client.post(f"/api/scraper/runs/{run_id}/advance").json()
    assert running["status"] == "RUNNING"
    assert running["processedSourceCount"] == 1

    stopped = product_client.post(
        f"/api/scraper/runs/{run_id}/stop-and-review"
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "REVIEW_READY"
    assert stopped.json()["stoppedEarly"] is True
    assert stopped.json()["validCount"] == 1

    candidates = product_client.get(
        f"/api/scraper/runs/{run_id}/candidates?page=1&pageSize=100"
    ).json()["items"]
    reviewable = candidates[0]
    assert reviewable["reviewGroup"] == "NEEDS_REVIEW"
    assert reviewable["sourceQualityValid"] is True
    assert "NOT_INDIA_ELIGIBLE" in reviewable["qualityFailures"]
    selected = product_client.patch(
        f"/api/scraper/runs/{run_id}/selection",
        json={"candidateIds": [reviewable["id"]], "selected": True},
    )
    assert selected.status_code == 200
    assert selected.json()["selectedCount"] == 1

    resumed = product_client.post(f"/api/scraper/runs/{run_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "RUNNING"
    finished = advance_to_review(product_client, run_id)
    assert finished["processedSourceCount"] == finished["sourceCount"]
    assert finished["stoppedEarly"] is False
    assert finished["selectedCount"] == 1


def test_stopped_fetch_cannot_complete_reclaimed_attempt(
    product_client: TestClient, monkeypatch
) -> None:
    login(product_client)
    configure_test_sources(monkeypatch, concurrent_sources=1)
    started = [Event(), Event()]
    release = [Event(), Event()]
    source_keys = []

    async def blocked_fetch(source, _config, **_kwargs) -> FetchResult:
        call = len(source_keys)
        source_keys.append(source.source_key)
        started[call].set()
        if not await asyncio.to_thread(release[call].wait, 10):
            raise TimeoutError("Test did not release fetch")
        return FetchResult(jobs=[scraper_job(call + 1)])

    monkeypatch.setattr(scraper_router, "fetch_source_jobs", blocked_fetch)
    run_id = product_client.post("/api/scraper/runs").json()["id"]
    run_path = f"/api/scraper/runs/{run_id}"
    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            original = executor.submit(product_client.post, f"{run_path}/advance")
            assert started[0].wait(5)
            stopped = product_client.post(f"{run_path}/stop-and-review")
            assert stopped.status_code == 200, stopped.text
            assert stopped.json()["status"] == "REVIEW_READY"
            assert not original.done()

            resumed = product_client.post(f"{run_path}/resume")
            assert resumed.status_code == 200, resumed.text
            replacement = executor.submit(product_client.post, f"{run_path}/advance")
            assert started[1].wait(5)
            assert source_keys[0] == source_keys[1]

            release[0].set()
            stale = original.result(timeout=5)
            assert stale.status_code == 200, stale.text
            assert stale.json()["processedSourceCount"] == 0
            assert stale.json()["validCount"] == 0
            assert not replacement.done()

            release[1].set()
            current = replacement.result(timeout=5)
            assert current.status_code == 200, current.text
            assert current.json()["processedSourceCount"] == 1
            assert current.json()["validCount"] == 1
        finally:
            for gate in release:
                gate.set()

    candidates = product_client.get(f"{run_path}/candidates").json()["items"]
    assert [item["sourceUrl"] for item in candidates] == [
        "https://jobs.example.test/backend-2"
    ]


def test_scraper_target_controls_auto_selection_and_cancel_is_terminal(
    product_client: TestClient, monkeypatch
) -> None:
    login(product_client)
    configure_test_sources(monkeypatch, target_job_count=3)

    async def many_jobs(_source, _config, **_kwargs) -> FetchResult:
        return FetchResult(jobs=[scraper_job(index) for index in range(10)])

    monkeypatch.setattr(scraper_router, "fetch_source_jobs", many_jobs)
    run_id = product_client.post("/api/scraper/runs").json()["id"]
    detail = advance_to_review(product_client, run_id)
    assert detail["validCount"] == 10
    candidates = product_client.get(
        f"/api/scraper/runs/{run_id}/candidates?page=1&pageSize=100"
    ).json()["items"]
    assert len([item for item in candidates if item["selected"]]) == 3

    selected_all = product_client.patch(
        f"/api/scraper/runs/{run_id}/selection/all",
        json={"selected": True},
    )
    assert selected_all.status_code == 200
    assert selected_all.json()["selectedCount"] == 10
    cleared_all = product_client.patch(
        f"/api/scraper/runs/{run_id}/selection/all",
        json={"selected": False},
    )
    assert cleared_all.status_code == 200
    assert cleared_all.json()["selectedCount"] == 0
    selected_all = product_client.patch(
        f"/api/scraper/runs/{run_id}/selection/all",
        json={"selected": True},
    )
    assert selected_all.json()["selectedCount"] == 10

    imported = product_client.post(
        f"/api/scraper/runs/{run_id}/import", json={"confirmPartial": False}
    )
    assert imported.status_code == 200
    next_run = product_client.post("/api/scraper/runs").json()
    next_run = advance_to_review(product_client, next_run["id"])
    assert next_run["status"] == "REVIEW_READY"
    cancelled = product_client.post(f"/api/scraper/runs/{next_run['id']}/cancel")
    assert cancelled.json()["status"] == "CANCELLED"
    cancelled_again = product_client.post(
        f"/api/scraper/runs/{next_run['id']}/cancel"
    )
    assert cancelled_again.status_code == 200
    assert cancelled_again.json()["status"] == "CANCELLED"
    attempts = product_client.get(
        f"/api/scraper/runs/{next_run['id']}/attempts?page=1&pageSize=100"
    ).json()["items"]
    assert all(attempt["status"] != "RUNNING" for attempt in attempts)
    assert (
        product_client.post(f"/api/scraper/runs/{next_run['id']}/advance").json()[
            "status"
        ]
        == "CANCELLED"
    )


def test_scraper_never_calls_bright_data_past_the_cap(
    product_client: TestClient, monkeypatch
) -> None:
    login(product_client)
    configure_test_sources(monkeypatch, bright_data_limit=0)
    calls = 0

    async def direct_fetch(_source, _config, **_kwargs) -> FetchResult:
        nonlocal calls
        calls += 1
        return FetchResult(jobs=[scraper_job()], bright_data_used=0)

    monkeypatch.setattr(scraper_router, "fetch_source_jobs", direct_fetch)
    run_id = product_client.post("/api/scraper/runs").json()["id"]
    detail = advance_to_review(product_client, run_id)
    assert detail["status"] == "REVIEW_READY"
    assert detail["brightDataUsed"] == 0
    assert calls == 2


def test_scraper_uses_seeded_sources_without_serp(
    product_client: TestClient, monkeypatch
) -> None:
    login(product_client)
    seed = {
        "name": "Example Labs",
        "ats_type": "greenhouse",
        "domain_hint": "boards.greenhouse.io",
        "board_token": "example",
    }
    config = replace(scraper_router.load_scraper_config(), seed_sources=(seed,))
    monkeypatch.setattr(scraper_router, "load_scraper_config", lambda: config)
    monkeypatch.setattr(
        scraper_router,
        "get_settings",
        lambda: SimpleNamespace(
            bright_data_api_key="test-key",
            bright_data_serp_zone="",
            bright_data_unlocker_zone="",
        ),
    )
    monkeypatch.setattr(scraper_router, "fetch_source_jobs", fake_fetch)

    sources = product_client.get("/api/scraper/sources")
    assert sources.status_code == 200
    assert [item["sourceKey"] for item in sources.json()] == ["greenhouse:example"]
    added = product_client.post(
        "/api/scraper/sources",
        json={"url": "https://jobs.ashbyhq.com/another-company"},
    )
    assert added.status_code == 201
    assert added.json()["sourceKey"] == "ashby:another-company"

    run = product_client.post("/api/scraper/runs").json()
    attempts = product_client.get(
        f"/api/scraper/runs/{run['id']}/attempts?page=1&pageSize=100"
    ).json()["items"]
    assert all(not item["stepKey"].startswith("discover:") for item in attempts)
    detail = advance_to_review(product_client, run["id"])
    assert detail["status"] == "REVIEW_READY"
    assert detail["brightDataUsed"] == 0
    assert detail["validCount"] == 1


def test_scraper_rejects_non_owner(product_client: TestClient) -> None:
    response = product_client.post(
        "/api/auth/login",
        json={"email": "friend@example.com", "password": "friend password"},
    )
    assert response.status_code == 200
    assert product_client.get("/api/scraper/config").status_code == 403
    assert product_client.post("/api/scraper/runs").status_code == 403
    assert product_client.get("/api/scraper/sources").status_code == 403
    assert product_client.get("/api/scraper/runs/example/stats").status_code == 403


def test_owner_can_refresh_and_manage_discovered_sources(
    product_client: TestClient, monkeypatch
) -> None:
    login(product_client)
    config = replace(
        scraper_router.load_scraper_config(),
        seed_sources=(),
        company_hints=({"name": "Example Labs", "domain": "example.test"},),
    )
    monkeypatch.setattr(scraper_router, "load_scraper_config", lambda: config)

    async def detect(_name, _domain, _config) -> FetchResult:
        source = SourceSpec(
            source_key="jsonld:example",
            name="Example Labs",
            ats_type="jsonld",
            domain_hint="example.test",
            board_token="https://example.test/careers",
        )
        return FetchResult(jobs=[source.__dict__], free_requests=1)

    monkeypatch.setattr(scraper_router, "discover_company_sources", detect)
    monkeypatch.setattr(scraper_router, "fetch_source_jobs", fake_fetch)
    created = product_client.post("/api/scraper/source-refresh")
    assert created.status_code == 201
    run_id = created.json()["id"]
    advanced = product_client.post(f"/api/scraper/source-refresh/{run_id}/advance")
    assert advanced.status_code == 200
    assert advanced.json()["status"] == "COMPLETED"
    assert advanced.json()["activatedSources"] == 1

    source = product_client.get("/api/scraper/sources").json()[0]
    assert source["healthStatus"] == "HEALTHY"
    disabled = product_client.patch(
        f"/api/scraper/sources/{source['id']}", json={"active": False}
    )
    assert disabled.status_code == 200
    assert disabled.json()["active"] is False
