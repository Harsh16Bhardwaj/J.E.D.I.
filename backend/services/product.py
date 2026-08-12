"""Deterministic cleanup, deduplication, and model-row transformations."""

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from backend.database import Job, ProfileVersion
from backend.schemas.modeling import PreparedJobSourceV2, PreparedJobV2
from backend.schemas.product import IncomingJob, PreparedJobV1
from backend.services.model_features import build_prepared_job_v2

LEGAL_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "llc",
    "ltd",
    "limited",
    "pvt",
    "private",
    "plc",
}
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "ref",
    "referrer",
    "source",
}
WORK_MODES = {
    "work from home": "remote",
    "wfh": "remote",
    "remote": "remote",
    "hybrid": "hybrid",
    "in office": "onsite",
    "in-office": "onsite",
    "on site": "onsite",
    "onsite": "onsite",
}
EMPLOYMENT_TYPES = {
    "full time": "full-time",
    "full-time": "full-time",
    "permanent": "full-time",
    "intern": "internship",
    "internship": "internship",
    "contract": "contract",
    "contractor": "contract",
    "part time": "part-time",
    "part-time": "part-time",
}


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def comparison_text(value: str | None) -> str:
    value = clean_text(value).casefold()
    return re.sub(r"[^\w+#.]+", " ", value).strip()


def company_key(value: str) -> str:
    tokens = comparison_text(value).split()
    while tokens and tokens[-1].rstrip(".") in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def canonical_url(value: str) -> str:
    raw = clean_text(value)
    parts = urlsplit(raw)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise ValueError("applyUrl must be an absolute HTTP or HTTPS URL")
    host = parts.netloc.casefold()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+", "/", parts.path).rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_")
            and key.casefold() not in TRACKING_QUERY_KEYS
        )
    )
    return urlunsplit((parts.scheme.casefold(), host, path, query, ""))


def normalize_choice(value: str | None, vocabulary: dict[str, str]) -> str | None:
    cleaned = comparison_text(value)
    if not cleaned:
        return None
    return vocabulary.get(cleaned, cleaned)


def tokens(value: str | None) -> set[str]:
    return {token for token in comparison_text(value).split() if len(token) > 1}


def dice(left: str | None, right: str | None) -> float:
    left_tokens, right_tokens = tokens(left), tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return (2 * len(left_tokens & right_tokens)) / (
        len(left_tokens) + len(right_tokens)
    )


def ranges_overlap(
    left_min: float | Decimal | None,
    left_max: float | Decimal | None,
    right_min: float | Decimal | None,
    right_max: float | Decimal | None,
) -> bool:
    if left_min is None and left_max is None:
        return False
    if right_min is None and right_max is None:
        return False
    left_low = float(left_min if left_min is not None else left_max)
    left_high = float(left_max if left_max is not None else left_min)
    right_low = float(right_min if right_min is not None else right_max)
    right_high = float(right_max if right_max is not None else right_min)
    return max(left_low, right_low) <= min(left_high, right_high)


def annualized_salary(
    value: float | Decimal | None,
    period: str | None,
) -> float | Decimal | None:
    if value is None:
        return None
    return value * 12 if period == "MONTHLY" else value


def annualized_salary_range(
    minimum: float | Decimal | None,
    maximum: float | Decimal | None,
    period: str | None,
) -> tuple[float | Decimal | None, float | Decimal | None]:
    return annualized_salary(minimum, period), annualized_salary(maximum, period)


def clean_job(job: IncomingJob) -> dict[str, Any]:
    apply_url = canonical_url(job.apply_url)
    cleaned = {
        "company_name": clean_text(job.company_name),
        "company_key": company_key(job.company_name),
        "role_title": clean_text(job.role_title),
        "role_family": clean_text(job.role_family) or None,
        "seniority": comparison_text(job.seniority) or None,
        "location": clean_text(job.location) or None,
        "work_mode": normalize_choice(job.work_mode, WORK_MODES),
        "employment_type": normalize_choice(job.employment_type, EMPLOYMENT_TYPES),
        "description": clean_text(job.description),
        "skills": sorted(
            {comparison_text(skill) for skill in job.skills if comparison_text(skill)}
        ),
        "experience_min_years": job.experience_min_years,
        "experience_max_years": job.experience_max_years,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": (
            comparison_text(job.salary_currency).upper()
            if job.salary_currency
            else None
        ),
        "salary_period": job.salary_period.value if job.salary_period else None,
        "posted_at": job.posted_at,
        "application_deadline": job.application_deadline,
        "can_apply_now": job.can_apply_now,
        "apply_url": apply_url,
    }
    if not cleaned["company_key"]:
        raise ValueError("companyName has no usable comparison tokens")
    key_material = "|".join(
        [
            cleaned["company_key"],
            comparison_text(cleaned["role_title"]),
            comparison_text(cleaned["location"]),
            comparison_text(cleaned["employment_type"]),
            " ".join(sorted(tokens(cleaned["description"]))),
        ]
    )
    cleaned["dedupe_key"] = hashlib.sha256(key_material.encode()).hexdigest()
    cleaned["code"] = make_code(
        cleaned["company_name"], cleaned["role_title"], cleaned["dedupe_key"]
    )
    return cleaned


def make_code(company: str, role: str, dedupe_key: str) -> str:
    def slug(value: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")[:24]

    return f"{slug(company)}-{slug(role)}-{dedupe_key[:8].upper()}"


def duplicate_signals(incoming: dict[str, Any], candidate: Any) -> dict[str, bool]:
    incoming_salary = annualized_salary_range(
        incoming["salary_min"], incoming["salary_max"], incoming["salary_period"]
    )
    candidate_salary = annualized_salary_range(
        candidate.salary_min,
        candidate.salary_max,
        getattr(candidate, "salary_period", None),
    )
    salary_compatible = (
        incoming["salary_currency"] is not None
        and candidate.salary_currency is not None
        and incoming["salary_currency"].casefold()
        == candidate.salary_currency.casefold()
        and ranges_overlap(
            *incoming_salary,
            *candidate_salary,
        )
    )
    incoming_location = comparison_text(incoming["location"])
    candidate_location = comparison_text(candidate.location)
    return {
        "role": dice(incoming["role_title"], candidate.role_title) >= 0.72,
        "location": bool(incoming_location)
        and bool(candidate_location)
        and (
            incoming_location == candidate_location
            or incoming["work_mode"] == candidate.work_mode == "remote"
        ),
        "work_mode": bool(incoming["work_mode"])
        and incoming["work_mode"] == candidate.work_mode,
        "employment_type": bool(incoming["employment_type"])
        and incoming["employment_type"] == candidate.employment_type,
        "experience": ranges_overlap(
            incoming["experience_min_years"],
            incoming["experience_max_years"],
            candidate.experience_min_years,
            candidate.experience_max_years,
        ),
        "salary": salary_compatible,
        "description": dice(incoming["description"], candidate.description) >= 0.72,
    }


def is_duplicate(incoming: dict[str, Any], candidate: Any) -> bool:
    if incoming["company_key"] != candidate.company_key:
        return False
    if (
        incoming["apply_url"] == candidate.apply_url
        or incoming["dedupe_key"] == candidate.dedupe_key
    ):
        return True
    return sum(duplicate_signals(incoming, candidate).values()) >= 5


def remove_duplicates(
    incoming: Iterable[dict[str, Any]], candidates: Iterable[Job]
) -> tuple[list[dict[str, Any]], int]:
    accepted: list[dict[str, Any]] = []
    known: list[Any] = list(candidates)
    duplicates = 0
    for item in incoming:
        if any(is_duplicate(item, candidate) for candidate in known):
            duplicates += 1
            continue
        accepted.append(item)
        known.append(_Candidate(item))
    return accepted, duplicates


class _Candidate:
    def __init__(self, item: dict[str, Any]) -> None:
        self.__dict__.update(item)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def overlap_ratio(left: str | Iterable[str], right: Iterable[str]) -> float:
    left_tokens = (
        tokens(left)
        if isinstance(left, str)
        else {comparison_text(item) for item in left if comparison_text(item)}
    )
    right_tokens = {comparison_text(item) for item in right if comparison_text(item)}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(right_tokens)


def preference_range_match(
    job_min: float | Decimal | None,
    job_max: float | Decimal | None,
    preferred_min: float | Decimal | None,
    preferred_max: float | Decimal | None,
) -> bool | None:
    if (job_min is None and job_max is None) or (
        preferred_min is None and preferred_max is None
    ):
        return None
    return ranges_overlap(job_min, job_max, preferred_min, preferred_max)


def prepare_job(
    job: Job,
    profile: ProfileVersion,
    feature_reference_at: Any | None = None,
) -> PreparedJobV2:
    location = comparison_text(job.location)
    preferred_locations = [
        comparison_text(item) for item in profile.preferred_locations
    ]
    location_match = bool(location) and any(
        preferred in location or location in preferred
        for preferred in preferred_locations
        if preferred
    )
    salary_inr_min = getattr(job, "salary_inr_min", None)
    salary_inr_max = getattr(job, "salary_inr_max", None)
    if salary_inr_min is not None or salary_inr_max is not None:
        annual_salary_min, annual_salary_max = salary_inr_min, salary_inr_max
        prepared_salary_currency = "INR"
    else:
        annual_salary_min, annual_salary_max = annualized_salary_range(
            job.salary_min, job.salary_max, job.salary_period
        )
        prepared_salary_currency = job.salary_currency or ""
    salary_match = preference_range_match(
        annual_salary_min,
        annual_salary_max,
        profile.salary_min,
        profile.salary_max,
    )
    if (
        salary_match is not None
        and prepared_salary_currency
        and profile.salary_currency
        and prepared_salary_currency.casefold() != profile.salary_currency.casefold()
    ):
        salary_match = False
    legacy = PreparedJobV1(
        job_id=job.id,
        code=job.code,
        company_name=comparison_text(job.company_name),
        company_key=job.company_key,
        role_title=comparison_text(job.role_title),
        role_family=comparison_text(job.role_family),
        seniority=comparison_text(job.seniority),
        location=location,
        work_mode=comparison_text(job.work_mode),
        employment_type=comparison_text(job.employment_type),
        description=comparison_text(job.description),
        skills=[comparison_text(item) for item in job.skills],
        experience_min_years=job.experience_min_years,
        experience_max_years=job.experience_max_years,
        salary_min=(
            float(annual_salary_min) if annual_salary_min is not None else None
        ),
        salary_max=(
            float(annual_salary_max) if annual_salary_max is not None else None
        ),
        salary_currency=prepared_salary_currency,
        can_apply_now=job.can_apply_now,
        resume_text=clean_text(profile.resume_text),
        preferred_titles=profile.preferred_titles,
        preferred_locations=profile.preferred_locations,
        preferred_skills=profile.preferred_skills,
        title_token_overlap=max(
            (dice(job.role_title, preferred) for preferred in profile.preferred_titles),
            default=0.0,
        ),
        skill_overlap=overlap_ratio(job.skills, profile.preferred_skills),
        preferred_location_match=location_match,
        experience_range_match=preference_range_match(
            job.experience_min_years,
            job.experience_max_years,
            profile.experience_min_years,
            profile.experience_max_years,
        ),
        salary_range_match=salary_match,
        description_token_count=len(tokens(job.description)),
    )
    source = PreparedJobSourceV2(
        **legacy.model_dump(exclude={"feature_schema_version"}),
        posted_at=getattr(job, "posted_at", None),
        feature_reference_at=feature_reference_at,
    )
    return build_prepared_job_v2(source)
