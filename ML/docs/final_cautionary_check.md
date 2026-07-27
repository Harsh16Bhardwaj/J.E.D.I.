# JEDI Final Cautionary Check

Date: 2026-06-28

Final datasets:

```text
data/jedi_master_labeled.csv
data/jedi_master_prepared.csv
```

## Merge Result

Merged sources:

- Original annotated master: 250 rows
- Early-career supplement: 81 rows

Final merged database:

```text
rows = 331
applied yes = 126
applied no = 205
positive rate = 38.1%
```

This is a healthier seed set than the original 250-row dataset.

## Core Checks

```text
invalid applied labels = 0
missing skills_or_requirements = 0
invalid score values outside 0-5 = 0
role_based_fallback skill rows = 100
```

Score columns were clamped to the valid 0-5 range before regenerating the prepared dataset.

## Standardized Coverage

Seniority:

```text
senior = 71
early_mid = 44
entry_level = 44
intern = 43
unknown = 38
mid = 36
junior = 25
new_grad = 10
staff = 10
lead = 8
principal = 2
```

Role family:

```text
fullstack = 103
backend = 97
ml_ai = 51
frontend = 41
other = 12
data_engineering = 7
data_science = 7
devops_cloud = 5
qa_testing = 4
analytics = 3
product_engineering = 1
```

Work mode:

```text
remote = 147
onsite = 110
hybrid = 35
unknown = 31
flexible = 8
```

Location bucket:

```text
bengaluru = 76
india_remote = 71
unknown = 59
us = 33
delhi_ncr = 19
global_remote = 15
hyderabad = 13
india_other = 13
europe = 12
pune = 10
mumbai = 6
chennai = 4
```

## Duplicate Caveat

There are duplicate `apply_url` groups, mostly from generic Wellfound/search/company pages:

```text
wellfound full-stack India page = 21 rows
wellfound backend India page = 20 rows
wellfound frontend India page = 16 rows
wellfound ML India page = 11 rows
```

These should not be blindly deduplicated by URL because the URL is sometimes a generic search/listing page, not a unique job posting.

Use this strategy during modeling:

1. Prefer `near_duplicate_key` for grouping.
2. Treat exact `apply_url` duplicates carefully.
3. For generic source pages, keep rows but avoid train/test leakage using `near_duplicate_key`.

Near-duplicate groups currently flagged:

```text
360customizer|backend_engineer|pune = 2
binocs_co|frontend_engineer|bengaluru = 2
scott_logic|graduate_software_developer|unknown = 2
scott_logic|lead_agentic_software_engineer|unknown = 2
```

## Readiness

The database is now good enough to append unlabeled jobs and begin the semi-supervised workflow after a supervised baseline.

Recommended next step:

1. Train a baseline on `data/jedi_master_prepared.csv`.
2. Use grouped/stratified validation.
3. Append unlabeled jobs in the same raw schema.
4. Run the same preparation script.
5. Pseudo-label only high-confidence unlabeled examples.
