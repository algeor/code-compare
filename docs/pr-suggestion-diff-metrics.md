# PR Suggestion Diff Metrics

## Goal

Measure whether small code suggestions were included in a merged pull request, even when a developer made minor edits such as renaming variables, changing formatting, or adapting surrounding code.

This is not a raw code quality score. It answers a narrower question:

> How much of the suggested snippet appears in the merged PR diff?

For this use case, containment is more important than general similarity. A suggestion can be useful even if only part of it is merged, and a merged implementation can preserve the idea while changing names or structure.

## Recommended Metric Stack

Use deterministic metrics as the source of truth, then apply ML-based similarity only for borderline cases.

| Layer | Metric | Best For | Handles Small Edits? | Output |
|---|---|---|---|---|
| 1 | Exact normalized match | Copy-pasted suggestions | Low | yes/no |
| 2 | Line recall | Line-level inclusion | Medium | 0-1 |
| 3 | Token recall | Suggestion containment | Medium | 0-1 |
| 4 | Identifier-normalized token recall | Variable/function renames | High | 0-1 |
| 5 | AST similarity | Structural preservation | High | 0-1 |
| 6 | Code embedding similarity | Rewritten but conceptually similar suggestions | Medium/High | 0-1 |
| 7 | Human review bucket | Final decision for ambiguous cases | Highest | used / partial / not used |

## Standard Framing: Code Clone Detection

The closest standardized research area for this problem is code clone detection.

Instead of inventing a custom framing, model the question as:

> Is this suggested snippet a Type-1, Type-2, Type-3, or Type-4 clone inside the merged PR diff?

Classic clone taxonomy:

| Clone Type | Meaning | Metric Mapping |
|---|---|---|
| Type-1 | Exact copy except whitespace/comments | exact normalized match |
| Type-2 | Same code with renamed identifiers, changed literals, or formatting | identifier-normalized token recall |
| Type-3 | Copied code with added, removed, or changed statements | token recall, GumTree edit script, AST similarity |
| Type-4 | Same behavior with a different implementation | embedding similarity, tests, semantic analysis |

For PR suggestion coverage, Type-1 through Type-3 are the most useful and explainable. Type-4 is valuable for research or manual review support, but it is harder to prove automatically.

Common standardized tools and approaches:

| Approach | Example Tools / Names | Use In This Problem |
|---|---|---|
| Token clone detection | PMD CPD, SourcererCC | Fast detection of copied or lightly edited snippets |
| Near-miss clone detection | NiCad | Good for renamed or partially edited suggestions |
| AST clone detection | Deckard, GumTree-style AST comparison | Structure-aware matching |
| Plagiarism-style code matching | MOSS, JPlag | Useful conceptual model for code reuse detection |
| Patch identity / normalized diff matching | Git patch-id, normalized patch comparison | Detect equivalent patch-level changes |
| Information retrieval | BM25, TF-IDF, embedding search | Retrieve likely PR hunks before deeper scoring |
| Supervised classification | Logistic regression, XGBoost, LightGBM over metrics | Convert metric signals into final labels using labeled data |

Recommended standardized architecture:

```text
candidate retrieval
→ clone detection metrics
→ structural diagnostics
→ supervised classifier
→ human review for borderline cases
```

This keeps the system aligned with known clone-detection practice while still fitting the specific goal of measuring suggestion inclusion in merged PR diffs.

## Primary Metric: Suggestion Recall in Merged Diff

For small snippets, the main metric should be recall from the suggestion into the merged PR diff.

```text
suggestion_recall = suggestion_tokens_found_in_merged_diff / total_suggestion_tokens
```

Interpretation:

| Score | Meaning |
|---:|---|
| 0.90-1.00 | Suggestion was basically merged |
| 0.60-0.90 | Suggestion was partially used |
| 0.30-0.60 | Some overlap; likely rewritten or only lightly used |
| 0.00-0.30 | Suggestion was mostly not used |

Precision can also be useful, but recall is usually the key signal here.

```text
precision = matched_suggestion_tokens / total_tokens_in_candidate_pr_chunk
recall = matched_suggestion_tokens / total_tokens_in_suggestion
f1 = 2 * precision * recall / (precision + recall)
```

Mental model:

| Metric | Question |
|---|---|
| Precision | How much of the matched PR chunk came from the suggestion? |
| Recall | How much of the suggestion appeared in the PR? |
| F1 | Balanced overlap score |

## Exact Normalized Match

Exact match is the fastest first pass.

Normalize both the suggestion and merged PR additions before comparison:

- trim leading/trailing whitespace
- normalize indentation
- collapse repeated blank lines
- optionally remove comments for a comment-insensitive score

This catches direct inclusion, but it breaks easily when developers rename variables or adapt formatting.

Use it as a cheap positive signal, not as the only metric.

## Line Recall

Line recall checks how many normalized suggestion lines appear in the merged diff additions.

```text
line_recall = suggestion_lines_found_in_pr_additions / total_suggestion_lines
```

Good for snippets that are copied mostly line-for-line.

Weaknesses:

- variable renames can make a line look different
- reordered lines reduce the score
- multiline formatting changes can reduce the score unfairly

## Token Recall

Token recall is usually better than line recall for small code snippets.

It compares code tokens rather than raw lines. Formatting changes matter less, and small edits only reduce the score partially.

Example:

```python
timeout = 30
```

Changed to:

```python
request_timeout = 30
```

Exact match fails, but token recall still keeps overlap for `=`, `30`, and surrounding syntax.

## Identifier-Normalized Token Recall

This is the most useful deterministic upgrade for developer-edited snippets.

Replace identifiers with placeholders before computing token recall.

Example:

```python
timeout = 30
```

and:

```python
request_timeout = 30
```

both normalize to:

```python
IDENT = 30
```

This handles:

- variable renames
- helper function renames
- parameter renames
- local naming style changes

Recommended paired interpretation:

| Raw Token Recall | Identifier-Normalized Recall | Meaning |
|---:|---:|---|
| High | High | Suggestion likely used directly |
| Medium | High | Suggestion likely used with renames |
| Low | High | Same structure, many names changed |
| Low | Low | Suggestion probably not used |

## AST Similarity

AST similarity compares code structure instead of text.

It is useful when developers preserve the shape of the suggestion but change names or formatting.

Good at detecting:

- same `if`/`else` shape
- same function call structure
- same loop structure
- same exception handling structure

Weaknesses:

- language-specific parsers are required
- snippets may not parse unless wrapped in valid context
- moved code may look like deletion plus insertion
- pure semantic changes may be invisible if structure stays similar

For Python, TSED can be used for tree edit distance. GumTree can also produce edit-operation features such as insert, delete, move, and update.

## CodeBLEU

CodeBLEU combines four code similarity signals:

- n-gram token overlap
- keyword-weighted n-gram overlap
- AST sub-tree overlap
- data-flow overlap

It is useful when comparing implementation similarity between a suggested snippet and candidate PR chunks.

Supported languages include Python, Java, JavaScript, C, C++, C#, Go, PHP, Ruby, and Rust.

Weaknesses:

- not available for every language or file type
- mostly measures similarity, not guaranteed inclusion
- may need careful chunking of the merged PR diff

## GumTree Edit-Script Features

GumTree reports which structural operations transform one code version into another:

- insert
- delete
- update
- move

Useful interpretation:

| Pattern | Meaning |
|---|---|
| Insert-heavy | PR added extra code beyond the suggestion |
| Delete-heavy | Suggested code was replaced or removed |
| Update-heavy | Names, literals, or small expressions changed |
| Move-heavy | Code was reorganized or refactored |

For small snippets, GumTree is best as a diagnostic metric after token recall or AST similarity flags a possible match.

## Diff Stats

Diff stats are simple counts:

- files changed
- lines added
- lines deleted
- net growth/shrink ratio

They do not prove a suggestion was used, but they help explain review effort.

Example use:

- suggestion recall is high, but final diff is much larger: the suggestion was used, then extended
- suggestion recall is low, and final diff is much larger: the suggestion likely missed required work
- suggestion recall is high, and final diff size is similar: the suggestion was close to final

## ML Similarity

ML models can help when the developer rewrote the suggestion but preserved the idea.

Prefer code-specific models over general RoBERTa:

| Model | Use |
|---|---|
| CodeBERT | General code/text similarity baseline |
| GraphCodeBERT | Better when data flow matters |
| UniXcoder | Strong code search and similarity candidate |
| CodeT5 / CodeT5+ | Code understanding and generation similarity |

Use embeddings like this:

```text
similarity = cosine_similarity(embed(suggestion), embed(candidate_pr_chunk))
```

Do not use ML as the only source of truth. It can produce plausible-looking matches where the PR did not actually include the suggestion.

Recommended policy:

```text
if deterministic_score >= 0.85:
    label = used
elif deterministic_score <= 0.30:
    label = not_used
else:
    use code_embedding_similarity as a tie-breaker
```

## Training Strategy

If labeled data exists, start with a simple supervised classifier over deterministic and embedding features.

Example dataset shape:

```text
suggestion_snippet
candidate_pr_chunk
language
exact_match
line_recall
token_recall
identifier_normalized_token_recall
ast_similarity
code_embedding_similarity
label: used / partially_used / not_used
```

Recommended order:

1. Build deterministic metrics.
2. Add pretrained code embedding similarity.
3. Train a simple classifier such as logistic regression, random forest, XGBoost, or LightGBM.
4. Calibrate thresholds and inspect false positives/false negatives.
5. Fine-tune CodeBERT, UniXcoder, or CodeT5 only if the simpler model fails on enough real cases.

Why not fine-tune first:

- harder to explain to reviewers
- requires more data hygiene
- more expensive to train and maintain
- deterministic features are often strong for containment problems

## Candidate Chunking

Compare each suggestion against likely PR chunks, not the whole PR diff as one blob.

Good candidate chunks:

- added hunks from the same file
- nearby added lines around matching identifiers
- changed function bodies
- added methods/classes
- files with overlapping imports, function names, or constants

Then keep the best-scoring candidate per suggestion.

```text
suggestion_score = max(score(suggestion, candidate_chunk) for candidate_chunk in merged_pr_chunks)
```

## Suggested Final Decision Logic

Use rule-based labels first, then train/calibrate using the labeled dataset.

Initial baseline:

| Condition | Label |
|---|---|
| exact normalized match | used |
| identifier-normalized recall >= 0.90 | used |
| token recall >= 0.80 and AST similarity >= 0.80 | used |
| identifier-normalized recall >= 0.60 or AST similarity >= 0.65 | partially_used |
| deterministic score is borderline and embedding similarity is high | partially_used / review |
| all deterministic scores low | not_used |

After enough labeled examples, replace hard thresholds with a trained classifier.

## Recommended Output Per Suggestion

For each suggestion, store both the decision and the evidence.

```json
{
  "suggestion_id": "SUG-123",
  "label": "partially_used",
  "best_file": "src/example.py",
  "best_hunk_id": "hunk-4",
  "exact_match": false,
  "line_recall": 0.42,
  "token_recall": 0.71,
  "identifier_normalized_token_recall": 0.88,
  "ast_similarity": 0.81,
  "embedding_similarity": 0.79,
  "reason": "The suggestion structure was preserved, but identifiers were renamed and extra guard logic was added."
}
```

## Summary

For small code suggestions, the strongest approach is:

```text
exact match
→ token recall
→ identifier-normalized token recall
→ AST similarity
→ code embedding similarity for borderline cases
→ supervised classifier once labels are available
```

The most important metric is identifier-normalized suggestion recall, because it directly answers whether the suggestion appeared in the merged PR while tolerating common developer edits.
