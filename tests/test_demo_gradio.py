from __future__ import annotations

import json

from pr_suggestion_metrics.demo_gradio import SAMPLE_MERGED_DIFF, SAMPLE_SUGGESTED_DIFF, analyze_for_demo


def test_analyze_for_demo_returns_summary_and_raw_payload() -> None:
    summary, raw_payload = analyze_for_demo(SAMPLE_SUGGESTED_DIFF, SAMPLE_MERGED_DIFF)
    payload = json.loads(raw_payload)

    assert "<div class=\"result-cards\">" in summary
    assert "<span>Status</span><strong>✅ Predicted</strong>" in summary
    assert "<span>Uncertainty</span><strong>N/A</strong>" in summary
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
