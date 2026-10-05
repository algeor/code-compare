# Semantic PR Suggestion Coverage

Research tooling for estimating how much of a code-review suggestion appears in a merged pull request.

## Current Status

The package provides two explicitly separate outputs:

- **Exact evidence:** path-aware, one-to-one normalized change-unit matching.
- **Experimental estimate:** a learned percentage for supported raw-diff inputs.

Neither output proves causality or final-state semantic equivalence. Unsupported edit shapes return a typed abstention instead of an invented score.

## Quick Start

```bash
uv sync --locked --extra test
uv run --locked --extra test pytest -q
```

Run inference with an explicit trusted model directory:

```python
from pathlib import Path

from pr_suggestion_metrics import predict_coverage_from_diffs

result = predict_coverage_from_diffs(
    suggested_diff,
    merged_pr_diff,
    model_dir=Path("models/pr_suggestion_coverage_regression"),
)

if result.status == "predicted":
    print(result.model_predicted_percentage)
else:
    print(result.applicability_reasons)
```

The result is a versioned `CoverageResult` containing the raw and rounded estimate, uncertainty status, exact evidence, input hashes, artifact hashes, and warnings.

## AI Reviewer Evaluation

Coverage measures whether a suggestion appears in merged code. It cannot say what the AI reviewer got wrong. Review quality is scored separately against atomic findings verified by tests, static analysis, specifications, or human review:

```python
from pr_suggestion_metrics import ReviewAssessmentUnit, evaluate_ai_review

evaluation = evaluate_ai_review(
    "review-42",
    [
        ReviewAssessmentUnit(
            unit_id="unsafe-fix",
            criterion="fix_safety",
            verdict="partially_correct",
            weight=2,
            ai_review_part="Catch every Exception and return None.",
            expected="Catch ValueError only and preserve unexpected failures.",
            explanation="The proposed fix hides unrelated defects.",
            evidence=["tests/test_parser.py::test_unexpected_error_propagates"],
            evidence_source="test",
            mistake_code="unsafe_fix",
        )
    ],
)

print(evaluation.score_percentage)
for deduction in evaluation.deductions:
    print(deduction.mistake_code, deduction.points_lost, deduction.explanation)
```

Every point below 100 maps to a concrete deduction such as an incorrect diagnosis, missed issue, wrong location, wrong severity, unsafe fix, weak rationale, or vague guidance. Use `summarize_ai_reviewer` to find recurring reviewer mistakes across many comments.

A local model may draft assessment units, but tests, static analysis, specifications, or humans must verify them. The merged PR is outcome context, not correctness ground truth.

## Capability Matrix

| Edit shape | Exact evidence | Learned estimator |
|---|---:|---:|
| Single-file addition | Yes | Yes |
| Multiple hunks | Yes | Abstains |
| Multiple files | Yes | Abstains |
| Deletion or replacement | Yes | Abstains |
| Rename or cross-file move | Yes | Abstains |
| Final-state semantic equivalence | No | No |

## Metric Vocabulary

- `suggestion_coverage_percentage`: primary learned estimate.
- `exact_change_unit_coverage_percentage`: transparent exact-match evidence.
- `final_diff_recall`: PR-scope diagnostic.
- `coverage_bucket`: display-only derivative.

Token, file, and line precision/recall are diagnostics. The project does not combine them into an aggregate coverage score.

## Benchmark Pipeline

Build label-free benchmark candidates while preparing the normal dataset:

```bash
uv run --locked pr-suggestion-build-dataset INPUT.jsonl --output-dir OUTPUT_DIR
```

Create deterministic leakage-resistant split assignments:

```bash
uv run --locked pr-suggestion-plan-splits \
  --examples OUTPUT_DIR/benchmark_candidates.jsonl \
  --output /secure/splits.csv \
  --report /secure/split-report.json \
  --policy repository_disjoint
```

After annotation and adjudication, freeze the benchmark:

```bash
uv run --locked pr-suggestion-freeze-benchmark \
  --examples OUTPUT_DIR/benchmark_candidates.jsonl \
  --annotations /secure/annotations.jsonl \
  --adjudications /secure/adjudications.jsonl \
  --splits /secure/splits.csv \
  --output-dir /secure/frozen-benchmark
```

Generate canonical model-ready features from non-test splits:

```bash
uv run --locked pr-suggestion-build-features \
  --benchmark-dir /secure/frozen-benchmark \
  --output-dir /secure/frozen-features
```

Select and train one supported model without reading test rows:

```bash
uv run --locked pr-suggestion-train \
  --features /secure/frozen-features/features.csv \
  --model-dir /secure/model
```

Abstained examples are preserved in dedicated artifacts. Calibration uses raw predictions and independent-group residuals.

## Repository Layout

```text
data/          research datasets and small fixtures
docs/          method, model, data, and reproducibility notes
models/        trusted local research artifacts
notebooks/     historical and exploratory analyses
reports/       generated evaluation outputs
src/           reusable Python package
tests/         regression, benchmark, metric, and model tests
```

Key documents:

- `docs/data-card.md`
- `docs/model-card.md`
- `docs/annotation-guide.md`
- `docs/reproducibility.md`
- `docs/pr-suggestion-diff-metrics.md`
- `docs/migration-1808e1c.md`

## Development

```bash
uv run --locked --extra dev ruff check src tests
uv run --locked --extra dev mypy \
  src/pr_suggestion_metrics/diff \
  src/pr_suggestion_metrics/benchmark \
  src/pr_suggestion_metrics/modeling \
  src/pr_suggestion_metrics/model_inference.py
uv build
```

`uv.lock` is the dependency source of truth. Model files are intentionally not bundled in the wheel; callers must provide an explicit trusted `model_dir`.
