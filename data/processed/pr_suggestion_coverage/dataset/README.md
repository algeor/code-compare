# FL PR Comment Pair Dataset

Raw rows read: 279
Dataset rows: 279
Repositories: 1

Files:
- dataset.jsonl: ML-ready records with full suggestion and landed diffs.
- labels.csv: compact manual labeling sheet keyed by example_id, including exact percentage and bucket labels.

Label options:
- 0%
- partial
- mostly
- 100%

Percentage buckets:
- 0
- 1-10
- 11-20
- 21-30
- 31-40
- 41-50
- 51-60
- 61-70
- 71-80
- 81-90
- 91-100
- 100

Important: deterministic_landed_estimate is only a weak sorting/helper signal, not ground truth.
