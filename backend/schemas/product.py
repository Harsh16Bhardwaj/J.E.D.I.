"""HTTP contracts for the private JEDI product API."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )


class LoginRequest(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(ApiModel):
    id: str
    email: str


class IncomingJob(ApiModel):
    company_name: str = Field(min_length=1, max_length=300)
    role_title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1)
    apply_url: str = Field(min_length=1, max_length=4000)
    role_family: str | None = Field(default=None, max_length=200)
    seniority: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=500)
    work_mode: str | None = Field(default=None, max_length=100)
    employment_type: str | None = Field(default=None, max_length=100)
    skills: list[str] = Field(default_factory=list)
    experience_min_years: float | None = Field(default=None, ge=0, le=80)
    experience_max_years: float | None = Field(default=None, ge=0, le=80)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=10)
    posted_at: datetime | None = None
    application_deadline: datetime | None = None
    can_apply_now: bool | None = None

    @field_validator("skills", mode="before")
    @classmethod
    def split_skills(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def ranges_are_ordered(self) -> "IncomingJob":
        for low_name, high_name in (
            ("experience_min_years", "experience_max_years"),
            ("salary_min", "salary_max"),
        ):
            low = getattr(self, low_name)
            high = getattr(self, high_name)
            if low is not None and high is not None and low > high:
                raise ValueError(f"{low_name} cannot exceed {high_name}")
        return self


class ImportEnvelope(ApiModel):
    external_batch_id: str = Field(min_length=1, max_length=300)
    schema_version: str = Field(min_length=1, max_length=100)
    prompt_version: str | None = Field(default=None, max_length=100)
    generated_at: datetime
    jobs: list[dict[str, Any]] = Field(min_length=1)


class ValidationIssue(ApiModel):
    source_index: int
    errors: list[dict[str, Any]]


class BatchCreateResponse(ApiModel):
    batch_id: str
    status: str
    received_count: int
    valid_count: int
    duplicate_count: int
    job_count: int
    replayed: bool
    validation_report: list[ValidationIssue]


class BatchSummary(ApiModel):
    id: str
    display_name: str | None
    external_batch_id: str
    schema_version: str
    prompt_version: str | None
    generated_at: datetime
    status: str
    received_count: int
    valid_count: int
    duplicate_count: int
    job_count: int
    created_at: datetime
    ranked_at: datetime | None


class BatchPage(ApiModel):
    items: list[BatchSummary]
    page: int
    page_size: int
    total: int


class ActionAvailability(ApiModel):
    can_delete: bool
    can_normalize: bool
    can_annotate: bool
    can_add_to_training: bool
    can_process_ranks: bool


class AnnotationResponse(ApiModel):
    job_id: str
    relevance_label: str | None
    apply_label: bool | None
    complete: bool


class JobResponse(ApiModel):
    id: str
    code: str
    company_name: str
    role_title: str
    role_family: str | None
    seniority: str | None
    location: str | None
    work_mode: str | None
    employment_type: str | None
    description: str
    skills: list[str]
    experience_min_years: float | None
    experience_max_years: float | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    posted_at: datetime | None
    application_deadline: datetime | None
    can_apply_now: bool | None
    apply_url: str
    annotation: AnnotationResponse | None


class BatchDetail(ApiModel):
    batch: BatchSummary
    actions: ActionAvailability
    prepared_count: int
    normalization_complete: bool
    manual_annotation_count: int
    jobs: list[JobResponse]


class RelevanceLabel(StrEnum):
    DREAM = "DREAM"
    STRONG_APPLY = "STRONG_APPLY"
    CONSIDER = "CONSIDER"
    REJECT = "REJECT"


class AnnotationInput(ApiModel):
    job_id: str | None = None
    relevance_label: RelevanceLabel | None = None
    apply_label: bool | None = None
    role_title_fit: float | None = Field(default=None, ge=0, le=5)
    role_family_fit: float | None = Field(default=None, ge=0, le=5)
    seniority_fit: float | None = Field(default=None, ge=0, le=5)
    location_fit: float | None = Field(default=None, ge=0, le=5)
    work_mode_fit: float | None = Field(default=None, ge=0, le=5)
    experience_fit: float | None = Field(default=None, ge=0, le=5)
    skills_fit: float | None = Field(default=None, ge=0, le=5)
    salary_fit: float | None = Field(default=None, ge=0, le=8)
    overall_preference: float | None = Field(default=None, ge=0, le=5)

    @model_validator(mode="after")
    def contains_annotation_update(self) -> "AnnotationInput":
        if not self.model_fields_set - {"job_id"}:
            raise ValueError("At least one annotation field is required")
        return self


class BatchAnnotationsRequest(ApiModel):
    annotations: list[AnnotationInput] = Field(min_length=1)

    @model_validator(mode="after")
    def job_ids_are_present(self) -> "BatchAnnotationsRequest":
        if any(item.job_id is None for item in self.annotations):
            raise ValueError("Every batch annotation requires jobId")
        job_ids = [item.job_id for item in self.annotations]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("A jobId may appear only once per batch annotation")
        return self


class TrainingSelection(StrEnum):
    ALL_ANNOTATED = "ALL_ANNOTATED"
    YES_ONLY = "YES_ONLY"
    NO_ONLY = "NO_ONLY"


class TrainingExamplesRequest(ApiModel):
    selection: TrainingSelection


class RankingItem(ApiModel):
    job_id: str
    rank: int = Field(ge=1)
    jedi_preference_score: float = Field(ge=0, le=100)
    apply_preference_probability: float = Field(ge=0, le=1)
    component_scores: dict[str, float] | None = None
    ranking_score: float | None = Field(default=None, ge=0, le=100)
    ranking_strategy: str = "apply-gate-then-jedi-v1"
    apply_threshold: float | None = Field(default=None, ge=0, le=1)
    model_apply_decision: bool | None = None
    apply_recommendation: bool | None = None
    output_schema_version: str = "score-response-v1"


class RankingsRequest(ApiModel):
    profile_version_id: str
    model_version_id: str
    rankings: list[RankingItem] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def ranks_are_unique(self) -> "RankingsRequest":
        ranks = [item.rank for item in self.rankings]
        jobs = [item.job_id for item in self.rankings]
        if len(ranks) != len(set(ranks)):
            raise ValueError("rank values must be unique")
        if len(jobs) != len(set(jobs)):
            raise ValueError("jobId values must be unique")
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise ValueError("rank values must be contiguous starting at 1")
        return self


class BatchNormalizationResponse(ApiModel):
    batch_id: str
    status: str
    prepared_count: int
    profile_version_id: str | None = None
    feature_schema_version: str | None = None
    replayed: bool


class TrainingExamplesResponse(ApiModel):
    batch_id: str
    selection: TrainingSelection
    added_or_updated_count: int


class CsvTrainingImportResponse(ApiModel):
    batch_id: str
    received_count: int
    imported_count: int
    duplicate_count: int
    invalid_count: int
    training_example_count: int
    feature_schema_version: str
    replayed: bool
    validation_report: list[dict[str, Any]]


class AnnotationEditorRow(ApiModel):
    job_id: str
    code: str
    company_name: str
    role_title: str
    role_family: str | None
    seniority: str | None
    location: str | None
    work_mode: str | None
    employment_type: str | None
    apply_url: str
    relevance_label: str | None
    apply_label: bool | None
    role_title_fit: float | None
    role_family_fit: float | None
    seniority_fit: float | None
    location_fit: float | None
    work_mode_fit: float | None
    experience_fit: float | None
    skills_fit: float | None
    salary_fit: float | None
    overall_preference: float | None
    complete: bool
    prepared: bool
    in_training: bool


class AnnotationEditorResponse(ApiModel):
    batch: BatchSummary
    rows: list[AnnotationEditorRow]
    complete_count: int
    prepared_count: int
    training_count: int


class RankingQueueResponse(ApiModel):
    batch_id: str
    status: str
    processing_run_id: str
    pending_execution: bool


class EmailDeliverySummary(ApiModel):
    id: str
    ranking_run_id: str
    status: str
    attempts: int
    error_code: str | None
    last_error: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EmailDigestResponse(ApiModel):
    batch_id: str
    delivery: EmailDeliverySummary | None


class EmailCronResponse(ApiModel):
    status: str
    delivery: EmailDeliverySummary | None


class RankingSaveResponse(ApiModel):
    batch_id: str
    status: str
    ranking_count: int
    email_delivery: EmailDeliverySummary | None = None


class RankingResponse(RankingItem):
    profile_version_id: str
    model_version_id: str
    processing_run_id: str


class ProcessingRunResponse(ApiModel):
    id: str
    stage: str
    status: str
    effective_status: str
    phase: str
    attempt: int
    retryable: bool | None
    trigger: str
    retry_of_run_id: str | None
    profile_version_id: str | None
    model_version_id: str | None
    model_name: str | None
    feature_schema_version: str | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    heartbeat_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    invocation: "ModelInvocationResponse | None" = None


class ModelInvocationResponse(ApiModel):
    id: str
    attempt: int
    status: str
    artifact_hash: str
    input_count: int
    output_count: int
    cold_start: bool | None
    timings_ms: dict[str, Any] | None
    error_code: str | None
    raw_response: dict[str, Any] | None
    started_at: datetime
    completed_at: datetime | None


class RankingExecutionResponse(ApiModel):
    batch_id: str
    status: str
    processing_run_id: str
    ranking_count: int
    cold_start: bool
    timings_ms: dict[str, float]


class RankingRetryResponse(RankingQueueResponse):
    retry_of_run_id: str


class WorkerPreparedJob(ApiModel):
    job_id: str
    payload: dict[str, Any]


class WorkerClaimResponse(ApiModel):
    run_id: str
    batch_id: str
    profile_version_id: str
    model_version_id: str
    feature_schema_version: str
    lease_token: str
    lease_expires_at: datetime
    jobs: list[WorkerPreparedJob]


class WorkerHeartbeatResponse(ApiModel):
    run_id: str
    lease_expires_at: datetime


class WorkerFailureRequest(ApiModel):
    error_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    error_message: str = Field(min_length=1, max_length=500)


class WorkerFailureResponse(ApiModel):
    run_id: str
    status: str
    batch_status: str


class PreparedJobV1(ApiModel):
    feature_schema_version: str = "prepared-job-v1"
    job_id: str
    code: str
    company_name: str
    company_key: str
    role_title: str
    role_family: str
    seniority: str
    location: str
    work_mode: str
    employment_type: str
    description: str
    skills: list[str]
    experience_min_years: float | None
    experience_max_years: float | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str
    can_apply_now: bool | None
    resume_text: str
    preferred_titles: list[str]
    preferred_locations: list[str]
    preferred_skills: list[str]
    title_token_overlap: float
    skill_overlap: float
    preferred_location_match: bool
    experience_range_match: bool | None
    salary_range_match: bool | None
    description_token_count: int


class NormalizeRequest(ApiModel):
    job: dict[str, Any]
    profile: dict[str, Any]


class ReviewStatus(StrEnum):
    NEW = "NEW"
    VIEWED = "VIEWED"
    SAVED = "SAVED"
    DISMISSED = "DISMISSED"


class ApplicationStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PREPARING = "PREPARING"
    APPLIED = "APPLIED"
    SCREENING = "SCREENING"
    ASSESSMENT = "ASSESSMENT"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class ApplicationMilestoneType(StrEnum):
    SCREENING = "SCREENING"
    ASSESSMENT = "ASSESSMENT"
    INTERVIEW = "INTERVIEW"
    FOLLOW_UP = "FOLLOW_UP"
    OTHER = "OTHER"


class ApplicationMilestoneStatus(StrEnum):
    PLANNED = "PLANNED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class JobSort(StrEnum):
    RECENT = "recent"
    SCORE = "score"


class AnnotationFilter(StrEnum):
    ALL = "all"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class ApplicationDueFilter(StrEnum):
    ALL = "all"
    OVERDUE = "overdue"
    TODAY = "today"
    WEEK = "week"
    NONE = "none"


class ApplicationSort(StrEnum):
    UPDATED = "updated"
    NEXT_ACTION = "nextAction"


class ProfileCreate(ApiModel):
    resume_text: str = Field(min_length=1)
    preferred_titles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_min_years: float | None = Field(default=None, ge=0, le=80)
    experience_max_years: float | None = Field(default=None, ge=0, le=80)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=10)

    @field_validator("resume_text")
    @classmethod
    def resume_is_not_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("resumeText cannot contain only whitespace")
        return value

    @model_validator(mode="after")
    def profile_ranges_are_ordered(self) -> "ProfileCreate":
        for low_name, high_name in (
            ("experience_min_years", "experience_max_years"),
            ("salary_min", "salary_max"),
        ):
            low = getattr(self, low_name)
            high = getattr(self, high_name)
            if low is not None and high is not None and low > high:
                raise ValueError(f"{low_name} cannot exceed {high_name}")
        return self


class ProfileSummary(ApiModel):
    id: str
    active: bool
    resume_preview: str
    preferred_titles: list[str]
    preferred_locations: list[str]
    preferred_skills: list[str]
    created_at: datetime


class ProfileDetail(ProfileSummary):
    content_hash: str
    resume_text: str
    experience_min_years: float | None
    experience_max_years: float | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None


class ProfileWriteResponse(ProfileDetail):
    replayed: bool


class ModelCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    artifact_manifest: dict[str, Any]
    feature_schema_version: str = Field(min_length=1, max_length=100)
    metrics: dict[str, Any] | None = None


class ModelSummary(ApiModel):
    id: str
    name: str
    content_hash: str
    feature_schema_version: str
    active: bool
    created_at: datetime


class ModelDetail(ModelSummary):
    artifact_manifest: dict[str, Any]
    metrics: dict[str, Any] | None


class ModelWriteResponse(ModelDetail):
    replayed: bool


class JobStatePatch(ApiModel):
    relevance_label: RelevanceLabel | None = None
    review_status: ReviewStatus | None = None
    notes: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def contains_update(self) -> "JobStatePatch":
        if not self.model_fields_set:
            raise ValueError("At least one state field is required")
        if "review_status" in self.model_fields_set and self.review_status is None:
            raise ValueError("reviewStatus cannot be null")
        return self


class JobStateResponse(ApiModel):
    job_id: str
    relevance_label: str | None
    review_status: str
    application_status: str
    viewed_at: datetime | None
    notes: str | None
    updated_at: datetime


class LatestPrediction(ApiModel):
    rank: int
    jedi_preference_score: float
    apply_preference_probability: float
    ranking_score: float
    ranking_strategy: str
    apply_recommendation: bool | None
    processing_run_id: str
    ranked_at: datetime


class JobListItem(ApiModel):
    id: str
    code: str
    company_name: str
    role_title: str
    location: str | None
    work_mode: str | None
    created_at: datetime
    relevance_label: str | None
    review_status: str
    application_status: str
    annotation_complete: bool
    latest_prediction: LatestPrediction | None = None


class JobPage(ApiModel):
    items: list[JobListItem]
    page: int
    page_size: int
    total: int


class JobAnnotationDetail(ApiModel):
    apply_label: bool | None
    role_title_fit: float | None
    role_family_fit: float | None
    seniority_fit: float | None
    location_fit: float | None
    work_mode_fit: float | None
    experience_fit: float | None
    skills_fit: float | None
    salary_fit: float | None
    overall_preference: float | None
    complete: bool


class PredictionSummary(ApiModel):
    id: str
    rank: int
    jedi_preference_score: float
    apply_preference_probability: float
    component_scores: dict[str, Any] | None
    ranking_score: float
    ranking_strategy: str
    apply_threshold: float | None
    model_apply_decision: bool | None
    apply_recommendation: bool | None
    output_schema_version: str
    profile_version_id: str
    model_version_id: str
    processing_run_id: str
    created_at: datetime


class JobEventResponse(ApiModel):
    id: str
    job_id: str
    event_type: str
    previous_status: str | None
    new_status: str | None
    notes: str | None
    event_at: datetime
    created_at: datetime


class JobDetail(ApiModel):
    job: JobResponse
    batch: BatchSummary
    state: JobStateResponse | None
    annotation: JobAnnotationDetail | None
    application: "ApplicationResponse"
    milestones: list["ApplicationMilestoneResponse"]
    predictions: list[PredictionSummary]
    events: list[JobEventResponse]


class ApplicationEventCreate(ApiModel):
    application_status: ApplicationStatus
    event_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=10_000)


class ApplicationPatch(ApiModel):
    applied_at: datetime | None = None
    target_apply_by: datetime | None = None
    next_action: str | None = Field(default=None, max_length=500)
    next_action_due_at: datetime | None = None
    portal_url: str | None = Field(default=None, max_length=4000)
    reference_code: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=10_000)
    expected_updated_at: datetime | None = None

    @field_validator("portal_url")
    @classmethod
    def portal_is_http(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return value
        from urllib.parse import urlsplit

        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("portalUrl must be an HTTP or HTTPS URL")
        return value

    @model_validator(mode="after")
    def contains_planning_update(self) -> "ApplicationPatch":
        changed = self.model_fields_set - {"expected_updated_at"}
        if not changed:
            raise ValueError("At least one application field is required")
        return self


class ApplicationResponse(ApiModel):
    job_id: str
    status: str
    applied_at: datetime | None
    target_apply_by: datetime | None
    next_action: str | None
    next_action_due_at: datetime | None
    portal_url: str | None
    reference_code: str | None
    notes: str | None
    closed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class ApplicationMilestoneCreate(ApiModel):
    type: ApplicationMilestoneType
    title: str = Field(min_length=1, max_length=300)
    scheduled_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=10_000)

    @field_validator("title")
    @classmethod
    def title_is_not_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title cannot contain only whitespace")
        return value


class ApplicationMilestonePatch(ApiModel):
    type: ApplicationMilestoneType | None = None
    title: str | None = Field(default=None, max_length=300)
    status: ApplicationMilestoneStatus | None = None
    scheduled_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def contains_update(self) -> "ApplicationMilestonePatch":
        if not self.model_fields_set:
            raise ValueError("At least one milestone field is required")
        if "title" in self.model_fields_set and (
            self.title is None or not self.title.strip()
        ):
            raise ValueError("title cannot be empty")
        if "type" in self.model_fields_set and self.type is None:
            raise ValueError("type cannot be null")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        return self


class ApplicationMilestoneResponse(ApiModel):
    id: str
    job_id: str
    type: str
    title: str
    status: str
    scheduled_at: datetime | None
    completed_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ApplicationListItem(ApiModel):
    job: JobListItem
    notes: str | None
    application: ApplicationResponse
    latest_event: JobEventResponse | None


class ApplicationPage(ApiModel):
    items: list[ApplicationListItem]
    page: int
    page_size: int
    total: int
    status_counts: dict[str, int]
    overdue_count: int


class ApplicationActionItem(ApiModel):
    job_id: str
    company_name: str
    role_title: str
    application_status: str
    next_action: str
    next_action_due_at: datetime
    application_updated_at: datetime


class ApplicationSummary(ApiModel):
    status_counts: dict[str, int]
    overdue_count: int
    due_today_count: int
    nearest_actions: list[ApplicationActionItem]


class BatchMetricBucket(ApiModel):
    label: str
    count: int


class BatchMetricsResponse(ApiModel):
    batch_id: str
    job_count: int
    ranked_count: int
    average_score: float | None
    top_25_average_score: float | None
    average_apply_probability: float | None
    recommended_count: int
    applied_count: int
    application_rate: float
    viewed_count: int
    bookmarked_count: int
    score_buckets: list[BatchMetricBucket]
    component_averages: dict[str, float]
