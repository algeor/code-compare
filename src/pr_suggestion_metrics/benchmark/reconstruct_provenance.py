"""Reconstruct provenance-complete benchmark candidates from inventory rows."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from pr_suggestion_metrics.artifact_io import read_jsonl_objects, staged_output_directory, write_jsonl_objects
from pr_suggestion_metrics.benchmark.inventory_exploration_datasets import ExplorationCandidateRecord
from pr_suggestion_metrics.collection.contracts import CandidateRow, DatasetSettings, RepoRef
from pr_suggestion_metrics.collection.extraction import extract_comment_diff_suggestions
from pr_suggestion_metrics.collection.github import GitHubHttpGateway
from pr_suggestion_metrics.collection.service import final_path_for_suggested_path, nested_string
from pr_suggestion_metrics.diff.parser import parse_unified_diff
from pr_suggestion_metrics.scientific_contracts import (
    BenchmarkCandidate,
    FileProvenance,
    FileSnapshot,
    SuggestionProvenance,
)


_REVIEW_ANCHOR_RE = re.compile(r"^github_review_comment:(?P<comment_id>[^#]+)#suggestion:(?P<index>\d+)$")
_SUPPORTED_INTERNAL_SOURCES = {"internal_raw_pairs", "internal_processed_dataset"}


class ProvenanceGateway(Protocol):
    """GitHub operations needed for provenance reconstruction."""

    async def fetch_pr_json(self, repo: RepoRef) -> dict[str, object]: ...

    async def fetch_pr_review_comments(self, repo: RepoRef) -> list[dict[str, object]]: ...

    async def fetch_file_snapshot(self, repo: RepoRef, *, path: str, revision_sha: str) -> FileSnapshot: ...


@dataclass(frozen=True)
class ReviewAnchor:
    """Stable pointer to one extracted suggestion fence inside a review comment."""

    comment_id: str
    suggestion_index: int


class ProvenanceDropRecord(BaseModel):
    """One inventory row that could not be safely promoted."""

    schema_version: str = "1.0"
    example_id: str
    chosen_source: str
    source_row_keys: list[str] = Field(default_factory=list)
    reasons: list[str]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Inventory JSONL, usually reconstructable.jsonl.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--github-token", help="Use one explicit GitHub token for every host.")
    return parser.parse_args()


def _parse_review_anchor(value: str | None) -> ReviewAnchor | None:
    if not value:
        return None
    match = _REVIEW_ANCHOR_RE.fullmatch(value)
    if match is None:
        return None
    return ReviewAnchor(
        comment_id=match.group("comment_id"),
        suggestion_index=int(match.group("index")),
    )


def _repo_ref(record: ExplorationCandidateRecord) -> RepoRef | None:
    if record.repo is None or record.pr_number is None:
        return None
    parts = record.repo.split("/", maxsplit=2)
    if len(parts) != 3 or not all(parts):
        return None
    return RepoRef(hostname=parts[0], owner=parts[1], repo=parts[2], pr_number=record.pr_number)


def _candidate_row(record: ExplorationCandidateRecord, repo: RepoRef) -> CandidateRow:
    return CandidateRow(
        inspection_id=f"phase5-{record.example_id}",
        github_repo_url=f"https://{repo.hostname}/{repo.owner}/{repo.repo}",
        repo_name=f"{repo.owner}/{repo.repo}",
        commit_id=None,
        pipeline_url=record.pr_url,
        execution_id=f"phase5-{record.example_id}",
        fault_id=record.example_id,
        handler_status="success",
        pr_number=str(repo.pr_number),
    )


def _matching_review_comment(comments: list[dict[str, object]], anchor: ReviewAnchor) -> dict[str, object] | None:
    for comment in comments:
        if str(comment.get("id") or "") == anchor.comment_id:
            return comment
    return None


def _suggested_paths(provenance: SuggestionProvenance, suggested_diff: str) -> list[str]:
    parsed = parse_unified_diff(suggested_diff)
    candidate_paths = [provenance.path]
    candidate_paths.extend(file_diff.canonical_path for file_diff in parsed.files)
    return list(dict.fromkeys(path for path in candidate_paths if path))


async def _snapshot_or_error(
    gateway: ProvenanceGateway,
    repo: RepoRef,
    *,
    path: str,
    revision_sha: str,
) -> tuple[FileSnapshot | None, str | None]:
    try:
        return await gateway.fetch_file_snapshot(repo, path=path, revision_sha=revision_sha), None
    except (httpx.HTTPError, ValueError) as exc:
        return None, f"snapshot for {path}@{revision_sha}: {type(exc).__name__}: {exc}"


async def _reconstruct_one(
    record: ExplorationCandidateRecord,
    *,
    gateway: ProvenanceGateway,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, ProvenanceDropRecord | None]:
    reasons: list[str] = []
    if record.chosen_source not in _SUPPORTED_INTERNAL_SOURCES:
        reasons.append("only internal inventory rows can be reconstructed safely")
    if not record.suggested_diff:
        reasons.append("missing suggested diff")
    if not record.landed_diff:
        reasons.append("missing merged PR diff")
    anchor = _parse_review_anchor(record.suggestion_anchor)
    if anchor is None:
        reasons.append("missing supported GitHub review-comment suggestion anchor")
    repo = _repo_ref(record)
    if repo is None:
        reasons.append("missing GitHub repository or PR identity")
    if reasons:
        return None, None, _drop_record(record, reasons)

    assert anchor is not None
    assert repo is not None
    assert record.suggested_diff is not None
    assert record.landed_diff is not None

    try:
        pr_json = await gateway.fetch_pr_json(repo)
        comments = await gateway.fetch_pr_review_comments(repo)
    except (httpx.HTTPError, ValueError) as exc:
        return None, None, _drop_record(record, [f"github metadata error: {type(exc).__name__}: {exc}"])

    if pr_json.get("merged") is not True:
        return None, None, _drop_record(record, ["PR is not merged"])

    comment = _matching_review_comment(comments, anchor)
    if comment is None:
        return None, None, _drop_record(record, [f"review comment {anchor.comment_id} not found"])

    suggestions = extract_comment_diff_suggestions(
        _candidate_row(record, repo),
        comment,
        source="all",
        author_filters=[],
        kind="review",
    )
    expected_diff_path = f"github_review_comment:{anchor.comment_id}#suggestion:{anchor.suggestion_index}"
    suggestion = next((item for item in suggestions if item.diff_path == expected_diff_path), None)
    if suggestion is None or suggestion.provenance is None:
        return None, None, _drop_record(record, [f"suggestion anchor {expected_diff_path} not found"])
    if suggestion.diff_text != record.suggested_diff:
        return None, None, _drop_record(record, ["fetched suggestion text differs from inventory row"])

    provenance_data = suggestion.provenance.model_dump(mode="json")
    merge_commit_sha = pr_json.get("merge_commit_sha") or record.merge_commit_sha
    provenance_data.update(
        {
            "pull_base_sha": nested_string(pr_json, "base", "sha"),
            "pull_head_sha": nested_string(pr_json, "head", "sha"),
            "merge_commit_sha": merge_commit_sha,
            "pr_merged_at": pr_json.get("merged_at"),
            "compared_diff_base_sha": nested_string(pr_json, "base", "sha"),
            "compared_diff_head_sha": nested_string(pr_json, "head", "sha"),
            "compared_diff_source": "github_pull_diff_api",
        }
    )

    base_revision = suggestion.provenance.original_commit_sha or suggestion.provenance.comment_commit_sha
    file_provenance: list[FileProvenance] = []
    snapshot_errors: list[str] = []
    for suggested_path in _suggested_paths(suggestion.provenance, record.suggested_diff):
        final_path, relation = final_path_for_suggested_path(suggested_path, record.landed_diff)
        suggestion_snapshot: FileSnapshot | None = None
        final_snapshot: FileSnapshot | None = None
        if base_revision:
            suggestion_snapshot, error = await _snapshot_or_error(
                gateway,
                repo,
                path=suggested_path,
                revision_sha=base_revision,
            )
            if error:
                snapshot_errors.append(f"suggestion-time {error}")
        if final_path and isinstance(merge_commit_sha, str):
            final_snapshot, error = await _snapshot_or_error(
                gateway,
                repo,
                path=final_path,
                revision_sha=merge_commit_sha,
            )
            if error:
                snapshot_errors.append(f"final-state {error}")
        file_provenance.append(
            FileProvenance(
                suggested_path=suggested_path,
                final_path=final_path,
                relation=relation,
                suggestion_base_snapshot=suggestion_snapshot,
                final_state_snapshot=final_snapshot,
            )
        )

    provenance_data["files"] = [item.model_dump(mode="json") for item in file_provenance]
    if len(file_provenance) == 1:
        provenance_data["suggestion_base_snapshot"] = (
            file_provenance[0].suggestion_base_snapshot.model_dump(mode="json")
            if file_provenance[0].suggestion_base_snapshot
            else None
        )
        provenance_data["final_state_snapshot"] = (
            file_provenance[0].final_state_snapshot.model_dump(mode="json")
            if file_provenance[0].final_state_snapshot
            else None
        )
    provenance_data["collection_errors"] = snapshot_errors

    try:
        provenance = SuggestionProvenance.model_validate(provenance_data)
    except ValidationError as exc:
        return None, None, _drop_record(record, [f"invalid reconstructed provenance: {exc}"])
    issues = provenance.validation_issues()
    if issues:
        return None, None, _drop_record(record, issues)

    enriched = record.model_dump(mode="json")
    enriched["status"] = "benchmark_ready"
    enriched["suggestion_provenance"] = provenance.model_dump(mode="json")
    enriched["missing_requirements"] = []
    enriched["quarantine_reasons"] = []
    candidate = BenchmarkCandidate(
        example_id=record.example_id,
        repo=record.repo or "",
        pr_url=record.pr_url or "",
        pr_number=record.pr_number or 0,
        suggested_diff=record.suggested_diff,
        landed_diff=record.landed_diff,
        suggestion_provenance=provenance,
    )
    return enriched, candidate.model_dump(mode="json"), None


def _drop_record(record: ExplorationCandidateRecord, reasons: list[str]) -> ProvenanceDropRecord:
    return ProvenanceDropRecord(
        example_id=record.example_id,
        chosen_source=record.chosen_source,
        source_row_keys=record.source_row_keys,
        reasons=list(dict.fromkeys(reasons)),
    )


async def reconstruct_inventory_provenance(
    *,
    input_path: Path,
    output_dir: Path,
    github_token: str | None = None,
    gateway: ProvenanceGateway | None = None,
) -> dict[str, Any]:
    """Promote only provenance-complete inventory rows into benchmark candidates."""
    rows = [ExplorationCandidateRecord.model_validate(row) for row in read_jsonl_objects(input_path)]
    if gateway is None:
        async with GitHubHttpGateway.connect(explicit_token=github_token, settings=DatasetSettings()) as http_gateway:
            return await reconstruct_inventory_provenance(
                input_path=input_path,
                output_dir=output_dir,
                gateway=http_gateway,
            )

    enriched_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    dropped_rows: list[dict[str, Any]] = []
    for record in rows:
        enriched, candidate, dropped = await _reconstruct_one(record, gateway=gateway)
        if enriched is not None and candidate is not None:
            enriched_rows.append(enriched)
            candidate_rows.append(candidate)
        elif dropped is not None:
            dropped_rows.append(dropped.model_dump(mode="json"))

    summary = {
        "schema_version": "1.0",
        "input_path": str(input_path),
        "input_rows": len(rows),
        "provenance_complete_rows": len(enriched_rows),
        "benchmark_candidate_examples": len(candidate_rows),
        "dropped_rows": len(dropped_rows),
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with staged_output_directory(output_dir) as staging_dir:
        write_jsonl_objects(staging_dir / "provenance_complete.jsonl", enriched_rows, sort_keys=True)
        write_jsonl_objects(staging_dir / "benchmark_candidates.jsonl", candidate_rows, sort_keys=True)
        write_jsonl_objects(staging_dir / "dropped_provenance.jsonl", dropped_rows, sort_keys=True)
        (staging_dir / "reconstruction_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return summary


def main() -> int:
    """Run provenance reconstruction from an inventory JSONL file."""
    args = parse_args()
    summary = asyncio.run(
        reconstruct_inventory_provenance(
            input_path=args.input,
            output_dir=args.output_dir,
            github_token=args.github_token,
        )
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
