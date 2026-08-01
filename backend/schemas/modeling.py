"""Strict, versioned contracts shared by model training and inference."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Reject contract drift instead of silently discarding unknown fields."""

    model_config = ConfigDict(extra="forbid")


class PreparedJobSourceV2(StrictModel):
    """Inference-available semantic values used to build model features."""

    job_id: str = Field(min_length=1)
    code: str = Field(min_length=1)
    company_name: str
    company_key: str
    role_title: str
    role_family: str = ""
    seniority: str = ""
    location: str = ""
    work_mode: str = ""
    employment_type: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    experience_min_years: float | None = Field(default=None, ge=0, le=80)
    experience_max_years: float | None = Field(default=None, ge=0, le=80)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str = ""
    can_apply_now: bool | None = None
    posted_at: datetime | None = None
    feature_reference_at: datetime | None = None

    resume_text: str = ""
    preferred_titles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    title_token_overlap: float = Field(ge=0, le=1)
    skill_overlap: float = Field(ge=0, le=1)
    preferred_location_match: bool
    experience_range_match: bool | None = None
    salary_range_match: bool | None = None
    description_token_count: int = Field(ge=0)

    @model_validator(mode="after")
    def ranges_are_ordered(self) -> "PreparedJobSourceV2":
        pairs = (
            ("experience", self.experience_min_years, self.experience_max_years),
            ("salary", self.salary_min, self.salary_max),
        )
        for label, minimum, maximum in pairs:
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"{label} minimum cannot exceed maximum")
        return self


class ModelFeaturesV2(StrictModel):
    """The 58 inference-available inputs consumed before score stacking."""

    # Five base numeric features.
    experience_min_years: float | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_midpoint: float | None = None
    experience_profile_fit_imputed: float = Field(ge=0, le=1)

    # Five boolean features represented as numeric 0/1 for sklearn.
    has_skills_or_requirements: float = Field(ge=0, le=1)
    is_bengaluru: float = Field(ge=0, le=1)
    is_gurgaon_ncr: float = Field(ge=0, le=1)
    is_india: float = Field(ge=0, le=1)
    salary_available: float = Field(ge=0, le=1)

    # Twelve categorical features present in the evaluated frontier contract.
    can_apply_now: str
    freshness: str
    role_family_standard: str
    seniority_standard: str
    employment_type_standard: str
    work_mode_standard: str
    city_standard: str
    country_standard: str
    location_bucket: str
    experience_min_bucket: str
    skills_imputation_type: str
    experience_profile_fit_imputation_reason: str

    # Thirty-four engineered flags. They must be derived without manual labels.
    feat_is_experience_mismatch: float = Field(ge=0, le=1)
    feat_is_senior_or_above: float = Field(ge=0, le=1)
    feat_is_lead_staff_principal: float = Field(ge=0, le=1)
    feat_is_early_career: float = Field(ge=0, le=1)
    feat_is_intern_or_new_grad: float = Field(ge=0, le=1)
    feat_is_entry_or_junior: float = Field(ge=0, le=1)
    feat_is_mid_level: float = Field(ge=0, le=1)
    feat_is_backend_or_fullstack: float = Field(ge=0, le=1)
    feat_is_ml_ai: float = Field(ge=0, le=1)
    feat_is_data_role: float = Field(ge=0, le=1)
    feat_is_devops_cloud: float = Field(ge=0, le=1)
    feat_is_qa_testing: float = Field(ge=0, le=1)
    feat_is_support_or_annotation: float = Field(ge=0, le=1)
    feat_is_security_role: float = Field(ge=0, le=1)
    feat_is_platform_infra: float = Field(ge=0, le=1)
    feat_is_llm_or_rag_role: float = Field(ge=0, le=1)
    feat_is_remote: float = Field(ge=0, le=1)
    feat_is_remote_global: float = Field(ge=0, le=1)
    feat_is_india_remote: float = Field(ge=0, le=1)
    feat_is_india_target_location: float = Field(ge=0, le=1)
    feat_is_bengaluru_or_ncr: float = Field(ge=0, le=1)
    feat_is_tier1_city: float = Field(ge=0, le=1)
    feat_is_location_mismatch: float = Field(ge=0, le=1)
    feat_is_low_salary: float = Field(ge=0, le=1)
    feat_is_mid_salary: float = Field(ge=0, le=1)
    feat_is_high_salary: float = Field(ge=0, le=1)
    feat_salary_good_but_role_bad: float = Field(ge=0, le=1)
    feat_low_salary_but_good_role: float = Field(ge=0, le=1)
    feat_good_role_good_location: float = Field(ge=0, le=1)
    feat_good_title_bad_experience: float = Field(ge=0, le=1)
    feat_remote_early_career: float = Field(ge=0, le=1)
    feat_onsite_or_hybrid_early_career: float = Field(ge=0, le=1)
    feat_bad_fit_combo: float = Field(ge=0, le=1)
    feat_strong_fit_combo: float = Field(ge=0, le=1)

    # Two raw strings transformed by the fitted word/character TF-IDF pipelines.
    enhanced_title_skill_text: str
    enhanced_context_text: str


class PreparedJobV2(PreparedJobSourceV2):
    """Durable prepared row pinned to the exact production feature contract."""

    feature_schema_version: Literal["prepared-job-v2"] = "prepared-job-v2"
    feature_schema_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_features: ModelFeaturesV2
