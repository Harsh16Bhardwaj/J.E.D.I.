from typing import Any

from pydantic import BaseModel, Field


class NormalizeRequest(BaseModel):
    schema_version: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    jobs: list[dict[str, Any]] = Field(min_length=1)


class NormalizedJob(BaseModel):
    source_index: int
    normalized: dict[str, Any]


class NormalizeResponse(BaseModel):
    schema_version: str
    jobs: list[NormalizedJob]
