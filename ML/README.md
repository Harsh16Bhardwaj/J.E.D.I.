# JEDI machine-learning workspace

This directory preserves the complete modeling history while keeping production
application code separate.

## Canonical assets

- Canonical training dataset: `data/final/jedi_final_model_dataset.csv`
- Final scored training jobs: `data/final/jedi_final_scored_training_jobs.csv`
- Frontier experiment notebook: `notebooks/experiments/jedi_final_boosting_experiments.ipynb`
- Final modeling workbook: `notebooks/final/jedi_final_model_workbook.ipynb`
- Model configuration: `config/jedi_final_model_config.json`
- Modeling decision history: `JEDI_MODELING_JOURNEY.md`

## Supporting work

- Baselines live in `notebooks/baseline/`.
- Profile-score and stacking experiments live in `notebooks/profile_scores/`.
- Evaluation reports and decision notes live in `docs/`.
- Reproducible data and evaluation utilities live in `tools/`.
- Experiment outputs live in `data/experiments/`.
- Leakage-safe and final result artifacts live in `data/results/`.
- Data lineage stages live in `data/source/`, `data/intermediate/`,
  `data/supplements/`, `data/audits/`, and `data/backups/`.

## Production bundles

Future deployable model bundles belong in `models/`. Commit manifests,
feature schemas, checksums, and small configuration files. Large `.joblib` and
`.onnx` binaries are intentionally ignored.
