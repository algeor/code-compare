"""Prepare, apply, and validate semantic percentage labels.

This module intentionally does not invent labels with heuristics. It prepares
examples for an LLM/human semantic labeling pass, then applies the returned
`expected_landed_percentage` as the only source-of-truth label.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LABEL_COLUMNS = [
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
]

BUCKETS = ["0", "1-10", "11-20", "21-30", "31-40", "41-50", "51-60", "61-70", "71-80", "81-90", "91-100"]
LABELS = {"0%", "partial", "mostly", "100%"}
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PROMPT_PATH = _REPOSITORY_ROOT / "docs" / "prompts" / "llm_semantic_percentage_labeling_prompt.md"


@dataclass(frozen=True)
class DatasetPaths:
    dataset_dir: Path

    @property
    def dataset_jsonl(self) -> Path:
        return self.dataset_dir / "dataset.jsonl"

    @property
    def labels_csv(self) -> Path:
        return self.dataset_dir / "labels.csv"

    @property
    def llm_labels_jsonl(self) -> Path:
        return self.dataset_dir / "llm_labels.jsonl"


def percentage_bucket(value: int) -> str:
    if value < 0 or value > 100:
        raise ValueError(f"percentage out of range: {value}")
    if value == 0:
        return "0"
    if value <= 10:
        return "1-10"
    lower = ((value - 1) // 10) * 10 + 1
    upper = min(lower + 9, 100)
    return f"{lower}-{upper}"


def coarse_label(value: int) -> str:
    if value == 0:
        return "0%"
    if value < 60:
        return "partial"
    if value < 90:
        return "mostly"
    return "100%"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON in {path} line {line_number}: {error}") from error
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_labels_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=LABEL_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in LABEL_COLUMNS})


def files_from_stats(row: dict[str, Any], key: str) -> str:
    stats = row.get(key) or {}
    if isinstance(stats, dict):
        files = stats.get("files") or stats.get("paths") or []
        if isinstance(files, list):
            return ";".join(str(file) for file in files)
    return ""


def trim_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n...[TRUNCATED_FOR_LABELING_BATCH]...\n" + text[-half:]


def prepare(args: argparse.Namespace) -> None:
    paths = DatasetPaths(args.dataset_dir)
    examples = load_jsonl(paths.dataset_jsonl)
    existing_labels = {row["example_id"]: row for row in load_csv(paths.labels_csv)} if paths.labels_csv.exists() else {}

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = Path(args.prompt_path)
    prompt_text = prompt_path.read_text()

    batch_index = 1
    batch_rows: list[dict[str, Any]] = []
    written = 0

    for example in examples:
        example_id = str(example["example_id"])
        previous = existing_labels.get(example_id, {})
        task = {
            "custom_id": example_id,
            "messages": [
                {"role": "system", "content": prompt_text},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "example_id": example_id,
                            "pr_url": example.get("pr_url", ""),
                            "repo": example.get("repo", ""),
                            "suggestion_source": example.get("suggestion_source", ""),
                            "suggested_diff": trim_text(str(example.get("suggested_diff", "")), args.max_diff_chars),
                            "landed_diff": trim_text(str(example.get("landed_diff", "")), args.max_diff_chars),
                            "weak_existing_label": previous.get("label", example.get("label", "")),
                            "weak_existing_percentage": previous.get(
                                "expected_landed_percentage", example.get("expected_landed_percentage", "")
                            ),
                            "deterministic_landed_estimate": example.get("deterministic_landed_estimate", ""),
                            "file_overlap_ratio": example.get("file_overlap_ratio", ""),
                            "changed_line_overlap_ratio": example.get("changed_line_overlap_ratio", ""),
                            "suggested_files": previous.get("suggested_files") or files_from_stats(example, "suggested_stats"),
                            "landed_files": previous.get("landed_files") or files_from_stats(example, "landed_stats"),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        batch_rows.append(task)

        if len(batch_rows) >= args.batch_size:
            write_jsonl(output_dir / f"semantic_labeling_batch_{batch_index:04d}.jsonl", batch_rows)
            written += len(batch_rows)
            batch_index += 1
            batch_rows = []

    if batch_rows:
        write_jsonl(output_dir / f"semantic_labeling_batch_{batch_index:04d}.jsonl", batch_rows)
        written += len(batch_rows)

    print(f"prepared examples: {written}")
    print(f"batch files: {batch_index}")
    print(f"output_dir: {output_dir}")


def read_llm_output(path: Path) -> dict[str, dict[str, Any]]:
    rows = load_jsonl(path)
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = row
        if "response" in row and isinstance(row["response"], dict):
            payload = row["response"]
        if "content" in payload and isinstance(payload["content"], str):
            payload = json.loads(payload["content"])
        example_id = str(payload["example_id"])
        result[example_id] = payload
    return result


def normalized_label_row(example: dict[str, Any], old_label: dict[str, Any], semantic: dict[str, Any]) -> dict[str, Any]:
    percentage = int(semantic["expected_landed_percentage"])
    if percentage < 0 or percentage > 100:
        raise ValueError(f"{example['example_id']}: percentage out of range: {percentage}")
    return {
        "example_id": example["example_id"],
        "label": coarse_label(percentage),
        "expected_landed_percentage": percentage,
        "expected_percentage_bucket": percentage_bucket(percentage),
        "label_notes": semantic.get("reasoning", old_label.get("label_notes", "")),
        "suggested_label": old_label.get("suggested_label", old_label.get("label", "")),
        "suggested_percentage": old_label.get(
            "suggested_percentage", old_label.get("expected_landed_percentage", example.get("deterministic_landed_estimate", ""))
        ),
        "suggested_rationale": old_label.get("suggested_rationale", ""),
        "pr_url": example.get("pr_url", old_label.get("pr_url", "")),
        "repo": example.get("repo", old_label.get("repo", "")),
        "suggestion_source": example.get("suggestion_source", old_label.get("suggestion_source", "")),
        "deterministic_landed_estimate": example.get(
            "deterministic_landed_estimate", old_label.get("deterministic_landed_estimate", "")
        ),
        "file_overlap_ratio": example.get("file_overlap_ratio", old_label.get("file_overlap_ratio", "")),
        "changed_line_overlap_ratio": example.get(
            "changed_line_overlap_ratio", old_label.get("changed_line_overlap_ratio", "")
        ),
        "suggested_files": old_label.get("suggested_files") or files_from_stats(example, "suggested_stats"),
        "landed_files": old_label.get("landed_files") or files_from_stats(example, "landed_stats"),
    }


def apply_labels(args: argparse.Namespace) -> None:
    paths = DatasetPaths(args.dataset_dir)
    examples = load_jsonl(paths.dataset_jsonl)
    old_labels = {row["example_id"]: row for row in load_csv(paths.labels_csv)} if paths.labels_csv.exists() else {}
    semantic_labels = read_llm_output(args.llm_output)

    missing = [row["example_id"] for row in examples if row["example_id"] not in semantic_labels]
    if missing:
        preview = ", ".join(missing[:10])
        raise ValueError(f"semantic labels missing {len(missing)} examples: {preview}")

    label_rows: list[dict[str, Any]] = []
    llm_rows: list[dict[str, Any]] = []
    updated_examples: list[dict[str, Any]] = []

    for example in examples:
        example_id = str(example["example_id"])
        semantic = semantic_labels[example_id]
        label_row = normalized_label_row(example, old_labels.get(example_id, {}), semantic)
        label_rows.append(label_row)

        llm_row = dict(semantic)
        llm_row["example_id"] = example_id
        llm_row["label"] = label_row["label"]
        llm_row["expected_landed_percentage"] = label_row["expected_landed_percentage"]
        llm_row["expected_percentage_bucket"] = label_row["expected_percentage_bucket"]
        llm_rows.append(llm_row)

        updated = dict(example)
        updated["label"] = label_row["label"]
        updated["expected_landed_percentage"] = label_row["expected_landed_percentage"]
        updated["expected_percentage_bucket"] = label_row["expected_percentage_bucket"]
        updated_examples.append(updated)

    write_labels_csv(paths.labels_csv, label_rows)
    write_jsonl(paths.llm_labels_jsonl, llm_rows)
    write_jsonl(paths.dataset_jsonl, updated_examples)
    validate_dataset(paths)


def validate_dataset(paths: DatasetPaths) -> None:
    examples = load_jsonl(paths.dataset_jsonl)
    labels = load_csv(paths.labels_csv)
    llm_labels = load_jsonl(paths.llm_labels_jsonl) if paths.llm_labels_jsonl.exists() else []

    example_ids = [str(row["example_id"]) for row in examples]
    label_ids = [str(row["example_id"]) for row in labels]
    llm_ids = [str(row["example_id"]) for row in llm_labels]

    errors: list[str] = []
    if len(example_ids) != len(set(example_ids)):
        errors.append("duplicate example_id in dataset.jsonl")
    if len(label_ids) != len(set(label_ids)):
        errors.append("duplicate example_id in labels.csv")
    if set(example_ids) != set(label_ids):
        errors.append("dataset.jsonl and labels.csv example_id sets differ")
    if llm_ids and set(example_ids) != set(llm_ids):
        errors.append("dataset.jsonl and llm_labels.jsonl example_id sets differ")

    by_example = {str(row["example_id"]): row for row in examples}
    by_llm = {str(row["example_id"]): row for row in llm_labels}
    label_counter: Counter[str] = Counter()
    bucket_counter: Counter[str] = Counter()

    for row in labels:
        example_id = str(row["example_id"])
        percentage = int(row["expected_landed_percentage"])
        expected_label = coarse_label(percentage)
        expected_bucket = percentage_bucket(percentage)
        label_counter[expected_label] += 1
        bucket_counter[expected_bucket] += 1
        if row["label"] not in LABELS:
            errors.append(f"{example_id}: invalid label {row['label']!r}")
        if row["label"] != expected_label:
            errors.append(f"{example_id}: label does not match percentage")
        if row["expected_percentage_bucket"] != expected_bucket:
            errors.append(f"{example_id}: bucket does not match percentage")
        if by_example.get(example_id, {}).get("expected_landed_percentage") != percentage:
            errors.append(f"{example_id}: dataset percentage does not match labels.csv")
        if by_llm and int(by_llm[example_id]["expected_landed_percentage"]) != percentage:
            errors.append(f"{example_id}: llm percentage does not match labels.csv")

    if errors:
        preview = "\n".join(errors[:20])
        raise ValueError(f"validation failed with {len(errors)} error(s):\n{preview}")

    print(f"validated examples: {len(examples)}")
    print("labels:", dict(label_counter))
    print("buckets:", {bucket: bucket_counter[bucket] for bucket in BUCKETS})


def validate(args: argparse.Namespace) -> None:
    validate_dataset(DatasetPaths(args.dataset_dir))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--dataset-dir", type=Path, required=True)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument(
        "--prompt-path",
        type=Path,
        default=_DEFAULT_PROMPT_PATH,
    )
    prepare_parser.add_argument("--batch-size", type=int, default=25)
    prepare_parser.add_argument("--max-diff-chars", type=int, default=24000)
    prepare_parser.set_defaults(func=prepare)

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--dataset-dir", type=Path, required=True)
    apply_parser.add_argument("--llm-output", type=Path, required=True)
    apply_parser.set_defaults(func=apply_labels)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--dataset-dir", type=Path, required=True)
    validate_parser.set_defaults(func=validate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
