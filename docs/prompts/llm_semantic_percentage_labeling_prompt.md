# LLM Prompt: Semantic Percentage Labels For Suggestion Coverage

You are labeling a machine learning dataset for code suggestion coverage.

The task is to decide, with code-level semantic reasoning, what percentage of a review suggestion landed in the final merged PR diff.

The source-of-truth label is:

```text
expected_landed_percentage
```

It must be an integer from `0` to `100`.

Buckets and coarse labels are derived after that. Do not start from a bucket. Do not start from a coarse label.

## Core Question

For each example:

```text
What percentage of the suggested code change is implemented in the landed diff?
```

You must compare implementation meaning, not only text overlap.

## Inputs

Each example contains:

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
suggested_files
landed_files
```

Treat deterministic estimates and overlap ratios as weak hints only. They are not labels.

## What Counts As Landed

Give credit when the landed diff preserves the suggestion's meaningful implementation.

Count as landed:

- exact suggested code
- equivalent logic with renamed variables, functions, classes, or imports
- equivalent logic after formatting, typing, linting, or import-order changes
- equivalent control flow expressed differently
- equivalent configuration values or constants moved to another location
- suggested behavior split across helper functions or files
- suggested behavior moved because of a refactor
- documentation/comment changes, but only when the suggestion itself was documentation/comment text

Do not give credit for:

- same file only
- same topic only
- unrelated nearby code
- context lines that were already present
- broad intent solved by a different implementation
- a deletion that only resembles the suggestion
- generic lines such as braces, imports, `return null`, or variable declarations unless they are central to the suggestion

## Semantic Review Procedure

For each example, do this in order:

1. Identify the suggestion's meaningful units.
   - API calls
   - assignments
   - conditionals
   - loops
   - error handling
   - constants/config keys
   - function signatures
   - data shape changes
   - tests/assertions
   - comments/docs, if relevant
2. Assign each unit an approximate importance weight.
   - Core behavior gets more weight.
   - Supporting syntax gets less weight.
   - Boilerplate gets little or no weight.
3. Inspect the landed diff for equivalent implementation.
4. For every important unit, decide whether it is:
   - landed exactly
   - landed equivalently
   - landed partially
   - absent
   - replaced by a different implementation
5. Estimate the final percentage from the weighted semantic coverage.
6. Derive the bucket and coarse label from the percentage.

## Percentage Scale

Use the full 0-100 range.

```text
0       Nothing meaningful from the suggestion landed.
1-10    Tiny semantic trace only.
11-20   Very small fragment landed.
21-30   Minor supporting part landed, core idea absent.
31-40   Clear partial implementation, important logic missing.
41-50   Around half of the meaningful suggestion landed.
51-60   More than half landed, but substantial parts missing.
61-70   Most core behavior landed, with notable omissions or rewrites.
71-80   Main logic landed, with meaningful edits/refactoring.
81-90   Almost all logic landed, with small non-trivial changes.
91-100  Semantically landed essentially as suggested; only trivial edits.
```

Use exact values when justified. For example, prefer `73` over `70` if that is the best estimate.

## Coarse Label Derivation

After choosing `expected_landed_percentage`, derive `label` exactly:

```text
0      -> 0%
1-59   -> partial
60-89  -> mostly
90-100 -> 100%
```

## Bucket Derivation

After choosing `expected_landed_percentage`, derive `expected_percentage_bucket` exactly:

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

`100` is not a valid bucket name. Percentage `100` belongs to `91-100`.

## Hard Cases

### Rename Only

If only names changed but the same behavior landed, keep the percentage high.

### Same Intent, Different Code

Do not give full credit. Score only the semantic parts that overlap with the suggestion.

### Tiny Suggestions

Be strict but fair.

- one-line equivalent landed: usually `90-100`
- same idea with changed expression: often `60-90`
- same file or topic only: `0`

### Large Landed Diff

Ignore unrelated landed changes. The question is only whether the suggestion landed.

### Large Suggestion

Weight important behavioral units. Do not let boilerplate dominate.

### Tests

If the suggestion is a test, score whether the same assertion/setup/test intent landed.

### Config / YAML / HCL / Dockerfile / Makefile / Shell

Score semantic effects: keys, values, commands, flags, dependencies, conditions, stages, and ordering when ordering changes behavior.

## Required JSONL Output

Return one JSON object per example:

```json
{
  "example_id": "...",
  "label": "0% | partial | mostly | 100%",
  "expected_landed_percentage": 0,
  "expected_percentage_bucket": "0 | 1-10 | 11-20 | 21-30 | 31-40 | 41-50 | 51-60 | 61-70 | 71-80 | 81-90 | 91-100",
  "reasoning": "Short semantic explanation of why this exact percentage is correct.",
  "semantic_units": [
    {
      "unit": "Specific suggested behavior/code unit.",
      "importance": "low | medium | high",
      "status": "landed_exactly | landed_equivalently | landed_partially | absent | different_implementation",
      "evidence": "Concrete landed or missing evidence."
    }
  ],
  "matched_parts": ["Specific suggested code/logic that landed."],
  "missing_or_changed_parts": ["Specific suggested code/logic that did not land or changed materially."],
  "confidence": "low | medium | high",
  "ambiguity_flags": ["optional flags"]
}
```

## Quality Bar

Do not be lazy.

Before finalizing each row, check:

```text
percentage is based on semantic units, not raw line count
reasoning cites concrete matched or missing code/logic
bucket matches percentage
coarse label matches percentage
confidence is low when the diff is too noisy or ambiguous
```

The goal is high accuracy for predicting whether the suggested implementation appears in merged/final code.
