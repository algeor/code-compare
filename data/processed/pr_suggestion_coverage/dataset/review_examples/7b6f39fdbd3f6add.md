# 7b6f39fdbd3f6add

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/48
Suggested label: 35%
File overlap: 1.0
Changed-line overlap: 0.0

## Suggested diff
```diff
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@
+- Bind the identifier for the current unit of work as a context variable on every log message when the current operation is in the context of a specific inspection; for this project that variable is `inspection_id`. Omit it when no inspection is in scope
```

## Landed PR diff
```diff
diff --git a/CLAUDE.md b/CLAUDE.md
index 549f2130..45cd55cf 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -130,6 +130,15 @@ Comments belong in exactly five situations:
 
 In every case the comment answers: **"Why didn't you do the obvious thing?"** — and names the exact consequence of doing it the naive way.
 
+## Logging
+
+- Use **structlog** for all logging — never the standard `logging` module directly
+- Bind `inspection_id` as a context variable on every log message when the current operation is in the context of a specific inspection; omit it when no inspection is in scope
+- Use `structlog.contextvars.bound_contextvars(inspection_id=...)` as a context manager to scope `inspection_id` to an operation — it restores the previous context on exit even if an exception is raised, which is critical for Temporal activities where thread pool workers are reused and leftover context from a previous activity would bleed into the next one
+- Log at the right level: `debug` for internal state, `info` for significant lifecycle events, `warning` for recoverable anomalies, `error` for failures that need attention
+- Prefer structured key-value pairs over interpolated strings: `log.info("Step completed", step_id=step_id, status=status)` not `log.info(f"step {step_id} completed with {status}")`
+- Write log messages as normal sentences with a capital first letter, not key-like strings: `"Step completed"` not `"step_completed"`
+
 ## Configuration and Environment
 
 - Use **Pydantic Settings** (`pydantic-settings`, `BaseSettings`) for all configuration — never `os.environ` or `os.getenv` directly in application code

```
