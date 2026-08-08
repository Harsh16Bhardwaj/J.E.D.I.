"""Contracts for shared-group registration, invitations, and onboarding."""

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from backend.schemas.email_management import normalize_email
from backend.schemas.product import ApiModel


class GroupSummary(ApiModel):
    id: str
    name: str


class SessionUserResponse(ApiModel):
    id: str
    email: str
    group: GroupSummary | None
    is_group_owner: bool
    onboarding_complete: bool


class RegisterRequest(ApiModel):
    invite_code: str = Field(
        min_length=5,
        max_length=64,
        pattern=r"^[A-Za-z0-9]+$",
    )
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("invite_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class InvitationSummary(ApiModel):
    id: str
    expires_at: datetime
    revoked_at: datetime | None
    usage_count: int
    created_at: datetime


class InvitationCreated(InvitationSummary):
    code: str


class SharedProfileSummary(ApiModel):
    id: str
    resume_preview: str
    preferred_titles: list[str]
    preferred_locations: list[str]
    preferred_skills: list[str]


class SharedModelSummary(ApiModel):
    id: str
    name: str
    feature_schema_version: str


class MemberProfileInput(ApiModel):
    resume_text: str | None = Field(default=None, max_length=100_000)
    preferred_titles: list[str] = Field(default_factory=list, max_length=100)
    preferred_locations: list[str] = Field(default_factory=list, max_length=100)
    preferred_skills: list[str] = Field(default_factory=list, max_length=200)
    experience_min_years: float | None = Field(default=None, ge=0, le=80)
    experience_max_years: float | None = Field(default=None, ge=0, le=80)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default="INR", max_length=10)

    @model_validator(mode="after")
    def ranges_are_ordered(self) -> "MemberProfileInput":
        if (
            self.experience_min_years is not None
            and self.experience_max_years is not None
            and self.experience_min_years > self.experience_max_years
        ):
            raise ValueError("experienceMinYears cannot exceed experienceMaxYears")
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("salaryMin cannot exceed salaryMax")
        return self


class MemberProfileResponse(MemberProfileInput):
    id: str
    content_hash: str
    updated_at: datetime


class OnboardingState(ApiModel):
    group: GroupSummary
    onboarding_complete: bool
    ranking_mode: str = "SHARED_GROUP_PROFILE"
    shared_profile: SharedProfileSummary | None
    shared_model: SharedModelSummary | None
    member_profile: MemberProfileResponse | None
    suggested_titles: list[str]
    suggested_locations: list[str]
    suggested_skills: list[str]


class OnboardingResult(OnboardingState):
    replayed: bool
    initialized_shared_profile: bool = False
    message: str = (
        "Your profile is saved for future personalization. "
        "JEDI v1 currently uses the group ranking profile."
    )


class GroupMemberSummary(ApiModel):
    id: str
    email: str
    onboarding_complete: bool
    joined_at: datetime
    is_owner: bool


class GroupSettingsResponse(ApiModel):
    group: GroupSummary
    is_group_owner: bool
    member_count: int
    members: list[GroupMemberSummary]
    shared_profile: SharedProfileSummary | None
    shared_model: SharedModelSummary | None
