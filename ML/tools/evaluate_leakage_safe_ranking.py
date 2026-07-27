"""Leakage-safe ranking evaluation for the JEDI frontier model.

This script reproduces the conservative XGBoost ranking family on the current
root dataset, but uses near_duplicate_key as the cross-validation group. It
also evaluates the Ridge-derived JEDI preference score on the same folds and
adds the product-relevant @25 cutoff.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MaxAbsScaler, OneHotEncoder
from xgboost import XGBClassifier


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "jedi_final_model_dataset.csv"
CONFIG_PATH = ROOT / "jedi_final_model_config.json"
OUTPUT_DIR = ROOT / "data" / "results"
RANDOM_STATE = 42
N_SPLITS = 5
KS = (10, 20, 25, 50)

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
PRED_SCORE_COLUMNS = [f"pred_{column}" for column in SCORE_TARGETS]


def to_binary(value):
    if pd.isna(value):
        return np.nan
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return 1.0
    if text in {"false", "0", "no"}:
        return 0.0
    return np.nan


def clip_scores(values):
    values = np.asarray(values, dtype=float).copy()
    for index, target in enumerate(SCORE_TARGETS):
        low, high = SCORE_BOUNDS.get(target, (0.0, 5.0))
        values[:, index] = np.clip(values[:, index], low, high)
    return values


def ranking_rows(model, variant, fold, y_true, scores):
    frame = pd.DataFrame(
        {"target": np.asarray(y_true, dtype=int), "score": np.asarray(scores, dtype=float)}
    ).sort_values("score", ascending=False)
    total_positive = max(int(frame["target"].sum()), 1)
    rows = []
    for k in KS:
        top = frame.head(k)
        gains = top["target"].to_numpy()
        discounts = 1 / np.log2(np.arange(2, len(gains) + 2))
        dcg = float(np.sum(gains * discounts))
        ideal = np.sort(frame["target"].to_numpy())[::-1][:k]
        ideal_dcg = float(np.sum(ideal * discounts[: len(ideal)]))
        rows.append(
            {
                "model": model,
                "variant": variant,
                "fold": fold,
                "k": k,
                "precision_at_k": float(top["target"].mean()),
                "recall_at_k": float(top["target"].sum() / total_positive),
                "ndcg_at_k": dcg / ideal_dcg if ideal_dcg else 0.0,
            }
        )
    return rows


def safe_corr(feature, target):
    feature = pd.to_numeric(pd.Series(feature), errors="coerce")
    target = pd.to_numeric(pd.Series(target), errors="coerce")
    valid = feature.notna() & target.notna()
    if valid.sum() < 3 or feature[valid].nunique() <= 1:
        return 0.0
    return float(feature[valid].corr(target[valid]))


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    score_weights = config["ranking_score"]["weights"]
    data = pd.read_csv(DATA_PATH)

    data["applied_clean"] = data["applied"].astype(str).str.strip().str.lower()
    invalid_labels = sorted(set(data["applied_clean"]) - {"yes", "no"})
    if invalid_labels:
        raise ValueError(f"Invalid target labels: {invalid_labels}")
    data["target_applied"] = data["applied_clean"].map({"no": 0, "yes": 1}).astype(int)

    for column in SCORE_TARGETS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    valid = data[SCORE_TARGETS].notna().all(axis=1)
    model_df = data.loc[valid].reset_index(drop=True).copy()
    y = model_df["target_applied"].astype(int)
    y_scores = model_df[SCORE_TARGETS].astype(float)

    # Use the normalized job identity when available. Unique fallbacks ensure
    # missing group keys never collapse unrelated rows into one giant group.
    normalized_group = model_df["near_duplicate_key"].fillna("").astype(str).str.strip()
    fallback_group = "row_" + model_df.index.astype(str)
    model_df["evaluation_group"] = np.where(
        normalized_group.ne(""), "job_" + normalized_group, fallback_group
    )
    groups = model_df["evaluation_group"]

    duplicate_counts = groups.value_counts()
    repeated_groups = set(duplicate_counts[duplicate_counts > 1].index)
    duplicate_audit = model_df.loc[
        groups.isin(repeated_groups),
        [
            "evaluation_group",
            "row_id",
            "company_name",
            "role_title",
            "location",
            "applied",
            "apply_url",
            "near_duplicate_key",
        ],
    ].copy()
    duplicate_audit["group_size"] = duplicate_audit["evaluation_group"].map(duplicate_counts)
    duplicate_audit["group_has_conflicting_labels"] = duplicate_audit.groupby(
        "evaluation_group"
    )["applied"].transform("nunique").gt(1)
    duplicate_audit.to_csv(
        OUTPUT_DIR / "jedi_duplicate_group_audit.csv", index=False
    )

    all_score_columns = [
        column
        for column in model_df.columns
        if column.endswith("_score")
        or column in {"company_match_score", "overall_preference_score"}
    ]
    leakage_columns = [
        "row_id",
        "applied",
        "applied_clean",
        "target_applied",
        "preference_reason",
        "apply_url",
        "source_platform",
        "source_type",
        "scraped_at",
        "near_duplicate_key",
        "evaluation_group",
        "company_name",
        "company_name_standard",
        "role_title_standard",
    ]
    dropped_columns = set(all_score_columns + leakage_columns)
    candidate_raw_features = [
        column for column in model_df.columns if column not in dropped_columns
    ]

    engineered_features = [
        column for column in model_df.columns if column.startswith("feat_")
    ]
    base_numeric = [
        "experience_min_years",
        "salary_min",
        "salary_max",
        "salary_midpoint",
        "experience_profile_fit_imputed",
    ]
    boolean_features = [
        "has_skills_or_requirements",
        "is_bengaluru",
        "is_gurgaon_ncr",
        "is_india",
        "salary_available",
    ]
    categorical_features = [
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
    ]
    base_numeric = [column for column in base_numeric if column in model_df]
    boolean_features = [column for column in boolean_features if column in model_df]
    categorical_features = [
        column for column in categorical_features if column in model_df
    ]

    for column in base_numeric + engineered_features:
        model_df[column] = pd.to_numeric(model_df[column], errors="coerce")
    for column in boolean_features:
        model_df[column] = model_df[column].map(to_binary)
    for column in ["enhanced_title_skill_text", "enhanced_context_text"]:
        model_df[column] = model_df[column].fillna("").astype(str)

    x_base = model_df[candidate_raw_features].copy()
    x_base["enhanced_title_skill_text"] = model_df["enhanced_title_skill_text"]
    x_base["enhanced_context_text"] = model_df["enhanced_context_text"]

    def sparse_preprocess(extra_numeric=None, dropped_engineered=None):
        extra_numeric = list(extra_numeric or [])
        dropped_engineered = set(dropped_engineered or [])
        active_engineered = [
            column
            for column in engineered_features
            if column not in dropped_engineered
        ]
        numeric_columns = (
            base_numeric + boolean_features + active_engineered + extra_numeric
        )
        numeric_pipeline = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", MaxAbsScaler()),
            ]
        )
        categorical_pipeline = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="most_frequent")),
                (
                    "onehot",
                    OneHotEncoder(handle_unknown="ignore", min_frequency=3),
                ),
            ]
        )
        return ColumnTransformer(
            [
                ("numeric", numeric_pipeline, numeric_columns),
                ("categorical", categorical_pipeline, categorical_features),
                (
                    "word_text",
                    TfidfVectorizer(
                        analyzer="word",
                        ngram_range=(1, 2),
                        min_df=2,
                        max_features=2600,
                        sublinear_tf=True,
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

    def make_score_model():
        return Pipeline(
            [
                ("preprocess", sparse_preprocess()),
                ("ridge", Ridge(alpha=2.0)),
            ]
        )

    def append_predicted_scores(frame, predictions):
        output = frame.copy()
        predictions = clip_scores(predictions)
        for index, target in enumerate(SCORE_TARGETS):
            output[f"pred_{target}"] = predictions[:, index]
        return output

    def jedi_preference_score(predictions):
        prediction_frame = pd.DataFrame(
            clip_scores(predictions), columns=SCORE_TARGETS
        )
        weighted = np.zeros(len(prediction_frame), dtype=float)
        for target, weight in score_weights.items():
            upper_bound = SCORE_BOUNDS.get(target, (0.0, 5.0))[1]
            weighted += (
                prediction_frame[target].to_numpy() / upper_bound
            ) * float(weight)
        return np.clip(weighted * 100.0, 0.0, 100.0)

    outer_cv = StratifiedGroupKFold(
        n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE
    )
    ranking_detail = []
    classification_detail = []
    fold_audit_rows = []
    prediction_frames = []

    for fold, (train_index, validation_index) in enumerate(
        outer_cv.split(x_base, y, groups), start=1
    ):
        x_train = x_base.iloc[train_index].copy()
        x_validation = x_base.iloc[validation_index].copy()
        y_train = y.iloc[train_index].copy()
        y_validation = y.iloc[validation_index].copy()
        score_train = y_scores.iloc[train_index].copy()
        train_groups = groups.iloc[train_index]
        validation_groups = groups.iloc[validation_index]

        overlap = set(train_groups).intersection(set(validation_groups))
        fold_audit_rows.append(
            {
                "fold": fold,
                "train_rows": len(train_index),
                "validation_rows": len(validation_index),
                "train_groups": train_groups.nunique(),
                "validation_groups": validation_groups.nunique(),
                "group_overlap_count": len(overlap),
                "validation_positive_rate": float(y_validation.mean()),
            }
        )
        if overlap:
            raise RuntimeError(f"Group leakage found in fold {fold}: {sorted(overlap)}")

        inner_cv = GroupKFold(n_splits=N_SPLITS)
        score_model = make_score_model()
        train_score_oof = clip_scores(
            cross_val_predict(
                score_model,
                x_train,
                score_train,
                cv=inner_cv,
                groups=train_groups,
                n_jobs=None,
            )
        )
        score_model.fit(x_train, score_train)
        validation_score_predictions = clip_scores(
            score_model.predict(x_validation)
        )

        x_train_stacked = append_predicted_scores(x_train, train_score_oof)
        x_validation_stacked = append_predicted_scores(
            x_validation, validation_score_predictions
        )
        preference_scores = jedi_preference_score(validation_score_predictions)
        ranking_detail.extend(
            ranking_rows(
                "ridge_weighted_preference",
                "jedi_preference_score",
                fold,
                y_validation,
                preference_scores,
            )
        )

        fold_predictions = model_df.iloc[validation_index][
            [
                "row_id",
                "company_name",
                "role_title",
                "applied",
                "evaluation_group",
            ]
        ].copy()
        fold_predictions["fold"] = fold
        fold_predictions["actual_applied"] = y_validation.to_numpy()
        fold_predictions["jedi_preference_score"] = preference_scores

        correlation_rows = [
            {
                "feature": column,
                "abs_corr": abs(safe_corr(x_train[column], y_train)),
            }
            for column in engineered_features
            if column in x_train
        ]
        correlation_frame = pd.DataFrame(correlation_rows).sort_values(
            ["abs_corr", "feature"]
        )
        scale_pos_weight = float(
            (y_train == 0).sum() / max((y_train == 1).sum(), 1)
        )

        for drop_count in (0, 5, 20):
            dropped_engineered = correlation_frame.head(drop_count)[
                "feature"
            ].tolist()
            for mode in ("raw", "stacked"):
                if mode == "raw":
                    train_frame = x_train
                    validation_frame = x_validation
                    extra_numeric = []
                else:
                    train_frame = x_train_stacked
                    validation_frame = x_validation_stacked
                    extra_numeric = PRED_SCORE_COLUMNS

                estimator = Pipeline(
                    [
                        (
                            "preprocess",
                            sparse_preprocess(
                                extra_numeric=extra_numeric,
                                dropped_engineered=dropped_engineered,
                            ),
                        ),
                        (
                            "classifier",
                            XGBClassifier(
                                objective="binary:logistic",
                                eval_metric="logloss",
                                tree_method="hist",
                                random_state=RANDOM_STATE,
                                n_jobs=4,
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
                estimator.fit(train_frame, y_train)
                probability = estimator.predict_proba(validation_frame)[:, 1]
                variant = f"{mode}_drop{drop_count}"
                ranking_detail.extend(
                    ranking_rows(
                        "xgb_conservative",
                        variant,
                        fold,
                        y_validation,
                        probability,
                    )
                )
                classification_detail.append(
                    {
                        "model": "xgb_conservative",
                        "variant": variant,
                        "fold": fold,
                        "roc_auc": roc_auc_score(y_validation, probability),
                        "average_precision": average_precision_score(
                            y_validation, probability
                        ),
                    }
                )
                fold_predictions[f"{variant}_apply_probability"] = probability

        prediction_frames.append(fold_predictions)

    ranking_detail = pd.DataFrame(ranking_detail)
    ranking_summary = (
        ranking_detail.groupby(["model", "variant", "k"])[
            ["precision_at_k", "recall_at_k", "ndcg_at_k"]
        ]
        .agg(["mean", "std"])
        .reset_index()
    )
    ranking_summary.columns = [
        "_".join(part for part in column if part)
        if isinstance(column, tuple)
        else column
        for column in ranking_summary.columns
    ]
    ranking_summary = ranking_summary.sort_values(
        ["k", "ndcg_at_k_mean", "precision_at_k_mean"],
        ascending=[True, False, False],
    )

    classification_detail = pd.DataFrame(classification_detail)
    classification_summary = (
        classification_detail.groupby(["model", "variant"])[
            ["roc_auc", "average_precision"]
        ]
        .agg(["mean", "std"])
        .reset_index()
    )
    classification_summary.columns = [
        "_".join(part for part in column if part)
        if isinstance(column, tuple)
        else column
        for column in classification_summary.columns
    ]

    fold_audit = pd.DataFrame(fold_audit_rows)
    predictions = pd.concat(prediction_frames).sort_values(
        ["fold", "row_id"]
    )

    ranking_detail.to_csv(
        OUTPUT_DIR / "jedi_leakage_safe_ranking_detail.csv", index=False
    )
    ranking_summary.to_csv(
        OUTPUT_DIR / "jedi_leakage_safe_ranking_summary.csv", index=False
    )
    classification_summary.to_csv(
        OUTPUT_DIR / "jedi_leakage_safe_classifier_summary.csv", index=False
    )
    fold_audit.to_csv(
        OUTPUT_DIR / "jedi_leakage_safe_fold_audit.csv", index=False
    )
    predictions.to_csv(
        OUTPUT_DIR / "jedi_leakage_safe_oof_predictions.csv", index=False
    )

    schema = {
        "dataset": str(DATA_PATH),
        "rows": len(model_df),
        "target": "applied -> target_applied (yes=1, no=0)",
        "group_key": "near_duplicate_key with a unique row fallback",
        "excluded_leakage_columns": sorted(leakage_columns),
        "base_numeric": base_numeric,
        "boolean": boolean_features,
        "categorical": categorical_features,
        "engineered": engineered_features,
        "text": {
            "enhanced_title_skill_text": "word TF-IDF, 1-2 grams, max 2600",
            "enhanced_context_text": "character TF-IDF, 3-5 grams, max 1800",
        },
        "optional_stacked_scores": PRED_SCORE_COLUMNS,
        "model": "xgb_conservative",
        "evaluation": {
            "outer_cv": "StratifiedGroupKFold(5)",
            "inner_score_cv": "GroupKFold(5)",
            "ranking_cutoffs": list(KS),
        },
    }
    (OUTPUT_DIR / "jedi_frontier_feature_schema.json").write_text(
        json.dumps(schema, indent=2), encoding="utf-8"
    )

    print("\nDuplicate audit")
    print(
        f"Repeated groups: {len(repeated_groups)}; "
        f"rows in repeated groups: {len(duplicate_audit)}; "
        f"conflicting groups: "
        f"{duplicate_audit.loc[duplicate_audit['group_has_conflicting_labels'], 'evaluation_group'].nunique()}"
    )
    print("\nFold leakage audit")
    print(fold_audit.to_string(index=False))
    print("\nLeakage-safe ranking @25")
    print(
        ranking_summary.loc[ranking_summary["k"] == 25]
        .head(10)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
