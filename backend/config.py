from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed service configuration."""

    app_name: str = "JEDI ML Service"
    app_version: str = "0.2.0"
    app_env: Literal["development", "test", "production"] = "development"
    cors_origins: str = "http://localhost:3000"
    database_url: str = "postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require"
    direct_database_url: str | None = None
    session_secret: str = "replace-with-at-least-32-random-characters"
    owner_registration_code: str = ""
    ml_service_secret: str = "replace-with-a-different-32-character-secret"
    session_cookie_name: str = "jedi_session"
    session_days: int = 7
    session_cookie_secure: bool = False
    email_enabled: bool = False
    gmail_smtp_user: str = ""
    gmail_smtp_app_password: str = ""
    digest_to_email: str = ""
    email_from_name: str = "JEDI Job Digest"
    cron_secret: str = ""
    model_bundle_root: str = "model_bundles"
    model_load_timeout_seconds: int = 30
    model_execution_timeout_seconds: int = 240
    model_max_batch_size: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        """Refuse production startup with placeholders or transport downgrades."""
        if self.app_env != "production":
            return self

        unsafe_fragments = {"replace", "password", "user", "host", "example"}
        database_value = self.database_url.casefold()
        if any(fragment in database_value for fragment in unsafe_fragments):
            raise ValueError("DATABASE_URL contains a placeholder value.")
        if urlparse(self.database_url).scheme not in {"postgresql", "postgres"}:
            raise ValueError("DATABASE_URL must be PostgreSQL in production.")
        for name, value in (
            ("SESSION_SECRET", self.session_secret),
            ("ML_SERVICE_SECRET", self.ml_service_secret),
        ):
            if len(value) < 32 or any(
                fragment in value.casefold() for fragment in unsafe_fragments
            ):
                raise ValueError(
                    f"{name} must be a non-placeholder 32+ character secret."
                )
        if self.owner_registration_code and (
            len(self.owner_registration_code) < 12
            or not self.owner_registration_code.isalnum()
        ):
            raise ValueError(
                "OWNER_REGISTRATION_CODE must contain 12+ letters and numbers."
            )
        if not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true in production.")
        if not self.allowed_origins or any(
            not origin.startswith("https://") for origin in self.allowed_origins
        ):
            raise ValueError("Production CORS origins must use HTTPS.")
        smtp_values = (self.gmail_smtp_user, self.gmail_smtp_app_password)
        if any(smtp_values) and not all(smtp_values):
            raise ValueError("Gmail SMTP user and app password must be set together.")
        if all(smtp_values):
            if len(self.cron_secret) < 32:
                raise ValueError("CRON_SECRET must be at least 32 characters.")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def sqlalchemy_database_url(self) -> str:
        """Use psycopg's async SQLAlchemy dialect for PostgreSQL URLs."""
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
