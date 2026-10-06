# Semantic PR Suggestion Coverage

Research tooling for estimating how much of a code-review suggestion appears in a merged pull request.

## Current Status

The package provides two explicitly separate outputs:

- **Deterministic evidence:** strict same-file matches separated from operation-strict, path-relaxed cross-file matches.
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
    model_dir=Path("/path/to/trusted-percentage-model"),
)

if result.status == "predicted":
    print(result.model_predicted_percentage)
else:
    print(result.applicability_reasons)
```

The result is a versioned `CoverageResult` containing the raw and rounded estimate, uncertainty status, deterministic evidence, input hashes, artifact hashes, and warnings. Result schema `1.1` embeds evidence schema `1.1` for both predictions and abstentions.

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

| Edit shape | Deterministic evidence | Learned estimator |
|---|---:|---:|
| Single-file addition | Yes | Yes |
| Multiple hunks | Yes | Abstains |
| Multiple files | Yes | Abstains |
| Deletion or replacement | Yes | Abstains |
| Rename or cross-file move | Yes | Abstains |
| Final-state semantic equivalence | No | No |

## Metric Vocabulary

- `suggestion_coverage_percentage`: primary learned estimate.
- `change_coverage_evidence.strict_same_file`: same operation, normalized content, and repository-relative path.
- `change_coverage_evidence.relaxed_cross_file`: same operation and normalized content on a different path.
- `final_diff_recall`: PR-scope diagnostic.

Both evidence buckets use `total_suggested_units` as their denominator. In evidence schema `1.1`, top-level `coverage_percentage`, `matched_units`, `matched_by_kind`, and `matches` remain for one compatibility cycle; they combine strict and relaxed matches and must not be interpreted as strict evidence.

Token, file, and line precision/recall are diagnostics. Token overlap is operation-aware, so additions cannot match removals. The explicitly named `relaxed_content_token` diagnostic ignores operation polarity. The project does not combine these diagnostics into an aggregate coverage score.

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
notebooks/     historical and exploratory analyses
reports/       generated evaluation outputs
research/      archived, unsupported research artifacts
src/           reusable Python package
tests/         regression, benchmark, metric, and model tests
```

Key documents:

- [`docs/README.md`](docs/README.md) — documentation map and source-of-truth rules.
- [`docs/architecture.md`](docs/architecture.md) — current boundaries and target dual-model architecture.
- `ROADMAP.md`
- `IMPLEMENTATION_PLAN.md`
- `docs/senior-code-review.md`
- `docs/implementation-progress.md`
- `docs/data-card.md`
- `docs/model-card.md`
- `docs/annotation-guide.md`
- `docs/reproducibility.md`
- `docs/pr-suggestion-diff-metrics.md`
- `research/archive/bucket-era/README.md`

## Development

```bash
uv run --locked --extra dev ruff check src tests
uv run --locked --extra dev mypy src/pr_suggestion_metrics
uv build
```

`uv.lock` is the dependency source of truth. Model files are intentionally not bundled in the wheel; callers must provide an explicit trusted `model_dir`.
