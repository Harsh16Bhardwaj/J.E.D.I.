"""Source discovery, public job adapters, enrichment, and quality filtering."""

import asyncio
import hashlib
import html
import json
import re
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlsplit

import httpx
from pydantic import ValidationError

from backend.config import get_settings
from backend.schemas.product import IncomingJob
from backend.services.batch_ingestion import clean_current_job
from backend.services.product import canonical_url
from backend.services.scraper_enrichment import extract_facts

CONFIG_PATH = Path(__file__).parents[1] / "scraper.toml"


def bright_data_setting_configured(value: str | None) -> bool:
    return bool(value and value.strip().casefold() not in {"...", "none", "null"})


@dataclass(frozen=True)
class ScraperConfig:
    version: str
    lookback_days: int
    review_lookback_days: int
    target_job_count: int
    bright_data_limit: int
    request_timeout_seconds: int
    concurrent_sources: int
    max_retries: int
    max_candidates_per_company: int
    minimum_description_characters: int
    lease_seconds: int
    retention_days: int
    title_aliases: tuple[str, ...]
    excluded_title_terms: tuple[str, ...]
    india_terms: tuple[str, ...]
    remote_terms: tuple[str, ...]
    ats_types: tuple[str, ...]
    seed_sources: tuple[dict[str, str], ...]
    company_hints: tuple[dict[str, str], ...]
    content_hash: str


@dataclass(frozen=True)
class SourceSpec:
    source_key: str
    name: str
    ats_type: str
    domain_hint: str
    board_token: str
    discovered: bool = True


@dataclass(frozen=True)
class FetchResult:
    jobs: list[dict[str, Any]]
    bright_data_used: int = 0
    free_requests: int = 0
    next_checkpoint: dict[str, Any] | None = None
    response_time_ms: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    provider_uses: tuple[dict[str, Any], ...] = ()


def _string_tuple(raw: dict[str, Any], name: str) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in raw.get(name, []) if str(item).strip())


@lru_cache
def load_scraper_config() -> ScraperConfig:
    content = CONFIG_PATH.read_bytes()
    raw = tomllib.loads(content.decode("utf-8"))
    return ScraperConfig(
        version=str(raw["version"]),
        lookback_days=int(raw["lookback_days"]),
        review_lookback_days=int(raw.get("review_lookback_days", 30)),
        target_job_count=int(raw["target_job_count"]),
        bright_data_limit=int(raw["bright_data_limit"]),
        request_timeout_seconds=int(raw["request_timeout_seconds"]),
        concurrent_sources=int(raw.get("concurrent_sources", 3)),
        max_retries=int(raw.get("max_retries", 2)),
        max_candidates_per_company=int(raw.get("max_candidates_per_company", 8)),
        minimum_description_characters=int(
            raw.get("minimum_description_characters", 300)
        ),
        lease_seconds=int(raw["lease_seconds"]),
        retention_days=int(raw["retention_days"]),
        title_aliases=_string_tuple(raw, "title_aliases"),
        excluded_title_terms=_string_tuple(raw, "excluded_title_terms"),
        india_terms=_string_tuple(raw, "india_terms"),
        remote_terms=_string_tuple(raw, "remote_terms"),
        ats_types=_string_tuple(raw, "ats_types"),
        seed_sources=tuple(raw.get("seed_sources", [])),
        company_hints=tuple(raw.get("company_hints", [])),
        content_hash=hashlib.sha256(content).hexdigest(),
    )


def clean_html(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        divisor = 1000 if value > 10_000_000_000 else 1
        return datetime.fromtimestamp(value / divisor, tz=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def experience_range(text: str) -> tuple[float | None, float | None]:
    normalized = text.casefold()
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*years?", normalized
    )
    if match:
        return float(match.group(1)), float(match.group(2))
    match = re.search(r"(\d+(?:\.\d+)?)\s*\+\s*years?", normalized)
    if match:
        return float(match.group(1)), None
    match = re.search(
        r"(?:minimum|min\.?|at least)\s*(\d+(?:\.\d+)?)\s*years?", normalized
    )
    if match:
        return float(match.group(1)), None
    return None, None


def role_family(title: str) -> str | None:
    value = title.casefold()
    if any(
        term in value
        for term in (
            "machine learning",
            "ml ",
            " ml",
            "ai ",
            " ai",
            "llm",
            "generative",
        )
    ):
        return "ml_ai"
    if "backend" in value or "back-end" in value:
        return "backend"
    if "full stack" in value or "full-stack" in value:
        return "fullstack"
    if "web" in value:
        return "web"
    if "software" in value:
        return "software"
    return None


def salary_period(value: Any) -> str | None:
    normalized = str(value or "").casefold()
    if "month" in normalized:
        return "MONTHLY"
    if "year" in normalized or "annual" in normalized or "annum" in normalized:
        return "YEARLY"
    return None


def title_allowed(title: str, config: ScraperConfig) -> bool:
    value = title.casefold()
    return title_matches_scope(title, config) and not any(
        term in value for term in config.excluded_title_terms
    )


def title_matches_scope(title: str, config: ScraperConfig) -> bool:
    """Return broad engineering relevance without applying seniority policy."""
    value = title.casefold()
    return any(alias in value for alias in config.title_aliases)


def location_allowed(location: str | None, config: ScraperConfig) -> bool:
    if not location:
        return False
    value = location.casefold()
    return any(term in value for term in (*config.india_terms, *config.remote_terms))


@dataclass(frozen=True)
class CandidateAssessment:
    admitted: bool
    geography_eligibility: str
    source_quality_valid: bool
    quality_failures: tuple[str, ...]
    date_evidence: str | None
    freshness_tier: str
    quality_score: float
    review_group: str
    extracted_facts: dict[str, Any]
    evidence_spans: tuple[dict[str, Any], ...]
    extraction_version: str
    description_fingerprint: str


_NON_INDIA_REMOTE = (
    "united states",
    "remote - us",
    "remote us",
    "us only",
    "u.s. only",
    "canada",
    "europe",
    "emea",
    "united kingdom",
    "uk only",
    "ireland",
    "spain",
    "poland",
    "estonia",
    "germany",
    "france",
    "australia",
)


def geography_eligibility(location: str | None, config: ScraperConfig) -> str:
    value = clean_html(location).casefold()
    if not value:
        return "INELIGIBLE"
    india = any(term in value for term in config.india_terms)
    global_remote = any(term in value for term in ("worldwide", "anywhere", "global"))
    remote = "remote" in value
    restricted = any(term in value for term in _NON_INDIA_REMOTE)
    if india or global_remote:
        return "ELIGIBLE"
    if remote and restricted:
        return "INELIGIBLE"
    if remote:
        return "AMBIGUOUS"
    return "INELIGIBLE"


def assess_candidate(job: dict[str, Any], config: ScraperConfig) -> CandidateAssessment:
    failures: list[str] = []
    title = str(job.get("roleTitle") or "")
    if not title_allowed(title, config):
        failures.append("TITLE_OUT_OF_SCOPE")

    extraction = extract_facts(job.get("description"))
    minimum = job.get("experienceMinYears")
    if minimum is None:
        minimum = extraction.facts.get("experienceMinYears")
        job["experienceMinYears"] = minimum
        job["experienceMaxYears"] = extraction.facts.get("experienceMaxYears")
    if not job.get("skills"):
        job["skills"] = extraction.facts.get("skills") or []
    if not job.get("employmentType"):
        job["employmentType"] = extraction.facts.get("employmentType")
    if not job.get("seniority"):
        job["seniority"] = extraction.facts.get("seniority")
    extracted_salary = extraction.facts.get("salary")
    if (
        extracted_salary
        and job.get("salaryMin") is None
        and job.get("salaryMax") is None
    ):
        job["salaryMin"] = extracted_salary["min"]
        job["salaryMax"] = extracted_salary["max"]
        job["salaryCurrency"] = extracted_salary["currency"]
        job["salaryPeriod"] = extracted_salary["period"]
    if minimum is not None and float(minimum) > 5:
        failures.append("EXPERIENCE_ABOVE_FIVE_YEARS")

    geography = geography_eligibility(job.get("location"), config)
    if extraction.facts.get("remoteCountryRestrictions"):
        geography = "INELIGIBLE"
    if geography == "INELIGIBLE":
        failures.append("NOT_INDIA_ELIGIBLE")
    elif geography == "AMBIGUOUS":
        failures.append("REMOTE_ELIGIBILITY_AMBIGUOUS")

    description = clean_html(job.get("description"))
    if len(description) < config.minimum_description_characters:
        failures.append("DESCRIPTION_TOO_SHORT")
    if extraction.boilerplate_suspected:
        failures.append("BOILERPLATE_DESCRIPTION")
    if extraction.closed_or_disabled or job.get("canApplyNow") is False:
        failures.append("APPLICATION_CLOSED")

    posted = parse_datetime(job.get("postedAt"))
    date_evidence = str(job.get("__dateEvidence") or "") or None
    verified_date = date_evidence in {
        "JSON_LD_DATE_POSTED",
        "ATS_PUBLISHED_AT",
        "ATS_RELEASED_DATE",
        "ATS_DETAIL_RELEASED_DATE",
    }
    freshness_tier = "REJECTED"
    if posted is None:
        failures.append("POSTED_DATE_UNVERIFIED")
    else:
        age = datetime.now(UTC) - posted.astimezone(UTC)
        if age < timedelta(days=-1):
            failures.append("SUSPICIOUS_FUTURE_DATE")
        elif verified_date and age <= timedelta(days=config.lookback_days):
            freshness_tier = "VERIFIED_RECENT"
        elif age <= timedelta(days=config.review_lookback_days):
            freshness_tier = "REVIEW_RECENT"
            failures.append("DATE_REQUIRES_REVIEW")
        else:
            failures.append("OUTSIDE_REVIEW_WINDOW")

    url = str(job.get("applyUrl") or "")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        failures.append("DIRECT_URL_REQUIRED")
    quality_failures = tuple(dict.fromkeys(failures))
    # Importability is intentionally narrower than recommendation. Location,
    # seniority, experience, and description richness belong in owner review
    # and the ranker; only factual/schema blockers prevent import.
    import_blocked = any(
        failure in quality_failures
        for failure in (
            "POSTED_DATE_UNVERIFIED",
            "OUTSIDE_REVIEW_WINDOW",
            "SUSPICIOUS_FUTURE_DATE",
            "DIRECT_URL_REQUIRED",
            "APPLICATION_CLOSED",
        )
    )
    source_quality = not import_blocked
    admitted = not any(
        failure in quality_failures
        for failure in (
            "POSTED_DATE_UNVERIFIED",
            "OUTSIDE_REVIEW_WINDOW",
            "SUSPICIOUS_FUTURE_DATE",
            "DIRECT_URL_REQUIRED",
            "APPLICATION_CLOSED",
        )
    )
    quality_score = 0.0
    quality_score += 20 if "DIRECT_URL_REQUIRED" not in quality_failures else 0
    quality_score += (
        20 if len(description) >= config.minimum_description_characters else 0
    )
    quality_score += (
        20
        if freshness_tier == "VERIFIED_RECENT"
        else 10
        if freshness_tier == "REVIEW_RECENT"
        else 0
    )
    quality_score += (
        20 if geography == "ELIGIBLE" else 8 if geography == "AMBIGUOUS" else 0
    )
    extracted_count = sum(
        bool(extraction.facts.get(field))
        for field in ("skills", "experienceMinYears", "employmentType", "education")
    )
    quality_score += min(20, extracted_count * 5)
    hard_rejected = any(
        failure in quality_failures
        for failure in (
            "POSTED_DATE_UNVERIFIED",
            "OUTSIDE_REVIEW_WINDOW",
            "SUSPICIOUS_FUTURE_DATE",
            "DIRECT_URL_REQUIRED",
            "APPLICATION_CLOSED",
        )
    )
    requires_owner_review = any(
        failure in quality_failures
        for failure in (
            "TITLE_OUT_OF_SCOPE",
            "EXPERIENCE_ABOVE_FIVE_YEARS",
            "NOT_INDIA_ELIGIBLE",
            "REMOTE_ELIGIBILITY_AMBIGUOUS",
            "DESCRIPTION_TOO_SHORT",
            "BOILERPLATE_DESCRIPTION",
            "DATE_REQUIRES_REVIEW",
        )
    )
    if hard_rejected:
        review_group = "REJECTED"
    elif (
        freshness_tier == "VERIFIED_RECENT"
        and geography == "ELIGIBLE"
        and source_quality
        and not requires_owner_review
    ):
        review_group = "RECOMMENDED"
    else:
        review_group = "NEEDS_REVIEW"
    return CandidateAssessment(
        admitted=admitted,
        geography_eligibility=geography,
        source_quality_valid=source_quality,
        quality_failures=quality_failures,
        date_evidence=date_evidence,
        freshness_tier=freshness_tier,
        quality_score=quality_score,
        review_group=review_group,
        extracted_facts=extraction.facts,
        evidence_spans=extraction.evidence,
        extraction_version=extraction.version,
        description_fingerprint=extraction.description_fingerprint,
    )


def candidate_allowed(job: dict[str, Any], config: ScraperConfig) -> bool:
    assessment = assess_candidate(job, config)
    return (
        assessment.admitted
        and assessment.source_quality_valid
        and assessment.geography_eligibility == "ELIGIBLE"
        and assessment.review_group == "RECOMMENDED"
    )


def validate_candidate(job: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    try:
        clean_current_job(IncomingJob.model_validate(job))
        return True, []
    except (ValidationError, ValueError) as exc:
        errors = (
            exc.errors(include_context=False)
            if isinstance(exc, ValidationError)
            else [{"type": "value_error", "msg": str(exc)}]
        )
        return False, errors


async def _bright_data_request(
    target_url: str,
    *,
    zone: str,
    data_format: str = "json",
) -> Any:
    settings = get_settings()
    if not bright_data_setting_configured(
        settings.bright_data_api_key
    ) or not bright_data_setting_configured(zone):
        raise RuntimeError("Bright Data API key and zone are not configured.")
    payload = {
        "zone": zone,
        "url": target_url,
        "format": "json" if data_format == "json" else "raw",
        "method": "GET",
        "country": "in",
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            "https://api.brightdata.com/request",
            headers={"Authorization": f"Bearer {settings.bright_data_api_key}"},
            json=payload,
        )
        response.raise_for_status()
        return response.json() if data_format == "json" else response.text


ATS_DOMAINS = {
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
    "lever": ("jobs.lever.co",),
    "ashby": ("jobs.ashbyhq.com",),
    "workable": ("apply.workable.com",),
    "smartrecruiters": ("jobs.smartrecruiters.com",),
    "recruitee": ("recruitee.com",),
    "personio": ("jobs.personio.de", "jobs.personio.com"),
    "workday": ("myworkdayjobs.com",),
}


def ats_type_from_host(host: str) -> str | None:
    normalized = host.casefold().split(":", 1)[0]
    for ats_type, domains in ATS_DOMAINS.items():
        if any(
            normalized == domain or normalized.endswith(f".{domain}")
            for domain in domains
        ):
            return ats_type
    return None


def seeded_source_specs(config: ScraperConfig) -> list[SourceSpec]:
    return [
        SourceSpec(
            source_key=f"{item['ats_type']}:{item['board_token'].casefold()}",
            name=item["name"],
            ats_type=item["ats_type"],
            domain_hint=item["domain_hint"],
            board_token=item["board_token"],
            discovered=False,
        )
        for item in config.seed_sources
        if item.get("ats_type") in config.ats_types
    ]


def infer_source_from_url(url: str, *, name: str | None = None) -> SourceSpec:
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("Enter an absolute public ATS URL.")
    host = parts.netloc.casefold().split(":", 1)[0]
    if any(
        host == domain or host.endswith(f".{domain}")
        for domain in ("linkedin.com", "indeed.com", "wellfound.com", "naukri.com")
    ):
        raise ValueError(
            "Aggregator job boards are not supported; use employer-direct pages."
        )
    ats_type = ats_type_from_host(host) or "jsonld"
    source = source_from_url(url, ats_type)
    if source is None:
        raise ValueError("The ATS company identifier could not be read from this URL.")
    if name and name.strip():
        source = SourceSpec(**{**source.__dict__, "name": name.strip()})
    return source


def source_from_url(url: str, ats_type: str) -> SourceSpec | None:
    parts = urlsplit(url)
    path = [item for item in parts.path.split("/") if item]
    if not path and ats_type not in {"recruitee", "personio"}:
        return None
    token = path[0] if path else parts.netloc.split(".", 1)[0]
    if ats_type == "greenhouse" and token in {"jobs", "job-boards"} and len(path) > 1:
        token = path[1]
    if ats_type == "recruitee":
        token = parts.netloc.casefold().removesuffix(".recruitee.com")
    elif ats_type == "personio":
        token = parts.netloc.casefold().split(".jobs.personio.", 1)[0]
    elif ats_type in {"workday", "jsonld"}:
        token = url.split("#", 1)[0].rstrip("/")
    safe_token = re.sub(r"[^A-Za-z0-9_.-]+", "-", token).strip("-")
    key_token = (
        safe_token
        if ats_type not in {"workday", "jsonld"}
        else hashlib.sha256(token.encode()).hexdigest()[:16]
    )
    if not safe_token:
        return None
    source_key = f"{ats_type}:{key_token.casefold()}"
    return SourceSpec(
        source_key=source_key,
        name=(
            parts.netloc.split(".", 1)[0]
            if ats_type in {"workday", "jsonld"}
            else safe_token
        )
        .replace("-", " ")
        .replace("_", " ")
        .title(),
        ats_type=ats_type,
        domain_hint=parts.netloc.casefold(),
        board_token=token,
    )


def source_identity_consistent(
    expected_name: str, source: SourceSpec, jobs: list[dict[str, Any]]
) -> bool:
    generic_tokens = {
        "company",
        "group",
        "labs",
        "limited",
        "technologies",
        "technology",
        "solutions",
        "india",
    }
    expected_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", expected_name.casefold())
        if len(token) >= 3 and token not in generic_tokens
    }
    if not expected_tokens:
        return False
    observed_parts = [source.board_token, source.domain_hint]
    if source.ats_type in {"workable", "smartrecruiters"}:
        observed_parts.extend(str(job.get("companyName") or "") for job in jobs[:5])
    elif source.ats_type == "jsonld":
        observed_parts.extend(
            str(job.get("companyName") or "")
            for job in jobs[:5]
            if job.get("__companyEvidence") == "JSON_LD_HIRING_ORGANIZATION"
        )
    observed = " ".join(observed_parts).casefold()
    return any(token in observed for token in expected_tokens)


async def discover_company_sources(
    company_name: str, domain: str, config: ScraperConfig
) -> FetchResult:
    """Follow employer-owned career links and return supported public boards."""
    root = domain.strip().rstrip("/")
    if not root.startswith(("http://", "https://")):
        root = f"https://{root}"
    urls = [root, urljoin(f"{root}/", "careers"), urljoin(f"{root}/", "jobs")]
    employer_host = urlsplit(root).netloc.casefold()
    visited: set[str] = set()
    discovered: dict[str, SourceSpec] = {}
    requests = 0
    for candidate_url in urls:
        if candidate_url in visited:
            continue
        visited.add(candidate_url)
        try:
            document, _ = await _get_text(candidate_url, config, allow_unlocker=False)
            requests += 1
        except Exception:
            continue
        links = re.findall(r'href=["\']([^"\']+)["\']', document, flags=re.IGNORECASE)
        for raw_link in links:
            link = urljoin(candidate_url, html.unescape(raw_link))
            host = urlsplit(link).netloc.casefold()
            if (
                host == employer_host
                and any(
                    term in urlsplit(link).path.casefold()
                    for term in ("career", "jobs")
                )
                and link not in urls
                and len(urls) < 8
            ):
                urls.append(link)
            ats_type = ats_type_from_host(host)
            if ats_type:
                source = source_from_url(link, ats_type)
                if source:
                    source = SourceSpec(**{**source.__dict__, "name": company_name})
                    discovered[source.source_key] = source
        if _job_posting_json_lds(document):
            source = source_from_url(candidate_url, "jsonld")
            if source:
                source = SourceSpec(**{**source.__dict__, "name": company_name})
                discovered[source.source_key] = source
    return FetchResult(
        jobs=[item.__dict__ for item in discovered.values()], free_requests=requests
    )


async def _get_json(
    url: str, config: ScraperConfig, *, allow_unlocker: bool = True
) -> tuple[Any, int]:
    try:
        async with httpx.AsyncClient(
            timeout=config.request_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "JEDI-Job-Collector/1.0"},
        ) as client:
            response = await client.get(url)
        if response.status_code not in {403, 429} and response.status_code < 500:
            response.raise_for_status()
            return response.json(), 0
    except json.JSONDecodeError:
        response = None
    except httpx.RequestError:
        response = None
    if not allow_unlocker:
        if response is not None:
            response.raise_for_status()
        raise RuntimeError("Direct ATS response was malformed.")
    raw = await _bright_data_request(
        url, zone=get_settings().bright_data_unlocker_zone, data_format="raw"
    )
    return json.loads(raw), 1


async def _get_json_conditional(
    url: str,
    config: ScraperConfig,
    *,
    etag: str | None,
    last_modified: str | None,
) -> tuple[Any | None, int, str | None, str | None, bool]:
    headers = {"User-Agent": "JEDI-Job-Collector/2.0"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    async with httpx.AsyncClient(
        timeout=config.request_timeout_seconds,
        follow_redirects=True,
        headers=headers,
    ) as client:
        response = await client.get(url)
    if response.status_code == 304:
        return None, 0, etag, last_modified, True
    response.raise_for_status()
    return (
        response.json(),
        0,
        response.headers.get("etag"),
        response.headers.get("last-modified"),
        False,
    )


async def _get_text(
    url: str, config: ScraperConfig, *, allow_unlocker: bool = True
) -> tuple[str, int]:
    last_error: Exception | None = None
    for retry in range(config.max_retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=config.request_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "JEDI-Job-Collector/1.0"},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text, 0
        except httpx.HTTPError as exc:
            last_error = exc
            if retry < config.max_retries:
                await asyncio.sleep(0.15 * (retry + 1))
    if not allow_unlocker:
        raise last_error or RuntimeError("Job detail request failed.")
    raw = await _bright_data_request(
        url, zone=get_settings().bright_data_unlocker_zone, data_format="raw"
    )
    return raw, 1


async def _post_json(url: str, payload: dict[str, Any], config: ScraperConfig) -> Any:
    last_error: Exception | None = None
    for retry in range(config.max_retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=config.request_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "JEDI-Job-Collector/2.0"},
            ) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            last_error = exc
            if retry < config.max_retries:
                await asyncio.sleep(0.15 * (retry + 1))
    raise last_error or RuntimeError("Public ATS request failed.")


def _job_posting_json_lds(document: str) -> list[dict[str, Any]]:
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        document,
        flags=re.IGNORECASE | re.DOTALL,
    )

    def find(value: Any) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if isinstance(value, dict):
            if value.get("@type") == "JobPosting":
                found.append(value)
            for nested in value.values():
                found.extend(find(nested))
        elif isinstance(value, list):
            for nested in value:
                found.extend(find(nested))
        return found

    postings: list[dict[str, Any]] = []
    for script in scripts:
        try:
            result = find(json.loads(html.unescape(script).strip()))
        except (json.JSONDecodeError, TypeError):
            continue
        postings.extend(result)
    return postings


def _job_posting_json_ld(document: str) -> dict[str, Any] | None:
    postings = _job_posting_json_lds(document)
    return postings[0] if postings else None


def _jsonld_location(posting: dict[str, Any]) -> str | None:
    values = posting.get("jobLocation") or posting.get("applicantLocationRequirements")
    values = values if isinstance(values, list) else [values]
    parts: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        address = value.get("address") or value
        if isinstance(address, dict):
            parts.extend(
                str(address.get(key))
                for key in ("addressLocality", "addressRegion", "addressCountry")
                if address.get(key)
            )
    if posting.get("jobLocationType") == "TELECOMMUTE":
        parts.insert(0, "Remote")
    return ", ".join(dict.fromkeys(parts)) or None


def _jsonld_job(
    source: SourceSpec, posting: dict[str, Any], fallback_url: str
) -> dict[str, Any]:
    organization = posting.get("hiringOrganization") or {}
    if isinstance(organization, dict) and organization.get("name"):
        source = SourceSpec(
            **{**source.__dict__, "name": clean_html(organization.get("name"))}
        )
    job = _job(
        source,
        title=posting.get("title"),
        description=posting.get("description"),
        url=posting.get("url") or fallback_url,
        location=_jsonld_location(posting),
        posted_at=posting.get("datePosted"),
        employment_type=posting.get("employmentType"),
        date_evidence="JSON_LD_DATE_POSTED" if posting.get("datePosted") else None,
    )
    if isinstance(organization, dict) and organization.get("name"):
        job["__companyEvidence"] = "JSON_LD_HIRING_ORGANIZATION"
    deadline = parse_datetime(posting.get("validThrough"))
    if deadline:
        job["applicationDeadline"] = deadline.isoformat()
        job["canApplyNow"] = deadline >= datetime.now(UTC)
    salary = posting.get("baseSalary") or {}
    value = salary.get("value") or {}
    if isinstance(value, dict):
        exact = value.get("value")
        if (
            exact is not None
            or value.get("minValue") is not None
            or value.get("maxValue") is not None
        ):
            job["salaryMin"] = value.get("minValue", exact)
            job["salaryMax"] = value.get("maxValue", exact)
            job["salaryCurrency"] = salary.get("currency") or posting.get(
                "salaryCurrency"
            )
            unit = str(value.get("unitText") or "").upper()
            job["salaryPeriod"] = (
                "MONTHLY"
                if "MONTH" in unit
                else "YEARLY"
                if any(term in unit for term in ("YEAR", "ANNUAL"))
                else None
            )
    return job


async def _enrich_job_page(
    job: dict[str, Any], config: ScraperConfig, *, allow_unlocker: bool
) -> int:
    if (
        len(clean_html(job.get("description"))) >= config.minimum_description_characters
        and job.get("postedAt")
        and job.get("__dateEvidence")
        in {
            "JSON_LD_DATE_POSTED",
            "ATS_PUBLISHED_AT",
            "ATS_RELEASED_DATE",
            "ATS_DETAIL_RELEASED_DATE",
        }
    ):
        return 0
    document, used = await _get_text(
        str(job.get("applyUrl") or ""), config, allow_unlocker=allow_unlocker
    )
    posting = _job_posting_json_ld(document)
    if posting is None and allow_unlocker and used == 0:
        settings = get_settings()
        if bright_data_setting_configured(
            settings.bright_data_api_key
        ) and bright_data_setting_configured(settings.bright_data_unlocker_zone):
            rendered = await _bright_data_request(
                str(job.get("applyUrl") or ""),
                zone=settings.bright_data_unlocker_zone,
                data_format="raw",
            )
            used += 1
            posting = _job_posting_json_ld(rendered)
    if not posting:
        return used
    if len(clean_html(posting.get("description"))) > len(
        clean_html(job.get("description"))
    ):
        job["description"] = clean_html(posting.get("description"))
        minimum, maximum = experience_range(job["description"])
        job["experienceMinYears"], job["experienceMaxYears"] = minimum, maximum
    if posting.get("datePosted"):
        job["postedAt"] = (
            parse_datetime(posting.get("datePosted")).isoformat()
            if parse_datetime(posting.get("datePosted"))
            else None
        )
        job["__dateEvidence"] = "JSON_LD_DATE_POSTED"
    deadline = parse_datetime(posting.get("validThrough"))
    if deadline:
        job["applicationDeadline"] = deadline.isoformat()
        job["canApplyNow"] = deadline >= datetime.now(UTC)
    salary = posting.get("baseSalary") or {}
    value = salary.get("value") or {}
    if isinstance(value, dict) and (
        value.get("minValue") is not None
        or value.get("maxValue") is not None
        or value.get("value") is not None
    ):
        exact = value.get("value")
        job["salaryMin"] = value.get("minValue", exact)
        job["salaryMax"] = value.get("maxValue", exact)
        job["salaryCurrency"] = salary.get("currency") or posting.get("salaryCurrency")
        unit = str(value.get("unitText") or "").upper()
        job["salaryPeriod"] = (
            "MONTHLY"
            if "MONTH" in unit
            else "YEARLY"
            if any(term in unit for term in ("YEAR", "ANNUAL"))
            else None
        )
    return used


def _job(
    source: SourceSpec,
    *,
    title: Any,
    description: Any,
    url: Any,
    location: Any,
    posted_at: Any,
    work_mode: Any = None,
    employment_type: Any = None,
    salary_min: Any = None,
    salary_max: Any = None,
    salary_currency: Any = None,
    salary_period: Any = None,
    date_evidence: str | None = None,
) -> dict[str, Any]:
    plain_description = clean_html(description)
    experience_min, experience_max = experience_range(plain_description)
    return {
        "companyName": source.name,
        "roleTitle": clean_html(title),
        "roleFamily": role_family(clean_html(title)),
        "seniority": None,
        "location": clean_html(location) or None,
        "workMode": clean_html(work_mode) or None,
        "employmentType": clean_html(employment_type) or None,
        "description": plain_description,
        "skills": [],
        "experienceMinYears": experience_min,
        "experienceMaxYears": experience_max,
        "salaryMin": salary_min,
        "salaryMax": salary_max,
        "salaryCurrency": str(salary_currency).upper() if salary_currency else None,
        "salaryPeriod": salary_period,
        "postedAt": parse_datetime(posted_at).isoformat()
        if parse_datetime(posted_at)
        else None,
        "applicationDeadline": None,
        "canApplyNow": True,
        "applyUrl": str(url or ""),
        "__dateEvidence": date_evidence,
    }


async def fetch_source_jobs(
    source: SourceSpec,
    config: ScraperConfig,
    *,
    allow_unlocker: bool = True,
    checkpoint: dict[str, Any] | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
    cached_jobs: list[dict[str, Any]] | None = None,
) -> FetchResult:
    used = 0
    free_requests = 0
    next_checkpoint: dict[str, Any] | None = None
    provider_uses: list[dict[str, Any]] = []
    unlocker_available = allow_unlocker and config.bright_data_limit > 0
    jobs: list[dict[str, Any]] = []
    if source.ats_type == "greenhouse":
        (
            data,
            units,
            response_etag,
            response_last_modified,
            unchanged,
        ) = await _get_json_conditional(
            f"https://boards-api.greenhouse.io/v1/boards/{quote_plus(source.board_token)}/jobs?content=true",
            config,
            etag=etag,
            last_modified=last_modified,
        )
        free_requests += 1
        used += units
        if unchanged:
            return FetchResult(
                jobs=list(cached_jobs or []),
                free_requests=free_requests,
                etag=etag,
                last_modified=last_modified,
            )
        for item in data.get("jobs", []):
            jobs.append(
                _job(
                    source,
                    title=item.get("title"),
                    description=item.get("content"),
                    url=item.get("absolute_url"),
                    location=(item.get("location") or {}).get("name"),
                    posted_at=None,
                )
            )
    elif source.ats_type == "lever":
        data, units = await _get_json(
            f"https://api.lever.co/v0/postings/{quote_plus(source.board_token)}?mode=json",
            config,
            allow_unlocker=False,
        )
        free_requests += 1
        used += units
        for item in data:
            categories = item.get("categories") or {}
            salary = item.get("salaryRange") or {}
            jobs.append(
                _job(
                    source,
                    title=item.get("text"),
                    description=item.get("descriptionPlain") or item.get("description"),
                    url=item.get("hostedUrl") or item.get("applyUrl"),
                    location=categories.get("location"),
                    posted_at=item.get("createdAt") or item.get("updatedAt"),
                    work_mode=item.get("workplaceType"),
                    employment_type=categories.get("commitment"),
                    salary_min=salary.get("min"),
                    salary_max=salary.get("max"),
                    salary_currency=salary.get("currency"),
                    salary_period=salary_period(salary.get("interval")),
                    date_evidence="ATS_CREATED_AT"
                    if item.get("createdAt")
                    else "ATS_UPDATED_AT"
                    if item.get("updatedAt")
                    else None,
                )
            )
    elif source.ats_type == "ashby":
        data, units = await _get_json(
            f"https://api.ashbyhq.com/posting-api/job-board/{quote_plus(source.board_token)}?includeCompensation=true",
            config,
            allow_unlocker=False,
        )
        free_requests += 1
        used += units
        for item in data.get("jobs", []):
            salary = next(
                (
                    part
                    for part in (
                        (item.get("compensation") or {}).get("summaryComponents") or []
                    )
                    if part.get("compensationType") == "Salary"
                ),
                {},
            )
            interval = str(salary.get("interval") or "")
            jobs.append(
                _job(
                    source,
                    title=item.get("title"),
                    description=item.get("descriptionPlain")
                    or item.get("descriptionHtml"),
                    url=item.get("jobUrl") or item.get("applyUrl"),
                    location=item.get("location"),
                    posted_at=item.get("publishedAt"),
                    work_mode=item.get("workplaceType"),
                    employment_type=item.get("employmentType"),
                    salary_min=salary.get("minValue"),
                    salary_max=salary.get("maxValue"),
                    salary_currency=salary.get("currencyCode"),
                    salary_period=salary_period(interval),
                    date_evidence="ATS_PUBLISHED_AT"
                    if item.get("publishedAt")
                    else None,
                )
            )
    elif source.ats_type == "workable":
        data, units = await _get_json(
            f"https://www.workable.com/api/accounts/{quote_plus(source.board_token)}?details=true",
            config,
            allow_unlocker=False,
        )
        free_requests += 1
        used += units
        source = SourceSpec(
            **{**source.__dict__, "name": data.get("name") or source.name}
        )
        for item in data.get("jobs", data.get("results", [])):
            location = item.get("location") or {}
            salary = item.get("salary") or {}
            jobs.append(
                _job(
                    source,
                    title=item.get("title"),
                    description=item.get("description")
                    or item.get("description_plain"),
                    url=item.get("url") or item.get("shortlink"),
                    location=location.get("location_str")
                    if isinstance(location, dict)
                    else location,
                    posted_at=item.get("created_at"),
                    work_mode=(
                        location.get("workplace_type")
                        if isinstance(location, dict)
                        else None
                    ),
                    employment_type=item.get("employment_type"),
                    salary_min=salary.get("salary_from"),
                    salary_max=salary.get("salary_to"),
                    salary_currency=salary.get("salary_currency"),
                    salary_period=salary_period(
                        salary.get("salary_period") or salary.get("period")
                    ),
                    date_evidence="ATS_CREATED_AT" if item.get("created_at") else None,
                )
            )
    elif source.ats_type == "smartrecruiters":
        listings: list[dict[str, Any]] = []
        offset = int((checkpoint or {}).get("offset", 0))
        data, units = await _get_json(
            f"https://api.smartrecruiters.com/v1/companies/{quote_plus(source.board_token)}/postings?limit=100&offset={offset}",
            config,
            allow_unlocker=False,
        )
        free_requests += 1
        used += units
        page = list(data.get("content", []))
        listings.extend(page)
        next_offset = offset + len(page)
        if page and next_offset < int(data.get("totalFound") or next_offset):
            next_checkpoint = {"offset": next_offset}
        for item in listings:
            company = (item.get("company") or {}).get("name")
            item_source = SourceSpec(
                **{**source.__dict__, "name": company or source.name}
            )
            location = item.get("location") or {}
            candidate = _job(
                item_source,
                title=item.get("name"),
                description=item.get("jobAd")
                or item.get("description")
                or item.get("name"),
                url=item.get("ref") or item.get("applyUrl"),
                location=location.get("fullLocation"),
                posted_at=item.get("releasedDate"),
                employment_type=(item.get("typeOfEmployment") or {}).get("label"),
                date_evidence="ATS_RELEASED_DATE" if item.get("releasedDate") else None,
            )
            if (
                title_matches_scope(candidate["roleTitle"], config)
            ):
                posting_id = (
                    item.get("id")
                    or str(item.get("ref") or "").rstrip("/").split("/")[-1]
                )
                if posting_id:
                    detail, units = await _get_json(
                        f"https://api.smartrecruiters.com/v1/companies/{quote_plus(source.board_token)}/postings/{quote_plus(str(posting_id))}",
                        config,
                        allow_unlocker=unlocker_available
                        and used < config.bright_data_limit,
                    )
                    used += units
                    free_requests += 1
                    if units:
                        provider_uses.append(
                            {
                                "candidateUrl": candidate["applyUrl"],
                                "provider": "brightdata-unlocker",
                                "units": units,
                                "reason": "ATS detail API was blocked or incomplete",
                            }
                        )
                    sections = detail.get("jobAd") or {}
                    pieces = [
                        sections.get("companyDescription"),
                        sections.get("jobDescription"),
                        sections.get("qualifications"),
                        sections.get("additionalInformation"),
                    ]
                    candidate["description"] = (
                        clean_html(" ".join(str(piece or "") for piece in pieces))
                        or candidate["description"]
                    )
                    candidate["applyUrl"] = (
                        detail.get("applyUrl") or candidate["applyUrl"]
                    )
                    candidate["postedAt"] = (
                        parse_datetime(detail.get("releasedDate")).isoformat()
                        if parse_datetime(detail.get("releasedDate"))
                        else candidate["postedAt"]
                    )
                    candidate["__dateEvidence"] = (
                        "ATS_DETAIL_RELEASED_DATE"
                        if detail.get("releasedDate")
                        else candidate.get("__dateEvidence")
                    )
                    candidate["experienceMinYears"], candidate["experienceMaxYears"] = (
                        experience_range(candidate["description"])
                    )
            jobs.append(candidate)
    elif source.ats_type == "recruitee":
        data, units = await _get_json(
            f"https://{source.board_token}.recruitee.com/api/offers/",
            config,
            allow_unlocker=False,
        )
        free_requests += 1
        used += units
        offers = data if isinstance(data, list) else data.get("offers", [])
        for item in offers:
            locations = item.get("locations") or []
            location = item.get("location")
            if not location and locations:
                location = ", ".join(
                    clean_html(value.get("name") if isinstance(value, dict) else value)
                    for value in locations
                )
            jobs.append(
                _job(
                    source,
                    title=item.get("title"),
                    description=item.get("description") or item.get("description_html"),
                    url=item.get("careers_url")
                    or item.get("offer_url")
                    or item.get("url"),
                    location=location,
                    posted_at=item.get("published_at") or item.get("created_at"),
                    employment_type=item.get("employment_type"),
                    date_evidence="ATS_PUBLISHED_AT"
                    if item.get("published_at")
                    else "ATS_CREATED_AT"
                    if item.get("created_at")
                    else None,
                )
            )
    elif source.ats_type == "personio":
        feed_url = (
            source.board_token
            if source.board_token.startswith("http")
            else f"https://{source.board_token}.jobs.personio.de/xml"
        )
        document, units = await _get_text(feed_url, config, allow_unlocker=False)
        free_requests += 1
        used += units
        root = ET.fromstring(document)
        for position in root.findall(".//position"):

            def xml_text(name: str, node_root: ET.Element = position) -> str | None:
                node = node_root.find(name)
                return (
                    clean_html(" ".join(node.itertext())) if node is not None else None
                )

            descriptions = " ".join(
                clean_html(" ".join(node.itertext()))
                for node in position.findall(".//jobDescriptions/jobDescription")
            )
            identifier = xml_text("id")
            vacancy_url = xml_text("url") or (
                f"https://{source.domain_hint}/job/{identifier}" if identifier else ""
            )
            jobs.append(
                _job(
                    source,
                    title=xml_text("name"),
                    description=descriptions,
                    url=vacancy_url,
                    location=xml_text("office"),
                    posted_at=xml_text("createdAt"),
                    employment_type=xml_text("employmentType"),
                    date_evidence="ATS_CREATED_AT" if xml_text("createdAt") else None,
                )
            )
    elif source.ats_type == "workday":
        parsed = urlsplit(source.board_token)
        path = [part for part in parsed.path.split("/") if part]
        if path and re.fullmatch(r"[a-z]{2}-[a-z]{2}", path[0], flags=re.IGNORECASE):
            path = path[1:]
        site = path[0] if path else "External"
        tenant = parsed.netloc.split(".", 1)[0]
        offset = int((checkpoint or {}).get("offset", 0))
        endpoint = f"https://{parsed.netloc}/wday/cxs/{tenant}/{site}/jobs"
        data = await _post_json(
            endpoint,
            {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": ""},
            config,
        )
        free_requests += 1
        postings = data.get("jobPostings", [])
        public_base_path = parsed.path.split("/job/", 1)[0].rstrip("/")
        next_offset = offset + len(postings)
        if postings and next_offset < int(data.get("total") or next_offset):
            next_checkpoint = {"offset": next_offset}
        for item in postings:
            external_path = item.get("externalPath")
            vacancy_url = (
                f"https://{parsed.netloc}{public_base_path}{external_path}"
                if external_path
                else ""
            )
            candidate = _job(
                source,
                title=item.get("title"),
                description=item.get("bulletFields") or item.get("title"),
                url=vacancy_url,
                location=item.get("locationsText"),
                posted_at=item.get("postedOn"),
                date_evidence="ATS_UPDATED_AT" if item.get("postedOn") else None,
            )
            if (
                title_matches_scope(candidate["roleTitle"], config)
                and external_path
            ):
                try:
                    detail, units = await _get_json(
                        f"https://{parsed.netloc}/wday/cxs/{tenant}/{site}{external_path}",
                        config,
                        allow_unlocker=unlocker_available
                        and used < config.bright_data_limit,
                    )
                    free_requests += 1
                    used += units
                    candidate["description"] = clean_html(
                        detail.get("jobPostingInfo", {}).get("jobDescription")
                        or detail.get("jobDescription")
                        or candidate["description"]
                    )
                    info = detail.get("jobPostingInfo") or {}
                    candidate["postedAt"] = (
                        parse_datetime(
                            info.get("startDate") or info.get("postedOn")
                        ).isoformat()
                        if parse_datetime(info.get("startDate") or info.get("postedOn"))
                        else candidate["postedAt"]
                    )
                    candidate["__dateEvidence"] = (
                        "ATS_PUBLISHED_AT"
                        if info.get("startDate")
                        else candidate["__dateEvidence"]
                    )
                    if units:
                        provider_uses.append(
                            {
                                "candidateUrl": vacancy_url,
                                "provider": "brightdata-unlocker",
                                "units": units,
                                "reason": "Workday shortlisted detail was blocked",
                            }
                        )
                except Exception:
                    pass
            jobs.append(candidate)
    elif source.ats_type == "jsonld":
        document, units = await _get_text(
            source.board_token, config, allow_unlocker=False
        )
        free_requests += 1
        used += units
        postings = _job_posting_json_lds(document)
        for posting in postings:
            fallback_url = source.board_token if len(postings) == 1 else ""
            jobs.append(_jsonld_job(source, posting, fallback_url))
    else:
        raise ValueError(f"Unsupported ATS type: {source.ats_type}")
    cached_by_url: dict[str, dict[str, Any]] = {}
    for cached in cached_jobs or []:
        try:
            cached_by_url[canonical_candidate_url(cached)] = cached
        except ValueError:
            continue
    for job in jobs:
        if not title_matches_scope(str(job.get("roleTitle") or ""), config):
            continue
        try:
            cached = cached_by_url.get(canonical_candidate_url(job))
        except ValueError:
            cached = None
        if cached:
            for field in (
                "description",
                "postedAt",
                "salaryMin",
                "salaryMax",
                "salaryCurrency",
                "salaryPeriod",
                "__dateEvidence",
            ):
                if cached.get(field) not in (None, ""):
                    job[field] = cached[field]
        if run_detail_needed := (
            len(clean_html(job.get("description")))
            < config.minimum_description_characters
            or not job.get("postedAt")
        ):
            try:
                detail_units = await _enrich_job_page(
                    job,
                    config,
                    allow_unlocker=unlocker_available
                    and used < config.bright_data_limit,
                )
                used += detail_units
                free_requests += 1
                if detail_units:
                    provider_uses.append(
                        {
                            "candidateUrl": str(job.get("applyUrl") or ""),
                            "provider": "brightdata-unlocker",
                            "units": detail_units,
                            "reason": (
                                "Shortlisted vacancy detail was blocked or incomplete"
                            ),
                        }
                    )
            except Exception:
                if run_detail_needed:
                    pass
    return FetchResult(
        jobs=jobs,
        bright_data_used=used,
        free_requests=free_requests,
        next_checkpoint=next_checkpoint,
        etag=locals().get("response_etag"),
        last_modified=locals().get("response_last_modified"),
        provider_uses=tuple(provider_uses),
    )


def canonical_candidate_url(job: dict[str, Any]) -> str:
    return canonical_url(str(job.get("applyUrl") or ""))
