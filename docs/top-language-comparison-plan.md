# Top Language Code Comparison Plan

## Goal

Improve snippet-to-merged-PR matching for the five highest-volume languages:

```text
Go, Python, C++, Rust, Java
```

The goal is not to perfectly understand every language at first. The goal is to reliably answer:

```text
Did this small suggested code change appear in the merged PR diff, possibly with small edits?
```

## Strategy

Use a layered approach.

```text
language detection
-> tokenization
-> normalization
-> hunk-local matching
-> optional structural scoring
-> supervised calibration
```

## Phase 1: Broad Tokenization

Add `Pygments` as the default tokenizer for Go, C++, Rust, and Java.

Keep the current Python tokenizer for Python because Python has a strong standard-library tokenizer.

Fallback order:

```text
Python file -> Python tokenizer
known structured format -> custom tokenizer
Go/C++/Rust/Java -> Pygments lexer
unknown -> regex fallback
```

Why this phase first:

- fast
- offline
- explainable
- works across all five languages
- avoids maintaining custom tokenizers per language

Output columns to add or keep:

```text
suggestion_language
tokenizer
tokenizer_fallback_reason
```

## Phase 2: Normalize Noise

Add two normalized token views:

```text
identifier_normalized_tokens
literal_normalized_tokens
```

Identifier normalization handles developer edits like:

```text
timeout -> request_timeout
client -> http_client
err -> error
```

Literal normalization handles edits like:

```text
30 -> 60
"dev" -> "prod"
true -> false
```

Metrics:

```text
token_recall
identifier_normalized_token_recall
literal_normalized_token_recall
identifier_and_literal_normalized_token_recall
```

## Phase 3: Compare Against Candidate Hunks

Do not compare the suggestion against the whole PR diff as one blob.

Compare it against likely candidate chunks:

```text
same-file added hunks
same-file neighboring hunks
same-extension hunks if file moved or renamed
high-anchor-overlap hunks across files
```

Keep the best candidate result:

```text
best_hunk_file
best_hunk_candidate_type
candidate_hunk_count
best_hunk_size
best_hunk_token_recall
best_hunk_identifier_normalized_recall
best_hunk_literal_normalized_recall
meaningful_anchor_recall
```

This is the most important part for small snippets because whole-PR comparison creates false positives.

Current implementation status: done.

Candidate types:

```text
same_file
neighboring_same_file
same_extension
anchor_overlap
```

Cross-file candidates are intentionally conservative. They can help moved/renamed files, but the final decision rule requires stronger anchor evidence before treating them like a strong match.

## Phase 4: Add Language-Specific Structural Scoring

Structural scoring is required for the top-language plan, but it should remain optional at runtime.

Run structural scoring after token metrics identify a likely candidate hunk.

This avoids expensive or brittle parsing on every possible chunk.

Recommended order:

| Language | Structural option | Priority |
|---|---|---|
| Python | Python `ast` now, Tree-sitter Python later if needed | High |
| Go | Tree-sitter Go or difftastic | High |
| Java | GumTree or Tree-sitter Java | High |
| C++ | Tree-sitter C++ or difftastic | Medium |
| Rust | Tree-sitter Rust or difftastic | Medium |

Structural features to store:

```text
structural_available
structural_engine
structural_language
structural_similarity
structural_error
```

Do not make structural scoring required for a decision. Treat it as extra evidence.

Current implementation status:

| Language | Status |
|---|---|
| Python | implemented with local stdlib `ast` node recall |
| Go | implemented with optional Tree-sitter node recall |
| Java | implemented with optional Tree-sitter node recall; GumTree remains separate and opt-in |
| C++ | implemented with optional Tree-sitter node recall |
| Rust | implemented with optional Tree-sitter node recall |

Tree-sitter parser binaries are cached under:

```text
ml/.tree-sitter-cache/
```

If the cache is missing and network is unavailable, the evaluator records `structural_available=false` and stores the failure in `structural_error` instead of failing the run.

## Phase 5: Calibrate With Labels

Use the labeled dataset to decide thresholds.

Start with rule evaluation:

```text
if exact match -> 100%
if high identifier/literal-normalized recall and anchors match -> 100%
if medium recall or structural similarity -> mostly/partial
if low same-file and low anchor overlap -> 0%
```

Then train a simple model over the metrics:

```text
logistic regression
random forest
gradient boosting
```

Do not fine-tune CodeBERT/Roberta first.

Use ML only after deterministic metrics are stable and explainable.

## Phase 6: Evaluate Per Language

Report quality separately for each top language.

Required reports:

```text
overall accuracy
overall mean absolute error
per-language accuracy
per-language mean absolute error
false 100% rate per language
false 0% rate per language
confusion matrix per language
```

This matters because one global metric can hide bad behavior in one language.

Example:

```text
Python accuracy: good
Go accuracy: okay
C++ accuracy: bad because punctuation-heavy tokens dominate
```

## Implementation Order

### Step 1

Add `Pygments` to `ml/requirements.txt`. Done.

### Step 2

Update `evaluate_metrics.py`:

```text
try custom tokenizer
try Pygments lexer by filename
fallback to regex
```

Done for the evaluator. Current behavior keeps the custom Python/JSON/YAML/Markdown/Dockerfile tokenizers and uses Pygments before regex fallback for other recognized files, including Go, C++, Rust, and Java.

### Step 3

Add literal normalization.

### Step 4

Add per-language score summaries to the visualization notebook.

### Step 5

Inspect false positives for Go/Python/C++/Rust/Java.

### Step 6

Only then add structural scoring for the weakest high-volume language.

## Expected Outcome

This should improve robustness for small developer edits:

- variable renames
- literal changes
- formatting changes
- extra guard clauses
- reordered nearby statements

It will not fully solve semantic rewrites. Those should be handled later with structural features or supervised classification.

## Short Recommendation

Implement this next:

```text
Pygments tokenizer for Go/C++/Rust/Java
literal normalization
per-language evaluation plots
```

Then decide whether Tree-sitter/difftastic is needed based on the per-language false positives and false negatives.
