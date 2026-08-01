"""Versioned HTTP and runtime contracts for JEDI model inference."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


class ScoreModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel,
        populate_by_name=True,
        extra="forbid",
    )


class ScoreRequest(ScoreModel):
    request_contract_version: Literal["score-request-v1"] = "score-request-v1"
    batch_id: str = Field(min_length=1)
    processing_run_id: str = Field(min_length=1)
    model_version_id: str = Field(min_length=1)


class ScoreTimings(ScoreModel):
    model_load: float = Field(ge=0)
    feature_build: float = Field(ge=0)
    preference_scoring: float = Field(ge=0)
    classification: float = Field(ge=0)
    validation: float = Field(ge=0)
    total: float = Field(ge=0)


class ScoreResult(ScoreModel):
    job_id: str
    rank: int = Field(ge=1)
    ranking_score: float = Field(ge=0, le=100)
    jedi_preference_score: float = Field(ge=0, le=100)
    apply_probability: float = Field(ge=0, le=1)
    model_apply_decision: bool
    apply_recommendation: bool
    component_scores: dict[str, float]
    warnings: list[str] = Field(default_factory=list)


class ScoreResponse(ScoreModel):
    response_contract_version: Literal["score-response-v1"] = "score-response-v1"
    batch_id: str
    processing_run_id: str
    model_version_id: str
    feature_schema_version: Literal["prepared-job-v2"] = "prepared-job-v2"
    artifact_hash: str
    decision_threshold: float = Field(ge=0, le=1)
    ranking_strategy: Literal["apply-gate-then-jedi-v1"] = "apply-gate-then-jedi-v1"
    cold_start: bool
    timings_ms: ScoreTimings
    results: list[ScoreResult] = Field(min_length=1, max_length=500)


class ModelRuntimeHealth(ScoreModel):
    state: Literal["UNINITIALIZED", "LOADING", "READY", "FAILED"]
    ready: bool
    model_version: str | None = None
    feature_schema_version: str | None = None
    request_contract_version: str | None = None
    response_contract_version: str | None = None
    artifact_hash: str | None = None
    cold_start: bool | None = None
    model_load_ms: float | None = None
    smoke_test_ms: float | None = None
    error_code: str | None = None


class ModelOperationResponse(ScoreModel):
    status: Literal["READY", "FAILED"]
    model_version_id: str | None = None
    deployment_id: str | None = None
    check_id: str | None = None
    runtime: ModelRuntimeHealth
    details: dict[str, Any] = Field(default_factory=dict)
