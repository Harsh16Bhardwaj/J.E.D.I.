# Enhanced Dataset Preparation Report

Date: 2026-06-29

## Output

| Artifact | Path |
| --- | --- |
| Enhanced root dataset | jedi_modeling_enhanced_dataset.csv |
| Experience fix audit | data/jedi_experience_fit_fix_audit.csv |
| Feature correlation report | data/jedi_enhanced_feature_correlation_report.csv |
| Low-correlation drop candidates | data/jedi_enhanced_low_correlation_drop_candidates.csv |
| Error audit | data/jedi_xgboost_error_audit.csv |

## Experience Fit Repair

| Metric | Rows |
| --- | --- |
| Total rows | 691 |
| Experience profile fit values imputed | 131 |
| Remaining NA experience profile fit | 0 |

### Imputation Reasons

| Reason | Rows |
| --- | --- |
| exp_min_0_1 | 92 |
| senior | 30 |
| lead_staff_principal | 9 |

## Strongest Explicit Features

| Feature | corr | abs_corr | rows_with_feature | positive_rate_when_1 |
| --- | --- | --- | --- | --- |
| feat_is_early_career | 0.634859 | 0.634859 | 356 | 0.747191 |
| feat_strong_fit_combo | 0.607620 | 0.607620 | 249 | 0.843373 |
| feat_is_experience_mismatch | -0.574479 | 0.574479 | 270 | 0.085185 |
| feat_onsite_or_hybrid_early_career | 0.515850 | 0.515850 | 259 | 0.772201 |
| feat_salary_good_but_role_bad | -0.420000 | 0.420000 | 154 | 0.051948 |
| feat_bad_fit_combo | -0.410917 | 0.410917 | 143 | 0.041958 |
| feat_is_entry_or_junior | 0.404016 | 0.404016 | 196 | 0.760204 |
| feat_is_high_salary | -0.398678 | 0.398678 | 144 | 0.055556 |
| feat_is_senior_or_above | -0.397013 | 0.397013 | 133 | 0.037594 |
| feat_good_title_bad_experience | -0.396822 | 0.396822 | 153 | 0.071895 |
| feat_is_location_mismatch | -0.354908 | 0.354908 | 134 | 0.082090 |
| feat_is_tier1_city | 0.346341 | 0.346341 | 419 | 0.579952 |
| feat_is_india_target_location | 0.329735 | 0.329735 | 552 | 0.523551 |
| feat_is_bengaluru_or_ncr | 0.327276 | 0.327276 | 302 | 0.625828 |
| feat_is_intern_or_new_grad | 0.320432 | 0.320432 | 160 | 0.731250 |

## Lowest-Correlation Explicit Features

| Feature | corr | abs_corr | rows_with_feature |
| --- | --- | --- | --- |
| feat_is_support_or_annotation | -0.020366 | 0.020366 | 6 |
| feat_is_qa_testing | 0.027270 | 0.027270 | 5 |
| feat_is_platform_infra | -0.031317 | 0.031317 | 245 |
| feat_is_india_remote | -0.035138 | 0.035138 | 175 |
| feat_is_data_role | 0.058829 | 0.058829 | 108 |
| feat_is_security_role | -0.073803 | 0.073803 | 38 |
| feat_is_ml_ai | -0.090918 | 0.090918 | 132 |
| feat_is_backend_or_fullstack | 0.093927 | 0.093927 | 360 |
| feat_is_remote_global | -0.126539 | 0.126539 | 32 |
| feat_is_low_salary | 0.146707 | 0.146707 | 83 |
| feat_low_salary_but_good_role | 0.164668 | 0.164668 | 54 |
| feat_is_llm_or_rag_role | -0.172133 | 0.172133 | 221 |
| feat_remote_early_career | 0.175564 | 0.175564 | 90 |
| feat_is_lead_staff_principal | -0.195879 | 0.195879 | 32 |
| feat_is_devops_cloud | -0.204854 | 0.204854 | 43 |
| feat_is_remote | -0.209124 | 0.209124 | 260 |
| feat_is_mid_salary | 0.243219 | 0.243219 | 464 |
| feat_good_role_good_location | 0.282311 | 0.282311 | 443 |
| feat_is_mid_level | -0.304068 | 0.304068 | 164 |
| feat_is_intern_or_new_grad | 0.320432 | 0.320432 | 160 |

## Error Audit From Previous XGBoost Run

| Metric | Rows |
| --- | --- |
| Error rows audited | 69 |
| Stacked false positives | 33 |
| Stacked false negatives | 30 |
| Oracle/label contradiction rows | 56 |
| High-confidence error rows | 26 |

### Likely Issue Buckets

| Likely issue | Rows |
| --- | --- |
| oracle_error_label_or_feature_contradiction | 31 |
| high_confidence_oracle_error_label_or_feature_contradiction | 25 |
| ambiguous_or_model_boundary | 7 |
| accepted_despite_visible_penalty | 3 |
| label_may_be_stricter_than_visible_features | 2 |
| high_confidence_accepted_despite_visible_penalty | 1 |

## Modeling Decision

The enhanced dataset keeps all rows, fixes the experience target, adds explicit rule features, and leaves low-correlation dropping to the notebook so the drop decision is made inside each fold.

