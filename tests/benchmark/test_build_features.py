from __future__ import annotations

import csv
import json
from pathlib import Path

from pr_suggestion_metrics.benchmark.build_features import build_frozen_feature_tables


def test_builds_features_and_records_unsupported_rows(tmp_path: Path) -> None:
    benchmark_dir = tmp_path / "benchmark"
    benchmark_dir.mkdir()
    supported = {
        "example_id": "supported",
        "repo": "host/owner/repo",
        "pr_url": "https://host/owner/repo/pull/1",
        "pr_number": 1,
        "suggested_diff": "--- a/a.py\n+++ b/a.py\n@@ -0,0 +1 @@\n+return value\n",
        "landed_diff": "--- a/a.py\n+++ b/a.py\n@@ -0,0 +1 @@\n+return value\n",
        "coverage_percentage": 100,
        "coverage_unrounded": 100.0,
    }
    unsupported = {
        **supported,
        "example_id": "unsupported",
        "suggested_diff": "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n",
    }
    (benchmark_dir / "train.jsonl").write_text(
        json.dumps(supported) + "\n" + json.dumps(unsupported) + "\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "features"
    manifest = build_frozen_feature_tables(benchmark_dir=benchmark_dir, output_dir=output_dir)

    with (output_dir / "features.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    abstentions = [json.loads(line) for line in (output_dir / "feature_abstentions.jsonl").read_text().splitlines()]
    assert [row["example_id"] for row in rows] == ["supported"]
    assert abstentions[0]["example_id"] == "unsupported"
    assert manifest["feature_rows"] == 1
    assert manifest["abstained_rows"] == 1
