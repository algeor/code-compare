"""Lexical normalization, notebook preparation, and token-based primitives."""

from __future__ import annotations

import io
import json
import keyword
import re
import tokenize
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from pr_suggestion_metrics.features.contracts import TokenizedText

_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_STRING_LITERAL_PATTERN = re.compile(r"^(['\"])(?:(?=(\\?))\2.)*?\1$")

_NUMBER_LITERAL_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")

_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|==|!=|<=|>=|->|=>|\S")

_MAX_LCS_CELLS = 250_000

_COMMON_TOKENS = {
    "!=",
    "(",
    ")",
    ",",
    ".",
    ":",
    "=",
    "==",
    "False",
    "None",
    "True",
    "[",
    "]",
    "and",
    "as",
    "class",
    "def",
    "elif",
    "else",
    "except",
    "finally",
    "for",
    "from",
    "if",
    "import",
    "in",
    "is",
    "not",
    "or",
    "return",
    "try",
    "while",
    "with",
    "{",
    "}",
}

_LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".groovy": "groovy",
    ".hcl": "hcl",
    ".htm": "html",
    ".html": "html",
    ".ipynb": "jupyter_notebook",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".tf": "hcl",
    ".toml": "toml",
    ".xml": "xml",
}

_DOCKERFILE_NAMES = {"dockerfile", "containerfile"}

_PYGMENTS_LEXER_BY_LANGUAGE = {
    "c": "c",
    "groovy": "groovy",
    "hcl": "hcl",
    "html": "html",
    "javascript": "javascript",
    "shell": "bash",
    "typescript": "typescript",
}

def prepare_lines_by_file(lines_by_file: dict[str, list[str]]) -> dict[str, list[str]]:
    prepared_lines_by_file: dict[str, list[str]] = {}
    for path, lines in lines_by_file.items():
        prepared_lines_by_file[path] = _prepare_lines_for_path(path, lines)
    return prepared_lines_by_file

def prepare_hunks_by_file(hunks_by_file: dict[str, list[list[str]]]) -> dict[str, list[list[str]]]:
    prepared_hunks_by_file: dict[str, list[list[str]]] = {}
    for path, hunk_groups in hunks_by_file.items():
        prepared_hunks_by_file[path] = [_prepare_lines_for_path(path, hunk_lines) for hunk_lines in hunk_groups]
    return prepared_hunks_by_file

def _prepare_lines_for_path(path: str, lines: list[str]) -> list[str]:
    if _is_notebook_path(path):
        notebook_lines = _extract_notebook_code_lines(lines)
        if notebook_lines:
            return _non_empty_normalized_lines(notebook_lines)
    return _non_empty_normalized_lines(lines)

def _is_notebook_path(path: str) -> bool:
    return Path(path).suffix.lower() == ".ipynb"

def _extract_notebook_code_lines(raw_lines: list[str]) -> list[str]:
    notebook_text = "\n".join(raw_lines)
    json_lines = _extract_notebook_code_lines_from_json(notebook_text)
    if json_lines:
        return json_lines
    return _extract_notebook_code_lines_from_diff_lines(raw_lines)

def _extract_notebook_code_lines_from_json(notebook_text: str) -> list[str]:
    try:
        notebook = json.loads(notebook_text)
    except json.JSONDecodeError:
        return []
    if not isinstance(notebook, dict):
        return []

    code_lines: list[str] = []
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        return []
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        code_lines.extend(_notebook_source_to_lines(cell.get("source")))
    return code_lines

def _notebook_source_to_lines(source: object) -> list[str]:
    if isinstance(source, str):
        return source.splitlines()
    if isinstance(source, list):
        lines: list[str] = []
        for item in source:
            if isinstance(item, str):
                lines.extend(item.splitlines())
        return lines
    return []

def _extract_notebook_code_lines_from_diff_lines(raw_lines: list[str]) -> list[str]:
    code_lines: list[str] = []
    in_source_array = False

    for raw_line in raw_lines:
        stripped_line = raw_line.strip()
        if not stripped_line:
            continue
        if stripped_line.startswith('"source":'):
            code_lines.extend(_decode_notebook_source_line(stripped_line.removeprefix('"source":').strip()))
            in_source_array = "[" in stripped_line and "]" not in stripped_line
            continue
        if in_source_array:
            if stripped_line.startswith("]"):
                in_source_array = False
                continue
            code_lines.extend(_decode_notebook_source_line(stripped_line))

    return code_lines

def _decode_notebook_source_line(raw_value: str) -> list[str]:
    cleaned_value = raw_value.rstrip(",")
    if cleaned_value.startswith("["):
        cleaned_value = cleaned_value.removeprefix("[").strip()
    if cleaned_value.endswith("]"):
        cleaned_value = cleaned_value.removesuffix("]").strip()
    if not cleaned_value:
        return []

    try:
        decoded_value = json.loads(cleaned_value)
    except json.JSONDecodeError:
        return []
    return _notebook_source_to_lines(decoded_value)

def _normalize_line(line: str) -> str:
    return " ".join(line.strip().split())

def non_empty_normalized_lines(lines: Iterable[str]) -> list[str]:
    return [normalized_line for line in lines if (normalized_line := _normalize_line(line))]

def calculate_line_recall(suggested_lines: list[str], landed_lines: list[str]) -> float:
    if not suggested_lines:
        return 0.0
    landed_counts = Counter(landed_lines)
    matched_count = 0
    for suggested_line in suggested_lines:
        if landed_counts[suggested_line] <= 0:
            continue
        matched_count += 1
        landed_counts[suggested_line] -= 1
    return matched_count / len(suggested_lines)

def tokenize_for_path(path: str, text: str) -> TokenizedText:
    language = _language_for_tokenization(path)
    if language == "python":
        return TokenizedText(language=language, tokenizer="python", tokens=_python_tokens(text))
    if language == "jupyter_notebook":
        return TokenizedText(language=language, tokenizer="notebook_python", tokens=_python_tokens(text))
    if language == "json":
        return TokenizedText(language=language, tokenizer="json", tokens=_json_tokens(text))
    if language == "yaml":
        return TokenizedText(language=language, tokenizer="yaml_like", tokens=_yaml_like_tokens(text))
    if language == "markdown":
        return TokenizedText(language=language, tokenizer="markdown", tokens=_markdown_tokens(text))
    if language == "dockerfile":
        return TokenizedText(language=language, tokenizer="dockerfile", tokens=_dockerfile_tokens(text))
    pygments_tokens = _pygments_tokens_for_path(path, text)
    if pygments_tokens:
        return TokenizedText(language=language, tokenizer="pygments", tokens=pygments_tokens)
    return TokenizedText(language=language, tokenizer="regex", tokens=_regex_code_tokens(text))

def language_for_tokenization(path: str) -> str:
    normalized_path = Path(path)
    if normalized_path.name.lower() in _DOCKERFILE_NAMES:
        return "dockerfile"
    if normalized_path.name == "Jenkinsfile":
        return "groovy"
    return _LANGUAGE_BY_EXTENSION.get(normalized_path.suffix.lower(), "text")

def tokenize_by_file(lines_by_file: dict[str, list[str]]) -> list[str]:
    tokens: list[str] = []
    for path, lines in lines_by_file.items():
        tokens.extend(_tokenize_for_path(path, "\n".join(lines)).tokens)
    return tokens

def dominant_tokenization(lines_by_file: dict[str, list[str]]) -> tuple[str, str]:
    if not lines_by_file:
        return "text", "regex"
    path, lines = max(lines_by_file.items(), key=lambda item: len(item[1]))
    tokenized_text = _tokenize_for_path(path, "\n".join(lines))
    return tokenized_text.language, tokenized_text.tokenizer

def _python_tokens(text: str) -> list[str]:
    try:
        return [
            token.string
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type
            not in {
                tokenize.ENCODING,
                tokenize.ENDMARKER,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.NEWLINE,
                tokenize.NL,
                tokenize.COMMENT,
            }
        ]
    except tokenize.TokenError:
        return _regex_code_tokens(text)

def _regex_code_tokens(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text)

def _pygments_tokens_for_path(path: str, text: str) -> list[str]:
    try:
        from pygments import lex  # type: ignore[import-not-found]
        from pygments.lexers import get_lexer_by_name  # type: ignore[import-not-found]
        from pygments.lexers import get_lexer_for_filename  # type: ignore[import-not-found]
        from pygments.token import Comment, Error, Text, Whitespace  # type: ignore[import-not-found]
        from pygments.util import ClassNotFound  # type: ignore[import-not-found]
    except ImportError:
        return []

    try:
        lexer = get_lexer_for_filename(path, stripnl=False)
    except ClassNotFound:
        lexer_alias = _PYGMENTS_LEXER_BY_LANGUAGE.get(_language_for_tokenization(path))
        if lexer_alias is None:
            return []
        try:
            lexer = get_lexer_by_name(lexer_alias, stripnl=False)
        except ClassNotFound:
            return []

    tokens: list[str] = []
    for token_type, token_value in lex(text, lexer):
        if token_type in Comment or token_type in Whitespace or token_type in Text or token_type in Error:
            continue
        stripped_value = token_value.strip()
        if not stripped_value:
            continue
        tokens.extend(_TOKEN_PATTERN.findall(stripped_value))
    return tokens

def _json_tokens(text: str) -> list[str]:
    try:
        parsed_value = json.loads(text)
    except json.JSONDecodeError:
        return _regex_code_tokens(text)

    tokens: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                tokens.extend(_TOKEN_PATTERN.findall(str(key)))
                collect(nested_value)
            return
        if isinstance(value, list):
            for nested_value in value:
                collect(nested_value)
            return
        if value is None:
            tokens.append("null")
            return
        if isinstance(value, bool):
            tokens.append(str(value).lower())
            return
        tokens.extend(_TOKEN_PATTERN.findall(str(value)))

    collect(parsed_value)
    return tokens

def _yaml_like_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for line in text.splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        key_match = re.match(r"^-?\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*:", stripped_line)
        if key_match:
            tokens.extend(_TOKEN_PATTERN.findall(key_match.group(1)))
        tokens.extend(_TOKEN_PATTERN.findall(stripped_line))
    return tokens

def _markdown_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    in_fenced_code_block = False
    for line in text.splitlines():
        stripped_line = line.strip()
        if stripped_line.startswith("```") or stripped_line.startswith("~~~"):
            in_fenced_code_block = not in_fenced_code_block
            continue
        if in_fenced_code_block:
            tokens.extend(_regex_code_tokens(line))
            continue
        tokens.extend(_TOKEN_PATTERN.findall(stripped_line.lstrip("#>-* ")))
    return tokens

def _dockerfile_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for line in text.splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        instruction, _, arguments = stripped_line.partition(" ")
        tokens.append(instruction.upper())
        tokens.extend(_TOKEN_PATTERN.findall(arguments))
    return tokens

def normalize_identifier_tokens(tokens: Iterable[str]) -> list[str]:
    return ["IDENT" if _is_identifier(token) else token for token in tokens]

def normalize_literal_tokens(tokens: Iterable[str]) -> list[str]:
    return ["LITERAL" if _is_literal(token) else token for token in tokens]

def normalize_identifier_and_literal_tokens(tokens: Iterable[str]) -> list[str]:
    return ["IDENT" if _is_identifier(token) else "LITERAL" if _is_literal(token) else token for token in tokens]

def _is_identifier(token: str) -> bool:
    return bool(_IDENTIFIER_PATTERN.fullmatch(token)) and not keyword.iskeyword(token)

def _is_literal(token: str) -> bool:
    return (
        bool(_STRING_LITERAL_PATTERN.fullmatch(token))
        or bool(_NUMBER_LITERAL_PATTERN.fullmatch(token))
        or token in {"true", "false", "null", "True", "False", "None"}
    )

def multiset_recall(suggested_items: list[str], landed_items: list[str]) -> float:
    if not suggested_items:
        return 0.0
    landed_counts = Counter(landed_items)
    matched_count = 0
    for item in suggested_items:
        if landed_counts[item] <= 0:
            continue
        matched_count += 1
        landed_counts[item] -= 1
    return matched_count / len(suggested_items)

def multiset_precision(suggested_items: list[str], landed_items: list[str]) -> float:
    if not landed_items:
        return 0.0
    suggested_counts = Counter(suggested_items)
    matched_count = 0
    for item in landed_items:
        if suggested_counts[item] <= 0:
            continue
        matched_count += 1
        suggested_counts[item] -= 1
    return matched_count / len(landed_items)

def f1_score(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)

def longest_common_contiguous_ratio(suggested_lines: list[str], landed_lines: list[str]) -> float:
    if not suggested_lines or not landed_lines:
        return 0.0

    previous_row = [0] * (len(landed_lines) + 1)
    best_length = 0
    for suggested_line in suggested_lines:
        current_row = [0] * (len(landed_lines) + 1)
        for index, landed_line in enumerate(landed_lines, start=1):
            if suggested_line != landed_line:
                continue
            current_row[index] = previous_row[index - 1] + 1
            best_length = max(best_length, current_row[index])
        previous_row = current_row
    return best_length / len(suggested_lines)

def lcs_recall(suggested_items: list[str], landed_items: list[str]) -> float:
    if not suggested_items or not landed_items:
        return 0.0
    if len(suggested_items) * len(landed_items) > _MAX_LCS_CELLS:
        return 0.0

    previous_row = [0] * (len(landed_items) + 1)
    for suggested_item in suggested_items:
        current_row = [0] * (len(landed_items) + 1)
        for index, landed_item in enumerate(landed_items, start=1):
            if suggested_item == landed_item:
                current_row[index] = previous_row[index - 1] + 1
            else:
                current_row[index] = max(previous_row[index], current_row[index - 1])
        previous_row = current_row
    return previous_row[-1] / len(suggested_items)

def calculate_size_ratio(suggested_line_count: int, candidate_line_count: int) -> float:
    if suggested_line_count <= 0 or candidate_line_count <= 0:
        return 0.0
    return min(suggested_line_count, candidate_line_count) / max(suggested_line_count, candidate_line_count)

def meaningful_anchors_for_path(path: str, text: str) -> list[str]:
    anchors: list[str] = []
    for token in _tokenize_for_path(path, text).tokens:
        if token in _COMMON_TOKENS:
            continue
        if len(token) <= 2 and not token.isdigit():
            continue
        if _is_identifier(token) or _STRING_LITERAL_PATTERN.fullmatch(token) or token.isdigit():
            anchors.append(token)
    return anchors

def _anchor_recall(path: str, suggestion_text: str, candidate_text: str) -> float:
    return _multiset_recall(_meaningful_anchors_for_path(path, suggestion_text), _meaningful_anchors_for_path(path, candidate_text))

def cross_path_anchor_recall(
    suggestion_path: str,
    suggestion_text: str,
    candidate_path: str,
    candidate_text: str,
) -> float:
    return _multiset_recall(
        _meaningful_anchors_for_path(suggestion_path, suggestion_text),
        _meaningful_anchors_for_path(candidate_path, candidate_text),
    )

def calculate_best_added_line_overlap(suggested_lines: list[str], landed_lines: list[str]) -> float:
    if not suggested_lines or not landed_lines:
        return 0.0
    window_size = len(suggested_lines)
    if len(landed_lines) <= window_size:
        return _line_recall(suggested_lines, landed_lines)
    return max(_line_recall(suggested_lines, landed_lines[index : index + window_size]) for index in range(len(landed_lines)))

def _normalize_lines_by_file(lines_by_file: dict[str, list[str]]) -> dict[str, list[str]]:
    return {path: _non_empty_normalized_lines(lines) for path, lines in lines_by_file.items()}


_prepare_lines_by_file = prepare_lines_by_file
_prepare_hunks_by_file = prepare_hunks_by_file
_non_empty_normalized_lines = non_empty_normalized_lines
_line_recall = calculate_line_recall
_tokenize_for_path = tokenize_for_path
_language_for_tokenization = language_for_tokenization
_tokenize_by_file = tokenize_by_file
_dominant_tokenization = dominant_tokenization
_normalize_identifier_tokens = normalize_identifier_tokens
_normalize_literal_tokens = normalize_literal_tokens
_normalize_identifier_and_literal_tokens = normalize_identifier_and_literal_tokens
_multiset_recall = multiset_recall
_multiset_precision = multiset_precision
_f1_score = f1_score
_longest_common_contiguous_ratio = longest_common_contiguous_ratio
_lcs_recall = lcs_recall
_size_ratio = calculate_size_ratio
_meaningful_anchors_for_path = meaningful_anchors_for_path
_cross_path_anchor_recall = cross_path_anchor_recall
_best_added_line_overlap = calculate_best_added_line_overlap
