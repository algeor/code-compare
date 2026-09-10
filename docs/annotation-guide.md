# Annotation Guide: Semantic Suggestion Coverage

**Status:** required protocol for a future human benchmark. It does not retroactively validate the repository's current LLM-assisted labels.

## 1. Question

For a verified code-review suggestion made before merge:

> What weighted fraction of the suggestion's meaningful semantic units is present in the final merged implementation?

Annotators measure **coverage**, not whether the author copied the suggestion and not whether the suggestion caused the implementation.

## 2. Materials Shown to Annotators

Show only:

- the suggestion text/diff;
- the exact code state the suggestion targeted;
- the final merged code state or a narrowly scoped, provenance-verified diff;
- file paths and limited context needed to understand behavior.

Do not show:

- lexical, token, AST, embedding, or model scores;
- deterministic estimates or existing labels;
- another annotator's decision;
- author identity, model output, or expected bucket;
- post hoc explanations designed to justify an existing score.

## 3. Eligibility and Abstention

Annotate only when chronology and code states are reconstructible. Mark `abstain` with one or more reasons when:

- the suggestion was made after the relevant change;
- the target revision or merge revision is missing;
- the suggestion is malformed or ambiguous;
- generated/binary content cannot be inspected;
- required behavior is outside the provided repository context;
- attribution between pre-existing and newly landed code cannot be determined;
- the annotator lacks the language/domain expertise needed for a defensible judgment.

Abstentions are valid outcomes and must not be silently converted to zero.

## 4. Semantic Units

Split the suggestion into the smallest independently judgeable meaningful units. Typical units include:

- API calls and argument changes;
- assignments and data transformations;
- conditions and branches;
- loops or iteration behavior;
- error handling and fallback behavior;
- function signatures and return contracts;
- configuration keys, values, flags, and commands;
- tests, setup, and assertions;
- documentation statements when the suggestion itself is documentation.

Do not create units for braces, formatting, imports, or boilerplate unless they carry behavior central to the suggestion.

## 5. Weights and Credits

Assign each unit an integer importance weight before judging the landed code:

| Weight | Meaning |
|---:|---|
| 1 | supporting detail; omission has small semantic effect |
| 2 | meaningful behavior or contract element |
| 3 | core behavior; omission defeats the main suggestion |

Assign one landed credit:

| Credit | Status | Rule |
|---:|---|---|
| 1.0 | `landed_exactly` | same meaningful implementation, allowing trivial formatting |
| 1.0 | `landed_equivalently` | behaviorally equivalent implementation with different text or structure |
| 0.5 | `landed_partially` | a clearly identifiable part of the unit landed, but important behavior is missing |
| 0.0 | `absent` | no defensible evidence that the unit landed |
| 0.0 | `different_implementation` | the problem was addressed, but not with the suggested semantic unit |

Do not vary partial credit case by case. If later research needs finer credit, version the guide and relabel; do not mutate this rubric in place.

## 6. Percentage Formula

For units `u_i`, weights `w_i`, and credits `c_i`:

```text
coverage = 100 * sum(w_i * c_i) / sum(w_i)
```

Round to the nearest integer only after aggregation. Store the unrounded value as well. The percentage must be computed from stored units; annotators must not choose an intuitive percentage first and reverse-engineer units afterward.

## 7. Evidence Rules

Every unit requires concrete evidence:

- final file path and line/span or stable syntax node;
- a short explanation of semantic equivalence or missing behavior;
- whether the evidence existed before the suggestion;
- whether it is part of the final merged state.

Ignore unrelated PR changes. A same-file or same-topic match is not sufficient. Generic tokens and context lines receive no credit unless they encode the unit's behavior.

## 8. Required Annotation Record

```json
{
  "example_id": "...",
  "guide_version": "1.0",
  "annotator_id": "pseudonymous-id",
  "decision": "scored",
  "abstention_reasons": [],
  "units": [
    {
      "unit_id": "u1",
      "description": "Specific suggested behavior",
      "weight": 3,
      "credit": 1.0,
      "status": "landed_equivalently",
      "evidence": [{"path": "src/example.py", "locator": "symbol or line", "explanation": "..."}],
      "preexisting": false
    }
  ],
  "coverage_unrounded": 100.0,
  "coverage_percentage": 100,
  "confidence": "high",
  "notes": ""
}
```

## 9. Annotation Workflow

1. Train annotators on examples excluded from every experiment.
2. Run a pilot and revise ambiguous instructions before freezing guide version 1.0.
3. Double-annotate every confirmatory test example independently.
4. Preserve both original records unchanged.
5. Compute agreement before adjudication.
6. Adjudicate disagreements using a third qualified reviewer or consensus meeting.
7. Store adjudication separately with reasons and references to both source records.
8. Freeze labels and hashes before model selection begins.

Recommended agreement reporting:

- absolute percentage difference distribution;
- percentage within 5 and 10 points;
- intraclass correlation for percentage scores;
- weighted agreement on unit statuses;
- abstention rate and disagreement reasons.

## 10. Hard Cases

- **Rename/move:** give credit only when the same semantic unit persists in the final state and provenance is verified.
- **Refactor:** equivalent behavior can receive full credit; cite the mapping.
- **Different solution:** solving the same broad problem does not automatically cover the suggested unit.
- **Deletion/replacement:** judge the behavioral unit, including what must be removed or changed; do not use addition-only overlap.
- **Large PR:** constrain review to plausible files/anchors, then verify against the final state.
- **Tiny suggestion:** one equivalent meaningful unit can score 100; generic boilerplate cannot.
- **Tests/config/docs:** judge assertions, effects, keys, values, commands, and factual statements—not token overlap alone.

## 11. Quality Gate

Reject an annotation batch if percentages cannot be recomputed exactly from stored units, evidence is missing, annotators saw model-derived hints, chronology is unverified, or duplicate examples cross frozen split boundaries.

Use `pr-suggestion-prepare-annotations` to generate blinded packets and `pr-suggestion-freeze-benchmark` to enforce this gate. Do not manually bypass a rejected record; correct or recollect its evidence.
