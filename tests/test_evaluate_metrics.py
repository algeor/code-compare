from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pr_suggestion_metrics.evaluate_metrics import _load_dataset, _load_labeled_examples


def _write_dataset_dir(tmp_path: Path, *, label_overrides: dict[str, object] | None = None) -> Path:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "dataset.jsonl").write_text(
        json.dumps(
            {
                "example_id": "example",
                "suggested_diff": "suggested",
                "landed_diff": "landed",
                "expected_landed_percentage": 50,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    label = {
        "example_id": "example",
        "expected_landed_percentage": 50,
        "deterministic_landed_estimate": 40,
        "file_overlap_ratio": 0.5,
        "changed_line_overlap_ratio": 0.25,
        **(label_overrides or {}),
    }
    with (dataset_dir / "labels.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(label))
        writer.writeheader()
        writer.writerow(label)
    return dataset_dir


def test_load_dataset_rejects_invalid_utf8(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_bytes(b'{"example_id":"example"}\xff\n')

    with pytest.raises(UnicodeDecodeError):
        _load_dataset(dataset_path)


def test_load_dataset_rejects_duplicate_example_ids(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    row = {"example_id": "duplicate", "suggested_diff": "suggested", "landed_diff": "landed"}
    dataset_path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate example_id 'duplicate'"):
        _load_dataset(dataset_path)


@pytest.mark.parametrize(
    ("label_overrides", "message"),
    [
        ({"expected_landed_percentage": 50.5}, "expected_landed_percentage"),
        ({"deterministic_landed_estimate": 40.5}, "deterministic_landed_estimate"),
        ({"file_overlap_ratio": "nan"}, "file_overlap_ratio"),
        ({"changed_line_overlap_ratio": 1.1}, "changed_line_overlap_ratio"),
    ],
)
def test_load_labeled_examples_rejects_invalid_numeric_labels(
    tmp_path: Path,
    label_overrides: dict[str, object],
    message: str,
) -> None:
    dataset_dir = _write_dataset_dir(tmp_path, label_overrides=label_overrides)

    with pytest.raises(ValueError, match=message):
        _load_labeled_examples(dataset_dir)
