# Incoming Training Supplement Cleaning Log

Input: `data/jedi_360_balanced_more_jobs_training_supplement_2026-06-29.csv`

Output: `data/jedi_360_balanced_more_jobs_training_supplement_cleaned_2026-06-29.csv`

## Changes

| Change | Rows |
|---|---:|
| company_names | 72 |
| role_titles | 5 |
| source_types | 360 |
| apply_urls | 360 |
| applied_labels | 2 |
| salary_ranges_swapped | 5 |
| experience_ranges_swapped | 3 |
| salary_fit_scores | 304 |
| preference_reasons | 360 |

## Salary-Fit Rule

| Salary midpoint | Score |
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

## Applied Label Repair

- `row_id=427`: `es` -> `yes`, because the row has strong positive fit scores.
- `row_id=603`: `es` -> `no`, because the row has low overall preference and close-call/no-fit signals.

## Merge Guidance

This cleaned file is now treated as curated training data. It is integrated into the main dataset, while source metadata remains excluded from model features.
