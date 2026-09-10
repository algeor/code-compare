"""Create blinded, balanced double-human annotation packets."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pr_suggestion_metrics.freeze_benchmark import BenchmarkExample, _read_jsonl
from pr_suggestion_metrics.model_artifacts import sha256_file


_FORBIDDEN_KEYS = {
    "label",
    "expected_landed_percentage",
    "expected_percentage_bucket",
    "deterministic_landed_estimate",
    "file_overlap_ratio",
    "changed_line_overlap_ratio",
    "metric_scores",
    "model_prediction",
}


def _safe_packet_name(annotator_id: str) -> str:
    digest = hashlib.sha256(annotator_id.encode("utf-8")).hexdigest()[:12]
    return f"annotator-{digest}.jsonl"


def _blinded_packet(example: BenchmarkExample, *, guide_version: str) -> dict[str, Any]:
    provenance = example.suggestion_provenance.model_dump(mode="json")
    provenance.pop("author_login", None)
    return {
        "example_id": example.example_id,
        "guide_version": guide_version,
        "repo": example.repo,
        "pr_number": example.pr_number,
        "suggested_diff": example.suggested_diff,
        "suggestion_provenance": provenance,
        "annotation": {
            "decision": "",
            "abstention_reasons": [],
            "units": [],
            "confidence": "",
            "notes": "",
        },
    }


def prepare_annotation_packets(
    *,
    examples_path: Path,
    annotator_ids: list[str],
    output_dir: Path,
    guide_version: str,
    seed: int,
) -> dict[str, Any]:
    """Assign every verified example to two blinded annotators."""
    unique_annotators = list(dict.fromkeys(annotator_ids))
    if len(unique_annotators) < 2:
        raise ValueError("At least two distinct annotators are required")

    raw_examples = _read_jsonl(examples_path)
    for raw_example in raw_examples:
        forbidden = sorted(_FORBIDDEN_KEYS & raw_example.keys())
        if forbidden:
            raise ValueError(f"Annotation source contains forbidden label/model fields: {forbidden}")
    examples = [BenchmarkExample.model_validate(row) for row in raw_examples]
    if len({example.example_id for example in examples}) != len(examples):
        raise ValueError("Example IDs must be unique")
    for example in examples:
        issues = example.suggestion_provenance.validation_issues()
        if issues:
            raise ValueError(f"Example {example.example_id} has incomplete provenance: {issues}")

    shuffled = examples.copy()
    random.Random(seed).shuffle(shuffled)
    assignments: dict[str, list[BenchmarkExample]] = {annotator_id: [] for annotator_id in unique_annotators}
    assignment_manifest: list[dict[str, Any]] = []
    for index, example in enumerate(shuffled):
        first = unique_annotators[index % len(unique_annotators)]
        second = unique_annotators[(index + 1) % len(unique_annotators)]
        assignments[first].append(example)
        assignments[second].append(example)
        assignment_manifest.append(
            {
                "example_id": example.example_id,
                "annotator_ids": sorted((first, second)),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=False)
    packet_hashes: dict[str, str] = {}
    for annotator_id, assigned_examples in assignments.items():
        packet_path = output_dir / _safe_packet_name(annotator_id)
        rows = [_blinded_packet(example, guide_version=guide_version) for example in assigned_examples]
        packet_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        packet_hashes[annotator_id] = sha256_file(packet_path)

    manifest = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "guide_version": guide_version,
        "seed": seed,
        "examples_sha256": sha256_file(examples_path),
        "example_count": len(examples),
        "assignment_count": len(examples) * 2,
        "assignments_per_annotator": dict(Counter({key: len(value) for key, value in assignments.items()})),
        "packet_sha256_by_annotator": packet_hashes,
        "assignments": sorted(assignment_manifest, key=lambda row: row["example_id"]),
        "blinding": {
            "model_outputs_removed": True,
            "overlap_features_removed": True,
            "existing_labels_removed": True,
            "source_author_removed": True,
        },
    }
    (output_dir / "assignment_manifest.private.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    """Parse annotation-packet arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--annotator", action="append", required=True, dest="annotators")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--guide-version", default="1.0")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> int:
    """Create blinded annotation packets."""
    args = parse_args()
    manifest = prepare_annotation_packets(
        examples_path=args.examples,
        annotator_ids=args.annotators,
        output_dir=args.output_dir,
        guide_version=args.guide_version,
        seed=args.seed,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
