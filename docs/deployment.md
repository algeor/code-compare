# Deployment

**Status:** current demo deployment guide; production release deployment is planned

**Audience:** demo operators and release engineers

**Purpose:** run or deploy the supported demo path without training or historical research code

## Current Deployment Shape

The current demo is a Gradio app backed by `AnalysisService`.

It shows:

- deterministic diff evidence;
- weak local percentage model output;
- deterministic-template grounded explanations;
- model versions, artifact hashes, warnings, and raw JSON.

The app entry points are:

- `src/pr_suggestion_metrics/demo_gradio.py` for the package CLI;
- `space/app.py` for Hugging Face Spaces.

This is a demonstration path, not a validated production service. The checked-in demo model is trained on weak local labels and must not be presented as production-grade validation evidence.

For the target CodeBERT explanation path, see [`explanation-model-design.md`](explanation-model-design.md).

## Run Locally

From the repository root:

```bash
uv sync --locked --all-extras
uv run --locked --extra demo pr-suggestion-demo
```

Optional explicit host and port:

```bash
uv run --locked --extra demo pr-suggestion-demo --server-name 127.0.0.1 --server-port 7860
```

The default model directory is:

```text
models/pr_suggestion_coverage/demo_weak_local/model
```

To use a different trusted model bundle:

```bash
uv run --locked --extra demo pr-suggestion-demo --model-dir /secure/trusted-percentage-model
```

## Hugging Face Space

The repository already includes the Space shim:

```text
space/app.py
```

For a Space deployment, configure Hugging Face to use that file as the app entry point. The app imports `build_app()` and loads the demo model from the repository-local demo path.

Use `space/README.md` for the short operator notes.

## What To Include

For a small demo deployment repository, include only what runtime needs:

```text
space/app.py
README.md
pyproject.toml
uv.lock or a generated runtime lock file
src/pr_suggestion_metrics/
models/pr_suggestion_coverage/demo_weak_local/model/
models/pr_suggestion_coverage/demo_weak_local/README.md
```

Do not upload the complete research workspace unless the deployment is intentionally private and approved. Large datasets, notebooks, reports, archived experiments, and training artifacts are not needed at runtime.

Keep verified model files together:

```text
model.joblib
feature_schema.json
artifact_manifest.json
```

The manifest provides integrity checks, not publisher authentication. Load `joblib` artifacts only from a trusted source.

## Demo Behavior To Verify

Before sharing the demo, test these cases:

- empty input returns a clean error;
- the sample addition produces a predicted result;
- malformed diffs produce abstention or structured errors;
- unsupported edit shapes abstain instead of inventing a score;
- raw JSON includes schema versions, input hashes, artifact hashes, warnings, and explanation output.

## Security And Privacy

- Do not send confidential source code, private diffs, credentials, or proprietary model artifacts to a public Space.
- Do not log raw diffs in hosted environments.
- Keep secrets in the hosting provider's secret store, never in Git.
- Add request size limits before exposing the app beyond a controlled demo audience.

## Production Follow-Up

Before treating the demo as a production service:

- replace the weak demo model with a release artifact from a frozen benchmark;
- authenticate model distribution outside local hashes;
- pin dependencies and build from a lock file;
- add health checks, timeouts, structured errors, rate limits, and safe logging;
- display model-card limitations beside every result;
- keep training code and archived research out of the hosted process;
- validate the CodeBERT explanation provider separately from the percentage estimator.

## Alternative Deployment Targets

- **PyPI:** package distribution only; no hosted interface.
- **Render, Railway, or similar:** useful when a JSON API matters more than a demo UI.
- **GitHub Pages:** documentation only; it cannot execute Python inference.
- **Internal hosting:** preferred when users submit confidential source code or pull-request diffs.
