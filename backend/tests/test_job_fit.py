# ruff: noqa: F401, F811

from datetime import UTC, datetime
from uuid import uuid4

from backend.schemas.job_intake import (
    DraftFitReport,
    JobDraftDetail,
    JobRequirement,
    SkillFitFinding,
)
from backend.schemas.learning import ResumeEvidence
from backend.services.job_fit import assess_documented_fit, compare_draft
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


def test_documented_fit_weights_and_withholds_uncertain_scores():
    report = DraftFitReport(has_resume=True, job_minimum_years=3, resume_years=4)
    for name, status in (("React", "evidenced"), ("AWS", "not_evidenced")):
        report.findings.append(
            SkillFitFinding(
                requirement=JobRequirement(
                    level="required", match="all", skills=[name], text=name
                ),
                status=status,
                evidence=[],
            )
        )
    assert assess_documented_fit(report).score == 60
    report.resume_years = 2
    assert assess_documented_fit(report).score == 40
    assert assess_documented_fit(report).role_experience == "below_minimum"
    report.findings[1].status = "needs_review"
    assert assess_documented_fit(report).score is None


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


def test_pasted_resume_preview_and_deletion_are_private(product_client):
    login(product_client)
    preview = product_client.post("/api/resume/extract-text", json={"text": RESUME})
    assert preview.status_code == 200, preview.text
    assert "React" in preview.json()["explicitSkills"]
    assert product_client.get("/api/resume").json() is None
    assert product_client.put("/api/resume", json=preview.json()).status_code == 200

    member = product_client.post(
        "/api/auth/login",
        json={"email": "friend@example.com", "password": "friend password"},
    )
    assert member.status_code == 200
    assert product_client.delete("/api/resume").status_code == 204
    login(product_client)
    assert product_client.get("/api/resume").json()["text"] == preview.json()["text"]
    assert product_client.delete("/api/resume").status_code == 204
    assert product_client.delete("/api/resume").status_code == 204
    assert product_client.get("/api/resume").json() is None


def test_fit_snapshot_keeps_reviewed_inputs_and_respects_retention(product_client):
    login(product_client)
    path = f"/api/job-drafts/{uuid4()}"
    fields = preview_job(DESCRIPTION).fields.model_dump(mode="json", by_alias=True)
    assert (
        product_client.put(
            path, json={"description": DESCRIPTION, "fields": fields, "revision": 0}
        ).status_code
        == 200
    )
    resume = {"text": RESUME, "explicitSkills": ["React"]}
    assert product_client.put("/api/resume", json=resume).status_code == 200
    fit = f"{path}/skill-fit"
    snapshots = f"{fit}/saved"
    initial = product_client.get(f"{fit}?revision=1").json()
    payload = {"draftRevision": 1, "inputVersion": initial["inputVersion"]}
    saved = product_client.put(snapshots, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["report"] == initial
    assert "inputs" not in saved.json()
    assert "no-store" in product_client.get(snapshots).headers["cache-control"]

    changed_resume = {**resume, "explicitSkills": ["Kubernetes"]}
    assert product_client.put("/api/resume", json=changed_resume).status_code == 200
    assert product_client.put(snapshots, json=payload).json() == saved.json()
    latest = product_client.get(f"{fit}?revision=1").json()
    assert latest["inputVersion"] != initial["inputVersion"]
    assert product_client.get(snapshots).json()["report"] == initial
    replacement = {**payload, "inputVersion": latest["inputVersion"]}
    assert product_client.put(snapshots, json=replacement).status_code == 409
    replacement["expectedSavedVersion"] = initial["inputVersion"]
    assert product_client.put(snapshots, json=replacement).json()["report"] == latest
    assert (
        product_client.delete(
            f"{snapshots}?inputVersion={initial['inputVersion']}"
        ).status_code
        == 409
    )

    member = product_client.post(
        "/api/auth/login",
        json={"email": "friend@example.com", "password": "friend password"},
    )
    assert member.status_code == 200
    assert product_client.get(snapshots).status_code == 404
    assert product_client.put(snapshots, json=replacement).status_code == 404
    assert product_client.delete("/api/resume").status_code == 204
    login(product_client)
    assert product_client.get(snapshots).json()["report"] == latest
    assert (
        product_client.delete(
            f"{snapshots}?inputVersion={latest['inputVersion']}"
        ).status_code
        == 204
    )
    assert product_client.get(snapshots).json() is None
    assert product_client.put(snapshots, json=payload).status_code == 409
    assert (
        product_client.put(
            snapshots, json={**replacement, "expectedSavedVersion": None}
        ).status_code
        == 200
    )
    assert product_client.delete("/api/resume").status_code == 204
    assert product_client.get(snapshots).json() is None
