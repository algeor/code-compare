# Metric Improvement Plan

## Problem

The current clone-style metric stack does not perform well enough yet.

Current behavior from `ml/reports/metric_scores.csv`:

- baseline deterministic estimate accuracy: about `60%`
- new clone-style rule accuracy: about `55%`
- biggest issue: too many false `100%` predictions
- weak classes: `partial` and `mostly`

The main failure mode is simple:

> Small or generic suggestions can get high token overlap against a large PR diff, even when the suggestion did not meaningfully land.

Example pattern:

```text
line_recall = 0.0
token_recall = high
identifier_normalized_token_recall = very high
predicted_label = 100%
human_label = 0%
```

This means identifier-normalized token recall is useful, but too permissive when used alone.

## Improvement Strategy

Improve the system in this order:

```text
candidate chunking
-> anchor-aware matching
-> weighted token scoring
-> GumTree structural features
-> supervised classifier
```

## 1. Better Candidate Chunking

Do not compare a suggestion against all added lines in a whole file.

Instead, split the landed PR diff into candidate chunks:

- same-file hunks
- nearby added-line windows
- changed function bodies when parseable
- added classes or methods
- chunks containing overlapping identifiers, literals, or function names

Then score each suggestion against each candidate chunk and keep the best match.

```text
suggestion_score = max(score(suggestion, candidate_chunk) for candidate_chunk in candidate_chunks)
```

Why this helps:

- reduces false matches from large PR diffs
- makes scores easier to explain
- gives a concrete `best_file` and `best_hunk` as evidence

## 2. Anchor-Aware Matching

A high score should require at least one meaningful anchor.

Good anchors:

- function names
- method names
- imported symbols
- string literals
- numeric constants with domain meaning
- attribute chains like `task["requirement_location"]`
- exception names
- class names
- config keys

Weak anchors:

- punctuation
- `True` / `False` / `None`
- common keywords like `if`, `return`, `except`
- generic identifiers after normalization

Example rule:

```text
if identifier_normalized_recall >= 0.90 but meaningful_anchor_count == 0:
    do not predict 100%
```

This directly addresses cases where generic code shape matches but the actual suggestion did not land.

## 3. Weighted Token Scoring

Token recall should not treat all tokens equally.

Downweight generic tokens:

- punctuation: `=`, `:`, `,`, `(`, `)`
- common keywords: `if`, `else`, `return`, `try`, `except`
- generic literals: `None`, `True`, `False`, `0`, `1`

Upweight meaningful tokens:

- function names
- method calls
- class names
- exception names
- string literals
- config keys
- constants
- attribute names

Useful extra metric:

```text
weighted_token_recall = matched_token_weight / total_suggestion_token_weight
```

This should make tiny suggestions less likely to become false `100%` matches.

## 4. GumTree Structural Features

Use GumTree as a structural diagnostic, not the first-pass matcher.

Best use:

```text
candidate chunking finds likely PR chunk
-> GumTree compares suggestion against that chunk
-> GumTree ratios become classifier features
```

Useful GumTree columns:

- `gumtree_available`
- `gumtree_language`
- `gumtree_operation_count`
- `gumtree_insert_ratio`
- `gumtree_delete_ratio`
- `gumtree_update_ratio`
- `gumtree_move_ratio`
- `gumtree_error`

Interpretation:

| Signal | Meaning |
|---|---|
| high update ratio | likely same structure with renamed identifiers/literals |
| high insert ratio | suggestion landed but PR added extra logic around it |
| high delete ratio | suggestion was replaced or mostly removed |
| high move ratio | suggestion may have landed in a different location |
| low operation count | suggestion and candidate are structurally close |

Important limitation:

GumTree requires language parsers. It should be supported where parser setup exists, and skipped for unsupported file types.

## 5. Supervised Classifier

Once better features exist, train a small classifier over them.

Start simple:

- logistic regression
- random forest
- XGBoost
- LightGBM

Feature candidates:

- `deterministic_landed_estimate`
- `file_overlap_ratio`
- `changed_line_overlap_ratio`
- `line_recall`
- `token_recall`
- `identifier_normalized_token_recall`
- `weighted_token_recall`
- `meaningful_anchor_count`
- `meaningful_anchor_recall`
- `best_candidate_chunk_size`
- `gumtree_operation_count`
- `gumtree_insert_ratio`
- `gumtree_delete_ratio`
- `gumtree_update_ratio`
- `gumtree_move_ratio`

Prediction target:

```text
0% | partial | mostly | 100%
```

Use the current labels as ground truth.

## Evaluation Plan

Compare every new approach against the existing baseline.

Baseline:

```text
deterministic_landed_estimate accuracy ~= 60%
```

Report:

- accuracy
- macro F1
- per-class precision/recall/F1
- confusion matrix
- false `100%` predictions
- false `0%` predictions

The most important product metric is reducing false `100%` predictions, because those incorrectly claim a suggestion landed fully.

## Recommended Next Implementation

Implement these next:

1. Extract landed diff hunks by file.
2. Score each suggestion against candidate hunks, not whole files.
3. Add meaningful anchor extraction.
4. Add weighted token recall.
5. Re-run `03_evaluate` and inspect `04_visualize`.

Only after that, add GumTree into the classifier features.
