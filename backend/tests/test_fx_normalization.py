import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

from backend.database import Job, ProfileVersion
from backend.services import fx
from backend.services.fx import FxRate, normalize_job_salary_to_inr
from backend.services.product import prepare_job


def job_with_usd_salary() -> Job:
    return Job(
        id="job-fx",
        code="JOB-FX",
        dedupe_key="fx-dedupe",
        company_key="example",
        batch_id="batch-fx",
        company_name="Example",
        role_title="Backend Engineer",
        role_family="backend",
        seniority="entry",
        location="Remote - India",
        work_mode="remote",
        employment_type="full-time",
        description="Build production Python APIs with tests and observability.",
        skills=["python", "fastapi"],
        experience_min_years=1,
        experience_max_years=3,
        salary_min=Decimal("1000"),
        salary_max=Decimal("2000"),
        salary_currency="USD",
        salary_period="MONTHLY",
        posted_at=datetime.now(UTC),
        can_apply_now=True,
        apply_url="https://jobs.example.test/backend",
    )


def test_scraper_normalization_preserves_source_and_prepares_annual_inr(
    monkeypatch,
) -> None:
    async def fake_rate(_currency: str) -> FxRate:
        return FxRate(rate=Decimal("90"), as_of=date(2026, 8, 11))

    monkeypatch.setattr(fx, "fetch_inr_rate", fake_rate)
    job = job_with_usd_salary()
    asyncio.run(normalize_job_salary_to_inr(job))
    assert job.salary_min == Decimal("1000")
    assert job.salary_currency == "USD"
    assert job.salary_inr_min == Decimal("1080000")
    assert job.salary_inr_max == Decimal("2160000")
    assert job.salary_fx_provider == "Frankfurter/FBIL"

    profile = ProfileVersion(
        id="profile-fx",
        content_hash="profile-hash",
        resume_text="Python backend engineer",
        preferred_titles=["Backend Engineer"],
        preferred_locations=["India"],
        preferred_skills=["python"],
        experience_min_years=1,
        experience_max_years=3,
        salary_min=Decimal("800000"),
        salary_max=Decimal("3000000"),
        salary_currency="INR",
    )
    prepared = prepare_job(job, profile, feature_reference_at=datetime.now(UTC))
    assert prepared.salary_currency == "INR"
    assert prepared.salary_min == 1_080_000
    assert prepared.model_features.salary_available == 1
    assert prepared.salary_range_match is True


def test_unavailable_rate_leaves_derived_salary_unknown(monkeypatch) -> None:
    async def no_rate(_currency: str):
        return None

    monkeypatch.setattr(fx, "fetch_inr_rate", no_rate)
    job = job_with_usd_salary()
    asyncio.run(normalize_job_salary_to_inr(job))
    assert job.salary_inr_min is None
    assert job.salary_inr_max is None
    assert job.salary_fx_provider is None
