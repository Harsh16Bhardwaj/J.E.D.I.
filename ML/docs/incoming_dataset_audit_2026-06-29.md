# Incoming Dataset Audit

File: `data/jedi_360_balanced_more_jobs_training_supplement_2026-06-29.csv`

## Summary

| Check | Result |
| --- | --- |
| Rows | 360 |
| Columns | 31 |
| Matches labeled schema | yes |
| Missing required columns | none |
| Extra columns vs labeled | none |
| Missing prepared-derived columns | 20 |
| Invalid applied labels | 2 |
| Invalid score examples | 0 |
| Numeric issue examples | 8 |
| Salary-fit mismatches | 304 |
| Suspicious/search/training URLs | 243 |
| URLs containing seed_role | 93 |
| Companies containing Seed | 66 |
| can_apply_now=No but applied=yes | 0 |
| Apply URL overlaps with master | 0 |
| Near-duplicate overlaps with master | 0 |

## Column Fit

The incoming file matches the base labeled dataset schema. It does not include prepared-derived columns, which is acceptable if it goes through the preparation pipeline after merge.

Missing prepared-derived columns: `skills_or_requirements_original`, `skills_array`, `has_skills_or_requirements`, `skills_imputation_type`, `role_family_standard`, `seniority_standard`, `employment_type_standard`, `work_mode_standard`, `city_standard`, `country_standard`, `location_bucket`, `is_bengaluru`, `is_gurgaon_ncr`, `is_india`, `experience_min_bucket`, `salary_midpoint`, `salary_available`, `near_duplicate_key`, `company_name_standard`, `role_title_standard`

## Value Distributions

### applied

| Value | Rows |
| --- | --- |
| no | 180 |
| yes | 178 |
| es | 2 |

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
| platform_search_seed_estimated_training_row | 219 |
| search_result_anchor_estimated_training_row | 117 |
| naukri_search_seed_robots_blocked_estimated | 24 |

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
| 5 | 230 |
| 4 | 99 |
| 3 | 31 |

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

No blank values detected in CSV fields.

## Structural Issues

### Invalid Scores

No invalid score examples found.

### Numeric Issues

| row_id | issue | value |
| --- | --- | --- |
| 339 | salary_max < salary_min | 1000000/900000 |
| 368 | salary_max < salary_min | 1000000/900000 |
| 383 | salary_max < salary_min | 1000000/900000 |
| 446 | salary_max < salary_min | 1000000/900000 |
| 477 | salary_max < salary_min | 1000000/900000 |
| 642 | experience_max_years < experience_min_years | 8/6 |
| 651 | experience_max_years < experience_min_years | 8/6 |
| 667 | experience_max_years < experience_min_years | 8/6 |

### Salary-Fit Mismatches

| row_id | salary_min | salary_max | actual_fit | expected_fit |
| --- | --- | --- | --- | --- |
| 332 | 900000 | 1300000 | 5 | 4 |
| 333 | 1000000 | 1200000 | 5 | 4 |
| 334 | 1200000 | 1200000 | 5 | 4 |
| 335 | 720000 | 900000 | 4 | 3 |
| 337 | 600000 | 1000000 | 4 | 2 |
| 338 | 900000 | 1400000 | 5 | 4 |
| 339 | 1000000 | 900000 | 5 | 3 |
| 340 | 900000 | 1500000 | 5 | 4 |
| 341 | 1000000 | 1400000 | 5 | 4 |
| 342 | 1100000 | 1200000 | 5 | 4 |
| 344 | 900000 | 1500000 | 5 | 4 |
| 346 | 480000 | 1200000 | 4 | 3 |
| 348 | 720000 | 1200000 | 5 | 3 |
| 349 | 600000 | 1000000 | 4 | 2 |
| 350 | 1000000 | 1400000 | 5 | 4 |
| 351 | 720000 | 1400000 | 5 | 4 |
| 353 | 1100000 | 1200000 | 5 | 4 |
| 354 | 720000 | 1400000 | 5 | 4 |
| 355 | 1000000 | 1300000 | 5 | 4 |
| 356 | 1100000 | 1200000 | 5 | 4 |
| 357 | 900000 | 1200000 | 5 | 4 |
| 359 | 1000000 | 1400000 | 5 | 4 |
| 360 | 1100000 | 1300000 | 5 | 4 |
| 361 | 1100000 | 1300000 | 5 | 4 |
| 363 | 480000 | 900000 | 4 | 1 |
| 364 | 900000 | 1200000 | 5 | 4 |
| 365 | 480000 | 1000000 | 4 | 2 |
| 368 | 1000000 | 900000 | 5 | 3 |
| 369 | 720000 | 900000 | 4 | 3 |
| 370 | 900000 | 1400000 | 5 | 4 |

### Duplicate Incoming Apply URLs

No duplicate incoming apply URLs found.

### Near-Duplicate Incoming Keys

No repeated incoming near-duplicate keys found.

## Semantic Issues

Suspicious/search/training URLs: 243 of 360

URLs containing `seed_role=`: 93 of 360

Company names containing `Seed`: 66 of 360

Rows with `can_apply_now=No` but `applied=yes`: 0

Examples:

| row_id | company | role | apply_url |
| --- | --- | --- | --- |
| 332 | Fynd Platform | Associate Software Engineer - Frontend - SaaS Platform | https://apply.workable.com/search?query=Fynd%20Software%20Engineer%20India&q=Associate+Software+Engineer+-+Frontend+-+SaaS+Platform+Delhi%2C+India&training_seed=1 |
| 333 | Calyb AI | AI Engineer Intern - LLM Apps - Data Products | https://wellfound.com/jobs?query=Calyb%20AI%20Applied%20AI%20ML%20Engineer&q=AI+Engineer+Intern+-+LLM+Apps+-+Data+Products+Pune%2C+Maharashtra%2C+India&training_seed=2 |
| 334 | Smallcase | Associate Software Engineer - Frontend - Product Team | https://apply.workable.com/search?query=Smallcase%20Frontend%20Engineer&q=Associate+Software+Engineer+-+Frontend+-+Product+Team+Faridabad%2C+Haryana%2C+India&training_seed=3 |
| 335 | Renan | Software Engineer Intern - Fullstack Product | https://wellfound.com/jobs?query=Renan%20Machine%20Learning%20Engineer&q=Software+Engineer+Intern+-+Fullstack+Product+Noida%2C+Uttar+Pradesh%2C+India&training_seed=4 |
| 336 | BotSpace | Junior Backend Developer - Data Products | https://wellfound.com/jobs?query=BotSpace%20Full%20Stack%20Engineer&q=Junior+Backend+Developer+-+Data+Products+Delhi%2C+India&training_seed=5 |
| 337 | Stripe Seed | Software Engineer Intern - Fullstack Product | https://boards.greenhouse.io/search?query=Stripe%20Software%20Engineer%20Intern%20Bengaluru&q=Software+Engineer+Intern+-+Fullstack+Product+Bengaluru%2C+Karnataka%2C+India&training_seed=6 |
| 338 | Sprinto | Frontend Engineer Intern | https://apply.workable.com/search?query=Sprinto%20Software%20Engineer%20Bengaluru&q=Frontend+Engineer+Intern+Delhi+NCR%2C+India&training_seed=7 |
| 341 | ShopBack | New Grad Software Engineer - Web Platform - Data Products | https://jobs.lever.co/shopback-2?department=11.+Engineering&q=New+Grad+Software+Engineer+-+Web+Platform+-+Data+Products+Gurugram%2C+Haryana%2C+India&training_seed=10 |
| 342 | Coupa India | SDE I - Full Stack Engineer - SaaS Platform | https://jobs.lever.co/coupa/edd3ac99-ffdd-47c2-b25d-e44171722d1d/apply?lever-source=themuse&q=SDE+I+-+Full+Stack+Engineer+-+SaaS+Platform+Hyderabad%2C+Telangana%2C+India&training_seed=11 |
| 346 | Keka HR | Data Engineering Intern - Growth Platform | https://apply.workable.com/search?query=Keka%20Backend%20Developer%20Hyderabad&q=Data+Engineering+Intern+-+Growth+Platform+Faridabad%2C+Haryana%2C+India&training_seed=15 |

Preference reason leading patterns:

| Pattern | Rows |
| --- | --- |
| target-positive sample | 200 |
| close-call boundary sample | 100 |
| negative/way-off sample | 60 |

## Recommendation

Do not merge this file directly into the real master job database as verified job rows.

It is structurally mergeable after normalization, but semantically it looks like generated or seed-estimated training data rather than real scraped job listings.

Safe use:

- keep as an experimental augmentation file
- mark `source_type` as `synthetic_training_supplement` or `estimated_training_row`
- exclude `source_platform`, `source_type`, `apply_url`, and `preference_reason` from training
- run the preparation pipeline to normalize enums and derived fields
- train/evaluate separately with and without this file before accepting it

