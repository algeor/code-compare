# P1 Language Support Plan

## Goal

Extend the PR suggestion coverage evaluator beyond the first top-language group.

P0 is:

```text
Python, Go, C++, Rust, Java
```

P1 is:

```text
Jupyter Notebook, HTML, Groovy, HCL, Shell, TypeScript, C, JavaScript
```

The goal is still the same question:

```text
Did this small suggested code change appear in the merged PR diff, possibly with small edits?
```

## Principle

Do not treat every P1 language the same.

Use the cheapest reliable layer first:

```text
file/language detection
-> language-aware tokenization
-> normalization
-> candidate-hunk matching
-> optional structural scoring
-> per-language calibration
```

Structural scoring should add evidence. It should not be the only decision maker.

## P1 Groups

### Group A: Code Languages With Good Structural Potential

```text
TypeScript, JavaScript, C, Shell
```

Plan:

- add explicit language detection if missing
- use Pygments tokenization where stable
- add Tree-sitter parser smoke tests where available
- enable structural node recall only after parser checks pass locally
- keep regex fallback if lexer/parser fails

Expected value:

- better handling of renamed variables
- better partial-match detection
- fewer false positives from whole-file or whole-PR token overlap

### Group B: Structured Or Semi-Structured Languages

```text
HTML, HCL, Groovy
```

Plan:

- add explicit language detection
- use language-aware tokenization first
- add normalization for identifiers and literals
- evaluate Tree-sitter only if the parser is stable locally
- keep structural scoring optional

Notes:

- HTML changes can be noisy because tags, attributes, text, and embedded JS/CSS behave differently.
- HCL is important for Terraform-like config changes and should not be treated as plain text long term.
- Groovy often appears in Jenkins or pipeline code, so token matching may already provide high value.

### Group C: Jupyter Notebook

```text
Jupyter Notebook / .ipynb
```

Do not compare `.ipynb` files as raw JSON.

Plan:

- parse notebook JSON with `nbformat` or standard `json`
- ignore execution metadata, outputs, IDs, and transient metadata
- extract `code` cells
- optionally extract markdown cells as a separate text signal
- compare code cells using the language declared in cell metadata when present
- default notebook code cells to Python when language metadata is missing
- aggregate cell-level scores into one notebook-level score

Suggested notebook features:

```text
notebook_code_cell_count
notebook_markdown_cell_count
notebook_best_cell_token_recall
notebook_best_cell_structural_similarity
notebook_metadata_ignored
```

Expected value:

- avoids false negatives caused by notebook JSON churn
- avoids false positives caused by execution counts and output blobs
- makes notebook suggestions comparable to normal source-code snippets

## Implementation Phases

### Phase 1: Measure Impact First

Create a per-language error report from the existing labeled dataset.

Report:

```text
example_count_by_language
accuracy_by_language
mean_absolute_error_by_language
false_100_percent_by_language
false_0_percent_by_language
```

Use this to confirm which P1 languages deserve parser work first.

### Phase 2: Add Language Detection

Extend extension/name mapping for:

```text
.ipynb -> jupyter_notebook
.html, .htm -> html
.groovy, Jenkinsfile -> groovy
.tf, .hcl -> hcl
.sh, .bash, .zsh -> shell
.ts, .tsx -> typescript
.js, .jsx -> javascript
.c, .h -> c
```

Keep Dockerfile and existing structured formats as special cases.

### Phase 3: Add Notebook Extraction

Add a small extractor before tokenization.

For `.ipynb` diffs:

- parse added JSON content when possible
- extract changed code cell source
- normalize notebook cell source into plain code snippets
- ignore outputs and execution metadata
- fall back to JSON/token comparison if parsing fails

### Phase 4: Add Tokenization Support

Use current tokenizer priority:

```text
Python tokenizer
-> custom structured tokenizers
-> Pygments lexer
-> regex fallback
```

Add or verify Pygments support for:

```text
html
groovy
hcl
shell
typescript
javascript
c
```

### Phase 5: Add Optional Structural Support

Extend the local structural parser smoke test for languages that pass locally.

Candidate parser list:

```text
typescript
javascript
c
html
```

Evaluate separately before enabling by default:

```text
shell
hcl
groovy
```

Reason:

- some grammars are useful but brittle on snippets
- shell snippets often parse poorly when extracted from partial diffs
- HCL and Groovy parser quality must be validated on real examples

### Phase 6: Keep Candidate-Hunk Matching

Do not compare suggestions against the full PR diff blob.

Continue comparing against:

```text
same_file
neighboring_same_file
same_extension
anchor_overlap
```

This is especially important for small snippets and notebooks.

### Phase 7: Update Reports And Visuals

Update the evaluation notebook and visualization notebook with:

```text
language distribution
accuracy by language
structural availability by language
token vs structural scatter plot
worst predictions table
notebook-specific score table
```

### Phase 8: Calibrate Per Language

Do not reuse one threshold blindly for all languages.

Start with rule-based calibration:

```text
high normalized token recall + same-file hunk -> strong match
medium token recall + high structural similarity -> partial/mostly
high token recall + low structural similarity -> suspicious
low token recall + high structural similarity -> possible rename/refactor
low same-file + low anchor overlap -> likely 0%
```

Then train a simple supervised model only after features are stable.

Recommended first models:

```text
logistic regression
random forest
gradient boosting
```

Do not fine-tune CodeBERT/Roberta first. Use embeddings later for borderline examples.

## Recommended Build Order

1. Jupyter notebook extraction.
2. P1 language detection mapping.
3. Pygments tokenization verification for P1.
4. Tree-sitter smoke tests for TypeScript, JavaScript, C, and HTML.
5. Optional parser experiments for Shell, HCL, and Groovy.
6. Per-language evaluation report.
7. Visualization notebook updates.
8. Threshold calibration.

## Done Criteria

P1 is ready when:

- `.ipynb` files are compared by cell content, not raw JSON noise
- P1 languages have explicit language labels in `metric_scores.csv`
- P1 examples use language-aware tokenization or a recorded fallback reason
- structural parser availability is visible per language
- evaluation reports show whether P1 improves labels instead of only adding columns
- notebook `03_evaluate` and notebook `04_visualize` expose the new behavior for inspection

