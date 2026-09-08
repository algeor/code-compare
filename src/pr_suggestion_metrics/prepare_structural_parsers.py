"""Prepare and verify local structural parsers for snippet comparison."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from pr_suggestion_metrics.evaluate_metrics import _structural_node_types


_SMOKE_SNIPPETS = {
    "c": "int add(int a, int b) { return a + b; }\n",
    "cpp": "int add(int a, int b) { return a + b; }\n",
    "go": "package main\nfunc add(a int, b int) int { return a + b }\n",
    "html": "<main><h1>Hello</h1><button disabled>Save</button></main>\n",
    "java": "class A { int add(int a, int b) { return a + b; } }\n",
    "javascript": "function add(a, b) { return a + b; }\n",
    "python": "def add(a, b):\n    return a + b\n",
    "rust": "fn add(a: i32, b: i32) -> i32 { a + b }\n",
    "typescript": "function add(a: number, b: number): number { return a + b; }\n",
}


@dataclass(frozen=True)
class ParserCheck:
    """Result of verifying one local structural parser."""

    language: str
    engine: str
    node_count: int
    error: str


def check_structural_parsers(languages: list[str]) -> list[ParserCheck]:
    """Check that the requested structural parsers work in the local ML environment."""
    checks: list[ParserCheck] = []
    for language in languages:
        snippet = _SMOKE_SNIPPETS[language]
        nodes, error, engine = _structural_node_types(language, snippet)
        checks.append(
            ParserCheck(
                language=language,
                engine=engine,
                node_count=len(nodes),
                error=error,
            )
        )
    return checks


def main() -> None:
    """Run parser checks from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--language",
        action="append",
        choices=sorted(_SMOKE_SNIPPETS),
        dest="languages",
        help="Language to verify. Repeat this flag to check several languages.",
    )
    args = parser.parse_args()

    languages = args.languages or sorted(_SMOKE_SNIPPETS)
    checks = check_structural_parsers(languages)
    failed_checks = [check for check in checks if check.error]

    for check in checks:
        status = "ok" if not check.error else check.error
        print(f"{check.language}: {check.engine or 'none'} nodes={check.node_count} status={status}")

    if failed_checks:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
