"""Optional GumTree edit-script feature adapter and availability cache."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

_GUMTREE_UNAVAILABLE_REASON: str | None = None

_GUMTREE_LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".java": "java",
    ".js": "js",
    ".jsx": "js",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
}

def gumtree_features_by_file(
    suggested_lines_by_file: dict[str, list[str]],
    landed_lines_by_file: dict[str, list[str]],
    enable_gumtree: bool,
) -> dict[str, bool | float | int | str]:
    if not enable_gumtree:
        return _empty_gumtree_features("disabled")

    best_features: dict[str, bool | float | int | str] | None = None
    for path, suggested_lines in suggested_lines_by_file.items():
        landed_lines = landed_lines_by_file.get(path)
        if not landed_lines:
            continue
        language = _gumtree_language_for_path(path)
        if language is None:
            continue
        candidate_features = _gumtree_features("\n".join(suggested_lines), "\n".join(landed_lines), language)
        if not candidate_features["available"]:
            return candidate_features
        if best_features is None or int(candidate_features["operation_count"]) < int(best_features["operation_count"]):
            best_features = candidate_features

    if best_features is None:
        return _empty_gumtree_features("no supported overlapping source file")
    return best_features

def _gumtree_language_for_path(path: str) -> str | None:
    return _GUMTREE_LANGUAGE_BY_EXTENSION.get(Path(path).suffix.lower())

def _gumtree_features(suggested_text: str, landed_text: str, language: str) -> dict[str, bool | float | int | str]:
    global _GUMTREE_UNAVAILABLE_REASON  # noqa: PLW0603 - cache optional dependency setup failures for this run.

    if _GUMTREE_UNAVAILABLE_REASON is not None:
        return _empty_gumtree_features(_GUMTREE_UNAVAILABLE_REASON)
    if not suggested_text.strip() or not landed_text.strip():
        return _empty_gumtree_features("empty code snippet")

    try:
        from code_diff import compute_edit_script, parse_ast  # type: ignore[import-not-found]
    except ImportError as exc:
        _GUMTREE_UNAVAILABLE_REASON = f"code-diff unavailable: {exc}"
        return _empty_gumtree_features(_GUMTREE_UNAVAILABLE_REASON)

    try:
        source_ast = parse_ast(suggested_text, lang=language)
        target_ast = parse_ast(landed_text, lang=language)
        edit_script = compute_edit_script(source_ast, target_ast)
    except Exception as exc:  # noqa: BLE001 - optional metric should not fail the full evaluation.
        error = f"{type(exc).__name__}: {exc}"
        if "tree-sitter" in error or "github.com" in error:
            _GUMTREE_UNAVAILABLE_REASON = error
        return _empty_gumtree_features(error)

    operation_count = len(edit_script)
    operation_counts = Counter(type(operation).__name__.lower() for operation in edit_script)
    if operation_count == 0:
        return {
            "available": True,
            "language": language,
            "operation_count": 0,
            "insert_ratio": 0.0,
            "delete_ratio": 0.0,
            "update_ratio": 0.0,
            "move_ratio": 0.0,
            "error": "",
        }
    return {
        "available": True,
        "language": language,
        "operation_count": operation_count,
        "insert_ratio": operation_counts["insert"] / operation_count,
        "delete_ratio": operation_counts["delete"] / operation_count,
        "update_ratio": operation_counts["update"] / operation_count,
        "move_ratio": operation_counts["move"] / operation_count,
        "error": "",
    }

def _empty_gumtree_features(error: str) -> dict[str, bool | float | int | str]:
    return {
        "available": False,
        "language": "",
        "operation_count": 0,
        "insert_ratio": 0.0,
        "delete_ratio": 0.0,
        "update_ratio": 0.0,
        "move_ratio": 0.0,
        "error": error,
    }


_gumtree_features_by_file = gumtree_features_by_file
