# Project Architecture Overview

**Status:** canonical architecture overview

**Audience:** contributors, reviewers, researchers, demo operators, and future agents

**Purpose:** provide a compact system map for the current project

## 1. Purpose

The project measures how much of a code-review suggestion is represented in a merged pull-request diff.

It produces:

- exact evidence from matching changed lines and renames;
- an experimental coverage percentage for supported raw diff shapes;
- short explanations based on inspectable evidence;
- separate AI review quality scoring against independent evidence.

It does not prove the suggestion caused the change. It also does not prove the final code behaves exactly like the suggestion.

## 2. High-Level Architecture

```text
User / CLI / Demo UI
        |
        v
AnalysisService
        |
        +--> diff checks + exact evidence
        |
        +--> feature extraction
        |
        +--> percentage model scoring
        |
        +--> safe explanation templates
        |
        v
Versioned AnalysisResult
```

See [`project-architecture.mmd`](project-architecture.mmd) for a Mermaid diagram version.

## 3. Main Layers

### Interface layer

Entry points for users, demos, and hosted showcases.

```text
README / docs
CLI commands
Gradio demo
Hugging Face Space shim
```

Key files:

```text
src/pr_suggestion_metrics/analysis_service.py
src/pr_suggestion_metrics/demo_gradio.py
space/app.py
```

### Domain layer

Core project meaning lives here.

```text
diff_semantics.py        exact change-unit evidence
reviewer_evaluation.py   separate AI review scoring
percentages.py           shared percentage validation
scientific_contracts.py  research rules
```

### Diff and feature layer

This layer turns diffs into checked evidence and model-ready features.

```text
diff/        unified diff parsing and diagnostics
features/    lexical, matching, structural, scoring features
```

Flow:

```text
raw suggested diff + merged PR diff
        -> parse / assess
        -> normalize change units
        -> strict same-file evidence
        -> relaxed cross-file evidence
        -> feature row
```

### Model runtime layer

This layer loads trusted model files and runs scoring.

```text
model_inference.py
model_artifacts.py
uncertainty.py
```

Rules:

- model directory must be explicit;
- manifest hashes are verified;
- unsupported inputs abstain;
- `joblib` model files are trusted-input only.

### Research pipeline layer

This layer creates repeatable benchmark and training files.

```text
collection/
benchmark/
modeling/
prepare_annotation_packets.py
freeze_benchmark.py
evaluate_frozen_benchmark.py
```

Target flow:

```text
collect candidates
 -> prepare blinded annotation packets
 -> check label disagreements
 -> freeze benchmark
 -> build feature table
 -> select/train model
 -> calibrate uncertainty
 -> protected evaluation
```

### Documentation and governance layer

This layer defines what the project can safely claim.

```text
README.md
docs/README.md
docs/architecture.md
docs/project-guide.md
docs/reproducibility.md
docs/data-card.md
docs/model-card.md
docs/implementation-progress.md
docs/senior-code-review.md
```

## 4. Important Boundaries

- `research/archive/` is historical only.
- Runtime scoring must not import training code.
- Supported code must not import archived bucket-era code.
- Exact evidence is not proof that the suggestion caused the change.
- Coverage scoring is separate from AI reviewer quality scoring.

## 5. Current Product Shape

```text
suggested diff + merged PR diff
        |
        v
AnalysisService
        |
        +--> exact evidence
        +--> weak/demo percentage model
        +--> template explanation
        |
        v
JSON result with hashes, warnings, evidence, score, or abstention
```

## 6. Future Product Shape

```text
checked diff evidence
        |
        +--> calibrated percentage model
        |
        +--> CodeBERT-style evidence provider
        |
        v
stable API / CLI / hosted demo result
```

The key next architecture goal is not more model tuning. It is a better benchmark: examples with trustworthy history, independent labels, a frozen answer key, and one protected final test.
