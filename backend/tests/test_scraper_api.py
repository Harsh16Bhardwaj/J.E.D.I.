# ruff: noqa: F401, F811

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

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
