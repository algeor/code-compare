# P1 Language Support Detailed Implementation

## Scope

Implement P1 language support for PR suggestion coverage matching.

P1 languages:

```text
Jupyter Notebook, HTML, Groovy, HCL, Shell, TypeScript, C, JavaScript
```

Primary file:

```text
ml/src/pr_suggestion_metrics/evaluate_metrics.py
```

Supporting files:

```text
ml/src/pr_suggestion_metrics/prepare_structural_parsers.py
ml/notebooks/03_evaluate/pr_suggestion_metric_evaluation.ipynb
ml/notebooks/04_visualize/metric_score_visualization.ipynb
ml/README.md
ml/requirements.txt
```

## Implementation Order

1. Add P1 language detection.
2. Add notebook-aware diff extraction.
3. Verify P1 tokenization.
4. Add optional Tree-sitter structural scoring for stable P1 languages.
5. Update score output only where new columns are useful.
6. Update notebooks.
7. Validate against the labeled dataset.

## Phase 1: Language Detection

Edit:

```text
_LANGUAGE_BY_EXTENSION
_language_for_tokenization(path: str) -> str
```

Add mappings:

```python
".ipynb": "jupyter_notebook",
".html": "html",
".htm": "html",
".groovy": "groovy",
".tf": "hcl",
".hcl": "hcl",
".ts": "typescript",
".tsx": "typescript",
".js": "javascript",
".jsx": "javascript",
".c": "c",
".h": "c",
```

Add filename detection:

```python
if normalized_path.name == "Jenkinsfile":
    return "groovy"
```

Keep Dockerfile detection before extension detection.

Acceptance checks:

```python
assert _language_for_tokenization("notebook.ipynb") == "jupyter_notebook"
assert _language_for_tokenization("index.html") == "html"
assert _language_for_tokenization("Jenkinsfile") == "groovy"
assert _language_for_tokenization("main.tf") == "hcl"
assert _language_for_tokenization("app.ts") == "typescript"
assert _language_for_tokenization("app.js") == "javascript"
assert _language_for_tokenization("main.c") == "c"
```

## Phase 2: Notebook-Aware Extraction

Do not compare `.ipynb` as raw JSON.

Raw notebook diffs contain noise:

- execution counts
- outputs
- cell IDs
- transient metadata
- JSON escaping

Add helper functions:

```text
_is_notebook_path(path: str) -> bool
_extract_notebook_code_lines(raw_lines: list[str]) -> tuple[list[str], str]
_extract_notebook_source_from_json(notebook_text: str) -> list[str]
_extract_notebook_source_from_diff_lines(raw_lines: list[str]) -> list[str]
```

Behavior:

- join added diff lines into text
- try `json.loads`
- if it parses, iterate `cells`
- keep `cell_type == "code"`
- read `source` as either `list[str]` or `str`
- drop metadata, outputs, execution count, and cell IDs
- if full JSON parse fails, extract added source-like JSON string lines as fallback
- if fallback also fails, return original normalized lines and mark extractor as fallback

Recommended extractor labels:

```text
notebook_json_code_cells
notebook_diff_source_lines
plain_diff_lines
```

Use the extracted code lines before tokenization and hunk comparison.

## Phase 3: Tokenization

Current tokenizer flow:

```text
Python tokenizer
-> JSON tokenizer
-> YAML-like tokenizer
-> Markdown tokenizer
-> Dockerfile tokenizer
-> Pygments tokenizer
-> regex fallback
```

Keep this flow.

P1 behavior:

- `jupyter_notebook`: extract code lines, then default tokenization to Python for code cells unless notebook metadata says otherwise.
- `html`: prefer Pygments, fallback regex.
- `groovy`: prefer Pygments, fallback regex.
- `hcl`: prefer Pygments if available, fallback regex.
- `shell`: prefer Pygments, fallback regex.
- `typescript`: prefer Pygments, fallback regex.
- `javascript`: prefer Pygments, fallback regex.
- `c`: prefer Pygments, fallback regex.

Add an optional `content_extractor` output only if it helps debugging notebook behavior. If adding it, extend `MetricResult` and `_write_scores`.

Recommended new output columns:

```text
content_extractor
notebook_code_cell_count
notebook_markdown_cell_count
```

Do not add notebook columns if there are too few notebook examples to evaluate yet.

## Phase 4: Structural Scoring

Current edit points:

```text
_TREE_SITTER_LANGUAGES
_tree_sitter_parser(language: str)
_structural_node_types(language: str, text: str)
_best_structural_scores(...)
```

Add stable P1 parser candidates first:

```python
_TREE_SITTER_LANGUAGES = {
    "c",
    "cpp",
    "go",
    "html",
    "java",
    "javascript",
    "rust",
    "typescript",
}
```

Do not enable Shell, HCL, or Groovy structural scoring by default until real examples prove the parsers are stable on partial snippets.

Structural scoring must remain optional:

- parser failure must not fail the evaluator
- store parser errors in `structural_error`
- keep `structural_available=false` when unsupported
- keep token metrics as the main signal

## Phase 5: Parser Smoke Test

Edit:

```text
ml/src/pr_suggestion_metrics/prepare_structural_parsers.py
```

Add snippets for:

```text
c
html
javascript
typescript
```

Candidate snippets:

```python
"c": "int add(int a, int b) { return a + b; }\n",
"javascript": "function add(a, b) { return a + b; }\n",
"typescript": "function add(a: number, b: number): number { return a + b; }\n",
"html": "<main><h1>Hello</h1><button disabled>Save</button></main>\n",
```

Run:

```bash
PYTHONPATH=ml/src ml/.venv/bin/python -m pr_suggestion_metrics.prepare_structural_parsers
```

Expected result:

```text
c: tree_sitter nodes=N status=ok
html: tree_sitter nodes=N status=ok
javascript: tree_sitter nodes=N status=ok
typescript: tree_sitter nodes=N status=ok
```

If a language fails, do not add it to `_TREE_SITTER_LANGUAGES` yet.

## Phase 6: Candidate-Hunk Matching

Keep existing hunk-local strategy.

Current function:

```text
_candidate_hunks_for_suggestion(...)
```

Keep candidate types:

```text
same_file
neighboring_same_file
same_extension
anchor_overlap
```

Notebook-specific adjustment:

- same file remains the strongest candidate
- compare notebook code-cell extracted content against notebook code-cell extracted landed hunks
- same-extension matching for `.ipynb` should use extracted cell source, not raw JSON

Avoid whole-PR comparison for P1. It creates false positives for small snippets.

## Phase 7: Prediction Rules

Do not let structural scoring override everything.

Production input constraint:

```text
available: suggestion + merged diff/code
not available: reviewer comment, before_code, human explanation
```

Therefore calibration uses only comparison-derived metrics.

Additional language-independent metrics added for this constraint:

```text
best_hunk_token_precision
best_hunk_token_f1
best_hunk_contiguous_line_ratio
best_hunk_token_lcs_recall
best_hunk_size_ratio
```

Metric meanings:

- `best_hunk_token_precision`: how much of the matched hunk is explained by suggestion tokens
- `best_hunk_token_f1`: balanced overlap between suggestion recall and hunk precision
- `best_hunk_contiguous_line_ratio`: longest exact contiguous suggested-line span found in the candidate hunk
- `best_hunk_token_lcs_recall`: order-aware token recall using longest common subsequence
- `best_hunk_size_ratio`: size compatibility between suggestion and candidate hunk

These metrics are designed to catch cases where a tiny suggestion overlaps with a much larger unrelated hunk.

Recommended rule behavior:

```text
exact normalized match -> 100%
high same-file normalized hunk recall -> 100% or mostly
medium hunk recall + high structural similarity -> mostly or partial
high token recall + low structural similarity -> suspicious, cap at mostly
low token recall + high structural similarity -> possible refactor, partial candidate
low same-file + low anchor overlap -> 0%
```

Important: calibrate thresholds with labels. Do not hard-code P1 thresholds without checking false positives.

Implemented calibration:

- exact normalized matches still return `100`
- non-exact `100%` predictions now require much stronger same-file or cross-file evidence
- same-file strong evidence requires high identifier-and-literal hunk recall, high anchor recall, at least two meaningful anchors, and high line-level overlap
- cross-file strong evidence requires even higher hunk recall, anchor recall, and at least four meaningful anchors
- weak same-file evidence is capped below `100%`
- cross-file evidence is capped below `100%` unless it passes the stricter strong-cross-file rule

Observed result on the current 279-example dataset:

```text
old clone-style metric accuracy: 0.538
calibrated clone-style metric accuracy: 0.663

old false 100% predictions: 86
calibrated false 100% predictions: 5

old 100% precision: 0.543
calibrated 100% precision: 0.947
```

Remaining issue:

```text
partial recall is still weak
```

That means the next calibration work should focus on separating `partial` from `mostly`, not on adding more parsers.

Implemented partial calibration:

- compute a partial-evidence gate from line-level overlap only
- use the maximum of `line_recall`, `best_added_line_overlap`, and `changed_line_overlap_ratio`
- if that overlap is present but moderate, and the contiguous-line match is low, cap the prediction at `partial`
- do not apply this cap to exact matches or strong `100%` evidence

Current rule:

```text
0.05 <= max(line_recall, best_added_line_overlap, changed_line_overlap_ratio) <= 0.60
and best_hunk_contiguous_line_ratio < 0.30
-> cap score at partial
```

Observed result on the current 279-example hand-labeled dataset:

```text
calibrated accuracy before partial rule: 0.656
calibrated accuracy after partial rule: 0.703

partial recall before partial rule: 0.000
partial recall after partial rule: 0.457

partial F1 before partial rule: 0.000
partial F1 after partial rule: 0.552

100% precision after partial rule: 0.966
```

Implemented no-landed-line-evidence calibration:

- catch cases where token or structural similarity is high, but no suggested line landed as an added line or contiguous span
- require low hunk precision and low anchor recall before returning `0%`
- this targets false positives where a suggestion resembles broad surrounding code but did not actually land

Current rule:

```text
max(line_recall, best_added_line_overlap, changed_line_overlap_ratio, best_hunk_contiguous_line_ratio) == 0
and best_hunk_token_precision < 0.30
and meaningful_anchor_recall < 0.50
-> 0%
```

Observed result after adding this rule:

```text
hand-labeled accuracy: 0.703 -> 0.763
hand-labeled MAE: 17.70 -> 13.34

0% recall: 0.521 -> 0.761
0% F1: 0.607 -> 0.777

partial F1: 0.552 -> 0.561
100% precision: stays 0.966
```

## Phase 8: Notebook Updates

Update:

```text
ml/notebooks/03_evaluate/pr_suggestion_metric_evaluation.ipynb
```

Add cells for:

- P1 language distribution
- P1 parser smoke test
- notebook extraction preview for one `.ipynb` example
- per-language accuracy summary
- false 100% and false 0% table

Update:

```text
ml/notebooks/04_visualize/metric_score_visualization.ipynb
```

Add visuals:

- accuracy by language
- mean absolute error by language
- structural availability by language
- token recall vs structural similarity scatter
- worst predictions table filtered to P1
- notebook examples table if notebook rows exist

## Phase 9: Validation Commands

Run parser smoke test:

```bash
PYTHONPATH=ml/src ml/.venv/bin/python -m pr_suggestion_metrics.prepare_structural_parsers
```

Run evaluator:

```bash
PYTHONPATH=ml/src ml/.venv/bin/python ml/src/pr_suggestion_metrics/evaluate_metrics.py \
  --dataset-dir ml/data/processed/pr_suggestion_coverage/dataset \
  --output ml/reports/metric_scores.csv
```

Check generated columns:

```bash
head -1 ml/reports/metric_scores.csv
```

Inspect P1 language distribution:

```bash
PYTHONPATH=ml/src ml/.venv/bin/python - <<'PY'
import csv
from collections import Counter

with open('ml/reports/metric_scores.csv', newline='') as scores_file:
    rows = list(csv.DictReader(scores_file))

print(Counter(row['suggestion_language'] for row in rows))
print(Counter(row['structural_engine'] or 'none' for row in rows))
PY
```

## Done Criteria

P1 implementation is done when:

- P1 languages are detected explicitly.
- `.ipynb` examples are compared by cell source, not raw notebook JSON.
- P1 tokenization uses Pygments or records fallback behavior.
- stable P1 Tree-sitter parsers pass local smoke tests.
- structural failures are recorded, not fatal.
- `03_evaluate` can inspect P1 behavior.
- `04_visualize` shows P1 quality and parser availability.
- generated metrics improve or explain the P1 failure modes in the labeled dataset.
