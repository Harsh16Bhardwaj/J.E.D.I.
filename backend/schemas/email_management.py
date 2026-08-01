"""Contracts for owner-managed newsletter settings and recipients."""

import re
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from backend.schemas.product import ApiModel

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    """Return the canonical address used for uniqueness comparisons."""
    normalized = value.strip().casefold()
    if len(normalized) > 320 or not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Enter a valid email address")
    return normalized


class EmailSettingsUpdate(ApiModel):
    enabled: bool | None = None
    sender_name: str | None = Field(default=None, min_length=1, max_length=100)
    send_after_ranking: bool | None = None

    @field_validator("sender_name")
    @classmethod
    def clean_sender_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def contains_update(self) -> "EmailSettingsUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one email setting is required")
        if "sender_name" in self.model_fields_set and self.sender_name is None:
            raise ValueError("senderName cannot be null")
        if "enabled" in self.model_fields_set and self.enabled is None:
            raise ValueError("enabled cannot be null")
        if (
            "send_after_ranking" in self.model_fields_set
            and self.send_after_ranking is None
        ):
            raise ValueError("sendAfterRanking cannot be null")
        return self


class EmailSettingsResponse(ApiModel):
    enabled: bool
    sender_name: str
    send_after_ranking: bool
    timezone: str = "Asia/Kolkata"
    scheduled_time: str = "00:00"
    transport_configured: bool
    active_recipient_count: int
    recipient_limit: int = 50


class ManualEmailDispatchResponse(ApiModel):
    status: Literal["processed", "empty", "not_ready"]
    ready: bool
    message: str
    claimed: int = 0
    sent: int = 0
    failed: int = 0
    remaining: int = 0


class MailEventEnqueueResponse(ApiModel):
    batch_id: str
    ranking_run_id: str
    created_count: int
    existing_count: int
    eligible_recipient_count: int
    skipped_recipient_count: int


class EmailRecipientCreate(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str | None = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalize_email(value)
        return value.strip()

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class EmailRecipientUpdate(ApiModel):
    email: str | None = Field(default=None, min_length=3, max_length=320)
    display_name: str | None = Field(default=None, max_length=100)
    active: bool | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None:
            normalize_email(value)
            return value.strip()
        return None

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def contains_update(self) -> "EmailRecipientUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one recipient field is required")
        if "email" in self.model_fields_set and self.email is None:
            raise ValueError("email cannot be null")
        if "active" in self.model_fields_set and self.active is None:
            raise ValueError("active cannot be null")
        return self


class EmailRecipientResponse(ApiModel):
    id: str
    email: str
    display_name: str | None
    group_member_id: str | None
    active: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EmailRecipientWriteResponse(EmailRecipientResponse):
    replayed: bool
    reactivated: bool
