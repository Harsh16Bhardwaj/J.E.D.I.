# JEDI Score Stacking Experiment Decisions

This document records the Ridge profile-score stacking experiment.

Status note:

```text
These metrics were recorded before the salary re-estimation pass.
Rerun the notebook after salary cleanup before treating them as latest model scores.
```

## What We Tested

We tested whether predicted profile-fit scores can improve the binary `applied=yes/no` classifier.

Architecture:

```text
raw job fields
 -> Ridge regression predicts profile-fit scores
 -> predicted scores are appended as features
 -> Logistic Regression predicts applied yes/no
```

Notebook:

```text
notebooks/profile_scores/jedi_ridge_score_stacked_logistic.ipynb
```

Main exported files:

```text
data/jedi_stacked_logistic_holdout_comparison.csv
data/jedi_stacked_logistic_outer_cv_detail.csv
data/jedi_stacked_logistic_outer_cv_summary.csv
data/jedi_stacked_logistic_test_predictions.csv
data/jedi_master_with_oof_predicted_profile_scores.csv
data/jedi_stacked_ridge_score_metrics.csv
```

## Models Compared

| Model | Meaning |
|---|---|
| `raw_logistic` | baseline Logistic Regression using raw job fields only |
| `stacked_predicted_scores_logistic` | raw job fields plus Ridge-predicted profile scores |
| `oracle_true_scores_logistic` | raw job fields plus true manual scores; diagnostic upper bound only |

Oracle true scores are not deployable because new jobs will not already have manually annotated scores.

## Holdout Result

At threshold `0.50`, the stacked model did not improve hard classification.

| Model | Accuracy | F1 yes | Recall yes | ROC-AUC | Average Precision |
|---|---:|---:|---:|---:|---:|
| Raw Logistic | 0.910 | 0.885 | 0.885 | 0.940 | 0.918 |
| Stacked Logistic | 0.910 | 0.885 | 0.885 | 0.950 | 0.940 |
| Oracle Logistic | 0.910 | 0.889 | 0.923 | 0.954 | 0.940 |

Interpretation:

The stacked model improved ranking/probability metrics, but not the default yes/no decision on this split.

## Leakage-Safe Outer CV Result

Outer CV is the better comparison because it avoids trusting one split.

| Model | Accuracy Mean | F1 yes Mean | Recall yes Mean | ROC-AUC Mean | Average Precision Mean |
|---|---:|---:|---:|---:|---:|
| Raw Logistic | 0.873 | 0.830 | 0.818 | 0.923 | 0.897 |
| Stacked Logistic | 0.891 | 0.854 | 0.834 | 0.933 | 0.911 |
| Oracle Logistic | 0.903 | 0.872 | 0.865 | 0.959 | 0.943 |

Stacking improvement over raw Logistic:

```text
accuracy:          +0.018
F1 yes:            +0.025
recall yes:        +0.015
ROC-AUC:           +0.010
average precision: +0.014
```

## Decision

The stacking experiment worked, but the improvement is modest.

Keep:

```text
raw_logistic = official simple baseline
stacked_predicted_scores_logistic = best Logistic variant so far
oracle_true_scores_logistic = diagnostic ceiling only
```

Do not over-claim this as a breakthrough.

Correct interpretation:

```text
Predicted profile scores help slightly.
They are more useful for ranking than for radically improving binary classification.
```

## Why This Does Not Reach 95%

The realistic leakage-safe comparison is outer CV, not the single holdout split.

Outer-CV accuracy:

```text
raw Logistic:     0.873
stacked Logistic: 0.891
oracle Logistic:  0.903
```

This means the deployable stacked model is still roughly `6` accuracy points away from `95%`.

The important diagnostic result is the oracle model. Even when the classifier gets the true manual profile-fit scores, it reaches only about `0.903` accuracy and `0.872` F1 on the positive class. That tells us the current bottleneck is not only score prediction. The dataset itself still lacks enough variety, hard negatives, borderline positives, and stable salary signal.

Therefore:

```text
profile-score stacking can improve the model,
but it cannot turn the current dataset into a 95%-quality classifier by itself.
```

## Why The Gain Is Limited

The predicted profile scores are derived from the same raw fields already seen by Logistic Regression. They repackage the signal; they do not add new external information.

Raw Logistic was already strong, so there was not much easy improvement left.

The score model is useful but imperfect. It predicts seniority, location, and overall preference fairly well, but title/role/skills scores are noisier.

Even the oracle model improves only moderately, which means true profile scores contain useful signal but are not a complete shortcut for `applied`.

## Improvements Still Possible Within This Approach

Small improvements may be possible:

1. Use only the strongest predicted score features:

```text
pred_overall_preference_score
pred_seniority_profile_fit_score
pred_location_profile_fit_score
```

Reason: weaker predicted title/role/skills scores may add noise.

2. Tune the classifier threshold.

The default `0.50` threshold is not always optimal for application decisions.

3. Use predicted scores for ranking, not only classification.

Recommended ranking formula to test:

```text
final_rank =
0.65 * applied_probability
+ 0.35 * predicted_overall_preference_score_scaled
```

4. Calibrate probabilities.

If the output is used as a ranking or decision score, probability calibration can help.

5. Collect more borderline labels.

This remains the highest-value improvement. The model needs more cases where a job looks good but is rejected, or looks imperfect but is still worth applying.

These improvements are worth trying, but they are incremental. The next major gain should come from cleaner labels, corrected salary signal, and targeted data collection.

## Practical Next Step

Do not spend too much time squeezing this exact stack.

Next useful experiment:

```text
compare final ranking strategies
```

Specifically:

```text
applied_probability only
vs
predicted_overall_preference_score only
vs
weighted blend of both
```
