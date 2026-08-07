"""Train and export the leakage-safe embedded JEDI production bundle.

The historical dataset contains manual component scores as targets. This script
uses them only as Ridge targets; every input is rebuilt through PreparedJobV2.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import scipy
import sklearn
import xgboost
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MaxAbsScaler, OneHotEncoder
from xgboost import XGBClassifier

from backend.schemas.modeling import PreparedJobSourceV2
from backend.services.model_features import (
    BASE_NUMERIC_FEATURES,
    BOOLEAN_FEATURES,
    CATEGORICAL_FEATURES,
    ENGINEERED_FEATURES,
    FEATURE_SCHEMA_HASH,
    FEATURE_SCHEMA_VERSION,
    STACKED_SCORE_FEATURES,
    build_model_features,
    build_prepared_job_v2,
    feature_schema_document,
)

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "ML" / "data" / "final" / "jedi_final_model_dataset.csv"
CONFIG_PATH = ROOT / "ML" / "config" / "jedi_final_model_config.json"
BUNDLE_DIR = ROOT / "backend" / "model_bundles" / "jedi-ranking-v1"
MODEL_VERSION = "jedi-ranking-v1"
THRESHOLD = 0.60
RANDOM_STATE = 42
SCORE_TARGETS = [
    "role_title_preference_score",
    "role_family_preference_score",
    "seniority_profile_fit_score",
    "location_profile_fit_score",
    "work_mode_fit_score",
    "experience_profile_fit_score",
    "skills_profile_fit_score",
    "salary_profile_fit_score",
    "overall_preference_score",
]
SCORE_BOUNDS = {"salary_profile_fit_score": (0.0, 8.0)}
PROFILE = {
    "resume_text": "Python FastAPI PostgreSQL backend and ML engineer",
    "preferred_titles": [
        "backend engineer",
        "fullstack engineer",
        "machine learning engineer",
        "data engineer",
    ],
    "preferred_locations": ["bengaluru", "delhi ncr", "india", "remote"],
    "preferred_skills": [
        "python",
        "fastapi",
        "postgresql",
        "backend",
        "machine learning",
    ],
    "experience_min_years": 0.0,
    "experience_max_years": 3.0,
    "salary_min": 600_000.0,
    "salary_max": 2_000_000.0,
}


def clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def number(value: object) -> float | None:
    if pd.isna(value) or clean(value).casefold() in {"", "na", "n/a", "unknown"}:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]+", value.casefold()))


def dice(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0.0


def overlap(items: list[str], preferred: list[str]) -> float:
    actual = set().union(*(tokens(item) for item in items)) if items else set()
    wanted = set().union(*(tokens(item) for item in preferred)) if preferred else set()
    return len(actual & wanted) / len(wanted) if actual and wanted else 0.0


def ranges_overlap(
    left_min: float | None,
    left_max: float | None,
    right_min: float | None,
    right_max: float | None,
) -> bool | None:
    if (left_min is None and left_max is None) or (
        right_min is None and right_max is None
    ):
        return None
    left_low = left_min if left_min is not None else left_max
    left_high = left_max if left_max is not None else left_min
    right_low = right_min if right_min is not None else right_max
    right_high = right_max if right_max is not None else right_min
    assert None not in (left_low, left_high, right_low, right_high)
    return max(left_low, right_low) <= min(left_high, right_high)


def parse_skills(row: pd.Series) -> list[str]:
    raw = clean(row.get("skills_array"))
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [clean(item) for item in parsed if clean(item)]
        except json.JSONDecodeError:
            pass
    return [
        item.strip()
        for item in re.split(r"[;,|]", clean(row.get("skills_or_requirements")))
        if item.strip()
    ]


def source_from_row(row: pd.Series) -> PreparedJobSourceV2:
    skills = parse_skills(row)
    role_title = clean(row.get("role_title"))
    location = clean(row.get("location"))
    experience_min = number(row.get("experience_min_years"))
    experience_max = number(row.get("experience_max_years"))
    salary_min = number(row.get("salary_min"))
    salary_max = number(row.get("salary_max"))
    can_apply_text = clean(row.get("can_apply_now")).casefold()
    can_apply = (
        True if can_apply_text == "yes" else False if can_apply_text == "no" else None
    )
    preferred_location_match = any(
        preferred in location.casefold() or location.casefold() in preferred
        for preferred in PROFILE["preferred_locations"]
        if location
    )
    return PreparedJobSourceV2(
        job_id=f"training-{clean(row.get('row_id'))}",
        code=f"TRAINING-{clean(row.get('row_id'))}",
        company_name=clean(row.get("company_name")),
        company_key=clean(row.get("company_name_standard")),
        role_title=role_title,
        role_family=clean(row.get("role_family")),
        seniority=clean(row.get("seniority")),
        location=location,
        work_mode=clean(row.get("work_mode")),
        employment_type=clean(row.get("employment_type")),
        description=" ".join(
            item for item in [role_title, location, " ".join(skills)] if item
        ),
        skills=skills,
        experience_min_years=experience_min,
        experience_max_years=experience_max,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency="INR",
        can_apply_now=can_apply,
        resume_text=str(PROFILE["resume_text"]),
        preferred_titles=list(PROFILE["preferred_titles"]),
        preferred_locations=list(PROFILE["preferred_locations"]),
        preferred_skills=list(PROFILE["preferred_skills"]),
        title_token_overlap=max(
            (dice(role_title, title) for title in PROFILE["preferred_titles"]),
            default=0.0,
        ),
        skill_overlap=overlap(skills, list(PROFILE["preferred_skills"])),
        preferred_location_match=preferred_location_match,
        experience_range_match=ranges_overlap(
            experience_min,
            experience_max,
            PROFILE["experience_min_years"],
            PROFILE["experience_max_years"],
        ),
        salary_range_match=ranges_overlap(
            salary_min,
            salary_max,
            PROFILE["salary_min"],
            PROFILE["salary_max"],
        ),
        description_token_count=len(tokens(" ".join([role_title, location, *skills]))),
    )


def clip_scores(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=float).copy()
    for index, target in enumerate(SCORE_TARGETS):
        low, high = SCORE_BOUNDS.get(target, (0.0, 5.0))
        result[:, index] = np.clip(result[:, index], low, high)
    return result


def preference_score(values: np.ndarray, weights: dict[str, float]) -> np.ndarray:
    frame = pd.DataFrame(clip_scores(values), columns=SCORE_TARGETS)
    score = np.zeros(len(frame), dtype=float)
    for target, weight in weights.items():
        high = SCORE_BOUNDS.get(target, (0.0, 5.0))[1]
        score += frame[target].to_numpy() / high * float(weight)
    return np.clip(score * 100.0, 0.0, 100.0)


def append_scores(frame: pd.DataFrame, values: np.ndarray) -> pd.DataFrame:
    output = frame.copy()
    clipped = clip_scores(values)
    for index, column in enumerate(STACKED_SCORE_FEATURES):
        output[column] = clipped[:, index]
    return output


def preprocessor(extra_numeric: list[str], dropped: set[str]) -> ColumnTransformer:
    numeric = (
        list(BASE_NUMERIC_FEATURES + BOOLEAN_FEATURES)
        + [item for item in ENGINEERED_FEATURES if item not in dropped]
        + extra_numeric
    )
    return ColumnTransformer(
        [
            (
                "numeric",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", MaxAbsScaler()),
                    ]
                ),
                numeric,
            ),
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        (
                            "onehot",
                            OneHotEncoder(handle_unknown="ignore", min_frequency=3),
                        ),
                    ]
                ),
                list(CATEGORICAL_FEATURES),
            ),
            (
                "word_text",
                TfidfVectorizer(
                    ngram_range=(1, 2), min_df=2, max_features=2600, sublinear_tf=True
                ),
                "enhanced_title_skill_text",
            ),
            (
                "char_text",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    min_df=2,
                    max_features=1800,
                    sublinear_tf=True,
                ),
                "enhanced_context_text",
            ),
        ],
        remainder="drop",
    )


def score_model() -> Pipeline:
    return Pipeline(
        [("preprocess", preprocessor([], set())), ("ridge", Ridge(alpha=2.0))]
    )


def low_correlation_features(
    frame: pd.DataFrame, target: pd.Series, count: int = 5
) -> set[str]:
    rows = []
    for column in ENGINEERED_FEATURES:
        correlation = frame[column].astype(float).corr(target.astype(float))
        rows.append(
            (abs(float(correlation)) if np.isfinite(correlation) else 0.0, column)
        )
    return {column for _, column in sorted(rows)[:count]}


def classifier_model(scale_pos_weight: float, dropped: set[str]) -> Pipeline:
    return Pipeline(
        [
            ("preprocess", preprocessor(list(STACKED_SCORE_FEATURES), dropped)),
            (
                "classifier",
                XGBClassifier(
                    objective="binary:logistic",
                    eval_metric="logloss",
                    tree_method="hist",
                    random_state=RANDOM_STATE,
                    n_jobs=1,
                    scale_pos_weight=scale_pos_weight,
                    n_estimators=500,
                    max_depth=2,
                    learning_rate=0.025,
                    min_child_weight=5,
                    subsample=0.90,
                    colsample_bytree=0.90,
                    reg_alpha=0.25,
                    reg_lambda=5.0,
                ),
            ),
        ]
    )


def ranking_at_25(target: np.ndarray, score: np.ndarray) -> dict[str, float]:
    order = np.argsort(-score)
    ranked = target[order]
    top = ranked[:25]
    discounts = 1 / np.log2(np.arange(2, len(top) + 2))
    ideal = np.sort(target)[::-1][:25]
    ideal_dcg = float(np.sum(ideal * discounts[: len(ideal)]))
    return {
        "precisionAt25": float(np.mean(top)),
        "recallAt25": float(np.sum(top) / max(np.sum(target), 1)),
        "ndcgAt25": float(np.sum(top * discounts) / ideal_dcg) if ideal_dcg else 0.0,
    }


def sha256(path: Path) -> str:
    if path.suffix.casefold() == ".json":
        normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        canonical = normalized.replace(b"\n", b"\r\n")
        return hashlib.sha256(canonical).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    data = pd.read_csv(DATA_PATH)
    valid = data[SCORE_TARGETS].notna().all(axis=1) & data["applied"].notna()
    data = data.loc[valid].reset_index(drop=True)
    prepared = [
        build_prepared_job_v2(source_from_row(row)) for _, row in data.iterrows()
    ]
    x = pd.DataFrame(build_model_features(prepared))
    y_scores = data[SCORE_TARGETS].astype(float)
    y = data["applied"].astype(str).str.strip().str.casefold().map({"no": 0, "yes": 1})
    if y.isna().any():
        raise ValueError("Applied target contains values other than yes/no")
    y = y.astype(int)
    groups = data["near_duplicate_key"].fillna("").astype(str)
    groups = groups.where(groups.str.strip().ne(""), "row-" + data.index.astype(str))
    weights = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["ranking_score"][
        "weights"
    ]

    oof_probability = np.zeros(len(data), dtype=float)
    oof_preference = np.zeros(len(data), dtype=float)
    outer = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    for train_index, validation_index in outer.split(x, y, groups):
        x_train, x_validation = x.iloc[train_index], x.iloc[validation_index]
        y_train = y.iloc[train_index]
        score_train = y_scores.iloc[train_index]
        train_groups = groups.iloc[train_index]
        inner = GroupKFold(n_splits=5)
        fold_score_model = score_model()
        train_score_oof = cross_val_predict(
            fold_score_model,
            x_train,
            score_train,
            groups=train_groups,
            cv=inner,
        )
        fold_score_model.fit(x_train, score_train)
        validation_scores = clip_scores(fold_score_model.predict(x_validation))
        dropped = low_correlation_features(x_train, y_train)
        scale = float((y_train == 0).sum() / max((y_train == 1).sum(), 1))
        fold_classifier = classifier_model(scale, dropped)
        fold_classifier.fit(append_scores(x_train, train_score_oof), y_train)
        oof_probability[validation_index] = fold_classifier.predict_proba(
            append_scores(x_validation, validation_scores)
        )[:, 1]
        oof_preference[validation_index] = preference_score(validation_scores, weights)

    decision = oof_probability >= THRESHOLD
    metrics = {
        "rows": len(data),
        "rocAuc": float(roc_auc_score(y, oof_probability)),
        "averagePrecision": float(average_precision_score(y, oof_probability)),
        "threshold": THRESHOLD,
        "precisionYes": float(precision_score(y, decision)),
        "recallYes": float(recall_score(y, decision)),
        "f1Yes": float(f1_score(y, decision)),
        "jediRanking": ranking_at_25(y.to_numpy(), oof_preference),
        "probabilityRanking": ranking_at_25(y.to_numpy(), oof_probability),
        "evaluation": "StratifiedGroupKFold(5) with nested GroupKFold Ridge stacking",
    }

    inner_all = GroupKFold(n_splits=5)
    final_score_oof = cross_val_predict(
        score_model(), x, y_scores, groups=groups, cv=inner_all
    )
    final_score_model = score_model().fit(x, y_scores)
    dropped = low_correlation_features(x, y)
    scale = float((y == 0).sum() / max((y == 1).sum(), 1))
    final_classifier = classifier_model(scale, dropped).fit(
        append_scores(x, final_score_oof), y
    )

    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    score_path = BUNDLE_DIR / "preference_pipeline.joblib"
    classifier_path = BUNDLE_DIR / "classifier_pipeline.joblib"
    booster_path = BUNDLE_DIR / "classifier.ubj"
    schema_path = BUNDLE_DIR / "feature_schema.json"
    golden_input_path = BUNDLE_DIR / "golden_input.json"
    golden_output_path = BUNDLE_DIR / "golden_output.json"
    joblib.dump(final_score_model, score_path, compress=3)
    joblib.dump(final_classifier, classifier_path, compress=3)
    final_classifier.named_steps["classifier"].get_booster().save_model(booster_path)
    schema_path.write_text(
        json.dumps(feature_schema_document(), indent=2),
        encoding="utf-8",
        newline="\n",
    )

    golden = prepared[0]
    golden_frame = pd.DataFrame(build_model_features([golden]))
    golden_scores = clip_scores(final_score_model.predict(golden_frame))
    golden_probability = float(
        final_classifier.predict_proba(append_scores(golden_frame, golden_scores))[0, 1]
    )
    golden_input_path.write_text(
        json.dumps(golden.model_dump(mode="json"), indent=2),
        encoding="utf-8",
        newline="\n",
    )
    golden_output_path.write_text(
        json.dumps(
            {
                "componentScores": dict(
                    zip(SCORE_TARGETS, golden_scores[0].tolist(), strict=True)
                ),
                "jediPreferenceScore": float(
                    preference_score(golden_scores, weights)[0]
                ),
                "applyProbability": golden_probability,
            },
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )

    artifact_paths = [
        score_path,
        classifier_path,
        booster_path,
        schema_path,
        golden_input_path,
        golden_output_path,
    ]
    checksums = {path.name: sha256(path) for path in artifact_paths}
    artifact_hash = hashlib.sha256(
        json.dumps(checksums, sort_keys=True).encode()
    ).hexdigest()
    manifest = {
        "modelVersion": MODEL_VERSION,
        "artifactHash": artifact_hash,
        "featureSchemaVersion": FEATURE_SCHEMA_VERSION,
        "featureSchemaHash": FEATURE_SCHEMA_HASH,
        "requestContractVersion": "score-request-v1",
        "responseContractVersion": "score-response-v1",
        "rankingStrategy": "apply-gate-then-jedi-v1",
        "decisionThreshold": THRESHOLD,
        "scoreTargets": SCORE_TARGETS,
        "scoreWeights": weights,
        "droppedEngineeredFeatures": sorted(dropped),
        "artifacts": checksums,
        "runtime": {
            "python": ".".join(platform.python_version_tuple()[:2]),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "scikitLearn": sklearn.__version__,
            "xgboost": xgboost.__version__,
            "joblib": joblib.__version__,
        },
        "training": {
            "dataset": str(DATA_PATH.relative_to(ROOT)),
            "datasetSha256": sha256(DATA_PATH),
            "profile": PROFILE,
            "leakagePolicy": "Inputs rebuilt exclusively through PreparedJobV2",
        },
        "metrics": metrics,
    }
    (BUNDLE_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8", newline="\n"
    )
    print(json.dumps({"bundle": str(BUNDLE_DIR), "metrics": metrics}, indent=2))


if __name__ == "__main__":
    main()
