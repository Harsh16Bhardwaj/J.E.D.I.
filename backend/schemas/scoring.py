from typing import Any

from pydantic import BaseModel, Field


class ScoreCandidate(BaseModel):
    canonical_job_id: str = Field(min_length=1)
    feature_snapshot: dict[str, Any]
    description: str


class ScoreRequest(BaseModel):
    batch_id: str = Field(min_length=1)
    profile_version_id: str = Field(min_length=1)
    candidates: list[ScoreCandidate] = Field(min_length=1, max_length=500)


class ScoreResult(BaseModel):
    canonical_job_id: str
    score: float
    rank: int
    reliability: str
    positive_reasons: list[str]
    negative_reasons: list[str]


class ScoreResponse(BaseModel):
    batch_id: str
    model_version: str
    results: list[ScoreResult]
