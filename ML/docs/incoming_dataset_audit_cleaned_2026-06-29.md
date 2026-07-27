# Incoming Dataset Audit

File: `data/jedi_360_balanced_more_jobs_training_supplement_cleaned_2026-06-29.csv`

## Summary

| Check | Result |
| --- | --- |
| Rows | 360 |
| Columns | 31 |
| Matches labeled schema | yes |
| Missing required columns | none |
| Extra columns vs labeled | none |
| Missing prepared-derived columns | 20 |
| Invalid applied labels | 0 |
| Invalid score examples | 0 |
| Numeric issue examples | 0 |
| Salary-fit mismatches | 0 |
| Suspicious/search/training URLs | 0 |
| URLs containing seed_role | 0 |
| Companies containing Seed | 0 |
| can_apply_now=No but applied=yes | 0 |
| Apply URL overlaps with master | 0 |
| Near-duplicate overlaps with master | 20 |

## Column Fit

The incoming file matches the base labeled dataset schema. It does not include prepared-derived columns, which is acceptable if it goes through the preparation pipeline after merge.

Missing prepared-derived columns: `skills_or_requirements_original`, `skills_array`, `has_skills_or_requirements`, `skills_imputation_type`, `role_family_standard`, `seniority_standard`, `employment_type_standard`, `work_mode_standard`, `city_standard`, `country_standard`, `location_bucket`, `is_bengaluru`, `is_gurgaon_ncr`, `is_india`, `experience_min_bucket`, `salary_midpoint`, `salary_available`, `near_duplicate_key`, `company_name_standard`, `role_title_standard`

## Value Distributions

### applied

| Value | Rows |
| --- | --- |
| no | 181 |
| yes | 179 |

### source_platform

| Value | Rows |
| --- | --- |
| Workable | 114 |
| Wellfound | 87 |
| Lever | 73 |
| Greenhouse | 62 |
| Naukri | 24 |

### source_type

| Value | Rows |
| --- | --- |
| curated_training_row | 360 |

### can_apply_now

| Value | Rows |
| --- | --- |
| Yes | 272 |
| Unknown | 73 |
| No | 15 |

### role_family

| Value | Rows |
| --- | --- |
| Fullstack | 93 |
| Backend | 57 |
| Generative AI | 46 |
| Data Engineering | 39 |
| Frontend | 38 |
| AI/ML | 34 |
| DevOps | 18 |
| Platform Engineering | 17 |
| Security Engineering | 10 |
| Quant/ML | 6 |
| Mobile | 2 |

### seniority

| Value | Rows |
| --- | --- |
| mid_level | 93 |
| intern | 87 |
| junior | 60 |
| senior | 30 |
| sde_1 | 27 |
| associate | 25 |
| new_grad | 20 |
| staff | 8 |
| entry_level | 6 |
| lead | 4 |

### work_mode

| Value | Rows |
| --- | --- |
| On-site | 133 |
| Hybrid | 121 |
| Remote | 90 |
| Global Remote | 16 |

### employment_type

| Value | Rows |
| --- | --- |
| full_time | 273 |
| internship | 87 |

### salary_profile_fit_score

| Value | Rows |
| --- | --- |
| 3 | 121 |
| 4 | 92 |
| 5 | 64 |
| 2 | 26 |
| 6 | 26 |
| 7 | 16 |
| 8 | 10 |
| 1 | 5 |

### overall_preference_score

| Value | Rows |
| --- | --- |
| 5 | 129 |
| 4 | 68 |
| 3 | 66 |
| 1 | 42 |
| 2 | 37 |
| 0 | 18 |

## Blank Columns

| Column | Blank rows |
| --- | --- |
| apply_url | 360 |

## Structural Issues

### Invalid Scores

No invalid score examples found.

### Numeric Issues

No numeric range examples found.

### Salary-Fit Mismatches

No salary-fit mismatches found.

### Duplicate Incoming Apply URLs

No duplicate incoming apply URLs found.

### Near-Duplicate Incoming Keys

No repeated incoming near-duplicate keys found.

## Semantic Issues

Suspicious/search/training URLs: 0 of 360

URLs containing `seed_role=`: 0 of 360

Company names containing `Seed`: 0 of 360

Rows with `can_apply_now=No` but `applied=yes`: 0

Examples:

| row_id | company | role | apply_url |
| --- | --- | --- | --- |

Preference reason leading patterns:

| Pattern | Rows |
| --- | --- |
| strong fit | 200 |
| close call | 100 |
| rejected fit | 60 |

## Recommendation

The file is structurally mergeable, but still needs enum normalization, duplicate checks, and preparation-pipeline processing before training.

