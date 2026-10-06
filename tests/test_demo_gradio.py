from __future__ import annotations

import json

from pr_suggestion_metrics.demo_gradio import SAMPLE_MERGED_DIFF, SAMPLE_SUGGESTED_DIFF, analyze_for_demo


def test_analyze_for_demo_returns_summary_and_raw_payload() -> None:
    summary, raw_payload = analyze_for_demo(SAMPLE_SUGGESTED_DIFF, SAMPLE_MERGED_DIFF)
    payload = json.loads(raw_payload)

    assert "**Status:** predicted" in summary
    assert "**Coverage:**" in summary
    assert "weak local Phase 5-derived labels" in summary
    assert payload["status"] == "predicted"
    assert payload["percentage"]["model_name"] == "extra_trees"
    assert payload["demo_disclaimer"] == "Weak local labels only; not human validated; not release validated."
