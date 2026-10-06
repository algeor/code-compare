"""Optional local structural parsing for deterministic features."""

from __future__ import annotations

import ast
from typing import Any

from pr_suggestion_metrics._paths import REPOSITORY_ROOT as _REPOSITORY_ROOT


_TREE_SITTER_PARSERS: dict[str, Any] = {}
_TREE_SITTER_UNAVAILABLE_REASONS: dict[str, str] = {}
_TREE_SITTER_LANGUAGES = {"c", "cpp", "go", "html", "java", "javascript", "rust", "typescript"}

__all__ = ["structural_node_types"]


def supports_structural_language(language: str) -> bool:
    """Return whether a local structural parser is supported for a language."""
    return language == "python" or language in _TREE_SITTER_LANGUAGES


def structural_node_types(language: str, text: str) -> tuple[list[str], str, str]:
    """Return structural node types, an error, and the parser engine used."""
    if language == "python":
        nodes, error = _python_ast_node_types(text)
        return nodes, error, "python_ast"
    if language in _TREE_SITTER_LANGUAGES:
        nodes, error = _tree_sitter_node_types(language, text)
        return nodes, error, "tree_sitter"
    return [], "no supported local structural parser", ""


def _tree_sitter_node_types(language: str, text: str) -> tuple[list[str], str]:
    if not text.strip():
        return [], "empty snippet"
    if language in _TREE_SITTER_UNAVAILABLE_REASONS:
        return [], _TREE_SITTER_UNAVAILABLE_REASONS[language]

    try:
        parser = _tree_sitter_parser(language)
        tree = parser.parse(text.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - optional structural metric should not fail evaluation.
        error = f"{type(exc).__name__}: {exc}"
        _TREE_SITTER_UNAVAILABLE_REASONS[language] = error
        return [], error

    node_types: list[str] = []
    nodes_to_visit = [tree.root_node]
    while nodes_to_visit:
        node = nodes_to_visit.pop()
        if node.is_named:
            node_types.append(node.type)
        nodes_to_visit.extend(reversed(node.children))

    if not node_types:
        return [], "no structural nodes found"
    return node_types, ""


def _tree_sitter_parser(language: str) -> Any:
    if language in _TREE_SITTER_PARSERS:
        return _TREE_SITTER_PARSERS[language]

    from tree_sitter_language_pack import PackConfig, configure, get_parser  # type: ignore[import-not-found]

    cache_dir = _REPOSITORY_ROOT / ".tree-sitter-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    configure(PackConfig(cache_dir=str(cache_dir), languages=sorted(_TREE_SITTER_LANGUAGES | {"python"})))
    parser = get_parser(language)
    _TREE_SITTER_PARSERS[language] = parser
    return parser


def _python_ast_node_types(text: str) -> tuple[list[str], str]:
    if not text.strip():
        return [], "empty snippet"

    parse_attempts = [text, "if True:\n" + _indent_block(text), "def _snippet():\n" + _indent_block(text)]
    last_error = ""
    for candidate_text in parse_attempts:
        node_types, parse_error = _parse_python_ast_node_types(candidate_text)
        if node_types:
            return node_types, ""
        last_error = parse_error

    fragment_nodes: list[str] = []
    for line in text.splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        for candidate_text in _python_fragment_parse_attempts(stripped_line):
            node_types, _ = _parse_python_ast_node_types(candidate_text)
            if node_types:
                fragment_nodes.extend(node_types)
                break

    if fragment_nodes:
        return fragment_nodes, ""
    return [], last_error or "could not parse Python snippet"


def _parse_python_ast_node_types(text: str) -> tuple[list[str], str]:
    try:
        parsed_tree = ast.parse(text)
    except SyntaxError as exc:
        return [], f"SyntaxError: {exc.msg}"
    node_types = [type(node).__name__ for node in ast.walk(parsed_tree) if not isinstance(node, ast.Load | ast.Store | ast.Del)]
    return node_types, ""


def _python_fragment_parse_attempts(stripped_line: str) -> list[str]:
    attempts = [stripped_line]
    if stripped_line.endswith(":"):
        if stripped_line.startswith(("elif ", "else:", "except", "finally:")):
            attempts.append("if True:\n    pass")
        else:
            attempts.append(stripped_line + "\n    pass")
    attempts.extend([
        "if True:\n    " + stripped_line,
        "def _snippet():\n    " + stripped_line,
    ])
    return attempts


def _indent_block(text: str) -> str:
    return "\n".join(f"    {line}" if line.strip() else line for line in text.splitlines())
