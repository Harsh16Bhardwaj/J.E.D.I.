# XGBoost Stacked Results Interpretation

Date: 2026-06-29

Notebook reviewed:

```text
notebooks/profile_scores/jedi_ridge_xgboost_stacked_kfold copy.ipynb
```

## Critical Data Note

The notebook loaded `691` rows, but trained/evaluated on only `560` rows.

Reason:

```text
131 rows have experience_profile_fit_score = NA
```

Those rows are all from `source_type = unknown`.

Dropped-label mix:

| applied | rows |
|---|---:|
| no | 114 |
| yes | 17 |

This means the current result is not yet the final result for the full merged dataset.

## Main CV Result

| Model | Accuracy | F1 yes | ROC-AUC | Average Precision |
|---|---:|---:|---:|---:|
| raw_xgboost | 0.8875 | 0.8920 | 0.9377 | 0.9332 |
| stacked_ridge_scores_xgboost | 0.8875 | 0.8917 | 0.9455 | 0.9436 |
| oracle_true_scores_xgboost | 0.9000 | 0.9053 | 0.9482 | 0.9456 |

## Interpretation

Stacking helped ranking/probability quality, but not hard yes/no classification.

Evidence:

```text
raw_xgboost errors:     63
stacked_xgboost errors: 63
oracle_xgboost errors:  56
```

The stacked model improved ROC-AUC and average precision, but its F1 was basically the same as raw XGBoost.

The oracle model is the important ceiling check. Even when XGBoost receives the true manual score columns, it only improves from `63` errors to `56` errors. That means score prediction is not the main bottleneck.

## Ridge Score Model Quality

Ridge predicted most score columns well.

Strong score targets:

| target | outer-CV MAE | outer-CV R2 |
|---|---:|---:|
| experience_profile_fit_score | 0.188 | 0.959 |
| seniority_profile_fit_score | 0.210 | 0.939 |
| location_profile_fit_score | 0.267 | 0.855 |
| salary_profile_fit_score | 0.484 | 0.857 |
| overall_preference_score | 0.493 | 0.837 |

Weakest target:

| target | outer-CV MAE | outer-CV R2 |
|---|---:|---:|
| role_title_preference_score | 0.386 | 0.616 |

So the score model is not terrible. The issue is that predicted scores mostly repackage what XGBoost already learns from raw fields.

## Threshold Review

The best threshold for stacked XGBoost was around `0.40-0.45`, not `0.50`.

Best stacked threshold result:

```text
threshold = 0.40
precision_yes = 0.879
recall_yes = 0.910
F1_yes = 0.894
```

This is only a small improvement over the default threshold.

## What This Means

This is not a losing battle.

The model already separates positives and negatives fairly well:

```text
mean probability for true yes = 0.840
mean probability for true no  = 0.163
```

But it still has hard contradictions:

```text
false positives = 33
false negatives = 30
high-confidence errors = 25
```

High-confidence errors usually mean at least one of these:

1. the label is inconsistent
2. the feature text is missing a reason for rejection
3. the model sees a pattern that usually means yes/no but this row is an exception
4. subjective preference changed across annotation batches

## Next Actions

1. Fix `experience_profile_fit_score = NA` for the 131 dropped rows.
2. Rerun this notebook on all 691 rows.
3. Add GroupKFold by `near_duplicate_key` for a harsher generalization check.
4. Stop optimizing only accuracy/F1; add ranking metrics:

```text
precision@10
precision@20
recall@20
NDCG@20
```

5. Audit high-confidence errors manually.
6. Train with curated rows, but validate separately on real verified rows.
7. Add better features for eligibility and rejection reasons:

```text
is_experience_mismatch
is_senior_or_lead
is_low_salary
is_role_family_mismatch
is_location_mismatch
is_remote_global
is_support_or_annotation
is_intern_or_new_grad
```

## Practical Decision

The classifier is probably good enough to become a ranker.

For the actual JEDI workflow, the important question is not:

```text
Can the model classify every row perfectly?
```

The useful question is:

```text
If 50 jobs arrive, can it push the best 10-20 jobs to the top?
```

That is the next metric target.
