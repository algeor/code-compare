"""Pure GitHub comment suggestion and provenance extraction."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from pr_suggestion_metrics.collection.contracts import CandidateRow, RepoRef, SuggestionDiff
from pr_suggestion_metrics.scientific_contracts import SuggestionProvenance

_FL_COMMENT_MARKERS = (
    "# Fault Localization",
    "Fault Analyzer",
    "<!--inspection_id_",
    "<!--feedback_block-->",
)
_CODE_SUGGESTION_FENCE_RE = re.compile(r"`{3,}(diff|patch|suggestion)\s*\n(.*?)\n`{3,}", re.IGNORECASE | re.DOTALL)
_FAULT_HANDLER_IDS_RE = re.compile(r"<!--fault_handler_ids_([^>]*)-->")


def parse_github_repo(candidate: CandidateRow) -> RepoRef | None:
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


def candidate_from_github_pr_url(url: str) -> CandidateRow:
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


def comment_author(comment: dict[str, object]) -> str:
    """Return the GitHub login for one comment, or empty string."""
    user = comment.get("user")
    if not isinstance(user, dict):
        return ""
    login = user.get("login")
    return login if isinstance(login, str) else ""


def matches_comment_source(
    comment: dict[str, object],
    *,
    source: Literal["fl", "hyperspace", "all"],
    author_filters: list[str],
) -> bool:
    """Return whether a comment should be mined for suggestion code fences."""
    body = comment.get("body")
    if not isinstance(body, str):
        return False
    author = comment_author(comment).lower()
    if author_filters and not any(value.lower() in author for value in author_filters):
        return False
    if source == "all":
        return True
    if source == "fl":
        return any(marker in body for marker in _FL_COMMENT_MARKERS)
    return "hyperspace" in author or "hyperspace" in body.lower()


def comment_path(comment: dict[str, object]) -> str | None:
    """Return the file path attached to a review comment, when available."""
    path = comment.get("path")
    return path if isinstance(path, str) and path else None


def normalize_comment_suggestion(language: str, text: str, path: str | None) -> str:
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


def extract_comment_diff_suggestions(
    candidate: CandidateRow,
    comment: dict[str, object],
    *,
    source: Literal["fl", "hyperspace", "all"],
    author_filters: list[str],
    kind: Literal["issue", "review"],
) -> list[SuggestionDiff]:
    """Extract code suggestion fences from one PR comment."""
    body = comment.get("body")
    if not isinstance(body, str) or not matches_comment_source(comment, source=source, author_filters=author_filters):
        return []

    comment_id = str(comment.get("id") or "unknown")
    html_url = str(comment.get("html_url") or "")
    source_kind = "github_review_comment" if kind == "review" else "github_issue_comment"
    suggestions: list[SuggestionDiff] = []
    for index, match in enumerate(_CODE_SUGGESTION_FENCE_RE.finditer(body), start=1):
        diff_text = normalize_comment_suggestion(match.group(1), match.group(2), comment_path(comment))
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
                        "author_login": comment_author(comment) or None,
                        "suggestion_created_at": comment.get("created_at"),
                        "suggestion_updated_at": comment.get("updated_at"),
                        "comment_commit_sha": comment.get("commit_id"),
                        "original_commit_sha": comment.get("original_commit_id"),
                        "path": comment_path(comment),
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


_parse_github_repo = parse_github_repo
_candidate_from_github_pr_url = candidate_from_github_pr_url
_comment_author = comment_author
_matches_comment_source = matches_comment_source
_comment_path = comment_path
_normalize_comment_suggestion = normalize_comment_suggestion
_extract_comment_diff_suggestions = extract_comment_diff_suggestions
