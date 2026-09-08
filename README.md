# Semantic PR Suggestion Coverage

This repository contains research data, notebooks, and reusable code for estimating semantic overlap between code-review suggestions and merged pull-request changes. The current score is an experimental model prediction, not proof that a suggestion caused code to be adopted.

## Layout

```text
data/          # raw, interim, processed, external, and embedding data
docs/          # review, method, paper, and reproducibility notes
models/        # trained and experimental model artifacts
notebooks/     # collection, preparation, evaluation, and analysis notebooks
reports/       # generated score reports and diagnostics
src/           # reusable Python package
tests/         # focused regression and model tests
pyproject.toml # package metadata and dependency groups
uv.lock        # exact cross-platform dependency lock
```

## Main Dataset

Current processed dataset:

```text
data/processed/pr_suggestion_coverage/dataset/
```

Important files:

- `dataset.jsonl`: ML-ready examples with `suggested_diff` and `landed_diff`.
- `labels.csv`: current LLM-assisted target labels keyed by `example_id`; these are not validated ground truth.
- `llm_labels.jsonl`: detailed label reasoning.
- `review_examples/`: per-example markdown review files.
- `supervised_training.jsonl`: training-friendly joined records.

Labels:

- `0%`
- `partial`
- `mostly`
- `100%`

## Notebook Order

Install the locked environment from the repository root:

```bash
uv sync --locked --all-extras
uv run --locked --all-extras python -m ipykernel install --prefix .venv --name code-compare --display-name code-compare
```

Use the `code-compare` kernel for notebooks.

Verify the local structural parsers used by the AST scoring step:

```bash
uv run --locked --extra structural pr-suggestion-prepare-parsers
```

Expected languages: Python through stdlib `ast`, plus Go, C++, Rust, Java, TypeScript, JavaScript, C, and HTML through the locked `tree-sitter-language-pack` dependency.

Run notebooks in this order when rebuilding from scratch:

1. `notebooks/01_collect/closed_pr_comment_pair_collection.ipynb`
2. `notebooks/02_prepare/data_preparation.ipynb`
3. `notebooks/03_evaluate/pr_suggestion_metric_evaluation.ipynb`
4. `notebooks/04_visualize/metric_score_visualization.ipynb`
5. `notebooks/05_external/import_hf_github_codereview.ipynb` if refreshing the external dataset
6. `notebooks/06_train/train_metric_classifier.ipynb`
7. `notebooks/07_visualize/model_performance_dashboard.ipynb`
8. `notebooks/08_train/train_regression_coverage_model.ipynb`

External dataset import notebook:

```text
notebooks/05_external/import_hf_github_codereview.ipynb
```

It imports `ronantakizawa/github-codereview` into a separate weak-label dataset under `data/external/github_codereview/`. Keep it separate from the internal LLM-assisted dataset.

## Supervised Model

The training notebook combines the internal labeled dataset with the cleaned Hugging Face code review dataset, trains several sklearn classifiers, compares them against the current rule-based metric label, and saves the best trained model to:

```text
models/pr_suggestion_coverage/model.joblib
models/pr_suggestion_coverage/feature_schema.json
models/pr_suggestion_coverage/evaluation_report.json
```

The split is source-aware and PR-group-aware: each dataset source contributes validation rows, and examples from the same PR stay on one side of the split.

Use the saved model from code like this:

```python
import pandas as pd

from pr_suggestion_metrics.model_inference import predict_coverage_labels

metric_rows = pd.read_csv("reports/metric_scores.csv")
predictions = predict_coverage_labels(metric_rows)
```

The model input is still a deterministic metric row derived from `suggestion + merged diff/code`; the application does not need labels at prediction time.

For granular `0-100` coverage, use the percentage regressor. The model returns an integer percentage directly. Buckets are optional reporting metadata derived after inference and are not a model target.

Regression artifacts are saved to:

```text
models/pr_suggestion_coverage_regression/model.joblib
models/pr_suggestion_coverage_regression/feature_schema.json
models/pr_suggestion_coverage_regression/evaluation_report.json
```

Use the regression model from code like this:

```python
import pandas as pd

from pr_suggestion_metrics.model_inference import predict_coverage_percentages

metric_rows = pd.read_csv("reports/metric_scores.csv")
predictions = predict_coverage_percentages(metric_rows)
```

Retrain and tune the percentage model from the repository root:

```bash
uv run --locked --extra train python \
  -m pr_suggestion_metrics.train_percentage_regressor \
  --internal-scores reports/metric_scores.csv \
  --internal-labels data/processed/pr_suggestion_coverage/dataset/labels.csv \
  --hf-scores data/external/github_codereview/metric_scores.csv \
  --hf-labels data/external/github_codereview/dataset/labels.csv \
  --hf-audit data/labeling_batches/hf_semantic_percentage_outputs/audit_report.jsonl \
  --model-dir models/pr_suggestion_coverage_regression
```

The trainer keeps the existing model unless the tuned candidate improves internal holdout percentage MAE.

### Two-stage percentage model

Suggestion coverage has strong endpoint clusters: many examples are exactly `0` or `100`, while the remaining examples need a granular percentage. A single regressor tends to pull endpoint predictions toward the middle.

The two-stage model handles these cases separately:

1. CatBoost classifies each example as `0`, `intermediate`, or `100`.
2. A second CatBoost model estimates the exact percentage only for intermediate examples.
3. The two predictions are combined into one bounded percentage. Buckets are never returned by inference.

Run the guarded experiment from the repository root:

```bash
uv run --locked --extra train python \
  -m pr_suggestion_metrics.train_two_stage_percentage \
  --internal-scores reports/metric_scores.csv \
  --internal-labels data/processed/pr_suggestion_coverage/dataset/labels.csv \
  --hf-scores data/external/github_codereview/metric_scores.csv \
  --hf-labels data/external/github_codereview/dataset/labels.csv \
  --hf-audit data/labeling_batches/hf_semantic_percentage_outputs/audit_report.jsonl \
  --model-dir models/pr_suggestion_coverage_regression
```

The two-stage model is deployed only when holdout MAE and RMSE improve without increasing dangerous endpoint errors.

Run its focused tests with:

```bash
uv run --locked --extra train --extra test python -m pytest -q
```

### Out-of-fold ensemble

The ensemble blends the Random Forest's stronger large-error behavior with the two-stage model's stronger close-range accuracy. Its blend weight is selected only from repeated PR-grouped out-of-fold predictions, so the final holdout remains untouched during tuning.

```bash
uv run --locked --extra train python \
  -m pr_suggestion_metrics.train_percentage_ensemble \
  --internal-scores reports/metric_scores.csv \
  --internal-labels data/processed/pr_suggestion_coverage/dataset/labels.csv \
  --hf-scores data/external/github_codereview/metric_scores.csv \
  --hf-labels data/external/github_codereview/dataset/labels.csv \
  --hf-audit data/labeling_batches/hf_semantic_percentage_outputs/audit_report.jsonl \
  --model-dir models/pr_suggestion_coverage_regression
```

The ensemble replaces the deployed model only when holdout MAE and within-10 accuracy improve, dangerous errors do not increase, and any RMSE regression stays below 2%. Its public inference output remains one integer percentage.

### Advanced model comparison

The advanced benchmark compares direct CatBoost MAE/Huber models, LightGBM L1/Huber models, and XGBoost absolute-error/Pseudo-Huber models. It then uses repeated grouped out-of-fold predictions to choose a non-negative blend of the strongest model from each family, the Random Forest baseline, and the two-stage model.

On macOS, LightGBM also requires `brew install libomp`.

```bash
uv run --locked --extra train python \
  -m pr_suggestion_metrics.train_advanced_percentage_models \
  --internal-scores reports/metric_scores.csv \
  --internal-labels data/processed/pr_suggestion_coverage/dataset/labels.csv \
  --hf-scores data/external/github_codereview/metric_scores.csv \
  --hf-labels data/external/github_codereview/dataset/labels.csv \
  --hf-audit data/labeling_batches/hf_semantic_percentage_outputs/audit_report.jsonl \
  --model-dir models/pr_suggestion_coverage_regression
```

### Frozen embedding experiments

Frozen embeddings compare the meaning of a suggestion with a small set of likely landed hunks. They are converted into scalar cosine-similarity features and added to the existing tabular metrics. Embedding vectors are cached by model revision and text hash.

The tested UniXcoder and CodeBERT candidates improved repeated grouped development metrics but worsened the final internal holdout. A leave-one-repository-out evaluation over 2,500 rows from 29 external repositories found only a tiny, uncertain 0.022-point MAE improvement for the guarded blend, while RMSE worsened by 0.175 points and within-10 accuracy fell by 0.76 percentage points. They are therefore saved as research artifacts under `models/pr_suggestion_coverage_embeddings/` and are **not** used by the current percentage artifact.

Generate the pinned feature tables:

```bash
HF_HOME="$HOME/.cache/huggingface" uv run --locked --extra train --extra embeddings python \
  -m pr_suggestion_metrics.generate_embedding_features \
  --dataset internal=data/processed/pr_suggestion_coverage/dataset/dataset.jsonl \
  --dataset hf_github_codereview=data/external/github_codereview/dataset/dataset.jsonl \
  --model-id microsoft/unixcoder-base \
  --revision 5604afdc964f6c53782a6813140ade5216b99006 \
  --alias unixcoder_encoder \
  --input-prefix '<encoder-only> </s> ' \
  --output data/embeddings/unixcoder_encoder_features.csv \
  --cache data/embeddings/cache/unixcoder.sqlite3
```

Use the same command with `microsoft/codebert-base`, revision `3b0952feddeffad0063f274080e3c23d75e7eb39`, alias `codebert`, and no input prefix for CodeBERT.

Compare single and combined embedding feature sets:

```bash
uv run --locked --extra train --extra embeddings python \
  -m pr_suggestion_metrics.train_embedding_percentage_models \
  --internal-scores reports/metric_scores.csv \
  --internal-labels data/processed/pr_suggestion_coverage/dataset/labels.csv \
  --hf-scores data/external/github_codereview/metric_scores.csv \
  --hf-labels data/external/github_codereview/dataset/labels.csv \
  --hf-audit data/labeling_batches/hf_semantic_percentage_outputs/audit_report.jsonl \
  --base-model-dir models/pr_suggestion_coverage_regression \
  --embedding-features unixcoder=data/embeddings/unixcoder_features.csv \
  --embedding-features unixcoder_encoder=data/embeddings/unixcoder_encoder_features.csv \
  --embedding-features codebert=data/embeddings/codebert_features.csv \
  --output-dir models/pr_suggestion_coverage_embeddings
```

Evaluate transfer to unseen repositories:

```bash
uv run --locked --extra train --extra embeddings python \
  -m pr_suggestion_metrics.evaluate_repository_held_out_embeddings \
  --internal-scores reports/metric_scores.csv \
  --internal-labels data/processed/pr_suggestion_coverage/dataset/labels.csv \
  --hf-scores data/external/github_codereview/metric_scores.csv \
  --hf-labels data/external/github_codereview/dataset/labels.csv \
  --hf-audit data/labeling_batches/hf_semantic_percentage_outputs/audit_report.jsonl \
  --base-model-dir models/pr_suggestion_coverage_regression \
  --embedding-model-dir models/pr_suggestion_coverage_embeddings \
  --embedding-features unixcoder=data/embeddings/unixcoder_features.csv \
  --embedding-features unixcoder_encoder=data/embeddings/unixcoder_encoder_features.csv \
  --embedding-features codebert=data/embeddings/codebert_features.csv \
  --output-dir models/pr_suggestion_coverage_embeddings/repository_held_out \
  --resume
```

The completed report and one-prediction-per-example table are stored in `models/pr_suggestion_coverage_embeddings/repository_held_out/`.

Jina was not executed because its checkpoint required repository-provided Python and the safe built-in loader did not match the checkpoint architecture. The pipeline rejects missing model weights rather than silently evaluating a partially initialized model.

Visual model diagnostics live in:

```text
notebooks/07_visualize/model_performance_dashboard.ipynb
```

The notebook also exports PNG charts to:

```text
reports/model_performance_dashboard/
```

The preparation notebook writes rebuilt artifacts to `dataset_candidate/` first so the current `dataset/labels.csv` is not overwritten accidentally.

## Script Evaluation

Run the reusable evaluator from the repo root:

```bash
uv run --locked --extra structural pr-suggestion-evaluate
```

It writes per-example scores to:

```text
reports/pr_suggestion_metric_scores.csv
```

Score CSVs include both coarse labels and granular percentage buckets:

```text
expected_landed_percentage
expected_percentage_bucket
predicted_percentage
predicted_percentage_bucket
```

Buckets use `0` as its own bucket, then ten-point ranges: `1-10`, `11-20`, ..., `91-100`.

## Metric Strategy

Use the clone-detection framing described in:

```text
docs/pr-suggestion-diff-metrics.md
```

The current recommended stack is:

```text
exact normalized match
-> line recall
-> token recall
-> identifier-normalized token recall
-> GumTree / local Tree-sitter / AST features
-> embeddings for borderline cases
-> supervised classifier once features are stable
```

P1 language support is documented in:

```text
docs/p1-language-support-plan.md
docs/p1-language-support-implementation.md
```

Current P1 behavior:

- Jupyter Notebook files are compared by extracted code-cell source instead of raw `.ipynb` JSON.
- HTML, Groovy, HCL, Shell, TypeScript, C, and JavaScript use language-aware tokenization when Pygments supports the file.
- TypeScript, JavaScript, C, and HTML also have optional local Tree-sitter structural scoring.
