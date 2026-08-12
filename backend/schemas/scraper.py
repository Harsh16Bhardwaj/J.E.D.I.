"""HTTP contracts for the owner-only manual scraper workspace."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from backend.schemas.product import ApiModel, BatchCreateResponse


class ScraperConfigSummary(ApiModel):
    version: str
    lookback_days: int
    review_lookback_days: int
    target_job_count: int
    bright_data_limit: int
    ats_types: list[str]
    title_aliases: list[str]
    company_hint_count: int
    seeded_source_count: int
    bright_data_configured: bool
    unlocker_configured: bool
    concurrent_sources: int
    max_candidates_per_company: int
    minimum_description_characters: int


class ScrapeSourceCreateRequest(ApiModel):
    url: str = Field(min_length=8, max_length=2000)
    name: str | None = Field(default=None, max_length=200)


class ScrapeSourceResponse(ApiModel):
    id: str
    source_key: str
    name: str
    ats_type: str
    domain_hint: str
    board_token: str
    active: bool
    last_seen_at: datetime | None
    created_at: datetime
    health_status: str
    last_success_at: datetime | None
    last_failure_at: datetime | None
    consecutive_failures: int
    consecutive_zero_yield: int
    response_time_ms: int | None
    jobs_scanned: int
    eligible_yield: int
    duplicate_yield: int
    cooldown_until: datetime | None


class ScrapeSourceUpdateRequest(ApiModel):
    active: bool


class ScrapeAttemptResponse(ApiModel):
    id: str
    step_key: str
    source_key: str
    provider: str
    status: str
    attempt_count: int
    discovered_count: int
    valid_count: int
    bright_data_used: int
    error_message: str | None
    checkpoint: dict | None
    response_time_ms: int | None
    free_request_count: int


class ScrapeCandidateResponse(ApiModel):
    id: str
    source_key: str
    source_provider: str
    ats_type: str
    source_url: str
    company_name: str
    role_title: str
    location: str | None
    experience_min_years: float | None
    experience_max_years: float | None
    posted_at: datetime | None
    geography_eligibility: str
    source_quality_valid: bool
    quality_failures: list[str]
    description_length: int
    date_evidence: str | None
    schema_valid: bool
    selected: bool
    validation_errors: list | None
    freshness_tier: str
    quality_score: float
    review_group: str
    extracted_facts: dict | None
    extraction_version: str | None


class ScrapeCandidateDetail(ScrapeCandidateResponse):
    payload: dict
    evidence_spans: list[dict]


class ScrapeAttemptPage(ApiModel):
    items: list[ScrapeAttemptResponse]
    page: int
    page_size: int
    total: int


class ScrapeCandidatePage(ApiModel):
    items: list[ScrapeCandidateResponse]
    page: int
    page_size: int
    total: int


class ScrapeRunSummary(ApiModel):
    id: str
    status: str
    config_version: str
    target_job_count: int
    bright_data_limit: int
    bright_data_used: int
    free_request_count: int
    bright_data_fallback_count: int
    provider_usage_reason: str
    normalization_status: str | None
    discovered_count: int
    valid_count: int
    selected_count: int
    failed_source_count: int
    source_count: int
    processed_source_count: int
    stopped_early: bool
    imported_batch_id: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ScrapeRunDetail(ScrapeRunSummary):
    attempts: list[ScrapeAttemptResponse]
    candidates: list[ScrapeCandidateResponse]


class ScrapeRunStats(ApiModel):
    by_ats: dict[str, dict[str, int]]
    by_rejection_reason: dict[str, int]


class SourceDiscoveryAttemptResponse(ApiModel):
    id: str
    company_name: str
    company_domain: str
    status: str
    attempt_count: int
    detected_count: int
    activated_count: int
    response_time_ms: int | None
    error_message: str | None


class SourceDiscoveryRunResponse(ApiModel):
    id: str
    status: str
    total_hints: int
    processed_hints: int
    detected_sources: int
    activated_sources: int
    failed_hints: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class SourceDiscoveryRunDetail(SourceDiscoveryRunResponse):
    attempts: list[SourceDiscoveryAttemptResponse]


class ScrapeRunPage(ApiModel):
    items: list[ScrapeRunSummary]
    page: int
    page_size: int
    total: int


class ScrapeSelectionRequest(ApiModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=500)
    selected: bool


class ScrapeBulkSelectionRequest(ApiModel):
    selected: bool
    review_group: Literal["RECOMMENDED", "NEEDS_REVIEW"] | None = None


class ScrapeImportRequest(ApiModel):
    confirm_partial: bool = False


class ScrapeImportResponse(ApiModel):
    run: ScrapeRunSummary
    batch: BatchCreateResponse
    normalization: dict | None = None
