# JEDI EDA Results Guide

Use this file side-by-side with `notebooks/eda/jedi_dataset_bias_audit.ipynb`.

The goal is not just to read charts. The goal is to learn how to convert EDA into modeling decisions. For JEDI, that means deciding whether the 250 annotated jobs are ready to become a seed set for semi-supervised learning.

## 0. First Principle: EDA Is a Risk Audit

EDA is not decoration. Treat every section as a question:

- Can this data train the behavior I want?
- What hidden shortcut might a model learn?
- Which labels or fields are unreliable?
- What should I fix before training?
- What should I sample next?

For JEDI, the model should learn your job preference, not just memorize source platforms, repeated companies, or annotation artifacts.

## 1. Dataset Shape

Notebook result:

- Rows: `250`
- Columns: `31`
- Main target-like field: `applied`
- Main human preference score: `overall_preference_score`
- Important feature groups: company, role title, role family, seniority, location, work mode, experience, skills, salary, freshness

How to think:

250 rows is enough for careful EDA and a simple baseline. It is not enough for a strong general model, especially because job data is high variance. A single job row has many dimensions: role, seniority, country, company quality, salary, skills, and source platform.

Actual assessment:

This is a good seed annotation set. It is not yet a final training set. The right next step is not deep learning. The right next step is cleaning target labels, reducing leakage, balancing samples, and training a transparent baseline.

## 2. Target Class Balance

Notebook result:

```text
no                                                     126   50.4%
Active listing / Apply visible or direct apply page... 100   40.0%
yes                                                     24    9.6%
```

The notebook then maps only `yes` and `no` into binary labels. That gives:

```text
positive_rate = 16.0%
```

How to think:

The target column is the most important column in supervised and semi-supervised learning. If the target is messy, everything downstream becomes fake.

You wanted `applied` to mean:

```text
Did I decide to apply? yes/no
```

But the actual `applied` column contains a third value:

```text
Active listing / Apply visible or direct apply page found
```

That sounds like `can_apply_now`, not `applied`.

Actual assessment:

This is the biggest issue in the dataset. The `applied` column is contaminated with availability/status information. Before modeling, split the meanings:

- `can_apply_now`: whether the application page is available
- `applied`: whether you personally chose to apply

Do not train a model until `applied` is clean binary or intentionally multiclass.

Decision:

For the first model, use only rows where `applied` is exactly `yes` or `no`, or manually repair the 100 contaminated rows.

## 3. Missingness and Field Quality

Notebook result:

Highest missing fields:

```text
experience_max_years             86.4%
experience_min_years             52.4%
experience_profile_fit_score     52.4%
skills_or_requirements           40.0%
scraped_at                        0.4%
```

Important model fields:

```text
role_title                  0.0% missing
role_family                 0.0% missing
seniority                   0.0% missing
location                    0.0% missing
work_mode                   0.0% missing
employment_type             0.0% missing
overall_preference_score    0.0% missing
applied                     0.0% missing
skills_or_requirements     40.0% missing
```

How to think:

Missingness is not just inconvenience. It can become a signal. If one source has missing skills and another source has detailed skills, the model may learn:

```text
missing skills = source X = good/bad
```

instead of learning real job fit.

Actual assessment:

The dangerous missing field is `skills_or_requirements` at `40%`. Skill fit is supposed to be a central JEDI signal, so missing skills weaken the model.

Experience fields are also weak. `experience_max_years` is missing in `86.4%` of rows, so it should not be treated as a reliable core feature yet.

Decision:

For the first baseline:

- Use `role_title`, `role_family`, `seniority`, `location`, `work_mode`, `employment_type`, salary fields, and available scores.
- Use `skills_or_requirements` only with a missing indicator, such as `has_skills_text`.
- Do not depend heavily on `experience_max_years`.

## 4. Source Platform Coverage

Notebook result:

```text
Lever        100 rows   40.0%
Wellfound     68 rows   27.2%
Greenhouse    50 rows   20.0%
Workable      18 rows    7.2%
Remotive      14 rows    5.6%
```

Applied rate among clean yes/no rows:

```text
Greenhouse   30%
Lever         9%
Wellfound    NaN
Workable     NaN
Remotive     NaN
```

How to think:

Source platform bias asks:

```text
Is the model learning job quality, or is it learning where the job came from?
```

If one platform dominates, source-specific wording can become a shortcut.

Actual assessment:

Lever is the largest source at `40%`, but the notebook marks source concentration as pass because no source exceeds the chosen `45%` warning threshold.

However, there is a more subtle issue: `Wellfound`, `Workable`, and `Remotive` have `NaN` applied rates because their `applied` values are likely not clean yes/no. That means source comparisons are currently distorted by the target-label issue.

Decision:

Do not conclude yet that Greenhouse jobs are more applicable than Lever jobs. First clean `applied`.

For the next annotation batch, avoid adding too many more Lever rows unless they fill a missing segment.

## 5. Role Family Coverage

Notebook result:

Top role families:

```text
fullstack              24 rows   9.6%
backend                20 rows   8.0%
frontend               10 rows   4.0%
ai engineering          9 rows   3.6%
fullstack / ai          7 rows   2.8%
generative ai / agentic ai 5 rows
ai/ml                   5 rows
```

How to think:

Role family coverage tells you whether your dataset matches your actual job-search intent.

Good coverage means the model has enough examples of roles you like and dislike inside each role group. Bad coverage means the model may overgeneralize:

```text
all backend = good
all senior AI = bad
all remote fullstack = maybe
```

Actual assessment:

There is no single role family dominating. That is good.

But there are too many tiny role-family variants:

```text
backend / fullstack
fullstack / backend
fullstack / ai
backend / ai platform
applied ai / ml engineering
generative ai / agentic ai
```

This fragmentation makes the EDA look more diverse than it really is.

Decision:

Before modeling, create a normalized `role_family_standard`:

- backend
- frontend
- fullstack
- ml_ai
- data
- devops_cloud
- product_engineering
- other

Keep the original `role_family` as raw text, but model on the standardized version.

## 6. Seniority Coverage

Notebook result:

Top seniority labels:

```text
senior                    56 rows   22.4%
unspecified               33 rows   13.2%
mid / 3+ years            18 rows    7.2%
early-mid                 13 rows    5.2%
early career              13 rows    5.2%
mid                       11 rows    4.4%
internship / entry        10 rows    4.0%
```

Applied rates:

```text
entry_level       100.0%   but only 4 rows
entry / sde i      75.0%   but only 4 rows
junior/mid         50.0%   6 rows
senior              6.25%  56 rows
lead/staff          0.0%
```

How to think:

Seniority is likely one of your strongest preference signals. A fresher/early-career profile should reject many senior, staff, lead, or principal roles even if the tech stack looks attractive.

Actual assessment:

The dataset has too many senior roles for your likely target market. This is useful because it teaches the model what to reject, but it can also create bias if the dataset becomes mostly senior rejections.

The positive examples are concentrated in small early-career groups. That is dangerous because the model has too few examples of the thing you actually want.

Decision:

Next annotation batch should deliberately collect more:

- intern
- entry_level
- new grad
- junior
- SDE I
- 0-2 years

Do not over-sample senior, lead, staff, or principal roles unless you need negative examples.

## 7. Work Mode Coverage

Notebook result:

```text
remote     129 rows   51.6%
onsite      71 rows   28.4%
unknown     30 rows   12.0%
hybrid      18 rows    7.2%
not listed   2 rows    0.8%
```

Applied rates:

```text
unknown   30.0%
onsite    20.8%
hybrid    11.1%
remote    10.5%
```

How to think:

Work mode can be a real preference, but it can also be a source artifact. Remote boards will naturally produce more remote jobs, and foreign remote jobs may be less suitable for fresher India applicants.

Actual assessment:

Remote is a dominant segment at `51.6%`. This could bias the model. If many remote jobs are senior/global roles, the model may learn that remote is bad, when the real issue is seniority, country, or eligibility.

Decision:

Do not interpret `remote` alone. Cross it with seniority and location.

For modeling, use interaction-aware features:

- `work_mode`
- `country/location bucket`
- `seniority_standard`

## 8. Employment Type Coverage

Notebook result:

Top values:

```text
full-time    137 rows   54.8%
full_time     48 rows   19.2%
full time     24 rows    9.6%
```

How to think:

This is a classic normalization problem. The same concept appears in multiple spellings:

```text
full-time
full_time
full time
```

A model will treat these as different categories unless you standardize them.

Actual assessment:

Employment type is not ready as-is. Most rows are full-time, but the column has many duplicate variants and some values that are not employment types at all, such as `remote`.

Decision:

Create `employment_type_standard`:

- full_time
- internship
- contract
- part_time
- freelance
- unknown

Move work-mode-like values out of employment type.

## 9. Location Coverage

Notebook result:

Top location variants:

```text
in office • bengaluru       20 rows
india                       11 rows
in office • bangalore urban  8 rows
remote only • india          8 rows
united states                7 rows
remote                       7 rows
remote only • everywhere     7 rows
remote - india               6 rows
```

How to think:

Location is messy because it mixes city, country, remote status, and source-specific formatting.

Actual assessment:

The same conceptual location appears in several forms:

```text
Bengaluru
Bangalore
Bangalore Urban
in office • Bengaluru
Bengaluru, Karnataka, India
```

Remote also appears inside location, even though `work_mode` already exists.

Decision:

Before modeling, create:

- `city_standard`
- `country_standard`
- `is_india`
- `is_bengaluru`
- `location_bucket`: Bengaluru, Hyderabad, Delhi NCR, India remote, India other, US, global remote, other

Keep raw `location`, but do not rely on it directly as a category.

## 10. Company Concentration and Duplicate Risk

Notebook result:

Top company share:

```text
Top 5 company share: 9.6%
```

Duplicate-like rates:

```text
apply_url duplicate rate              28.8%
role_title duplicate rate             26.8%
skills_or_requirements duplicate rate 42.4%
```

How to think:

Company concentration is fine if no company dominates. Duplicate risk is more serious because train/test leakage can inflate model performance.

If the same URL or nearly same job appears in both train and validation, the model looks smarter than it is.

Actual assessment:

Company concentration is acceptable. No company dominates.

But duplicate apply URLs at `28.8%` is a red flag. Some rows may be true duplicates, repeated imports, or multiple records pointing to the same posting.

Decision:

Before training:

- deduplicate exact `apply_url`
- or group split by `apply_url`
- also consider grouping by `company_name + role_title`

Do not random-split blindly.

## 11. Score Distributions

Notebook result:

Score averages:

```text
company_match_score              mean 3.97
role_title_preference_score      mean 3.78
role_family_preference_score     mean 4.44
seniority_profile_fit_score      mean 3.16
location_profile_fit_score       mean 3.01
work_mode_fit_score              mean 4.63
experience_profile_fit_score     mean 2.45
skills_profile_fit_score         mean 4.15
salary_profile_fit_score         mean 5.26
overall_preference_score         mean 2.80
```

Out-of-range scores:

```text
role_family_preference_score max 6
work_mode_fit_score max 6
skills_profile_fit_score max 6
salary_profile_fit_score max 8
```

How to think:

Score distributions tell you whether your annotation scale is calibrated.

If almost everything gets 5, the score is not useful. If some scores go beyond the intended range, the labels need validation.

Actual assessment:

Several scores exceed the expected 1-5 scale. This must be fixed before modeling.

Salary score is suspicious. It has mean `5.256` and max `8`, while its correlation with `applied` is almost zero. That means salary score is either not on the same scale, not consistently annotated, or not driving your apply decision.

Decision:

Before modeling:

- clamp or manually repair scores outside 0-5 or 1-5
- decide whether `0` is allowed
- document the scoring scale
- treat salary score carefully

## 12. Score and Label Alignment

Notebook result:

Highest correlation with `applied`:

```text
experience_profile_fit_score   0.524
overall_preference_score       0.501
seniority_profile_fit_score    0.292
location_profile_fit_score     0.207
role_title_preference_score    0.198
skills_profile_fit_score       0.183
```

Weak or useless correlation:

```text
salary_profile_fit_score       0.006
work_mode_fit_score           -0.019
```

How to think:

Correlation is not causation, but it shows which annotations line up with the final decision.

Strong alignment means the score is likely useful. Weak alignment means either:

- the factor does not matter much
- the score is noisy
- the column has scale issues
- the final label is contaminated

Actual assessment:

The most meaningful signal appears to be experience fit and overall preference. That makes sense for your job search: seniority/experience mismatch is probably the fastest rejection reason.

Salary and work mode do not currently explain `applied`. Salary has obvious scale issues, and work mode may be confounded by seniority/source/location.

Decision:

For the first baseline:

- include experience/seniority signals strongly
- include overall score only if you are modeling your final preference, not raw job facts
- do not trust salary score until cleaned
- do not overinterpret work mode alone

## 13. Skill Signal Audit

Notebook result:

Frequent skill tokens:

```text
backend                 24 rows
fullstack               22 rows
product engineering     21 rows
ai                      15 rows
react                   11 rows
software engineering    10 rows
python                  10 rows
apis                    10 rows
frontend                 9 rows
typescript               9 rows
node.js                  8 rows
agentic ai               7 rows
```

How to think:

This section checks whether the text field reflects the skill clusters you care about.

Actual assessment:

The skills are aligned with your intended project direction: backend, fullstack, AI, React, Python, APIs, Node, agentic AI. That is good.

But `skills_or_requirements` is missing in `40%` of rows, so text modeling will only work well after improving extraction coverage.

Decision:

Use skill text in baseline experiments, but add:

- `has_skills_text`
- token count
- standardized skill tags later

Do not rely only on free text yet.

## 14. Sparse and Dominant Segments

Notebook result:

Dominant segments:

```text
employment_type = full-time   54.8%
work_mode = remote            51.6%
source_platform = lever       40.0%
```

Sparse segment table has many entries, `182` flagged rows/segments.

How to think:

Dominant segments can cause bias. Sparse segments can cause unstable conclusions.

If a category has 3 rows and 100% applied rate, that does not mean the category is perfect. It means the sample is tiny.

Actual assessment:

The dataset is not dominated by role family, but it is dominated by full-time, remote, and Lever. It also has many fragmented category values.

Decision:

The next data work should be normalization first, not more modeling:

- normalize employment type
- normalize seniority
- normalize role family
- normalize location
- clean target labels

Only then should you decide which segments need more annotation.

## 15. Suggested Sampling Weights

Notebook result:

Suggested sample weight range:

```text
min 0.336
median 0.892
max 2.699
```

High-weight examples include rare positive labels and rare seniority/source combinations.

How to think:

Sampling weights are a way to stop common segments from controlling the model. They are useful for experiments, but they do not replace better data.

Actual assessment:

The highest-weight rows are mostly rare positives and rare seniority groups. That matches the class imbalance problem: `yes` labels are scarce.

Decision:

Use weights in experiments, but do not depend on weights alone. Also collect more positive examples.

## 16. Readiness Checklist

Notebook result:

```text
target_balance              review   positive_rate=16.0%
role_family_concentration   pass     largest_segment_share=9.6%
seniority_concentration     pass     largest_segment_share=22.4%
source_platform_concentration pass   largest_segment_share=40.0%
critical_missingness        review   max_critical_missing=40.0%
duplicate_apply_urls        review   duplicate_url_rate=28.8%
```

How to think:

This is the executive summary of the EDA.

Pass does not mean perfect. Review means do not ignore before modeling.

Actual assessment:

The dataset is not blocked by role-family concentration. That is good.

The dataset is blocked or weakened by:

- target-label contamination
- low positive class rate
- missing skills text
- duplicate apply URLs
- category fragmentation
- out-of-range scores

Decision:

Do not move directly into semi-supervised learning yet. Do a cleaning and standardization pass first.

## 17. What Actions Should Come From This EDA?

### Immediate cleanup actions

1. Fix `applied`
   - Allowed values should be only `yes` / `no`, or maybe blank for unlabeled.
   - Move `Active listing / Apply visible...` into `can_apply_now`.

2. Fix score ranges
   - Decide the valid scale: likely `0-5` or `1-5`.
   - Repair values like `6` and `8`.

3. Deduplicate
   - Exact duplicate: same `apply_url`.
   - Near duplicate: same company + title + location.

4. Normalize categories
   - `role_family_standard`
   - `seniority_standard`
   - `employment_type_standard`
   - `work_mode_standard`
   - `location_bucket`

5. Add missingness indicators
   - `has_skills_text`
   - `has_experience_min`
   - `has_experience_max`
   - `has_salary`

### Modeling actions after cleanup

Start with a baseline, not deep learning:

1. Logistic regression / linear model with tabular features
2. Tree model such as Random Forest or XGBoost/LightGBM if available
3. Text baseline with TF-IDF on title + skills
4. Combined tabular + text baseline

Validation:

- stratify by `applied`
- group by `apply_url` or company/title to avoid duplicate leakage
- track precision, recall, F1, PR-AUC, ROC-AUC
- inspect false positives and false negatives manually

Semi-supervised learning:

- only after a reliable baseline
- only pseudo-label high-confidence unlabeled jobs
- keep uncertain jobs for human annotation
- avoid feeding contaminated labels into pseudo-labeling

## 18. How to Read Future EDAs Like an Engineer

For every chart/table, ask this sequence:

1. **What is this measuring?**
   - Example: class balance measures whether `yes/no` labels are usable.

2. **Is this field conceptually clean?**
   - Example: `applied` is not clean because it contains application availability text.

3. **Is the distribution healthy?**
   - Example: `remote` is over half the data, so work-mode bias is possible.

4. **Can this leak the answer?**
   - Example: `preference_reason` may leak your final decision.

5. **Can this create shortcut learning?**
   - Example: source platform may act as a proxy for job quality.

6. **Is the sample size enough?**
   - Example: `entry_level` has 100% applied rate but only 4 rows, so do not trust the rate too much.

7. **What action follows?**
   - Clean, normalize, deduplicate, resample, collect more data, or exclude from training.

## Final Read

The EDA says your dataset is promising but not yet modeling-ready.

The strongest real signals are:

- experience fit
- overall preference
- seniority fit
- role/location fit

The weakest or riskiest parts are:

- contaminated `applied`
- missing skill text
- duplicate URLs
- fragmented categories
- out-of-range score values
- salary/work-mode scores not aligning with final decision

The correct next phase is a **data cleaning and modeling-prep notebook**, not semi-supervised learning directly.
