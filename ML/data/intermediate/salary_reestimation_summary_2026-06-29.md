# JEDI Salary Re-Estimation Summary

Date: 2026-06-29

## Reason

Many rows had placeholder salary values:

```text
salary_min = 1200000
salary_max = 1500000
salary_midpoint = 1350000
```

These values were too uniform and made salary less useful as a learning signal.

## Action

Rows with the placeholder `12-15 LPA` salary range were re-estimated using role context:

- seniority
- role family
- company match score
- work mode
- city/location
- premium stack signals
- generic/support/testing/annotation signals

The rewrite intentionally introduced more low-bracket salaries where the role looked generic, early-career, low-signal, or less selective.

## Salary-Fit Scale

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

## Final Prepared Dataset Check

```text
rows = 331
old 12-15 LPA placeholders remaining = 0
```

Salary midpoint distribution:

| Bracket | Rows |
|---|---:|
| 4-6 LPA or lower | 37 |
| 6-7 LPA | 11 |
| 7-8 LPA | 10 |
| 8-10 LPA | 21 |
| 10-12 LPA | 24 |
| 12-25 LPA | 136 |
| 25-40 LPA | 75 |
| 40-50 LPA | 11 |
| 50+ LPA | 6 |

Salary-fit score distribution:

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

## Files Updated

```text
data/jedi_master_labeled.csv
data/jedi_master_prepared.csv
```

Reusable script:

```text
tools/reestimate_salary_imputations.js
```

## Caution

This is still inferred salary data, not verified company salary data. It is better than a single repeated median value, but models should treat salary as one signal, not as the main decision driver.

All baseline and stacked model outputs created before this salary rewrite should be rerun before comparing final model quality.
