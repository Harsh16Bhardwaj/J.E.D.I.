"""Leakage-safe feature construction shared by training and inference.

Only values available before a user labels a job may enter this module. Manual
fit scores and the applied target are deliberately absent from the contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from backend.schemas.modeling import (
    ModelFeaturesV2,
    PreparedJobSourceV2,
    PreparedJobV2,
)

FEATURE_SCHEMA_VERSION = "prepared-job-v2"

BASE_NUMERIC_FEATURES = (
    "experience_min_years",
    "salary_min",
    "salary_max",
    "salary_midpoint",
    "experience_profile_fit_imputed",
)
BOOLEAN_FEATURES = (
    "has_skills_or_requirements",
    "is_bengaluru",
    "is_gurgaon_ncr",
    "is_india",
    "salary_available",
)
CATEGORICAL_FEATURES = (
    "can_apply_now",
    "freshness",
    "role_family_standard",
    "seniority_standard",
    "employment_type_standard",
    "work_mode_standard",
    "city_standard",
    "country_standard",
    "location_bucket",
    "experience_min_bucket",
    "skills_imputation_type",
    "experience_profile_fit_imputation_reason",
)
ENGINEERED_FEATURES = tuple(
    name for name in ModelFeaturesV2.model_fields if name.startswith("feat_")
)
TEXT_FEATURES = ("enhanced_title_skill_text", "enhanced_context_text")
MODEL_INPUT_FEATURES = (
    BASE_NUMERIC_FEATURES
    + BOOLEAN_FEATURES
    + CATEGORICAL_FEATURES
    + ENGINEERED_FEATURES
    + TEXT_FEATURES
)
STACKED_SCORE_FEATURES = (
    "pred_role_title_preference_score",
    "pred_role_family_preference_score",
    "pred_seniority_profile_fit_score",
    "pred_location_profile_fit_score",
    "pred_work_mode_fit_score",
    "pred_experience_profile_fit_score",
    "pred_skills_profile_fit_score",
    "pred_salary_profile_fit_score",
    "pred_overall_preference_score",
)

_KNOWN_ROLE_FAMILIES = {
    "frontend",
    "backend",
    "fullstack",
    "data_engineering",
    "data_science",
    "analytics",
    "ml_ai",
    "devops_cloud",
    "qa_testing",
    "product_engineering",
    "other",
}
_ROLE_PATTERNS = (
    ("qa_testing", (r"\bqa\b", r"quality assurance", r"test (?:engineer|automation)")),
    ("fullstack", (r"full[ -]?stack",)),
    ("frontend", (r"front[ -]?end", r"\bui engineer", r"mobile")),
    ("backend", (r"back[ -]?end", r"\bapi\b", r"server")),
    ("data_engineering", (r"data engineer", r"\betl\b", r"spark", r"airflow")),
    ("data_science", (r"data scien", r"\bscientist\b")),
    ("analytics", (r"\banalytics?\b", r"business intelligence")),
    ("ml_ai", (r"machine learning", r"\bai\b", r"\bllm", r"genai", r"\brag\b")),
    ("devops_cloud", (r"devops", r"\bsre\b", r"cloud engineer", r"kubernetes")),
    ("product_engineering", (r"product engineer",)),
)
_FALLBACK_SKILLS = {
    "backend": ("apis", "databases", "backend engineering"),
    "fullstack": ("frontend", "apis", "databases"),
    "frontend": ("javascript", "user interfaces", "web development"),
    "data_engineering": ("sql", "data pipelines", "etl"),
    "data_science": ("python", "statistics", "machine learning"),
    "analytics": ("sql", "analytics", "reporting"),
    "ml_ai": ("python", "machine learning", "llms"),
    "devops_cloud": ("cloud", "ci/cd", "infrastructure"),
    "qa_testing": ("testing", "test automation", "quality assurance"),
}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return re.sub(r"\s+", " ", text)


def _contains(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _flag(value: bool) -> float:
    return 1.0 if value else 0.0


def _role_family(source: PreparedJobSourceV2) -> str:
    existing = re.sub(r"[^a-z0-9]+", "_", _norm(source.role_family)).strip("_")
    if existing in _KNOWN_ROLE_FAMILIES:
        return existing
    text = _norm(f"{source.role_title} {source.role_family} {' '.join(source.skills)}")
    for family, patterns in _ROLE_PATTERNS:
        if _contains(text, patterns):
            return family
    return "other"


def _seniority(source: PreparedJobSourceV2) -> str:
    text = _norm(f"{source.seniority} {source.role_title}")
    patterns = (
        ("principal", (r"\bprincipal\b",)),
        ("staff", (r"\bstaff\b",)),
        ("lead", (r"\blead\b", r"tech lead")),
        ("senior", (r"\bsenior\b", r"\bsr\.?\b")),
        ("intern", (r"\bintern(?:ship)?\b",)),
        ("new_grad", (r"new grad", r"graduate", r"campus")),
        ("entry_level", (r"entry[ -]?level", r"associate", r"sde i\b")),
        ("junior", (r"\bjunior\b", r"\bjr\.?\b")),
        ("early_mid", (r"early[ -]?mid",)),
        ("mid", (r"\bmid(?:dle)?[ -]?level\b", r"sde ii\b")),
    )
    for level, level_patterns in patterns:
        if _contains(text, level_patterns):
            return level
    years = source.experience_min_years
    if years is None:
        return "unknown"
    if years <= 0:
        return "entry_level"
    if years <= 1:
        return "junior"
    if years <= 2:
        return "early_mid"
    if years <= 4:
        return "mid"
    return "senior"


def _employment_type(source: PreparedJobSourceV2) -> str:
    text = _norm(f"{source.employment_type} {source.role_title}")
    patterns = (
        ("internship", (r"\bintern(?:ship)?\b",)),
        ("apprenticeship", (r"apprentice", r"trainee", r"accelerator")),
        ("freelance", (r"freelance",)),
        ("part_time", (r"part[ -]?time",)),
        ("contract", (r"contract",)),
        ("temporary", (r"temporary", r"\btemp\b")),
        ("full_time", (r"full[ -]?time", r"permanent", r"employee")),
    )
    for value, value_patterns in patterns:
        if _contains(text, value_patterns):
            return value
    return "unknown"


def _work_mode(source: PreparedJobSourceV2) -> str:
    text = _norm(f"{source.work_mode} {source.location} {source.employment_type}")
    if _contains(text, (r"onsite or remote", r"office or remote", r"flexible")):
        return "flexible"
    if "hybrid" in text:
        return "hybrid"
    if _contains(text, (r"remote", r"work from home", r"\bwfh\b")):
        return "remote"
    if _contains(text, (r"on[ -]?site", r"in[ -]?office", r"\boffice\b")):
        return "onsite"
    return "unknown"


def _location(
    source: PreparedJobSourceV2, work_mode: str
) -> tuple[str, str, str, bool, bool, bool]:
    text = _norm(source.location)
    bengaluru = _contains(text, (r"bengaluru", r"bangalore"))
    ncr = _contains(
        text, (r"gurgaon", r"gurugram", r"noida", r"delhi", r"faridabad", r"\bncr\b")
    )
    india = _contains(
        text,
        (
            r"india",
            r"bengaluru",
            r"bangalore",
            r"gurgaon",
            r"gurugram",
            r"noida",
            r"delhi",
            r"hyderabad",
            r"pune",
            r"mumbai",
            r"chennai",
        ),
    )
    city, country, bucket = "unknown", "unknown", "unknown"
    city_terms = (
        ("bengaluru", bengaluru),
        ("delhi_ncr", ncr),
        ("hyderabad", "hyderabad" in text),
        ("pune", "pune" in text),
        ("mumbai", "mumbai" in text),
        ("chennai", "chennai" in text),
    )
    for candidate, matches in city_terms:
        if matches:
            city, country, bucket = candidate, "india", candidate
            break
    if country == "unknown" and _contains(
        text, (r"united states", r"\busa\b", r"new york", r"california", r"seattle")
    ):
        country, bucket = "us", "us"
    elif country == "unknown" and _contains(
        text, (r"europe", r"united kingdom", r"\buk\b", r"germany", r"france")
    ):
        country, bucket = "europe", "europe"
    elif country == "unknown" and india:
        country, bucket = "india", "india_other"
    if work_mode == "remote":
        if india:
            country, bucket = "india", "india_remote"
        elif _contains(text, (r"global", r"worldwide", r"anywhere", r"everywhere")):
            bucket = "global_remote"
    return city, country, bucket, bengaluru, ncr, india


def _experience_bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value <= 0:
        return "0"
    if value <= 1:
        return "1"
    if value <= 2:
        return "2"
    if value <= 3:
        return "3"
    return "4_plus"


def _freshness(posted_at: datetime | None, reference_at: datetime | None) -> str:
    if posted_at is None or reference_at is None:
        return "unknown"
    posted = posted_at if posted_at.tzinfo else posted_at.replace(tzinfo=UTC)
    reference = (
        reference_at if reference_at.tzinfo else reference_at.replace(tzinfo=UTC)
    )
    days = max((reference.date() - posted.date()).days, 0)
    if days <= 1:
        return "posted_today"
    if days <= 7:
        return "within_7_days"
    if days <= 30:
        return "within_30_days"
    if days <= 90:
        return "within_90_days"
    return "older"


def _salary_values(
    source: PreparedJobSourceV2,
) -> tuple[float | None, float | None, float | None]:
    currency = _norm(source.salary_currency).replace("₹", "inr")
    if currency and currency not in {"inr", "rs", "rs.", "rupee", "rupees"}:
        return None, None, None
    minimum, maximum = source.salary_min, source.salary_max
    values = [value for value in (minimum, maximum) if value is not None]
    midpoint = sum(values) / len(values) if values else None
    return minimum, maximum, midpoint


def feature_schema_document() -> dict[str, Any]:
    """Return the canonical, hashable schema manifest without artifact details."""

    contract = {
        "featureSchemaVersion": FEATURE_SCHEMA_VERSION,
        "baseNumeric": list(BASE_NUMERIC_FEATURES),
        "boolean": list(BOOLEAN_FEATURES),
        "categorical": list(CATEGORICAL_FEATURES),
        "engineered": list(ENGINEERED_FEATURES),
        "text": list(TEXT_FEATURES),
        "stackedScores": list(STACKED_SCORE_FEATURES),
        "modelInputFeatureCount": len(MODEL_INPUT_FEATURES),
        "classifierFeatureCount": len(MODEL_INPUT_FEATURES)
        + len(STACKED_SCORE_FEATURES),
        "leakagePolicy": {
            "forbiddenSources": [
                "applied",
                "apply_label",
                "manual_fit_scores",
                "relevance_label",
                "application_outcome",
            ],
            "rule": "Every base feature must be available before prediction.",
        },
    }
    encoded = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    return {**contract, "featureSchemaHash": hashlib.sha256(encoded).hexdigest()}


FEATURE_SCHEMA_HASH = feature_schema_document()["featureSchemaHash"]


def build_prepared_job_v2(
    value: PreparedJobSourceV2 | Mapping[str, Any],
) -> PreparedJobV2:
    """Build the durable V2 payload without using annotation or outcome fields."""

    source = (
        value
        if isinstance(value, PreparedJobSourceV2)
        else PreparedJobSourceV2.model_validate(value)
    )
    role = _role_family(source)
    seniority = _seniority(source)
    employment = _employment_type(source)
    work_mode = _work_mode(source)
    city, country, location_bucket, bengaluru, ncr, india = _location(source, work_mode)
    salary_min, salary_max, salary_midpoint = _salary_values(source)

    original_skills = [
        skill for skill in (_norm(item) for item in source.skills) if skill
    ]
    has_skills = bool(original_skills)
    skills = original_skills or list(
        _FALLBACK_SKILLS.get(role, ("problem solving", "communication"))
    )
    skills_imputation = "original" if has_skills else "role_based_fallback"

    is_senior = seniority in {"senior", "lead", "staff", "principal"}
    is_lead = seniority in {"lead", "staff", "principal"}
    is_intern = seniority in {"intern", "new_grad"}
    is_entry = seniority in {"entry_level", "junior"}
    is_early = is_intern or is_entry
    is_mid = seniority in {"early_mid", "mid"}
    is_backend = role in {"backend", "fullstack"}
    is_ml = role == "ml_ai"
    is_data = role in {"data_engineering", "data_science", "analytics"}
    is_devops = role == "devops_cloud"
    is_qa = role == "qa_testing"
    combined_text = _norm(
        " ".join((source.role_title, source.role_family, source.location, *skills))
    )
    is_support = _contains(
        combined_text,
        (r"annotation", r"customer support", r"content moderation", r"manual labeling"),
    )
    is_security = _contains(
        combined_text, (r"security", r"cyber", r"\biam\b", r"threat")
    )
    is_platform = _contains(
        combined_text,
        (r"platform", r"infrastructure", r"distributed systems", r"reliability"),
    )
    is_llm = is_ml or _contains(
        combined_text, (r"\bllm", r"\brag\b", r"genai", r"generative ai", r"agentic")
    )
    remote_global = location_bucket == "global_remote"
    india_remote = location_bucket == "india_remote"
    target_india = india or location_bucket in {"india_remote", "india_other"}
    bengaluru_or_ncr = bengaluru or ncr
    tier1 = bengaluru_or_ncr or city in {"hyderabad", "pune", "mumbai", "chennai"}

    experience_mismatch = source.experience_range_match is False or is_senior
    location_mismatch = (
        bool(source.preferred_locations) and not source.preferred_location_match
    )
    salary_available = salary_midpoint is not None
    low_salary = salary_available and salary_midpoint <= 800_000
    mid_salary = salary_available and 800_000 < salary_midpoint < 2_000_000
    high_salary = salary_available and salary_midpoint >= 2_000_000
    good_role = is_backend or is_ml or is_data
    bad_role = is_senior or is_support or is_qa or is_devops
    good_location = source.preferred_location_match or (
        not source.preferred_locations and target_india and not remote_global
    )
    weak_skill_match = bool(source.preferred_skills) and source.skill_overlap < 0.20
    strong_skill_match = not source.preferred_skills or source.skill_overlap >= 0.30
    strong_title_match = (
        not source.preferred_titles or source.title_token_overlap >= 0.40
    )
    mismatch_count = sum((experience_mismatch, location_mismatch, weak_skill_match))

    experience_imputed = source.experience_range_match is None
    if experience_imputed:
        experience_reason = "missing_range_signal"
    elif source.experience_range_match:
        experience_reason = "range_overlap"
    else:
        experience_reason = "range_mismatch"

    can_apply = (
        "unknown"
        if source.can_apply_now is None
        else ("yes" if source.can_apply_now else "no")
    )
    title_skill_text = " | ".join(
        item for item in (source.role_title, role, seniority, *skills) if item
    )
    context_text = " | ".join(
        item
        for item in (
            source.role_title,
            source.role_family,
            source.seniority,
            source.location,
            source.work_mode,
            source.employment_type,
            " ".join(skills),
        )
        if item
    )

    features = ModelFeaturesV2(
        experience_min_years=source.experience_min_years,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_midpoint=salary_midpoint,
        experience_profile_fit_imputed=_flag(experience_imputed),
        has_skills_or_requirements=_flag(has_skills),
        is_bengaluru=_flag(bengaluru),
        is_gurgaon_ncr=_flag(ncr),
        is_india=_flag(india),
        salary_available=_flag(salary_available),
        can_apply_now=can_apply,
        freshness=_freshness(source.posted_at, source.feature_reference_at),
        role_family_standard=role,
        seniority_standard=seniority,
        employment_type_standard=employment,
        work_mode_standard=work_mode,
        city_standard=city,
        country_standard=country,
        location_bucket=location_bucket,
        experience_min_bucket=_experience_bucket(source.experience_min_years),
        skills_imputation_type=skills_imputation,
        experience_profile_fit_imputation_reason=experience_reason,
        feat_is_experience_mismatch=_flag(experience_mismatch),
        feat_is_senior_or_above=_flag(is_senior),
        feat_is_lead_staff_principal=_flag(is_lead),
        feat_is_early_career=_flag(is_early),
        feat_is_intern_or_new_grad=_flag(is_intern),
        feat_is_entry_or_junior=_flag(is_entry),
        feat_is_mid_level=_flag(is_mid),
        feat_is_backend_or_fullstack=_flag(is_backend),
        feat_is_ml_ai=_flag(is_ml),
        feat_is_data_role=_flag(is_data),
        feat_is_devops_cloud=_flag(is_devops),
        feat_is_qa_testing=_flag(is_qa),
        feat_is_support_or_annotation=_flag(is_support),
        feat_is_security_role=_flag(is_security),
        feat_is_platform_infra=_flag(is_platform),
        feat_is_llm_or_rag_role=_flag(is_llm),
        feat_is_remote=_flag(work_mode == "remote"),
        feat_is_remote_global=_flag(remote_global),
        feat_is_india_remote=_flag(india_remote),
        feat_is_india_target_location=_flag(target_india),
        feat_is_bengaluru_or_ncr=_flag(bengaluru_or_ncr),
        feat_is_tier1_city=_flag(tier1),
        feat_is_location_mismatch=_flag(location_mismatch),
        feat_is_low_salary=_flag(low_salary),
        feat_is_mid_salary=_flag(mid_salary),
        feat_is_high_salary=_flag(high_salary),
        feat_salary_good_but_role_bad=_flag(high_salary and bad_role),
        feat_low_salary_but_good_role=_flag(low_salary and is_early and good_role),
        feat_good_role_good_location=_flag(
            good_role and good_location and not remote_global
        ),
        feat_good_title_bad_experience=_flag(
            source.title_token_overlap >= 0.40 and experience_mismatch
        ),
        feat_remote_early_career=_flag(work_mode == "remote" and is_early),
        feat_onsite_or_hybrid_early_career=_flag(
            work_mode in {"onsite", "hybrid"} and is_early
        ),
        feat_bad_fit_combo=_flag(
            mismatch_count >= 2 or (bad_role and experience_mismatch)
        ),
        feat_strong_fit_combo=_flag(
            good_role
            and good_location
            and strong_title_match
            and strong_skill_match
            and not experience_mismatch
        ),
        enhanced_title_skill_text=title_skill_text,
        enhanced_context_text=context_text,
    )
    return PreparedJobV2(
        **source.model_dump(),
        feature_schema_hash=FEATURE_SCHEMA_HASH,
        model_features=features,
    )


def build_model_features(
    rows: Iterable[PreparedJobV2 | Mapping[str, Any]],
) -> list[dict[str, float | str | None]]:
    """Validate durable rows and return model columns in canonical order."""

    output: list[dict[str, float | str | None]] = []
    job_ids: set[str] = set()
    for raw in rows:
        row = (
            raw if isinstance(raw, PreparedJobV2) else PreparedJobV2.model_validate(raw)
        )
        if row.feature_schema_hash != FEATURE_SCHEMA_HASH:
            raise ValueError(f"Feature schema hash mismatch for job {row.job_id}")
        if row.job_id in job_ids:
            raise ValueError(f"Duplicate prepared job id: {row.job_id}")
        job_ids.add(row.job_id)
        values = row.model_features.model_dump()
        if tuple(values) != MODEL_INPUT_FEATURES:
            raise ValueError(f"Feature order mismatch for job {row.job_id}")
        for name in BASE_NUMERIC_FEATURES + BOOLEAN_FEATURES + ENGINEERED_FEATURES:
            value = values[name]
            if value is not None and not math.isfinite(float(value)):
                raise ValueError(f"Non-finite feature {name} for job {row.job_id}")
        output.append({name: values[name] for name in MODEL_INPUT_FEATURES})
    if not output:
        raise ValueError("At least one prepared job is required")
    return output
