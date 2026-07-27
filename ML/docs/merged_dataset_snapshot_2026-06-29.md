# Merged Dataset Snapshot

Date: 2026-06-29

## Merge

| Item | Value |
| --- | --- |
| Master rows before | 331 |
| Supplement rows added | 360 |
| Master rows after | 691 |
| Supplement source_type after merge | curated_training_row |
| Backup directory | data/backups/2026-06-29_before_360_merge |

## Applied Distribution

| applied | rows |
| --- | --- |
| no | 386 |
| yes | 305 |

## Source Type Distribution

| source_type | rows |
| --- | --- |
| curated_training_row | 360 |
| unknown | 200 |
| deterministic_scrape_candidate | 50 |
| web_verified_job_estimated_salary | 39 |
| web_verified_job_listed_salary | 24 |
| web_board_verified_estimated_fields | 13 |
| naukri_search_seed_estimated_not_verified | 5 |

## Salary Fit Distribution

| salary_profile_fit_score | rows |
| --- | --- |
| 5 | 190 |
| 3 | 145 |
| 4 | 129 |
| 6 | 101 |
| 2 | 35 |
| 0 | 29 |
| 7 | 27 |
| 1 | 19 |
| 8 | 16 |

## Seniority Distribution

| seniority | rows |
| --- | --- |
| intern | 115 |
| mid_level | 103 |
| junior | 72 |
| senior | 52 |
| Senior | 41 |
| entry_level | 33 |
| Unspecified | 33 |
| sde_1 | 29 |
| associate | 27 |
| new_grad | 20 |
| Mid / 3+ years | 18 |
| Early Career | 13 |
| Early-mid | 13 |
| mid | 11 |
| staff | 11 |
| Internship / Entry | 10 |
| Unspecified / likely mid | 9 |
| lead | 6 |
| Lead | 6 |
| Unspecified / likely mid+ | 6 |

## Role Family Distribution

| role_family | rows |
| --- | --- |
| Fullstack | 130 |
| Backend | 85 |
| Frontend | 55 |
| Generative AI | 48 |
| Data Engineering | 44 |
| AI/ML | 39 |
| DevOps | 18 |
| Platform Engineering | 17 |
| Security Engineering | 12 |
| AI Engineering | 9 |
| Fullstack / AI | 9 |
| Software Engineering | 9 |
| Generative AI / Agentic AI | 6 |
| Quant/ML | 6 |
| AI / Generative AI | 5 |
| Backend / Fullstack | 5 |
| Fullstack / Backend | 4 |
| Applied AI / ML Engineering | 3 |
| Backend / AI Platform | 3 |
| Frontend / Mobile | 3 |

## Prepared Dataset Snapshot

The prepared dataset was regenerated after merge:

```text
data/jedi_master_prepared.csv
rows = 691
```

### Standard Role Family

| role_family_standard | rows |
| --- | ---: |
| fullstack | 196 |
| backend | 164 |
| ml_ai | 132 |
| frontend | 81 |
| data_engineering | 46 |
| devops_cloud | 43 |
| other | 12 |
| data_science | 9 |
| qa_testing | 4 |
| analytics | 3 |
| product_engineering | 1 |

### Standard Seniority

| seniority_standard | rows |
| --- | ---: |
| intern | 130 |
| entry_level | 111 |
| senior | 101 |
| junior | 85 |
| early_mid | 83 |
| mid | 81 |
| unknown | 38 |
| new_grad | 30 |
| staff | 18 |
| lead | 12 |
| principal | 2 |

### Location Bucket

| location_bucket | rows |
| --- | ---: |
| india_remote | 175 |
| delhi_ncr | 123 |
| bengaluru | 119 |
| unknown | 64 |
| hyderabad | 44 |
| us | 39 |
| pune | 37 |
| europe | 21 |
| mumbai | 21 |
| india_other | 18 |
| chennai | 15 |
| global_remote | 15 |

### Work Mode

| work_mode_standard | rows |
| --- | ---: |
| remote | 260 |
| onsite | 236 |
| hybrid | 156 |
| unknown | 31 |
| flexible | 8 |

### Location Flags

| flag | true rows |
| --- | ---: |
| is_india | 552 |
| is_bengaluru | 146 |
| is_gurgaon_ncr | 159 |
