# FL PR Comment Pair Dataset

Raw rows read: 279
Dataset rows: 279
Repositories: 1

Files:
- dataset.jsonl: ML-ready records with full suggestion and landed diffs.
- labels.csv: compact percentage-target sheet keyed by example_id.

Target format:
- expected_landed_percentage: integer from 0 through 100

Important: deterministic_landed_estimate is only a weak sorting/helper signal, not ground truth.
