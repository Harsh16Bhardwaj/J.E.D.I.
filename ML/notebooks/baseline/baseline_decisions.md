# JEDI Baseline Modeling Decisions

This document records the baseline phase for JEDI: what we tried, what we learned, and why the next step is profile-fit score stacking.

## Current State

The prepared supervised dataset has 331 labeled jobs:

- `applied=no`: 205 rows
- `applied=yes`: 126 rows
- positive rate: about 38%

The first modeling target was binary:

```text
raw job fields -> applied yes/no
```

We intentionally excluded manually annotated fit-score columns from the classifier inputs to avoid leakage.

## Baselines Tried

| Model | Holdout F1 yes | CV F1 mean | Role |
|---|---:|---:|---|
| Logistic Regression | 0.885 | 0.830 | official interpretable baseline |
| Random Forest | 0.880 | 0.828 | tree-based comparison |
| Complement Naive Bayes | 0.840 | 0.791 | text sanity baseline |
| Gradient Boosting | 0.902 | 0.838 | current performance candidate |

Gradient boosting gave the best held-out score, but logistic regression stayed very close under cross-validation and is easier to explain.

## Smart Decisions Made

- Used clean binary `applied` as the first action target.
- Removed profile-fit score columns from classifier features to avoid target leakage.
- Dropped source columns so the model does not learn scraper/source bias.
- Used TF-IDF for text-heavy columns like title and skills.
- Used one-hot encoding for standardized low-cardinality enums.
- Used class balancing because `applied=yes` is the minority class.
- Used k-fold cross-validation instead of trusting one split.
- Kept logistic regression as the reference baseline.
- Treated gradient boosting as a candidate, not final proof.
- Stopped over-tuning weaker baselines and moved to a higher-value modeling idea.

## Why Scores Are Not Final Yet

The scores are promising but not production-final because:

- 331 rows is still small.
- `applied` is a personal-preference action label, not an objective quality label.
- Salary is saturated because most collected roles already clear the preferred threshold.
- There is limited numeric data.
- Many useful signals are text or sparse categories.
- Some role/seniority/location segments need more examples.
- Duplicate or near-duplicate jobs can leak across random splits.

## Next Decision

The next experiment should test profile-fit score stacking:

```text
raw job fields
 -> predict profile-fit scores
 -> append predicted scores
 -> predict applied yes/no
```

The key rule is that the final classifier should use **predicted** profile scores, not true manually annotated scores.

Next notebook:

```text
jedi_profile_score_stacking_experiment.ipynb
```

## Follow-Up Completed

This was completed in:

```text
notebooks/profile_scores/jedi_ridge_score_stacked_logistic.ipynb
notebooks/profile_scores/stacking_experiment_decisions.md
```

Result:

```text
score stacking improved outer-CV F1 from 0.830 to 0.854,
but did not improve the holdout hard classification result at threshold 0.50.
```

Decision:

```text
keep stacked Logistic as the best Logistic variant,
but treat predicted profile scores as more useful for ranking than for a major binary-classification jump.
```
