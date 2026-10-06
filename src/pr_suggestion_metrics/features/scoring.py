"""Feature assembly and deterministic percentage scoring."""

from __future__ import annotations

from dataclasses import asdict

from pr_suggestion_metrics.diff.parser import DiffDialect, assess_unified_diff
from pr_suggestion_metrics.features.contracts import (
    MetricResult,
    RawDiffAssessment,
    RawDiffAssessmentStatus,
    RawDiffSource,
    ScoringExample,
    ScoringInput,
)
from pr_suggestion_metrics.features.gumtree import gumtree_features_by_file
from pr_suggestion_metrics.features.lexical import (
    calculate_best_added_line_overlap,
    calculate_line_recall,
    dominant_tokenization,
    multiset_recall,
    non_empty_normalized_lines,
    normalize_identifier_and_literal_tokens,
    normalize_identifier_tokens,
    normalize_literal_tokens,
    prepare_hunks_by_file,
    prepare_lines_by_file,
    tokenize_by_file,
)
from pr_suggestion_metrics.features.matching import (
    added_hunks_by_file_from_diff,
    added_lines_by_file_from_diff,
    calculate_best_hunk_scores,
    best_structural_scores,
)

def score_example(example: ScoringInput, *, enable_gumtree: bool) -> MetricResult:
    suggested_lines_by_file = prepare_lines_by_file(added_lines_by_file_from_diff(example.suggested_diff))
    landed_lines_by_file = prepare_lines_by_file(added_lines_by_file_from_diff(example.landed_diff))
    landed_hunks_by_file = prepare_hunks_by_file(added_hunks_by_file_from_diff(example.landed_diff))
    suggested_lines = [line for lines in suggested_lines_by_file.values() for line in lines]
    landed_lines = [line for path in suggested_lines_by_file for line in landed_lines_by_file.get(path, [])]
    landed_lines_by_suggested_file = {path: landed_lines_by_file.get(path, []) for path in suggested_lines_by_file}
    suggested_text = "\n".join(suggested_lines)
    landed_text = "\n".join(landed_lines)

    suggestion_language, tokenizer_name = dominant_tokenization(suggested_lines_by_file)
    suggested_tokens = tokenize_by_file(suggested_lines_by_file)
    landed_tokens = tokenize_by_file(landed_lines_by_suggested_file)
    identifier_normalized_suggested_tokens = normalize_identifier_tokens(suggested_tokens)
    identifier_normalized_landed_tokens = normalize_identifier_tokens(landed_tokens)
    literal_normalized_suggested_tokens = normalize_literal_tokens(suggested_tokens)
    literal_normalized_landed_tokens = normalize_literal_tokens(landed_tokens)
    identifier_and_literal_normalized_suggested_tokens = normalize_identifier_and_literal_tokens(suggested_tokens)
    identifier_and_literal_normalized_landed_tokens = normalize_identifier_and_literal_tokens(landed_tokens)

    line_recall = calculate_line_recall(suggested_lines, landed_lines)
    token_recall = multiset_recall(suggested_tokens, landed_tokens)
    identifier_normalized_token_recall = multiset_recall(
        identifier_normalized_suggested_tokens,
        identifier_normalized_landed_tokens,
    )
    literal_normalized_token_recall = multiset_recall(literal_normalized_suggested_tokens, literal_normalized_landed_tokens)
    identifier_and_literal_normalized_token_recall = multiset_recall(
        identifier_and_literal_normalized_suggested_tokens,
        identifier_and_literal_normalized_landed_tokens,
    )
    exact_normalized_match = bool(suggested_text) and suggested_text in landed_text
    best_added_line_overlap = calculate_best_added_line_overlap(suggested_lines, landed_lines)
    best_hunk_scores = calculate_best_hunk_scores(suggested_lines_by_file, landed_hunks_by_file)
    structural_scores = best_structural_scores(suggested_lines_by_file, landed_hunks_by_file)
    gumtree_features = gumtree_features_by_file(suggested_lines_by_file, landed_lines_by_file, enable_gumtree)
    predicted_percentage = _predict_percentage(
        exact_normalized_match,
        line_recall,
        token_recall,
        identifier_normalized_token_recall,
        best_added_line_overlap,
        float(best_hunk_scores["best_hunk_token_recall"]),
        float(best_hunk_scores["best_hunk_token_precision"]),
        float(best_hunk_scores["best_hunk_token_f1"]),
        float(best_hunk_scores["best_hunk_identifier_normalized_recall"]),
        float(best_hunk_scores["best_hunk_literal_normalized_recall"]),
        float(best_hunk_scores["best_hunk_identifier_and_literal_normalized_recall"]),
        float(best_hunk_scores["best_hunk_contiguous_line_ratio"]),
        float(best_hunk_scores["best_hunk_token_lcs_recall"]),
        float(best_hunk_scores["best_hunk_size_ratio"]),
        float(best_hunk_scores["meaningful_anchor_recall"]),
        int(best_hunk_scores["meaningful_anchor_count"]),
        str(best_hunk_scores["best_hunk_candidate_type"]),
        example.file_overlap_ratio,
        example.changed_line_overlap_ratio,
    )
    return MetricResult(
        exact_normalized_match=exact_normalized_match,
        suggestion_language=suggestion_language,
        tokenizer=tokenizer_name,
        line_recall=line_recall,
        token_recall=token_recall,
        identifier_normalized_token_recall=identifier_normalized_token_recall,
        literal_normalized_token_recall=literal_normalized_token_recall,
        identifier_and_literal_normalized_token_recall=identifier_and_literal_normalized_token_recall,
        best_added_line_overlap=best_added_line_overlap,
        best_hunk_token_recall=float(best_hunk_scores["best_hunk_token_recall"]),
        best_hunk_token_precision=float(best_hunk_scores["best_hunk_token_precision"]),
        best_hunk_token_f1=float(best_hunk_scores["best_hunk_token_f1"]),
        best_hunk_identifier_normalized_recall=float(best_hunk_scores["best_hunk_identifier_normalized_recall"]),
        best_hunk_literal_normalized_recall=float(best_hunk_scores["best_hunk_literal_normalized_recall"]),
        best_hunk_identifier_and_literal_normalized_recall=float(
            best_hunk_scores["best_hunk_identifier_and_literal_normalized_recall"]
        ),
        best_hunk_contiguous_line_ratio=float(best_hunk_scores["best_hunk_contiguous_line_ratio"]),
        best_hunk_token_lcs_recall=float(best_hunk_scores["best_hunk_token_lcs_recall"]),
        best_hunk_size_ratio=float(best_hunk_scores["best_hunk_size_ratio"]),
        meaningful_anchor_recall=float(best_hunk_scores["meaningful_anchor_recall"]),
        meaningful_anchor_count=int(best_hunk_scores["meaningful_anchor_count"]),
        best_hunk_size=int(best_hunk_scores["best_hunk_size"]),
        best_hunk_file=str(best_hunk_scores["best_hunk_file"]),
        best_hunk_candidate_type=str(best_hunk_scores["best_hunk_candidate_type"]),
        candidate_hunk_count=int(best_hunk_scores["candidate_hunk_count"]),
        structural_available=bool(structural_scores["available"]),
        structural_engine=str(structural_scores["engine"]),
        structural_language=str(structural_scores["language"]),
        structural_similarity=float(structural_scores["similarity"]),
        structural_node_recall=float(structural_scores["node_recall"]),
        structural_error=str(structural_scores["error"]),
        gumtree_available=bool(gumtree_features["available"]),
        gumtree_language=str(gumtree_features["language"]),
        gumtree_operation_count=int(gumtree_features["operation_count"]),
        gumtree_insert_ratio=float(gumtree_features["insert_ratio"]),
        gumtree_delete_ratio=float(gumtree_features["delete_ratio"]),
        gumtree_update_ratio=float(gumtree_features["update_ratio"]),
        gumtree_move_ratio=float(gumtree_features["move_ratio"]),
        gumtree_error=str(gumtree_features["error"]),
        file_overlap_ratio=example.file_overlap_ratio,
        changed_line_overlap_ratio=example.changed_line_overlap_ratio,
        predicted_percentage=predicted_percentage,
    )

def _suggestion_shape_support_issues(suggested_diff: str) -> list[str]:
    """Return existing suggestion-shape reasons without parser validity concerns."""
    issues: list[str] = []
    added_lines_by_file = added_lines_by_file_from_diff(suggested_diff)
    files_with_additions = [path for path, lines in added_lines_by_file.items() if non_empty_normalized_lines(lines)]
    parsed = assess_unified_diff(suggested_diff, dialect="suggestion_fragment").parsed_diff
    removed_lines = [line for line in parsed.changed_lines if line.operation == "deletion" and line.text.strip()]
    hunk_count = parsed.hunk_count

    if not suggested_diff.strip():
        issues.append("suggestion diff is empty")
    if not files_with_additions:
        issues.append("suggestion diff contains no supported added code lines")
    if removed_lines:
        issues.append("suggestion deletions and replacements are not yet supported")
    if len(files_with_additions) > 1:
        issues.append("multi-file suggestions are not yet supported by raw inference")
    if hunk_count > 1:
        issues.append("multi-hunk suggestions are not yet supported by raw inference")
    if any(file_diff.rename_from or file_diff.rename_to for file_diff in parsed.files):
        issues.append("renamed suggestion files are not yet supported")
    return issues


def assess_raw_diff(
    diff_text: str,
    *,
    source: RawDiffSource = "suggested_diff",
) -> RawDiffAssessment:
    """Assess parser validity and current feature applicability for one raw diff."""
    dialect: DiffDialect = "suggestion_fragment" if source == "suggested_diff" else "git_unified"
    parser_assessment = assess_unified_diff(diff_text, dialect=dialect)
    support_issues = (
        tuple(_suggestion_shape_support_issues(diff_text))
        if source == "suggested_diff"
        else ()
    )
    if not parser_assessment.is_valid:
        status: RawDiffAssessmentStatus = "invalid"
    elif support_issues:
        status = "valid_but_unsupported"
    else:
        status = "valid"
    return RawDiffAssessment(
        source=source,
        dialect=dialect,
        status=status,
        diagnostics=parser_assessment.diagnostics,
        support_issues=support_issues,
    )


def raw_diff_support_issues(suggested_diff: str) -> list[str]:
    """Project typed suggestion assessment reasons into the legacy list API."""
    return list(assess_raw_diff(suggested_diff).reasons)

def score_diff_pair(suggested_diff: str, merged_pr_diff: str, *, enable_gumtree: bool = False) -> MetricResult:
    """Compute deterministic model features for a supported suggestion/merged-PR diff pair."""
    suggested_assessment = assess_raw_diff(suggested_diff)
    if suggested_assessment.status != "valid":
        raise ValueError("Unsupported suggestion diff: " + "; ".join(suggested_assessment.reasons))
    merged_assessment = assess_raw_diff(merged_pr_diff, source="merged_pr_diff")
    if merged_assessment.status != "valid":
        raise ValueError("Invalid merged PR diff: " + "; ".join(merged_assessment.reasons))

    suggested_lines_by_file = added_lines_by_file_from_diff(suggested_diff)
    landed_lines_by_file = added_lines_by_file_from_diff(merged_pr_diff)
    suggested_files = set(suggested_lines_by_file)
    landed_files = set(landed_lines_by_file)
    suggested_lines = {
        (path, line.strip())
        for path, lines in suggested_lines_by_file.items()
        for line in lines
        if line.strip()
    }
    landed_lines = {
        (path, line.strip())
        for path, lines in landed_lines_by_file.items()
        for line in lines
        if line.strip()
    }
    file_overlap_ratio = len(suggested_files & landed_files) / len(suggested_files) if suggested_files else 0.0
    changed_line_overlap_ratio = len(suggested_lines & landed_lines) / len(suggested_lines) if suggested_lines else 0.0

    return score_example(
        ScoringExample(
            suggested_diff=suggested_diff,
            landed_diff=merged_pr_diff,
            file_overlap_ratio=file_overlap_ratio,
            changed_line_overlap_ratio=changed_line_overlap_ratio,
        ),
        enable_gumtree=enable_gumtree,
    )

def metric_result_to_feature_row(metric_result: MetricResult) -> dict[str, object]:
    """Convert a metric result into the model feature-row representation."""
    return asdict(metric_result)

def _predict_percentage(
    exact_normalized_match: bool,
    line_recall: float,
    token_recall: float,
    identifier_normalized_token_recall: float,
    best_added_line_overlap: float,
    best_hunk_token_recall: float,
    best_hunk_token_precision: float,
    best_hunk_token_f1: float,
    best_hunk_identifier_normalized_recall: float,
    best_hunk_literal_normalized_recall: float,
    best_hunk_identifier_and_literal_normalized_recall: float,
    best_hunk_contiguous_line_ratio: float,
    best_hunk_token_lcs_recall: float,
    best_hunk_size_ratio: float,
    meaningful_anchor_recall: float,
    meaningful_anchor_count: int,
    best_hunk_candidate_type: str,
    file_overlap_ratio: float,
    changed_line_overlap_ratio: float,
) -> int:
    if exact_normalized_match:
        return 100
    is_cross_file_candidate = best_hunk_candidate_type in {"same_extension", "anchor_overlap"}
    has_strong_same_file_evidence = (
        best_hunk_candidate_type in {"same_file", "neighboring_same_file"}
        and best_hunk_identifier_and_literal_normalized_recall >= 0.98
        and meaningful_anchor_recall >= 0.90
        and meaningful_anchor_count >= 2
        and best_hunk_token_precision >= 0.40
        and best_hunk_size_ratio >= 0.25
        and (line_recall >= 0.90 or best_added_line_overlap >= 0.90 or changed_line_overlap_ratio >= 0.90)
    )
    has_strong_cross_file_evidence = (
        is_cross_file_candidate
        and best_hunk_identifier_and_literal_normalized_recall >= 0.99
        and meaningful_anchor_recall >= 0.95
        and meaningful_anchor_count >= 4
        and best_hunk_token_precision >= 0.50
        and best_hunk_size_ratio >= 0.30
        and (line_recall >= 0.85 or best_added_line_overlap >= 0.85 or changed_line_overlap_ratio >= 0.85)
    )
    if file_overlap_ratio <= 0 and identifier_normalized_token_recall < 0.95 and not has_strong_cross_file_evidence:
        return 0
    if has_strong_same_file_evidence or has_strong_cross_file_evidence:
        return 95
    if best_hunk_token_recall == 0 and meaningful_anchor_recall == 0:
        return 0
    if _has_no_landed_line_evidence(
        line_recall,
        best_added_line_overlap,
        changed_line_overlap_ratio,
        best_hunk_contiguous_line_ratio,
        best_hunk_token_precision,
        meaningful_anchor_recall,
    ):
        return 0
    score = max(
        line_recall,
        best_added_line_overlap,
        best_hunk_token_recall * 0.80,
        best_hunk_token_precision * 0.85,
        best_hunk_token_f1 * 0.90,
        best_hunk_identifier_normalized_recall * 0.76,
        best_hunk_literal_normalized_recall * 0.72,
        best_hunk_identifier_and_literal_normalized_recall * 0.68,
        best_hunk_contiguous_line_ratio * 0.92,
        best_hunk_token_lcs_recall * 0.88,
        token_recall * 0.62,
        identifier_normalized_token_recall * 0.68,
        meaningful_anchor_recall * 0.78,
    )
    if is_cross_file_candidate:
        score = min(score, 0.80)
    if best_hunk_candidate_type in {"same_file", "neighboring_same_file"} and (
        line_recall < 0.50 and best_added_line_overlap < 0.50 and changed_line_overlap_ratio < 0.50
    ):
        score = min(score, 0.82)
    if best_hunk_size_ratio < 0.10 and best_hunk_contiguous_line_ratio < 0.50:
        score = min(score, 0.72)
    if _has_partial_evidence(
        line_recall,
        best_added_line_overlap,
        changed_line_overlap_ratio,
        best_hunk_contiguous_line_ratio,
    ):
        score = min(score, 0.55)
    return round(score * 100)

def _has_partial_evidence(
    line_recall: float,
    best_added_line_overlap: float,
    changed_line_overlap_ratio: float,
    best_hunk_contiguous_line_ratio: float,
) -> bool:
    overlap_signal = max(line_recall, best_added_line_overlap, changed_line_overlap_ratio)
    return 0.05 <= overlap_signal <= 0.60 and best_hunk_contiguous_line_ratio < 0.30

def _has_no_landed_line_evidence(
    line_recall: float,
    best_added_line_overlap: float,
    changed_line_overlap_ratio: float,
    best_hunk_contiguous_line_ratio: float,
    best_hunk_token_precision: float,
    meaningful_anchor_recall: float,
) -> bool:
    line_signal = max(line_recall, best_added_line_overlap, changed_line_overlap_ratio, best_hunk_contiguous_line_ratio)
    return line_signal == 0 and best_hunk_token_precision < 0.30 and meaningful_anchor_recall < 0.50


_score_example = score_example
