# PR Suggestion Diff Diagnostics

## Purpose

Diff precision and recall provide transparent lexical diagnostics. They do **not** measure semantic adoption and are not combined into a product score.

## Shared Parsing Contract

All diff diagnostics, feature extraction, and exact evidence use the canonical typed parser in `pr_suggestion_metrics.diff.parser`.

Each parsed changed line records:

- old and new file paths;
- operation type;
- hunk identity;
- source and target line numbers;
- original line text.

Formatting-only blank lines remain available to the parser but are excluded from coverage denominators.

## Diagnostics

### Changed-Code Token Precision

```text
matched changed-code tokens / suggestion changed-code tokens
```

Diff headers, paths, hunk coordinates, metadata, and context lines are excluded. The legacy raw-diff tokenizer remains available only as `raw_diff_word_tokens` for historical diagnostics.

### Final-Diff Token Recall

```text
matched changed-code tokens / merged-PR changed-code tokens
```

This describes PR scope, not the fraction of the suggestion that landed.

### Changed-File Overlap

File precision and recall compare canonical repository-relative paths. Renames use the final path; deletions use the original path.

### Path-Aware Changed-Line Precision

```text
matched (operation, path, normalized line) occurrences
-----------------------------------------------------
suggestion changed-line occurrences
```

Matching is one-to-one. Identical text in unrelated files does not receive credit.

## Exact Evidence Baseline

`analyze_change_coverage` supports additions, deletions, replacements, explicit renames, multiple files, and multiple hunks. It returns matched and unmatched units with paths and line locations.

Its result is an auditable exact-match baseline. It does not prove:

- semantic equivalence;
- causal use of a suggestion;
- absence before the suggestion;
- persistence in the final repository state.

## Learned Estimate

The learned raw-diff estimator currently supports only single-file, single-hunk, pure-addition suggestions. All other shapes return a typed `CoverageResult` with `status="abstained"` and explicit applicability reasons.

## Removed Metric

The former equal-weight average of token, file, and line F1 is not a supported metric. It had no defensible weighting theory and answered a symmetric similarity question rather than suggestion coverage.
