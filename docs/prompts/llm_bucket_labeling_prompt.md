# LLM Prompt: Label Suggestion Coverage With 0-100 Buckets

You are labeling code review suggestion examples for a machine learning dataset.

The goal is **high-accuracy labels** for measuring whether a suggested code change actually appears in the merged/final PR code or diff.

This is not a style review. This is not intent classification. Your job is to compare:

```text
suggested_diff -> landed_diff
```

and estimate how much of the suggested change landed in the final merged PR.

## Input Files

Dataset folder:

```text
/Users/I551270/Documents/GitHub/pipeline-fl-control-plane/ml/data/processed/pr_suggestion_coverage/dataset/
```

Primary examples:

```text
/Users/I551270/Documents/GitHub/pipeline-fl-control-plane/ml/data/processed/pr_suggestion_coverage/dataset/dataset.jsonl
```

Each JSONL row contains fields such as:

```text
example_id
pr_url
repo
suggestion_source
suggested_diff
landed_diff
deterministic_landed_estimate
file_overlap_ratio
changed_line_overlap_ratio
suggested_stats
landed_stats
metadata
```

Existing label sheet to update:

```text
/Users/I551270/Documents/GitHub/pipeline-fl-control-plane/ml/data/processed/pr_suggestion_coverage/dataset/labels.csv
```

Detailed label output to create/update:

```text
/Users/I551270/Documents/GitHub/pipeline-fl-control-plane/ml/data/processed/pr_suggestion_coverage/dataset/llm_labels.jsonl
```

## Core Labeling Question

For each `example_id`:

```text
How much of suggested_diff appears in the merged/final landed_diff?
```

Measure implementation overlap, not intent alone.

The correct label is based on whether the suggested code, logic, structure, behavior, or equivalent implementation appears in the final PR diff.

## Main Rule

Only give credit for parts of the suggestion that are actually present in the landed/final change.

Count as landed:

- the exact suggested lines
- the same code with variable/function renames
- the same logic with formatting changes
- the same behavior moved to another nearby location
- the same implementation split across multiple files
- the same code after import ordering, typing, or style cleanup

Do not count as landed:

- same file path only
- same broad topic only
- surrounding context that was already present
- unrelated changes in the PR
- a different implementation that solves a similar problem but does not preserve the suggested logic
- deleted code that merely resembles the suggestion
- comments/documentation unless the suggestion itself was comments/documentation

If the final PR solves the same issue with a different implementation, assign only the percentage corresponding to the overlap with the suggested implementation.

## Required Percentage Label

Assign `expected_landed_percentage` as an integer from `0` to `100`.

Use the whole range. Do not collapse everything into only `0`, `40`, `80`, and `100`.

Guidance:

```text
0       Nothing meaningful from the suggestion landed.
1-10    Tiny trace only; mostly absent.
11-20   Very small fragment landed.
21-30   Some minor supporting piece landed, but most is absent.
31-40   Clear partial implementation, but important suggested logic is missing.
41-50   About half of the meaningful suggestion landed.
51-60   More than half landed, but substantial pieces are missing or changed.
61-70   Most core behavior landed, with notable omissions or rewrites.
71-80   Main suggested logic landed, with meaningful edits/refactoring.
81-90   Almost all suggested logic landed, with small non-trivial changes.
91-100  Suggestion landed essentially as-is; only trivial formatting, naming, or context changed.
```

## Required Bucket Label

Derive `expected_percentage_bucket` from `expected_landed_percentage` exactly as follows:

```text
0       -> 0
1-10    -> 1-10
11-20   -> 11-20
21-30   -> 21-30
31-40   -> 31-40
41-50   -> 41-50
51-60   -> 51-60
61-70   -> 61-70
71-80   -> 71-80
81-90   -> 81-90
91-100  -> 91-100
```

Important: `100` is not a valid bucket name. A percentage of `100` must use bucket `91-100`.

## Coarse Label

Also assign the existing coarse `label` field from the percentage:

```text
0                 -> 0%
1-59              -> partial
60-89             -> mostly
90-100            -> 100%
```

The coarse `label` must always match `expected_landed_percentage` using this mapping.

## Review Procedure For Each Example

1. Read `suggested_diff` first.
2. Identify the meaningful suggested change:
   - added lines
   - removed lines if relevant
   - logic/behavior
   - function/class/config key names
   - file path context
3. Read `landed_diff`.
4. Ignore unrelated PR changes.
5. Find whether the suggestion appears in the final merged diff.
6. Decide the exact `expected_landed_percentage`.
7. Derive `expected_percentage_bucket`.
8. Derive coarse `label`.
9. Write concrete evidence explaining what matched and what did not.

## Special Cases

### Variable Or Function Renames

Renames should not automatically reduce the score if the same logic landed.

Example:

```text
suggested: result = fetch_value()
landed:    response = fetch_value()
```

This can still be high coverage if the semantic change is the same.

### Same Intent, Different Implementation

Do not give full credit.

If the PR solves the same problem differently, use `partial` or `mostly` depending on how much suggested logic survived.

### Extra PR Changes

Ignore extra unrelated changes. The label is only about the suggestion.

### File Moves Or Renames

If the same suggested logic lands in another file due to a rename or refactor, count it as landed.

### Tiny Suggestions

For one-line suggestions, be strict but fair:

- exact or equivalent line landed: usually `90-100`
- same idea but different expression: often `60-90`
- only same file/context: `0`

### Empty Or Non-Code Suggestions

If `suggested_diff` contains no meaningful added/changed content, set:

```text
expected_landed_percentage: 0
expected_percentage_bucket: 0
label: 0%
confidence: low or medium
```

and explain that there was no meaningful suggested code to compare.

## Required `labels.csv` Fields

Update or create `labels.csv` with exactly these columns:

```text
example_id
label
expected_landed_percentage
expected_percentage_bucket
label_notes
suggested_label
suggested_percentage
suggested_rationale
pr_url
repo
suggestion_source
deterministic_landed_estimate
file_overlap_ratio
changed_line_overlap_ratio
suggested_files
landed_files
```

Field instructions:

- `example_id`: copy from `dataset.jsonl`.
- `label`: coarse label derived from `expected_landed_percentage`.
- `expected_landed_percentage`: your final 0-100 judgment.
- `expected_percentage_bucket`: bucket derived from `expected_landed_percentage`.
- `label_notes`: short evidence-based explanation.
- `suggested_label`: preserve existing value if present; otherwise use deterministic/baseline estimate label.
- `suggested_percentage`: preserve existing value if present; otherwise use `deterministic_landed_estimate`.
- `suggested_rationale`: preserve existing value if present; otherwise summarize deterministic/baseline signals.
- `pr_url`, `repo`, `suggestion_source`, `deterministic_landed_estimate`, `file_overlap_ratio`, `changed_line_overlap_ratio`: copy from source data when available.
- `suggested_files`: semicolon-separated files touched by `suggested_diff`.
- `landed_files`: semicolon-separated files touched by `landed_diff`.

Do not leave `label`, `expected_landed_percentage`, `expected_percentage_bucket`, or `label_notes` empty.

## Required `llm_labels.jsonl` Fields

Write one JSON object per example:

```json
{
  "example_id": "...",
  "pr_url": "...",
  "repo": "...",
  "label": "0% | partial | mostly | 100%",
  "expected_landed_percentage": 0,
  "expected_percentage_bucket": "0 | 1-10 | 11-20 | 21-30 | 31-40 | 41-50 | 51-60 | 61-70 | 71-80 | 81-90 | 91-100",
  "reasoning": "Short, concrete explanation of why this percentage is correct.",
  "matched_parts": [
    "Specific suggested code/logic that appears in landed_diff."
  ],
  "missing_or_changed_parts": [
    "Specific suggested code/logic that is absent or materially changed."
  ],
  "evidence": {
    "suggested_files": ["..."],
    "landed_files": ["..."],
    "matched_line_examples": ["..."],
    "non_matching_line_examples": ["..."]
  },
  "confidence": "low | medium | high",
  "ambiguity_flags": [
    "optional short flags such as renamed_symbol, moved_file, equivalent_rewrite, tiny_suggestion, noisy_landed_diff"
  ]
}
```

## Accuracy Requirements

Prioritize correctness over speed.

Before finalizing each row, verify:

```text
expected_landed_percentage is an integer from 0 to 100
expected_percentage_bucket matches expected_landed_percentage
label matches expected_landed_percentage
reasoning cites actual matched or missing code/logic
matched_parts and missing_or_changed_parts are concrete
```

At the end, run consistency checks:

```text
number of dataset.jsonl rows == number of labels.csv data rows == number of llm_labels.jsonl rows
no duplicate example_id values
no missing example_id values
no invalid labels
no invalid buckets
no bucket named 100
all percentage 100 rows use bucket 91-100
labels.csv and llm_labels.jsonl agree on example_id, label, expected_landed_percentage, and expected_percentage_bucket
```

## Output Summary

After labeling, report:

```text
total examples
labeled examples
counts by coarse label
counts by percentage bucket
low-confidence examples
examples with ambiguity_flags
any skipped or malformed examples
output file paths
```

Do not stop after a few examples. Process all examples. If interrupted, resume from existing `llm_labels.jsonl` and skip already labeled `example_id` values.
