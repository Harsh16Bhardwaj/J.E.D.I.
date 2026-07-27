# XGBoost Error Audit Report

Date: 2026-06-29

Source:

```text
data/jedi_xgboost_stacked_oof_predictions.csv
data/jedi_xgboost_error_audit.csv
```

## Summary

The previous XGBoost stacked run produced:

| Error type | Rows |
|---|---:|
| false_positive | 33 |
| false_negative | 30 |
| oracle_only_error | 6 |

High-confidence errors:

| high_confidence_error, error_type | Rows |
|---|---:|
| 0, false_negative | 18 |
| 0, false_positive | 20 |
| 0, oracle_only_error | 5 |
| 1, false_negative | 12 |
| 1, false_positive | 13 |
| 1, oracle_only_error | 1 |

## Main Issue Buckets

| Likely issue | Rows |
|---|---:|
| oracle_error_label_or_feature_contradiction | 31 |
| high_confidence_oracle_error_label_or_feature_contradiction | 25 |
| ambiguous_or_model_boundary | 7 |
| accepted_despite_visible_penalty | 3 |
| label_may_be_stricter_than_visible_features | 2 |
| high_confidence_accepted_despite_visible_penalty | 1 |

## What This Means

The mistakes are not random.

The model often fails on rows where the visible features contradict the label:

- A row looks like an obvious yes but is labeled no.
- A row looks like an obvious no but is labeled yes.
- Even the oracle model fails, meaning true manual scores still do not fully explain the final label.

This is a data/label-definition issue more than an algorithm issue.

## False Positive Pattern

False positives are rows labeled `no`, but the model predicts `yes`.

Common flags:

| Issue flags | Rows |
|---|---:|
| good_role_good_location;strong_fit_combo | 24 |
| low_salary;good_role_good_location;strong_fit_combo | 8 |
| support_or_annotation;low_salary;good_role_good_location;strong_fit_combo | 1 |
| qa_testing;low_salary | 1 |
| devops_cloud | 1 |

Interpretation:

Many false positives look like good early-career rows from the visible fields. If they are truly `no`, the reason is probably hidden in `preference_reason`, skills nuance, company quality, or personal taste that is not encoded as a clean feature.

High-confidence false-positive examples:

| row_id | company | role | issue |
|---:|---|---|---|
| 461 | TerraPay | SDE I - Backend Platform - Data Products | looks like strong fit but labeled no |
| 410 | Mercari India | SDE I - Backend Platform - Core Platform | looks like strong fit but labeled no |
| 463 | Delta Exchange | Frontend Engineer Intern - Data Products | likely hidden reason not captured |
| 316 | Origin | CVAT Annotation Intern | annotation/support role must be penalized harder |
| 280 | Anaplan | Associate DevOps Engineer | DevOps should be a clearer rejection signal |
| 265 | Xsolla | Junior QA Engineer | QA/testing should be a clearer rejection signal |

## False Negative Pattern

False negatives are rows labeled `yes`, but the model predicts `no`.

Common flags:

| Issue flags | Rows |
|---|---:|
| experience_mismatch;good_role_good_location | 9 |
| experience_mismatch;good_role_good_location;good_title_bad_experience | 5 |
| experience_mismatch | 3 |
| experience_mismatch;senior_or_above;salary_good_but_role_bad;good_role_good_location;good_title_bad_experience | 3 |

Interpretation:

Many false negatives are rows where you accepted a job despite a visible penalty, usually experience/seniority. The model sees the penalty and rejects it.

High-confidence false-negative examples:

| row_id | company | role | issue |
|---:|---|---|---|
| 533 | Veeam India | Data Engineer - Python + Spark - Internal Tools | accepted despite experience mismatch |
| 532 | Gyrus.AI | AI Application Engineer - Internal Tools | accepted despite experience mismatch |
| 601 | Dobbe AI | Junior Platform Engineer | accepted despite devops/low-salary penalty |
| 50 | ClickHouse | Core Software Engineer (C++) - Remote | accepted despite senior/experience penalty |
| 48 | Definitive Healthcare India | Senior Software Engineer | accepted despite senior/experience penalty |
| 307 | SIRPI Products and Services | Frontend Developer | accepted despite low salary |

## Column/Feature Issues Found

The current columns still miss some important decision reasons:

1. `role_family` is too broad for rejection reasons.
   - Example: `AI Data / ML Ops`, `QA / Test`, and `DevOps / Platform` need stronger explicit flags.

2. `skills_profile_fit_score` does not fully encode bad skill direction.
   - Kubernetes/DevOps, annotation, QA, and support need separate flags.

3. `experience_profile_fit_score` was missing for 131 rows.
   - This is now fixed in `jedi_modeling_enhanced_dataset.csv`.

4. `overall_preference_score` does not explain all `applied` decisions.
   - Some rows with strong-looking scores are still labeled no, and some weak-looking rows are labeled yes.

5. `preference_reason` contains useful hidden logic but is excluded from training.
   - That is correct for avoiding leakage, but the useful parts should be converted into clean features.

## Action

The enhanced dataset now adds explicit feature columns for these cases:

```text
feat_is_experience_mismatch
feat_is_senior_or_above
feat_is_support_or_annotation
feat_is_qa_testing
feat_is_devops_cloud
feat_is_remote_global
feat_salary_good_but_role_bad
feat_good_title_bad_experience
feat_strong_fit_combo
```

Next notebook:

```text
notebooks/profile_scores/jedi_enhanced_ridge_xgboost_kfold.ipynb
```

This notebook should be rerun before judging the final result.
