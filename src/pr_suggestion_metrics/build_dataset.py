#!/usr/bin/env python3
"""Build an ML-ready dataset from FL suggestion/merged PR diff pairs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

HumanLabel = Literal["0%", "partial", "mostly", "100%"]
PercentageBucket = Literal[
    "0",
    "1-10",
    "11-20",
    "21-30",
    "31-40",
    "41-50",
    "51-60",
    "61-70",
    "71-80",
    "81-90",
    "91-100",
]

_DIFF_PATH_RE = re.compile(r"^diff --git a/(.*?) b/(.*)$")
_OLD_FILE_RE = re.compile(r"^---\s+(?:a/)?(.+)$")
_NEW_FILE_RE = re.compile(r"^\+\+\+\s+(?:b/)?(.+)$")
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class RawPair(BaseModel):
    """One raw row produced by the PR suggestion pair collector."""

    inspection_id: str
    fault_id: str
    handler_code_changes_diff: str
    merged_pr_diff: str
    repo_host: str
    repo_owner: str
    repo_name: str
    pr_number: int
    pr_url: str
    source_branch: str | None = None
    target_branch: str | None = None
    base_sha: str | None = None
    head_sha: str | None = None
    merge_commit_sha: str | None = None
    inspection_commit_sha: str | None = None
    handler_diff_path: str
    merged_pr_diff_source: str
    expected_landed_percentage: int | None = None
    human_label: HumanLabel | None = None
    reviewer_edited_version: str | None = None
    renamed_files: bool | None = None
    config_files_touched: bool | None = None


class DiffStats(BaseModel):
    """Small, deterministic features extracted from a unified diff."""

    file_count: int
    added_lines: int
    removed_lines: int
    hunk_count: int
    files: list[str]


class DatasetRow(BaseModel):
    """One label-ready training example."""

    example_id: str
    inspection_id: str
    fault_id: str
    repo: str
    pr_url: str
    pr_number: int
    source_branch: str | None
    target_branch: str | None
    base_sha: str | None
    head_sha: str | None
    merge_commit_sha: str | None
    suggestion_source: str
    merged_pr_diff_source: str
    suggested_diff: str
    landed_diff: str
    suggested_stats: DiffStats
    landed_stats: DiffStats
    file_overlap_ratio: float
    changed_line_overlap_ratio: float
    deterministic_landed_estimate: int
    label: HumanLabel | None = None
    expected_landed_percentage: int | None = None
    expected_percentage_bucket: PercentageBucket | None = None
    label_notes: str = ""
    split: Literal["unassigned", "train", "validation", "test"] = "unassigned"
    metadata: dict[str, object] = Field(default_factory=dict)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="Raw pair JSONL files.")
    parser.add_argument("--output-dir", type=Path, default=Path("/private/tmp/fl-pr-ml-dataset"))
    parser.add_argument("--dedupe", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def _read_pairs(paths: list[Path]) -> list[RawPair]:
    """Read raw JSONL pairs from one or more files."""
    rows: list[RawPair] = []
    for path in paths:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    rows.append(RawPair.model_validate_json(line))
                except ValueError as exc:
                    raise ValueError(f"Could not parse {path}:{line_number}: {exc}") from exc
    return rows


def _diff_stats(diff_text: str) -> DiffStats:
    """Compute compact unified-diff statistics."""
    files: list[str] = []
    added_lines = 0
    removed_lines = 0
    hunk_count = 0
    for line in diff_text.splitlines():
        match = _DIFF_PATH_RE.match(line)
        if match:
            files.append(match.group(2))
            continue
        new_file_match = _NEW_FILE_RE.match(line)
        if new_file_match and new_file_match.group(1) != "/dev/null":
            files.append(new_file_match.group(1))
            continue
        if _HUNK_RE.match(line):
            hunk_count += 1
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added_lines += 1
        elif line.startswith("-"):
            removed_lines += 1
    return DiffStats(
        file_count=len(set(files)),
        added_lines=added_lines,
        removed_lines=removed_lines,
        hunk_count=hunk_count,
        files=sorted(set(files)),
    )


def _changed_files_from_headers(diff_text: str) -> set[str]:
    """Return changed files from git and unified diff headers."""
    files: set[str] = set()
    for line in diff_text.splitlines():
        git_match = _DIFF_PATH_RE.match(line)
        if git_match:
            files.add(git_match.group(2))
            continue
        new_file_match = _NEW_FILE_RE.match(line)
        if new_file_match and new_file_match.group(1) != "/dev/null":
            files.add(new_file_match.group(1))
            continue
        old_file_match = _OLD_FILE_RE.match(line)
        if old_file_match and old_file_match.group(1) != "/dev/null":
            files.add(old_file_match.group(1))
    return files


def _changed_lines(diff_text: str) -> set[str]:
    """Return normalized added/removed lines for rough deterministic overlap."""
    lines: set[str] = set()
    for line in diff_text.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            normalized = line[1:].strip()
            if normalized:
                lines.add(normalized)
    return lines


def _ratio(left: set[str], right: set[str]) -> float:
    """Return how much of left appears in right."""
    if not left:
        return 0.0
    return round(len(left & right) / len(left), 4)


def _estimate_landed_percentage(file_overlap: float, line_overlap: float) -> int:
    """Build a crude label-prior for sorting, not a replacement for human labeling."""
    return round((0.35 * file_overlap + 0.65 * line_overlap) * 100)


def _suggest_label(percentage: int) -> HumanLabel:
    """Map the deterministic percentage to a review starting label."""
    if percentage >= 90:
        return "100%"
    if percentage >= 60:
        return "mostly"
    if percentage >= 20:
        return "partial"
    return "0%"


def _rationale(row: DatasetRow) -> str:
    """Explain the deterministic suggestion in one compact sentence."""
    return (
        f"Suggested files overlapping landed files: {row.file_overlap_ratio:.0%}; "
        f"changed-line overlap: {row.changed_line_overlap_ratio:.0%}; "
        f"suggested {row.suggested_stats.file_count} file(s), landed {row.landed_stats.file_count} file(s)."
    )


def _example_id(pair: RawPair) -> str:
    """Create a stable ID for deduplication and labeling."""
    raw = f"{pair.pr_url}|{pair.handler_diff_path}|{pair.handler_code_changes_diff}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _dataset_row(pair: RawPair) -> DatasetRow:
    """Convert one raw pair into a model-training row."""
    suggested_stats = _diff_stats(pair.handler_code_changes_diff)
    landed_stats = _diff_stats(pair.merged_pr_diff)
    file_overlap = _ratio(set(suggested_stats.files), set(landed_stats.files))
    changed_line_overlap = _ratio(_changed_lines(pair.handler_code_changes_diff), _changed_lines(pair.merged_pr_diff))
    return DatasetRow(
        example_id=_example_id(pair),
        inspection_id=pair.inspection_id,
        fault_id=pair.fault_id,
        repo=f"{pair.repo_host}/{pair.repo_owner}/{pair.repo_name}",
        pr_url=pair.pr_url,
        pr_number=pair.pr_number,
        source_branch=pair.source_branch,
        target_branch=pair.target_branch,
        base_sha=pair.base_sha,
        head_sha=pair.head_sha,
        merge_commit_sha=pair.merge_commit_sha,
        suggestion_source=pair.handler_diff_path,
        merged_pr_diff_source=pair.merged_pr_diff_source,
        suggested_diff=pair.handler_code_changes_diff,
        landed_diff=pair.merged_pr_diff,
        suggested_stats=suggested_stats,
        landed_stats=landed_stats,
        file_overlap_ratio=file_overlap,
        changed_line_overlap_ratio=changed_line_overlap,
        deterministic_landed_estimate=_estimate_landed_percentage(file_overlap, changed_line_overlap),
        label=pair.human_label,
        expected_landed_percentage=pair.expected_landed_percentage,
        expected_percentage_bucket=_percentage_bucket(pair.expected_landed_percentage)
        if pair.expected_landed_percentage is not None
        else None,
        metadata={
            "renamed_files": pair.renamed_files,
            "config_files_touched": pair.config_files_touched,
            "reviewer_edited_version": pair.reviewer_edited_version,
            "inspection_commit_sha": pair.inspection_commit_sha,
        },
    )


def _write_jsonl(path: Path, rows: list[DatasetRow]) -> None:
    """Write dataset rows as JSONL."""
    path.write_text("".join(row.model_dump_json(exclude_none=False) + "\n" for row in rows), encoding="utf-8")


def _write_labels_csv(path: Path, rows: list[DatasetRow]) -> None:
    """Write a compact CSV intended for manual labels."""
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "example_id",
                "label",
                "expected_landed_percentage",
                "expected_percentage_bucket",
                "label_notes",
                "suggested_label",
                "suggested_percentage",
                "suggested_rationale",
                "pr_url",
                "repo",
                "suggestion_source",
                "deterministic_landed_estimate",
                "file_overlap_ratio",
                "changed_line_overlap_ratio",
                "suggested_files",
                "landed_files",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "example_id": row.example_id,
                    "label": row.label or "",
                    "expected_landed_percentage": (
                        row.expected_landed_percentage if row.expected_landed_percentage is not None else ""
                    ),
                    "expected_percentage_bucket": _percentage_bucket(row.expected_landed_percentage)
                    if row.expected_landed_percentage is not None
                    else "",
                    "label_notes": row.label_notes,
                    "suggested_label": _suggest_label(row.deterministic_landed_estimate),
                    "suggested_percentage": row.deterministic_landed_estimate,
                    "suggested_rationale": _rationale(row),
                    "pr_url": row.pr_url,
                    "repo": row.repo,
                    "suggestion_source": row.suggestion_source,
                    "deterministic_landed_estimate": row.deterministic_landed_estimate,
                    "file_overlap_ratio": row.file_overlap_ratio,
                    "changed_line_overlap_ratio": row.changed_line_overlap_ratio,
                    "suggested_files": ";".join(row.suggested_stats.files),
                    "landed_files": ";".join(row.landed_stats.files),
                }
            )


def _write_summary(path: Path, rows: list[DatasetRow], raw_count: int) -> None:
    """Write a small human-readable summary."""
    repos = sorted({row.repo for row in rows})
    content = [
        "# FL PR Comment Pair Dataset",
        "",
        f"Raw rows read: {raw_count}",
        f"Dataset rows: {len(rows)}",
        f"Repositories: {len(repos)}",
        "",
        "Files:",
        "- dataset.jsonl: ML-ready records with full suggestion and landed diffs.",
        "- labels.csv: compact manual labeling sheet keyed by example_id.",
        "",
        "Label options:",
        "- 0%",
        "- partial",
        "- mostly",
        "- 100%",
        "",
        "Important: deterministic_landed_estimate is only a weak sorting/helper signal, not ground truth.",
    ]
    path.write_text("\n".join(content) + "\n", encoding="utf-8")


def _percentage_bucket(percentage: int) -> PercentageBucket:
    """Map a manual 0-100 percentage to the dataset bucket label."""
    bounded_percentage = max(0, min(100, int(round(percentage))))
    if bounded_percentage == 0:
        return "0"
    lower_bound = ((bounded_percentage - 1) // 10) * 10 + 1
    upper_bound = min(lower_bound + 9, 100)
    return f"{lower_bound}-{upper_bound}"  # type: ignore[return-value]


def main() -> int:
    """Build the dataset artifacts."""
    args = parse_args()
    pairs = _read_pairs(args.inputs)
    rows = [_dataset_row(pair) for pair in pairs]
    if args.dedupe:
        deduped: dict[str, DatasetRow] = {}
        for row in rows:
            deduped.setdefault(row.example_id, row)
        rows = list(deduped.values())

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(args.output_dir / "dataset.jsonl", rows)
    _write_labels_csv(args.output_dir / "labels.csv", rows)
    _write_summary(args.output_dir / "README.md", rows, len(pairs))
    print(f"Wrote {len(rows)} dataset row(s) to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
