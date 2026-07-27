# JEDI Next Annotation Batch Plan

Date: 2026-06-29

## Goal

Add a targeted batch of new labeled jobs.

Recommended next batch:

```text
170 rows
```

This should take the dataset from `331` labeled rows to about `501` labeled rows.

This is a good next milestone, but it is not enough to expect stable `95%` model quality. For stronger semi-supervised learning and more reliable generalization, aim for:

```text
500 labeled rows = next milestone
800-1000 labeled rows = stronger target
```

## Label Mix

Target:

```text
35-45% applied=yes
55-65% applied=no
```

Suggested 170-row mix:

| Type | Rows |
|---|---:|
| strong likely positives | 60 |
| attractive hard negatives | 50 |
| borderline or ambiguous cases | 40 |
| low-salary / low-signal early-career roles | 20 |

## Salary Classes

Collect examples across:

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

Purpose:

Teach the model that salary is useful, but not decisive. A high salary can still be a rejection if the role is too senior or badly aligned.

## Seniority Classes

Collect:

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

Priority:

```text
intern
new_grad
entry_level
junior
0-2 years
```

Still include senior and lead roles as hard negatives.

## Role Classes

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

Priority positives:

```text
backend
fullstack
ml_ai
data_engineering
strong frontend
```

Useful negatives:

```text
QA-only
manual testing
data annotation
support-heavy roles
generic analyst roles
operations roles
```

## Location Classes

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

Priority positives:

```text
Bengaluru
Delhi NCR
Hyderabad
Pune
India remote only when clearly early-career friendly
```

## Work Mode Classes

Collect:

```text
onsite
hybrid
remote
flexible
unknown
```

Preference:

Onsite and hybrid should be well represented because they are strategically useful early-career. Remote should still be represented enough that the model learns when remote is acceptable.

## Hard Negative Templates

Deliberately add these:

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

These teach preference boundaries better than obvious bad jobs.

## Current Rule

Do not add only attractive jobs.

The model needs:

```text
good jobs you accept
good-looking jobs you reject
imperfect jobs you still accept
obvious bad jobs in small quantity only
```
