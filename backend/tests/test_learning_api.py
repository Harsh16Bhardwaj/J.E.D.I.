import asyncio
from datetime import timedelta
from io import BytesIO

from pypdf import PdfWriter
from sqlalchemy import select

from backend.database import LearningAttempt, utc_now
from backend.services.resume import parse_resume_text
from backend.tests.test_group_access import create_invite, login_owner
from backend.tests.test_learning import RESUME

pytest_plugins = ["backend.tests.test_group_access"]


def test_learning_requires_auth(group_client):
    client, _ = group_client
    assert client.get("/api/learning/topics").status_code == 401
    assert client.get("/api/resume").status_code == 401


def test_resume_review_is_private_and_independent_of_preferences(group_client):
    client, _ = group_client
    login_owner(client)
    assert client.get("/api/resume").json() is None
    evidence = parse_resume_text(RESUME).model_dump(by_alias=True)
    assert client.put("/api/resume", json=evidence).status_code == 200
    assert (
        client.get("/api/resume").json()["explicitSkills"] == evidence["explicitSkills"]
    )
    assert (
        client.get("/api/onboarding").json()["sharedProfile"]["resumePreview"]
        == "Python backend engineer"
    )
    invite = create_invite(client)
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/register",
            json={
                "inviteCode": invite["code"],
                "email": "other@example.com",
                "password": "correct horse",
            },
        ).status_code
        == 201
    )
    assert client.get("/api/resume").json() is None


def test_attempt_grading_locks_answers_and_hides_keys(group_client):
    client, _ = group_client
    login_owner(client)
    topics = client.get("/api/learning/topics").json()
    assert topics[0]["questionCount"] == 3
    response = client.post(
        "/api/learning/attempts",
        json={"topicId": "react-rendering", "questionCount": 2, "durationSeconds": 60},
    )
    assert response.status_code == 201
    attempt = response.json()
    assert "answer" not in attempt["questions"][0]
    assert "explanation" not in attempt["questions"][0]["options"][0]
    path = f"/api/learning/attempts/{attempt['id']}"
    first = attempt["questions"][0]
    answer = {"questionId": first["id"], "optionId": "a"}
    graded = client.post(path + "/answers", json=answer)
    assert graded.status_code == 200
    assert graded.json()["questions"][0]["answer"]["correctOptionId"]
    assert graded.json()["questions"][1].get("answer") is None
    assert client.post(path + "/answers", json=answer).status_code == 200
    answer["optionId"] = "b"
    assert client.post(path + "/answers", json=answer).status_code == 409
    finished = client.post(path + "/finish").json()
    assert finished["status"] == "FINISHED"
    assert finished["unanswered"] == 1
    assert client.post(path + "/answers", json=answer).status_code == 409
    invite = create_invite(client)
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={
            "inviteCode": invite["code"],
            "email": "outsider@example.com",
            "password": "correct horse",
        },
    )
    assert client.get(path).status_code == 404
    assert client.post(path + "/finish").status_code == 404


def test_attempt_bounds_and_expiry(group_client):
    client, factory = group_client
    login_owner(client)
    assert (
        client.post(
            "/api/learning/attempts",
            json={
                "topicId": "react-rendering",
                "questionCount": 4,
                "durationSeconds": 60,
            },
        ).status_code
        == 422
    )
    attempt = client.post(
        "/api/learning/attempts",
        json={"topicId": "react-rendering", "questionCount": 1, "durationSeconds": 30},
    ).json()

    async def expire():
        async with factory() as session:
            row = await session.scalar(
                select(LearningAttempt).where(LearningAttempt.id == attempt["id"])
            )
            row.deadline_at = utc_now() - timedelta(seconds=1)
            await session.commit()

    asyncio.run(expire())
    path = f"/api/learning/attempts/{attempt['id']}"
    assert (
        client.post(
            path + "/answers",
            json={"questionId": attempt["questions"][0]["id"], "optionId": "b"},
        ).status_code
        == 409
    )
    result = client.get(path).json()
    assert result["status"] == "EXPIRED"
    assert result["unanswered"] == 1


def test_upload_rejects_arbitrary_and_unreadable_pdf(group_client):
    client, _ = group_client
    login_owner(client)
    result = client.post(
        "/api/resume/extract",
        files={"file": ("resume.pdf", b"fake PDF", "application/pdf")},
    )
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "INVALID_PDF"
    writer = PdfWriter()
    writer.add_blank_page(600, 800)
    output = BytesIO()
    writer.write(output)
    result = client.post(
        "/api/resume/extract",
        files={"file": ("resume.pdf", output.getvalue(), "application/pdf")},
    )
    assert result.json()["error"]["code"] == "UNREADABLE_RESUME"


def test_valid_upload_review_and_dynamic_job_track(group_client):
    from backend.database import Batch, Job
    from backend.tests.test_learning import make_resume_pdf

    client, factory = group_client
    login_owner(client)
    upload = client.post(
        "/api/resume/extract",
        files={"file": ("resume.pdf", make_resume_pdf(), "application/pdf")},
    )
    assert upload.status_code == 200
    assert "React" in upload.json()["explicitSkills"]
    assert client.get("/api/resume").json() is None  # Review is not an implicit save.
    non_resume = client.post(
        "/api/resume/extract",
        files={
            "file": (
                "guide.pdf",
                make_resume_pdf(
                    "Docker React Guide\n" + "How to build containers. " * 30
                ),
                "application/pdf",
            )
        },
    )
    assert non_resume.json()["error"]["code"] == "INVALID_RESUME"

    async def add_job():
        async with factory() as session:
            session.add(
                Batch(
                    id="learn-batch",
                    external_batch_id="learn-batch",
                    content_hash="learn-batch",
                    schema_version="1",
                    generated_at=utc_now(),
                    raw_envelope={},
                )
            )
            await session.flush()
            session.add(
                Job(
                    id="learn-job",
                    code="L-1",
                    dedupe_key="learn-job",
                    company_key="example",
                    batch_id="learn-batch",
                    company_name="Example",
                    role_title="Frontend Engineer",
                    description="React is required. Docker is preferred.",
                    skills=["React", "Docker"],
                    apply_url="https://example.com",
                )
            )
            await session.commit()

    asyncio.run(add_job())
    path = "/api/jobs/learn-job/skill-gap"
    assert client.get(path).json()["hasResume"] is False
    evidence = upload.json()
    evidence["explicitSkills"] = ["Python"]
    evidence["inferredSkills"] = []
    client.put("/api/resume", json=evidence)
    gap = client.get(path).json()
    assert gap["missing"][0]["topicIds"] == ["react-rendering"]
    evidence["explicitSkills"].append("React")
    client.put("/api/resume", json=evidence)
    gap = client.get(path).json()
    assert gap["matched"][0]["skill"] == "React"
    assert all(x["skill"] != "React" for x in gap["missing"])
    attempt = client.post(
        "/api/learning/attempts",
        json={
            "topicId": "react-rendering",
            "questionCount": 1,
            "durationSeconds": 60,
            "jobId": "learn-job",
        },
    )
    assert attempt.json()["jobId"] == "learn-job"


def test_new_backend_banks_start_and_grade_sprints(group_client):
    client, _ = group_client
    login_owner(client)
    available = {item["topicId"] for item in client.get("/api/learning/topics").json()}
    for topic in ("python-fundamentals", "fastapi-fundamentals", "sql-fundamentals"):
        assert topic in available
        response = client.post(
            "/api/learning/attempts",
            json={
                "topicId": topic,
                "questionCount": 3,
                "durationSeconds": 60,
            },
        )
        assert response.status_code == 201
        attempt = response.json()
        assert len(attempt["questions"]) == 3
        assert all("answer" not in item for item in attempt["questions"])
        question = attempt["questions"][0]
        graded = client.post(
            f"/api/learning/attempts/{attempt['id']}/answers",
            json={
                "questionId": question["id"],
                "optionId": "a",
            },
        )
        assert graded.status_code == 200
        assert graded.json()["questions"][0]["answer"]["explanation"]


def test_tutor_requires_submitted_answer_and_keeps_grade_unchanged(
    group_client, monkeypatch
):
    from backend.routers import learning

    client, _ = group_client
    login_owner(client)
    attempt = client.post(
        "/api/learning/attempts",
        json={
            "topicId": "react-rendering",
            "questionCount": 1,
            "durationSeconds": 60,
        },
    ).json()
    question = attempt["questions"][0]
    path = f"/api/learning/attempts/{attempt['id']}"
    body = {"questionId": question["id"]}
    assert client.post(path + "/tutor", json=body).status_code == 409
    client.post(path + "/answers", json={"questionId": question["id"], "optionId": "a"})
    before = client.get(path).json()

    async def provider(stored_question, selected, message, history):
        assert stored_question["id"] == question["id"]
        assert stored_question["answer"]["correctOptionId"]
        assert selected == "a"
        return "A helpful explanation."

    monkeypatch.setattr(learning, "explain_answer", provider)
    reply = client.post(path + "/tutor", json=body)
    assert reply.status_code == 200
    assert reply.json()["reply"] == "A helpful explanation."
    after = client.get(path).json()
    assert after["correct"] == before["correct"]
    assert after["questions"] == before["questions"]
    assert (
        client.post(path + "/tutor", json={"questionId": "unknown"}).status_code == 404
    )
    assert (
        client.post(path + "/tutor", json={**body, "message": "x" * 1001}).status_code
        == 422
    )
    invite = create_invite(client)
    client.post("/api/auth/logout")
    assert client.post(path + "/tutor", json=body).status_code == 401
    assert (
        client.post(
            "/api/auth/register",
            json={
                "inviteCode": invite["code"],
                "email": "tutor-other@example.com",
                "password": "correct horse",
            },
        ).status_code
        == 201
    )
    assert client.post(path + "/tutor", json=body).status_code == 404
