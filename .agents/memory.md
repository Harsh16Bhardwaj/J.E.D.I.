# JEDI Agent Memory

Last updated: 2026-06-29

This file is the handoff memory for future agents working in `D:\ML\JEDI`.

## Project Identity

JEDI means **Job Evaluation & Delivery Intelligence**.

The project is a job personalization and screening system. The goal is not merely binary classification. The real product need is:

1. ingest scraped/manual job data,
2. normalize it into a stable schema,
3. predict personal fit scores,
4. compute a decimal ranking score,
5. use a classifier probability as a guardrail,
6. show the best jobs for review/application.

The user wants this to be portfolio-worthy and personally useful.

## Current Clean Root

The root is intentionally clean. Keep it that way.

Root project-facing artifacts:

```txt
jedi_final_model_workbook.ipynb
jedi_final_model_dataset.csv
jedi_final_model_config.json
JEDI_MODELING_JOURNEY.md
```

Do not move these unless explicitly asked.

## Final Dataset

Primary final dataset:

```txt
jedi_final_model_dataset.csv
data/final/jedi_final_model_dataset.csv
```

Current size:

```txt
691 rows
90 columns
```

Important prepared features include:

```txt
skills_array
role_family_standard
seniority_standard
employment_type_standard
work_mode_standard
city_standard
country_standard
location_bucket
is_bengaluru
is_gurgaon_ncr
is_india
salary_midpoint
salary_available
near_duplicate_key
experience_profile_fit_imputed
feat_* explicit features
enhanced_title_skill_text
enhanced_context_text
```

The dataset has repaired experience profile fit values. Earlier notebooks silently dropped 131 rows because `experience_profile_fit_score` was missing. That was fixed before the final dataset.

## Final Folder Organization

Curated final files:

```txt
data/final/
data/results/
```

Historical and support files:

```txt
data/experiments/      old model outputs
data/audits/           audits, correlation files, error analysis
data/intermediate/     master labeled/prepared CSVs and salary notes
data/supplements/      incoming extra training data
notebooks/baseline/    baseline notebooks
notebooks/eda/         EDA/bias audit notebook
notebooks/profile_scores/
notebooks/experiments/ old root experiment notebooks
docs/                  older decision and audit docs
screener/              local CSV/XLSX annotation UI
tools/                 data prep and cleaning scripts
tools/archive/         old notebook generator
```

## Best Final Results

Curated result files:

```txt
data/results/jedi_final_boosting_experiment_summary.csv
data/results/jedi_final_boosting_threshold_best.csv
data/results/jedi_final_boosting_ranking_summary.csv
data/results/jedi_enhanced_xgboost_outer_cv_summary.csv
```

Best default-threshold classifier:

```txt
Model: xgb_balanced
Variant: stacked_drop20
Accuracy: 87.70%
Precision: 85.79%
Recall: 86.56%
F1 yes: 86.13%
ROC-AUC: 93.20%
PR-AUC: 90.33%
```

Best tuned-threshold operating point:

```txt
Model: xgb_deeper
Variant: stacked_drop20
Threshold: 0.35
Precision: 84.89%
Recall: 89.84%
F1 yes: 87.26%
Balanced accuracy: 88.57%
```

Best ranking result:

```txt
Precision@50: 90.80%
Recall@50: 74.43%
NDCG@50: 0.9244
```

Important correction: an earlier `threshold_best.csv` was inflated because it selected the best threshold from a single fold. This was corrected to aggregate thresholds across folds.

## Final Modeling Decision

The final system should not use `Applied` as the only output.

Final product output should be:

```txt
predicted fit scores
JEDI preference score
apply probability
apply recommendation
```

Reason: if 50 jobs are scraped daily, many may be apply-worthy. The product still needs to sort them and surface the best 25.

## Final Modeling Flow

The final notebook implements this cleanly:

```txt
jedi_final_model_workbook.ipynb
```

Flow:

1. Load `jedi_final_model_dataset.csv`.
2. Read saved final metrics from `data/results/`.
3. Define score targets.
4. Drop leakage columns and handwritten preference scores from raw classifier inputs.
5. Train Ridge regression to predict fit-score columns.
6. Compute `jedi_preference_score` as weighted sum of predicted fit scores.
7. Train stacked XGBoost using normal job features plus predicted fit scores.
8. Use XGBoost probability as apply-worthy guardrail.
9. Save scored jobs to `data/final/jedi_final_scored_training_jobs.csv` when run.

## Final Score Formula

`jedi_preference_score` is a 0-100 decimal ranking score.

Weights:

```txt
role_title_preference_score:     0.18
role_family_preference_score:    0.12
skills_profile_fit_score:        0.18
experience_profile_fit_score:    0.14
location_profile_fit_score:      0.12
work_mode_fit_score:             0.07
salary_profile_fit_score:        0.07
seniority_profile_fit_score:     0.05
overall_preference_score:        0.07
```

Salary score is normalized from a 0-8 scale. Other fit scores are normalized from a 0-5 scale.

The binary classifier should not be the main score. It is the guardrail.

Recommended card outputs:

```txt
JEDI Score: 84.2 / 100
Apply Probability: 0.87
Decision: Strong Match
Predicted role fit, skills fit, experience fit, salary fit, location fit
```

## Columns To Treat Carefully

Do not train directly on these as raw features:

```txt
applied
target_applied
preference_reason
apply_url
source_platform
source_type
scraped_at
near_duplicate_key
company_name
company_name_standard
role_title_standard
handwritten *_score columns
company_match_score
overall_preference_score
```

Preference scores are targets first. Predicted scores may be appended into the stacked classifier.

## Historical Modeling Notes

What was tried:

```txt
Logistic Regression baseline
Random Forest
Naive Bayes
Gradient Boosting
Ridge regression for profile scores
Ridge stacked into Logistic Regression
Ridge stacked into XGBoost
Enhanced XGBoost with explicit features and better NLP
Final boosting experiments with stronger XGBoost, SVD boosting, and threshold tuning
```

CatBoost was included in the final experiment notebook, but it did not run because the environment reported:

```txt
catboost available: False
```

XGBoost plateaued. Further parameter tuning is unlikely to create a major jump without better data or embeddings.

## User Preferences And Decisions

The user prefers:

```txt
onsite/hybrid early-career roles over fully remote roles
Bengaluru and Gurgaon/NCR signals
early-career, intern, fresher, SDE-1 style opportunities
role/experience/location/skills fit above salary
salary still matters but is not the top factor
```

Salary fit logic:

```txt
4-6 LPA: very low
6-8 LPA: low
8-10 LPA: okay
10-12 LPA: good
12-25 LPA: strong
25-40 LPA: very strong
40-50 LPA: excellent
50+ LPA: exceptional
```

The user accepted that many salary values are imputed. Do not over-trust salary as a predictor.

## Deployment Direction

Recommended architecture:

```txt
Scrapers / manual imports
  -> normalizer
  -> database raw_jobs + normalized_jobs
  -> model scoring service
  -> ranked job board UI
  -> annotation feedback loop
  -> scheduled retraining
```

The model service should expose something like:

```txt
POST /score-jobs
input: normalized job records
output: predicted fit scores, jedi_preference_score, apply_probability, recommendation
```

Store every prediction with model version.

## Continuous Learning Direction

If the user gets around 150 new jobs per week:

1. Score all incoming jobs.
2. User reviews top jobs and annotates:
   - applied yes/no,
   - corrected fit scores when needed,
   - optional reason.
3. Store annotations separately from raw scraped data.
4. Retrain on a schedule, preferably weekly or every 300-500 newly labeled rows.
5. Compare new model against current production model on a fixed holdout set.
6. Promote only if ranking metrics improve or stay stable without hurting F1 badly.

Use model versions:

```txt
model_v1
model_v2
model_v3
```

Keep a fixed validation set so the model does not fool us with random fluctuations.

## Next Best Technical Step

Create a production scorer script or service from the final notebook:

```txt
src/train.py
src/score.py
src/features.py
models/
```

Artifacts to save:

```txt
models/score_model_ridge.joblib
models/apply_classifier_xgboost.joblib
models/feature_config.json
```

Then build the pipeline:

```txt
new jobs CSV/DB rows
  -> normalize
  -> score.py
  -> ranked output table
  -> UI review
```

## Important Caution

Do not delete exploratory folders unless explicitly asked. They are no longer root-facing, but they contain the history behind the final notebook.

Do not claim the model is 95% accurate. The honest story is:

```txt
binary classification plateaued around 86-87% F1
ranking quality is strong enough for the product use case
Precision@50 around 90.8% is the strongest current product metric
```
