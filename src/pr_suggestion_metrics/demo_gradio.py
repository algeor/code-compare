"""Gradio demo UI for the local PR suggestion analysis service."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
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
    uncertainty_text = _uncertainty_text(uncertainty.status, uncertainty.lower, uncertainty.upper)
    input_fingerprint = _input_fingerprint(suggested_diff, merged_pr_diff)

    summary = _summary_markdown(
        status=result.status,
        percentage_text=percentage_text,
        matched_units=evidence.matched_units,
        total_units=evidence.total_suggested_units,
        uncertainty_text=uncertainty_text,
        percentage_model=result.model_versions["percentage_model"],
        explanation_model=result.model_versions["explanation_model"],
        explanation_version=result.model_versions["explanation_model_version"],
        explanation_summary=result.explanation.summary,
        input_fingerprint=input_fingerprint,
        ignores_extra_merged_lines=evidence.matched_units == evidence.total_suggested_units,
    )
    return summary, json.dumps(
        _json_payload(result.model_dump(mode="json"), input_fingerprint=input_fingerprint),
        indent=2,
        sort_keys=True,
    )


def _summary_markdown(
    *,
    status: str,
    percentage_text: str,
    matched_units: int,
    total_units: int,
    uncertainty_text: str,
    percentage_model: str,
    explanation_model: str,
    explanation_version: str,
    explanation_summary: str,
    input_fingerprint: str,
    ignores_extra_merged_lines: bool,
) -> str:
    badge = "✅ Predicted" if status == "predicted" else "⚠️ Abstained"
    scope_note = (
        "All suggested units were found. Extra merged PR lines are ignored because coverage measures suggestion adoption."
        if ignores_extra_merged_lines
        else "Some suggested units were not found in the merged PR diff."
    )
    return f"""## Result

<div class="result-cards">
  <div class="result-card"><span>Status</span><strong>{badge}</strong></div>
  <div class="result-card"><span>Coverage</span><strong>{percentage_text}</strong></div>
  <div class="result-card"><span>Exact Evidence</span><strong>{matched_units}/{total_units}</strong></div>
  <div class="result-card"><span>Uncertainty</span><strong>{uncertainty_text}</strong></div>
</div>

**What this means:** {scope_note}

**Input fingerprint:** `{input_fingerprint}`

## Explanation

{explanation_summary}

## Versions

- Percentage model: `{percentage_model}`
- Explainer: `{explanation_model}` `{explanation_version}`

_Demo note: trained on weak local Phase 5-derived labels, not human ground truth._
"""


def _uncertainty_text(status: str, lower: int | None, upper: int | None) -> str:
    if status == "calibrated" and lower is not None and upper is not None:
        return f"{lower}–{upper}%"
    return "N/A"


def _input_fingerprint(suggested_diff: str, merged_pr_diff: str) -> str:
    digest = sha256(f"{suggested_diff}\0{merged_pr_diff}".encode("utf-8")).hexdigest()
    return digest[:12]


def _pending_result() -> tuple[str, str]:
    return "Analyzing latest inputs…", ""


def build_app(*, model_dir: Path = DEFAULT_DEMO_MODEL_DIR) -> Any:
    """Build the Gradio Blocks app lazily so core imports do not require Gradio."""
    import gradio as gr

    def run(suggested_diff: str, merged_pr_diff: str) -> tuple[str, str]:
        return analyze_for_demo(suggested_diff, merged_pr_diff, model_dir=model_dir)

    css = """
    .gradio-container { max-width: 1180px !important; }
    textarea { font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important; }
    .result-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 10px 0 22px; }
    .result-card { border: 1px solid #ece7df; border-radius: 14px; padding: 14px 16px; background: #fffaf4; }
    .result-card span { display: block; color: #6b625b; font-size: 0.88rem; margin-bottom: 5px; }
    .result-card strong { color: #2f2a26; font-size: 1.15rem; }
    """
    with gr.Blocks(title="PR Suggestion Coverage Demo", css=css) as app:
        gr.Markdown(
            "# PR Suggestion Coverage Demo\n"
            "Paste a review suggestion diff and the merged PR diff. The demo returns one stable analysis result: "
            "deterministic evidence, a weak local percentage model, and a grounded template explanation."
        )
        with gr.Row():
            suggested = gr.Textbox(label="Suggested diff", value=SAMPLE_SUGGESTED_DIFF, lines=14)
            merged = gr.Textbox(label="Merged PR diff", value=SAMPLE_MERGED_DIFF, lines=14)
        button = gr.Button("Analyze", variant="primary")
        with gr.Row():
            summary = gr.Markdown(label="Summary")
            payload = gr.Code(label="Raw API Result", language="json")
        button.click(_pending_result, outputs=[summary, payload], queue=False).then(
            run,
            inputs=[suggested, merged],
            outputs=[summary, payload],
        )
    return app


def _json_payload(payload: dict[str, Any], *, input_fingerprint: str) -> dict[str, Any]:
    payload["demo_input_fingerprint"] = input_fingerprint
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
