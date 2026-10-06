from __future__ import annotations

import csv
import json
from pathlib import Path

from pr_suggestion_metrics.model_inference import predict_coverage_percentages
from pr_suggestion_metrics.modeling.demo_train import _split_for_group, train_demo_model


def _row(index: int, *, pr_number: int) -> dict[str, object]:
    landed_line = f"value_{index} = {index}" if index % 2 == 0 else f"other_{index} = {index}"
    return {
        "example_id": f"example-{index}",
        "repo": "host/owner/repo",
        "pr_url": f"https://host/owner/repo/pull/{pr_number}",
        "pr_number": pr_number,
        "suggested_diff": f"--- a/file_{index}.py\n+++ b/file_{index}.py\n@@ -0,0 +1 @@\n+value_{index} = {index}\n",
        "landed_diff": f"--- a/file_{index}.py\n+++ b/file_{index}.py\n@@ -0,0 +1 @@\n+{landed_line}\n",
        "expected_landed_percentage": 100 if index % 2 == 0 else 0,
    }


def _rows_covering_required_splits() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    split_counts = {"train": 0, "development": 0, "calibration": 0}
    pr_number = 1
    while split_counts["train"] < 4 or split_counts["development"] < 2 or split_counts["calibration"] < 1:
        group_id = f"host/owner/repo#{pr_number}"
        split = _split_for_group(group_id)
        if (
            split == "train"
            and split_counts[split] < 4
            or split == "development"
            and split_counts[split] < 2
            or split == "calibration"
            and split_counts[split] < 1
        ):
            rows.append(_row(len(rows), pr_number=pr_number))
            split_counts[split] += 1
        pr_number += 1
    return rows


def test_train_demo_model_builds_weak_phase5_derived_artifact(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        "".join(json.dumps(row) + "\n" for row in _rows_covering_required_splits()),
        encoding="utf-8",
    )
    output_dir = tmp_path / "demo_model"

    manifest = train_demo_model(dataset_path=dataset_path, output_dir=output_dir)

    assert manifest["purpose"] == "interview_demo_percentage_model"
    assert manifest["validation_claim"] == "weak local labels only; not human validated; not release validated"
    assert manifest["feature_report"]["label_source"] == "weak_local_llm_assisted_demo"
    assert (output_dir / "features.csv").is_file()
    assert (output_dir / "model" / "model.joblib").is_file()
    assert (output_dir / "model" / "artifact_manifest.json").is_file()
    assert (output_dir / "README.md").read_text(encoding="utf-8").startswith("# Demo percentage model")

    with (output_dir / "features.csv").open(encoding="utf-8", newline="") as stream:
        feature_rows = list(csv.DictReader(stream))
    predictions = predict_coverage_percentages(feature_rows[:1], model_dir=output_dir / "model")

    assert {row["split"] for row in feature_rows} == {"train", "development", "calibration"}
    assert {row["label_source"] for row in feature_rows} == {"weak_local_llm_assisted_demo"}
    assert predictions["model_predicted_percentage"].between(0, 100).all()
