"""Contracts for the compact operational dashboard feed."""

from datetime import datetime
from enum import StrEnum

from backend.schemas.product import ApiModel, SalaryPeriod


class LeaderboardPeriod(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    OVERALL = "overall"


class DashboardJob(ApiModel):
    id: str
    code: str
    company_name: str
    role_title: str
    seniority: str | None
    location: str | None
    work_mode: str | None
    employment_type: str | None
    description: str
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_period: SalaryPeriod | None
    posted_at: datetime | None
    apply_url: str
    batch_id: str
    batch_name: str
    batch_created_at: datetime
    review_status: str
    application_status: str
    rank: int | None
    jedi_preference_score: float | None
    ranking_score: float | None
    apply_preference_probability: float | None
    apply_recommendation: bool | None
    ranked_at: datetime | None


class DashboardFeed(ApiModel):
    today_jobs: list[DashboardJob]
    job_feed_scope: str
    leaderboard: list[DashboardJob]
    leaderboard_period: LeaderboardPeriod
    fresh: bool
    not_applied: bool
    generated_at: datetime
