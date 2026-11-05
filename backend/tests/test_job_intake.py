# ruff: noqa: F401, F811

from uuid import uuid4

from fastapi.testclient import TestClient

from backend.services.job_intake import preview_job
from backend.tests.test_product_api import login, product_client

DESCRIPTION = """Job title: Frontend Engineer
Employer: Example Labs
Location: Bengaluru
Work mode: Hybrid
Requirements:
- React.js and ReactJS
- React Native
- 3-5 years of engineering experience
- Python or Java
Preferred skills:
- Supervised learning, unsupervised learning, and PyTorch
- Docker is not required
Responsibilities:
- Build accessible interfaces and maintain CI/CD.
"""


def test_preview_keeps_aliases_and_requirement_classes_separate() -> None:
    preview = preview_job(DESCRIPTION)
    fields = preview.fields
    assert (fields.title, fields.employer, fields.work_mode) == (
        "Frontend Engineer",
        "Example Labs",
        "HYBRID",
    )
    assert fields.required_skills == ["React", "React Native"]
    assert fields.preferred_skills == [
        "Supervised Learning",
        "Unsupervised Learning",
        "PyTorch",
    ]
    assert fields.mentioned_skills == ["Python", "Java", "Docker", "CI/CD"]
    assert (fields.experience_min_years, fields.experience_max_years) == (3, 5)
    assert fields.responsibilities == [
        "Build accessible interfaces and maintain CI/CD."
    ]
    assert any(
        item.field == "React" and "React.js" in item.text for item in preview.evidence
    )


def test_preview_leaves_preferred_years_and_conflicting_locations_unknown() -> None:
    preview = preview_job(
        "Location: London\nLocation: Pune\nPreferred skills:\n"
        "3+ years of backend experience and React Native."
    )
    assert preview.fields.location == ""
    assert preview.fields.experience_min_years is None
    assert preview.fields.preferred_skills == ["React Native"]
    assert preview.requirements[0].experience_min_years is None
    assert len(preview.warnings) == 2


def test_preview_preserves_alternatives_and_scopes_experience() -> None:
    preview = preview_job(
        "Backend Engineer II\n"
        "Requirements\n"
        "3+ years of Python or Java; AWS is a plus.\n"
        "SQL and Docker or Kubernetes required.\n"
        "JavaScript or 2 years of TypeScript.\n"
        "Go to the careers page. No Redis experience required."
    )
    assert preview.fields.title == "Backend Engineer II"
    assert any(item.field == "title" and item.inferred for item in preview.evidence)
    assert preview.fields.experience_min_years is None
    choice, preferred, mixed, asymmetric = preview.requirements
    assert (choice.level, choice.match, choice.skills) == (
        "required",
        "any",
        ["Python", "Java"],
    )
    assert choice.experience_min_years == 3
    assert (preferred.level, preferred.skills) == ("preferred", ["AWS"])
    assert mixed.match == "review"
    assert asymmetric.match == "any"
    assert asymmetric.experience_min_years is None
    assert "Go" not in preview.fields.required_skills
    assert "Redis" not in preview.fields.required_skills


def test_drafts_are_private_revision_checked_and_retryable(
    product_client: TestClient,
) -> None:
    base = "/api/job-drafts"
    assert product_client.get(base).status_code == 401
    login(product_client)
    preview = product_client.post(f"{base}/preview", json={"description": DESCRIPTION})
    assert preview.status_code == 200, preview.text
    assert "no-store" in preview.headers["cache-control"]
    assert product_client.get(base).json() == []
    assert (
        product_client.post(f"{base}/preview", json={"description": "   "}).status_code
        == 422
    )

    path = f"{base}/{uuid4()}"
    fields = {
        **preview.json()["fields"],
        "title": "Reviewed frontend role",
        "requiredSkills": ["React.js", "ReactJS", "React Native"],
    }
    original = {"description": DESCRIPTION, "fields": fields, "revision": 0}
    saved = product_client.put(path, json=original)
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1
    assert saved.json()["fields"]["requiredSkills"] == ["React", "React Native"]
    assert saved.json()["requirements"] == preview.json()["requirements"]
    assert product_client.put(path, json=original).json()["revision"] == 1

    updated = {
        **original,
        "fields": {**fields, "location": "Mumbai"},
        "revision": 1,
    }
    assert product_client.put(path, json=updated).json()["revision"] == 2
    assert product_client.put(path, json=original).status_code == 409
    assert product_client.delete(f"{path}?revision=1").status_code == 409
    assert product_client.get(path).json()["fields"]["location"] == "Mumbai"
    assert product_client.get(base).json()[0]["title"] == "Reviewed frontend role"

    member = product_client.post(
        "/api/auth/login",
        json={"email": "friend@example.com", "password": "friend password"},
    )
    assert member.status_code == 200
    assert product_client.get(base).json() == []
    assert product_client.get(path).status_code == 404
    assert product_client.put(path, json=updated).status_code == 404
    assert product_client.delete(f"{path}?revision=2").status_code == 204

    login(product_client)
    assert product_client.get(path).status_code == 200
    assert product_client.delete(f"{path}?revision=2").status_code == 204
    assert product_client.get(path).status_code == 404
