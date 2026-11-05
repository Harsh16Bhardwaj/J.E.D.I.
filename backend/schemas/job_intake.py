"""Contracts for member-private pasted job drafts."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from backend.schemas.product import ApiModel

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Skill = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=20, max_length=20_000)
]
Responsibility = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000)
]


class PasteJobRequest(ApiModel):
    description: Description


class LinkJobRequest(ApiModel):
    url: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)
    ]


class JobDraftFields(ApiModel):
    title: ShortText = ""
    employer: ShortText = ""
    location: ShortText = ""
    work_mode: Literal["REMOTE", "HYBRID", "ON_SITE"] | None = None
    employment_type: ShortText = ""
    education: ShortText = ""
    authorization: ShortText = ""
    compensation: ShortText = ""
    experience_min_years: float | None = Field(default=None, ge=0, le=80)
    experience_max_years: float | None = Field(default=None, ge=0, le=80)
    required_skills: list[Skill] = Field(default_factory=list, max_length=100)
    preferred_skills: list[Skill] = Field(default_factory=list, max_length=100)
    mentioned_skills: list[Skill] = Field(default_factory=list, max_length=100)
    responsibilities: list[Responsibility] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def validate_experience_range(self):
        if (
            self.experience_min_years is not None
            and self.experience_max_years is not None
            and self.experience_min_years > self.experience_max_years
        ):
            raise ValueError("Maximum experience must be at least the minimum.")
        return self


class JobEvidence(ApiModel):
    field: str
    text: str
    inferred: bool = False


class JobRequirement(ApiModel):
    level: Literal["required", "preferred", "uncertain"]
    match: Literal["all", "any", "review"]
    skills: list[str]
    experience_min_years: float | None = None
    experience_max_years: float | None = None
    text: str


class JobPreview(ApiModel):
    fields: JobDraftFields
    evidence: list[JobEvidence]
    warnings: list[str]
    requirements: list[JobRequirement] = Field(default_factory=list)
    source_url: str | None = None


class LinkedJobPreview(JobPreview):
    source_url: str
    description: Description


class SaveJobDraft(PasteJobRequest):
    fields: JobDraftFields
    revision: int = Field(ge=0)
    source_url: str | None = Field(default=None, max_length=2_000)


class JobDraftSummary(ApiModel):
    id: UUID
    title: str
    employer: str
    updated_at: datetime


class JobDraftDetail(JobPreview):
    id: UUID
    description: str
    revision: int
    updated_at: datetime


class SkillFitFinding(ApiModel):
    requirement: JobRequirement
    status: Literal["evidenced", "needs_review", "not_evidenced"]
    evidence: list[str]
    note: str | None = None


class DraftFitReport(ApiModel):
    has_resume: bool
    findings: list[SkillFitFinding] = Field(default_factory=list)
    job_minimum_years: float | None = None
    resume_years: float | None = None
