# JEDI Score Stacking Experiment Report

Date: 2026-06-29

Status note:

```text
These metrics document the score-stacking run completed before the salary re-estimation pass.
After the salary cleanup, rerun the notebook before treating these as the latest current-model scores.
```

## Experiment

We tested a two-stage model:

```text
raw job fields
 -> Ridge Regression predicts profile-fit scores
 -> predicted scores are appended as model features
 -> Logistic Regression predicts applied yes/no
```

The goal was to check whether predicted personal-fit scores improve the final application decision model.

## Models Compared

| Model | Purpose |
|---|---|
| Raw Logistic | baseline classifier using raw job fields only |
| Stacked Logistic | classifier using raw fields plus Ridge-predicted fit scores |
| Oracle Logistic | diagnostic model using true manual fit scores |

The oracle model is not deployable. It exists only to estimate the best-case value of the profile-fit score columns.

## Results

### Holdout Result

| Model | Accuracy | F1 yes | Recall yes | ROC-AUC | Average Precision |
|---|---:|---:|---:|---:|---:|
| Raw Logistic | 0.910 | 0.885 | 0.885 | 0.940 | 0.918 |
| Stacked Logistic | 0.910 | 0.885 | 0.885 | 0.950 | 0.940 |
| Oracle Logistic | 0.910 | 0.889 | 0.923 | 0.954 | 0.940 |

### Leakage-Safe Outer CV Result

| Model | Accuracy | F1 yes | Recall yes | ROC-AUC | Average Precision |
|---|---:|---:|---:|---:|---:|
| Raw Logistic | 0.873 | 0.830 | 0.818 | 0.923 | 0.897 |
| Stacked Logistic | 0.891 | 0.854 | 0.834 | 0.933 | 0.911 |
| Oracle Logistic | 0.903 | 0.872 | 0.865 | 0.959 | 0.943 |

## Decision

Score stacking is useful, but not enough.

It improved outer-CV F1 from `0.830` to `0.854`, and improved ranking metrics as well. But it did not materially change the single holdout hard classification at threshold `0.50`.

The key finding is the oracle result. Even with true manual scores, the model reaches only about `0.903` outer-CV accuracy. That means the current limitation is not just the score-prediction stage. The dataset needs more coverage, more hard examples, and cleaner feature signal.

## Why This Is Not Good Enough Yet

- The dataset has only `331` labeled rows.
- Many rows are good jobs, so the model sees fewer true bad-fit examples.
- Salary was previously over-smoothed by median-style imputation.
- Several attractive-but-wrong cases are underrepresented.
- The predicted fit scores are derived from the same raw fields, so they mostly repackage existing signal.
- The target label is personal preference, not an objective ground truth.

## Keep

- Keep Logistic Regression as the interpretable baseline.
- Keep stacked Logistic as the best Logistic variant so far.
- Keep oracle Logistic only as a diagnostic upper bound.
- Use predicted scores for ranking experiments, not as a promised accuracy breakthrough.

## Next Step

Improve the dataset first:

```text
1. correct salary imputation
2. add more low-salary and borderline rows
3. add attractive hard negatives
4. add early-career positives across locations and role families
5. rerun baselines and stacking after the data update
```
