"""CLI orchestration for GitHub suggestion collection."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from pr_suggestion_metrics.artifact_io import write_jsonl_object_lines
from pr_suggestion_metrics.collection.contracts import PairedExample
from pr_suggestion_metrics.collection.extraction import candidate_from_github_pr_url
from pr_suggestion_metrics.collection.service import collect_pairs, load_suggestion_diffs_from_pr_comments

_DESCRIPTION = "Collect suggestion-vs-merged-diff examples from GitHub pull requests."


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=_DESCRIPTION)
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


def progress(message: str) -> None:
    """Print a progress message immediately to stderr."""
    print(message, file=sys.stderr, flush=True)


def write_pairs_jsonl(pairs: list[PairedExample], output: Path | None) -> None:
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
    progress("GitHub: loading direct PR candidates")
    candidates = [candidate_from_github_pr_url(url) for url in args.github_pr_url]
    progress(f"GitHub: loaded {len(candidates)} direct PR candidate(s)")

    progress("GitHub: loading suggestion diffs from PR comments")
    suggestions, suggestion_misses = await load_suggestion_diffs_from_pr_comments(
        candidates,
        github_token=args.github_token,
        source=args.comment_source,
        author_filters=args.comment_author_contains,
        review_comments_only=args.review_comments_only,
        github_concurrency=args.github_concurrency,
        progress=progress,
    )
    progress(f"GitHub: loaded {len(suggestions)} comment suggestion diff(s), misses={len(suggestion_misses)}")

    progress("GitHub: fetching merged PR diffs")
    pairs, github_misses = await collect_pairs(
        suggestions,
        github_token=args.github_token,
        include_unmerged_prs=args.include_unmerged_prs,
        progress=progress,
    )
    progress(f"GitHub: collected {len(pairs)} pair(s), misses={len(github_misses)}")
    write_pairs_jsonl(pairs, args.output)
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


_progress = progress
_write_pairs_jsonl = write_pairs_jsonl
