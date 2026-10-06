"""Gradio demo UI for the local PR suggestion analysis service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pr_suggestion_metrics.analysis_service import DEFAULT_DEMO_MODEL_DIR, AnalysisService


SAMPLE_SUGGESTED_DIFF = """--- a/app.py
+++ b/app.py
@@ -0,0 +1 @@
+value = 1
"""
SAMPLE_MERGED_DIFF = SAMPLE_SUGGESTED_DIFF


def analyze_for_demo(
    suggested_diff: str,
    merged_pr_diff: str,
    *,
    model_dir: Path = DEFAULT_DEMO_MODEL_DIR,
) -> tuple[str, str]:
    """Return a human summary and raw JSON payload for the demo UI."""
    try:
        result = AnalysisService(model_dir=model_dir).analyze(
            suggested_diff=suggested_diff,
            merged_pr_diff=merged_pr_diff,
            example_id="demo-input",
        )
    except Exception as exc:  # pragma: no cover - defensive UI boundary
        payload = {"status": "error", "message": str(exc)}
        return f"**Status:** error\n\n{exc}", json.dumps(payload, indent=2, sort_keys=True)

    percentage = result.percentage.model_predicted_percentage
    percentage_text = "abstained" if percentage is None else f"{percentage}%"
    evidence = result.percentage.change_coverage_evidence
    uncertainty = result.percentage.uncertainty
    uncertainty_text: str = uncertainty.status
    if uncertainty.reason:
        uncertainty_text = f"{uncertainty_text}: {uncertainty.reason}"

    summary = "\n".join(
        [
            f"**Status:** {result.status}",
            f"**Coverage:** {percentage_text}",
            f"**Exact evidence:** {evidence.matched_units}/{evidence.total_suggested_units} suggested units matched",
            f"**Uncertainty:** {uncertainty_text}",
            f"**Percentage model:** {result.model_versions['percentage_model']}",
            f"**Explainer:** {result.model_versions['explanation_model']} {result.model_versions['explanation_model_version']}",
            "",
            result.explanation.summary,
            "",
            "_Demo note: trained on weak local Phase 5-derived labels, not human ground truth._",
        ]
    )
    return summary, json.dumps(_json_payload(result.model_dump(mode="json")), indent=2, sort_keys=True)


def build_app(*, model_dir: Path = DEFAULT_DEMO_MODEL_DIR) -> Any:
    """Build the Gradio Blocks app lazily so core imports do not require Gradio."""
    import gradio as gr

    def run(suggested_diff: str, merged_pr_diff: str) -> tuple[str, str]:
        return analyze_for_demo(suggested_diff, merged_pr_diff, model_dir=model_dir)

    with gr.Blocks(title="PR Suggestion Coverage Demo") as app:
        gr.Markdown(
            "# PR Suggestion Coverage Demo\n"
            "Interview prototype: deterministic evidence + weak local percentage model + grounded explanation."
        )
        with gr.Row():
            suggested = gr.Textbox(label="Suggested diff", value=SAMPLE_SUGGESTED_DIFF, lines=12)
            merged = gr.Textbox(label="Merged PR diff", value=SAMPLE_MERGED_DIFF, lines=12)
        button = gr.Button("Analyze")
        summary = gr.Markdown(label="Summary")
        payload = gr.Code(label="Raw API Result", language="json")
        button.click(run, inputs=[suggested, merged], outputs=[summary, payload])
    return app


def _json_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload["demo_disclaimer"] = "Weak local labels only; not human validated; not release validated."
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_DEMO_MODEL_DIR)
    parser.add_argument("--server-name", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, default=7860)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    build_app(model_dir=args.model_dir).launch(server_name=args.server_name, server_port=args.server_port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
