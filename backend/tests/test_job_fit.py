# ruff: noqa: F401, F811

from datetime import UTC, datetime
from uuid import uuid4

from backend.schemas.job_intake import JobDraftDetail
from backend.schemas.learning import ResumeEvidence
from backend.services.job_fit import compare_draft
from backend.services.job_intake import preview_job
from backend.tests.test_learning import RESUME
from backend.tests.test_product_api import login, product_client

DESCRIPTION = """Job title: Backend Engineer
Requirements:
3+ years of Python or Java
React.js
Kubernetes
Preferred skills:
Machine learning
"""


def test_draft_fit_preserves_alternatives_and_does_not_infer_years():
    preview = preview_job(DESCRIPTION)
    draft = JobDraftDetail(
        **preview.model_dump(),
        id=uuid4(),
        description=DESCRIPTION,
        revision=1,
        updated_at=datetime.now(UTC),
    )
    resume = ResumeEvidence(
        text="Java developer\nReactJS\nNo Kubernetes experience\nPyTorch",
        explicit_skills=["ReactJS", "Java", "PyTorch"],
        experience_years=7,
    )
    report = compare_draft(draft, resume)
    results = {tuple(item.requirement.skills): item for item in report.findings}
    assert results[("Python", "Java")].status == "needs_review"
    assert results[("Python", "Java")].requirement.experience_min_years == 3
    assert results[("React",)].status == "evidenced"
    assert results[("React",)].evidence == ["ReactJS"]
    assert results[("Kubernetes",)].status == "not_evidenced"
    assert results[("Machine Learning",)].status == "not_evidenced"
    assert report.job_minimum_years is None

    resume.explicit_skills.append("Supervised Learning")
    updated = compare_draft(draft, resume)
    assert updated.findings[-1].status == "needs_review"

    draft.requirements[0].experience_min_years = None
    assert compare_draft(draft, resume).findings[0].status == "evidenced"
    draft.fields.mentioned_skills.remove("Java")
    assert all(
        "Java" not in item.requirement.skills
        for item in compare_draft(draft, resume).findings
    )


def test_saved_draft_fit_reads_only_the_members_resume(product_client):
    login(product_client)
    path = f"/api/job-drafts/{uuid4()}"
    fields = preview_job(DESCRIPTION).fields.model_dump(mode="json", by_alias=True)
    saved = product_client.put(
        path, json={"description": DESCRIPTION, "fields": fields, "revision": 0}
    )
    assert saved.status_code == 200, saved.text
    fit = f"{path}/skill-fit?revision=1"
    assert product_client.get(fit).json()["hasResume"] is False
    assert product_client.get(f"{path}/skill-fit?revision=2").status_code == 409

    evidence = product_client.put(
        "/api/resume", json={"text": RESUME, "explicitSkills": ["React"]}
    )
    assert evidence.status_code == 200, evidence.text
    report = product_client.get(fit).json()
    assert report["hasResume"] is True
    assert any(
        item["requirement"]["skills"] == ["React"] and item["status"] == "evidenced"
        for item in report["findings"]
    )

    member = product_client.post(
        "/api/auth/login",
        json={"email": "friend@example.com", "password": "friend password"},
    )
    assert member.status_code == 200
    assert product_client.get(fit).status_code == 404
