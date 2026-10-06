from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pr_suggestion_metrics.benchmark.build_features import build_frozen_feature_tables
from pr_suggestion_metrics.model_artifacts import sha256_file


def _write_benchmark_manifest(benchmark_dir: Path) -> Path:
    manifest_path = benchmark_dir / "benchmark_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "artifact_sha256": {
                    split: sha256_file(benchmark_dir / f"{split}.jsonl")
                    for split in ("train", "development", "calibration")
                }
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


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
    (benchmark_dir / "development.jsonl").write_text("", encoding="utf-8")
    (benchmark_dir / "calibration.jsonl").write_text("", encoding="utf-8")
    benchmark_manifest_path = _write_benchmark_manifest(benchmark_dir)

    output_dir = tmp_path / "features"
    manifest = build_frozen_feature_tables(benchmark_dir=benchmark_dir, output_dir=output_dir)

    with (output_dir / "features.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    abstentions = [json.loads(line) for line in (output_dir / "feature_abstentions.jsonl").read_text().splitlines()]
    assert [row["example_id"] for row in rows] == ["supported"]
    assert abstentions[0]["example_id"] == "unsupported"
    assert manifest["feature_rows"] == 1
    assert manifest["abstained_rows"] == 1
    assert manifest["benchmark_manifest_sha256"] == sha256_file(benchmark_manifest_path)


def test_rejects_tampered_split_before_creating_output(tmp_path: Path) -> None:
    benchmark_dir = tmp_path / "benchmark"
    benchmark_dir.mkdir()
    for split in ("train", "development", "calibration"):
        (benchmark_dir / f"{split}.jsonl").write_text("", encoding="utf-8")
    _write_benchmark_manifest(benchmark_dir)
    (benchmark_dir / "development.jsonl").write_text("tampered\n", encoding="utf-8")
    output_dir = tmp_path / "features"

    try:
        build_frozen_feature_tables(benchmark_dir=benchmark_dir, output_dir=output_dir)
    except ValueError as exc:
        assert "development split does not match" in str(exc)
    else:
        raise AssertionError("Expected tampered split rejection")

    assert not output_dir.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("coverage_percentage", 99.5),
        ("coverage_unrounded", float("inf")),
    ],
)
def test_rejects_invalid_coverage_values(tmp_path: Path, field: str, value: float) -> None:
    benchmark_dir = tmp_path / "benchmark"
    benchmark_dir.mkdir()
    row = {
        "example_id": "invalid-coverage",
        "repo": "host/owner/repo",
        "pr_url": "https://host/owner/repo/pull/1",
        "pr_number": 1,
        "suggested_diff": "--- a/a.py\n+++ b/a.py\n@@ -0,0 +1 @@\n+return value\n",
        "landed_diff": "--- a/a.py\n+++ b/a.py\n@@ -0,0 +1 @@\n+return value\n",
        "coverage_percentage": 100,
        "coverage_unrounded": 100.0,
    }
    row[field] = value
    (benchmark_dir / "train.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (benchmark_dir / "development.jsonl").write_text("", encoding="utf-8")
    (benchmark_dir / "calibration.jsonl").write_text("", encoding="utf-8")
    _write_benchmark_manifest(benchmark_dir)

    with pytest.raises(ValueError, match=field):
        build_frozen_feature_tables(benchmark_dir=benchmark_dir, output_dir=tmp_path / "features")
