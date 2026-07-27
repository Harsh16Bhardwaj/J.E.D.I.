from typing import Literal

from pydantic import BaseModel


class ServiceMetadata(BaseModel):
    service: str
    version: str
    docs_url: str
    status: Literal["foundation"]


class HealthResponse(BaseModel):
    service: str
    status: Literal["ok", "ready"]


class ServiceInfoResponse(BaseModel):
    service: str
    api_version: str
    capabilities: list[str]


class NotImplementedResponse(BaseModel):
    status: Literal["not_implemented"] = "not_implemented"
    route: str
    message: str
