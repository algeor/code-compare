# Percentage Model Research and Embeddings Plan

## Objective

Predict the semantic coverage of a code-review suggestion as one integer from `0` to `100`.

Buckets may be derived later for reporting, but they are not the model output or training target.

## Current Data Constraints

- Internal semantic labels: 279 examples.
- Audited Hugging Face labels: 2,500 examples.
- The target distribution has large exact endpoints at `0` and `100`.
- Hugging Face labels have confidence-dependent training weights.
- All validation splits must be grouped by pull request to prevent related examples leaking across folds.
- Model selection uses internal semantic labels because they best match the production domain.

## Researched Non-Embedding Approaches

### 1. Native categorical boosting

CatBoost directly processes categorical features and explicitly recommends against external one-hot encoding because it can reduce quality and training efficiency. This makes it a good fit for language, tokenizer, candidate type, and structural-engine features.

Experiments:

- Direct CatBoost regression with MAE loss.
- Direct CatBoost regression with Huber loss.
- Two-stage CatBoost with endpoint classification followed by intermediate regression.

Source: https://catboost.ai/en/docs/features/categorical-features

### 2. Robust gradient boosting losses

The labels include uncertain weak supervision and a small number of large disagreements. Robust losses should reduce the influence of those outliers.

Experiments:

- LightGBM `regression_l1`.
- LightGBM `huber`.
- XGBoost `reg:absoluteerror`.
- XGBoost `reg:pseudohubererror`.

Sources:

- https://lightgbm.readthedocs.io/en/stable/Parameters.html
- https://xgboost.readthedocs.io/en/stable/parameter.html

### 3. Out-of-fold ensembling

Stacking and blending combine models whose errors are not identical. Blend weights must be learned from predictions generated for rows excluded from each component's training fold.

This project uses repeated PR-grouped out-of-fold predictions and a non-negative convex blend. The blend retains at least 50% weight on the incumbent model to limit variance on the small internal dataset. The untouched internal holdout remains the final deployment gate.

Source: https://scikit-learn.org/stable/modules/ensemble.html#stacked-generalization

## Experiment Results

Repeated grouped out-of-fold results on the internal development set:

| Candidate | MAE | RMSE | Within 10 | Dangerous error |
| --- | ---: | ---: | ---: | ---: |
| Random Forest baseline | 11.952 | 21.735 | 66.0% | 1.91% |
| Two-stage CatBoost | **10.866** | 21.124 | 68.9% | 0.96% |
| Direct CatBoost MAE | 11.340 | 21.835 | **70.8%** | **0.48%** |
| Direct CatBoost Huber | 13.373 | 22.811 | 62.2% | 1.44% |
| LightGBM L1 | 11.732 | 22.644 | 69.4% | 1.44% |
| LightGBM Huber | 28.555 | 38.869 | 23.9% | **0.48%** |
| XGBoost L1 | 11.426 | 22.103 | 68.4% | 0.96% |
| XGBoost Pseudo-Huber | 11.569 | **20.988** | 67.5% | **0.48%** |

What worked:

- The two-stage model produced the best standalone out-of-fold MAE.
- Direct CatBoost MAE produced complementary predictions and strong within-10 accuracy.
- XGBoost Pseudo-Huber produced the best challenger RMSE and R-squared, although its MAE was not the best in its family.
- A conservative convex blend generalized better than any single challenger on typical-error metrics.

What did not work:

- LightGBM Huber underfit this endpoint-heavy target badly.
- CatBoost Huber was consistently weaker than CatBoost MAE.
- Ridge stacking overfit the small meta-training dataset and was rejected.
- An unconstrained blend placed too much weight on the two-stage model and increased holdout RMSE.

## Final Non-Embedding Model

The deployed model is a guarded convex ensemble:

- 50% Random Forest baseline;
- 30% two-stage CatBoost;
- 20% direct CatBoost MAE;
- fallback to Random Forest when the blended prediction differs from it by more than 20 points.

Compared with the previous Random Forest on the untouched 70-row internal holdout:

| Metric | Previous | Final ensemble | Change |
| --- | ---: | ---: | ---: |
| MAE | 10.157 | **9.743** | 4.1% better |
| RMSE | **19.136** | 19.310 | 0.91% worse |
| Within 5 points | 55.7% | **61.4%** | +5.7 points |
| Within 10 points | 68.6% | **74.3%** | +5.7 points |
| Dangerous error rate | 1.43% | 1.43% | unchanged |

The ensemble was accepted because MAE and both close-accuracy measures improved, dangerous errors did not increase, and the RMSE regression remained below the explicit 2% tolerance.

Warm prediction over 2,500 rows took a median 0.0507 seconds, versus 0.0439 seconds for Random Forest alone: a 1.16x slowdown while still processing about 49,000 rows per second on the evaluation machine.

## Evaluation Protocol

1. Reserve 25% of internal examples as the final PR-grouped holdout.
2. Run three repetitions of four-fold grouped validation on the remaining internal examples.
3. Add all audited Hugging Face examples only to each training fold.
4. Select model variants and ensemble weights using out-of-fold predictions only.
5. Evaluate the selected candidate once on the untouched holdout.
6. Deploy only when:
   - percentage MAE improves;
   - within-10-points accuracy improves;
   - dangerous endpoint errors do not increase;
   - percentage RMSE improves or its regression stays below 2%.
7. Continue returning only `model_predicted_percentage` as an integer in `[0, 100]`.

All reported evaluation metrics use the same rounded integer percentages returned by production inference.

## Embeddings Results and Next Plan

Frozen UniXcoder and CodeBERT features are now implemented and evaluated. They remain isolated from production because the selected embedding blend failed the strict holdout deployment gates.

Development results favored embedding-enhanced two-stage models, especially CodeBERT (MAE `10.818`, RMSE `20.828`). The selected guarded blend reached development MAE `10.766`, but on the 70-row holdout it worsened MAE from `9.743` to `10.129`, RMSE from `19.310` to `20.212`, and within-10 accuracy from `74.3%` to `72.9%`. Dangerous errors were unchanged. The current non-embedding production ensemble was therefore retained.

A leave-one-repository-out evaluation now provides a stricter transfer test. Each of the 29 external repositories was held out in turn, while the model trained on all 279 internal rows and the other 28 external repositories. Across 2,500 predictions, the guarded embedding blend changed MAE from `4.1064` to `4.0844`, but the 0.022-point reduction was uncertain (repository-bootstrap 95% interval `-0.0431` to `+0.0825`). RMSE worsened from `8.8214` to `8.9965`, and within-10 accuracy fell from `89.16%` to `88.40%`. Standalone embedding models were worse than production on MAE, RMSE, and within-10 accuracy.

Confidence-stratified results indicate that embeddings help clear examples but hurt ambiguous ones. High-confidence MAE improved from `1.0146` to `0.8261`; low-confidence MAE worsened from `8.8235` to `9.3371`. This supports using future semantic models selectively, after confidence or uncertainty estimation, rather than as an unconditional replacement.

Jina was not executed because the checkpoint required repository-supplied Python, while the safe built-in loader produced an architecture mismatch and missing weights. It should only be revisited through a reviewed implementation.

### Why embeddings may help

The current features measure lexical overlap, normalized tokens, structural overlap, and diff geometry. They can miss semantically equivalent changes when implementations use different names, APIs, control flow, helper functions, or file locations.

Code-aware embeddings can add a semantic signal for those cases. They should supplement, not replace, deterministic features.

### Candidate approaches

#### A. Frozen bi-encoder features

Encode the suggestion and landed code independently, then calculate compact pair features:

- cosine similarity;
- dot-product similarity after normalization;
- maximum and mean suggestion-to-hunk similarity;
- top-three hunk similarities;
- similarity margin between the best and second-best hunks;
- per-file maximum similarity;
- optional PCA projection of absolute difference and elementwise product vectors.

Start with:

- `microsoft/unixcoder-base` for code-aware representations;
- `jinaai/jina-embeddings-v2-base-code` when long-context support is important.

UniXcoder is pretrained from code, comments, and AST-related data. Jina's model supports many programming languages and up to 8,192 tokens, but long diffs should still be chunked for attribution and stable latency.

Sources:

- https://huggingface.co/microsoft/unixcoder-base
- https://huggingface.co/jinaai/jina-embeddings-v2-base-code

#### B. Cross-encoder pair scoring

Feed the suggestion and each candidate landed hunk into one transformer and predict their semantic match jointly. Cross-encoders are usually more accurate than independent embeddings for a known pair, but are slower because every suggestion-hunk pair requires a forward pass.

Use the cross-encoder only on the top candidate hunks selected by deterministic overlap or a bi-encoder. Store features such as maximum score, mean top-three score, and score margin.

Source: https://www.sbert.net/examples/cross_encoder/applications/README.html

#### C. Fine-tuned semantic percentage model

After frozen-feature baselines are stable, fine-tune a pair model directly against percentage labels.

Recommended progression:

1. Binary pretraining: distinguish matched from clearly unmatched suggestion/diff pairs.
2. Three-regime fine-tuning: `0`, intermediate, and `100` as an auxiliary objective.
3. Percentage regression head: optimize Huber or MAE loss.
4. Multi-task loss: percentage regression plus endpoint classification.

Do not start here. With only 279 internal labels, direct fine-tuning has a high overfitting risk.

## Embedding Data Preparation

1. Parse suggestions and landed diffs into files and hunks.
2. Remove diff metadata that cannot affect semantics, but preserve added/deleted markers and language identifiers.
3. Pair each suggestion with candidate hunks from overlapping files first.
4. Add cross-file candidates when filenames, identifiers, or imports suggest moved code.
5. Chunk by syntax boundaries when possible; otherwise use overlapping token windows.
6. Cache embeddings by a hash of model version, preprocessing version, language, and normalized text.
7. Never compute normalization, PCA, calibration, or learned aggregation parameters using holdout rows.

## Feature Integration

Start with scalar similarity features rather than hundreds of raw embedding dimensions. This is safer for the small internal dataset.

Recommended first feature set:

- best hunk cosine similarity;
- mean top-three hunk similarity;
- best-to-second-best margin;
- suggestion-to-full-diff similarity;
- source and target embedding norms;
- number of chunks above similarity thresholds `0.6`, `0.7`, and `0.8`;
- same-file and cross-file best similarities;
- interaction between semantic similarity and existing token/AST overlap.

If raw vectors are later used, fit PCA inside each training fold and compare 16, 32, and 64 dimensions. Never fit PCA globally before cross-validation.

## Training Strategy

1. Generate frozen embeddings for every example and cache them.
2. Join only derived embedding features to the current metric table.
3. Re-run the same repeated PR-grouped evaluation.
4. Compare:
   - current deployed model;
   - current model plus scalar embedding similarities;
   - non-negative ensemble with an embedding-enhanced model;
   - cross-encoder score features.
5. Tune on internal out-of-fold predictions.
6. Use Hugging Face confidence weights during training.
7. Keep the internal holdout untouched until one final evaluation.

## Embedding Acceptance Gates

An embedding candidate should be deployed only if it:

- improves internal holdout MAE and RMSE;
- does not increase dangerous endpoint errors;
- improves or preserves within-10-points accuracy;
- has stable gains across languages and repositories;
- stays within an agreed inference latency and memory budget;
- reproduces results from a pinned model revision and preprocessing version.

## Diagnostics

Report metrics by:

- label regime: `0`, intermediate, `100`;
- programming language;
- suggestion size;
- landed diff size;
- same-file versus cross-file match;
- audit confidence;
- repository, when the sample size is sufficient.

Inspect the largest regressions manually. Prioritize additional labels where models disagree most or where confidence is low.

## Recommended Implementation Order

1. Freeze the current production and embedding experiment artifacts.
2. Treat the completed repository-held-out evaluation as exploratory because its labels are LLM-assisted.
3. Build a new independently human-adjudicated, multi-repository test set.
4. Diagnose embedding failures by confidence, language, label regime, and candidate retrieval.
5. Test hard-negative retrieval and stronger pooling without consulting the new test set.
6. Add a cross-encoder only for examples where deterministic and embedding models disagree.
7. Revisit Jina only through a security-reviewed or native implementation.
8. Fine-tune only after the internal labeled set is substantially larger.
