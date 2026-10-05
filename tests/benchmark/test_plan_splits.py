from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

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
