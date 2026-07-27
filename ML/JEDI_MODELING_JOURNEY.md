# JEDI Modeling Journey

JEDI is a job personalization and screening project. The goal is not only to predict whether a job should be applied to, but to rank daily scraped jobs so the strongest 25 roles surface first.

## Dataset Work

The first dataset was manually annotated and then audited for bias, missingness, and class imbalance. The major issues were:

- missing or weak skills/requirements text,
- experience fields that silently dropped rows,
- salary values that were sometimes imputed too uniformly,
- source/platform fields that were not useful training signals,
- too many already-good roles and not enough hard negative examples.

The dataset was then cleaned and expanded. Experience fit was repaired, salary buckets were made more realistic, skills text was normalized, explicit boolean features were added, and the final modeling dataset reached 691 rows.

Final dataset in root:

```txt
jedi_final_model_dataset.csv
```

## Modeling Stages

1. Logistic Regression was used as the baseline because it is interpretable and gives a stable first reference point.
2. Random Forest, Naive Bayes, and Gradient Boosting were tested to see whether nonlinear models or text assumptions helped.
3. Ridge regression was used to predict profile-fit scores.
4. Stacked models appended predicted fit scores into the classifier.
5. XGBoost was tested with raw, stacked, and oracle score variants.
6. Enhanced XGBoost added better text processing, explicit features, experience repair, and low-correlation feature dropping.
7. Final boosting experiments tried stronger XGBoost settings, SVD-based boosting, threshold tuning, and ranking metrics.

## Final Results

Best default-threshold classifier:

| Metric | Value |
|---|---:|
| Model | xgb_balanced |
| Variant | stacked_drop20 |
| Accuracy | 87.70% |
| Precision | 85.79% |
| Recall | 86.56% |
| F1 yes | 86.13% |
| ROC-AUC | 93.20% |
| PR-AUC | 90.33% |

Best tuned-threshold operating point:

| Metric | Value |
|---|---:|
| Model | xgb_deeper |
| Variant | stacked_drop20 |
| Threshold | 0.35 |
| Precision | 84.89% |
| Recall | 89.84% |
| F1 yes | 87.26% |
| Balanced accuracy | 88.57% |

Best ranking result:

| Metric | Value |
|---|---:|
| Precision@50 | 90.80% |
| Recall@50 | 74.43% |
| NDCG@50 | 0.9244 |

## Main Decision

The classifier plateaued around the high-80% F1 range. That is good enough for a classical ML stage, but it should not be the only product output.

The final JEDI output should be:

- predicted fit scores,
- a decimal JEDI preference score,
- an apply probability,
- a yes/no apply recommendation.

The ranking score is a weighted sum of predicted fit scores:

```txt
JEDI preference score =
  0.18 role title fit
+ 0.12 role family fit
+ 0.18 skills fit
+ 0.14 experience fit
+ 0.12 location fit
+ 0.07 work mode fit
+ 0.07 salary fit
+ 0.05 seniority fit
+ 0.07 overall preference fit
```

Salary is normalized from a 0-8 scale. The other fit scores are normalized from a 0-5 scale. The final score is reported on a 0-100 scale.

## Final Product Interpretation

Precision@50 is satisfactory for the current JEDI screener. If 50 jobs are scraped daily, the system can rank them and expose the top 25 for review. The binary classifier is used as a guardrail, while the weighted preference score is the main sort key.

## Next Work

The next real improvement will not come from squeezing another XGBoost parameter. It will come from:

- more labeled rows,
- more hard negative jobs,
- better embeddings for job descriptions,
- cleaner separation between ranking and classification,
- eventual RAG/agentic explanation layers for resume tailoring.
