"""Diff hunk extraction, candidate matching, and structural score selection."""

from __future__ import annotations

from pathlib import Path

from pr_suggestion_metrics.diff.parser import parse_unified_diff
from pr_suggestion_metrics.features.contracts import CandidateHunk
from pr_suggestion_metrics.features.lexical import (
    cross_path_anchor_recall,
    f1_score,
    language_for_tokenization,
    lcs_recall,
    longest_common_contiguous_ratio,
    meaningful_anchors_for_path,
    multiset_precision,
    multiset_recall,
    non_empty_normalized_lines,
    normalize_identifier_and_literal_tokens,
    normalize_identifier_tokens,
    normalize_literal_tokens,
    calculate_size_ratio,
    tokenize_for_path,
)
from pr_suggestion_metrics.features.structural import structural_node_types, supports_structural_language

def added_lines_by_file_from_diff(diff_text: str) -> dict[str, list[str]]:
    added_lines_by_file: dict[str, list[str]] = {}
    for line in parse_unified_diff(diff_text).changed_lines:
        if line.operation == "addition" and line.path is not None:
            added_lines_by_file.setdefault(line.path, []).append(line.text)
    return added_lines_by_file

def added_hunks_by_file_from_diff(diff_text: str) -> dict[str, list[list[str]]]:
    added_hunks_by_file: dict[str, list[list[str]]] = {}
    for file_diff in parse_unified_diff(diff_text).files:
        hunks: dict[int, list[str]] = {}
        for line in file_diff.lines:
            if line.operation == "addition" and line.path is not None:
                hunks.setdefault(line.hunk_index, []).append(line.text)
        for hunk_index in sorted(hunks):
            path = file_diff.new_path or file_diff.old_path
            if path is not None:
                added_hunks_by_file.setdefault(path, []).append(hunks[hunk_index])
    return added_hunks_by_file

def _candidate_hunks_for_suggestion(
    suggestion_path: str,
    suggestion_text: str,
    landed_hunks_by_file: dict[str, list[list[str]]],
) -> list[CandidateHunk]:
    candidates: list[CandidateHunk] = []
    seen_candidates: set[tuple[str, str, tuple[str, ...]]] = set()

    def add_candidate(path: str, lines: list[str], candidate_type: str) -> None:
        normalized_lines = non_empty_normalized_lines(lines)
        if not normalized_lines:
            return
        key = (path, candidate_type, tuple(normalized_lines))
        if key in seen_candidates:
            return
        seen_candidates.add(key)
        candidates.append(CandidateHunk(path=path, lines=normalized_lines, candidate_type=candidate_type))

    same_file_hunks = landed_hunks_by_file.get(suggestion_path, [])
    for hunk_lines in same_file_hunks:
        add_candidate(suggestion_path, hunk_lines, "same_file")

    for index in range(len(same_file_hunks) - 1):
        add_candidate(suggestion_path, same_file_hunks[index] + same_file_hunks[index + 1], "neighboring_same_file")

    suggestion_suffix = Path(suggestion_path).suffix.lower()
    for candidate_path, hunk_groups in landed_hunks_by_file.items():
        if candidate_path == suggestion_path:
            continue
        candidate_suffix = Path(candidate_path).suffix.lower()
        for hunk_lines in hunk_groups:
            hunk_text = "\n".join(non_empty_normalized_lines(hunk_lines))
            if suggestion_suffix and suggestion_suffix == candidate_suffix:
                add_candidate(candidate_path, hunk_lines, "same_extension")
                continue
            anchor_recall = cross_path_anchor_recall(suggestion_path, suggestion_text, candidate_path, hunk_text)
            if anchor_recall >= 0.30:
                add_candidate(candidate_path, hunk_lines, "anchor_overlap")

    return candidates

def calculate_best_hunk_scores(
    suggested_lines_by_file: dict[str, list[str]],
    landed_hunks_by_file: dict[str, list[list[str]]],
) -> dict[str, float | int | str]:
    best_score = 0.0
    best_hunk_scores: dict[str, float | int | str] = {
        "best_hunk_token_recall": 0.0,
        "best_hunk_token_precision": 0.0,
        "best_hunk_token_f1": 0.0,
        "best_hunk_identifier_normalized_recall": 0.0,
        "best_hunk_literal_normalized_recall": 0.0,
        "best_hunk_identifier_and_literal_normalized_recall": 0.0,
        "best_hunk_contiguous_line_ratio": 0.0,
        "best_hunk_token_lcs_recall": 0.0,
        "best_hunk_size_ratio": 0.0,
        "meaningful_anchor_recall": 0.0,
        "meaningful_anchor_count": 0,
        "best_hunk_size": 0,
        "best_hunk_file": "",
        "best_hunk_candidate_type": "",
        "candidate_hunk_count": 0,
    }
    candidate_hunk_count = 0

    for path, suggested_lines in suggested_lines_by_file.items():
        suggestion_text = "\n".join(suggested_lines)
        suggestion_tokens = tokenize_for_path(path, suggestion_text).tokens
        normalized_suggestion_tokens = normalize_identifier_tokens(suggestion_tokens)
        literal_normalized_suggestion_tokens = normalize_literal_tokens(suggestion_tokens)
        identifier_and_literal_normalized_suggestion_tokens = normalize_identifier_and_literal_tokens(suggestion_tokens)
        anchor_count = len(meaningful_anchors_for_path(path, suggestion_text))

        for candidate_hunk in _candidate_hunks_for_suggestion(path, suggestion_text, landed_hunks_by_file):
            candidate_hunk_count += 1
            normalized_hunk_lines = candidate_hunk.lines
            hunk_text = "\n".join(normalized_hunk_lines)
            hunk_tokens = tokenize_for_path(candidate_hunk.path, hunk_text).tokens
            normalized_hunk_tokens = normalize_identifier_tokens(hunk_tokens)
            literal_normalized_hunk_tokens = normalize_literal_tokens(hunk_tokens)
            identifier_and_literal_normalized_hunk_tokens = normalize_identifier_and_literal_tokens(hunk_tokens)
            token_recall = multiset_recall(suggestion_tokens, hunk_tokens)
            token_precision = multiset_precision(suggestion_tokens, hunk_tokens)
            token_f1 = f1_score(token_precision, token_recall)
            identifier_normalized_recall = multiset_recall(normalized_suggestion_tokens, normalized_hunk_tokens)
            literal_normalized_recall = multiset_recall(literal_normalized_suggestion_tokens, literal_normalized_hunk_tokens)
            identifier_and_literal_normalized_recall = multiset_recall(
                identifier_and_literal_normalized_suggestion_tokens,
                identifier_and_literal_normalized_hunk_tokens,
            )
            anchor_recall = cross_path_anchor_recall(path, suggestion_text, candidate_hunk.path, hunk_text)
            contiguous_line_ratio = longest_common_contiguous_ratio(suggested_lines, normalized_hunk_lines)
            token_lcs_recall = lcs_recall(
                identifier_and_literal_normalized_suggestion_tokens,
                identifier_and_literal_normalized_hunk_tokens,
            )
            size_ratio = calculate_size_ratio(len(suggested_lines), len(normalized_hunk_lines))
            score = max(
                token_recall,
                token_f1,
                identifier_normalized_recall * 0.95,
                literal_normalized_recall * 0.9,
                identifier_and_literal_normalized_recall * 0.85,
                contiguous_line_ratio,
                token_lcs_recall * 0.95,
                anchor_recall,
            )
            if score <= best_score:
                continue
            best_score = score
            best_hunk_scores = {
                "best_hunk_token_recall": token_recall,
                "best_hunk_token_precision": token_precision,
                "best_hunk_token_f1": token_f1,
                "best_hunk_identifier_normalized_recall": identifier_normalized_recall,
                "best_hunk_literal_normalized_recall": literal_normalized_recall,
                "best_hunk_identifier_and_literal_normalized_recall": identifier_and_literal_normalized_recall,
                "best_hunk_contiguous_line_ratio": contiguous_line_ratio,
                "best_hunk_token_lcs_recall": token_lcs_recall,
                "best_hunk_size_ratio": size_ratio,
                "meaningful_anchor_recall": anchor_recall,
                "meaningful_anchor_count": anchor_count,
                "best_hunk_size": len(normalized_hunk_lines),
                "best_hunk_file": candidate_hunk.path,
                "best_hunk_candidate_type": candidate_hunk.candidate_type,
                "candidate_hunk_count": candidate_hunk_count,
            }

    best_hunk_scores["candidate_hunk_count"] = candidate_hunk_count
    return best_hunk_scores

def best_structural_scores(
    suggested_lines_by_file: dict[str, list[str]],
    landed_hunks_by_file: dict[str, list[list[str]]],
) -> dict[str, bool | float | str]:
    best_scores: dict[str, bool | float | str] = {
        "available": False,
        "engine": "",
        "language": "",
        "similarity": 0.0,
        "node_recall": 0.0,
        "error": "no supported local structural parser",
    }
    best_score = 0.0

    for path, suggested_lines in suggested_lines_by_file.items():
        language = language_for_tokenization(path)
        structural_language = _structural_language_for_tokenization(language)
        if not supports_structural_language(structural_language):
            continue

        suggestion_text = "\n".join(suggested_lines)
        suggestion_nodes, suggestion_error, engine = structural_node_types(structural_language, suggestion_text)
        if suggestion_error:
            best_scores = {
                "available": False,
                "engine": engine,
                "language": structural_language,
                "similarity": 0.0,
                "node_recall": 0.0,
                "error": suggestion_error,
            }
            continue

        for candidate_hunk in _candidate_hunks_for_suggestion(path, suggestion_text, landed_hunks_by_file):
            candidate_language = language_for_tokenization(candidate_hunk.path)
            if _structural_language_for_tokenization(candidate_language) != structural_language:
                continue
            hunk_text = "\n".join(candidate_hunk.lines)
            hunk_nodes, hunk_error, _ = structural_node_types(structural_language, hunk_text)
            if hunk_error:
                continue
            node_recall = multiset_recall(suggestion_nodes, hunk_nodes)
            if node_recall <= best_score:
                continue
            best_score = node_recall
            best_scores = {
                "available": True,
                "engine": engine,
                "language": structural_language,
                "similarity": node_recall,
                "node_recall": node_recall,
                "error": "",
            }

    return best_scores

def _structural_language_for_tokenization(language: str) -> str:
    if language == "jupyter_notebook":
        return "python"
    return language


_added_lines_by_file_from_diff = added_lines_by_file_from_diff
_added_hunks_by_file_from_diff = added_hunks_by_file_from_diff
_best_hunk_scores = calculate_best_hunk_scores
_best_structural_scores = best_structural_scores
