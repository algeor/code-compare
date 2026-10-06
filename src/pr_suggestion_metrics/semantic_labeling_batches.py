"""Prepare, apply, and validate semantic percentage labels.

This module intentionally does not invent labels with heuristics. It prepares
examples for an LLM/human semantic labeling pass, then applies the returned
`expected_landed_percentage` as the only source-of-truth label.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pr_suggestion_metrics._paths import REPOSITORY_ROOT as _REPOSITORY_ROOT
from pr_suggestion_metrics.artifact_io import read_jsonl_objects, write_jsonl_objects
from pr_suggestion_metrics.percentages import OBSOLETE_DERIVED_LABEL_FIELDS, parse_integer_percentage


LABEL_COLUMNS = [
    "example_id",
    "expected_landed_percentage",
    "label_notes",
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

_DEFAULT_PROMPT_PATH = _REPOSITORY_ROOT / "research" / "prompts" / "llm_semantic_percentage_labeling_prompt.md"


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
    examples = read_jsonl_objects(paths.dataset_jsonl)
    existing_labels = {row["example_id"]: row for row in load_csv(paths.labels_csv)} if paths.labels_csv.exists() else {}

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = Path(args.prompt_path)
    prompt_text = prompt_path.read_text()

    batch_index = 1
    batch_rows: list[dict[str, Any]] = []
    written = 0
    written_batches = 0

    if args.batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")
    if args.max_diff_chars <= 0:
        raise ValueError("max_diff_chars must be greater than zero")

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
            write_jsonl_objects(
                output_dir / f"semantic_labeling_batch_{batch_index:04d}.jsonl",
                batch_rows,
                ensure_ascii=False,
                sort_keys=True,
            )
            written += len(batch_rows)
            written_batches += 1
            batch_index += 1
            batch_rows = []

    if batch_rows:
        write_jsonl_objects(
            output_dir / f"semantic_labeling_batch_{batch_index:04d}.jsonl",
            batch_rows,
            ensure_ascii=False,
            sort_keys=True,
        )
        written += len(batch_rows)
        written_batches += 1

    print(f"prepared examples: {written}")
    print(f"batch files: {written_batches}")
    print(f"output_dir: {output_dir}")


def read_llm_output(path: Path) -> dict[str, dict[str, Any]]:
    rows = read_jsonl_objects(path)
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = row
        if "response" in row and isinstance(row["response"], dict):
            payload = row["response"]
        if "content" in payload and isinstance(payload["content"], str):
            payload = json.loads(payload["content"])
        example_id = str(payload["example_id"])
        if example_id in result:
            raise ValueError(f"duplicate semantic label for example_id {example_id!r}")
        result[example_id] = payload
    return result


def normalized_label_row(example: dict[str, Any], old_label: dict[str, Any], semantic: dict[str, Any]) -> dict[str, Any]:
    percentage = parse_integer_percentage(
        semantic["expected_landed_percentage"],
        name=f"{example['example_id']}: percentage",
    )
    return {
        "example_id": example["example_id"],
        "expected_landed_percentage": percentage,
        "label_notes": semantic.get("reasoning", old_label.get("label_notes", "")),
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
    examples = read_jsonl_objects(paths.dataset_jsonl)
    old_labels = {row["example_id"]: row for row in load_csv(paths.labels_csv)} if paths.labels_csv.exists() else {}
    semantic_labels = read_llm_output(args.llm_output)

    example_ids = [str(row["example_id"]) for row in examples]
    if len(example_ids) != len(set(example_ids)):
        raise ValueError("duplicate example_id in dataset.jsonl")
    missing = [example_id for example_id in example_ids if example_id not in semantic_labels]
    if missing:
        preview = ", ".join(missing[:10])
        raise ValueError(f"semantic labels missing {len(missing)} examples: {preview}")
    unexpected = sorted(set(semantic_labels) - set(example_ids))
    if unexpected:
        preview = ", ".join(unexpected[:10])
        raise ValueError(f"semantic labels contain {len(unexpected)} unknown examples: {preview}")

    label_rows: list[dict[str, Any]] = []
    llm_rows: list[dict[str, Any]] = []
    updated_examples: list[dict[str, Any]] = []

    for example in examples:
        example_id = str(example["example_id"])
        semantic = semantic_labels[example_id]
        label_row = normalized_label_row(example, old_labels.get(example_id, {}), semantic)
        label_rows.append(label_row)

        llm_row = {key: value for key, value in semantic.items() if key not in OBSOLETE_DERIVED_LABEL_FIELDS}
        llm_row["example_id"] = example_id
        llm_row["expected_landed_percentage"] = label_row["expected_landed_percentage"]
        llm_rows.append(llm_row)

        updated = dict(example)
        for field in OBSOLETE_DERIVED_LABEL_FIELDS:
            updated.pop(field, None)
        updated["expected_landed_percentage"] = label_row["expected_landed_percentage"]
        updated_examples.append(updated)

    write_labels_csv(paths.labels_csv, label_rows)
    write_jsonl_objects(paths.llm_labels_jsonl, llm_rows, ensure_ascii=False, sort_keys=True)
    write_jsonl_objects(paths.dataset_jsonl, updated_examples, ensure_ascii=False, sort_keys=True)
    validate_dataset(paths)


def validate_dataset(paths: DatasetPaths) -> None:
    examples = read_jsonl_objects(paths.dataset_jsonl)
    labels = load_csv(paths.labels_csv)
    llm_labels = read_jsonl_objects(paths.llm_labels_jsonl) if paths.llm_labels_jsonl.exists() else []

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

    for row in labels:
        example_id = str(row["example_id"])
        try:
            percentage = parse_integer_percentage(
                row["expected_landed_percentage"],
                name=f"{example_id}: labels.csv percentage",
            )
        except ValueError as error:
            errors.append(str(error))
            continue
        try:
            dataset_percentage = parse_integer_percentage(
                by_example.get(example_id, {}).get("expected_landed_percentage"),
                name=f"{example_id}: dataset percentage",
            )
        except ValueError as error:
            errors.append(str(error))
        else:
            if dataset_percentage != percentage:
                errors.append(f"{example_id}: dataset percentage does not match labels.csv")
        llm_row = by_llm.get(example_id)
        if llm_row is not None:
            try:
                llm_percentage = parse_integer_percentage(
                    llm_row.get("expected_landed_percentage"),
                    name=f"{example_id}: llm percentage",
                )
            except ValueError as error:
                errors.append(str(error))
            else:
                if llm_percentage != percentage:
                    errors.append(f"{example_id}: llm percentage does not match labels.csv")

    if errors:
        preview = "\n".join(errors[:20])
        raise ValueError(f"validation failed with {len(errors)} error(s):\n{preview}")

    print(f"validated examples: {len(examples)}")


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
