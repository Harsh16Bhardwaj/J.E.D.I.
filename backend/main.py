from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

if __package__:
    from backend.config import get_settings
    from backend.routers import embeddings, health, normalization, scoring
else:
    from config import get_settings
    from routers import embeddings, health, normalization, scoring

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Foundation API contracts for JEDI normalization and ranking.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-JEDI-TIMESTAMP",
        "X-JEDI-SIGNATURE",
    ],
)

app.include_router(health.router)
app.include_router(normalization.router)
app.include_router(embeddings.router)
app.include_router(scoring.router)
