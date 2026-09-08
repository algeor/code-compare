# PR Suggestion Coverage ML Worklog

Historical documentation of the work done in this thread to build, evaluate, visualize, and improve the PR suggestion coverage comparison pipeline.

Last updated: 2026-09-03

## 1. Problem Statement

We needed a way to compare small code suggestions against the final merged PR diff and answer:

```text
Did the suggested code actually land in the merged/final PR?
```

The comparison must tolerate small developer edits such as variable renames, formatting changes, import movement, refactoring, and nearby context changes. Exact string matching alone is not enough.

## 2. Metric Strategy Research

We reviewed several approaches:

- normalized exact match 
  - Drop repetitive spaces, newlines, uniformalized lines and characters. Compare exact strict block match.
- line overlap / line recall
  - Percentual overlap between suggested and landed change lines in the code. 
- token overlap / token recall
  - Percentual overlap of tokens (function names, variables,punctuation)
- identifier-normalized token recall
  - more forgiving, if dev changed names
- literal-normalized token recall
  - drabs the shape of the code in case of a value change
- LCS-style similarity
  - longest common subsequence. like line overlap but more forgiving
- candidate hunk matching
  - takes pieces of the code and compares with the helf of LCS
- AST / structural scoring
  - builds on top of candidate hunks and parses, extracts structural node types
  - computes recall/similarity over those node types. 
  - Keeps the best structural match.
    - "python", "c", "cpp", "go", "html", "java", "javascript", "rust", "typescript"
- GumTree tree edit distance
  - edits taken to reach from suggestion to landed diffs
  - 
- embedding or ML-based matching
- supervised models over deterministic metric features

The selected strategy was:

```text
deterministic metrics first -> supervised model over metric features
```

Reasoning:

- deterministic metrics are inspectable
- the model can be explained through features
- the final application only has `suggestion + merged/final diff/code`
- pure semantic models would need more labels and are harder to trust early

Main docs created or updated:

```text
ml/docs/pr-suggestion-diff-metrics.md
ml/docs/metric-improvement-plan.md
ml/docs/language-aware-code-comparison-research.md
ml/docs/top-language-comparison-plan.md
```

## 3. ML Project Layout

The ML work was organized under:

```text
ml/
  data/
  docs/
  notebooks/
  reports/
  models/
  src/
```

Main internal examples:

```text
ml/data/processed/pr_suggestion_coverage/dataset/dataset.jsonl
```

Main labels:

```text
ml/data/processed/pr_suggestion_coverage/dataset/labels.csv
ml/data/processed/pr_suggestion_coverage/dataset/llm_labels.jsonl
```

External Hugging Face-derived examples are separate:

```text
ml/data/external/github_codereview/dataset/
```

Reusable code lives in:

```text
ml/src/pr_suggestion_metrics/
```

Important modules:

```text
build_dataset.py
collect_pr_code_changes.py
evaluate_metrics.py
model_inference.py
prepare_structural_parsers.py
```

`ml/` remains ignored, per request.

## 4. Core Evaluator

The main evaluator is:

```text
ml/src/pr_suggestion_metrics/evaluate_metrics.py
```

It computes deterministic features for each example, including:

- `expected_landed_percentage`
- `expected_percentage_bucket`
- `predicted_percentage`
- `predicted_percentage_bucket`
- line recall
- token recall
- identifier-normalized token recall
- literal-normalized token recall
- best candidate hunk metrics
- meaningful anchor recall
- structural parser metrics
- optional GumTree metrics
- file overlap metrics

Generated score files:

```text
ml/reports/metric_scores.csv
ml/data/processed/pr_suggestion_coverage/dataset/metric_scores.csv
ml/data/external/github_codereview/metric_scores.csv
```

## 5. Candidate Hunk Matching

We added matching against candidate hunks instead of comparing each suggestion only against the entire PR diff.

Reason:

```text
Small suggestions should be compared against the most relevant changed hunk, not diluted by all unrelated PR changes.
```

Important hunk features:

- `best_hunk_token_recall`
- `best_hunk_token_precision`
- `best_hunk_token_f1`
- `best_hunk_contiguous_line_ratio`
- `best_hunk_token_lcs_recall`
- `best_hunk_size_ratio`
- `meaningful_anchor_recall`
- `candidate_hunk_count`

## 6. Language-Aware Support

We added language-aware comparison because the examples cover many languages and file formats.

Priority languages discussed:

```text
Go, Python, C++, Rust, Java
```

Additional P1 group:

```text
HTML, Groovy, HCL, Jupyter Notebook, Shell, TypeScript, C, JavaScript
```

Implemented behavior:

- extension-based language detection
- Python-aware tokenization
- JSON/YAML/Markdown/Dockerfile handling
- Pygments fallback tokenization
- Jupyter Notebook code-cell extraction instead of raw `.ipynb` JSON comparison
- optional local Tree-sitter structural scoring

Docs:

```text
ml/docs/p1-language-support-plan.md
ml/docs/p1-language-support-implementation.md
```

## 7. GumTree Decision

We considered GumTree for tree edit distance.

Decision:

```text
Keep GumTree optional. Use token, hunk, and local structural metrics as the default path.
```

Reason:

- broad language support is required
- parser failures must not block evaluation
- GumTree adds operational weight
- structural scoring should augment, not replace, token/hunk metrics

## 8. Notebook Pipeline

Current notebook sequence:

```text
01_collect/closed_pr_comment_pair_collection.ipynb
02_prepare/data_preparation.ipynb
03_evaluate/pr_suggestion_metric_evaluation.ipynb
04_visualize/metric_score_visualization.ipynb
05_external/import_hf_github_codereview.ipynb
06_train/train_metric_classifier.ipynb
07_visualize/model_performance_dashboard.ipynb
08_train/train_regression_coverage_model.ipynb
```

## 9. Visualization

Metric visualization notebook:

```text
ml/notebooks/04_visualize/metric_score_visualization.ipynb
```

Model dashboard notebook:

```text
ml/notebooks/07_visualize/model_performance_dashboard.ipynb
```

Exported charts live in:

```text
ml/reports/model_performance_dashboard/
```

Important chart exports:

```text
headline_model_comparison.png
confusion_matrices.png
performance_by_source.png
feature_importance.png
model_confidence.png
metric_distributions_by_label.png
metric_scatter_correctness.png
percentage_bucket_distribution.png
rule_metric_bucket_confusion.png
model_coarse_bucket_confusion.png
```

## 10. Hugging Face Dataset Import

We created a notebook to import and transform:

```text
ronantakizawa/github-codereview
```

Notebook:

```text
ml/notebooks/05_external/import_hf_github_codereview.ipynb
```

Output:

```text
ml/data/external/github_codereview/dataset/
```

Problem found:

```text
HF streaming could hang or run too long.
```

Fixes:

- `REFRESH_IMPORT = False` by default
- local files load automatically when present
- `TARGET_ROWS`
- `MAX_SCANNED_ROWS`
- progress logging
- partial interrupt handling

Result:

```text
Existing local import loads 219 examples without streaming HF again.
```

## 11. Classifier Model

Classifier notebook:

```text
ml/notebooks/06_train/train_metric_classifier.ipynb
```

Saved artifacts:

```text
ml/models/pr_suggestion_coverage/model.joblib
ml/models/pr_suggestion_coverage/feature_schema.json
ml/models/pr_suggestion_coverage/evaluation_report.json
```

Models tested:

- logistic regression
- random forest
- histogram gradient boosting

Important split fix:

```text
Initial group split was too coarse for internal data because everything is one repo.
We changed it to source-aware, PR-level grouped split.
```

Current saved classifier:

```text
random_forest
```

Latest classifier results after relabeling and bucket fix:

```text
overall accuracy: 85.95%
overall macro F1: 84.57%
overall percentage MAE: 8.76
internal accuracy: 77.14%
internal macro F1: 75.66%
internal percentage MAE: 14.86
```

## 12. Inference Helper

Reusable inference helper:

```text
ml/src/pr_suggestion_metrics/model_inference.py
```

Exports:

```python
predict_coverage_labels(...)
predict_coverage_percentages(...)
prepare_model_features(...)
```

Classifier inference:

```python
import pandas as pd
from pr_suggestion_metrics import predict_coverage_labels

metric_rows = pd.read_csv("ml/reports/metric_scores.csv")
predictions = predict_coverage_labels(metric_rows)
```

Regression inference:

```python
import pandas as pd
from pr_suggestion_metrics import predict_coverage_percentages

metric_rows = pd.read_csv("ml/reports/metric_scores.csv")
predictions = predict_coverage_percentages(metric_rows)
```

## 13. Bucketed Target

We moved from only four coarse labels:

```text
0%, partial, mostly, 100%
```

to percentage buckets:

```text
0
1-10
11-20
21-30
31-40
41-50
51-60
61-70
71-80
81-90
91-100
```

Important rule:

```text
100 is not a bucket name.
100% maps to 91-100.
```

Coarse labels are derived from percentage:

```text
0      -> 0%
1-59   -> partial
60-89  -> mostly
90-100 -> 100%
```

## 14. Regression Model

Regression notebook:

```text
ml/notebooks/08_train/train_regression_coverage_model.ipynb
```

Purpose:

```text
Predict a 0-100 landed percentage, then bucket the prediction.
```

Models tested:

- ridge
- KNN regressor
- random forest regressor
- extra trees regressor
- gradient boosting regressor
- histogram gradient boosting regressor

KNN was included as a similarity-style baseline. It did not win.

Saved artifacts:

```text
ml/models/pr_suggestion_coverage_regression/model.joblib
ml/models/pr_suggestion_coverage_regression/feature_schema.json
ml/models/pr_suggestion_coverage_regression/evaluation_report.json
```

Current saved regression model:

```text
extra_trees
```

Latest regression results after relabeling and bucket fix:

```text
overall MAE: 7.45
overall bucket exact accuracy: 50.41%
overall bucket +/-1 accuracy: 86.78%
overall dangerous error rate: 0%
```

Internal-only regression results:

```text
internal MAE: 11.07
internal bucket exact accuracy: 44.29%
internal bucket +/-1 accuracy: 78.57%
internal dangerous error rate: 0%
```

Observation:

```text
Regression reduces dangerous high/low mistakes, but exact bucket accuracy is still not production-grade.
```

## 15. Labeling Prompts

Original coarse-label prompt:

```text
ml/docs/prompts/llm_labeling_prompt.md
```

New bucket-label prompt:

```text
ml/docs/prompts/llm_bucket_labeling_prompt.md
```

The bucket prompt specifies:

- input files
- exact `labels.csv` fields
- exact `llm_labels.jsonl` fields
- bucket scheme
- coarse label mapping
- accuracy requirements
- final/merged diff comparison rule
- validation checks
- `100 -> 91-100`

Core labeling rule:

```text
Measure whether suggested_diff appears in the merged/final landed_diff.
```

## 16. Relabeling Review And Fix

After the relabeling pass, we reviewed:

```text
labels.csv
llm_labels.jsonl
```

Initial QA found:

```text
279 dataset rows
279 labels.csv rows
279 llm_labels.jsonl rows
0 duplicate IDs
0 missing IDs
```

Issue found:

```text
104 examples used expected_percentage_bucket=100
```

Fix applied:

```text
labels.csv: fixed 104 rows
llm_labels.jsonl: fixed 104 rows
```

Final QA:

```text
issues: 0
```

Current label distribution:

```text
100%: 104
mostly: 70
0%: 70
partial: 35
```

Current bucket distribution:

```text
91-100: 104
0: 70
71-80: 42
81-90: 28
41-50: 20
31-40: 10
21-30: 4
11-20: 1
```

Confidence distribution:

```text
high: 178
medium: 99
low: 2
```

## 17. Evaluator Bucket Bug

After fixing labels, metric regeneration still produced bucket `100`.

Root cause in `evaluate_metrics.py`:

```python
if bounded_percentage == 100:
    return "100"
```

Fix:

```text
Removed the special case so 100 maps to 91-100.
```

Validation:

```text
_percentage_bucket(0)   -> 0
_percentage_bucket(91)  -> 91-100
_percentage_bucket(100) -> 91-100
```

After regeneration:

```text
ml/reports/metric_scores.csv mismatches: 0
ml/data/processed/pr_suggestion_coverage/dataset/metric_scores.csv mismatches: 0
```

## 18. Current Status

The pipeline now supports:

1. Loading suggestion/final diff examples.
2. Labeling with coarse labels, exact percentages, and buckets.
3. Computing deterministic similarity metrics.
4. Candidate hunk comparison.
5. Language-aware tokenization and optional structural scoring.
6. Metric visualization.
7. Classifier training.
8. Regression training.
9. Model inference for labels and percentages.

Current saved classifier:

```text
random_forest
```

Current saved regression model:

```text
extra_trees
```

## 19. Remaining Risks

- Internal validation set is still small.
- Bucket distribution is sparse for low/mid buckets.
- HF examples are easier than internal examples.
- Exact bucket accuracy is not yet strong enough for a production claim.
- Model quality depends heavily on label quality.

Recommended next steps:

1. Add more internal examples, especially for sparse buckets.
2. Review low-confidence examples manually.
3. Use the bucket prompt for another labeling pass.
4. Regenerate metrics after label changes.
5. Retrain classifier and regression models.
6. Treat internal validation as the main decision metric.
7. Consider a hybrid policy:

```text
rule metric for exact bucket confidence
regression model for percentage estimate and dangerous-error reduction
```

## 20. Useful Commands

Regenerate internal metric scores:

```bash
PYTHONPATH=ml/src ml/.venv/bin/python ml/src/pr_suggestion_metrics/evaluate_metrics.py \
  --dataset-dir ml/data/processed/pr_suggestion_coverage/dataset \
  --output ml/reports/metric_scores.csv
```

Train classifier:

```bash
MPLCONFIGDIR=ml/.matplotlib-cache PYTHONPATH=ml/src ml/.ml-venv/bin/python ml/.ml-venv/bin/jupyter-nbconvert \
  --to notebook --execute ml/notebooks/06_train/train_metric_classifier.ipynb \
  --output /tmp/train_metric_classifier.ipynb \
  --ExecutePreprocessor.timeout=900
```

Train regression model:

```bash
MPLCONFIGDIR=ml/.matplotlib-cache PYTHONPATH=ml/src ml/.ml-venv/bin/python ml/.ml-venv/bin/jupyter-nbconvert \
  --to notebook --execute ml/notebooks/08_train/train_regression_coverage_model.ipynb \
  --output /tmp/train_regression_coverage_model.ipynb \
  --ExecutePreprocessor.timeout=900
```

## 21. HF Relabel And Retrain Pass

We relabeled the Hugging Face code review dataset in:

```text
ml/data/external/github_codereview/dataset/
```

Rows relabeled and validated:

```text
2500
```

Coarse label counts:

```text
100%: 1192
mostly: 285
partial: 487
0%: 536
```

Bucket counts:

```text
0: 536
1-10: 71
11-20: 75
21-30: 63
31-40: 69
41-50: 169
51-60: 51
61-70: 163
71-80: 50
81-90: 211
91-100: 1042
```

Low-confidence examples to manually inspect:

```text
88c8321d58d58b11
0b2467e4fe43b4f9
fd3a083099b6c8d8
```

After relabeling, HF metrics were regenerated:

```bash
PYTHONPATH=ml/src ml/.ml-venv/bin/python ml/src/pr_suggestion_metrics/evaluate_metrics.py \
  --dataset-dir ml/data/external/github_codereview/dataset \
  --output ml/data/external/github_codereview/metric_scores.csv
```

Standalone metric comparison on the full HF set:

```text
baseline deterministic_landed_estimate accuracy: 0.760
new clone-style metric stack accuracy: 0.676
baseline MAE: 16.06
new metric MAE: 16.76
```

The metric stack alone is not better than the deterministic baseline on this HF split. It overpredicts `mostly`, but it still provides useful features for learned models.

Retrained classifier results:

```text
hist_gradient_boosting: accuracy=0.812, macro_f1=0.736, MAE=8.56
random_forest: accuracy=0.802, macro_f1=0.741, MAE=8.69
logistic_regression: accuracy=0.754, macro_f1=0.699, MAE=10.15
rule_based_current: accuracy=0.682, macro_f1=0.609, MAE=13.92
```

Retrained regression results:

```text
saved model: extra_trees
extra_trees: MAE=8.37, R2=0.831, exact_bucket=0.571, within_1_bucket=0.812, dangerous_error=0.001
random_forest: MAE=8.42, R2=0.839, exact_bucket=0.552, within_1_bucket=0.793, dangerous_error=0.004
hist_gradient_boosting: MAE=9.00, R2=0.833, exact_bucket=0.559, within_1_bucket=0.789, dangerous_error=0.004
rule_metric_percentage: MAE=15.32, R2=0.529, exact_bucket=0.577, within_1_bucket=0.699, dangerous_error=0.028
```

Interpretation:

- The learned models now beat the rule metric strongly on percentage MAE.
- Exact bucket accuracy is still only moderate because 10-point buckets are strict.
- `within_1_bucket` is much stronger and probably the more realistic operational signal.
- Dangerous error rate is very low for the saved regression model.
- Next quality gain should come from more manually checked labels, especially ambiguous `partial` and `mostly` examples.
