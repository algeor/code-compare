"""Show Diff Precision/Recall and model output for one dataset example."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pr_suggestion_metrics.diff_precision_recall import compare_diffs
from pr_suggestion_metrics.model_inference import predict_coverage_from_diffs


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATASET = _REPOSITORY_ROOT / "data" / "external" / "github_codereview" / "dataset" / "dataset.jsonl"
_DEFAULT_EXAMPLE_ID = "4cd17d7210f1d44c"


def _load_example(path: Path, example_id: str) -> dict[str, object]:
    with path.open(encoding="utf-8") as input_file:
        for line in input_file:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("example_id") == example_id:
                return row
    raise ValueError(f"Example {example_id!r} was not found in {path}")


def _percentage(value: float) -> int:
    return round(value * 100)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--example-id", default=_DEFAULT_EXAMPLE_ID)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    example = _load_example(args.dataset, args.example_id)
    draft_diff = str(example["suggested_diff"])
    final_diff = str(example["landed_diff"])
    result = compare_diffs(draft_diff, final_diff)
    prediction = predict_coverage_from_diffs(draft_diff, final_diff, example_id=args.example_id)

    print(f"example: {args.example_id}")
    print(f"repository: {example.get('repo', 'unknown')}")
    print(f"pull request: {example.get('pr_url', 'unknown')}")
    print(f"reference percentage: {example.get('expected_landed_percentage', 'unknown')}%")
    print(f"model percentage: {prediction['model_predicted_percentage']}%")
    print()
    print("Diff Precision/Recall")
    print(f"  token: precision={_percentage(result.token.precision)}% recall={_percentage(result.token.recall)}%")
    print(f"  file:  precision={_percentage(result.file.precision)}% recall={_percentage(result.file.recall)}%")
    print(f"  line:  precision={_percentage(result.line.precision)}% recall={_percentage(result.line.recall)}%")
    print(f"  aggregate F1: {_percentage(result.aggregate_f1)}%")


if __name__ == "__main__":
    main()
