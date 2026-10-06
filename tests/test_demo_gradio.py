from __future__ import annotations

import json
from pathlib import Path

import pytest

from pr_suggestion_metrics.demo_gradio import SAMPLE_MERGED_DIFF, SAMPLE_SUGGESTED_DIFF, analyze_for_demo, parse_args


EXAMPLE_PAIRS_PATH = Path(__file__).resolve().parents[1] / "data" / "examples" / "diff_checker_pairs.jsonl"
EXPECTED_DEMO_STATUS_BY_ID = {
    "exact_same_file_addition": "predicted",
    "final_has_extra_lines": "predicted",
    "suggestion_has_extra_line": "predicted",
    "same_code_moved_to_new_file": "predicted",
    "same_text_wrong_operation": "abstained",
    "no_overlap_same_file": "predicted",
    "exact_rename_only": "abstained",
    "duplicate_line_occurrence": "predicted",
    "exact_replacement": "abstained",
}


def test_parse_args_uses_auto_port_by_default() -> None:
    args = parse_args([])

    assert args.server_port is None


def test_parse_args_accepts_fixed_server_port() -> None:
    args = parse_args(["--server-port", "7860"])

    assert args.server_port == 7860


def _example_pairs() -> list[dict[str, object]]:
    return [json.loads(line) for line in EXAMPLE_PAIRS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_analyze_for_demo_returns_summary_and_raw_payload() -> None:
    summary, raw_payload = analyze_for_demo(SAMPLE_SUGGESTED_DIFF, SAMPLE_MERGED_DIFF)
    payload = json.loads(raw_payload)

    assert "<div class=\"result-cards\">" in summary
    assert "<span>Status</span><strong>✅ Predicted</strong>" in summary
    assert "<span>Uncertainty</span><strong>N/A</strong>" in summary
    assert "All scored suggestion change lines were found" in summary
    assert "**Input fingerprint:**" in summary
    assert "## Versions" in summary
    assert "weak local Phase 5-derived labels" in summary
    assert payload["status"] == "predicted"
    assert payload["percentage"]["model_name"] == "extra_trees"
    assert len(payload["demo_input_fingerprint"]) == 12
    assert payload["demo_disclaimer"] == "Weak local labels only; not human validated; not release validated."


def test_analyze_for_demo_uses_latest_inputs() -> None:
    _, first_payload = analyze_for_demo(SAMPLE_SUGGESTED_DIFF, SAMPLE_MERGED_DIFF)
    _, second_payload = analyze_for_demo(
        "--- a/new.py\n+++ b/new.py\n@@ -0,0 +1 @@\n+new_value = 2\n",
        "--- a/new.py\n+++ b/new.py\n@@ -0,0 +1 @@\n+different_value = 3\n",
    )

    first = json.loads(first_payload)
    second = json.loads(second_payload)

    assert first["demo_input_fingerprint"] != second["demo_input_fingerprint"]
    assert first["percentage"]["input_hashes"] != second["percentage"]["input_hashes"]


@pytest.mark.parametrize("example", _example_pairs(), ids=lambda row: str(row["id"]))
def test_analyze_for_demo_accepts_diff_checker_examples(example: dict[str, object]) -> None:
    example_id = str(example["id"])
    summary, raw_payload = analyze_for_demo(
        str(example["suggested_diff"]),
        str(example["merged_pr_diff"]),
    )
    payload = json.loads(raw_payload)
    percentage = payload["percentage"]
    evidence = percentage["change_coverage_evidence"]
    status_badge = "✅ Predicted" if payload["status"] == "predicted" else "⚠️ Abstained"

    assert payload["status"] == EXPECTED_DEMO_STATUS_BY_ID[example_id]
    assert payload["demo_input_fingerprint"]
    assert payload["demo_disclaimer"] == "Weak local labels only; not human validated; not release validated."
    assert evidence["coverage_percentage"] == example["expected_exact_coverage_percentage"]
    assert f"<span>Status</span><strong>{status_badge}</strong>" in summary
    if payload["status"] == "predicted":
        assert percentage["model_predicted_percentage"] is not None
        assert percentage["model_name"] == "extra_trees"
    else:
        assert percentage["model_predicted_percentage"] is None
        assert percentage["applicability_reasons"]
