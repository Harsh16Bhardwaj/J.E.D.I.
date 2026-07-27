const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const NOTEBOOK_PATH = path.join(ROOT, "notebooks", "profile_scores", "jedi_enhanced_ridge_xgboost_kfold.ipynb");

function md(source) {
  return {
    cell_type: "markdown",
    metadata: {},
    source: source.split("\n").map((line, idx, arr) => idx === arr.length - 1 ? line : `${line}\n`),
  };
}

function code(source) {
  return {
    cell_type: "code",
    execution_count: null,
    metadata: {},
    outputs: [],
    source: source.split("\n").map((line, idx, arr) => idx === arr.length - 1 ? line : `${line}\n`),
  };
}

const cells = [
  md(`# JEDI Enhanced Ridge -> XGBoost K-Fold Workbook

**Input:** \`jedi_modeling_enhanced_dataset.csv\`

**Changes from previous notebook:**

- uses all 691 rows after fixing \`experience_profile_fit_score\`
- adds explicit rule features
- drops weak engineered features inside each fold
- uses word TF-IDF plus character TF-IDF
- reports classification and ranking metrics`),

  md(`## Step 0: Imports And Paths`),

  code(`from pathlib import Path
import warnings

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    mean_absolute_error,
    precision_score,
    recall_score,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

try:
    from xgboost import XGBClassifier
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "xgboost is not installed in this kernel. Run '%pip install xgboost', restart the kernel, then rerun."
    ) from exc

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 180)
pd.set_option("display.max_colwidth", 140)

RANDOM_STATE = 42
N_SPLITS = 5
DROP_LOW_CORR_COUNT = 20


def find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "jedi_modeling_enhanced_dataset.csv").exists():
            return candidate
    raise FileNotFoundError("Could not find jedi_modeling_enhanced_dataset.csv.")


PROJECT_ROOT = find_project_root(Path.cwd())
DATA_PATH = PROJECT_ROOT / "jedi_modeling_enhanced_dataset.csv"
OUTPUT_DIR = PROJECT_ROOT / "data"

print(PROJECT_ROOT)
print(DATA_PATH)`),

  md(`## Step 1: Load Enhanced Dataset`),

  code(`df = pd.read_csv(DATA_PATH)

print("Rows: {:,}".format(len(df)))
print("Columns: {:,}".format(df.shape[1]))
display(df.head(3))
display(df["applied"].value_counts().rename_axis("applied").reset_index(name="rows"))

if "experience_profile_fit_score" not in df.columns:
    raise ValueError("Enhanced dataset missing experience_profile_fit_score")

print("Experience score NA rows:", df["experience_profile_fit_score"].isna().sum())`),

  md(`## Step 2: Targets`),

  code(`SCORE_TARGETS = [
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

df["applied_clean"] = df["applied"].astype(str).str.strip().str.lower()
bad_labels = sorted(set(df["applied_clean"]) - {"yes", "no"})
if bad_labels:
    raise ValueError("Invalid applied labels: {}".format(bad_labels))

df["target_applied"] = df["applied_clean"].map({"no": 0, "yes": 1}).astype(int)

for col in SCORE_TARGETS:
    df[col] = pd.to_numeric(df[col], errors="coerce")

valid_rows = df["target_applied"].notna() & df[SCORE_TARGETS].notna().all(axis=1)
if valid_rows.sum() != len(df):
    print("Rows dropped due to missing target values:", len(df) - valid_rows.sum())

model_df = df.loc[valid_rows].reset_index(drop=True).copy()
y_applied = model_df["target_applied"].astype(int)
y_scores = model_df[SCORE_TARGETS].astype(float)

display(pd.DataFrame({
    "target": SCORE_TARGETS,
    "min": [y_scores[c].min() for c in SCORE_TARGETS],
    "max": [y_scores[c].max() for c in SCORE_TARGETS],
    "mean": [y_scores[c].mean() for c in SCORE_TARGETS],
    "missing": [y_scores[c].isna().sum() for c in SCORE_TARGETS],
}))
display(y_applied.value_counts().rename_axis("target_applied").reset_index(name="rows"))`),

  md(`## Step 3: Leakage-Free Features`),

  code(`ALL_SCORE_COLUMNS = [
    c for c in model_df.columns
    if c.endswith("_score") or c in ["company_match_score", "overall_preference_score"]
]

LEAKAGE_OR_METADATA_COLUMNS = [
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
    "company_name",
    "company_name_standard",
    "role_title_standard",
]

drop_columns = sorted(set(ALL_SCORE_COLUMNS + LEAKAGE_OR_METADATA_COLUMNS))
available_drop_columns = [c for c in drop_columns if c in model_df.columns]
candidate_raw_features = [c for c in model_df.columns if c not in available_drop_columns]

meta_columns = [
    "row_id",
    "company_name",
    "role_title",
    "role_family",
    "seniority",
    "location",
    "applied",
    "source_type",
    "preference_reason",
]
meta = model_df[[c for c in meta_columns if c in model_df.columns]].copy()

display(pd.DataFrame({"dropped_from_training_X": available_drop_columns}))
display(pd.DataFrame({"candidate_raw_feature": candidate_raw_features}))`),

  md(`## Step 4: Feature Groups And Text Fields`),

  code(`engineered_feature_columns = [c for c in model_df.columns if c.startswith("feat_")]

base_numeric_features = [
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

base_numeric_features = [c for c in base_numeric_features if c in model_df.columns]
boolean_features = [c for c in boolean_features if c in model_df.columns]
categorical_features = [c for c in categorical_features if c in model_df.columns]

for col in base_numeric_features + engineered_feature_columns:
    model_df[col] = pd.to_numeric(model_df[col], errors="coerce")


def to_binary(value):
    if pd.isna(value):
        return np.nan
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return 1.0
    if text in {"false", "0", "no"}:
        return 0.0
    return np.nan


for col in boolean_features:
    model_df[col] = model_df[col].map(to_binary)

for col in ["enhanced_title_skill_text", "enhanced_context_text"]:
    if col not in model_df.columns:
        model_df[col] = ""
    model_df[col] = model_df[col].fillna("").astype(str)

X_raw = model_df[candidate_raw_features].copy()
X_raw["enhanced_title_skill_text"] = model_df["enhanced_title_skill_text"]
X_raw["enhanced_context_text"] = model_df["enhanced_context_text"]

display(pd.DataFrame({
    "group": ["base_numeric", "boolean", "categorical", "engineered"],
    "count": [
        len(base_numeric_features),
        len(boolean_features),
        len(categorical_features),
        len(engineered_feature_columns),
    ],
    "columns": [
        ", ".join(base_numeric_features),
        ", ".join(boolean_features),
        ", ".join(categorical_features),
        ", ".join(engineered_feature_columns),
    ],
}))`),

  md(`## Step 5: Correlation-Based Feature Drop Functions`),

  code(`def safe_corr(x, y):
    x = pd.to_numeric(pd.Series(x), errors="coerce")
    y = pd.to_numeric(pd.Series(y), errors="coerce")
    valid = x.notna() & y.notna()
    if valid.sum() < 3:
        return 0.0
    if x[valid].nunique() <= 1:
        return 0.0
    return float(x[valid].corr(y[valid]))


def select_low_correlation_features(X_train, y_train, candidate_cols, drop_count=20):
    rows = []
    for col in candidate_cols:
        if col not in X_train.columns:
            continue
        corr = safe_corr(X_train[col], y_train)
        rows.append({
            "feature": col,
            "correlation": corr,
            "abs_correlation": abs(corr),
            "non_null": int(pd.Series(X_train[col]).notna().sum()),
        })
    corr_df = pd.DataFrame(rows).sort_values(["abs_correlation", "feature"]).reset_index(drop=True)
    drop_features = corr_df.head(min(drop_count, len(corr_df)))["feature"].tolist()
    return drop_features, corr_df


global_drop_features, global_corr_df = select_low_correlation_features(
    X_raw,
    y_applied,
    engineered_feature_columns,
    drop_count=DROP_LOW_CORR_COUNT,
)

display(global_corr_df.sort_values("abs_correlation", ascending=False).head(20))
display(global_corr_df.head(DROP_LOW_CORR_COUNT))`),

  md(`## Step 6: Pipelines With Better NLP`),

  code(`def make_preprocess(extra_numeric_features=None, dropped_engineered_features=None):
    extra_numeric_features = list(extra_numeric_features or [])
    dropped_engineered_features = set(dropped_engineered_features or [])

    active_engineered = [c for c in engineered_feature_columns if c not in dropped_engineered_features]
    numeric_cols = base_numeric_features + boolean_features + active_engineered + extra_numeric_features

    numeric_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    categorical_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=3)),
    ])

    title_skill_word = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        min_df=2,
        max_features=2600,
        sublinear_tf=True,
    )

    context_char = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=2,
        max_features=1800,
        sublinear_tf=True,
    )

    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_transformer, numeric_cols),
            ("categorical", categorical_transformer, categorical_features),
            ("title_skill_word", title_skill_word, "enhanced_title_skill_text"),
            ("context_char", context_char, "enhanced_context_text"),
        ],
        remainder="drop",
    )


def make_score_model(alpha=2.0):
    return Pipeline(steps=[
        ("preprocess", make_preprocess(dropped_engineered_features=[])),
        ("regressor", Ridge(alpha=alpha)),
    ])


def make_xgb_model(extra_numeric_features=None, dropped_engineered_features=None, scale_pos_weight=1.0):
    return Pipeline(steps=[
        ("preprocess", make_preprocess(
            extra_numeric_features=extra_numeric_features,
            dropped_engineered_features=dropped_engineered_features,
        )),
        ("classifier", XGBClassifier(
            n_estimators=450,
            max_depth=3,
            learning_rate=0.03,
            min_child_weight=4,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_alpha=0.15,
            reg_lambda=3.5,
            objective="binary:logistic",
            eval_metric="logloss",
            tree_method="hist",
            random_state=RANDOM_STATE,
            n_jobs=4,
            scale_pos_weight=scale_pos_weight,
        )),
    ])


SCORE_BOUNDS = {"salary_profile_fit_score": (0.0, 8.0)}


def clip_scores(predictions):
    predictions = np.asarray(predictions, dtype=float).copy()
    for idx, target in enumerate(SCORE_TARGETS):
        low, high = SCORE_BOUNDS.get(target, (0.0, 5.0))
        predictions[:, idx] = np.clip(predictions[:, idx], low, high)
    return predictions


PRED_SCORE_COLUMNS = ["pred_" + c for c in SCORE_TARGETS]
TRUE_SCORE_COLUMNS = ["true_" + c for c in SCORE_TARGETS]


def append_score_columns(X_base, score_array, prefix):
    X_aug = X_base.copy()
    score_array = clip_scores(score_array)
    for idx, score_name in enumerate(SCORE_TARGETS):
        X_aug[prefix + "_" + score_name] = score_array[:, idx]
    return X_aug`),

  md(`## Step 7: Metrics`),

  code(`def regression_metrics(y_true, y_pred, split_name, fold=None):
    y_true_df = pd.DataFrame(np.asarray(y_true, dtype=float), columns=SCORE_TARGETS)
    y_pred_df = pd.DataFrame(clip_scores(y_pred), columns=SCORE_TARGETS)
    rows = []
    for target in SCORE_TARGETS:
        actual = y_true_df[target]
        pred = y_pred_df[target]
        abs_error = (pred - actual).abs()
        rows.append({
            "fold": fold,
            "split": split_name,
            "target": target,
            "mae": mean_absolute_error(actual, pred),
            "rmse": np.sqrt(np.mean(np.square(pred - actual))),
            "r2": r2_score(actual, pred),
            "spearman": actual.corr(pred, method="spearman"),
            "within_0_5": (abs_error <= 0.5).mean(),
            "within_1_0": (abs_error <= 1.0).mean(),
        })
    return pd.DataFrame(rows)


def classification_summary(model_name, fold, y_true, proba, threshold=0.50):
    proba = np.asarray(proba, dtype=float)
    pred = (proba >= threshold).astype(int)
    return {
        "model": model_name,
        "fold": fold,
        "threshold": threshold,
        "accuracy": accuracy_score(y_true, pred),
        "balanced_accuracy": balanced_accuracy_score(y_true, pred),
        "precision_yes": precision_score(y_true, pred, zero_division=0),
        "recall_yes": recall_score(y_true, pred, zero_division=0),
        "f1_yes": f1_score(y_true, pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, proba),
        "average_precision": average_precision_score(y_true, proba),
        "log_loss": log_loss(y_true, proba, labels=[0, 1]),
        "brier_score": brier_score_loss(y_true, proba),
        "predicted_yes_count": int(pred.sum()),
    }


def ranking_summary(model_name, y_true, proba, ks=(10, 20, 50)):
    frame = pd.DataFrame({"y": np.asarray(y_true), "p": np.asarray(proba)})
    frame = frame.sort_values("p", ascending=False).reset_index(drop=True)
    rows = []
    total_pos = max(int(frame["y"].sum()), 1)
    for k in ks:
        top = frame.head(k)
        precision_at_k = top["y"].mean()
        recall_at_k = top["y"].sum() / total_pos
        gains = top["y"].values
        discounts = 1 / np.log2(np.arange(2, len(gains) + 2))
        dcg = float(np.sum(gains * discounts))
        ideal_gains = np.sort(frame["y"].values)[::-1][:k]
        ideal_dcg = float(np.sum(ideal_gains * discounts[:len(ideal_gains)]))
        rows.append({
            "model": model_name,
            "k": k,
            "precision_at_k": precision_at_k,
            "recall_at_k": recall_at_k,
            "ndcg_at_k": dcg / ideal_dcg if ideal_dcg else 0.0,
        })
    return pd.DataFrame(rows)


def threshold_table(y_true, proba, model_name):
    rows = []
    for threshold in np.arange(0.20, 0.81, 0.05):
        pred = (np.asarray(proba) >= threshold).astype(int)
        rows.append({
            "model": model_name,
            "threshold": round(float(threshold), 2),
            "predicted_yes_count": int(pred.sum()),
            "precision_yes": precision_score(y_true, pred, zero_division=0),
            "recall_yes": recall_score(y_true, pred, zero_division=0),
            "f1_yes": f1_score(y_true, pred, zero_division=0),
            "balanced_accuracy": balanced_accuracy_score(y_true, pred),
        })
    return pd.DataFrame(rows)`),

  md(`## Step 8: Leakage-Safe K-Fold`),

  code(`def run_enhanced_stacked_xgb_cv():
    outer_cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    inner_cv = KFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)

    classification_rows = []
    regression_rows = []
    prediction_frames = []
    fold_drop_rows = []

    for fold_idx, (train_idx, val_idx) in enumerate(outer_cv.split(X_raw, y_applied), start=1):
        X_tr_raw = X_raw.iloc[train_idx].copy()
        X_val_raw = X_raw.iloc[val_idx].copy()
        y_tr = y_applied.iloc[train_idx].copy()
        y_val = y_applied.iloc[val_idx].copy()
        y_tr_scores = y_scores.iloc[train_idx].copy()
        y_val_scores = y_scores.iloc[val_idx].copy()

        dropped_features, fold_corr = select_low_correlation_features(
            X_tr_raw,
            y_tr,
            engineered_feature_columns,
            drop_count=DROP_LOW_CORR_COUNT,
        )
        for _, row in fold_corr.iterrows():
            fold_drop_rows.append({
                "fold": fold_idx,
                "feature": row["feature"],
                "correlation": row["correlation"],
                "abs_correlation": row["abs_correlation"],
                "dropped": row["feature"] in dropped_features,
            })

        scale_pos_weight = float((y_tr == 0).sum() / max((y_tr == 1).sum(), 1))

        fold_score_model = make_score_model(alpha=2.0)
        train_score_oof = cross_val_predict(
            fold_score_model,
            X_tr_raw,
            y_tr_scores,
            cv=inner_cv,
            n_jobs=None,
        )
        train_score_oof = clip_scores(train_score_oof)
        fold_score_model.fit(X_tr_raw, y_tr_scores)
        val_score_pred = clip_scores(fold_score_model.predict(X_val_raw))

        regression_rows.append(regression_metrics(y_tr_scores, train_score_oof, "train_inner_oof", fold=fold_idx))
        regression_rows.append(regression_metrics(y_val_scores, val_score_pred, "outer_validation", fold=fold_idx))

        X_tr_stacked = append_score_columns(X_tr_raw, train_score_oof, prefix="pred")
        X_val_stacked = append_score_columns(X_val_raw, val_score_pred, prefix="pred")
        X_tr_oracle = append_score_columns(X_tr_raw, y_tr_scores.values, prefix="true")
        X_val_oracle = append_score_columns(X_val_raw, y_val_scores.values, prefix="true")

        fold_configs = [
            ("raw_enhanced_xgboost", make_xgb_model(dropped_engineered_features=dropped_features, scale_pos_weight=scale_pos_weight), X_tr_raw, X_val_raw),
            ("stacked_ridge_scores_enhanced_xgboost", make_xgb_model(PRED_SCORE_COLUMNS, dropped_engineered_features=dropped_features, scale_pos_weight=scale_pos_weight), X_tr_stacked, X_val_stacked),
            ("oracle_true_scores_enhanced_xgboost", make_xgb_model(TRUE_SCORE_COLUMNS, dropped_engineered_features=dropped_features, scale_pos_weight=scale_pos_weight), X_tr_oracle, X_val_oracle),
        ]

        fold_predictions = meta.iloc[val_idx].reset_index(drop=True).copy()
        fold_predictions["fold"] = fold_idx
        fold_predictions["actual_applied"] = y_val.reset_index(drop=True).values

        for target_idx, target in enumerate(SCORE_TARGETS):
            fold_predictions["true_" + target] = y_val_scores.reset_index(drop=True)[target]
            fold_predictions["pred_" + target] = val_score_pred[:, target_idx]

        for model_name, estimator, X_tr, X_val in fold_configs:
            estimator.fit(X_tr, y_tr)
            proba = estimator.predict_proba(X_val)[:, 1]
            classification_rows.append(classification_summary(model_name, fold_idx, y_val, proba, threshold=0.50))
            fold_predictions[model_name + "_probability"] = proba
            fold_predictions[model_name + "_prediction"] = (proba >= 0.50).astype(int)

        prediction_frames.append(fold_predictions)

    return (
        pd.DataFrame(classification_rows),
        pd.concat(regression_rows, ignore_index=True),
        pd.concat(prediction_frames, ignore_index=True).sort_values(["fold", "row_id"]).reset_index(drop=True),
        pd.DataFrame(fold_drop_rows),
    )


cv_detail, score_cv_detail, oof_predictions, fold_feature_correlations = run_enhanced_stacked_xgb_cv()

display(cv_detail)
display(score_cv_detail.head(20))
display(fold_feature_correlations.head(20))
display(oof_predictions.head(10))`),

  md(`## Step 9: Aggregate Results`),

  code(`metric_columns = [
    "accuracy",
    "balanced_accuracy",
    "precision_yes",
    "recall_yes",
    "f1_yes",
    "roc_auc",
    "average_precision",
    "log_loss",
    "brier_score",
    "predicted_yes_count",
]

cv_summary = cv_detail.groupby("model")[metric_columns].agg(["mean", "std"])
flat_cv_summary = cv_summary.copy()
flat_cv_summary.columns = [metric + "_" + stat for metric, stat in flat_cv_summary.columns]
flat_cv_summary = flat_cv_summary.reset_index().sort_values("f1_yes_mean", ascending=False)

display(cv_summary)
display(flat_cv_summary)

score_cv_summary = (
    score_cv_detail
    .groupby(["split", "target"])[["mae", "rmse", "r2", "spearman", "within_0_5", "within_1_0"]]
    .agg(["mean", "std"])
)
display(score_cv_summary)`),

  md(`## Step 10: Threshold And Ranking Metrics`),

  code(`threshold_review = pd.concat([
    threshold_table(oof_predictions["actual_applied"], oof_predictions[model + "_probability"], model)
    for model in [
        "raw_enhanced_xgboost",
        "stacked_ridge_scores_enhanced_xgboost",
        "oracle_true_scores_enhanced_xgboost",
    ]
], ignore_index=True)

ranking_review = pd.concat([
    ranking_summary(model, oof_predictions["actual_applied"], oof_predictions[model + "_probability"])
    for model in [
        "raw_enhanced_xgboost",
        "stacked_ridge_scores_enhanced_xgboost",
        "oracle_true_scores_enhanced_xgboost",
    ]
], ignore_index=True)

display(threshold_review.sort_values(["model", "f1_yes"], ascending=[True, False]).groupby("model").head(5))
display(ranking_review)`),

  md(`## Step 11: Save Artifacts`),

  code(`cv_detail_path = OUTPUT_DIR / "jedi_enhanced_xgboost_outer_cv_detail.csv"
cv_summary_path = OUTPUT_DIR / "jedi_enhanced_xgboost_outer_cv_summary.csv"
score_cv_detail_path = OUTPUT_DIR / "jedi_enhanced_xgboost_ridge_score_cv_detail.csv"
oof_predictions_path = OUTPUT_DIR / "jedi_enhanced_xgboost_oof_predictions.csv"
threshold_review_path = OUTPUT_DIR / "jedi_enhanced_xgboost_threshold_review.csv"
ranking_review_path = OUTPUT_DIR / "jedi_enhanced_xgboost_ranking_review.csv"
fold_feature_corr_path = OUTPUT_DIR / "jedi_enhanced_xgboost_fold_feature_correlations.csv"

cv_detail.to_csv(cv_detail_path, index=False)
flat_cv_summary.to_csv(cv_summary_path, index=False)
score_cv_detail.to_csv(score_cv_detail_path, index=False)
oof_predictions.to_csv(oof_predictions_path, index=False)
threshold_review.to_csv(threshold_review_path, index=False)
ranking_review.to_csv(ranking_review_path, index=False)
fold_feature_correlations.to_csv(fold_feature_corr_path, index=False)

display(pd.DataFrame({
    "artifact": [
        "cv_detail",
        "cv_summary",
        "ridge_score_cv_detail",
        "oof_predictions",
        "threshold_review",
        "ranking_review",
        "fold_feature_correlations",
    ],
    "path": [
        str(cv_detail_path),
        str(cv_summary_path),
        str(score_cv_detail_path),
        str(oof_predictions_path),
        str(threshold_review_path),
        str(ranking_review_path),
        str(fold_feature_corr_path),
    ],
}))`),

  md(`## Step 12: Readout`),

  code(`best_model = flat_cv_summary.iloc[0]["model"]
best_f1 = flat_cv_summary.iloc[0]["f1_yes_mean"]
best_auc = flat_cv_summary.iloc[0]["roc_auc_mean"]

print("Best CV model by F1_yes:", best_model)
print("F1_yes mean: {:.4f}".format(best_f1))
print("ROC-AUC mean: {:.4f}".format(best_auc))

display(
    oof_predictions
    .sort_values("stacked_ridge_scores_enhanced_xgboost_probability", ascending=False)
    .head(25)
    [[
        "row_id",
        "company_name",
        "role_title",
        "actual_applied",
        "stacked_ridge_scores_enhanced_xgboost_probability",
        "raw_enhanced_xgboost_probability",
        "oracle_true_scores_enhanced_xgboost_probability",
    ] + ["pred_" + c for c in SCORE_TARGETS]]
)`),
];

const notebook = {
  cells,
  metadata: {
    kernelspec: { display_name: "Python 3", language: "python", name: "python3" },
    language_info: {
      codemirror_mode: { name: "ipython", version: 3 },
      file_extension: ".py",
      mimetype: "text/x-python",
      name: "python",
      nbconvert_exporter: "python",
      pygments_lexer: "ipython3",
      version: "3.12",
    },
  },
  nbformat: 4,
  nbformat_minor: 5,
};

fs.writeFileSync(NOTEBOOK_PATH, `${JSON.stringify(notebook, null, 1)}\n`, "utf8");
console.log(JSON.stringify({
  notebook: path.relative(ROOT, NOTEBOOK_PATH),
  cells: cells.length,
}, null, 2));
