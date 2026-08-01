from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas.modeling import PreparedJobSourceV2, PreparedJobV2
from backend.services.model_features import (
    BASE_NUMERIC_FEATURES,
    BOOLEAN_FEATURES,
    CATEGORICAL_FEATURES,
    ENGINEERED_FEATURES,
    FEATURE_SCHEMA_HASH,
    MODEL_INPUT_FEATURES,
    STACKED_SCORE_FEATURES,
    TEXT_FEATURES,
    build_model_features,
    build_prepared_job_v2,
    feature_schema_document,
)
from backend.services.model_runtime import model_runtime


def source_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "job_id": "job-1",
        "code": "ACME-BACKEND-1",
        "company_name": "Acme",
        "company_key": "acme",
        "role_title": "Backend Engineer Intern",
        "role_family": "Backend / Cloud",
        "seniority": "Intern",
        "location": "Bengaluru, India",
        "work_mode": "Hybrid",
        "employment_type": "Internship",
        "description": "Build FastAPI services.",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "experience_min_years": 0.0,
        "experience_max_years": 1.0,
        "salary_min": 600_000.0,
        "salary_max": 800_000.0,
        "salary_currency": "INR",
        "can_apply_now": True,
        "posted_at": datetime(2026, 7, 29, tzinfo=UTC),
        "feature_reference_at": datetime(2026, 8, 1, tzinfo=UTC),
        "resume_text": "Python backend engineer",
        "preferred_titles": ["backend engineer"],
        "preferred_locations": ["bengaluru", "remote"],
        "preferred_skills": ["python", "fastapi"],
        "title_token_overlap": 0.8,
        "skill_overlap": 1.0,
        "preferred_location_match": True,
        "experience_range_match": True,
        "salary_range_match": True,
        "description_token_count": 4,
    }
    values.update(overrides)
    return values


def test_contract_has_only_inference_available_features() -> None:
    document = feature_schema_document()

    assert len(BASE_NUMERIC_FEATURES) == 5
    assert len(BOOLEAN_FEATURES) == 5
    assert len(CATEGORICAL_FEATURES) == 12
    assert len(ENGINEERED_FEATURES) == 34
    assert len(TEXT_FEATURES) == 2
    assert len(MODEL_INPUT_FEATURES) == 58
    assert len(STACKED_SCORE_FEATURES) == 9
    assert document["modelInputFeatureCount"] == 58
    assert document["classifierFeatureCount"] == 67
    assert document["featureSchemaHash"] == FEATURE_SCHEMA_HASH

    forbidden = {
        "applied",
        "apply_label",
        "role_title_preference_score",
        "seniority_profile_fit_score",
        "location_profile_fit_score",
        "experience_profile_fit_score",
        "salary_profile_fit_score",
        "overall_preference_score",
    }
    assert forbidden.isdisjoint(MODEL_INPUT_FEATURES)


def test_builder_is_deterministic_and_produces_expected_semantics() -> None:
    first = build_prepared_job_v2(source_values())
    second = build_prepared_job_v2(source_values())

    assert first == second
    assert first.feature_schema_version == "prepared-job-v2"
    assert first.feature_schema_hash == FEATURE_SCHEMA_HASH
    features = first.model_features
    assert features.role_family_standard == "backend"
    assert features.seniority_standard == "intern"
    assert features.work_mode_standard == "hybrid"
    assert features.employment_type_standard == "internship"
    assert features.location_bucket == "bengaluru"
    assert features.freshness == "within_7_days"
    assert features.salary_midpoint == 700_000.0
    assert features.feat_is_early_career == 1.0
    assert features.feat_is_backend_or_fullstack == 1.0
    assert features.feat_is_experience_mismatch == 0.0
    assert features.feat_strong_fit_combo == 1.0
    assert "fastapi" in features.enhanced_title_skill_text


def test_missing_values_have_explicit_non_label_fallbacks() -> None:
    prepared = build_prepared_job_v2(
        source_values(
            skills=[],
            salary_min=None,
            salary_max=None,
            salary_currency="",
            posted_at=None,
            can_apply_now=None,
            experience_range_match=None,
            preferred_skills=[],
        )
    )
    features = prepared.model_features

    assert features.has_skills_or_requirements == 0.0
    assert features.skills_imputation_type == "role_based_fallback"
    assert features.salary_available == 0.0
    assert features.salary_midpoint is None
    assert features.feat_is_low_salary == 0.0
    assert features.freshness == "unknown"
    assert features.can_apply_now == "unknown"
    assert features.experience_profile_fit_imputed == 1.0
    assert features.experience_profile_fit_imputation_reason == "missing_range_signal"


def test_foreign_currency_is_not_compared_to_inr_salary_bands() -> None:
    prepared = build_prepared_job_v2(
        source_values(salary_min=100_000, salary_max=120_000, salary_currency="USD")
    )

    assert prepared.model_features.salary_min is None
    assert prepared.model_features.salary_max is None
    assert prepared.model_features.salary_midpoint is None
    assert prepared.model_features.salary_available == 0.0


def test_exact_contract_rejects_manual_labels_and_invalid_ranges() -> None:
    with pytest.raises(ValidationError, match="applied"):
        PreparedJobSourceV2.model_validate({**source_values(), "applied": "yes"})

    with pytest.raises(ValidationError, match="experience minimum"):
        PreparedJobSourceV2.model_validate(
            source_values(experience_min_years=4, experience_max_years=2)
        )


def test_model_feature_rows_are_ordered_and_batch_ids_are_unique() -> None:
    first = build_prepared_job_v2(source_values())
    second = build_prepared_job_v2(source_values(job_id="job-2", code="ACME-BACKEND-2"))
    output = build_model_features([first, second])

    assert len(output) == 2
    assert tuple(output[0]) == MODEL_INPUT_FEATURES

    with pytest.raises(ValueError, match="Duplicate prepared job id"):
        build_model_features([first, first])


def test_model_feature_rows_reject_contract_hash_drift() -> None:
    prepared = build_prepared_job_v2(source_values())
    payload = prepared.model_dump()
    payload["feature_schema_hash"] = "0" * 64

    with pytest.raises(ValueError, match="Feature schema hash mismatch"):
        build_model_features([payload])


def test_model_feature_rows_do_not_mutate_prepared_payloads() -> None:
    prepared = build_prepared_job_v2(source_values()).model_dump()
    before = deepcopy(prepared)

    build_model_features([prepared])

    assert prepared == before


def test_embedded_bundle_passes_golden_and_reuses_warm_runtime() -> None:
    bundle_path = Path(__file__).parents[1] / "model_bundles" / "jedi-ranking-v1"
    prepared = PreparedJobV2.model_validate_json(
        (bundle_path / "golden_input.json").read_text(encoding="utf-8")
    )
    model_runtime.reset_for_tests()
    first = model_runtime.score(
        [prepared],
        batch_id="batch",
        processing_run_id="run-1",
        model_version_id="model",
    )
    second = model_runtime.score(
        [prepared],
        batch_id="batch",
        processing_run_id="run-2",
        model_version_id="model",
    )

    assert first.cold_start is True
    assert second.cold_start is False
    assert first.results[0].model_dump(exclude={"rank"}) == second.results[
        0
    ].model_dump(exclude={"rank"})
    assert model_runtime.health().ready is True
