# Semantic Suggestion Coverage Paper

This directory contains the research paper and its reproducibility artifacts.

- `semantic-suggestion-coverage-paper.md`: accessible research-grade paper.
- `references.bib`: machine-readable bibliography.
- `analysis_results.json`: generated dataset summaries, holdout metrics, subgroup results, and grouped-bootstrap intervals.
- `assets/`: generated publication figures.
- `../../models/pr_suggestion_coverage_embeddings/evaluation_report.json`: frozen embedding experiment results.

Regenerate statistics and figures from the repository root:

```bash
MPLCONFIGDIR=.matplotlib-cache \
uv run --locked --extra train --extra notebooks python \
  -m pr_suggestion_metrics.generate_percentage_paper_assets \
  --output-dir docs/paper \
  --model-dir models/pr_suggestion_coverage_regression
```

The paper is an internal working paper. Assign named authors and complete the confirmatory evaluation described in Section 11 before external submission.
