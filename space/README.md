# PR Suggestion Coverage Demo

Interview demo for PR suggestion coverage analysis.

This Space wraps the local `AnalysisService` and shows:

- deterministic diff evidence
- weak local percentage model output
- template-based grounded explanation
- artifact hashes and model versions in the raw result

Important: this is not human-validated release science. The percentage model is trained on weak local Phase 5-derived labels.

Local run from the repository root:

```bash
uv run --locked --extra demo pr-suggestion-demo
```

Interview flow:

1. Paste a suggested diff.
2. Paste the merged PR diff.
3. Click Analyze.
4. Show the coverage card first.
5. Open the raw JSON to show hashes, versions, and evidence.

For Hugging Face Spaces, use Gradio and set the app file to `space/app.py`.
