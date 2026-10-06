#!/usr/bin/env python3
"""Collect suggestion-vs-merged-diff examples from GitHub pull requests."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import re
import sys
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urljoin, urlparse

import httpx
from pydantic import BaseModel
from pydantic import SecretStr
from pydantic_settings import BaseSettings

from pr_suggestion_metrics.artifact_io import write_jsonl_object_lines
from pr_suggestion_metrics.diff.parser import parse_unified_diff
from pr_suggestion_metrics.scientific_contracts import FileProvenance, FileSnapshot, SuggestionProvenance

_FL_COMMENT_MARKERS = (
    "# Fault Localization",
    "Fault Analyzer",
    "<!--inspection_id_",
    "<!--feedback_block-->",
)
_CODE_SUGGESTION_FENCE_RE = re.compile(r"`{3,}(diff|patch|suggestion)\s*\n(.*?)\n`{3,}", re.IGNORECASE | re.DOTALL)
_FAULT_HANDLER_IDS_RE = re.compile(r"<!--fault_handler_ids_([^>]*)-->")


class CandidateRow(BaseModel):
    """One GitHub pull request selected for suggestion collection."""

    inspection_id: str
    created_at: str | None = None
    github_repo_url: str | None = None
    repo_name: str | None = None
    commit_id: str | None = None
    pipeline_url: str | None = None
    execution_id: str
    fault_id: str
    handler_status: str
    pr_number: str | None = None


class SuggestionDiff(BaseModel):
    """One suggestion diff extracted from a GitHub PR comment."""

    candidate: CandidateRow
    diff_path: str
    diff_text: str
    diff_bytes: int
    provenance: SuggestionProvenance | None = None


class CodeChangeMiss(BaseModel):
    """One candidate or suggestion that could not be collected."""

    inspection_id: str
    execution_id: str
    fault_id: str
    diff_path: str
    reason: str


class DatasetSettings(BaseSettings):
    """Settings used when collecting from GitHub."""

    github_wdf_token: SecretStr | None = None
    github_tool_token: SecretStr | None = None
    ssl_ca_bundle: str | None = "/etc/ssl/ca-bundle.pem"

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


class RepoRef(BaseModel):
    """Parsed GitHub repository reference."""

    hostname: str
    owner: str
    repo: str
    pr_number: int


class PairedExample(BaseModel):
    """Dataset row pairing one comment suggestion with the final merged PR diff."""

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
    reviewer_edited_version: str | None = None
    renamed_files: bool | None = None
    config_files_touched: bool | None = None
    suggestion_provenance: SuggestionProvenance | None = None


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--github-pr-url",
        action="append",
        required=True,
        help="GitHub PR URL to collect. Repeatable.",
    )
    parser.add_argument(
        "--comment-source",
        choices=("fl", "hyperspace", "all"),
        default="fl",
        help="Which PR comments/review comments to treat as suggestion sources.",
    )
    parser.add_argument(
        "--comment-author-contains",
        action="append",
        default=[],
        help="Only use comments whose GitHub author login contains this text. Repeatable.",
    )
    parser.add_argument(
        "--review-comments-only",
        action="store_true",
        help="Only scan inline PR review comments; skips top-level PR issue comments.",
    )
    parser.add_argument(
        "--github-concurrency",
        type=int,
        default=8,
        help="Maximum concurrent GitHub PRs to scan/fetch. Default: 8.",
    )
    parser.add_argument("--output", type=Path, help="Write paired examples to this file. Defaults to stdout.")
    parser.add_argument("--github-token", help="Use one explicit GitHub token for every host.")
    parser.add_argument(
        "--include-unmerged-prs",
        action="store_true",
        help="Include PRs that are not merged yet. Default skips them because there is no landed diff.",
    )
    return parser.parse_args()


def _api_base(hostname: str) -> str:
    """Return the REST API base URL for GitHub.com or GitHub Enterprise."""
    if hostname == "github.com":
        return "https://api.github.com"
    return urljoin(f"https://{hostname}/", "api/v3").rstrip("/")


def _parse_github_repo(candidate: CandidateRow) -> RepoRef | None:
    """Parse repo host, owner, name, and PR number from a candidate."""
    pr_number_raw = candidate.pr_number
    for value in (candidate.github_repo_url, candidate.pipeline_url):
        if not value:
            continue
        parsed = urlparse(value)
        if not parsed.hostname:
            continue
        if "github" not in parsed.hostname:
            continue
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 2:
            continue
        repo = path_parts[1]
        if repo.endswith(".git"):
            repo = repo.removesuffix(".git")
        pr_number = pr_number_raw
        if pr_number is None and "pull" in path_parts:
            pull_index = path_parts.index("pull")
            if len(path_parts) > pull_index + 1:
                pr_number = path_parts[pull_index + 1]
        if pr_number is None:
            continue
        try:
            return RepoRef(
                hostname=parsed.hostname,
                owner=path_parts[0],
                repo=repo,
                pr_number=int(pr_number),
            )
        except ValueError:
            continue
    return None


def _candidate_from_github_pr_url(url: str) -> CandidateRow:
    """Build a candidate row from a direct GitHub PR URL."""
    parsed = urlparse(url)
    if not parsed.hostname:
        raise ValueError(f"GitHub PR URL has no host: {url!r}")
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 4 or path_parts[2] != "pull":
        raise ValueError(f"GitHub PR URL must look like /owner/repo/pull/number: {url!r}")
    owner, repo_name, _, pr_number = path_parts[:4]
    int(pr_number)
    return CandidateRow(
        inspection_id=f"github-pr-{parsed.hostname}-{owner}-{repo_name}-{pr_number}",
        github_repo_url=f"https://{parsed.hostname}/{owner}/{repo_name}",
        repo_name=f"{owner}/{repo_name}",
        commit_id=None,
        pipeline_url=url,
        execution_id=f"github-pr-{pr_number}",
        fault_id=f"github-pr-{pr_number}",
        handler_status="success",
        pr_number=pr_number,
    )


def _github_headers(token: str | None, accept: str = "application/vnd.github+json") -> dict[str, str]:
    """Build GitHub API headers."""
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _progress(message: str) -> None:
    """Print a progress message immediately to stderr."""
    print(message, file=sys.stderr, flush=True)


def _github_verify_value(settings: DatasetSettings) -> str | bool:
    """Return an httpx verify value that works on local machines and SAP hosts."""
    if settings.ssl_ca_bundle and Path(settings.ssl_ca_bundle).exists():
        return settings.ssl_ca_bundle
    return True


def _token_for_host(hostname: str, *, explicit_token: str | None, settings: DatasetSettings) -> str | None:
    """Resolve a GitHub token for one host."""
    if explicit_token:
        return explicit_token
    if "wdf" in hostname and settings.github_wdf_token:
        return settings.github_wdf_token.get_secret_value()
    if settings.github_tool_token:
        return settings.github_tool_token.get_secret_value()
    return None


async def _fetch_pr_json(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
) -> dict[str, object]:
    """Fetch GitHub pull request metadata as JSON."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{_api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/pulls/{repo.pr_number}"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"GitHub PR response for {url} was not an object")
    return data


async def _fetch_pr_diff(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
) -> str:
    """Fetch the full pull request diff from GitHub."""
    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{_api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/pulls/{repo.pr_number}"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.text


async def _fetch_pr_comments(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
) -> list[dict[str, object]]:
    """Fetch all issue comments on one pull request."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    comments: list[dict[str, object]] = []
    page = 1
    while True:
        url = f"{_api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/issues/{repo.pr_number}/comments"
        response = await client.get(url, headers=headers, params={"per_page": 100, "page": page})
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError(f"GitHub comments response for {url} was not a list")
        comments.extend(entry for entry in data if isinstance(entry, dict))
        if len(data) < 100:
            return comments
        page += 1


async def _fetch_pr_review_comments(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
) -> list[dict[str, object]]:
    """Fetch all pull request review comments for one PR."""
    comments: list[dict[str, object]] = []
    page = 1
    while True:
        url = f"{_api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/pulls/{repo.pr_number}/comments"
        response = await client.get(url, headers=_github_headers(token), params={"per_page": 100, "page": page})
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError(f"GitHub review comments response for {url} was not a list")
        comments.extend(entry for entry in data if isinstance(entry, dict))
        if len(data) < 100:
            return comments
        page += 1


async def _fetch_file_snapshot(
    client: httpx.AsyncClient,
    *,
    repo: RepoRef,
    token: str | None,
    path: str,
    revision_sha: str,
) -> FileSnapshot:
    """Fetch one UTF-8 repository file at an immutable Git revision."""
    encoded_path = quote(path, safe="/")
    url = f"{_api_base(repo.hostname)}/repos/{repo.owner}/{repo.repo}/contents/{encoded_path}"
    response = await client.get(url, headers=_github_headers(token), params={"ref": revision_sha})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("type") != "file":
        raise ValueError(f"GitHub content response for {path}@{revision_sha} was not a file")
    content = payload.get("content")
    if not isinstance(content, str) or payload.get("encoding") != "base64":
        raise ValueError(f"GitHub content response for {path}@{revision_sha} was not base64 text")
    decoded = base64.b64decode(content, validate=False).decode("utf-8", errors="replace")
    return FileSnapshot(
        revision_sha=revision_sha,
        path=path,
        content=decoded,
        content_sha256=hashlib.sha256(decoded.encode("utf-8")).hexdigest(),
        source="github_contents_api",
    )


def _comment_author(comment: dict[str, object]) -> str:
    """Return the GitHub login for one comment, or empty string."""
    user = comment.get("user")
    if not isinstance(user, dict):
        return ""
    login = user.get("login")
    return login if isinstance(login, str) else ""


def _matches_comment_source(
    comment: dict[str, object],
    *,
    source: Literal["fl", "hyperspace", "all"],
    author_filters: list[str],
) -> bool:
    """Return whether a comment should be mined for suggestion code fences."""
    body = comment.get("body")
    if not isinstance(body, str):
        return False
    author = _comment_author(comment).lower()
    if author_filters and not any(value.lower() in author for value in author_filters):
        return False
    if source == "all":
        return True
    if source == "fl":
        return any(marker in body for marker in _FL_COMMENT_MARKERS)
    return "hyperspace" in author or "hyperspace" in body.lower()


def _comment_path(comment: dict[str, object]) -> str | None:
    """Return the file path attached to a review comment, when available."""
    path = comment.get("path")
    return path if isinstance(path, str) and path else None


def _normalize_comment_suggestion(language: str, text: str, path: str | None) -> str:
    """Represent a PR-comment suggestion as diff-like text for downstream tooling."""
    normalized = text.strip()
    if language.lower() in {"diff", "patch"}:
        if path and not normalized.startswith(("diff --git ", "--- ")):
            return f"--- a/{path}\n+++ b/{path}\n{normalized}"
        return normalized
    if path:
        added = "\n".join(f"+{line}" for line in normalized.splitlines())
        return f"--- a/{path}\n+++ b/{path}\n@@\n{added}"
    return normalized


def _extract_comment_diff_suggestions(
    candidate: CandidateRow,
    comment: dict[str, object],
    *,
    source: Literal["fl", "hyperspace", "all"],
    author_filters: list[str],
    kind: Literal["issue", "review"],
) -> list[SuggestionDiff]:
    """Extract code suggestion fences from one PR comment."""
    body = comment.get("body")
    if not isinstance(body, str) or not _matches_comment_source(comment, source=source, author_filters=author_filters):
        return []

    comment_id = str(comment.get("id") or "unknown")
    html_url = str(comment.get("html_url") or "")
    source_kind = "github_review_comment" if kind == "review" else "github_issue_comment"
    suggestions: list[SuggestionDiff] = []
    for index, match in enumerate(_CODE_SUGGESTION_FENCE_RE.finditer(body), start=1):
        diff_text = _normalize_comment_suggestion(match.group(1), match.group(2), _comment_path(comment))
        if not diff_text:
            continue
        following_text = body[match.end() :]
        handler_match = _FAULT_HANDLER_IDS_RE.search(following_text)
        fault_id = f"github-{kind}-comment-{comment_id}-{index}"
        if handler_match and handler_match.group(1).strip():
            fault_id = handler_match.group(1).split(",", maxsplit=1)[0].strip()
        comment_candidate = candidate.model_copy(
            update={
                "execution_id": f"github-{kind}-comment-{comment_id}-{index}",
                "fault_id": fault_id,
            }
        )
        suggestions.append(
            SuggestionDiff(
                candidate=comment_candidate,
                diff_path=f"github_{kind}_comment:{comment_id}#suggestion:{index}",
                diff_text=diff_text,
                diff_bytes=len(diff_text.encode("utf-8")),
                provenance=SuggestionProvenance.model_validate(
                    {
                        "source_kind": source_kind,
                        "suggestion_id": f"github:{kind}:{comment_id}:{index}",
                        "comment_url": html_url or None,
                        "author_login": _comment_author(comment) or None,
                        "suggestion_created_at": comment.get("created_at"),
                        "suggestion_updated_at": comment.get("updated_at"),
                        "comment_commit_sha": comment.get("commit_id"),
                        "original_commit_sha": comment.get("original_commit_id"),
                        "path": _comment_path(comment),
                        "line": comment.get("line"),
                        "start_line": comment.get("start_line"),
                        "side": comment.get("side"),
                        "start_side": comment.get("start_side"),
                        "original_line": comment.get("original_line"),
                        "original_start_line": comment.get("original_start_line"),
                        "original_position": comment.get("original_position"),
                    }
                ),
            )
        )
    return suggestions


async def _load_suggestion_diffs_from_pr_comments(
    candidates: list[CandidateRow],
    *,
    github_token: str | None,
    source: Literal["fl", "hyperspace", "all"],
    author_filters: list[str],
    review_comments_only: bool,
    github_concurrency: int,
) -> tuple[list[SuggestionDiff], list[CodeChangeMiss]]:
    """Load suggestion diffs from GitHub PR issue/review comments."""
    settings = DatasetSettings()
    suggestions: list[SuggestionDiff] = []
    misses: list[CodeChangeMiss] = []
    grouped_candidates: dict[tuple[str, str, str, int], CandidateRow] = {}

    for candidate in candidates:
        repo = _parse_github_repo(candidate)
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
    concurrency = max(1, github_concurrency)
    semaphore = asyncio.Semaphore(concurrency)

    async def scan_repo(
        client: httpx.AsyncClient,
        repo: RepoRef,
        index: int,
    ) -> tuple[list[SuggestionDiff], CodeChangeMiss | None]:
        async with semaphore:
            if index == 1 or index % 10 == 0 or index == len(repos):
                _progress(f"GitHub: scanning PR comments {index}/{len(repos)}")
            candidate = grouped_candidates[(repo.hostname, repo.owner, repo.repo, repo.pr_number)]
            token = _token_for_host(repo.hostname, explicit_token=github_token, settings=settings)
            try:
                if review_comments_only:
                    issue_comments: list[dict[str, object]] = []
                    review_comments = await _fetch_pr_review_comments(client, repo=repo, token=token)
                else:
                    issue_comments, review_comments = await asyncio.gather(
                        _fetch_pr_comments(client, repo=repo, token=token),
                        _fetch_pr_review_comments(client, repo=repo, token=token),
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
                    _extract_comment_diff_suggestions(
                        candidate,
                        comment,
                        source=source,
                        author_filters=author_filters,
                        kind="issue",
                    )
                )
            for comment in review_comments:
                found_for_pr.extend(
                    _extract_comment_diff_suggestions(
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

    async with httpx.AsyncClient(verify=_github_verify_value(settings), timeout=30.0) as client:
        outcomes = await asyncio.gather(*(scan_repo(client, repo, index) for index, repo in enumerate(repos, start=1)))

    for found_suggestions, miss in outcomes:
        suggestions.extend(found_suggestions)
        if miss is not None:
            misses.append(miss)

    return suggestions, misses


def _nested_string(data: dict[str, object], key: str, nested_key: str) -> str | None:
    """Extract a string from a one-level nested GitHub object."""
    nested = data.get(key)
    if not isinstance(nested, dict):
        return None
    value = nested.get(nested_key)
    return value if isinstance(value, str) else None


def _diff_has_renames(diff_text: str) -> bool:
    """Return True when a unified diff includes a file rename marker."""
    return "\nrename from " in diff_text or "\nrename to " in diff_text


def _final_path_for_suggested_path(
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


def _diff_touches_config(diff_text: str) -> bool:
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


async def _collect_pairs(
    suggestions: list[SuggestionDiff],
    *,
    github_token: str | None,
    include_unmerged_prs: bool,
) -> tuple[list[PairedExample], list[CodeChangeMiss]]:
    """Fetch merged PR diffs and pair them with comment suggestion diffs."""
    settings = DatasetSettings()
    pairs: list[PairedExample] = []
    misses: list[CodeChangeMiss] = []
    pr_cache: dict[tuple[str, str, str, int], tuple[dict[str, object], str]] = {}
    snapshot_cache: dict[tuple[str, str, str, str, str], FileSnapshot] = {}

    async with httpx.AsyncClient(verify=_github_verify_value(settings), timeout=30.0) as client:
        for index, suggestion in enumerate(suggestions, start=1):
            if index == 1 or index % 10 == 0 or index == len(suggestions):
                _progress(f"GitHub: fetching merged PR diff {index}/{len(suggestions)}")
            candidate = suggestion.candidate
            repo = _parse_github_repo(candidate)
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

            token = _token_for_host(repo.hostname, explicit_token=github_token, settings=settings)
            repo_key = (repo.hostname, repo.owner, repo.repo, repo.pr_number)
            try:
                if repo_key not in pr_cache:
                    pr_cache[repo_key] = await asyncio.gather(
                        _fetch_pr_json(client, repo=repo, token=token),
                        _fetch_pr_diff(client, repo=repo, token=token),
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

            merged = pr_json.get("merged")
            if merged is not True and not include_unmerged_prs:
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
                        "pull_base_sha": _nested_string(pr_json, "base", "sha"),
                        "pull_head_sha": _nested_string(pr_json, "head", "sha"),
                        "merge_commit_sha": pr_json.get("merge_commit_sha"),
                        "pr_merged_at": pr_json.get("merged_at"),
                        "compared_diff_base_sha": _nested_string(pr_json, "base", "sha"),
                        "compared_diff_head_sha": _nested_string(pr_json, "head", "sha"),
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
                    final_path, relation = _final_path_for_suggested_path(suggested_path, pr_diff)
                    suggestion_snapshot: FileSnapshot | None = None
                    final_snapshot: FileSnapshot | None = None
                    if base_revision:
                        cache_key = (repo.hostname, repo.owner, repo.repo, suggested_path, base_revision)
                        try:
                            if cache_key not in snapshot_cache:
                                snapshot_cache[cache_key] = await _fetch_file_snapshot(
                                    client,
                                    repo=repo,
                                    token=token,
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
                                snapshot_cache[cache_key] = await _fetch_file_snapshot(
                                    client,
                                    repo=repo,
                                    token=token,
                                    path=final_path,
                                    revision_sha=final_revision,
                                )
                            final_snapshot = snapshot_cache[cache_key]
                        except (httpx.HTTPError, ValueError) as exc:
                            snapshot_errors.append(
                                f"final-state snapshot for {final_path}: {type(exc).__name__}: {exc}"
                            )
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
                    source_branch=_nested_string(pr_json, "head", "ref"),
                    target_branch=_nested_string(pr_json, "base", "ref"),
                    base_sha=_nested_string(pr_json, "base", "sha"),
                    head_sha=_nested_string(pr_json, "head", "sha"),
                    merge_commit_sha=merge_commit_sha if isinstance(merge_commit_sha, str) else None,
                    inspection_commit_sha=candidate.commit_id,
                    handler_diff_path=suggestion.diff_path,
                    merged_pr_diff_source="github_pull_diff_api",
                    renamed_files=_diff_has_renames(pr_diff),
                    config_files_touched=_diff_touches_config(pr_diff),
                    suggestion_provenance=provenance,
                )
            )

    return pairs, misses


def _write_pairs_jsonl(pairs: list[PairedExample], output: Path | None) -> None:
    """Write paired examples as JSONL to stdout or a file."""
    if output is None:
        lines = [pair.model_dump_json(exclude_none=False) for pair in pairs]
        content = "\n".join(lines)
        if content:
            content += "\n"
        print(content, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl_object_lines(output, (pair.model_dump_json(exclude_none=False) for pair in pairs))


async def async_main() -> int:
    """Collect suggestion examples from GitHub pull request comments."""
    args = parse_args()
    _progress("GitHub: loading direct PR candidates")
    candidates = [_candidate_from_github_pr_url(url) for url in args.github_pr_url]
    _progress(f"GitHub: loaded {len(candidates)} direct PR candidate(s)")

    _progress("GitHub: loading suggestion diffs from PR comments")
    suggestions, suggestion_misses = await _load_suggestion_diffs_from_pr_comments(
        candidates,
        github_token=args.github_token,
        source=args.comment_source,
        author_filters=args.comment_author_contains,
        review_comments_only=args.review_comments_only,
        github_concurrency=args.github_concurrency,
    )
    _progress(f"GitHub: loaded {len(suggestions)} comment suggestion diff(s), misses={len(suggestion_misses)}")

    _progress("GitHub: fetching merged PR diffs")
    pairs, github_misses = await _collect_pairs(
        suggestions,
        github_token=args.github_token,
        include_unmerged_prs=args.include_unmerged_prs,
    )
    _progress(f"GitHub: collected {len(pairs)} pair(s), misses={len(github_misses)}")
    _write_pairs_jsonl(pairs, args.output)
    print(
        "summary: "
        f"candidates={len(candidates)} suggestions={len(suggestions)} pairs={len(pairs)} "
        f"misses={len(suggestion_misses) + len(github_misses)}",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    """Script entry point."""
    try:
        return asyncio.run(async_main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
