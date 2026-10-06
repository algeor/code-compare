# Deployment

## Recommended Free Option

Deploy a small Gradio application on [Hugging Face Spaces](https://huggingface.co/spaces).

This is the best fit for the current project because Spaces provides a free CPU tier for ML demos. The repository is currently a Python package and collection of command-line tools, so it needs a small web entry point before it can be hosted.

The free tier is suitable for a demonstration, not a production service:

- The application may sleep while unused and take time to start again.
- CPU, memory, storage, and request throughput are limited.
- Availability is not guaranteed by a production service-level agreement.
- A public Space must not receive confidential source code, private diffs, credentials, or proprietary model artifacts.

Check the current Hugging Face pricing and organizational security policy before deployment because hosting plans can change.

## What to Deploy

Do not upload the complete research workspace. It contains large datasets, notebooks, reports, and training artifacts that the inference application does not need.

Create a small deployment repository containing only:

```text
app.py
README.md
requirements.txt
pyproject.toml
src/pr_suggestion_metrics/
models/trusted-percentage-model/
```

Keep all three verified regression-model files together:

```text
models/trusted-percentage-model/model.joblib
models/trusted-percentage-model/feature_schema.json
models/trusted-percentage-model/artifact_manifest.json
```

The repository does not bundle an active model. Train and validate one from a frozen percentage benchmark before deployment; archived models are unsupported.

The application should:

1. Accept a suggested diff and the merged pull-request diff.
2. Call `predict_coverage_from_diffs` with the regression model directory.
3. Display the predicted semantic coverage percentage and the model limitations.
4. Explain when the model abstains because a diff shape is not supported.

## Minimal Application

Create `app.py` in the deployment repository:

```python
from pathlib import Path

import gradio as gr

from pr_suggestion_metrics.model_inference import predict_coverage_from_diffs


MODEL_DIR = Path(__file__).parent / "models" / "trusted-percentage-model"


def compare_diffs(suggested_diff: str, merged_diff: str) -> str:
    if not suggested_diff.strip() or not merged_diff.strip():
        return "Paste both diffs before comparing them."

    result = predict_coverage_from_diffs(
        suggested_diff,
        merged_diff,
        model_dir=MODEL_DIR,
    )
    if result["status"] != "predicted":
        warnings = "; ".join(result["warnings"])
        return f"The model could not score this input: {warnings}"

    percentage = result["model_predicted_percentage"]
    return f"Estimated semantic coverage: {percentage}%"


demo = gr.Interface(
    fn=compare_diffs,
    inputs=[
        gr.Code(label="Suggested diff", language=None),
        gr.Code(label="Merged PR diff", language=None),
    ],
    outputs=gr.Textbox(label="Result"),
    title="Semantic PR Suggestion Coverage",
    description=(
        "Experimental estimate of semantic overlap. "
        "The score does not prove that a suggestion caused a code change."
    ),
)


if __name__ == "__main__":
    demo.launch()
```

Add an automated smoke test before publishing.

## Dependencies

Create `requirements.txt` in the deployment repository:

```text
gradio
-e .[structural]
```

Also copy the project's `pyproject.toml` so that the editable package installation works. For reproducible deployment, replace the unbounded `gradio` dependency with a tested version range before publishing.

The structural dependency group enables the local AST and Tree-sitter features used while scoring supported languages. It does not install the much larger training or embedding stacks.

## Space Configuration

Create the Space README with this YAML header at the very top:

```yaml
---
title: Semantic PR Suggestion Coverage
emoji: 🔎
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: "<tested-version>"
app_file: app.py
pinned: false
python_version: "3.11"
---
```

Replace `<tested-version>` with the same Gradio version used in `requirements.txt`.

## Publish

1. Sign in to Hugging Face and create a new Space.
2. Select **Gradio** as the SDK and **CPU Basic** as the free hardware.
3. Clone the Space repository shown on its setup page.
4. Copy the minimal deployment files into that repository.
5. Commit and push the files to the Space repository.
6. Open the Space's build log and wait for the application to become ready.
7. Test empty input, a known example, malformed diffs, and a large input.

Hugging Face rebuilds the application automatically after each push.

## Local Check Before Publishing

From the deployment repository, install and run the application:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

Open the local URL printed by Gradio and verify the result against a known repository example.

## Alternative Deployment Targets

- **PyPI:** Publish the package for installation with `pip`; this does not provide a hosted interface or API.
- **Render, Railway, or similar:** Wrap inference in FastAPI when a JSON API is more important than a demo UI. Free-tier availability and sleep behavior vary.
- **GitHub Pages:** Suitable only for static documentation. It cannot execute the Python model.
- **Internal hosting:** Use this instead of a public free service when users will submit confidential source code or pull-request diffs.

## Production Follow-up

Before treating the demo as a production service:

- Pin every dependency and build from a lock file.
- Add request-size limits, timeouts, health checks, and structured error handling.
- Add rate limiting and authentication if the service is not public.
- Keep secrets in the hosting provider's secret store, never in Git.
- Monitor latency, errors, memory use, and model-version changes.
- Display the model-card limitations beside every prediction.
