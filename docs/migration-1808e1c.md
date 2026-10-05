# Migration Guide: Non-LLM Pipeline Hardening

**Change:** `1808e1c` (`[feat] Harden suggestion coverage pipeline`)  
**Scope:** diff metrics, benchmark processing, training, inference, packaging, CI, and documentation  
**Excluded:** replacement or validation of the existing LLM-assisted labels

## Summary

This change replaces several disconnected or ambiguous paths with one supported workflow:

```text
provenance-complete candidates
-> deterministic split planning
-> benchmark freezing
-> canonical feature generation
-> development-selected training
-> grouped uncertainty calibration
-> frozen evaluation
```

## Breaking Changes

### Explicit Model Directory

Model-loading and inference functions no longer assume that model artifacts exist beside the source checkout.

Before:

```python
predictions = predict_coverage_percentages(rows)
result = predict_coverage_from_diffs(suggested_diff, merged_diff)
```

After:

```python
from pathlib import Path

model_dir = Path("models/pr_suggestion_coverage_regression")
predictions = predict_coverage_percentages(rows, model_dir=model_dir)
result = predict_coverage_from_diffs(
    suggested_diff,
    merged_diff,
    model_dir=model_dir,
)
```

This makes installed-wheel behavior explicit and avoids hidden repository-relative paths.

### Typed Inference Result

`predict_coverage_from_diffs` now returns a versioned Pydantic `CoverageResult` instead of an unstructured dictionary.

Preferred access:

```python
if result.status == "predicted":
    print(result.model_raw_percentage)
    print(result.model_predicted_percentage)
else:
    print(result.applicability_reasons)
```

Temporary dictionary-style field access remains available for migration, but new code should use attributes and `result.model_dump(mode="json")` for serialization.

The result shape is stable across predictions and abstentions. It includes:

- result schema and metric names;
- raw and rounded estimates;
- uncertainty status and interval;
- applicability reasons;
- exact change-unit evidence;
- input and artifact hashes;
- warnings.

### Diff Diagnostic Semantics

Token overlap now uses changed code only. Diff headers, paths, hunk coordinates, metadata, and context lines are excluded.

Changed-line matching now uses:

```text
(operation, repository-relative path, normalized content)
```

Blank changed lines are excluded from coverage denominators.

The unsupported equal-weight `aggregate_diff_f1` property and report output were removed. Token, file, and line precision/recall remain diagnostics only.

### Dependency Installation

The root `requirements.txt` was removed. Use the locked `uv` workflow:

```bash
uv sync --locked --extra test
```

The `test` extra now includes the public collector dependencies required during test collection.

## New Supported Commands

### Plan Leakage-Resistant Splits

```bash
uv run --locked pr-suggestion-plan-splits \
  --examples data/benchmark-source/examples.jsonl \
  --output /secure/splits.csv \
  --report /secure/split-report.json \
  --policy repository_disjoint
```

The planner keeps pull requests and near-duplicate suggestions together. With enough independent groups, it creates separate train, development, calibration, and test splits.

### Build Frozen Features

```bash
uv run --locked pr-suggestion-build-features \
  --benchmark-dir /secure/frozen-benchmark \
  --output-dir /secure/frozen-features
```

This command reads only non-test benchmark splits. Unsupported diff shapes are written to `feature_abstentions.jsonl` rather than silently dropped.

### Train the Supported Model

```bash
uv run --locked pr-suggestion-train \
  --features /secure/frozen-features/features.csv \
  --model-dir /secure/model
```

The trainer:

- fits candidates on `train`;
- selects using `development` only;
- reserves `calibration` rows;
- rejects any input containing test rows;
- removes constant and explicitly excluded leakage-prone features;
- writes model, schema, training report, and integrity manifest together.

## Benchmark Contract Changes

- Dataset generation now writes `benchmark_candidates.jsonl` using a dedicated label-free schema.
- Null legacy label fields no longer block annotation-packet preparation.
- Provenance supports multiple file snapshots and rename mappings.
- Confirmatory candidates are limited to anchored inline review suggestions.
- Duplicate annotator records are rejected.
- Exact and normalized-token near duplicates cannot cross split boundaries.
- Abstentions are preserved in `abstained.jsonl` instead of rejecting the entire freeze.
- Calibration has its own optional split and output artifact.
- Agreement reports include abstention agreement, unit-definition overlap, ICC, and weighted kappa.

## Evaluation Changes

- Calibration uses raw continuous model predictions.
- Residuals are calibrated at the independent-group level.
- Frozen evaluation reports grouped bootstrap confidence intervals.
- Reports include repository, edit-type, and suggestion-size subgroup metrics.
- Private labels and consumption receipts can be supplied from a separate protected location.

## Canonical Diff Parser

All supported metric paths now consume `pr_suggestion_metrics.diff.parser`.

The parser records:

- old and new paths;
- additions, deletions, and context;
- hunk identity;
- source and target line numbers;
- rename metadata.

The exact evidence layer still allows explicit cross-file matches, but labels them as moves. Path-aware line diagnostics do not grant credit across unrelated files.

## Upgrade Checklist

1. Replace `requirements.txt` installation with `uv sync --locked`.
2. Pass `model_dir` explicitly to every inference function.
3. Replace dictionary-centric result handling with `CoverageResult` attributes.
4. Remove uses of `aggregate_diff_f1`.
5. Update changed-line keys from `(operation, content)` to `(operation, path, content)`.
6. Generate benchmark candidates, splits, and features with the new commands.
7. Keep calibration data separate from development selection and test evaluation.
8. Run the validation commands below.

## Validation

```bash
uv lock --check
uv run --locked --all-extras pytest -q
uv run --locked --extra dev ruff check src tests
uv build
```

At implementation time, the repository passed 77 tests, Ruff, focused mypy checks, wheel creation, and an isolated installed-wheel smoke test.
