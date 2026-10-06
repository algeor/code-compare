"""Collection services for pairing GitHub suggestions with merged diffs."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from typing import Literal, Protocol

import httpx

from pr_suggestion_metrics.collection.contracts import (
    CandidateRow,
    CodeChangeMiss,
    DatasetSettings,
    PairedExample,
    RepoRef,
    SuggestionDiff,
)
from pr_suggestion_metrics.collection.extraction import extract_comment_diff_suggestions, parse_github_repo
from pr_suggestion_metrics.collection.github import GitHubHttpGateway
from pr_suggestion_metrics.diff.parser import parse_unified_diff
from pr_suggestion_metrics.scientific_contracts import FileProvenance, FileSnapshot, SuggestionProvenance


class CollectionGateway(Protocol):
    """GitHub operations required by collection services."""

    async def fetch_pr_json(self, repo: RepoRef) -> dict[str, object]: ...

    async def fetch_pr_diff(self, repo: RepoRef) -> str: ...

    async def fetch_pr_comments(self, repo: RepoRef) -> list[dict[str, object]]: ...

    async def fetch_pr_review_comments(self, repo: RepoRef) -> list[dict[str, object]]: ...

    async def fetch_file_snapshot(self, repo: RepoRef, *, path: str, revision_sha: str) -> FileSnapshot: ...


ProgressCallback = Callable[[str], None]


def _default_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def nested_string(data: dict[str, object], key: str, nested_key: str) -> str | None:
    """Extract a string from a one-level nested GitHub object."""
    nested = data.get(key)
    if not isinstance(nested, dict):
        return None
    value = nested.get(nested_key)
    return value if isinstance(value, str) else None


def diff_has_renames(diff_text: str) -> bool:
    """Return True when a unified diff includes a file rename marker."""
    return "\nrename from " in diff_text or "\nrename to " in diff_text


def final_path_for_suggested_path(
    path: str,
    merged_pr_diff: str,
) -> tuple[str | None, Literal["same", "renamed", "deleted"]]:
    """Resolve a suggestion-time path through merged-PR rename/delete metadata."""
    for file_diff in parse_unified_diff(merged_pr_diff).files:
        if file_diff.old_path != path and file_diff.new_path != path:
            continue
        if file_diff.new_path is None:
            return None, "deleted"
        if file_diff.old_path is not None and file_diff.old_path != file_diff.new_path:
            return file_diff.new_path, "renamed"
        return file_diff.new_path, "same"
    return path, "same"


def diff_touches_config(diff_text: str) -> bool:
    """Return True when changed paths look like config files."""
    config_suffixes = (
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".conf",
        ".properties",
        ".xml",
    )
    config_names = {
        "dockerfile",
        "makefile",
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    }
    for line in diff_text.splitlines():
        if not line.startswith("diff --git "):
            continue
        path = line.rsplit(" b/", maxsplit=1)[-1].strip().lower()
        name = path.rsplit("/", maxsplit=1)[-1]
        if name in config_names or path.endswith(config_suffixes):
            return True
    return False


async def load_suggestion_diffs_from_pr_comments(
    candidates: list[CandidateRow],
    *,
    github_token: str | None,
    source: Literal["fl", "hyperspace", "all"],
    author_filters: list[str],
    review_comments_only: bool,
    github_concurrency: int,
    gateway: CollectionGateway | None = None,
    progress: ProgressCallback = _default_progress,
) -> tuple[list[SuggestionDiff], list[CodeChangeMiss]]:
    """Load suggestion diffs from GitHub PR issue/review comments."""
    if gateway is not None:
        return await _load_suggestion_diffs_with_gateway(
            candidates,
            source=source,
            author_filters=author_filters,
            review_comments_only=review_comments_only,
            github_concurrency=github_concurrency,
            gateway=gateway,
            progress=progress,
        )

    settings = DatasetSettings()
    async with GitHubHttpGateway.connect(explicit_token=github_token, settings=settings) as http_gateway:
        return await _load_suggestion_diffs_with_gateway(
            candidates,
            source=source,
            author_filters=author_filters,
            review_comments_only=review_comments_only,
            github_concurrency=github_concurrency,
            gateway=http_gateway,
            progress=progress,
        )


async def _load_suggestion_diffs_with_gateway(
    candidates: list[CandidateRow],
    *,
    source: Literal["fl", "hyperspace", "all"],
    author_filters: list[str],
    review_comments_only: bool,
    github_concurrency: int,
    gateway: CollectionGateway,
    progress: ProgressCallback,
) -> tuple[list[SuggestionDiff], list[CodeChangeMiss]]:
    suggestions: list[SuggestionDiff] = []
    misses: list[CodeChangeMiss] = []
    grouped_candidates: dict[tuple[str, str, str, int], CandidateRow] = {}

    for candidate in candidates:
        repo = parse_github_repo(candidate)
        if repo is None:
            misses.append(
                CodeChangeMiss(
                    inspection_id=candidate.inspection_id,
                    execution_id=candidate.execution_id,
                    fault_id=candidate.fault_id,
                    diff_path="github_comments",
                    reason="github_repo_or_pr_not_resolved",
                )
            )
            continue
        key = (repo.hostname, repo.owner, repo.repo, repo.pr_number)
        grouped_candidates.setdefault(key, candidate)

    repos = [
        RepoRef(hostname=host, owner=owner, repo=repo_name, pr_number=pr_number)
        for host, owner, repo_name, pr_number in grouped_candidates
    ]
    semaphore = asyncio.Semaphore(max(1, github_concurrency))

    async def scan_repo(repo: RepoRef, index: int) -> tuple[list[SuggestionDiff], CodeChangeMiss | None]:
        async with semaphore:
            if index == 1 or index % 10 == 0 or index == len(repos):
                progress(f"GitHub: scanning PR comments {index}/{len(repos)}")
            candidate = grouped_candidates[(repo.hostname, repo.owner, repo.repo, repo.pr_number)]
            try:
                if review_comments_only:
                    issue_comments: list[dict[str, object]] = []
                    review_comments = await gateway.fetch_pr_review_comments(repo)
                else:
                    issue_comments, review_comments = await asyncio.gather(
                        gateway.fetch_pr_comments(repo),
                        gateway.fetch_pr_review_comments(repo),
                    )
            except (httpx.HTTPError, ValueError) as exc:
                return [], CodeChangeMiss(
                    inspection_id=candidate.inspection_id,
                    execution_id=candidate.execution_id,
                    fault_id=candidate.fault_id,
                    diff_path="github_comments",
                    reason=f"github_comments_error: {exc}",
                )

            found_for_pr: list[SuggestionDiff] = []
            for comment in issue_comments:
                found_for_pr.extend(
                    extract_comment_diff_suggestions(
                        candidate,
                        comment,
                        source=source,
                        author_filters=author_filters,
                        kind="issue",
                    )
                )
            for comment in review_comments:
                found_for_pr.extend(
                    extract_comment_diff_suggestions(
                        candidate,
                        comment,
                        source=source,
                        author_filters=author_filters,
                        kind="review",
                    )
                )
            if not found_for_pr:
                return [], CodeChangeMiss(
                    inspection_id=candidate.inspection_id,
                    execution_id=candidate.execution_id,
                    fault_id=candidate.fault_id,
                    diff_path="github_comments",
                    reason="no_comment_suggestion_found",
                )
            return found_for_pr, None

    outcomes = await asyncio.gather(*(scan_repo(repo, index) for index, repo in enumerate(repos, start=1)))
    for found_suggestions, miss in outcomes:
        suggestions.extend(found_suggestions)
        if miss is not None:
            misses.append(miss)
    return suggestions, misses


async def collect_pairs(
    suggestions: list[SuggestionDiff],
    *,
    github_token: str | None,
    include_unmerged_prs: bool,
    gateway: CollectionGateway | None = None,
    progress: ProgressCallback = _default_progress,
) -> tuple[list[PairedExample], list[CodeChangeMiss]]:
    """Fetch merged PR diffs and pair them with comment suggestion diffs."""
    if gateway is not None:
        return await _collect_pairs_with_gateway(
            suggestions,
            include_unmerged_prs=include_unmerged_prs,
            gateway=gateway,
            progress=progress,
        )

    settings = DatasetSettings()
    async with GitHubHttpGateway.connect(explicit_token=github_token, settings=settings) as http_gateway:
        return await _collect_pairs_with_gateway(
            suggestions,
            include_unmerged_prs=include_unmerged_prs,
            gateway=http_gateway,
            progress=progress,
        )


async def _collect_pairs_with_gateway(
    suggestions: list[SuggestionDiff],
    *,
    include_unmerged_prs: bool,
    gateway: CollectionGateway,
    progress: ProgressCallback,
) -> tuple[list[PairedExample], list[CodeChangeMiss]]:
    pairs: list[PairedExample] = []
    misses: list[CodeChangeMiss] = []
    pr_cache: dict[tuple[str, str, str, int], tuple[dict[str, object], str]] = {}
    snapshot_cache: dict[tuple[str, str, str, str, str], FileSnapshot] = {}

    for index, suggestion in enumerate(suggestions, start=1):
        if index == 1 or index % 10 == 0 or index == len(suggestions):
            progress(f"GitHub: fetching merged PR diff {index}/{len(suggestions)}")
        candidate = suggestion.candidate
        repo = parse_github_repo(candidate)
        if repo is None:
            misses.append(
                CodeChangeMiss(
                    inspection_id=candidate.inspection_id,
                    execution_id=candidate.execution_id,
                    fault_id=candidate.fault_id,
                    diff_path=suggestion.diff_path,
                    reason="github_repo_or_pr_not_resolved",
                )
            )
            continue

        repo_key = (repo.hostname, repo.owner, repo.repo, repo.pr_number)
        try:
            if repo_key not in pr_cache:
                pr_cache[repo_key] = await asyncio.gather(
                    gateway.fetch_pr_json(repo),
                    gateway.fetch_pr_diff(repo),
                )
            pr_json, pr_diff = pr_cache[repo_key]
        except httpx.HTTPError as exc:
            misses.append(
                CodeChangeMiss(
                    inspection_id=candidate.inspection_id,
                    execution_id=candidate.execution_id,
                    fault_id=candidate.fault_id,
                    diff_path=suggestion.diff_path,
                    reason=f"github_error: {exc}",
                )
            )
            continue

        if pr_json.get("merged") is not True and not include_unmerged_prs:
            misses.append(
                CodeChangeMiss(
                    inspection_id=candidate.inspection_id,
                    execution_id=candidate.execution_id,
                    fault_id=candidate.fault_id,
                    diff_path=suggestion.diff_path,
                    reason="pr_not_merged",
                )
            )
            continue

        provenance: SuggestionProvenance | None = None
        if suggestion.provenance is not None:
            provenance_data = suggestion.provenance.model_dump(mode="json")
            provenance_data.update(
                {
                    "pull_base_sha": nested_string(pr_json, "base", "sha"),
                    "pull_head_sha": nested_string(pr_json, "head", "sha"),
                    "merge_commit_sha": pr_json.get("merge_commit_sha"),
                    "pr_merged_at": pr_json.get("merged_at"),
                    "compared_diff_base_sha": nested_string(pr_json, "base", "sha"),
                    "compared_diff_head_sha": nested_string(pr_json, "head", "sha"),
                    "compared_diff_source": "github_pull_diff_api",
                }
            )
            snapshot_errors: list[str] = []
            base_revision = suggestion.provenance.original_commit_sha or suggestion.provenance.comment_commit_sha
            final_revision = pr_json.get("merge_commit_sha")
            parsed_suggestion = parse_unified_diff(suggestion.diff_text)
            candidate_paths = [suggestion.provenance.path]
            candidate_paths.extend(file_diff.canonical_path for file_diff in parsed_suggestion.files)
            suggested_paths = list(dict.fromkeys(path for path in candidate_paths if path))
            file_provenance: list[FileProvenance] = []
            for suggested_path in suggested_paths:
                final_path, relation = final_path_for_suggested_path(suggested_path, pr_diff)
                suggestion_snapshot: FileSnapshot | None = None
                final_snapshot: FileSnapshot | None = None
                if base_revision:
                    cache_key = (repo.hostname, repo.owner, repo.repo, suggested_path, base_revision)
                    try:
                        if cache_key not in snapshot_cache:
                            snapshot_cache[cache_key] = await gateway.fetch_file_snapshot(
                                repo,
                                path=suggested_path,
                                revision_sha=base_revision,
                            )
                        suggestion_snapshot = snapshot_cache[cache_key]
                    except (httpx.HTTPError, ValueError) as exc:
                        snapshot_errors.append(
                            f"suggestion-time snapshot for {suggested_path}: {type(exc).__name__}: {exc}"
                        )
                if final_path and isinstance(final_revision, str):
                    cache_key = (repo.hostname, repo.owner, repo.repo, final_path, final_revision)
                    try:
                        if cache_key not in snapshot_cache:
                            snapshot_cache[cache_key] = await gateway.fetch_file_snapshot(
                                repo,
                                path=final_path,
                                revision_sha=final_revision,
                            )
                        final_snapshot = snapshot_cache[cache_key]
                    except (httpx.HTTPError, ValueError) as exc:
                        snapshot_errors.append(f"final-state snapshot for {final_path}: {type(exc).__name__}: {exc}")
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
            provenance = SuggestionProvenance.model_validate(provenance_data)

        merge_commit_sha = pr_json.get("merge_commit_sha")
        pairs.append(
            PairedExample(
                inspection_id=candidate.inspection_id,
                fault_id=candidate.fault_id,
                handler_code_changes_diff=suggestion.diff_text,
                merged_pr_diff=pr_diff,
                repo_host=repo.hostname,
                repo_owner=repo.owner,
                repo_name=repo.repo,
                pr_number=repo.pr_number,
                pr_url=f"https://{repo.hostname}/{repo.owner}/{repo.repo}/pull/{repo.pr_number}",
                source_branch=nested_string(pr_json, "head", "ref"),
                target_branch=nested_string(pr_json, "base", "ref"),
                base_sha=nested_string(pr_json, "base", "sha"),
                head_sha=nested_string(pr_json, "head", "sha"),
                merge_commit_sha=merge_commit_sha if isinstance(merge_commit_sha, str) else None,
                inspection_commit_sha=candidate.commit_id,
                handler_diff_path=suggestion.diff_path,
                merged_pr_diff_source="github_pull_diff_api",
                renamed_files=diff_has_renames(pr_diff),
                config_files_touched=diff_touches_config(pr_diff),
                suggestion_provenance=provenance,
            )
        )

    return pairs, misses


_nested_string = nested_string
_diff_has_renames = diff_has_renames
_final_path_for_suggested_path = final_path_for_suggested_path
_diff_touches_config = diff_touches_config
_load_suggestion_diffs_from_pr_comments = load_suggestion_diffs_from_pr_comments
_collect_pairs = collect_pairs
