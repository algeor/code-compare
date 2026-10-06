"""Audit semantic HF labels and assign confidence-aware training weights."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pr_suggestion_metrics._paths import REPOSITORY_ROOT
from pr_suggestion_metrics.artifact_io import read_jsonl_objects, write_jsonl_objects
from pr_suggestion_metrics.model_artifacts import sha256_file
from pr_suggestion_metrics.percentages import (
    OBSOLETE_DERIVED_LABEL_FIELDS,
    parse_integer_percentage,
    round_bounded_percentage,
)


DEFAULT_MANUAL_OVERRIDES_PATH = REPOSITORY_ROOT / "research" / "audit" / "manual_semantic_overrides.json"


def load_manual_overrides(path: Path) -> tuple[dict[str, tuple[int, str]], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise ValueError("Manual override policy must be a JSON object with schema_version='1.0'")
    rows = payload.get("overrides")
    if not isinstance(rows, list):
        raise ValueError("Manual override policy must contain an overrides list")
    overrides: dict[str, tuple[int, str]] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Manual override {index} must be a JSON object")
        example_id = row.get("example_id")
        rationale = row.get("rationale")
        reviewer = row.get("reviewer")
        guide_version = row.get("guide_version")
        if (
            not isinstance(example_id, str)
            or not example_id.strip()
            or not isinstance(rationale, str)
            or not rationale.strip()
            or not isinstance(reviewer, str)
            or not reviewer.strip()
            or not isinstance(guide_version, str)
            or not guide_version.strip()
        ):
            raise ValueError(f"Manual override {index} must include example_id, rationale, reviewer, and guide_version")
        if example_id in overrides:
            raise ValueError(f"Duplicate manual override for {example_id}")
        percentage = parse_integer_percentage(
            row.get("expected_landed_percentage"),
            name=f"Manual override percentage for {example_id}",
        )
        overrides[example_id] = (percentage, rationale)
    return overrides, str(payload["schema_version"])


def apply_manual_override(row: dict[str, Any], overrides: dict[str, tuple[int, str]] | None = None) -> dict[str, Any]:
    if overrides is None:
        overrides, _ = load_manual_overrides(DEFAULT_MANUAL_OVERRIDES_PATH)
    override = overrides.get(row["example_id"])
    updated = dict(row)
    for field in OBSOLETE_DERIVED_LABEL_FIELDS:
        updated.pop(field, None)
    if override is None:
        return updated
    percentage, reasoning = override
    updated["expected_landed_percentage"] = percentage
    updated["reasoning"] = reasoning
    updated["confidence"] = "high"
    updated["ambiguity_flags"] = list(dict.fromkeys([*updated.get("ambiguity_flags", []), "manually_verified"]))
    if percentage == 0:
        units = []
        for unit in updated.get("semantic_units", []):
            changed = dict(unit)
            changed["status"] = "absent"
            changed["evidence"] = reasoning
            units.append(changed)
        updated["semantic_units"] = units
        updated["matched_parts"] = []
        updated["missing_or_changed_parts"] = [unit["unit"] for unit in units]
    elif percentage == 100:
        units = []
        for unit in updated.get("semantic_units", []):
            changed = dict(unit)
            if changed["status"] in {"absent", "different_implementation", "landed_partially"}:
                changed["status"] = "landed_equivalently"
                changed["evidence"] = reasoning
            units.append(changed)
        updated["semantic_units"] = units
        updated["matched_parts"] = [unit["unit"] for unit in units]
        updated["missing_or_changed_parts"] = []
    return updated


def audit_status(row: dict[str, Any]) -> tuple[str, float]:
    flags = set(row.get("ambiguity_flags", []))
    statuses = {unit["status"] for unit in row.get("semantic_units", [])}
    if "manually_verified" in flags:
        return "manually_verified", 1.25
    if row["confidence"] == "high":
        return "accepted_high_confidence", 0.85
    has_landed = bool(statuses & {"landed_exactly", "landed_equivalently"})
    has_changed = bool(statuses & {"landed_partially", "absent", "different_implementation"})
    if row["confidence"] == "medium" and has_landed and has_changed:
        return "accepted_mixed_evidence", 0.85
    if row["confidence"] == "medium":
        return "accepted_medium_confidence", 0.50
    if "possible_moved_implementation" in flags:
        return "uncertain_cross_file", 0.08
    if statuses == {"landed_partially"}:
        return "uncertain_fuzzy_only", 0.08
    return "uncertain_metric_disagreement", 0.12


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semantic-output-dir", type=Path, required=True)
    parser.add_argument("--metric-scores", type=Path, required=True)
    parser.add_argument("--manual-overrides", type=Path, default=DEFAULT_MANUAL_OVERRIDES_PATH)
    args = parser.parse_args()

    aggregate_path = args.semantic_output_dir / "all_labels.jsonl"
    original_rows = read_jsonl_objects(aggregate_path)
    manual_overrides, override_schema_version = load_manual_overrides(args.manual_overrides)
    unknown_override_ids = sorted(set(manual_overrides) - {row["example_id"] for row in original_rows})
    if unknown_override_ids:
        raise ValueError(f"Manual overrides reference unknown examples: {unknown_override_ids}")
    rows = [apply_manual_override(row, manual_overrides) for row in original_rows]
    score_rows = {row["example_id"]: row for row in csv.DictReader(args.metric_scores.open(newline=""))}
    audit_rows = []
    for row in rows:
        status, weight = audit_status(row)
        score = score_rows[row["example_id"]]
        expected_percentage = parse_integer_percentage(
            row["expected_landed_percentage"],
            name=f"Expected percentage for {row['example_id']}",
        )
        metric_percentage = round_bounded_percentage(score["predicted_percentage"])
        audit_rows.append(
            {
                "example_id": row["example_id"],
                "audit_status": status,
                "training_weight": weight,
                "confidence": row["confidence"],
                "expected_landed_percentage": expected_percentage,
                "metric_percentage": metric_percentage,
                "metric_disagreement": abs(expected_percentage - metric_percentage),
                "manually_verified": row["example_id"] in manual_overrides,
            }
        )

    write_jsonl_objects(aggregate_path, rows, ensure_ascii=False, separators=(",", ":"))
    by_id = {row["example_id"]: row for row in rows}
    for batch_path in sorted(args.semantic_output_dir.glob("semantic_labeling_batch_*.jsonl")):
        batch_rows = read_jsonl_objects(batch_path)
        write_jsonl_objects(
            batch_path,
            [by_id[row["example_id"]] for row in batch_rows],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    write_jsonl_objects(
        args.semantic_output_dir / "audit_report.jsonl",
        audit_rows,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    curated = [row for row in audit_rows if row["audit_status"] in {"manually_verified", "accepted_mixed_evidence"}]
    write_jsonl_objects(
        args.semantic_output_dir / "curated_mixed_coverage.jsonl",
        curated,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    summary = {
        "rows": len(rows),
        "manually_verified_rows": sum(row["manually_verified"] for row in audit_rows),
        "curated_mixed_coverage_rows": len(curated),
        "audit_statuses": dict(Counter(row["audit_status"] for row in audit_rows)),
        "confidence": dict(Counter(row["confidence"] for row in rows)),
        "manual_override_policy": {
            "path": str(args.manual_overrides),
            "schema_version": override_schema_version,
            "sha256": sha256_file(args.manual_overrides),
        },
    }
    (args.semantic_output_dir / "audit_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
