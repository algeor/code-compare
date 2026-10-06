#!/usr/bin/env python3
"""Collect suggestion-vs-merged-diff examples from GitHub pull requests.

Compatibility facade for the decomposed collection package.
"""

from pr_suggestion_metrics.cli.collect import (
    _progress,
    _write_pairs_jsonl,
    async_main,
    main,
    parse_args,
)
from pr_suggestion_metrics.collection.contracts import (
    CandidateRow,
    CodeChangeMiss,
    DatasetSettings,
    PairedExample,
    RepoRef,
    SuggestionDiff,
)
from pr_suggestion_metrics.collection.extraction import (
    _candidate_from_github_pr_url,
    _comment_author,
    _comment_path,
    _extract_comment_diff_suggestions,
    _matches_comment_source,
    _normalize_comment_suggestion,
    _parse_github_repo,
)
from pr_suggestion_metrics.collection.github import (
    _api_base,
    _fetch_file_snapshot,
    _fetch_pr_comments,
    _fetch_pr_diff,
    _fetch_pr_json,
    _fetch_pr_review_comments,
    _github_headers,
    _github_verify_value,
    _token_for_host,
)
from pr_suggestion_metrics.collection.service import (
    _collect_pairs,
    _diff_has_renames,
    _diff_touches_config,
    _final_path_for_suggested_path,
    _load_suggestion_diffs_from_pr_comments,
    _nested_string,
)

__all__ = [
    "CandidateRow",
    "CodeChangeMiss",
    "DatasetSettings",
    "PairedExample",
    "RepoRef",
    "SuggestionDiff",
    "_api_base",
    "_candidate_from_github_pr_url",
    "_collect_pairs",
    "_comment_author",
    "_comment_path",
    "_diff_has_renames",
    "_diff_touches_config",
    "_extract_comment_diff_suggestions",
    "_fetch_file_snapshot",
    "_fetch_pr_comments",
    "_fetch_pr_diff",
    "_fetch_pr_json",
    "_fetch_pr_review_comments",
    "_final_path_for_suggested_path",
    "_github_headers",
    "_github_verify_value",
    "_load_suggestion_diffs_from_pr_comments",
    "_matches_comment_source",
    "_nested_string",
    "_normalize_comment_suggestion",
    "_parse_github_repo",
    "_progress",
    "_token_for_host",
    "_write_pairs_jsonl",
    "async_main",
    "main",
    "parse_args",
]


if __name__ == "__main__":
    raise SystemExit(main())
