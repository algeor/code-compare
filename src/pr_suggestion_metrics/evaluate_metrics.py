"""Evaluate PR suggestion coverage metrics against labeled examples."""

from __future__ import annotations

import argparse
import ast
import csv
import io
import json
import keyword
import re
import tokenize
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


Label = Literal["0%", "partial", "mostly", "100%"]
PercentageBucket = Literal[
    "0",
    "1-10",
    "11-20",
    "21-30",
    "31-40",
    "41-50",
    "51-60",
    "61-70",
    "71-80",
    "81-90",
    "91-100",
    "100",
]

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATASET_DIR = _REPOSITORY_ROOT / "data" / "processed" / "pr_suggestion_coverage" / "dataset"
_DEFAULT_OUTPUT_PATH = _REPOSITORY_ROOT / "reports" / "pr_suggestion_metric_scores.csv"
_LABELS: tuple[Label, ...] = ("0%", "partial", "mostly", "100%")
_PERCENTAGE_BUCKETS: tuple[PercentageBucket, ...] = (
    "0",
    "1-10",
    "11-20",
    "21-30",
    "31-40",
    "41-50",
    "51-60",
    "61-70",
    "71-80",
    "81-90",
    "91-100",
    "100",
)
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STRING_LITERAL_PATTERN = re.compile(r"^(['\"])(?:(?=(\\?))\2.)*?\1$")
_NUMBER_LITERAL_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|==|!=|<=|>=|->|=>|\S")
_MAX_LCS_CELLS = 250_000
_GUMTREE_UNAVAILABLE_REASON: str | None = None
_TREE_SITTER_PARSERS: dict[str, object] = {}
_TREE_SITTER_UNAVAILABLE_REASONS: dict[str, str] = {}
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
_GUMTREE_LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".java": "java",
    ".js": "js",
    ".jsx": "js",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
}
_TREE_SITTER_LANGUAGES = {"c", "cpp", "go", "html", "java", "javascript", "rust", "typescript"}
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


@dataclass(frozen=True)
class DatasetExample:
    """One suggestion/landed-diff pair from dataset.jsonl."""

    example_id: str
    suggested_diff: str
    landed_diff: str


@dataclass(frozen=True)
class LabeledExample:
    """One joined dataset row with human label and baseline estimates."""

    example_id: str
    label: Label
    expected_landed_percentage: int
    deterministic_landed_estimate: int
    file_overlap_ratio: float
    changed_line_overlap_ratio: float
    suggested_diff: str
    landed_diff: str


@dataclass(frozen=True)
class ScoringExample:
    """Label-free suggestion/PR-diff pair used by the public scoring boundary."""

    suggested_diff: str
    landed_diff: str
    file_overlap_ratio: float
    changed_line_overlap_ratio: float


@dataclass(frozen=True)
class MetricResult:
    """Computed deterministic suggestion coverage metrics for one example."""

    exact_normalized_match: bool
    suggestion_language: str
    tokenizer: str
    line_recall: float
    token_recall: float
    identifier_normalized_token_recall: float
    literal_normalized_token_recall: float
    identifier_and_literal_normalized_token_recall: float
    best_added_line_overlap: float
    best_hunk_token_recall: float
    best_hunk_token_precision: float
    best_hunk_token_f1: float
    best_hunk_identifier_normalized_recall: float
    best_hunk_literal_normalized_recall: float
    best_hunk_identifier_and_literal_normalized_recall: float
    best_hunk_contiguous_line_ratio: float
    best_hunk_token_lcs_recall: float
    best_hunk_size_ratio: float
    meaningful_anchor_recall: float
    meaningful_anchor_count: int
    best_hunk_size: int
    best_hunk_file: str
    best_hunk_candidate_type: str
    candidate_hunk_count: int
    structural_available: bool
    structural_engine: str
    structural_language: str
    structural_similarity: float
    structural_node_recall: float
    structural_error: str
    gumtree_available: bool
    gumtree_language: str
    gumtree_operation_count: int
    gumtree_insert_ratio: float
    gumtree_delete_ratio: float
    gumtree_update_ratio: float
    gumtree_move_ratio: float
    gumtree_error: str
    file_overlap_ratio: float
    changed_line_overlap_ratio: float
    predicted_percentage: int
    predicted_label: Label


@dataclass(frozen=True)
class TokenizedText:
    """Tokens plus the strategy used to derive them."""

    language: str
    tokenizer: str
    tokens: list[str]


@dataclass(frozen=True)
class CandidateHunk:
    """One landed-diff candidate chunk compared against a suggestion."""

    path: str
    lines: list[str]
    candidate_type: str


def _load_dataset(dataset_path: Path) -> dict[str, DatasetExample]:
    examples: dict[str, DatasetExample] = {}
    with dataset_path.open() as dataset_file:
        for line in dataset_file:
            raw_example = json.loads(line)
            example = DatasetExample(
                example_id=raw_example["example_id"],
                suggested_diff=raw_example["suggested_diff"],
                landed_diff=raw_example["landed_diff"],
            )
            examples[example.example_id] = example
    return examples


def _validate_dataset_label_consistency(dataset_dir: Path) -> None:
    dataset_rows: dict[str, dict[str, object]] = {}
    with (dataset_dir / "dataset.jsonl").open() as dataset_file:
        for line in dataset_file:
            if not line.strip():
                continue
            raw_row = json.loads(line)
            dataset_rows[raw_row["example_id"]] = raw_row

    mismatches: list[str] = []
    with (dataset_dir / "labels.csv").open() as labels_file:
        for row in csv.DictReader(labels_file):
            dataset_row = dataset_rows.get(row["example_id"])
            if dataset_row is None:
                mismatches.append(f"{row['example_id']}: missing from dataset.jsonl")
                continue
            dataset_label = dataset_row.get("label")
            if dataset_label is not None and dataset_label != row["label"]:
                mismatches.append(f"{row['example_id']}: dataset label {dataset_label!r} != labels.csv {row['label']!r}")
            dataset_percentage = dataset_row.get("expected_landed_percentage")
            if dataset_percentage is not None and int(dataset_percentage) != int(row["expected_landed_percentage"]):
                mismatches.append(
                    f"{row['example_id']}: dataset percentage {dataset_percentage!r} "
                    f"!= labels.csv {row['expected_landed_percentage']!r}"
                )

    if mismatches:
        preview = "\n".join(mismatches[:10])
        raise ValueError(f"Dataset labels disagree with labels.csv:\n{preview}")


def _load_labeled_examples(dataset_dir: Path) -> list[LabeledExample]:
    _validate_dataset_label_consistency(dataset_dir)
    examples = _load_dataset(dataset_dir / "dataset.jsonl")
    labeled_examples: list[LabeledExample] = []
    with (dataset_dir / "labels.csv").open() as labels_file:
        for row in csv.DictReader(labels_file):
            dataset_example = examples[row["example_id"]]
            labeled_examples.append(
                LabeledExample(
                    example_id=row["example_id"],
                    label=_parse_label(row["label"]),
                    expected_landed_percentage=int(row["expected_landed_percentage"]),
                    deterministic_landed_estimate=int(float(row["deterministic_landed_estimate"])),
                    file_overlap_ratio=float(row["file_overlap_ratio"]),
                    changed_line_overlap_ratio=float(row["changed_line_overlap_ratio"]),
                    suggested_diff=dataset_example.suggested_diff,
                    landed_diff=dataset_example.landed_diff,
                )
            )
    return labeled_examples


def _parse_label(raw_label: str) -> Label:
    if raw_label not in _LABELS:
        raise ValueError(f"Unknown label {raw_label!r}.")
    return raw_label  # type: ignore[return-value]


def _added_lines_by_file_from_diff(diff_text: str) -> dict[str, list[str]]:
    added_lines_by_file: dict[str, list[str]] = {}
    current_file: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line.removeprefix("+++ b/")
            added_lines_by_file.setdefault(current_file, [])
            continue
        if line.startswith("+++"):
            current_file = None
            continue
        if line.startswith("diff --git"):
            current_file = None
            continue
        if current_file is not None and line.startswith("+"):
            added_lines_by_file[current_file].append(line[1:])
    return added_lines_by_file


def _added_hunks_by_file_from_diff(diff_text: str) -> dict[str, list[list[str]]]:
    added_hunks_by_file: dict[str, list[list[str]]] = {}
    current_file: str | None = None
    current_hunk: list[str] | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line.removeprefix("+++ b/")
            added_hunks_by_file.setdefault(current_file, [])
            continue
        if line.startswith("+++") or line.startswith("diff --git"):
            current_file = None
            current_hunk = None
            continue
        if line.startswith("@@") and current_file is not None:
            current_hunk = []
            added_hunks_by_file[current_file].append(current_hunk)
            continue
        if current_file is not None and current_hunk is not None and line.startswith("+"):
            current_hunk.append(line[1:])
    return added_hunks_by_file


def _prepare_lines_by_file(lines_by_file: dict[str, list[str]]) -> dict[str, list[str]]:
    prepared_lines_by_file: dict[str, list[str]] = {}
    for path, lines in lines_by_file.items():
        prepared_lines_by_file[path] = _prepare_lines_for_path(path, lines)
    return prepared_lines_by_file


def _prepare_hunks_by_file(hunks_by_file: dict[str, list[list[str]]]) -> dict[str, list[list[str]]]:
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


def _non_empty_normalized_lines(lines: Iterable[str]) -> list[str]:
    return [normalized_line for line in lines if (normalized_line := _normalize_line(line))]


def _line_recall(suggested_lines: list[str], landed_lines: list[str]) -> float:
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


def _tokenize_for_path(path: str, text: str) -> TokenizedText:
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


def _language_for_tokenization(path: str) -> str:
    normalized_path = Path(path)
    if normalized_path.name.lower() in _DOCKERFILE_NAMES:
        return "dockerfile"
    if normalized_path.name == "Jenkinsfile":
        return "groovy"
    return _LANGUAGE_BY_EXTENSION.get(normalized_path.suffix.lower(), "text")


def _tokenize_by_file(lines_by_file: dict[str, list[str]]) -> list[str]:
    tokens: list[str] = []
    for path, lines in lines_by_file.items():
        tokens.extend(_tokenize_for_path(path, "\n".join(lines)).tokens)
    return tokens


def _dominant_tokenization(lines_by_file: dict[str, list[str]]) -> tuple[str, str]:
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


def _normalize_identifier_tokens(tokens: Iterable[str]) -> list[str]:
    return ["IDENT" if _is_identifier(token) else token for token in tokens]


def _normalize_literal_tokens(tokens: Iterable[str]) -> list[str]:
    return ["LITERAL" if _is_literal(token) else token for token in tokens]


def _normalize_identifier_and_literal_tokens(tokens: Iterable[str]) -> list[str]:
    return ["IDENT" if _is_identifier(token) else "LITERAL" if _is_literal(token) else token for token in tokens]


def _is_identifier(token: str) -> bool:
    return bool(_IDENTIFIER_PATTERN.fullmatch(token)) and not keyword.iskeyword(token)


def _is_literal(token: str) -> bool:
    return (
        bool(_STRING_LITERAL_PATTERN.fullmatch(token))
        or bool(_NUMBER_LITERAL_PATTERN.fullmatch(token))
        or token in {"true", "false", "null", "True", "False", "None"}
    )


def _multiset_recall(suggested_items: list[str], landed_items: list[str]) -> float:
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


def _multiset_precision(suggested_items: list[str], landed_items: list[str]) -> float:
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


def _f1_score(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _longest_common_contiguous_ratio(suggested_lines: list[str], landed_lines: list[str]) -> float:
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


def _lcs_recall(suggested_items: list[str], landed_items: list[str]) -> float:
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


def _size_ratio(suggested_line_count: int, candidate_line_count: int) -> float:
    if suggested_line_count <= 0 or candidate_line_count <= 0:
        return 0.0
    return min(suggested_line_count, candidate_line_count) / max(suggested_line_count, candidate_line_count)


def _meaningful_anchors_for_path(path: str, text: str) -> list[str]:
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


def _cross_path_anchor_recall(suggestion_path: str, suggestion_text: str, candidate_path: str, candidate_text: str) -> float:
    return _multiset_recall(
        _meaningful_anchors_for_path(suggestion_path, suggestion_text),
        _meaningful_anchors_for_path(candidate_path, candidate_text),
    )


def _best_added_line_overlap(suggested_lines: list[str], landed_lines: list[str]) -> float:
    if not suggested_lines or not landed_lines:
        return 0.0
    window_size = len(suggested_lines)
    if len(landed_lines) <= window_size:
        return _line_recall(suggested_lines, landed_lines)
    return max(_line_recall(suggested_lines, landed_lines[index : index + window_size]) for index in range(len(landed_lines)))


def _candidate_hunks_for_suggestion(
    suggestion_path: str,
    suggestion_text: str,
    landed_hunks_by_file: dict[str, list[list[str]]],
) -> list[CandidateHunk]:
    candidates: list[CandidateHunk] = []
    seen_candidates: set[tuple[str, str, tuple[str, ...]]] = set()

    def add_candidate(path: str, lines: list[str], candidate_type: str) -> None:
        normalized_lines = _non_empty_normalized_lines(lines)
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
            hunk_text = "\n".join(_non_empty_normalized_lines(hunk_lines))
            if suggestion_suffix and suggestion_suffix == candidate_suffix:
                add_candidate(candidate_path, hunk_lines, "same_extension")
                continue
            anchor_recall = _cross_path_anchor_recall(suggestion_path, suggestion_text, candidate_path, hunk_text)
            if anchor_recall >= 0.30:
                add_candidate(candidate_path, hunk_lines, "anchor_overlap")

    return candidates


def _best_hunk_scores(
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
        suggestion_tokens = _tokenize_for_path(path, suggestion_text).tokens
        normalized_suggestion_tokens = _normalize_identifier_tokens(suggestion_tokens)
        literal_normalized_suggestion_tokens = _normalize_literal_tokens(suggestion_tokens)
        identifier_and_literal_normalized_suggestion_tokens = _normalize_identifier_and_literal_tokens(suggestion_tokens)
        anchor_count = len(_meaningful_anchors_for_path(path, suggestion_text))

        for candidate_hunk in _candidate_hunks_for_suggestion(path, suggestion_text, landed_hunks_by_file):
            candidate_hunk_count += 1
            normalized_hunk_lines = candidate_hunk.lines
            hunk_text = "\n".join(normalized_hunk_lines)
            hunk_tokens = _tokenize_for_path(candidate_hunk.path, hunk_text).tokens
            normalized_hunk_tokens = _normalize_identifier_tokens(hunk_tokens)
            literal_normalized_hunk_tokens = _normalize_literal_tokens(hunk_tokens)
            identifier_and_literal_normalized_hunk_tokens = _normalize_identifier_and_literal_tokens(hunk_tokens)
            token_recall = _multiset_recall(suggestion_tokens, hunk_tokens)
            token_precision = _multiset_precision(suggestion_tokens, hunk_tokens)
            token_f1 = _f1_score(token_precision, token_recall)
            identifier_normalized_recall = _multiset_recall(normalized_suggestion_tokens, normalized_hunk_tokens)
            literal_normalized_recall = _multiset_recall(literal_normalized_suggestion_tokens, literal_normalized_hunk_tokens)
            identifier_and_literal_normalized_recall = _multiset_recall(
                identifier_and_literal_normalized_suggestion_tokens,
                identifier_and_literal_normalized_hunk_tokens,
            )
            anchor_recall = _cross_path_anchor_recall(path, suggestion_text, candidate_hunk.path, hunk_text)
            contiguous_line_ratio = _longest_common_contiguous_ratio(suggested_lines, normalized_hunk_lines)
            token_lcs_recall = _lcs_recall(identifier_and_literal_normalized_suggestion_tokens, identifier_and_literal_normalized_hunk_tokens)
            size_ratio = _size_ratio(len(suggested_lines), len(normalized_hunk_lines))
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


def _best_structural_scores(
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
        language = _language_for_tokenization(path)
        structural_language = _structural_language_for_tokenization(language)
        if structural_language != "python" and structural_language not in _TREE_SITTER_LANGUAGES:
            continue

        suggestion_text = "\n".join(suggested_lines)
        suggestion_nodes, suggestion_error, engine = _structural_node_types(structural_language, suggestion_text)
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
            candidate_language = _language_for_tokenization(candidate_hunk.path)
            if _structural_language_for_tokenization(candidate_language) != structural_language:
                continue
            hunk_text = "\n".join(candidate_hunk.lines)
            hunk_nodes, hunk_error, _ = _structural_node_types(structural_language, hunk_text)
            if hunk_error:
                continue
            node_recall = _multiset_recall(suggestion_nodes, hunk_nodes)
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


def _structural_node_types(language: str, text: str) -> tuple[list[str], str, str]:
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


def _tree_sitter_parser(language: str) -> object:
    if language in _TREE_SITTER_PARSERS:
        return _TREE_SITTER_PARSERS[language]

    from tree_sitter_language_pack import PackConfig, configure, get_parser  # type: ignore[import-not-found]

    cache_dir = Path(__file__).resolve().parents[2] / ".tree-sitter-cache"
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


def _score_example(example: LabeledExample | ScoringExample, *, enable_gumtree: bool) -> MetricResult:
    suggested_lines_by_file = _prepare_lines_by_file(_added_lines_by_file_from_diff(example.suggested_diff))
    landed_lines_by_file = _prepare_lines_by_file(_added_lines_by_file_from_diff(example.landed_diff))
    landed_hunks_by_file = _prepare_hunks_by_file(_added_hunks_by_file_from_diff(example.landed_diff))
    suggested_lines = [line for lines in suggested_lines_by_file.values() for line in lines]
    landed_lines = [line for path in suggested_lines_by_file for line in landed_lines_by_file.get(path, [])]
    landed_lines_by_suggested_file = {path: landed_lines_by_file.get(path, []) for path in suggested_lines_by_file}
    suggested_text = "\n".join(suggested_lines)
    landed_text = "\n".join(landed_lines)

    suggestion_language, tokenizer_name = _dominant_tokenization(suggested_lines_by_file)
    suggested_tokens = _tokenize_by_file(suggested_lines_by_file)
    landed_tokens = _tokenize_by_file(landed_lines_by_suggested_file)
    identifier_normalized_suggested_tokens = _normalize_identifier_tokens(suggested_tokens)
    identifier_normalized_landed_tokens = _normalize_identifier_tokens(landed_tokens)
    literal_normalized_suggested_tokens = _normalize_literal_tokens(suggested_tokens)
    literal_normalized_landed_tokens = _normalize_literal_tokens(landed_tokens)
    identifier_and_literal_normalized_suggested_tokens = _normalize_identifier_and_literal_tokens(suggested_tokens)
    identifier_and_literal_normalized_landed_tokens = _normalize_identifier_and_literal_tokens(landed_tokens)

    line_recall = _line_recall(suggested_lines, landed_lines)
    token_recall = _multiset_recall(suggested_tokens, landed_tokens)
    identifier_normalized_token_recall = _multiset_recall(
        identifier_normalized_suggested_tokens,
        identifier_normalized_landed_tokens,
    )
    literal_normalized_token_recall = _multiset_recall(literal_normalized_suggested_tokens, literal_normalized_landed_tokens)
    identifier_and_literal_normalized_token_recall = _multiset_recall(
        identifier_and_literal_normalized_suggested_tokens,
        identifier_and_literal_normalized_landed_tokens,
    )
    exact_normalized_match = bool(suggested_text) and suggested_text in landed_text
    best_added_line_overlap = _best_added_line_overlap(suggested_lines, landed_lines)
    best_hunk_scores = _best_hunk_scores(suggested_lines_by_file, landed_hunks_by_file)
    structural_scores = _best_structural_scores(suggested_lines_by_file, landed_hunks_by_file)
    gumtree_features = _gumtree_features_by_file(suggested_lines_by_file, landed_lines_by_file, enable_gumtree)
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
        predicted_label=_bucket_percentage(predicted_percentage),
    )


def raw_diff_support_issues(suggested_diff: str) -> list[str]:
    """Return reasons why a suggestion diff is outside the currently supported inference domain."""
    issues: list[str] = []
    added_lines_by_file = _added_lines_by_file_from_diff(suggested_diff)
    files_with_additions = [path for path, lines in added_lines_by_file.items() if _non_empty_normalized_lines(lines)]
    removed_lines = [
        line
        for line in suggested_diff.splitlines()
        if line.startswith("-") and not line.startswith("---") and line[1:].strip()
    ]
    hunk_count = sum(line.startswith("@@") for line in suggested_diff.splitlines())

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
    if "rename from " in suggested_diff or "rename to " in suggested_diff:
        issues.append("renamed suggestion files are not yet supported")
    return issues


def score_diff_pair(suggested_diff: str, merged_pr_diff: str, *, enable_gumtree: bool = False) -> MetricResult:
    """Compute deterministic model features for a supported suggestion/merged-PR diff pair."""
    support_issues = raw_diff_support_issues(suggested_diff)
    if support_issues:
        raise ValueError("Unsupported suggestion diff: " + "; ".join(support_issues))

    suggested_lines_by_file = _added_lines_by_file_from_diff(suggested_diff)
    landed_lines_by_file = _added_lines_by_file_from_diff(merged_pr_diff)
    suggested_files = set(suggested_lines_by_file)
    landed_files = set(landed_lines_by_file)
    suggested_lines = {
        line.strip()
        for lines in suggested_lines_by_file.values()
        for line in lines
        if line.strip()
    }
    landed_lines = {
        line.strip()
        for lines in landed_lines_by_file.values()
        for line in lines
        if line.strip()
    }
    file_overlap_ratio = len(suggested_files & landed_files) / len(suggested_files) if suggested_files else 0.0
    changed_line_overlap_ratio = len(suggested_lines & landed_lines) / len(suggested_lines) if suggested_lines else 0.0

    return _score_example(
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


def _normalize_lines_by_file(lines_by_file: dict[str, list[str]]) -> dict[str, list[str]]:
    return {path: _non_empty_normalized_lines(lines) for path, lines in lines_by_file.items()}


def _gumtree_features_by_file(
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


def _bucket_percentage(percentage: int) -> Label:
    if percentage == 0:
        return "0%"
    if percentage < 60:
        return "partial"
    if percentage < 90:
        return "mostly"
    return "100%"


def _percentage_bucket(percentage: int) -> PercentageBucket:
    bounded_percentage = max(0, min(100, int(round(percentage))))
    if bounded_percentage == 0:
        return "0"
    lower_bound = ((bounded_percentage - 1) // 10) * 10 + 1
    upper_bound = min(lower_bound + 9, 100)
    return f"{lower_bound}-{upper_bound}"  # type: ignore[return-value]


def _print_evaluation(name: str, actual_labels: list[Label], predicted_labels: list[Label]) -> None:
    print(f"\n{name}")
    print(f"accuracy: {_accuracy(actual_labels, predicted_labels):.3f}")
    print("confusion actual -> predicted")
    print("actual," + ",".join(_LABELS))
    for label in _LABELS:
        row_counts = Counter(predicted for actual, predicted in zip(actual_labels, predicted_labels) if actual == label)
        print(label + "," + ",".join(str(row_counts[predicted_label]) for predicted_label in _LABELS))
    print("per-class precision recall f1")
    for label in _LABELS:
        precision, recall, f1_score = _precision_recall_f1(actual_labels, predicted_labels, label)
        print(f"{label}: precision={precision:.3f} recall={recall:.3f} f1={f1_score:.3f}")


def _accuracy(actual_labels: list[Label], predicted_labels: list[Label]) -> float:
    return sum(actual == predicted for actual, predicted in zip(actual_labels, predicted_labels)) / len(actual_labels)


def _precision_recall_f1(actual_labels: list[Label], predicted_labels: list[Label], label: Label) -> tuple[float, float, float]:
    true_positive_count = sum(actual == label and predicted == label for actual, predicted in zip(actual_labels, predicted_labels))
    false_positive_count = sum(actual != label and predicted == label for actual, predicted in zip(actual_labels, predicted_labels))
    false_negative_count = sum(actual == label and predicted != label for actual, predicted in zip(actual_labels, predicted_labels))
    precision = true_positive_count / (true_positive_count + false_positive_count or 1)
    recall = true_positive_count / (true_positive_count + false_negative_count or 1)
    f1_score = 2 * precision * recall / (precision + recall or 1)
    return precision, recall, f1_score


def _mean_absolute_error(actual_percentages: list[int], predicted_percentages: list[int]) -> float:
    return sum(abs(actual - predicted) for actual, predicted in zip(actual_percentages, predicted_percentages)) / len(
        actual_percentages
    )


def _write_scores(output_path: Path, examples: list[LabeledExample], metric_results: list[MetricResult]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=[
                "example_id",
                "label",
                "expected_landed_percentage",
                "expected_percentage_bucket",
                "predicted_label",
                "predicted_percentage",
                "predicted_percentage_bucket",
                "suggestion_language",
                "tokenizer",
                "exact_normalized_match",
                "line_recall",
                "token_recall",
                "identifier_normalized_token_recall",
                "literal_normalized_token_recall",
                "identifier_and_literal_normalized_token_recall",
                "best_added_line_overlap",
                "best_hunk_token_recall",
                "best_hunk_token_precision",
                "best_hunk_token_f1",
                "best_hunk_identifier_normalized_recall",
                "best_hunk_literal_normalized_recall",
                "best_hunk_identifier_and_literal_normalized_recall",
                "best_hunk_contiguous_line_ratio",
                "best_hunk_token_lcs_recall",
                "best_hunk_size_ratio",
                "meaningful_anchor_recall",
                "meaningful_anchor_count",
                "best_hunk_size",
                "best_hunk_file",
                "best_hunk_candidate_type",
                "candidate_hunk_count",
                "structural_available",
                "structural_engine",
                "structural_language",
                "structural_similarity",
                "structural_node_recall",
                "structural_error",
                "gumtree_available",
                "gumtree_language",
                "gumtree_operation_count",
                "gumtree_insert_ratio",
                "gumtree_delete_ratio",
                "gumtree_update_ratio",
                "gumtree_move_ratio",
                "gumtree_error",
                "file_overlap_ratio",
                "changed_line_overlap_ratio",
            ],
        )
        writer.writeheader()
        for example, metric_result in zip(examples, metric_results):
            writer.writerow(
                {
                    "example_id": example.example_id,
                    "label": example.label,
                    "expected_landed_percentage": example.expected_landed_percentage,
                    "expected_percentage_bucket": _percentage_bucket(example.expected_landed_percentage),
                    "predicted_label": metric_result.predicted_label,
                    "predicted_percentage": metric_result.predicted_percentage,
                    "predicted_percentage_bucket": _percentage_bucket(metric_result.predicted_percentage),
                    "suggestion_language": metric_result.suggestion_language,
                    "tokenizer": metric_result.tokenizer,
                    "exact_normalized_match": metric_result.exact_normalized_match,
                    "line_recall": f"{metric_result.line_recall:.6f}",
                    "token_recall": f"{metric_result.token_recall:.6f}",
                    "identifier_normalized_token_recall": f"{metric_result.identifier_normalized_token_recall:.6f}",
                    "literal_normalized_token_recall": f"{metric_result.literal_normalized_token_recall:.6f}",
                    "identifier_and_literal_normalized_token_recall": (
                        f"{metric_result.identifier_and_literal_normalized_token_recall:.6f}"
                    ),
                    "best_added_line_overlap": f"{metric_result.best_added_line_overlap:.6f}",
                    "best_hunk_token_recall": f"{metric_result.best_hunk_token_recall:.6f}",
                    "best_hunk_token_precision": f"{metric_result.best_hunk_token_precision:.6f}",
                    "best_hunk_token_f1": f"{metric_result.best_hunk_token_f1:.6f}",
                    "best_hunk_identifier_normalized_recall": (
                        f"{metric_result.best_hunk_identifier_normalized_recall:.6f}"
                    ),
                    "best_hunk_literal_normalized_recall": f"{metric_result.best_hunk_literal_normalized_recall:.6f}",
                    "best_hunk_identifier_and_literal_normalized_recall": (
                        f"{metric_result.best_hunk_identifier_and_literal_normalized_recall:.6f}"
                    ),
                    "best_hunk_contiguous_line_ratio": f"{metric_result.best_hunk_contiguous_line_ratio:.6f}",
                    "best_hunk_token_lcs_recall": f"{metric_result.best_hunk_token_lcs_recall:.6f}",
                    "best_hunk_size_ratio": f"{metric_result.best_hunk_size_ratio:.6f}",
                    "meaningful_anchor_recall": f"{metric_result.meaningful_anchor_recall:.6f}",
                    "meaningful_anchor_count": metric_result.meaningful_anchor_count,
                    "best_hunk_size": metric_result.best_hunk_size,
                    "best_hunk_file": metric_result.best_hunk_file,
                    "best_hunk_candidate_type": metric_result.best_hunk_candidate_type,
                    "candidate_hunk_count": metric_result.candidate_hunk_count,
                    "structural_available": metric_result.structural_available,
                    "structural_engine": metric_result.structural_engine,
                    "structural_language": metric_result.structural_language,
                    "structural_similarity": f"{metric_result.structural_similarity:.6f}",
                    "structural_node_recall": f"{metric_result.structural_node_recall:.6f}",
                    "structural_error": metric_result.structural_error,
                    "gumtree_available": metric_result.gumtree_available,
                    "gumtree_language": metric_result.gumtree_language,
                    "gumtree_operation_count": metric_result.gumtree_operation_count,
                    "gumtree_insert_ratio": f"{metric_result.gumtree_insert_ratio:.6f}",
                    "gumtree_delete_ratio": f"{metric_result.gumtree_delete_ratio:.6f}",
                    "gumtree_update_ratio": f"{metric_result.gumtree_update_ratio:.6f}",
                    "gumtree_move_ratio": f"{metric_result.gumtree_move_ratio:.6f}",
                    "gumtree_error": metric_result.gumtree_error,
                    "file_overlap_ratio": f"{metric_result.file_overlap_ratio:.6f}",
                    "changed_line_overlap_ratio": f"{metric_result.changed_line_overlap_ratio:.6f}",
                }
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate PR suggestion coverage metrics against labeled data.")
    parser.add_argument("--dataset-dir", type=Path, default=_DEFAULT_DATASET_DIR)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--enable-gumtree",
        action="store_true",
        help="Compute optional GumTree edit-script features for supported source files.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    examples = _load_labeled_examples(args.dataset_dir)
    metric_results = [_score_example(example, enable_gumtree=args.enable_gumtree) for example in examples]
    actual_labels = [example.label for example in examples]
    actual_percentages = [example.expected_landed_percentage for example in examples]
    baseline_percentages = [example.deterministic_landed_estimate for example in examples]
    baseline_labels = [_bucket_percentage(percentage) for percentage in baseline_percentages]
    predicted_percentages = [metric_result.predicted_percentage for metric_result in metric_results]
    predicted_labels = [metric_result.predicted_label for metric_result in metric_results]

    print(f"examples: {len(examples)}")
    print(f"baseline MAE: {_mean_absolute_error(actual_percentages, baseline_percentages):.2f}")
    print(f"new metric MAE: {_mean_absolute_error(actual_percentages, predicted_percentages):.2f}")
    _print_evaluation("baseline deterministic_landed_estimate", actual_labels, baseline_labels)
    _print_evaluation("new clone-style metric stack", actual_labels, predicted_labels)
    _write_scores(args.output, examples, metric_results)
    print(f"\nwrote per-example scores: {args.output}")


if __name__ == "__main__":
    main()
