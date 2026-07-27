# JEDI Data Decisions

Date: 2026-06-27

This file records modeling-prep decisions after the first 250 fully annotated jobs and the EDA pass.

## Current Dataset State

- Annotated rows: `250`
- Target column: `applied`
- Target is now clean binary:
  - `yes`: `64`
  - `no`: `186`
  - positive rate: `25.6%`
- This is usable for a first baseline, but the positive class is still thin.

## Target Label Decision

`applied` is the predictor/target column for the first supervised model.

Allowed values:

```text
yes
no
```

No other status text should be stored in `applied`.

Application availability belongs in:

```text
can_apply_now
```

Reason:

The model should learn whether I want to apply, not whether the application page exists.

## Fields To Exclude From Training

Drop or ignore these during model training:

```text
source_platform
source_type
scraped_at
apply_url
preference_reason
```

Reason:

- `source_platform` and `source_type` can create source shortcuts.
- `scraped_at` is operational metadata.
- `apply_url` is an identifier and leakage risk.
- `preference_reason` is written after evaluation and may leak the target decision.

Keep these fields in the dataset for audit/debugging, but exclude them from model features.

## Experience Decision

Use:

```text
experience_min_years
```

Ignore for now:

```text
experience_max_years
```

Reason:

`experience_max_years` is too sparse and less important for fit. Minimum required experience is a good enough signal for fresher/entry-level filtering.

Derived feature:

```text
experience_min_bucket
```

Suggested buckets:

```text
0
1
2
3
4_plus
unknown
```

## Skills / Requirements Decision

Do not impute missing `skills_or_requirements` by mode.

Reason:

Mode imputation would repeat the most common skill text and create fake evidence. It would make many unrelated jobs look artificially similar.

Keep raw field:

```text
skills_or_requirements
```

Add normalized derived fields:

```text
skills_array
has_skills_or_requirements
skills_imputation_type
```

`skills_array` should be an array/list of normalized skills:

```text
["python", "sql", "fastapi", "react"]
```

`has_skills_or_requirements`:

```text
true
false
```

`skills_imputation_type`:

```text
original
role_based_fallback
missing
```

For missing skills, create a conservative role-based fallback in a separate derived field. Do not overwrite raw `skills_or_requirements`.

Example:

```text
role_family=backend, seniority=entry_level
skills_array=["api development", "databases", "git", "debugging", "backend fundamentals"]
skills_imputation_type=role_based_fallback
```

Reason:

The model can use the fallback, but it can also learn that the fallback was inferred and lower-confidence.

## Role Family Normalization

Create:

```text
role_family_standard
```

Allowed enum values:

```text
backend
frontend
fullstack
ml_ai
data_science
data_engineering
devops_cloud
qa_testing
product_engineering
analytics
other
unknown
```

Reason:

The raw role family field has too many variants, such as `Backend / Fullstack`, `Fullstack / AI`, and `AI Engineering`. The model needs stable categories.

## Seniority Normalization

Create:

```text
seniority_standard
```

Allowed enum values:

```text
intern
new_grad
entry_level
junior
early_mid
mid
senior
lead
staff
principal
unknown
```

Reason:

Seniority is one of the strongest real preference signals. The raw field is fragmented and must be normalized before modeling.

## Employment Type Normalization

Create:

```text
employment_type_standard
```

Allowed enum values:

```text
full_time
internship
contract
part_time
freelance
apprenticeship
temporary
unknown
```

Nothing else should be allowed in the normalized field.

Reason:

The raw field currently has variants like `Full-time`, `full_time`, `Full time`, `Full-time [Remote]`, and even work-mode-like values such as `Remote`. These must map into one stable enum.

## Work Mode Decision

Create:

```text
work_mode_standard
```

Allowed enum values:

```text
onsite
hybrid
remote
flexible
unknown
```

Preference interpretation:

- Onsite and hybrid are valuable early in career for networking, mentorship, and workplace exposure.
- Remote is not automatically bad, but many remote roles are senior/global and can be a hidden mismatch.

Do not let work mode dominate the model alone. It should be interpreted with seniority and location.

## Location Normalization

Create:

```text
city_standard
country_standard
location_bucket
```

Also create one-hot / boolean features:

```text
is_bengaluru
is_gurgaon_ncr
is_india
```

`is_gurgaon_ncr` should include:

```text
Gurgaon
Gurugram
Noida
Delhi
New Delhi
Faridabad
Delhi NCR
NCR
```

Suggested `location_bucket` enum:

```text
bengaluru
delhi_ncr
hyderabad
pune
mumbai
chennai
india_remote
india_other
global_remote
us
europe
other
unknown
```

Reason:

Raw location mixes city, country, office mode, and source-specific strings. One-hot location flags help the model learn practical geographic preference without overfitting every raw city string.

## Salary Decision

Salary is useful, but not the most important factor.

Keep:

```text
salary_min
salary_max
salary_profile_fit_score
```

Add:

```text
salary_midpoint
salary_available
```

Reason:

EDA showed salary score did not align strongly with `applied`, partly because salary scoring needs cleanup and scale consistency. Salary should influence decisions, but not overpower experience, role, location, and skill fit.

## Score Priority Decision

Expected importance for early models:

1. experience / seniority fit
2. overall preference score
3. role title and role family fit
4. location fit
5. skills fit
6. salary fit
7. work mode fit

Reason:

Experience fit and overall preference had the strongest alignment with `applied`. Role should matter slightly more than the current correlation suggests because role-title fit is central to job targeting. Location is also important because early-career onsite/hybrid opportunities are strategically valuable.

## Duplicate Decision

Before model training:

1. Deduplicate exact duplicate `apply_url`.
2. If exact duplicates differ in annotations, keep the row with the most complete fields and latest manual annotation.
3. Create a near-duplicate key:

```text
company_name_standard + role_title_standard + location_bucket
```

4. During train/test split, group by exact `apply_url` or near-duplicate key to prevent leakage.

Reason:

Duplicate jobs in both train and validation can make the model look better than it is.

## What We Are Not Acting On Yet

No immediate action on the fifth EDA point beyond keeping the note.

Reason:

The current signal is enough for planning, but it does not require a data mutation right now.

## Next Annotation Batch: 70-80 Jobs

Goal:

Increase positive examples and improve coverage of strategically important early-career categories.

Current target balance:

```text
yes = 64
no = 186
positive_rate = 25.6%
```

Recommended next batch:

```text
70-80 total jobs
50-55 likely-positive candidates
15-20 controlled negatives
5-10 ambiguous/borderline jobs
```

If 50 of the next 80 become `yes`, the dataset becomes:

```text
yes = 114
total = 330
positive_rate = 34.5%
```

This is much healthier for a first model.

### Priority Categories To Add

Focus on:

```text
intern
new_grad
entry_level
junior
SDE I
0-2 years
1-2 years
```

Role families:

```text
backend
frontend
fullstack
ml_ai entry-level
data_engineering entry-level
devops_cloud junior
```

Locations:

```text
Bengaluru
Delhi NCR / Gurgaon / Noida / Delhi / Faridabad
Hyderabad
Pune
India remote only if early-career friendly
```

Work mode:

```text
onsite
hybrid
remote only when clearly entry-level or exceptionally relevant
```

### Controlled Negative Examples

Still include some negatives, but choose useful negatives:

```text
senior backend roles
staff / lead roles
remote global roles requiring 4+ years
AI roles with strong title match but senior requirements
jobs with great salary but poor experience fit
```

Reason:

The model needs to learn why attractive-looking jobs can still be bad fits.

## Additional Attention Needed

Before semi-supervised learning, create a cleaning/prep notebook that:

1. validates binary target labels
2. normalizes enums
3. creates location flags
4. creates `skills_array`
5. adds missingness indicators
6. deduplicates or groups duplicates
7. exports a modeling-ready dataset

Only after that should we train the first baseline and then consider pseudo-labeling.

## Prepared Dataset Artifact

Final merged datasets:

```text
data/jedi_master_labeled.csv
data/jedi_master_prepared.csv
```

Repeatable preparation script:

```text
tools/prepare_modeling_dataset.ps1
```

Applied transformations:

- Filled missing `skills_or_requirements` with conservative role/company/title/seniority-based fallback skills.
- Preserved original skills in `skills_or_requirements_original`.
- Added `skills_array` as a JSON array string.
- Added `has_skills_or_requirements` and `skills_imputation_type`.
- Added normalized enum columns:
  - `role_family_standard`
  - `seniority_standard`
  - `employment_type_standard`
  - `work_mode_standard`
- Added location features:
  - `city_standard`
  - `country_standard`
  - `location_bucket`
  - `is_bengaluru`
  - `is_gurgaon_ncr`
  - `is_india`
- Added helper features:
  - `experience_min_bucket`
  - `salary_midpoint`
  - `salary_available`
  - `company_name_standard`
  - `role_title_standard`
  - `near_duplicate_key`

Current prepared dataset checks:

```text
rows = 331
applied yes = 126
applied no = 205
missing skills_or_requirements = 0
role_based_fallback skill rows = 100
```

## Score Stacking Experiment

Notebook:

```text
notebooks/profile_scores/jedi_ridge_score_stacked_logistic.ipynb
```

Experiment:

```text
raw job fields
 -> Ridge predicts profile-fit scores
 -> predicted scores are appended
 -> Logistic Regression predicts applied yes/no
```

Models compared:

```text
raw_logistic
stacked_predicted_scores_logistic
oracle_true_scores_logistic
```

Outer-CV result:

| Model | Accuracy | F1 yes | Recall yes | ROC-AUC | Average Precision |
|---|---:|---:|---:|---:|---:|
| Raw Logistic | 0.873 | 0.830 | 0.818 | 0.923 | 0.897 |
| Stacked Logistic | 0.891 | 0.854 | 0.834 | 0.933 | 0.911 |
| Oracle Logistic | 0.903 | 0.872 | 0.865 | 0.959 | 0.943 |

Decision:

Stacking works, but the improvement is modest. Keep it as the best Logistic variant so far, but do not treat it as a breakthrough.

Predicted profile scores are likely more valuable for ranking than for a large binary-classification improvement.

Next ranking experiment:

```text
final_rank =
0.65 * applied_probability
+ 0.35 * predicted_overall_preference_score_scaled
```

## Salary Re-Estimation

Date: 2026-06-29

Problem:

```text
many rows used the same imputed salary range:
salary_min = 1200000
salary_max = 1500000
salary_midpoint = 1350000
```

Decision:

Replace these repeated placeholder salaries with conservative role-aware estimates instead of keeping one median-like value.

Rule inputs:

```text
seniority
role family
company match score
work mode
city/location
premium stack signals
generic/support/testing/annotation signals
```

Salary-fit score scale:

| Salary midpoint | salary_profile_fit_score |
|---:|---:|
| up to 6 LPA | 0 |
| 6-7 LPA | 1 |
| 7-8 LPA | 2 |
| 8-10 LPA | 3 |
| 10-12 LPA | 4 |
| 12-25 LPA | 5 |
| 25-40 LPA | 6 |
| 40-50 LPA | 7 |
| above 50 LPA | 8 |

Final check after rewrite:

```text
prepared rows = 331
old 12-15 LPA placeholders remaining = 0
```

Current salary-fit distribution:

| Score | Rows |
|---:|---:|
| 0 | 37 |
| 1 | 11 |
| 2 | 10 |
| 3 | 21 |
| 4 | 24 |
| 5 | 136 |
| 6 | 75 |
| 7 | 11 |
| 8 | 6 |

Files updated:

```text
data/jedi_master_labeled.csv
data/jedi_master_prepared.csv
data/salary_reestimation_summary_2026-06-29.md
tools/reestimate_salary_imputations.js
```

Caution:

These are inferred salaries, not verified company-provided compensation. They are suitable for reducing median-imputation distortion, but salary should remain a secondary feature behind experience, role, and overall preference.

All modeling notebooks should be rerun after this salary rewrite before comparing final results.

## Next Data Collection Classes

The next data batch should be targeted, not random.

Primary target:

```text
add 170 labeled rows next
then reassess with refreshed baselines
```

Longer-term target:

```text
500 labeled rows = next usable milestone
800-1000 labeled rows = better target for stable semi-supervised learning
```

Do not expect 95%-quality performance from the current 331-row dataset. Even the oracle profile-score model reached only about `0.903` outer-CV accuracy.

### Label Mix

Aim for:

```text
35-45% applied=yes
55-65% applied=no
```

The important negatives should be hard negatives, not obvious junk.

Suggested 170-row batch:

```text
60 strong likely positives
50 attractive hard negatives
40 borderline/ambiguous cases
20 low-salary or low-signal early-career roles
```

### Salary Classes

Collect across all brackets:

```text
4-6 LPA
6-8 LPA
8-10 LPA
10-12 LPA
12-18 LPA
18-25 LPA
25-40 LPA
40-50 LPA
50+ LPA
```

Reason:

The model needs to learn that salary helps, but that high salary can still be rejected when seniority or role fit is wrong.

### Seniority Classes

Prioritize:

```text
intern
new_grad
entry_level
junior
early_mid
mid
senior
lead/staff
```

Reason:

The current project is early-career focused. We still need senior/lead rows as hard negatives because many attractive jobs are wrong mainly due to experience requirements.

### Role-Family Classes

Collect:

```text
backend
frontend
fullstack
ml_ai
data_engineering
data_science / analytics
devops_cloud
qa_testing
product_engineering
other/support/operations
```

Reason:

The model should learn both preferred role families and nearby-but-wrong categories.

### Location Classes

Collect:

```text
Bengaluru
Delhi NCR / Gurgaon / Noida / Delhi / Faridabad
Hyderabad
Pune
Mumbai
Chennai
India remote
global remote
US / Europe
unknown or messy location
```

Reason:

Location is a real preference signal, but it should not become a brittle city-name shortcut.

### Work-Mode Classes

Collect:

```text
onsite
hybrid
remote
flexible
unknown
```

Reason:

Onsite/hybrid is strategically valuable early-career, but remote should be represented enough that the model learns when remote is acceptable.

### Hard Negative Classes

Deliberately add:

```text
great company + senior requirement
great salary + wrong seniority
great title + poor skills fit
ML/AI title + data annotation/support work
remote global + 4+ years required
backend/fullstack title + low salary and generic stack
good location + weak role
bad location + otherwise strong role
```

Reason:

These rows teach the model actual preference boundaries. They are more valuable than obvious bad jobs.
