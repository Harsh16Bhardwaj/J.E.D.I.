import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.auth import hash_password
from backend.config import get_settings
from backend.database import (
    Base,
    Group,
    GroupMember,
    ModelVersion,
    ProfileVersion,
    User,
    get_session,
)
from backend.main import app
from backend.routers import operations
from backend.services.email import get_email_transport
from backend.services.product import annualized_salary_range

BUNDLE_MANIFEST = json.loads(
    (
        Path(__file__).parents[1]
        / "model_bundles"
        / "jedi-ranking-v1"
        / "manifest.json"
    ).read_text(encoding="utf-8")
)


@pytest.fixture
def product_client() -> Iterator[TestClient]:
    settings = get_settings()
    original_secret = settings.session_secret
    settings.session_secret = "test-session-secret-that-is-longer-than-32-bytes"
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def setup() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(
                User(
                    id="user-1",
                    email="owner@example.com",
                    password_hash=hash_password("correct horse"),
                )
            )
            session.add(
                User(
                    id="user-2",
                    email="friend@example.com",
                    password_hash=hash_password("friend password"),
                )
            )
            session.add(
                ProfileVersion(
                    id="profile-1",
                    content_hash="profile-hash",
                    resume_text="Python FastAPI PostgreSQL backend engineer",
                    preferred_titles=["backend engineer"],
                    preferred_locations=["remote"],
                    preferred_skills=["python", "fastapi"],
                    active=True,
                )
            )
            session.add(
                ModelVersion(
                    id="model-1",
                    name="test-model",
                    artifact_manifest=BUNDLE_MANIFEST,
                    feature_schema_version="prepared-job-v2",
                    request_contract_version="score-request-v1",
                    active=True,
                )
            )
            session.add(
                Group(
                    id="group-1",
                    name="JEDI",
                    owner_id="user-1",
                    active_profile_version_id="profile-1",
                    active_model_version_id="model-1",
                )
            )
            session.add(
                GroupMember(
                    id="member-1",
                    group_id="group-1",
                    user_id="user-1",
                    onboarding_completed_at=datetime.now(UTC),
                )
            )
            session.add(
                GroupMember(
                    id="member-2",
                    group_id="group-1",
                    user_id="user-2",
                    onboarding_completed_at=datetime.now(UTC),
                )
            )
            await session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    asyncio.run(setup())
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())
    settings.session_secret = original_secret


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "OWNER@example.com", "password": "correct horse"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"
    assert response.cookies.get("jedi_session")


def batch_payload() -> dict:
    posted_at = (
        datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        - timedelta(days=1)
    ).isoformat()
    return {
        "externalBatchId": "daily-2026-07-28",
        "schemaVersion": "import-v1",
        "promptVersion": "prompt-v1",
        "generatedAt": "2026-07-28T08:00:00Z",
        "jobs": [
            {
                "companyName": "Acme Pvt Ltd",
                "roleTitle": "Backend Engineer",
                "description": "Build Python FastAPI services and PostgreSQL systems.",
                "applyUrl": "https://jobs.acme.test/backend?utm_source=feed",
                "location": "Remote",
                "workMode": "WFH",
                "employmentType": "Full time",
                "skills": ["Python", "FastAPI", "PostgreSQL"],
                "postedAt": posted_at,
                "experienceMinYears": 1,
                "experienceMaxYears": 3,
            },
            {
                "companyName": "Acme",
                "roleTitle": "Backend Engineer",
                "description": "Build Python FastAPI services and PostgreSQL systems.",
                "applyUrl": "https://jobs.acme.test/backend?utm_source=other",
                "location": "Remote",
                "workMode": "remote",
                "employmentType": "full-time",
                "skills": "Python, FastAPI",
                "postedAt": posted_at,
                "experienceMinYears": 1,
                "experienceMaxYears": 3,
            },
            {
                "companyName": "Broken Job",
                "roleTitle": "Unknown",
                "applyUrl": "https://broken.test/job",
            },
        ],
    }


def test_misc_csv_bootstrap_and_annotation_editor(
    product_client: TestClient,
) -> None:
    csv_text = (
        "company_name,role_title,description,apply_url,skills,applied,"
        "role_title_fit,role_family_fit,seniority_fit,location_fit,"
        "work_mode_fit,experience_fit,skills_fit,salary_fit,overall_preference\n"
        "CSV Labs,Python Engineer,Build reliable Python APIs,"
        "https://csv.test/jobs/1,Python;FastAPI,yes,5,4,4,5,5,4,5,6,5\n"
        "CSV Labs,Data Engineer,Build data pipelines,"
        "https://csv.test/jobs/2,Python;SQL,,,,,,,,,,\n"
    )
    unauthorized = product_client.post(
        "/api/misc/training-data/import-csv",
        files={"file": ("jobs.csv", csv_text, "text/csv")},
    )
    assert unauthorized.status_code == 401
    login(product_client)

    imported = product_client.post(
        "/api/misc/training-data/import-csv",
        files={"file": ("jobs.csv", csv_text, "text/csv")},
    )
    assert imported.status_code == 201
    body = imported.json()
    assert body["importedCount"] == 2
    assert body["trainingExampleCount"] == 1
    assert body["featureSchemaVersion"] == "prepared-job-v2"

    replay = product_client.post(
        "/api/misc/training-data/import-csv",
        files={"file": ("jobs.csv", csv_text, "text/csv")},
    )
    assert replay.status_code == 201
    assert replay.json()["replayed"] is True

    editor = product_client.get(
        f"/api/misc/batches/{body['batchId']}/annotation-editor"
    )
    assert editor.status_code == 200
    assert len(editor.json()["rows"]) == 2
    assert editor.json()["completeCount"] == 1
    assert editor.json()["preparedCount"] == 2
    assert editor.json()["trainingCount"] == 1


def test_dashboard_today_leaderboard_and_visibility_filters(
    product_client: TestClient,
) -> None:
    assert product_client.get("/api/dashboard").status_code == 401
    login(product_client)
    payload = batch_payload()
    payload["externalBatchId"] = "dashboard-today"
    payload["generatedAt"] = datetime.now(UTC).isoformat()
    created = product_client.post("/api/batches", json=payload).json()
    batch_id = created["batchId"]
    job_id = product_client.get(f"/api/batches/{batch_id}").json()["jobs"][0]["id"]
    assert product_client.post(f"/api/batches/{batch_id}/normalize").status_code == 200
    assert product_client.post(f"/api/batches/{batch_id}/rank").status_code == 202
    ranked = product_client.post(
        f"/api/batches/{batch_id}/rankings",
        json={
            "profileVersionId": "profile-1",
            "modelVersionId": "model-1",
            "rankings": [
                {
                    "jobId": job_id,
                    "rank": 1,
                    "jediPreferenceScore": 94.5,
                    "applyPreferenceProbability": 0.91,
                    "rankingScore": 94.5,
                    "applyThreshold": 0.6,
                    "modelApplyDecision": True,
                    "applyRecommendation": True,
                }
            ],
        },
    )
    assert ranked.status_code == 200

    low_payload = batch_payload()
    low_payload["externalBatchId"] = "dashboard-below-threshold"
    low_payload["generatedAt"] = datetime.now(UTC).isoformat()
    low_payload["jobs"][0]["companyName"] = "Below Threshold Inc"
    low_payload["jobs"][1]["companyName"] = "Below Threshold Inc"
    low_batch_id = product_client.post("/api/batches", json=low_payload).json()[
        "batchId"
    ]
    low_job_id = product_client.get(f"/api/batches/{low_batch_id}").json()["jobs"][
        0
    ]["id"]
    assert (
        product_client.post(f"/api/batches/{low_batch_id}/normalize").status_code
        == 200
    )
    assert product_client.post(f"/api/batches/{low_batch_id}/rank").status_code == 202
    low_ranked = product_client.post(
        f"/api/batches/{low_batch_id}/rankings",
        json={
            "profileVersionId": "profile-1",
            "modelVersionId": "model-1",
            "rankings": [
                {
                    "jobId": low_job_id,
                    "rank": 1,
                    "jediPreferenceScore": 99,
                    "applyPreferenceProbability": 0.59,
                    "rankingScore": 99,
                    "applyThreshold": 0.6,
                    "modelApplyDecision": False,
                    "applyRecommendation": False,
                }
            ],
        },
    )
    assert low_ranked.status_code == 200

    dashboard = product_client.get("/api/dashboard")
    assert dashboard.status_code == 200
    today_jobs = dashboard.json()["todayJobs"]
    dashboard_job = next(item for item in today_jobs if item["id"] == job_id)
    assert dashboard.json()["jobFeedScope"] == "today"
    assert dashboard_job["description"].startswith("Build Python FastAPI")
    assert dashboard_job["employmentType"] == "full-time"
    assert dashboard_job["postedAt"] is not None
    assert dashboard_job["salaryMin"] is None
    assert [item["id"] for item in today_jobs[:2]] == [low_job_id, job_id]
    assert dashboard.json()["leaderboard"][0]["id"] == low_job_id
    assert dashboard.json()["leaderboard"][0]["jediPreferenceScore"] == 99
    assert dashboard.json()["leaderboard"][0]["applyPreferenceProbability"] == 0.59
    metrics = product_client.get(f"/api/batches/{batch_id}/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["rankedCount"] == 1
    assert metrics.json()["averageScore"] == 94.5
    assert metrics.json()["top25AverageScore"] == 94.5
    assert metrics.json()["recommendedCount"] == 1
    assert metrics.json()["applicationRate"] == 0
    assert product_client.get("/api/jobs", params={"minScore": 94}).json()["total"] == 2
    assert product_client.get("/api/jobs", params={"minScore": 95}).json()["total"] == 1
    assert (
        product_client.get("/api/dashboard?leaderboardPeriod=weekly").status_code == 200
    )
    assert (
        product_client.get("/api/dashboard?leaderboardPeriod=overall").status_code
        == 200
    )
    assert (
        product_client.get("/api/dashboard?leaderboardPeriod=invalid").status_code
        == 422
    )

    product_client.patch(f"/api/jobs/{job_id}/state", json={"reviewStatus": "VIEWED"})
    fresh_jobs = product_client.get("/api/dashboard?fresh=true").json()["todayJobs"]
    assert [item["id"] for item in fresh_jobs] == [low_job_id]
    viewed_metrics = product_client.get(f"/api/batches/{batch_id}/metrics").json()
    assert viewed_metrics["viewedCount"] == 1
    product_client.post(
        f"/api/jobs/{job_id}/application-events",
        json={"applicationStatus": "APPLIED"},
    )
    filtered = product_client.get("/api/dashboard?notApplied=true").json()
    assert [item["id"] for item in filtered["todayJobs"]] == [low_job_id]
    assert [item["id"] for item in filtered["leaderboard"]] == [low_job_id]
    applied_metrics = product_client.get(f"/api/batches/{batch_id}/metrics").json()
    assert applied_metrics["applicationRate"] == 1


def test_dashboard_falls_back_to_latest_jobs(product_client: TestClient) -> None:
    login(product_client)
    payload = batch_payload()
    payload["externalBatchId"] = "dashboard-yesterday"
    payload["generatedAt"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    created = product_client.post("/api/batches", json=payload)
    assert created.status_code == 201
    batch_id = created.json()["batchId"]
    job_id = product_client.get(f"/api/batches/{batch_id}").json()["jobs"][0]["id"]
    assert product_client.post(f"/api/batches/{batch_id}/normalize").status_code == 200
    assert product_client.post(f"/api/batches/{batch_id}/rank").status_code == 202
    assert product_client.post(
        f"/api/batches/{batch_id}/rankings",
        json={
            "profileVersionId": "profile-1",
            "modelVersionId": "model-1",
            "rankings": [
                {
                    "jobId": job_id,
                    "rank": 1,
                    "jediPreferenceScore": 80,
                    "applyPreferenceProbability": 0.6,
                    "rankingScore": 80,
                    "applyThreshold": 0.6,
                    "modelApplyDecision": True,
                    "applyRecommendation": True,
                }
            ],
        },
    ).status_code == 200

    dashboard = product_client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["jobFeedScope"] == "latest"
    assert len(dashboard.json()["todayJobs"]) == 1


def test_auth_runs_before_json_parsing(product_client: TestClient) -> None:
    response = product_client.post(
        "/api/batches",
        content="{not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401


def test_batch_import_rejects_unverified_and_stale_jobs(
    product_client: TestClient,
) -> None:
    login(product_client)
    payload = batch_payload()
    payload["externalBatchId"] = "stale-jobs"
    payload["jobs"] = [
        {
            **payload["jobs"][0],
            "companyName": "Stale Labs",
            "applyUrl": "https://stale.test/job",
            "postedAt": (datetime.now(UTC) - timedelta(days=31)).isoformat(),
        },
        {
            **payload["jobs"][0],
            "companyName": "Unknown Date Labs",
            "applyUrl": "https://unknown-date.test/job",
            "postedAt": None,
        },
    ]

    response = product_client.post("/api/batches", json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["message"] == "No valid unique jobs remain; nothing was created."
    messages = [
        item["msg"]
        for issue in error["details"]["validationReport"]
        for item in issue["errors"]
    ]
    assert any("30-day" in message for message in messages)
    assert any("postedAt is required" in message for message in messages)


def test_monthly_salary_period_is_persisted_and_annualized(
    product_client: TestClient,
) -> None:
    login(product_client)
    payload = batch_payload()
    payload["externalBatchId"] = "monthly-internship"
    payload["jobs"] = [
        {
            **payload["jobs"][0],
            "companyName": "Intern Labs",
            "employmentType": "Internship",
            "salaryMin": 30_000,
            "salaryMax": 50_000,
            "salaryCurrency": "INR",
            "salaryPeriod": "MONTHLY",
        }
    ]

    created = product_client.post("/api/batches", json=payload)
    assert created.status_code == 201
    batch_id = created.json()["batchId"]
    detail = product_client.get(f"/api/batches/{batch_id}").json()
    assert detail["jobs"][0]["salaryPeriod"] == "MONTHLY"
    job = product_client.get("/api/jobs").json()["items"][0]
    assert job["salaryPeriod"] == "MONTHLY"
    assert job["batchCreatedAt"]
    assert annualized_salary_range(30_000, 50_000, "MONTHLY") == (
        360_000,
        600_000,
    )


def test_batch_review_training_and_ranking_flow(
    product_client: TestClient,
) -> None:
    assert (
        product_client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "wrong"},
        ).status_code
        == 401
    )
    login(product_client)

    created = product_client.post("/api/batches", json=batch_payload())
    assert created.status_code == 201
    result = created.json()
    assert result["receivedCount"] == 3
    assert result["validCount"] == 2
    assert result["duplicateCount"] == 1
    assert result["jobCount"] == 1
    assert len(result["validationReport"]) == 1
    batch_id = result["batchId"]

    replay = product_client.post("/api/batches", json=batch_payload())
    assert replay.status_code == 201
    assert replay.json()["replayed"] is True
    batches = product_client.get("/api/batches").json()
    assert batches["total"] == 1
    assert len(batches["items"]) == 1
    friendly_name = batches["items"][0]["displayName"]
    assert friendly_name is not None
    assert len(friendly_name.split()) == 3
    assert len(friendly_name.rsplit(" ", 1)[1]) == 2
    assert friendly_name.rsplit(" ", 1)[1].isdigit()

    detail = product_client.get(f"/api/batches/{batch_id}")
    assert detail.status_code == 200
    job_id = detail.json()["jobs"][0]["id"]
    assert detail.json()["actions"]["canNormalize"] is True

    normalized = product_client.post(f"/api/batches/{batch_id}/normalize")
    assert normalized.status_code == 200
    assert normalized.json()["preparedCount"] == 1
    normalized_detail = product_client.get(f"/api/batches/{batch_id}").json()
    assert normalized_detail["preparedCount"] == 1
    assert normalized_detail["normalizationComplete"] is True
    assert normalized_detail["manualAnnotationCount"] == 0
    assert normalized_detail["actions"]["canNormalize"] is False

    annotation = {
        "jobId": job_id,
        "relevanceLabel": "STRONG_APPLY",
        "applyLabel": True,
        "roleTitleFit": 5,
        "roleFamilyFit": 4,
        "seniorityFit": 4,
        "locationFit": 5,
        "workModeFit": 5,
        "experienceFit": 4,
        "skillsFit": 5,
        "salaryFit": 6,
        "overallPreference": 5,
    }
    annotated = product_client.patch(
        f"/api/batches/{batch_id}/annotations",
        json={"annotations": [annotation]},
    )
    assert annotated.status_code == 200
    assert annotated.json()[0]["complete"] is True
    assert (
        product_client.get(f"/api/batches/{batch_id}").json()[
            "manualAnnotationCount"
        ]
        == 1
    )

    training = product_client.post(
        f"/api/batches/{batch_id}/training-examples",
        json={"selection": "YES_ONLY"},
    )
    assert training.status_code == 200
    assert training.json()["addedOrUpdatedCount"] == 1
    export = product_client.get("/api/training-examples/export.csv")
    assert export.status_code == 200
    assert "apply_label" in export.text
    assert "profile_version_id" in export.text
    assert "payload_hash" in export.text

    queued = product_client.post(f"/api/batches/{batch_id}/rank")
    assert queued.status_code == 202
    assert queued.json()["pendingExecution"] is True
    first_run_id = queued.json()["processingRunId"]
    history = product_client.get(f"/api/batches/{batch_id}/processing-runs")
    ranking_run = next(run for run in history.json() if run["id"] == first_run_id)
    assert ranking_run["modelName"] == "test-model"

    rankings = product_client.post(
        f"/api/batches/{batch_id}/rankings",
        json={
            "profileVersionId": "profile-1",
            "modelVersionId": "model-1",
            "rankings": [
                {
                    "jobId": job_id,
                    "rank": 1,
                    "jediPreferenceScore": 91.5,
                    "applyPreferenceProbability": 0.94,
                    "componentScores": {"skills": 5},
                    "rankingScore": 91.5,
                    "applyThreshold": 0.6,
                    "modelApplyDecision": True,
                    "applyRecommendation": True,
                }
            ],
        },
    )
    assert rankings.status_code == 200
    assert rankings.json()["status"] == "RANKED"
    assert rankings.json()["emailDelivery"] is None
    ranked = product_client.get(f"/api/batches/{batch_id}/rankings")
    assert ranked.status_code == 200
    assert ranked.json()[0]["rank"] == 1
    assert ranked.json()[0]["processingRunId"] == first_run_id

    rerun = product_client.post(f"/api/batches/{batch_id}/rank")
    assert rerun.status_code == 202
    assert rerun.json()["processingRunId"] != first_run_id
    reranked = product_client.post(
        f"/api/batches/{batch_id}/rankings",
        json={
            "profileVersionId": "profile-1",
            "modelVersionId": "model-1",
            "rankings": [
                {
                    "jobId": job_id,
                    "rank": 1,
                    "jediPreferenceScore": 88.0,
                    "applyPreferenceProbability": 0.87,
                    "componentScores": {"skills": 4},
                    "rankingScore": 88.0,
                    "applyThreshold": 0.6,
                    "modelApplyDecision": True,
                    "applyRecommendation": True,
                }
            ],
        },
    )
    assert reranked.status_code == 200
    assert (
        product_client.get(f"/api/batches/{batch_id}/rankings").json()[0][
            "jediPreferenceScore"
        ]
        == 88.0
    )
    historical = product_client.get(
        f"/api/batches/{batch_id}/rankings",
        params={"runId": first_run_id},
    )
    assert historical.status_code == 200
    assert historical.json()[0]["jediPreferenceScore"] == 91.5
    assert product_client.delete(f"/api/batches/{batch_id}").status_code == 409


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/profiles", {"resumeText": "Resume"}),
        ("GET", "/api/profiles", None),
        ("GET", "/api/profiles/active", None),
        ("GET", "/api/profiles/profile-1", None),
        ("POST", "/api/profiles/profile-1/activate", None),
        ("GET", "/api/jobs", None),
        ("GET", "/api/jobs/job-1", None),
        ("PATCH", "/api/jobs/job-1/state", {"reviewStatus": "VIEWED"}),
        ("GET", "/api/applications", None),
        ("GET", "/api/models", None),
        (
            "POST",
            "/api/jobs/job-1/application-events",
            {"applicationStatus": "APPLIED"},
        ),
        ("GET", "/api/jobs/job-1/application-events", None),
    ],
)
def test_workspace_routes_require_authentication(
    product_client: TestClient,
    method: str,
    path: str,
    body: dict | None,
) -> None:
    response = product_client.request(method, path, json=body)
    assert response.status_code == 401


def test_profile_create_replay_and_single_activation(
    product_client: TestClient,
) -> None:
    login(product_client)
    invalid = product_client.post(
        "/api/profiles",
        json={
            "resumeText": "Resume",
            "experienceMinYears": 5,
            "experienceMaxYears": 2,
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    payload = {
        "resumeText": "  Python   backend engineer  ",
        "preferredTitles": [" Backend Engineer ", "backend engineer"],
        "preferredLocations": [" Remote "],
        "preferredSkills": ["Python", " python ", "FastAPI"],
        "salaryMin": 100,
        "salaryMax": 200,
        "salaryCurrency": " usd ",
    }
    created = product_client.post("/api/profiles", json=payload)
    assert created.status_code == 201
    profile = created.json()
    assert profile["active"] is False
    assert profile["resumeText"] == "Python backend engineer"
    assert profile["preferredTitles"] == ["Backend Engineer"]
    assert profile["preferredSkills"] == ["Python", "FastAPI"]
    assert profile["salaryCurrency"] == "USD"
    assert profile["replayed"] is False

    replay = product_client.post("/api/profiles", json=payload)
    assert replay.status_code == 200
    assert replay.json()["id"] == profile["id"]
    assert replay.json()["replayed"] is True

    detail = product_client.get(f"/api/profiles/{profile['id']}")
    assert detail.status_code == 200
    assert detail.json()["contentHash"] == profile["contentHash"]
    activated = product_client.post(f"/api/profiles/{profile['id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["active"] is True
    profiles = product_client.get("/api/profiles").json()
    assert sum(item["active"] for item in profiles) == 1
    assert (
        next(item for item in profiles if item["id"] == "profile-1")["active"] is False
    )
    assert product_client.get("/api/profiles/missing").status_code == 404
    assert product_client.get("/api/profiles/active").json()["id"] == profile["id"]


def test_model_registry_replay_and_single_activation(
    product_client: TestClient,
) -> None:
    login(product_client)
    payload = {
        "name": "ranking-v2",
        "artifactManifest": {"bundle": "ML/models/ranking-v2"},
        "featureSchemaVersion": "prepared-job-v1",
        "metrics": {"ndcg25": 0.97},
    }
    created = product_client.post("/api/models", json=payload)
    assert created.status_code == 201
    assert created.json()["active"] is False
    assert created.json()["replayed"] is False

    replay = product_client.post("/api/models", json=payload)
    assert replay.status_code == 200
    assert replay.json()["id"] == created.json()["id"]
    assert replay.json()["replayed"] is True
    conflict = product_client.post(
        "/api/models",
        json={**payload, "artifactManifest": {"bundle": "different"}},
    )
    assert conflict.status_code == 409
    activated = product_client.post(f"/api/models/{created.json()['id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["active"] is True
    models = product_client.get("/api/models").json()
    assert sum(item["active"] for item in models) == 1
    assert product_client.get("/api/models/missing").status_code == 404


def create_test_job(client: TestClient) -> tuple[str, str]:
    created = client.post("/api/batches", json=batch_payload())
    batch_id = created.json()["batchId"]
    detail = client.get(f"/api/batches/{batch_id}").json()
    return batch_id, detail["jobs"][0]["id"]


def test_job_workspace_and_application_history(
    product_client: TestClient,
) -> None:
    login(product_client)
    batch_id, job_id = create_test_job(product_client)

    listed = product_client.get(
        "/api/jobs",
        params={
            "search": "Acme",
            "batchId": batch_id,
            "reviewStatus": "NEW",
            "applicationStatus": "NOT_STARTED",
            "page": 1,
            "pageSize": 1,
        },
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == job_id
    assert (
        product_client.get("/api/jobs", params={"viewed": False}).json()["total"]
        == 1
    )
    assert product_client.get("/api/jobs", params={"viewed": True}).json()["total"] == 0
    detail = product_client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["state"] is None
    assert detail.json()["annotation"] is None
    assert detail.json()["events"] == []
    assert (
        product_client.patch(
            f"/api/jobs/{job_id}/annotation",
            json={},
        ).status_code
        == 422
    )
    assert (
        product_client.patch(
            f"/api/batches/{batch_id}/annotations",
            json={
                "annotations": [
                    {"jobId": job_id, "applyLabel": True},
                    {"jobId": job_id, "applyLabel": False},
                ]
            },
        ).status_code
        == 422
    )

    assert product_client.patch(f"/api/jobs/{job_id}/state", json={}).status_code == 422
    state = product_client.patch(
        f"/api/jobs/{job_id}/state",
        json={
            "relevanceLabel": "STRONG_APPLY",
            "reviewStatus": "VIEWED",
            "notes": "  Worth applying  ",
        },
    )
    assert state.status_code == 200
    assert state.json()["reviewStatus"] == "VIEWED"
    assert state.json()["applicationStatus"] == "NOT_STARTED"
    assert state.json()["notes"] == "Worth applying"
    filtered = product_client.get(
        "/api/jobs",
        params={
            "relevanceLabel": "STRONG_APPLY",
            "reviewStatus": "VIEWED",
        },
    )
    assert filtered.json()["total"] == 1
    assert product_client.get("/api/jobs", params={"viewed": True}).json()["total"] == 1
    assert (
        product_client.get("/api/jobs", params={"viewed": False}).json()["total"]
        == 0
    )
    bookmarked = product_client.patch(
        f"/api/jobs/{job_id}/state",
        json={"reviewStatus": "SAVED"},
    )
    assert bookmarked.status_code == 200
    assert bookmarked.json()["reviewStatus"] == "SAVED"
    assert (
        product_client.get(
            "/api/jobs", params={"reviewStatus": "SAVED"}
        ).json()["total"]
        == 1
    )
    assert (
        product_client.patch(
            f"/api/jobs/{job_id}/state",
            json={"reviewStatus": "VIEWED"},
        ).status_code
        == 200
    )

    for status_value, event_at in (
        ("APPLIED", "2026-07-29T08:00:00Z"),
        ("INTERVIEW", "2026-07-29T09:00:00Z"),
    ):
        event = product_client.post(
            f"/api/jobs/{job_id}/application-events",
            json={
                "applicationStatus": status_value,
                "eventAt": event_at,
                "notes": f"Moved to {status_value}",
            },
        )
        assert event.status_code == 201

    events = product_client.get(f"/api/jobs/{job_id}/application-events").json()
    assert [event["eventType"] for event in events] == [
        "INTERVIEW",
        "APPLIED",
    ]
    assert (
        product_client.get("/api/jobs", params={"applied": True}).json()["total"]
        == 1
    )
    assert (
        product_client.get("/api/jobs", params={"applied": False}).json()["total"]
        == 0
    )
    applications = product_client.get("/api/applications", params={"search": "Backend"})
    assert applications.status_code == 200
    assert applications.json()["total"] == 1
    assert applications.json()["items"][0]["latestEvent"]["eventType"] == "INTERVIEW"
    assert (
        product_client.get(
            "/api/applications", params={"applicationStatus": "APPLIED"}
        ).json()["total"]
        == 0
    )

    reset = product_client.post(
        f"/api/jobs/{job_id}/application-events",
        json={"applicationStatus": "NOT_STARTED"},
    )
    assert reset.status_code == 201
    assert (
        product_client.get("/api/jobs", params={"applied": False}).json()["total"]
        == 1
    )
    assert product_client.get("/api/applications").json()["total"] == 0
    assert (
        product_client.get(
            "/api/applications",
            params={"applicationStatus": "NOT_STARTED"},
        ).json()["total"]
        == 1
    )
    assert len(product_client.get(f"/api/jobs/{job_id}").json()["events"]) == 3
    assert product_client.get("/api/jobs/missing").status_code == 404
    assert (
        product_client.post(
            f"/api/jobs/{job_id}/application-events",
            json={"applicationStatus": "INVALID"},
        ).status_code
        == 422
    )


def test_application_event_failure_rolls_back_state(
    product_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    login(product_client)
    _, job_id = create_test_job(product_client)
    original_commit = AsyncSession.commit

    async def fail_commit(_session: AsyncSession) -> None:
        raise SQLAlchemyError("forced commit failure")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    failed = product_client.post(
        f"/api/jobs/{job_id}/application-events",
        json={"applicationStatus": "APPLIED"},
    )
    assert failed.status_code == 500
    monkeypatch.setattr(AsyncSession, "commit", original_commit)

    detail = product_client.get(f"/api/jobs/{job_id}").json()
    assert detail["state"] is None
    assert detail["events"] == []


def test_application_planning_status_and_milestone_lifecycle(
    product_client: TestClient,
) -> None:
    login(product_client)
    _, job_id = create_test_job(product_client)

    initial = product_client.get(f"/api/jobs/{job_id}/application")
    assert initial.status_code == 200
    assert initial.json()["status"] == "NOT_STARTED"
    assert initial.json()["updatedAt"] is None

    missing_action = product_client.patch(
        f"/api/jobs/{job_id}/application",
        json={"nextActionDueAt": "2026-08-04T12:00:00Z"},
    )
    assert missing_action.status_code == 422

    planned = product_client.patch(
        f"/api/jobs/{job_id}/application",
        json={
            "nextAction": "Prepare assessment",
            "nextActionDueAt": "2026-08-04T12:00:00Z",
            "portalUrl": "https://jobs.acme.test/application/123",
            "referenceCode": "APP-123",
        },
    )
    assert planned.status_code == 200
    stale_version = planned.json()["updatedAt"]

    changed = product_client.patch(
        f"/api/jobs/{job_id}/application",
        json={"notes": "Current note", "expectedUpdatedAt": stale_version},
    )
    assert changed.status_code == 200
    assert (
        product_client.patch(
            f"/api/jobs/{job_id}/application",
            json={"notes": "Stale overwrite", "expectedUpdatedAt": stale_version},
        ).status_code
        == 409
    )

    applied = product_client.post(
        f"/api/jobs/{job_id}/application-events",
        json={
            "applicationStatus": "APPLIED",
            "eventAt": "2026-08-01T10:00:00Z",
        },
    )
    assert applied.status_code == 201
    assert applied.json()["previousStatus"] == "NOT_STARTED"
    assert applied.json()["newStatus"] == "APPLIED"
    application = product_client.get(f"/api/jobs/{job_id}/application").json()
    assert application["appliedAt"].startswith("2026-08-01T10:00:00")
    action_summary = product_client.get("/api/applications/summary").json()
    assert (
        action_summary["nearestActions"][0]["applicationUpdatedAt"]
        == application["updatedAt"]
    )

    accepted = product_client.post(
        f"/api/jobs/{job_id}/application-events",
        json={
            "applicationStatus": "ACCEPTED",
            "eventAt": "2026-08-08T10:00:00Z",
        },
    )
    assert accepted.status_code == 201
    assert (
        product_client.get(f"/api/jobs/{job_id}/application")
        .json()["closedAt"]
        .startswith("2026-08-08T10:00:00")
    )
    assert (
        product_client.post(
            f"/api/jobs/{job_id}/application-events",
            json={"applicationStatus": "INTERVIEW"},
        ).status_code
        == 201
    )
    assert (
        product_client.get(f"/api/jobs/{job_id}/application").json()["closedAt"] is None
    )

    created = product_client.post(
        f"/api/jobs/{job_id}/application-milestones",
        json={
            "type": "INTERVIEW",
            "title": "Technical Round 2",
            "scheduledAt": "2026-08-07T10:00:00Z",
        },
    )
    assert created.status_code == 201
    milestone_id = created.json()["id"]
    completed = product_client.patch(
        f"/api/jobs/{job_id}/application-milestones/{milestone_id}",
        json={"status": "COMPLETED"},
    )
    assert completed.status_code == 200
    assert completed.json()["completedAt"] is not None
    reopened = product_client.patch(
        f"/api/jobs/{job_id}/application-milestones/{milestone_id}",
        json={"status": "PLANNED"},
    )
    assert reopened.json()["completedAt"] is None
    assert (
        product_client.get(f"/api/jobs/{job_id}/application").json()["status"]
        == "INTERVIEW"
    )
    detail = product_client.get(f"/api/jobs/{job_id}").json()
    assert detail["milestones"][0]["title"] == "Technical Round 2"


def test_member_job_activity_and_applications_are_private(
    product_client: TestClient,
) -> None:
    login(product_client)
    batch_id, job_id = create_test_job(product_client)
    assert product_client.post(f"/api/jobs/{job_id}/view").status_code == 200
    assert (
        product_client.patch(
            f"/api/jobs/{job_id}/annotation",
            json={"relevanceLabel": "DREAM", "applyLabel": True},
        ).status_code
        == 200
    )
    assert (
        product_client.post(
            f"/api/jobs/{job_id}/application-events",
            json={"applicationStatus": "APPLIED"},
        ).status_code
        == 201
    )
    milestone = product_client.post(
        f"/api/jobs/{job_id}/application-milestones",
        json={"type": "INTERVIEW", "title": "Owner interview"},
    ).json()

    assert product_client.post("/api/auth/logout").status_code == 204
    friend_login = product_client.post(
        "/api/auth/login",
        json={"email": "friend@example.com", "password": "friend password"},
    )
    assert friend_login.status_code == 200

    friend_job = product_client.get(f"/api/jobs/{job_id}").json()
    assert friend_job["state"] is None
    assert friend_job["annotation"] is None
    assert friend_job["application"]["status"] == "NOT_STARTED"
    assert friend_job["events"] == []
    assert friend_job["milestones"] == []
    assert product_client.get("/api/applications").json()["total"] == 0
    friend_fresh_jobs = product_client.get(
        "/api/dashboard?fresh=true"
    ).json()["todayJobs"]
    assert [job["id"] for job in friend_fresh_jobs] == [job_id]
    assert (
        product_client.patch(
            f"/api/jobs/{job_id}/application-milestones/{milestone['id']}",
            json={"status": "CANCELLED"},
        ).status_code
        == 404
    )
    assert (
        product_client.post(
            f"/api/batches/{batch_id}/training-examples",
            json={"selection": "ALL_ANNOTATED"},
        ).status_code
        == 403
    )

    assert product_client.post(f"/api/jobs/{job_id}/view").status_code == 200
    friend_list = product_client.get("/api/jobs").json()["items"][0]
    assert friend_list["reviewStatus"] == "VIEWED"
    assert friend_list["applicationStatus"] == "NOT_STARTED"

    assert product_client.post("/api/auth/logout").status_code == 204
    login(product_client)
    owner_job = product_client.get(f"/api/jobs/{job_id}").json()
    assert owner_job["state"]["relevanceLabel"] == "DREAM"
    assert owner_job["application"]["status"] == "APPLIED"
    assert owner_job["milestones"][0]["title"] == "Owner interview"


def test_worker_claim_failure_retry_and_idempotent_callback(
    product_client: TestClient,
) -> None:
    login(product_client)
    batch_id, job_id = create_test_job(product_client)
    assert product_client.post(f"/api/batches/{batch_id}/normalize").status_code == 200
    assert product_client.post(f"/api/batches/{batch_id}/rank").status_code == 202

    assert product_client.post("/internal/processing-runs/claim").status_code == 401
    assert (
        product_client.post(
            "/internal/processing-runs/claim",
            headers={"X-JEDI-SERVICE-TOKEN": "wrong"},
        ).status_code
        == 401
    )

    service_headers = {
        "X-JEDI-SERVICE-TOKEN": get_settings().ml_service_secret,
    }
    claimed = product_client.post(
        "/internal/processing-runs/claim",
        headers=service_headers,
    )
    assert claimed.status_code == 200
    lease = claimed.json()
    assert lease["batchId"] == batch_id
    assert lease["profileVersionId"] == "profile-1"
    assert lease["featureSchemaVersion"] == "prepared-job-v2"
    assert lease["jobs"][0]["jobId"] == job_id
    assert (
        product_client.post(
            "/internal/processing-runs/claim",
            headers=service_headers,
        ).status_code
        == 204
    )

    run_id = lease["runId"]
    assert (
        product_client.post(
            f"/internal/processing-runs/{run_id}/heartbeat",
            headers={**service_headers, "X-JEDI-LEASE-TOKEN": "wrong"},
        ).status_code
        == 409
    )
    lease_headers = {
        **service_headers,
        "X-JEDI-LEASE-TOKEN": lease["leaseToken"],
    }
    assert (
        product_client.post(
            f"/internal/processing-runs/{run_id}/heartbeat",
            headers=lease_headers,
        ).status_code
        == 200
    )
    failed = product_client.post(
        f"/internal/processing-runs/{run_id}/fail",
        headers=lease_headers,
        json={
            "errorCode": "MODEL_LOAD_FAILED",
            "errorMessage": "  Safe   model load failure.  ",
        },
    )
    assert failed.status_code == 200
    assert failed.json()["batchStatus"] == "NORMALIZED"

    runs = product_client.get(f"/api/batches/{batch_id}/processing-runs")
    assert runs.status_code == 200
    assert runs.json()[0]["status"] == "FAILED"
    assert runs.json()[0]["errorCode"] == "MODEL_LOAD_FAILED"
    assert runs.json()[0]["errorMessage"] == "Safe model load failure."
    assert "leaseToken" not in runs.json()[0]

    retried = product_client.post(f"/api/batches/{batch_id}/rank")
    assert retried.status_code == 202
    assert retried.json()["processingRunId"] != run_id
    second_claim = product_client.post(
        "/internal/processing-runs/claim",
        headers=service_headers,
    )
    assert second_claim.status_code == 200
    second_lease = second_claim.json()
    callback_headers = {
        **service_headers,
        "X-JEDI-LEASE-TOKEN": second_lease["leaseToken"],
    }
    ranking_body = {
        "profileVersionId": "profile-1",
        "modelVersionId": "model-1",
        "rankings": [
            {
                "jobId": job_id,
                "rank": 1,
                "jediPreferenceScore": 93.0,
                "applyPreferenceProbability": 0.96,
                "componentScores": {"skills": 5},
                "rankingScore": 93.0,
                "applyThreshold": 0.6,
                "modelApplyDecision": True,
                "applyRecommendation": True,
            }
        ],
    }
    mismatch = product_client.post(
        f"/internal/batches/{batch_id}/rankings",
        headers=callback_headers,
        json={**ranking_body, "modelVersionId": "different-model"},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "CONFLICT"
    saved = product_client.post(
        f"/internal/batches/{batch_id}/rankings",
        headers=callback_headers,
        json=ranking_body,
    )
    assert saved.status_code == 200
    assert saved.json()["status"] == "RANKED"
    duplicate = product_client.post(
        f"/internal/batches/{batch_id}/rankings",
        headers=callback_headers,
        json=ranking_body,
    )
    assert duplicate.status_code == 200
    assert duplicate.json() == saved.json()


def test_embedded_execution_persists_complete_auditable_ranking(
    product_client: TestClient,
) -> None:
    login(product_client)
    batch_id, job_id = create_test_job(product_client)
    assert product_client.post(f"/api/batches/{batch_id}/normalize").status_code == 200
    queued = product_client.post(f"/api/batches/{batch_id}/rank")
    assert queued.status_code == 202
    run_id = queued.json()["processingRunId"]

    executed = product_client.post(f"/api/processing-runs/{run_id}/execute")
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "SUCCEEDED"
    assert executed.json()["rankingCount"] == 1

    rankings = product_client.get(f"/api/batches/{batch_id}/rankings").json()
    assert len(rankings) == 1
    assert rankings[0]["jobId"] == job_id
    assert rankings[0]["rankingStrategy"] == "apply-gate-then-jedi-v1"
    assert rankings[0]["applyThreshold"] == 0.6
    assert rankings[0]["outputSchemaVersion"] == "score-response-v1"

    runs = product_client.get(f"/api/batches/{batch_id}/processing-runs").json()
    ranking_run = next(item for item in runs if item["id"] == run_id)
    assert ranking_run["phase"] == "COMPLETED"
    assert ranking_run["invocation"]["outputCount"] == 1
    assert ranking_run["invocation"]["rawResponse"]["results"][0]["jobId"] == job_id


def test_expired_worker_lease_stops_after_three_attempts(
    product_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    login(product_client)
    batch_id, _ = create_test_job(product_client)
    product_client.post(f"/api/batches/{batch_id}/normalize")
    product_client.post(f"/api/batches/{batch_id}/rank")
    monkeypatch.setattr(operations, "LEASE_DURATION", timedelta(seconds=-1))
    headers = {"X-JEDI-SERVICE-TOKEN": get_settings().ml_service_secret}

    attempts = [
        product_client.post(
            "/internal/processing-runs/claim",
            headers=headers,
        )
        for _ in range(3)
    ]
    assert [response.status_code for response in attempts] == [200, 200, 200]
    assert (
        product_client.post(
            "/internal/processing-runs/claim",
            headers=headers,
        ).status_code
        == 204
    )

    runs = product_client.get(f"/api/batches/{batch_id}/processing-runs").json()
    ranking_run = next(run for run in runs if run["stage"] == "ranking")
    assert ranking_run["attempt"] == 3
    assert ranking_run["status"] == "FAILED"
    assert ranking_run["errorCode"] == "RETRY_EXHAUSTED"


class FakeEmailTransport:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.snapshots: list[dict] = []

    async def send(self, delivery) -> str:
        self.snapshots.append(delivery.payload_snapshot)
        if self.fail:
            raise RuntimeError("secret provider failure")
        return delivery.message_id


def test_ranking_enqueues_personalized_events_and_cron_sends(
    product_client: TestClient,
) -> None:
    settings = get_settings()
    original = (
        settings.gmail_smtp_user,
        settings.gmail_smtp_app_password,
        settings.cron_secret,
    )
    transport = FakeEmailTransport()
    settings.gmail_smtp_user = "sender@example.com"
    settings.gmail_smtp_app_password = "test-app-password"
    settings.cron_secret = "c" * 64
    app.dependency_overrides[get_email_transport] = lambda: transport

    try:
        login(product_client)
        assert (
            product_client.post(
                "/api/onboarding",
                json={
                    "resumeText": "Python FastAPI backend engineer",
                    "preferredTitles": ["Backend Engineer"],
                    "preferredLocations": ["Remote"],
                    "preferredSkills": ["Python", "FastAPI"],
                },
            ).status_code
            == 200
        )
        configured = product_client.patch(
            "/api/email/settings",
            json={"enabled": True, "sendAfterRanking": True},
        )
        assert configured.status_code == 200

        payload = batch_payload()
        created = product_client.post("/api/batches", json=payload)
        batch_id = created.json()["batchId"]
        job_id = product_client.get(f"/api/batches/{batch_id}").json()["jobs"][0]["id"]
        product_client.post(f"/api/batches/{batch_id}/normalize")
        product_client.post(f"/api/batches/{batch_id}/rank")
        body = {
            "profileVersionId": "profile-1",
            "modelVersionId": "model-1",
            "rankings": [
                {
                    "jobId": job_id,
                    "rank": 1,
                    "jediPreferenceScore": 92,
                    "applyPreferenceProbability": 0.95,
                    "componentScores": {"skills_fit": 5, "title_fit": 4},
                    "rankingScore": 92,
                    "applyThreshold": 0.6,
                    "modelApplyDecision": True,
                    "applyRecommendation": True,
                }
            ],
        }
        ranked = product_client.post(
            f"/api/batches/{batch_id}/rankings",
            json=body,
        )
        assert ranked.status_code == 200, ranked.text
        assert ranked.json()["status"] == "RANKED"
        assert ranked.json()["emailDelivery"] is None

        history = product_client.get(f"/api/batches/{batch_id}/email-deliveries")
        assert history.status_code == 200
        assert {item["status"] for item in history.json()} == {"UNTOUCHED", "BLOCKED"}
        assert product_client.get("/internal/email-deliveries/run").status_code == 401

        cron = product_client.get(
            "/internal/email-deliveries/run",
            headers={"Authorization": f"Bearer {settings.cron_secret}"},
        )
        assert cron.status_code == 200
        assert cron.json()["status"] == "processed"
        assert cron.json()["sent"] == 1
        assert transport.snapshots[-1]["templateVersion"] == "personalized-top-ten-v3"
        ledger = product_client.get("/api/email/events?page=1&pageSize=25")
        assert ledger.status_code == 200
        assert ledger.json()["total"] == 2
        assert ledger.json()["statusCounts"]["SENT"] == 1
        sent_event = next(
            item for item in ledger.json()["items"] if item["status"] == "SENT"
        )
        assert sent_event["attemptHistory"][0]["trigger"] == "CRON"
        assert sent_event["attemptHistory"][0]["status"] == "SENT"

        # A rerank gets a distinct event; a row send never drains other events.
        rerun = product_client.post(f"/api/batches/{batch_id}/rank")
        assert rerun.status_code == 202
        assert (
            product_client.post(
                f"/api/batches/{batch_id}/rankings", json=body
            ).status_code
            == 200
        )
        reranked_ledger = product_client.get("/api/email/events?pageSize=25").json()
        queued_event = next(
            item
            for item in reranked_ledger["items"]
            if item["status"] == "UNTOUCHED"
            and item["recipient"] == "owner@example.com"
        )
        manual_one = product_client.post(f"/api/email/events/{queued_event['id']}/send")
        assert manual_one.status_code == 200
        assert manual_one.json()["event"]["status"] == "SENT"
        assert manual_one.json()["event"]["attemptHistory"][0]["trigger"] == "MANUAL"

        calls_before = len(transport.snapshots)
        manual = product_client.post("/api/email/manual-dispatch")
        assert manual.status_code == 200
        assert manual.json()["ready"] is True
        assert manual.json()["sent"] == 0
        assert len(transport.snapshots) == calls_before
        assert (
            product_client.get(
                "/internal/email-deliveries/run",
                headers={"Authorization": f"Bearer {settings.cron_secret}"},
            ).json()["status"]
            == "empty"
        )
    finally:
        app.dependency_overrides.pop(get_email_transport, None)
        (
            settings.gmail_smtp_user,
            settings.gmail_smtp_app_password,
            settings.cron_secret,
        ) = original


def test_owner_idempotently_creates_member_mail_events(
    product_client: TestClient,
) -> None:
    assert product_client.post("/api/batches/unknown/mail-events").status_code == 401
    login(product_client)
    onboarding = product_client.post(
        "/api/onboarding",
        json={
            "resumeText": "Python FastAPI engineer",
            "preferredTitles": ["Backend Engineer"],
            "preferredLocations": ["Remote"],
            "preferredSkills": ["Python", "FastAPI"],
            "experienceMinYears": 0,
            "experienceMaxYears": 3,
            "salaryCurrency": "INR",
        },
    )
    assert onboarding.status_code == 200
    legacy_recipient = product_client.post(
        "/api/email/recipients",
        json={"email": "legacy-unlinked@example.com"},
    )
    assert legacy_recipient.status_code == 201
    model = product_client.post(
        "/api/models",
        json={
            "name": "mail-event-model-v2",
            "artifactManifest": BUNDLE_MANIFEST,
            "featureSchemaVersion": "prepared-job-v2",
        },
    )
    assert model.status_code == 201
    model_id = model.json()["id"]
    assert (
        product_client.post(f"/api/models/{model_id}/deployment-check").status_code
        == 200
    )
    assert product_client.post(f"/api/models/{model_id}/activate").status_code == 200

    created = product_client.post("/api/batches", json=batch_payload())
    batch_id = created.json()["batchId"]
    before_ranking = product_client.post(f"/api/batches/{batch_id}/mail-events")
    assert before_ranking.status_code == 409

    job_id = product_client.get(f"/api/batches/{batch_id}").json()["jobs"][0]["id"]
    assert product_client.post(f"/api/batches/{batch_id}/normalize").status_code == 200
    queued = product_client.post(f"/api/batches/{batch_id}/rank")
    assert queued.status_code == 202, queued.text
    ranked = product_client.post(
        f"/api/batches/{batch_id}/rankings",
        json={
            "profileVersionId": "profile-1",
            "modelVersionId": model_id,
            "rankings": [
                {
                    "jobId": job_id,
                    "rank": 1,
                    "jediPreferenceScore": 92,
                    "applyPreferenceProbability": 0.95,
                    "rankingScore": 92,
                    "applyThreshold": 0.6,
                    "modelApplyDecision": True,
                    "applyRecommendation": True,
                }
            ],
        },
    )
    assert ranked.status_code == 200

    first = product_client.post(f"/api/batches/{batch_id}/mail-events")
    assert first.status_code == 200
    assert first.json()["createdCount"] == 0
    assert first.json()["existingCount"] == 2
    assert first.json()["eligibleRecipientCount"] == 1
    assert first.json()["skippedRecipientCount"] == 1

    replay = product_client.post(f"/api/batches/{batch_id}/mail-events")
    assert replay.status_code == 200
    assert replay.json()["createdCount"] == 0
    assert replay.json()["existingCount"] == 2
    history = product_client.get(f"/api/batches/{batch_id}/email-deliveries")
    assert history.status_code == 200
    assert len(history.json()) == 2
    assert {item["status"] for item in history.json()} == {"UNTOUCHED", "BLOCKED"}
    assert all(item["attempts"] == 0 for item in history.json())

    ledger = product_client.get("/api/email/events?status=BLOCKED&pageSize=10")
    assert ledger.status_code == 200
    assert ledger.json()["total"] == 1
    blocked_id = ledger.json()["items"][0]["id"]
    assert (
        product_client.post(f"/api/email/events/{blocked_id}/requeue").status_code
        == 409
    )
    assert (
        product_client.post(f"/api/email/events/{blocked_id}/cancel").status_code == 200
    )

    product_client.post("/api/auth/logout")
    friend_login = product_client.post(
        "/api/auth/login",
        json={"email": "friend@example.com", "password": "friend password"},
    )
    assert friend_login.status_code == 200
    forbidden = product_client.post(f"/api/batches/{batch_id}/mail-events")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "GROUP_OWNER_REQUIRED"
    assert product_client.get("/api/email/events").status_code == 403


def test_email_settings_and_recipient_crud(product_client: TestClient) -> None:
    settings = get_settings()
    original_smtp = (
        settings.gmail_smtp_user,
        settings.gmail_smtp_app_password,
    )
    settings.gmail_smtp_user = ""
    settings.gmail_smtp_app_password = ""
    assert product_client.get("/api/email/settings").status_code == 401
    assert product_client.get("/api/email/recipients").status_code == 401
    assert product_client.post("/api/email/manual-dispatch").status_code == 401
    assert (
        product_client.post(
            "/api/email/recipients",
            json={"email": "person@example.com"},
        ).status_code
        == 401
    )
    assert (
        product_client.patch(
            "/api/email/recipients/unknown",
            json={"active": False},
        ).status_code
        == 401
    )
    assert product_client.delete("/api/email/recipients/unknown").status_code == 401

    login(product_client)
    try:
        manual_dispatch = product_client.post("/api/email/manual-dispatch")
        assert manual_dispatch.status_code == 409
        assert "SMTP" in manual_dispatch.json()["error"]["message"]

        initial = product_client.get("/api/email/settings")
        assert initial.status_code == 200
        assert initial.json()["activeRecipientCount"] == 0
        assert initial.json()["recipientLimit"] == 50
        assert initial.json()["scheduledTime"] == "00:00"

        unavailable = product_client.patch(
            "/api/email/settings",
            json={"enabled": True},
        )
        assert unavailable.status_code == 409
        assert unavailable.json()["error"]["code"] == "CONFLICT"

        settings.gmail_smtp_user = "sender@example.com"
        settings.gmail_smtp_app_password = "test-app-password"
        configured = product_client.patch(
            "/api/email/settings",
            json={
                "enabled": True,
                "senderName": " JEDI Dispatch ",
                "sendAfterRanking": False,
            },
        )
        assert configured.status_code == 200
        assert configured.json()["senderName"] == "JEDI Dispatch"
        assert configured.json()["transportConfigured"] is True

        assert (
            product_client.post(
                "/api/email/recipients",
                json={"email": "not-an-email"},
            ).status_code
            == 422
        )
        created = product_client.post(
            "/api/email/recipients",
            json={"email": "Person@Example.com", "displayName": "Person"},
        )
        assert created.status_code == 201
        recipient_id = created.json()["id"]
        assert created.json()["replayed"] is False

        replay = product_client.post(
            "/api/email/recipients",
            json={"email": "person@example.com", "displayName": "Person"},
        )
        assert replay.status_code == 200
        assert replay.json()["id"] == recipient_id
        assert replay.json()["replayed"] is True

        detail = product_client.get(f"/api/email/recipients/{recipient_id}")
        assert detail.status_code == 200
        disabled = product_client.patch(
            f"/api/email/recipients/{recipient_id}",
            json={"displayName": "Updated Person", "active": False},
        )
        assert disabled.json()["active"] is False
        assert len(product_client.get("/api/email/recipients?active=false").json()) == 1

        reactivated = product_client.post(
            "/api/email/recipients",
            json={
                "email": "person@example.com",
                "displayName": "Updated Person",
            },
        )
        assert reactivated.status_code == 200
        assert reactivated.json()["reactivated"] is True

        second = product_client.post(
            "/api/email/recipients",
            json={"email": "second@example.com"},
        ).json()
        conflict = product_client.patch(
            f"/api/email/recipients/{second['id']}",
            json={"email": "PERSON@example.com"},
        )
        assert conflict.status_code == 409

        assert (
            product_client.delete(f"/api/email/recipients/{recipient_id}").status_code
            == 204
        )
        assert all(
            item["id"] != recipient_id
            for item in product_client.get("/api/email/recipients").json()
        )
        deleted = product_client.get("/api/email/recipients?includeDeleted=true").json()
        assert next(item for item in deleted if item["id"] == recipient_id)["deletedAt"]

        # One active recipient already exists. Add 49 more, then enforce the cap.
        for index in range(49):
            assert (
                product_client.post(
                    "/api/email/recipients",
                    json={"email": f"recipient-{index}@example.com"},
                ).status_code
                == 201
            )
        over_limit = product_client.post(
            "/api/email/recipients",
            json={"email": "recipient-over-limit@example.com"},
        )
        assert over_limit.status_code == 409
        assert (
            product_client.get("/api/email/settings").json()["activeRecipientCount"]
            == 50
        )
    finally:
        settings.gmail_smtp_user, settings.gmail_smtp_app_password = original_smtp


def test_batch_normalization_and_ranking_use_group_versions(product_client):
    """An unrelated globally active contract must not affect this group's jobs."""

    async def change_global_contracts():
        async for session in app.dependency_overrides[get_session]():
            profile = await session.get(ProfileVersion, "profile-1")
            model = await session.get(ModelVersion, "model-1")
            profile.active = False
            model.active = False
            session.add(
                ProfileVersion(
                    id="unrelated-profile",
                    content_hash="unrelated-hash",
                    resume_text="Unrelated sales profile",
                    preferred_titles=["Sales"],
                    preferred_locations=[],
                    preferred_skills=[],
                    active=True,
                )
            )
            session.add(
                ModelVersion(
                    id="unrelated-model",
                    name="unrelated-model",
                    artifact_manifest=BUNDLE_MANIFEST,
                    feature_schema_version="prepared-job-v2",
                    request_contract_version="score-request-v1",
                    active=True,
                )
            )
            await session.commit()

    asyncio.run(change_global_contracts())
    product_client.post(
        "/api/auth/login",
        json={
            "email": "friend@example.com",
            "password": "friend password",
        },
    )
    batch_id = product_client.post("/api/batches", json=batch_payload()).json()[
        "batchId"
    ]
    normalized = product_client.post(f"/api/batches/{batch_id}/normalize")
    assert normalized.status_code == 200
    assert normalized.json()["profileVersionId"] == "profile-1"
    detail = product_client.get(f"/api/batches/{batch_id}").json()
    assert detail["normalizationComplete"] is True
    assert detail["actions"]["canProcessRanks"] is True
    queued = product_client.post(f"/api/batches/{batch_id}/rank")
    assert queued.status_code == 202
    runs = product_client.get(f"/api/batches/{batch_id}/processing-runs").json()
    ranking = next(run for run in runs if run["id"] == queued.json()["processingRunId"])
    assert ranking["profileVersionId"] == "profile-1"
    assert ranking["modelVersionId"] == "model-1"
    executed = product_client.post(
        f"/api/processing-runs/{ranking['id']}/execute"
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "SUCCEEDED"
    assert executed.json()["rankingCount"] == 1
