"""Audited reference-rate conversion used by scraper normalization."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

from backend.database import Job
from backend.services.product import annualized_salary_range

FX_POLICY_VERSION = "inr-fx-v1"
FX_PROVIDER = "Frankfurter/FBIL"
FX_TTL = timedelta(hours=12)
_RATE_CACHE: dict[str, tuple[datetime, "FxRate"]] = {}


@dataclass(frozen=True)
class FxRate:
    rate: Decimal
    as_of: date
    provider: str = FX_PROVIDER


async def fetch_inr_rate(currency: str) -> FxRate | None:
    code = currency.strip().upper()
    if code == "INR":
        return FxRate(rate=Decimal("1"), as_of=datetime.now(UTC).date())
    cached = _RATE_CACHE.get(code)
    if cached and datetime.now(UTC) - cached[0] < FX_TTL:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(
                f"https://api.frankfurter.dev/v2/rate/{code}/INR",
                params={"providers": "FBIL"},
                headers={"User-Agent": "JEDI-INR-Normalizer/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
        rate = Decimal(str(payload["rate"]))
        as_of = date.fromisoformat(str(payload["date"]))
        if rate <= 0 or datetime.now(UTC).date() - as_of > timedelta(days=7):
            return None
    except (httpx.HTTPError, KeyError, ValueError, InvalidOperation):
        return None
    result = FxRate(rate=rate, as_of=as_of)
    _RATE_CACHE[code] = (datetime.now(UTC), result)
    return result


async def normalize_job_salary_to_inr(job: Job) -> None:
    """Populate derived annual INR values without changing source compensation."""

    job.salary_inr_min = None
    job.salary_inr_max = None
    job.salary_fx_rate = None
    job.salary_fx_as_of = None
    job.salary_fx_provider = None
    if not job.salary_currency or (job.salary_min is None and job.salary_max is None):
        return
    annual_min, annual_max = annualized_salary_range(
        job.salary_min, job.salary_max, job.salary_period
    )
    rate = await fetch_inr_rate(job.salary_currency)
    if rate is None:
        return
    job.salary_inr_min = (
        Decimal(str(annual_min)) * rate.rate if annual_min is not None else None
    )
    job.salary_inr_max = (
        Decimal(str(annual_max)) * rate.rate if annual_max is not None else None
    )
    job.salary_fx_rate = rate.rate
    job.salary_fx_as_of = datetime.combine(rate.as_of, datetime.min.time(), tzinfo=UTC)
    job.salary_fx_provider = rate.provider
