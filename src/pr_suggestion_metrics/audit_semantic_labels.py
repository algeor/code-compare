"""Audit semantic HF labels and assign confidence-aware training weights."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


MANUAL_OVERRIDES: dict[str, tuple[int, str]] = {
    "e8d9a574d827f4d3": (35, "Only the display-label capitalization changed; the surrounding option structure was pre-existing context."),
    "f4b13b9adb24873b": (35, "The LOCAL_STORAGE_KEYS container landed, but the requested CONVERSATION_SELECTED_TAB key was replaced by a different consolidated state key."),
    "caf4ed920acd6855": (95, "The reusable scrollToNext callback and both onCtaClick assignments landed; only the placeholder body was replaced by the concrete scrolling implementation."),
    "8abbc680b3adae7f": (95, "Pending, finished, and currently blocked durations all landed with equivalent reordered control flow; the unreachable error branch became the blocked fallback."),
    "fdfa3d8a0d5b16de": (95, "The cached CreateValueCallback and GetValue usage landed; initialization moved from lazy subscription setup into both constructors."),
    "4e14496d5c9dfd5f": (25, "Only the generic if/else shape is visible; the landed API renames and formatting do not establish the omitted suggested behavior."),
    "1f9e18baaaaf249a": (95, "The nil early return and type-assertion guard landed exactly in flattened control flow."),
    "407860575f31504a": (65, "The voice-path bounds guards landed, but the requested invalid-structure alert was omitted."),
    "33cea56ba8be5055": (45, "A renamed plural URL input and placeholder landed, while the requested maxCrawlPages field did not."),
    "3b49d360f39592b7": (0, "Only generic pytest markers overlap; the requested pendulum-links test did not land."),
    "389f75d5e99249e8": (88, "The visibility warning landed and was expanded to cover both scene and events editors."),
    "d56150cfb6715ec2": (95, "The try/catch success gating landed equivalently through catch-to-null followed by an explicit newKey guard."),
    "3e8fe05f8b5d83a7": (55, "Property lookup landed through findProperty, but the required fail-fast error for a missing property did not."),
    "5667db04ba8c46e6": (95, "The content-size-category guard and updateSize call landed with an equivalent positive if condition."),
    "e51ed1b7afc675c8": (95, "The property metadata map, attribute paths, types, and cycle flags landed; ellipses represented omitted supporting entries."),
    "8abdc533a573218e": (100, "The Combine listener chain landed exactly with only line wrapping and indentation changes."),
    "ccf28a898be800b2": (50, "The current_tag extraction landed, but the requested safe non_standard_tag initialization remained absent."),
    "1a66f505207cb24d": (100, "The complete Gradle configuration example landed verbatim inside the warning text."),
    "1c9430c52b59d9c4": (95, "The NamedTuple return-type assertion landed directly on the end expression instead of a separate opts binding."),
    "8f00eb4614b8b994": (95, "The LocalCPUBackend branch landed with an equivalent inverted condition that wraps every other backend."),
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows))


def percentage_bucket(value: int) -> str:
    if value == 0:
        return "0"
    lower = ((value - 1) // 10) * 10 + 1
    return f"{lower}-{min(lower + 9, 100)}"


def coarse_label(value: int) -> str:
    if value == 0:
        return "0%"
    if value < 60:
        return "partial"
    if value < 90:
        return "mostly"
    return "100%"


def apply_manual_override(row: dict[str, Any]) -> dict[str, Any]:
    override = MANUAL_OVERRIDES.get(row["example_id"])
    if override is None:
        return row
    percentage, reasoning = override
    updated = dict(row)
    updated["expected_landed_percentage"] = percentage
    updated["expected_percentage_bucket"] = percentage_bucket(percentage)
    updated["label"] = coarse_label(percentage)
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
    if row["confidence"] == "medium" and row["label"] in {"partial", "mostly"} and has_landed and has_changed:
        return "accepted_mixed_evidence", 0.85
    if row["confidence"] == "medium":
        return "accepted_medium_confidence", 0.50
    if "possible_moved_implementation" in flags:
        return "uncertain_cross_file", 0.08
    if all(unit["status"] == "landed_partially" for unit in row.get("semantic_units", [])):
        return "uncertain_fuzzy_only", 0.08
    return "uncertain_metric_disagreement", 0.12


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semantic-output-dir", type=Path, required=True)
    parser.add_argument("--metric-scores", type=Path, required=True)
    args = parser.parse_args()

    aggregate_path = args.semantic_output_dir / "all_labels.jsonl"
    rows = [apply_manual_override(row) for row in load_jsonl(aggregate_path)]
    score_rows = {row["example_id"]: row for row in csv.DictReader(args.metric_scores.open(newline=""))}
    audit_rows = []
    for row in rows:
        status, weight = audit_status(row)
        score = score_rows[row["example_id"]]
        audit_rows.append(
            {
                "example_id": row["example_id"],
                "audit_status": status,
                "training_weight": weight,
                "confidence": row["confidence"],
                "label": row["label"],
                "expected_landed_percentage": row["expected_landed_percentage"],
                "metric_percentage": int(float(score["predicted_percentage"])),
                "metric_disagreement": abs(row["expected_landed_percentage"] - int(float(score["predicted_percentage"]))),
                "manually_verified": row["example_id"] in MANUAL_OVERRIDES,
            }
        )

    write_jsonl(aggregate_path, rows)
    by_id = {row["example_id"]: row for row in rows}
    for batch_path in sorted(args.semantic_output_dir.glob("semantic_labeling_batch_*.jsonl")):
        batch_rows = load_jsonl(batch_path)
        write_jsonl(batch_path, [by_id[row["example_id"]] for row in batch_rows])

    write_jsonl(args.semantic_output_dir / "audit_report.jsonl", audit_rows)
    curated = [row for row in audit_rows if row["audit_status"] in {"manually_verified", "accepted_mixed_evidence"} and row["label"] in {"partial", "mostly"}]
    write_jsonl(args.semantic_output_dir / "curated_partial_mostly.jsonl", curated)
    summary = {
        "rows": len(rows),
        "manually_verified_rows": len(MANUAL_OVERRIDES),
        "curated_partial_mostly_rows": len(curated),
        "audit_statuses": dict(Counter(row["audit_status"] for row in audit_rows)),
        "confidence": dict(Counter(row["confidence"] for row in rows)),
        "labels": dict(Counter(row["label"] for row in rows)),
    }
    (args.semantic_output_dir / "audit_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
