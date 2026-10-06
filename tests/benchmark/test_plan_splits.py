from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from pr_suggestion_metrics.benchmark.plan_splits import plan_splits


def _snapshot(revision: str, path: str) -> dict[str, str]:
    content = f"content for {path}"
    return {
        "revision_sha": revision,
        "path": path,
        "content": content,
        "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "source": "test",
    }


def _example(index: int) -> dict[str, object]:
    path = f"src/file_{index}.py"
    return {
        "example_id": f"example-{index}",
        "repo": f"host/owner/repo-{index}",
        "pr_url": f"https://host/owner/repo-{index}/pull/{index}",
        "pr_number": index,
        "suggested_diff": f"--- a/{path}\n+++ b/{path}\n@@\n+call_{index}({',' * index})\n",
        "landed_diff": f"--- a/{path}\n+++ b/{path}\n@@\n+call_{index}({',' * index})\n",
        "suggestion_provenance": {
            "source_kind": "github_review_comment",
            "suggestion_id": f"suggestion-{index}",
            "suggestion_created_at": f"2026-01-{index:02d}T00:00:00Z",
            "original_commit_sha": "a" * 40,
            "path": path,
            "merge_commit_sha": "d" * 40,
            "pr_merged_at": f"2026-02-{index:02d}T00:00:00Z",
            "compared_diff_base_sha": "b" * 40,
            "compared_diff_head_sha": "c" * 40,
            "suggestion_base_snapshot": _snapshot("a" * 40, path),
            "final_state_snapshot": _snapshot("d" * 40, path),
        },
    }


def test_planner_is_deterministic_and_creates_calibration_split(tmp_path: Path) -> None:
    examples_path = tmp_path / "examples.jsonl"
    examples_path.write_text("".join(json.dumps(_example(index)) + "\n" for index in range(1, 9)))
    first_output = tmp_path / "first.csv"
    second_output = tmp_path / "second.csv"

    first = plan_splits(
        examples_path=examples_path,
        output_path=first_output,
        report_path=tmp_path / "first.json",
        policy="repository_disjoint",
        seed=42,
    )
    plan_splits(
        examples_path=examples_path,
        output_path=second_output,
        report_path=tmp_path / "second.json",
        policy="repository_disjoint",
        seed=42,
    )

    assert first_output.read_text() == second_output.read_text()
    with first_output.open(newline="") as stream:
        splits = {row["split"] for row in csv.DictReader(stream)}
    assert splits == {"train", "development", "calibration", "test"}
    assert first["independent_components"] == 8


def test_temporal_planner_is_stable_for_equal_timestamps(tmp_path: Path) -> None:
    rows = [_example(index) for index in range(1, 5)]
    for row in rows:
        row["suggestion_provenance"]["pr_merged_at"] = "2026-02-01T00:00:00Z"  # type: ignore[index]
    first_examples = tmp_path / "first.jsonl"
    reversed_examples = tmp_path / "reversed.jsonl"
    first_examples.write_text("".join(json.dumps(row) + "\n" for row in rows))
    reversed_examples.write_text("".join(json.dumps(row) + "\n" for row in reversed(rows)))

    first_output = tmp_path / "first.csv"
    reversed_output = tmp_path / "reversed.csv"
    plan_splits(
        examples_path=first_examples,
        output_path=first_output,
        report_path=tmp_path / "first.json",
        policy="temporal",
        seed=42,
    )
    plan_splits(
        examples_path=reversed_examples,
        output_path=reversed_output,
        report_path=tmp_path / "reversed.json",
        policy="temporal",
        seed=42,
    )

    assert first_output.read_text() == reversed_output.read_text()


def test_temporal_planner_orders_timezone_offsets_by_instant(tmp_path: Path) -> None:
    rows = [_example(index) for index in range(1, 5)]
    merge_times = (
        "2026-02-01T00:30:00+01:00",
        "2026-02-01T00:00:00Z",
        "2026-02-01T01:00:00Z",
        "2026-02-01T02:00:00Z",
    )
    for row, merge_time in zip(rows, merge_times, strict=True):
        row["suggestion_provenance"]["pr_merged_at"] = merge_time  # type: ignore[index]
    examples_path = tmp_path / "examples.jsonl"
    examples_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    output_path = tmp_path / "splits.csv"

    plan_splits(
        examples_path=examples_path,
        output_path=output_path,
        report_path=tmp_path / "report.json",
        policy="temporal",
        seed=42,
    )

    with output_path.open(newline="") as stream:
        assignments = {row["example_id"]: row["split"] for row in csv.DictReader(stream)}
    assert assignments["example-1"] == "train"
    assert assignments["example-2"] == "development"


def test_planner_rejects_unknown_policy(tmp_path: Path) -> None:
    examples_path = tmp_path / "examples.jsonl"
    examples_path.write_text("".join(json.dumps(_example(index)) + "\n" for index in range(1, 5)))

    with pytest.raises(ValueError, match="Unsupported split policy"):
        plan_splits(
            examples_path=examples_path,
            output_path=tmp_path / "splits.csv",
            report_path=tmp_path / "report.json",
            policy="typo",  # type: ignore[arg-type]
            seed=42,
        )
