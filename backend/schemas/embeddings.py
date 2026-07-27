from pydantic import BaseModel, Field


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=100)
    model_version: str | None = None


class EmbeddingVector(BaseModel):
    source_index: int
    values: list[float]


class EmbedResponse(BaseModel):
    model_version: str
    dimensions: int
    embeddings: list[EmbeddingVector]
