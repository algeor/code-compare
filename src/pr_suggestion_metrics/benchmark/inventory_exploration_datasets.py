"""Inventory and normalize existing exploration datasets for Phase 5 benchmark work."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from pr_suggestion_metrics._paths import REPOSITORY_ROOT
from pr_suggestion_metrics.artifact_io import read_jsonl_objects, staged_output_directory, write_jsonl_objects
from pr_suggestion_metrics.diff.parser import DiffDialect, assess_unified_diff
from pr_suggestion_metrics.scientific_contracts import BenchmarkCandidate, SuggestionProvenance


InventoryStatus = Literal["benchmark_ready", "needs_reconstruction", "quarantined"]
SourceName = Literal[
    "internal_raw_pairs",
    "internal_processed_dataset",
    "external_github_codereview",
]

_DEFAULT_INTERNAL_RAW_PAIRS = REPOSITORY_ROOT / "data" / "raw" / "raw_pairs.jsonl"
_DEFAULT_INTERNAL_DATASET = REPOSITORY_ROOT / "data" / "processed" / "pr_suggestion_coverage" / "dataset" / "dataset.jsonl"
_DEFAULT_EXTERNAL_DATASET = REPOSITORY_ROOT / "data" / "external" / "github_codereview" / "dataset" / "dataset.jsonl"
_PR_URL_RE = re.compile(r"/pull/(?P<number>\d+)(?:/)?$")
_SOURCE_PRIORITY: dict[SourceName, int] = {
    "internal_raw_pairs": 3,
    "internal_processed_dataset": 2,
    "external_github_codereview": 1,
}
_REQUIREMENT_LABELS: dict[str, str] = {
    "repository_identity": "repository identity",
    "pr_identity": "PR URL or PR identifier",
    "suggestion_anchor": "stable inline suggestion anchor",
    "suggested_diff": "suggested diff",
    "original_file_path": "original file path",
    "original_snapshot_or_context": "original file snapshot or enough pre-suggestion context",
    "merged_pr_diff": "merged PR diff",
    "final_snapshot_or_context": "final file snapshot or enough final evidence",
    "merge_revision": "merge commit or comparable final revision",
    "final_path_mapping": "final path mapping when a rename is involved",
    "suggestion_provenance": "validated suggestion provenance",
}


class EvidenceAvailability(BaseModel):
    """Availability of the Phase 5 evidence requirements for one normalized row."""

    repository_identity: bool
    pr_identity: bool
    suggestion_anchor: bool
    suggested_diff: bool
    original_file_path: bool
    original_snapshot_or_context: bool
    merged_pr_diff: bool
    final_snapshot_or_context: bool
    merge_revision: bool
    final_path_mapping: bool
    suggestion_provenance: bool


class ExplorationCandidateRecord(BaseModel):
    """Normalized candidate-pool row derived from one or more exploration sources."""

    schema_version: Literal["1.0"] = "1.0"
    example_id: str
    chosen_source: SourceName
    source_datasets: list[SourceName] = Field(default_factory=list)
    source_row_keys: list[str] = Field(default_factory=list)
    repo: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    suggestion_anchor: str | None = None
    suggested_diff: str | None = None
    landed_diff: str | None = None
    original_file_path: str | None = None
    merge_commit_sha: str | None = None
    weak_label_percentage: int | None = None
    status: InventoryStatus
    evidence: EvidenceAvailability
    missing_requirements: list[str] = Field(default_factory=list)
    quarantine_reasons: list[str] = Field(default_factory=list)
    suggestion_provenance: dict[str, Any] | None = None


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--internal-raw-pairs", type=Path, default=_DEFAULT_INTERNAL_RAW_PAIRS)
    parser.add_argument("--internal-dataset", type=Path, default=_DEFAULT_INTERNAL_DATASET)
    parser.add_argument("--external-dataset", type=Path, default=_DEFAULT_EXTERNAL_DATASET)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def _parse_pr_number(pr_url: str | None) -> int | None:
    if not pr_url:
        return None
    match = _PR_URL_RE.search(pr_url)
    return int(match.group("number")) if match else None


def _internal_example_id(pr_url: str, handler_diff_path: str, handler_code_changes_diff: str) -> str:
    raw = f"{pr_url}|{handler_diff_path}|{handler_code_changes_diff}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _int_value(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _path_from_suggested_diff(diff_text: str | None) -> str | None:
    if not diff_text:
        return None
    try:
        parsed = assess_unified_diff(diff_text, dialect="suggestion_fragment").parsed_diff
    except ValueError:
        return None
    for file_diff in parsed.files:
        if file_diff.canonical_path:
            return file_diff.canonical_path
    return None


def _diff_has_context(diff_text: str | None, *, dialect: DiffDialect) -> bool:
    if not diff_text:
        return False
    try:
        parsed = assess_unified_diff(diff_text, dialect=dialect).parsed_diff
    except ValueError:
        return False
    return any(line.operation == "context" for line in parsed.lines)


def _diff_hints_rename(diff_text: str | None) -> bool:
    if not diff_text:
        return False
    try:
        parsed = assess_unified_diff(diff_text, dialect="git_unified").parsed_diff
    except ValueError:
        return False
    return any(file_diff.rename_from or file_diff.rename_to for file_diff in parsed.files)


def _validated_provenance(row: dict[str, Any]) -> tuple[SuggestionProvenance | None, list[str]]:
    payload = row.get("suggestion_provenance")
    if payload is None:
        return None, []
    if not isinstance(payload, dict):
        return None, ["suggestion_provenance payload is not a JSON object"]
    try:
        provenance = SuggestionProvenance.model_validate(payload)
    except ValueError as exc:
        return None, [f"invalid suggestion_provenance: {exc}"]
    issues = provenance.validation_issues()
    return (provenance if not issues else None), ([f"invalid suggestion_provenance: {issue}" for issue in issues] if issues else [])


def _final_path_mapping_available(row: dict[str, Any], provenance: SuggestionProvenance | None) -> bool:
    if provenance is not None and provenance.files:
        return True
    renamed_hint = bool(row.get("renamed_files")) or _diff_hints_rename(_string(row.get("landed_diff")))
    return not renamed_hint


def _missing_requirements(evidence: EvidenceAvailability) -> list[str]:
    missing: list[str] = []
    for key, label in _REQUIREMENT_LABELS.items():
        if not getattr(evidence, key):
            missing.append(label)
    return missing


def _status_for_row(evidence: EvidenceAvailability) -> InventoryStatus:
    if not _missing_requirements(evidence):
        return "benchmark_ready"
    reconstructable_requirements = (
        evidence.repository_identity,
        evidence.pr_identity,
        evidence.suggestion_anchor,
        evidence.suggested_diff,
        evidence.original_file_path,
        evidence.merged_pr_diff,
        evidence.merge_revision,
    )
    if all(reconstructable_requirements):
        return "needs_reconstruction"
    return "quarantined"


def _build_record(
    *,
    source: SourceName,
    source_row_key: str,
    example_id: str,
    repo: str | None,
    pr_url: str | None,
    pr_number: int | None,
    suggestion_anchor: str | None,
    suggested_diff: str | None,
    landed_diff: str | None,
    original_file_path: str | None,
    merge_commit_sha: str | None,
    weak_label_percentage: int | None,
    provenance: SuggestionProvenance | None,
    provenance_errors: list[str],
    final_path_mapping_available: bool,
    original_context_available: bool,
) -> ExplorationCandidateRecord:
    evidence = EvidenceAvailability(
        repository_identity=bool(repo),
        pr_identity=bool(pr_url) or pr_number is not None,
        suggestion_anchor=bool(suggestion_anchor),
        suggested_diff=bool(suggested_diff),
        original_file_path=bool(original_file_path),
        original_snapshot_or_context=(
            (provenance is not None and provenance.suggestion_base_snapshot is not None) or original_context_available
        ),
        merged_pr_diff=bool(landed_diff),
        final_snapshot_or_context=(provenance is not None and provenance.final_state_snapshot is not None),
        merge_revision=bool((provenance.merge_commit_sha if provenance is not None else None) or merge_commit_sha),
        final_path_mapping=final_path_mapping_available,
        suggestion_provenance=provenance is not None,
    )
    missing_requirements = _missing_requirements(evidence)
    status = _status_for_row(evidence)
    quarantine_reasons = provenance_errors.copy()
    if status == "quarantined":
        quarantine_reasons.extend(missing_requirements)
    return ExplorationCandidateRecord(
        example_id=example_id,
        chosen_source=source,
        source_datasets=[source],
        source_row_keys=[source_row_key],
        repo=repo,
        pr_url=pr_url,
        pr_number=pr_number,
        suggestion_anchor=suggestion_anchor,
        suggested_diff=suggested_diff,
        landed_diff=landed_diff,
        original_file_path=original_file_path,
        merge_commit_sha=(provenance.merge_commit_sha if provenance is not None else None) or merge_commit_sha,
        weak_label_percentage=weak_label_percentage,
        status=status,
        evidence=evidence,
        missing_requirements=missing_requirements,
        quarantine_reasons=list(dict.fromkeys(quarantine_reasons)),
        suggestion_provenance=provenance.model_dump(mode="json") if provenance is not None else None,
    )


def _normalize_internal_raw_pairs(row: dict[str, Any]) -> ExplorationCandidateRecord:
    pr_url = _string(row.get("pr_url"))
    handler_diff_path = _string(row.get("handler_diff_path"))
    suggested_diff = _string(row.get("handler_code_changes_diff"))
    landed_diff = _string(row.get("merged_pr_diff"))
    repo_parts = (_string(row.get("repo_host")), _string(row.get("repo_owner")), _string(row.get("repo_name")))
    repo = "/".join(part for part in repo_parts if part) if all(repo_parts) else None
    source_row_key = ":".join(
        part
        for part in (_string(row.get("inspection_id")), _string(row.get("fault_id")), handler_diff_path)
        if part
    )
    provenance, provenance_errors = _validated_provenance(row)
    original_file_path = _path_from_suggested_diff(suggested_diff)
    return _build_record(
        source="internal_raw_pairs",
        source_row_key=source_row_key,
        example_id=_internal_example_id(pr_url or "", handler_diff_path or "", suggested_diff or ""),
        repo=repo,
        pr_url=pr_url,
        pr_number=_int_value(row.get("pr_number")) or _parse_pr_number(pr_url),
        suggestion_anchor=handler_diff_path,
        suggested_diff=suggested_diff,
        landed_diff=landed_diff,
        original_file_path=original_file_path,
        merge_commit_sha=_string(row.get("merge_commit_sha")),
        weak_label_percentage=_int_value(row.get("expected_landed_percentage")),
        provenance=provenance,
        provenance_errors=provenance_errors,
        final_path_mapping_available=_final_path_mapping_available(
            {"landed_diff": landed_diff, "renamed_files": row.get("renamed_files")},
            provenance,
        ),
        original_context_available=_diff_has_context(suggested_diff, dialect="suggestion_fragment"),
    )


def _normalize_internal_dataset(row: dict[str, Any]) -> ExplorationCandidateRecord:
    pr_url = _string(row.get("pr_url"))
    suggested_diff = _string(row.get("suggested_diff"))
    landed_diff = _string(row.get("landed_diff"))
    provenance, provenance_errors = _validated_provenance(row)
    original_file_path = _path_from_suggested_diff(suggested_diff)
    metadata_value = row.get("metadata")
    metadata = metadata_value if isinstance(metadata_value, dict) else {}
    return _build_record(
        source="internal_processed_dataset",
        source_row_key=_string(row.get("example_id")) or "unknown",
        example_id=_string(row.get("example_id")) or _internal_example_id(pr_url or "", _string(row.get("suggestion_source")) or "", suggested_diff or ""),
        repo=_string(row.get("repo")),
        pr_url=pr_url,
        pr_number=_int_value(row.get("pr_number")) or _parse_pr_number(pr_url),
        suggestion_anchor=_string(row.get("suggestion_source")),
        suggested_diff=suggested_diff,
        landed_diff=landed_diff,
        original_file_path=original_file_path,
        merge_commit_sha=_string(row.get("merge_commit_sha")),
        weak_label_percentage=_int_value(row.get("expected_landed_percentage")),
        provenance=provenance,
        provenance_errors=provenance_errors,
        final_path_mapping_available=_final_path_mapping_available(
            {"landed_diff": landed_diff, "renamed_files": metadata.get("renamed_files")},
            provenance,
        ),
        original_context_available=_diff_has_context(suggested_diff, dialect="suggestion_fragment"),
    )


def _normalize_external_dataset(row: dict[str, Any]) -> ExplorationCandidateRecord:
    pr_url = _string(row.get("pr_url"))
    suggested_diff = _string(row.get("suggested_diff"))
    landed_diff = _string(row.get("landed_diff"))
    metadata_value = row.get("metadata")
    metadata = metadata_value if isinstance(metadata_value, dict) else {}
    original_file_path = _string(row.get("file_path")) or _string(metadata.get("file_path")) or _path_from_suggested_diff(suggested_diff)
    return _build_record(
        source="external_github_codereview",
        source_row_key=_string(row.get("example_id")) or "unknown",
        example_id=_string(row.get("example_id")) or hashlib.sha256(json.dumps(row, sort_keys=True).encode("utf-8")).hexdigest()[:16],
        repo=_string(row.get("repo")),
        pr_url=pr_url,
        pr_number=_parse_pr_number(pr_url),
        suggestion_anchor=None,
        suggested_diff=suggested_diff,
        landed_diff=landed_diff,
        original_file_path=original_file_path,
        merge_commit_sha=None,
        weak_label_percentage=_int_value(row.get("expected_landed_percentage")),
        provenance=None,
        provenance_errors=[],
        final_path_mapping_available=not _diff_hints_rename(landed_diff),
        original_context_available=_diff_has_context(suggested_diff, dialect="suggestion_fragment"),
    )


def _normalized_records_by_source(
    *,
    internal_raw_pairs_path: Path,
    internal_dataset_path: Path,
    external_dataset_path: Path,
) -> tuple[dict[SourceName, list[ExplorationCandidateRecord]], dict[SourceName, list[str]]]:
    rows_by_source: dict[SourceName, list[ExplorationCandidateRecord]] = {
        "internal_raw_pairs": [],
        "internal_processed_dataset": [],
        "external_github_codereview": [],
    }
    field_names_by_source: dict[SourceName, set[str]] = {
        "internal_raw_pairs": set(),
        "internal_processed_dataset": set(),
        "external_github_codereview": set(),
    }
    source_specs: tuple[tuple[SourceName, Path, Any], ...] = (
        ("internal_raw_pairs", internal_raw_pairs_path, _normalize_internal_raw_pairs),
        ("internal_processed_dataset", internal_dataset_path, _normalize_internal_dataset),
        ("external_github_codereview", external_dataset_path, _normalize_external_dataset),
    )
    for source_name, path, normalizer in source_specs:
        for row in read_jsonl_objects(path):
            field_names_by_source[source_name].update(row.keys())
            rows_by_source[source_name].append(normalizer(row))
    sorted_field_names = {source: sorted(names) for source, names in field_names_by_source.items()}
    return rows_by_source, sorted_field_names


def _merge_record(existing: ExplorationCandidateRecord, candidate: ExplorationCandidateRecord) -> ExplorationCandidateRecord:
    preferred = candidate if _SOURCE_PRIORITY[candidate.chosen_source] > _SOURCE_PRIORITY[existing.chosen_source] else existing
    merged = preferred.model_copy(deep=True)
    merged.source_datasets = sorted(set(existing.source_datasets + candidate.source_datasets))
    merged.source_row_keys = sorted(set(existing.source_row_keys + candidate.source_row_keys))
    if merged.weak_label_percentage is None:
        merged.weak_label_percentage = existing.weak_label_percentage or candidate.weak_label_percentage
    if merged.suggestion_provenance is None:
        merged.suggestion_provenance = existing.suggestion_provenance or candidate.suggestion_provenance
    return merged


def _dedupe_records(rows_by_source: dict[SourceName, list[ExplorationCandidateRecord]]) -> list[ExplorationCandidateRecord]:
    deduped: dict[str, ExplorationCandidateRecord] = {}
    for source_rows in rows_by_source.values():
        for row in source_rows:
            current = deduped.get(row.example_id)
            deduped[row.example_id] = row if current is None else _merge_record(current, row)
    return sorted(deduped.values(), key=lambda row: row.example_id)


def _benchmark_ready_rows(rows: list[ExplorationCandidateRecord]) -> list[dict[str, Any]]:
    ready_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.status != "benchmark_ready" or row.suggestion_provenance is None:
            continue
        candidate = BenchmarkCandidate(
            example_id=row.example_id,
            repo=row.repo or "",
            pr_url=row.pr_url or "",
            pr_number=row.pr_number or 0,
            suggested_diff=row.suggested_diff or "",
            landed_diff=row.landed_diff or "",
            suggestion_provenance=SuggestionProvenance.model_validate(row.suggestion_provenance),
        )
        ready_rows.append(candidate.model_dump(mode="json"))
    return ready_rows


def inventory_exploration_datasets(
    *,
    internal_raw_pairs_path: Path,
    internal_dataset_path: Path,
    external_dataset_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Write a Phase 5 inventory for the checked-in exploration datasets."""
    rows_by_source, field_names_by_source = _normalized_records_by_source(
        internal_raw_pairs_path=internal_raw_pairs_path,
        internal_dataset_path=internal_dataset_path,
        external_dataset_path=external_dataset_path,
    )
    deduped_rows = _dedupe_records(rows_by_source)
    benchmark_ready = [row.model_dump(mode="json") for row in deduped_rows if row.status == "benchmark_ready"]
    reconstructable = [row.model_dump(mode="json") for row in deduped_rows if row.status == "needs_reconstruction"]
    quarantined = [row.model_dump(mode="json") for row in deduped_rows if row.status == "quarantined"]
    benchmark_candidate_rows = _benchmark_ready_rows(deduped_rows)

    source_rows: tuple[tuple[SourceName, list[ExplorationCandidateRecord], Path], ...] = (
        ("internal_raw_pairs", rows_by_source["internal_raw_pairs"], internal_raw_pairs_path),
        ("internal_processed_dataset", rows_by_source["internal_processed_dataset"], internal_dataset_path),
        ("external_github_codereview", rows_by_source["external_github_codereview"], external_dataset_path),
    )
    source_counts = {
        source: {
            "field_names": field_names_by_source[source],
            "path": str(path),
            "rows": len(rows),
            "status_counts": dict(Counter(row.status for row in rows)),
        }
        for source, rows, path in source_rows
    }
    summary = {
        "schema_version": "1.0",
        "sources": source_counts,
        "deduped_examples": len(deduped_rows),
        "status_counts": dict(Counter(row.status for row in deduped_rows)),
        "benchmark_ready_examples": len(benchmark_ready),
        "reconstructable_examples": len(reconstructable),
        "quarantined_examples": len(quarantined),
        "benchmark_candidate_examples": len(benchmark_candidate_rows),
        "phase5_readiness": {
            "existing_local_benchmark_ready_rows": len(benchmark_ready),
            "existing_local_reconstructable_rows": len(reconstructable),
            "existing_local_quarantined_rows": len(quarantined),
        },
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with staged_output_directory(output_dir) as staging_dir:
        write_jsonl_objects(staging_dir / "candidate_pool.jsonl", [row.model_dump(mode="json") for row in deduped_rows], sort_keys=True)
        write_jsonl_objects(staging_dir / "benchmark_ready.jsonl", benchmark_ready, sort_keys=True)
        write_jsonl_objects(staging_dir / "benchmark_candidates.jsonl", benchmark_candidate_rows, sort_keys=True)
        write_jsonl_objects(staging_dir / "reconstructable.jsonl", reconstructable, sort_keys=True)
        write_jsonl_objects(staging_dir / "quarantined.jsonl", quarantined, sort_keys=True)
        (staging_dir / "inventory_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    """Inventory and normalize the checked-in exploration datasets."""
    args = parse_args()
    summary = inventory_exploration_datasets(
        internal_raw_pairs_path=args.internal_raw_pairs,
        internal_dataset_path=args.internal_dataset,
        external_dataset_path=args.external_dataset,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
