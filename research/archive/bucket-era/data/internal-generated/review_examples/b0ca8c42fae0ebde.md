# b0ca8c42fae0ebde

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/77
Suggested label: 100%
File overlap: 1.0
Changed-line overlap: 1.0

## Suggested diff
```diff
--- a/fl_control_plane/temporal/job_polling.py
+++ b/fl_control_plane/temporal/job_polling.py
@@
+if terminal_status is not None:
+                pod_logs = await fetch_pod_logs(job_name)
+                log.info(
+                    "Kubernetes Job finished",
+                    job_name=job_name,
+                    job_kind=job_kind,
+                    status=terminal_status,
+                    **log_context,
+                )
+                return K8sJobPollResult(status=terminal_status, pod_logs=pod_logs)
```

## Landed PR diff
```diff
diff --git a/CLAUDE.md b/CLAUDE.md
index bf4681a8..1ec02fc1 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -1,5 +1,5 @@
 # Python Code Style Guide
-
+ 
 ** READ docs/design/FL_Architecture_Design.md FIRST **
 
 @docs/design/FL_Architecture_Design.md
diff --git a/chart/templates/deployment.yaml b/chart/templates/deployment.yaml
index 21f6124c..2d8c57a1 100644
--- a/chart/templates/deployment.yaml
+++ b/chart/templates/deployment.yaml
@@ -200,9 +200,11 @@ spec:
             - name: EE_AGENT_IMAGE_PULL_SECRET
               value: {{ .Values.imagePullSecret.name | default "" | quote }}
             - name: EE_JOB_ACTIVE_DEADLINE_SECONDS
-              value: {{ .Values.executionEngine.jobActiveDeadlineSeconds | default 3600 | quote }}
+              value: {{ .Values.executionEngine.jobActiveDeadlineSeconds | default 21600 | quote }}
             - name: EE_JOB_POLL_TIMEOUT_SECONDS
-              value: {{ .Values.executionEngine.jobPollTimeoutSeconds | default 3660 | quote }}
+              value: {{ .Values.executionEngine.jobPollTimeoutSeconds | default 4500 | quote }}
+            - name: EE_JOB_POLL_CLEANUP_GRACE_SECONDS
+              value: {{ .Values.executionEngine.jobPollCleanupGraceSeconds | default 120 | quote }}
             - name: EE_JOB_TTL_SECONDS_AFTER_FINISHED
               value: {{ .Values.executionEngine.jobTtlSecondsAfterFinished | default 3600 | quote }}
             - name: EE_JOB_BACKOFF_LIMIT
diff --git a/chart/templates/dispatcher-rbac.yaml b/chart/templates/dispatcher-rbac.yaml
index ad43d419..56bdd257 100644
--- a/chart/templates/dispatcher-rbac.yaml
+++ b/chart/templates/dispatcher-rbac.yaml
@@ -15,7 +15,7 @@ metadata:
 rules:
   - apiGroups: ["batch"]
     resources: ["jobs"]
-    verbs: ["create", "get", "delete"]
+    verbs: ["create", "get", "patch"]
   - apiGroups: ["external-secrets.io"]
     resources: ["externalsecrets"]
     verbs: ["create", "patch"]
diff --git a/chart/values.yaml b/chart/values.yaml
index 7fcde913..b1f53c4f 100644
--- a/chart/values.yaml
+++ b/chart/values.yaml
@@ -54,10 +54,14 @@ handlerConfigRepository:
 executionEngine:
   # Default container image for agent_task jobs (overridden per-handler by the CR).
   agentImagePullPolicy: "IfNotPresent"
-  jobActiveDeadlineSeconds: 3600
-  # Client-side polling timeout — slightly above jobActiveDeadlineSeconds so
-  # Kubernetes always marks the job terminal before the client gives up.
-  jobPollTimeoutSeconds: 3660
+  # Hard k8s safety deadline for all execution-engine Jobs.
+  jobActiveDeadlineSeconds: 21600
+  # Client-side polling timeout. When reached, the poll activity captures logs,
+  # suspends the still-running Job, and returns a failed result.
+  jobPollTimeoutSeconds: 4500
+  # Extra Temporal activity runtime after the client-side timeout for log fetch
+  # and Job suspension.
+  jobPollCleanupGraceSeconds: 120
   jobTtlSecondsAfterFinished: 3600
   jobBackoffLimit: 0
   jobPollIntervalSeconds: 10
diff --git a/fl_control_plane/config.py b/fl_control_plane/config.py
index 5e847be3..21a8c9b3 100644
--- a/fl_control_plane/config.py
+++ b/fl_control_plane/config.py
@@ -4,7 +4,7 @@
 
 import re
 
-from pydantic import SecretStr, field_validator, model_validator
+from pydantic import Field, SecretStr, field_validator, model_validator
 
 from fl_shared import SharedSettings
 
@@ -43,6 +43,17 @@ class ServerSettings(SharedSettings):
     temporal_task_queue: str = "pipeline-inspection"
     tenant_id: str = "default"
 
+    # Execution-engine poll budgets captured into new workflow inputs. The
+    # workflow itself must not read env vars during replay.
+    execution_engine_job_poll_timeout_seconds: int = Field(
+        default=4500,
+        validation_alias="EE_JOB_POLL_TIMEOUT_SECONDS",
+    )
+    execution_engine_job_poll_cleanup_grace_seconds: int = Field(
+        default=120,
+        validation_alias="EE_JOB_POLL_CLEANUP_GRACE_SECONDS",
+    )
+
     # GitHub tokens for WIP detection — WDF for internal GitHub, TOOL for github.tools.sap
     github_wdf_token: SecretStr | None = None
     github_tool_token: SecretStr | None = None
diff --git a/fl_control_plane/execution_engine/config.py b/fl_control_plane/execution_engine/config.py
index af747626..a23536f3 100644
--- a/fl_control_plane/execution_engine/config.py
+++ b/fl_control_plane/execution_engine/config.py
@@ -28,14 +28,17 @@ class Settings(BaseSettings):
         config_repo_url: URL of the Failure Checks Repo that holds handler skill and
             MCP config files. Passed to every agent_task job as CONFIG_REPO_URL.
         config_repo_commitish: Branch or commit to check out in the config repo.
-        job_active_deadline_seconds: Hard wall-clock timeout for the entire Job.
-            Kubernetes terminates the pod and marks the Job failed when exceeded.
-            Keep this generous (default 3600s) — it is a safety net, not the
-            primary timeout mechanism.
+        job_active_deadline_seconds: Hard wall-clock safety deadline for all
+            execution-engine Jobs. Keep this generous (default 21600s / 6 h) so
+            Temporal polling can collect logs and clean up before Kubernetes
+            deletes the pod.
         job_poll_timeout_seconds: Client-side deadline for the dispatcher's poll
-            loop. Raised as TimeoutError if the job has not reached a terminal
-            state within this window. Should be set equal to or slightly above
-            job_active_deadline_seconds so Kubernetes always wins the race.
+            loop. If the job has not reached a terminal state within this window,
+            the poll activity captures pod logs, suspends the Job, and returns
+            a failed result.
+        job_poll_cleanup_grace_seconds: Extra Temporal activity runtime reserved
+            after the client-side poll timeout for log collection and job
+            suspension.
         job_ttl_seconds_after_finished: How long Kubernetes retains a completed or
             failed Job object before garbage-collecting it.
         job_backoff_limit: Maximum pod restart attempts before the Job is marked failed.
@@ -67,8 +70,9 @@ class Settings(BaseSettings):
     secret_store_name: str = "vault-clusters"
     config_repo_url: str
     config_repo_commitish: str = "main"
-    job_active_deadline_seconds: int = 3600
-    job_poll_timeout_seconds: int = 3660
+    job_active_deadline_seconds: int = 21600
+    job_poll_timeout_seconds: int = 4500
+    job_poll_cleanup_grace_seconds: int = 120
     job_ttl_seconds_after_finished: int = 3600
     job_backoff_limit: int = 0
     job_poll_interval_seconds: int = 10
diff --git a/fl_control_plane/execution_engine/dispatcher.py b/fl_control_plane/execution_engine/dispatcher.py
index 7b39e5e0..842232b1 100644
--- a/fl_control_plane/execution_engine/dispatcher.py
+++ b/fl_control_plane/execution_engine/dispatcher.py
@@ -1,4 +1,4 @@
-"""Dispatch FaultHandler jobs to Kubernetes and poll for completion."""
+"""Dispatch FaultHandler jobs to Kubernetes."""
 
 from __future__ import annotations
 
@@ -10,8 +10,6 @@
 from uuid import uuid4
 
 from kubernetes_asyncio import client
-from kubernetes_asyncio import config as k8s_config
-from kubernetes_asyncio.client.exceptions import ApiException
 
 from fl_control_plane.execution_engine.config import get_settings
 from fl_control_plane.execution_engine.models import HandlerExecution
@@ -21,14 +19,6 @@
 
 log = logging.getLogger(__name__)
 
-_K8S_CONDITION_TRUE = "True"
-_K8S_CONDITION_COMPLETE = "Complete"
-_K8S_CONDITION_FAILED = "Failed"
-_STATUS_SUCCEEDED = "succeeded"
-_STATUS_FAILED = "failed"
-_IMAGE_PULL_ERROR_REASONS = {"ImagePullBackOff", "ErrImagePull", "InvalidImageName"}
-_LOG_TAIL_LINES = 400
-
 
 @dataclass
 class _JobSpec:  # pylint: disable=too-many-instance-attributes
@@ -50,14 +40,6 @@ class _JobSpec:  # pylint: disable=too-many-instance-attributes
     hdlf_inspection_cert_secret_name: str | None = None
 
 
-async def _load_k8s() -> None:
-    """Load k8s credentials — in-cluster service account in prod, kubeconfig locally."""
-    try:
-        k8s_config.load_incluster_config()  # type: ignore[no-untyped-call]
-    except k8s_config.ConfigException:
-        await k8s_config.load_kube_config()
-
-
 def _make_job_spec(
     handler: FaultHandlerSpec,
     inspection_id: str,
@@ -389,94 +371,6 @@ async def _submit_job(js: _JobSpec) -> HandlerExecution:
     )
 
 
-async def _job_status(job_name: str) -> str | None:
-    """Return the terminal status of a k8s Job, or None if still running."""
-    async with client.ApiClient() as api_client:
-        job = await client.BatchV1Api(api_client).read_namespaced_job(job_name, get_settings().namespace)
-    if job.status is None:
-        return None
-    for condition in job.status.conditions or []:
-        if condition.status == _K8S_CONDITION_TRUE:
-            if condition.type == _K8S_CONDITION_COMPLETE:
-                return _STATUS_SUCCEEDED
-            if condition.type == _K8S_CONDITION_FAILED:
-                return _STATUS_FAILED
-    return None
-
-
-async def _check_for_image_pull_error(job_name: str) -> str | None:
-    """Return the waiting reason if any container is stuck on an image pull error, else None.
-
-    Queries pods by the ``job-name`` label k8s attaches automatically to every pod
-    spawned by a Job. ``container_statuses`` is absent until the container is first
-    scheduled, so every field in the chain is guarded against None.
-    """
-    async with client.ApiClient() as api_client:
-        pods = await client.CoreV1Api(api_client).list_namespaced_pod(
-            get_settings().namespace,
-            label_selector=f"job-name={job_name}",
-        )
-    for pod in pods.items:
-        for cs in (pod.status and pod.status.container_statuses) or []:
-            if cs.state and cs.state.waiting and cs.state.waiting.reason in _IMAGE_PULL_ERROR_REASONS:
-                return cs.state.waiting.reason
-    return None
-
-
-async def _delete_job(job_name: str) -> None:
-    """Delete a k8s Job and its pods with foreground cascading deletion.
-
-    Kept for future cleanup paths, but image-pull failures intentionally do not
-    call it today because operators need the failed Job to inspect which image
-    could not be downloaded.
-    """
-    try:
-        async with client.ApiClient() as api_client:
-            await client.BatchV1Api(api_client).delete_namespaced_job(
-                job_name,
-                get_settings().namespace,
-                propagation_policy="Foreground",
-            )
-    except ApiException:
-        log.warning(
-            "Failed to delete job %s — check RBAC (jobs delete verb)",
-            job_name,
-            exc_info=True,
-        )
-
-
-async def _fetch_pod_logs(job_name: str) -> str | None:
-    """Return the last _LOG_TAIL_LINES lines of logs from the job's pod.
-
-    Queries pods by the ``job-name`` label that k8s attaches automatically to
-    every pod spawned by a Job. Handler jobs run with ``backoff_limit=0`` so
-    there is exactly one pod per job. Returns ``None`` when logs are permanently
-    unavailable (missing pod, already GC'd, RBAC denial), but lets transient k8s
-    API errors propagate so Temporal can retry before the pod is garbage-collected.
-    """
-    try:
-        async with client.ApiClient() as api_client:
-            core = client.CoreV1Api(api_client)
-            pods = await core.list_namespaced_pod(
-                get_settings().namespace,
-                label_selector=f"job-name={job_name}",
-            )
-            if not pods.items:
-                return None
-            pod_name = pods.items[0].metadata.name
-            logs: str = await core.read_namespaced_pod_log(
-                pod_name,
-                get_settings().namespace,
-                tail_lines=_LOG_TAIL_LINES,
-            )
-            return logs
-    except ApiException as exc:
-        if exc.status in (403, 404):
-            log.warning("pod_log_fetch_failed", exc_info=True, extra={"job_name": job_name})
-            return None
-        raise
-
-
 # pylint: disable=too-many-arguments,too-many-positional-arguments
 def build_finalizer_job_spec(
     inspection_id: str,
diff --git a/fl_control_plane/execution_engine/job_activity.py b/fl_control_plane/execution_engine/job_activity.py
index b780f6c7..ca9362ac 100644
--- a/fl_control_plane/execution_engine/job_activity.py
+++ b/fl_control_plane/execution_engine/job_activity.py
@@ -3,9 +3,6 @@
 
 from __future__ import annotations
 
-import asyncio
-import time
-
 import structlog
 from kubernetes_asyncio.client.exceptions import ApiException
 from temporalio import activity
@@ -13,10 +10,6 @@
 
 from fl_control_plane.execution_engine.config import get_settings
 from fl_control_plane.execution_engine.dispatcher import (
-    _check_for_image_pull_error,
-    _fetch_pod_logs,
-    _job_status,
-    _load_k8s,
     _make_job_spec,
     _submit_job,
 )
@@ -24,12 +17,14 @@
     patch_certificate_owner,
     provision_inspection_access,
 )
+from fl_control_plane.execution_engine.k8s_jobs import load_k8s
 from fl_control_plane.execution_engine.models import (
     HandlerExecutionResult,
     HandlerJobSubmission,
     SubmitHandlerJobRequest,
 )
 from fl_control_plane.temporal.base_activity import run_with_heartbeat
+from fl_control_plane.temporal.job_polling import poll_k8s_job_until_terminal
 
 log = structlog.get_logger(__name__)
 
@@ -58,7 +53,7 @@ async def submit_handler_job_activity(
             Temporal will retry with exponential backoff.
     """
     async with run_with_heartbeat():
-        await _load_k8s()
+        await load_k8s()
 
         job_spec = _make_job_spec(
             request.handler,
@@ -149,68 +144,25 @@ async def poll_handler_job_activity(
 
     Raises:
         ApplicationError: Non-retryable (``type="InvalidInput"``) for 4xx k8s errors.
-        ApiException: For 5xx / network errors during polling — Temporal retries.
+        ApiException: For 5xx / network errors during status polling — Temporal
+            retries before the client-side poll timeout is reached.
     """
-    deadline = time.monotonic() + get_settings().job_poll_timeout_seconds
-
-    async with run_with_heartbeat():
-        while True:
-            # Re-load on every iteration: projected SA tokens rotate (default 1h)
-            # and load_incluster_config reads the token file fresh each call.
-            await _load_k8s()
-            try:
-                terminal_status, image_pull_error = await asyncio.gather(
-                    _job_status(submission.job_name),
-                    _check_for_image_pull_error(submission.job_name),
-                )
-            except ApiException as exc:
-                if exc.status is not None and 400 <= exc.status < 500:
-                    raise ApplicationError(
-                        f"k8s 4xx reading job {submission.job_name!r}: {exc.reason}",
-                        type="InvalidInput",
-                        non_retryable=True,
-                    ) from exc
-                raise
-
-            if image_pull_error:
-                # Keep the Job for debugging so operators can inspect which image failed to download.
-                # await _delete_job(submission.job_name)
-                raise ApplicationError(
-                    f"Job {submission.job_name!r} terminated: image pull failed "
-                    f"({image_pull_error}). Check EE_AGENT_IMAGE.",
-                    type="InvalidInput",
-                    non_retryable=True,
-                )
-
-            if terminal_status is not None:
-                pod_logs = await _fetch_pod_logs(submission.job_name)
-                log.info(
-                    "handler_job_finished",
-                    job_name=submission.job_name,
-                    execution_id=submission.execution_id,
-                    fault_id=submission.fault_id,
-                    handler_name=submission.handler_name,
-                    status=terminal_status,
-                )
-                return HandlerExecutionResult(
-                    execution_id=submission.execution_id,
-                    fault_id=submission.fault_id,
-                    handler_name=submission.handler_name,
-                    status=terminal_status,
-                    pod_logs=pod_logs,
-                )
-
-            if time.monotonic() >= deadline:
-                log.warning(
-                    "handler_job_client_timeout",
-                    job_name=submission.job_name,
-                    job_active_deadline_seconds=get_settings().job_poll_timeout_seconds,
-                )
-                raise ApplicationError(
-                    f"Client-side poll timeout after {get_settings().job_poll_timeout_seconds}s"
-                    " — k8s may not have reported terminal status",
-                    type="PollTimeout",
-                )
-
-            activity.heartbeat({"job_name": submission.job_name})
-            await asyncio.sleep(get_settings().job_poll_interval_seconds)
+    poll_result = await poll_k8s_job_until_terminal(
+        job_name=submission.job_name,
+        job_description="job",
+        job_kind="handler",
+        log_context={
+            "execution_id": submission.execution_id,
+            "fault_id": submission.fault_id,
+            "handler_name": submission.handler_name,
+        },
+    )
+    return HandlerExecutionResult(
+        execution_id=submission.execution_id,
+        fault_id=submission.fault_id,
+        handler_name=submission.handler_name,
+        status=poll_result.status,
+        failure_reason=poll_result.failure_reason,
+        timed_out=poll_result.timed_out,
+        pod_logs=poll_result.pod_logs,
+    )
diff --git a/fl_control_plane/execution_engine/k8s_jobs.py b/fl_control_plane/execution_engine/k8s_jobs.py
new file mode 100644
index 00000000..c50ef2a0
--- /dev/null
+++ b/fl_control_plane/execution_engine/k8s_jobs.py
@@ -0,0 +1,117 @@
+"""Generic Kubernetes Job operations used by execution-engine activities."""
+
+from __future__ import annotations
+
+from typing import Literal
+
+import structlog
+from kubernetes_asyncio import client
+from kubernetes_asyncio import config as k8s_config
+from kubernetes_asyncio.client.exceptions import ApiException
+
+from fl_control_plane.execution_engine.config import get_settings
+
+log = structlog.get_logger(__name__)
+
+K8sJobStatus = Literal["succeeded", "failed"]
+
+_K8S_CONDITION_TRUE = "True"
+_K8S_CONDITION_COMPLETE = "Complete"
+_K8S_CONDITION_FAILED = "Failed"
+_STATUS_SUCCEEDED: K8sJobStatus = "succeeded"
+_STATUS_FAILED: K8sJobStatus = "failed"
+_IMAGE_PULL_ERROR_REASONS = {"ImagePullBackOff", "ErrImagePull", "InvalidImageName"}
+_LOG_TAIL_LINES = 400
+
+
+async def load_k8s() -> None:
+    """Load k8s credentials from the in-cluster service account or local kubeconfig."""
+    try:
+        k8s_config.load_incluster_config()  # type: ignore[no-untyped-call]
+    except k8s_config.ConfigException:
+        await k8s_config.load_kube_config()
+
+
+async def job_status(job_name: str) -> K8sJobStatus | None:
+    """Return the terminal status of a k8s Job, or None if still running."""
+    async with client.ApiClient() as api_client:
+        job = await client.BatchV1Api(api_client).read_namespaced_job(job_name, get_settings().namespace)
+    if job.status is None:
+        return None
+    for condition in job.status.conditions or []:
+        if condition.status == _K8S_CONDITION_TRUE:
+            if condition.type == _K8S_CONDITION_COMPLETE:
+                return _STATUS_SUCCEEDED
+            if condition.type == _K8S_CONDITION_FAILED:
+                return _STATUS_FAILED
+    return None
+
+
+async def check_for_image_pull_error(job_name: str) -> str | None:
+    """Return a waiting image-pull reason for any Job pod container, else None.
+
+    Queries pods by the ``job-name`` label k8s attaches automatically to every pod
+    spawned by a Job. ``container_statuses`` is absent until the container is first
+    scheduled, so every field in the chain is guarded against None.
+    """
+    async with client.ApiClient() as api_client:
+        pods = await client.CoreV1Api(api_client).list_namespaced_pod(
+            get_settings().namespace,
+            label_selector=f"job-name={job_name}",
+        )
+    for pod in pods.items:
+        for container_status in (pod.status and pod.status.container_statuses) or []:
+            state = container_status.state
+            if state and state.waiting and state.waiting.reason in _IMAGE_PULL_ERROR_REASONS:
+                return state.waiting.reason
+    return None
+
+
+async def suspend_job(job_name: str) -> None:
+    """Suspend a k8s Job so active pods stop while the Job object is retained."""
+    try:
+        async with client.ApiClient() as api_client:
+            await client.BatchV1Api(api_client).patch_namespaced_job(
+                job_name,
+                get_settings().namespace,
+                {"spec": {"suspend": True}},
+            )
+    except ApiException:
+        log.warning(
+            "Failed to suspend Kubernetes Job",
+            job_name=job_name,
+            exc_info=True,
+        )
+
+
+async def fetch_pod_logs(job_name: str) -> str | None:
+    """Return the last log lines from the Job's pod.
+
+    Queries pods by the ``job-name`` label that k8s attaches automatically to
+    every pod spawned by a Job. Execution-engine jobs run with ``backoff_limit=0``
+    so there is exactly one pod per job. Returns ``None`` when logs are
+    permanently unavailable (missing pod, already GC'd, RBAC denial), but lets
+    transient k8s API errors propagate so Temporal can retry before the pod is
+    garbage-collected.
+    """
+    try:
+        async with client.ApiClient() as api_client:
+            core = client.CoreV1Api(api_client)
+            pods = await core.list_namespaced_pod(
+                get_settings().namespace,
+                label_selector=f"job-name={job_name}",
+            )
+            if not pods.items:
+                return None
+            pod_name = pods.items[0].metadata.name
+            logs: str = await core.read_namespaced_pod_log(
+                pod_name,
+                get_settings().namespace,
+                tail_lines=_LOG_TAIL_LINES,
+            )
+            return logs
+    except ApiException as exc:
+        if exc.status in (403, 404):
+            log.warning("Pod log fetch failed", job_name=job_name, exc_info=True)
+            return None
+        raise
diff --git a/fl_control_plane/execution_engine/local_testing/trigger.py b/fl_control_plane/execution_engine/local_testing/trigger.py
index 86143ebf..2f1faa3b 100644
--- a/fl_control_plane/execution_engine/local_testing/trigger.py
+++ b/fl_control_plane/execution_engine/local_testing/trigger.py
@@ -6,11 +6,12 @@
   → Handler Orchestrator → [trigger mechanism TBD] → Execution Engine
 
 None of those components upstream of the Execution Engine are built yet.
-This script simulates the built pieces so the Execution Engine can be exercised locally:
+This script simulates all of them so the Execution Engine can be exercised locally:
 
-  1. Creates Inspection + FailedStage rows            (stand-in for Ingestion API + Data Extractor)
-  2. Calls evaluate() — the real Handler Orchestrator
-  3. Calls dispatch_all() — the real Execution Engine
+  1. Seeds a local FaultHandler row                   (stand-in for k8s operator)
+  2. Creates Inspection + FailedStage rows            (stand-in for Ingestion API + Data Extractor)
+  3. Calls evaluate() — the real Handler Orchestrator
+  4. Calls dispatch_all() — the local Execution Engine wrapper
 
 Steps 1-3 and the call to dispatch_all() will be replaced by the production
 components when they are built. This file will be deleted at that point.
@@ -29,20 +30,47 @@
 import json
 import os
 import sys
+from collections.abc import AsyncIterator
 from pathlib import Path
 
 from alembic import command
 from alembic.config import Config
 from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
 
-from fl_control_plane.database import FailedStage, Inspection
-from fl_control_plane.execution_engine.dispatcher import (  # pylint: disable=no-name-in-module
-    dispatch_all,  # not yet implemented in production
-)
+from fl_control_plane.database import FailedStage, FaultHandler, Inspection
+from fl_control_plane.execution_engine import dispatcher
+from fl_control_plane.execution_engine.models import HandlerExecution
 from fl_control_plane.handler_orchestrator.orchestrator import evaluate
+from fl_shared.cr_models import FaultHandlerSpec
 
 ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
 
+_LOCAL_HANDLER_SPEC = {
+    "fault_id": "local-agent-task",
+    "execution": {
+        "type": "agent_task",
+        "task": "Analyze the failed pipeline using the available inspection data.",
+        "skills": [],
+        "mcps": [],
+    },
+    "applicability": {
+        "failure_match": {"strategy": "pipeline_scoped", "match": None},
+        "infrastructure": None,
+    },
+}
+
+
+class _LocalInspectionReader:
+    """Serve optional local log text without requiring an HDLF snapshot."""
+
+    async def stream_stage_log(self, _inspection_id: str, _stage_dir: str) -> AsyncIterator[bytes]:
+        """Yield the configured local stage log."""
+        yield os.environ.get("FL_TEST_STAGE_LOG", "").encode()
+
+    async def stream_console_log(self, _inspection_id: str) -> AsyncIterator[bytes]:
+        """Yield the configured local pipeline log."""
+        yield os.environ.get("FL_TEST_PIPELINE_LOG", "").encode()
+
 
 def _alembic_cfg(sync_conn) -> Config:
     """Wire an Alembic Config to an existing sync connection."""
@@ -52,6 +80,25 @@ def _alembic_cfg(sync_conn) -> Config:
     return cfg
 
 
+async def dispatch_all(
+    inspection_id: str,
+    handlers: list[FaultHandlerSpec],
+    repo_url: str = "",
+    commitish: str = "HEAD",
+) -> list[HandlerExecution]:
+    """Submit one Kubernetes Job for each selected handler in local testing."""
+    submissions = []
+    for handler in handlers:
+        job_spec = dispatcher._make_job_spec(  # pylint: disable=protected-access
+            handler,
+            inspection_id,
+            repo_url=repo_url,
+            commitish=commitish,
+        )
+        submissions.append(await dispatcher._submit_job(job_spec))  # pylint: disable=protected-access
+    return submissions
+
+
 async def run() -> None:
     """Run the full trigger workflow: seed, inspect, evaluate, dispatch."""
     engine = create_async_engine("sqlite+aiosqlite:///:memory:")
@@ -61,6 +108,25 @@ async def run() -> None:
     session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
 
     async with session_factory() as db:
+        db.add(
+            FaultHandler(
+                cr_id="local/local-agent-task",
+                cr_name="local-agent-task",
+                cr_namespace="local-testing",
+                fault_id="local-agent-task",
+                execution_type="agent_task",
+                strategy="pipeline_scoped",
+                ci_systems=None,
+                repo_patterns=None,
+                trigger_scope="all",
+                merge_target_branch=None,
+                spec_json=json.dumps(_LOCAL_HANDLER_SPEC),
+                resource_version="local",
+                is_active=True,
+            )
+        )
+        await db.flush()
+
         inspection = Inspection(
             status="IN_PROGRESS",
             pipeline_url=os.environ["FL_TEST_PIPELINE_URL"],
@@ -79,11 +145,11 @@ async def run() -> None:
         )
         await db.commit()
 
-        result = await evaluate(inspection.id, db)
+        result = await evaluate(inspection.id, db, _LocalInspectionReader())
 
     print(f"selected handlers: {len(result.handlers)}")
-    for h in result.handlers:
-        print(f"  - {h.metadata.name} (fault_id={h.spec.fault_id})")
+    for handler in result.handlers:
+        print(f"  - {handler.fault_id}")
     print()
     for d in result.decisions:
         print(f"  {d.result:20s} {d.handler_name}: {d.reason}")
@@ -97,6 +163,8 @@ async def run() -> None:
     findings = await dispatch_all(
         inspection_id=inspection.id,
         handlers=result.handlers,
+        repo_url=result.github_repo_url or "",
+        commitish=result.commit_id or "HEAD",
     )
 
     for f in findings:
diff --git a/fl_control_plane/execution_engine/models.py b/fl_control_plane/execution_engine/models.py
index eeeb8d97..d0d3170c 100644
--- a/fl_control_plane/execution_engine/models.py
+++ b/fl_control_plane/execution_engine/models.py
@@ -142,6 +142,9 @@ class HandlerExecutionResult(BaseModel):
             failed. ``None`` on ``"succeeded"``. Set to the k8s Job condition
             ``message`` field when available, or to the activity error message
             when the failure is infrastructure-level.
+        timed_out: ``True`` when the execution-engine client-side poll deadline
+            expired before the k8s Job reached a terminal state. Consumers should
+            use this flag instead of parsing ``failure_reason`` text.
         pod_logs: Last 400 lines of stdout/stderr from the job's pod, captured
             after the job reaches a terminal state. ``None`` when log fetching
             failed or the pod could not be found (e.g. already garbage-collected).
@@ -153,4 +156,5 @@ class HandlerExecutionResult(BaseModel):
     handler_name: str
     status: Literal["succeeded", "failed"]
     failure_reason: str | None = None
+    timed_out: bool = False
     pod_logs: str | None = None
diff --git a/fl_control_plane/finalizer_dispatcher/models.py b/fl_control_plane/finalizer_dispatcher/models.py
index 1a53d003..6ad64a63 100644
--- a/fl_control_plane/finalizer_dispatcher/models.py
+++ b/fl_control_plane/finalizer_dispatcher/models.py
@@ -47,7 +47,8 @@ class FinalizationResult(BaseModel):
             "dispatched" — finalizer Job completed successfully.
             "skipped" — all STOP gate verdicts had require_finalizer=False; no Job created.
             "failed" — finalizer Job exited with a non-zero status.
-            "timed_out" — finalizer Job exceeded active_deadline_seconds.
+            "timed_out" — finalizer Job exceeded active_deadline_seconds or the
+            execution-engine client-side poll timeout.
         finalizer_id: Logical identifier of the selected finalizer, e.g. "default-finalizer".
             None when status is "skipped" (no finalizer was selected).
         finalizer_execution_id: UUID of the `finalizer_execution` row written by this activity.
diff --git a/fl_control_plane/handler_orchestrator/orchestrator.py b/fl_control_plane/handler_orchestrator/orchestrator.py
index 57ba5599..35cfe811 100644
--- a/fl_control_plane/handler_orchestrator/orchestrator.py
+++ b/fl_control_plane/handler_orchestrator/orchestrator.py
@@ -9,7 +9,7 @@
 import json
 import logging
 
-from sqlalchemy import select
+from sqlalchemy import select, true
 from sqlalchemy.ext.asyncio import AsyncSession
 from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
 
@@ -71,9 +71,7 @@ async def _load_pipeline_context(inspection_id: str, db: AsyncSession) -> Pipeli
 
 async def _load_active_handlers(db: AsyncSession) -> list[FaultHandler]:
     """Load all active FaultHandler rows from the DB."""
-    result = await db.execute(
-        select(FaultHandler).where(FaultHandler.is_active == True)  # noqa: E712 # pylint: disable=singleton-comparison
-    )
+    result = await db.execute(select(FaultHandler).where(FaultHandler.is_active == true()))
     return list(result.scalars().all())
 
 
diff --git a/fl_control_plane/ingestion_api/router.py b/fl_control_plane/ingestion_api/router.py
index 60283d27..c941d94a 100644
--- a/fl_control_plane/ingestion_api/router.py
+++ b/fl_control_plane/ingestion_api/router.py
@@ -138,6 +138,8 @@ async def create_inspection(
         correlation_id=None,
         ingestion_timestamp=datetime.now(tz=UTC).isoformat(),
         replay_inspection_id=replay_inspection_id,
+        job_poll_timeout_seconds=settings.execution_engine_job_poll_timeout_seconds,
+        job_poll_cleanup_grace_seconds=settings.execution_engine_job_poll_cleanup_grace_seconds,
     )
 
     workflow_id = f"pipeline-inspection-{settings.tenant_id}-{source_system}-{inspection.id}"
diff --git a/fl_control_plane/temporal/finalize_activity.py b/fl_control_plane/temporal/finalize_activity.py
index be148cd5..0c855cce 100644
--- a/fl_control_plane/temporal/finalize_activity.py
+++ b/fl_control_plane/temporal/finalize_activity.py
@@ -1,9 +1,7 @@
 """Temporal activities for dispatching and polling the finalizer k8s Job."""
 # pylint: disable=duplicate-code
 
-import asyncio
 import json
-import time
 from datetime import UTC, datetime
 
 import structlog
@@ -15,10 +13,6 @@
 from fl_control_plane.database import Inspection, async_session
 from fl_control_plane.execution_engine.config import get_settings
 from fl_control_plane.execution_engine.dispatcher import (
-    _check_for_image_pull_error,
-    _fetch_pod_logs,
-    _job_status,
-    _load_k8s,
     _submit_job,
     build_finalizer_job_spec,
 )
@@ -26,9 +20,11 @@
     patch_certificate_owner,
     provision_inspection_access,
 )
+from fl_control_plane.execution_engine.k8s_jobs import load_k8s
 from fl_control_plane.finalizer_dispatcher.activity import write_finalizer_execution
 from fl_control_plane.finalizer_dispatcher.selector import pick_finalizer, should_dispatch
 from fl_control_plane.temporal.base_activity import run_with_heartbeat
+from fl_control_plane.temporal.job_polling import poll_k8s_job_until_terminal
 from fl_control_plane.temporal.models import (
     FinalizeInspectionRequest,
     FinalizeInspectionResult,
@@ -134,7 +130,7 @@ async def submit_finalizer_job_activity(
 
     started_at = datetime.now(UTC).isoformat()
     async with run_with_heartbeat():
-        await _load_k8s()
+        await load_k8s()
         job_spec.hdlf_inspection_cert_secret_name = await provision_inspection_access(
             inspection_id=request.inspection_id,
             execution_id=execution_id,
@@ -215,9 +211,8 @@ async def poll_finalizer_job_activity(
             is stuck on an image pull error.
         ApplicationError: Non-retryable (``type="InvalidInput"``) for 4xx k8s
             errors while reading job state.
-        ApiException: For 5xx / network errors during polling — Temporal retries.
-        ApplicationError: (``type="PollTimeout"``) when the job does not reach
-            a terminal state within ``job_poll_timeout_seconds``.
+        ApiException: For 5xx / network errors during status polling — Temporal
+            retries before the client-side poll timeout is reached.
     """
     if submission.job_name is None:
         return FinalizerJobResult(
@@ -227,65 +222,24 @@ async def poll_finalizer_job_activity(
             status="skipped",
         )
 
-    deadline = time.monotonic() + get_settings().job_poll_timeout_seconds
-
-    async with run_with_heartbeat():
-        while True:
-            # Re-load on every iteration: projected SA tokens rotate (default 1h).
-            await _load_k8s()
-            try:
-                status, image_pull_error = await asyncio.gather(
-                    _job_status(submission.job_name),
-                    _check_for_image_pull_error(submission.job_name),
-                )
-            except ApiException as exc:
-                if exc.status is not None and 400 <= exc.status < 500:
-                    raise ApplicationError(
-                        f"k8s 4xx reading finalizer job {submission.job_name!r}: {exc.reason}",
-                        type="InvalidInput",
-                        non_retryable=True,
-                    ) from exc
-                raise
-
-            if image_pull_error:
-                raise ApplicationError(
-                    f"Finalizer job {submission.job_name!r} image pull failed "
-                    f"({image_pull_error}). Check EE_AGENT_IMAGE.",
-                    type="InvalidInput",
-                    non_retryable=True,
-                )
-
-            if status is not None:
-                pod_logs = await _fetch_pod_logs(submission.job_name)
-                log.info(
-                    "finalizer_job_finished",
-                    inspection_id=submission.inspection_id,
-                    execution_id=submission.execution_id,
-                    job_name=submission.job_name,
-                    status=status,
-                )
-                return FinalizerJobResult(
-                    execution_id=submission.execution_id,
-                    registry_id=submission.registry_id,
-                    started_at=submission.started_at,
-                    status=status,
-                    pod_logs=pod_logs,
-                )
-
-            if time.monotonic() >= deadline:
-                log.warning(
-                    "finalizer_job_client_timeout",
-                    job_name=submission.job_name,
-                    job_poll_timeout_seconds=get_settings().job_poll_timeout_seconds,
-                )
-                raise ApplicationError(
-                    f"Finalizer job poll timeout after {get_settings().job_poll_timeout_seconds}s",
-                    type="PollTimeout",
-                    non_retryable=True,
-                )
-
-            activity.heartbeat({"job_name": submission.job_name})
-            await asyncio.sleep(get_settings().job_poll_interval_seconds)
+    poll_result = await poll_k8s_job_until_terminal(
+        job_name=submission.job_name,
+        job_description="finalizer job",
+        job_kind="finalizer",
+        log_context={
+            "inspection_id": submission.inspection_id,
+            "execution_id": submission.execution_id,
+        },
+    )
+    return FinalizerJobResult(
+        execution_id=submission.execution_id,
+        registry_id=submission.registry_id,
+        started_at=submission.started_at,
+        status=poll_result.status,
+        failure_reason=poll_result.failure_reason,
+        timed_out=poll_result.timed_out,
+        pod_logs=poll_result.pod_logs,
+    )
 
 
 @activity.defn
@@ -306,7 +260,12 @@ async def mark_inspection_terminal_activity(
     async with async_session() as db:
         if job_result.execution_id is not None and job_result.status != "skipped":
             assert job_result.registry_id is not None  # always set when execution_id is set
-            finalizer_status = "success" if job_result.status == "succeeded" else "failed"
+            if job_result.status == "succeeded":
+                finalizer_status = "success"
+            elif job_result.timed_out:
+                finalizer_status = "timed_out"
+            else:
+                finalizer_status = "failed"
             started_at = _parse_finalizer_started_at(job_result.started_at, finished_at)
             await write_finalizer_execution(
                 session=db,
@@ -314,7 +273,7 @@ async def mark_inspection_terminal_activity(
                 inspection_id=request.finalize_request.inspection_id,
                 registry_id=job_result.registry_id,
                 status=finalizer_status,
-                status_message=None,
+                status_message=job_result.failure_reason,
                 started_at=started_at,
             )
 
diff --git a/fl_control_plane/temporal/job_polling.py b/fl_control_plane/temporal/job_polling.py
new file mode 100644
index 00000000..3b798498
--- /dev/null
+++ b/fl_control_plane/temporal/job_polling.py
@@ -0,0 +1,151 @@
+"""Shared Kubernetes Job polling helpers for Temporal activities."""
+
+from __future__ import annotations
+
+import asyncio
+import time
+from datetime import UTC, datetime
+from typing import Literal
+
+import structlog
+from kubernetes_asyncio.client.exceptions import ApiException
+from pydantic import BaseModel
+from temporalio import activity
+from temporalio.exceptions import ApplicationError
+
+from fl_control_plane.execution_engine.config import get_settings
+from fl_control_plane.execution_engine.k8s_jobs import (
+    check_for_image_pull_error,
+    fetch_pod_logs,
+    job_status,
+    load_k8s,
+    suspend_job,
+)
+from fl_control_plane.temporal.base_activity import run_with_heartbeat
+
+log = structlog.get_logger(__name__)
+
+
+class K8sJobPollResult(BaseModel):
+    """Terminal or client-timeout outcome for one Kubernetes Job poll."""
+
+    status: Literal["succeeded", "failed"]
+    pod_logs: str | None
+    failure_reason: str | None = None
+    timed_out: bool = False
+
+
+def _job_poll_deadline_monotonic(timeout_seconds: int) -> float:
+    """Return a monotonic deadline anchored to the first Temporal schedule time."""
+    try:
+        scheduled_time = activity.info().scheduled_time
+    except RuntimeError:
+        return time.monotonic() + timeout_seconds
+
+    if scheduled_time.tzinfo is None:
+        scheduled_time = scheduled_time.replace(tzinfo=UTC)
+    elapsed_seconds = max(0.0, (datetime.now(UTC) - scheduled_time).total_seconds())
+    return time.monotonic() + max(0.0, timeout_seconds - elapsed_seconds)
+
+
+async def _fetch_logs_and_suspend_job(job_name: str, job_kind: str) -> str | None:
+    """Collect the current pod log tail, then suspend a timed-out Job."""
+    try:
+        pod_logs = await fetch_pod_logs(job_name)
+    except ApiException:
+        log.warning(
+            "Timed-out Kubernetes Job log fetch failed",
+            job_name=job_name,
+            job_kind=job_kind,
+            exc_info=True,
+        )
+        pod_logs = None
+    await suspend_job(job_name)
+    return pod_logs
+
+
+async def poll_k8s_job_until_terminal(
+    *,
+    job_name: str,
+    job_description: str,
+    job_kind: str,
+    log_context: dict[str, object],
+) -> K8sJobPollResult:
+    """Poll a Kubernetes Job until terminal or the client-side poll timeout.
+
+    Args:
+        job_name: Kubernetes Job name.
+        job_description: Human-readable job type used in operator-facing errors.
+        job_kind: Short job kind label attached to structured log events.
+        log_context: Additional structured fields bound to lifecycle log events.
+
+    Returns:
+        Terminal Job result. On client-side timeout, pod logs are fetched before
+        the still-running Job is suspended, and the result status is ``"failed"``.
+
+    Raises:
+        ApplicationError: Non-retryable for image pull errors and Kubernetes 4xx
+            responses while reading Job state.
+        ApiException: For transient Kubernetes status-read failures.
+    """
+    settings = get_settings()
+    deadline = _job_poll_deadline_monotonic(settings.job_poll_timeout_seconds)
+
+    async with run_with_heartbeat():
+        while True:
+            await load_k8s()
+            try:
+                terminal_status, image_pull_error = await asyncio.gather(
+                    job_status(job_name),
+                    check_for_image_pull_error(job_name),
+                )
+            except ApiException as exc:
+                if exc.status is not None and 400 <= exc.status < 500:
+                    raise ApplicationError(
+                        f"k8s 4xx reading {job_description} {job_name!r}: {exc.reason}",
+                        type="InvalidInput",
+                        non_retryable=True,
+                    ) from exc
+                raise
+
+            if image_pull_error:
+                raise ApplicationError(
+                    f"{job_description.capitalize()} {job_name!r} image pull failed "
+                    f"({image_pull_error}). Check EE_AGENT_IMAGE.",
+                    type="InvalidInput",
+                    non_retryable=True,
+                )
+
+            if terminal_status is not None:
+                pod_logs = await fetch_pod_logs(job_name)
+                log.info(
+                    "Kubernetes Job finished",
+                    job_name=job_name,
+                    job_kind=job_kind,
+                    status=terminal_status,
+                    **log_context,
+                )
+                return K8sJobPollResult(status=terminal_status, pod_logs=pod_logs)
+
+            if time.monotonic() >= deadline:
+                pod_logs = await _fetch_logs_and_suspend_job(job_name, job_kind)
+                failure_reason = (
+                    f"Client-side poll timeout after {settings.job_poll_timeout_seconds}s - k8s Job was suspended"
+                )
+                log.warning(
+                    "Kubernetes Job poll timed out",
+                    job_name=job_name,
+                    job_kind=job_kind,
+                    job_poll_timeout_seconds=settings.job_poll_timeout_seconds,
+                    pod_logs_captured=pod_logs is not None,
+                    **log_context,
+                )
+                return K8sJobPollResult(
+                    status="failed",
+                    failure_reason=failure_reason,
+                    timed_out=True,
+                    pod_logs=pod_logs,
+                )
+
+            activity.heartbeat({"job_name": job_name})
+            await asyncio.sleep(settings.job_poll_interval_seconds)
diff --git a/fl_control_plane/temporal/models.py b/fl_control_plane/temporal/models.py
index 75ec5a04..814851b6 100644
--- a/fl_control_plane/temporal/models.py
+++ b/fl_control_plane/temporal/models.py
@@ -2,7 +2,7 @@
 
 from typing import Literal
 
-from pydantic import BaseModel, ConfigDict
+from pydantic import BaseModel, ConfigDict, Field
 
 from fl_control_plane.execution_engine.models import HandlerExecutionResult
 from fl_control_plane.handler_orchestrator.models import ApplicabilityDecision
@@ -58,6 +58,12 @@ class IngestionRequest(BaseModel):
             or ``None`` for a normal (non-replay) inspection. When set, the data
             extraction activity copies HDLF data from this inspection instead of
             downloading from CI.
+        job_poll_timeout_seconds: Client-side Kubernetes Job poll timeout captured
+            when the workflow is started. Defaults to the execution-engine
+            default for workflow inputs that do not set it explicitly.
+        job_poll_cleanup_grace_seconds: Additional Temporal activity runtime
+            reserved after ``job_poll_timeout_seconds`` for pod log collection and
+            Job suspension. Defaults to the execution-engine cleanup grace.
     """
 
     model_config = ConfigDict(extra="forbid")
@@ -69,6 +75,8 @@ class IngestionRequest(BaseModel):
     correlation_id: str | None
     ingestion_timestamp: str
     replay_inspection_id: str | None = None
+    job_poll_timeout_seconds: int = Field(default=4500, ge=1)
+    job_poll_cleanup_grace_seconds: int = Field(default=120, ge=0)
 
 
 class MetadataExtractionResult(BaseModel):
@@ -457,6 +465,12 @@ class FinalizerJobResult(BaseModel):
             activity runtime. ``None`` when the finalizer was skipped.
         status: Terminal k8s job outcome — ``"succeeded"``, ``"failed"``, or
             ``"skipped"`` when ``should_dispatch`` suppressed the job.
+        failure_reason: Operator-facing failure detail when the poller failed the
+            job client-side, such as a poll timeout. ``None`` for succeeded and
+            skipped jobs.
+        timed_out: ``True`` when the execution-engine client-side poll deadline
+            expired before the finalizer Job reached a terminal state. Consumers
+            should use this flag instead of parsing ``failure_reason`` text.
         pod_logs: Last 400 lines of container stdout/stderr. ``None`` when
             skipped or when the log fetch failed (pod already GC'd, RBAC denial).
     """
@@ -465,6 +479,8 @@ class FinalizerJobResult(BaseModel):
     registry_id: str | None = None
     started_at: str | None = None
     status: Literal["succeeded", "failed", "skipped"] = "skipped"
+    failure_reason: str | None = None
+    timed_out: bool = False
     pod_logs: str | None = None
 
 
diff --git a/fl_control_plane/temporal/workflow.py b/fl_control_plane/temporal/workflow.py
index 4058775a..b3a0baf7 100644
--- a/fl_control_plane/temporal/workflow.py
+++ b/fl_control_plane/temporal/workflow.py
@@ -94,6 +94,42 @@
     from fl_shared.cr_models import FaultHandlerSpec
 
 
+_JOB_POLL_ACTIVITY_SCHEDULE_TO_CLOSE_MULTIPLIER = 3
+
+
+def _job_poll_activity_timeouts(request: IngestionRequest) -> tuple[timedelta, timedelta]:
+    """Return schedule-to-close and start-to-close timeouts for Job polling.
+
+    Temporal timeout semantics:
+    - ``start_to_close_timeout`` caps one attempt, from worker pickup until
+      success, failure, or worker crash. When it expires, that attempt fails and
+      Temporal may retry according to the retry policy.
+    - ``schedule_to_close_timeout`` caps the full activity lifecycle: queue wait,
+      every attempt, and all retry backoff delays. When it expires, the activity
+      fails with no further retries, regardless of the retry policy.
+
+    At least one of these timeouts must be set. When both are set, whichever
+    fires first wins. Job polling uses start-to-close to detect a hung worker or
+    bound one attempt, and schedule-to-close to bound the total retry envelope.
+    """
+    start_to_close_timeout = timedelta(
+        seconds=request.job_poll_timeout_seconds + request.job_poll_cleanup_grace_seconds,
+    )
+    schedule_to_close_timeout = start_to_close_timeout * _JOB_POLL_ACTIVITY_SCHEDULE_TO_CLOSE_MULTIPLIER
+    return schedule_to_close_timeout, start_to_close_timeout
+
+
+def _handler_execution_db_status(
+    result: HandlerExecutionResult,
+) -> Literal["success", "failed", "timed_out"]:
+    """Map a handler poll result to the handler_executions DB status."""
+    if result.status == "succeeded":
+        return "success"
+    if result.timed_out:
+        return "timed_out"
+    return "failed"
+
+
 @workflow.defn
 class PipelineInspectionWorkflow:
     """Temporal workflow that drives the pipeline inspection stage.
@@ -105,7 +141,8 @@ class PipelineInspectionWorkflow:
     Temporal's retry policy. ``ConfigError``, ``InvalidInput``, and
     ``PollTimeout`` types are non-retryable and fail the workflow immediately;
     ``TransientFailure`` is retried up to ``maximum_attempts`` times with
-    exponential backoff.
+    exponential backoff. Expected client-side k8s Job poll timeouts are returned
+    as failed domain results instead of failing the Temporal activity.
 
     Determinism contract: this class contains no I/O, no datetime.now(), no
     random calls, and no asyncio.sleep. All side effects are delegated to
@@ -132,6 +169,7 @@ async def run(self, request: IngestionRequest) -> WorkflowResult:
             maximum_interval=timedelta(seconds=60),
             non_retryable_error_types=["ConfigError", "InvalidInput", "PollTimeout"],
         )
+        job_poll_schedule_to_close_timeout, job_poll_start_to_close_timeout = _job_poll_activity_timeouts(request)
 
         async def _finalize_inspection(
             finalize_status: Literal["COMPLETED", "FAILED"],
@@ -157,8 +195,8 @@ async def _finalize_inspection(
                 finalizer_job_result: FinalizerJobResult = await execute_activity(
                     poll_finalizer_job_activity,
                     finalizer_submission,
-                    schedule_to_close_timeout=timedelta(minutes=90),
-                    start_to_close_timeout=timedelta(minutes=75),
+                    schedule_to_close_timeout=job_poll_schedule_to_close_timeout,
+                    start_to_close_timeout=job_poll_start_to_close_timeout,
                     heartbeat_timeout=timedelta(seconds=30),
                     retry_policy=_activity_retry_policy,
                 )
@@ -307,8 +345,8 @@ async def _run_handler(handler: FaultHandlerSpec) -> HandlerExecutionResult:
                         return await execute_activity(
                             poll_handler_job_activity,
                             submission,
-                            schedule_to_close_timeout=timedelta(minutes=90),
-                            start_to_close_timeout=timedelta(minutes=75),
+                            schedule_to_close_timeout=job_poll_schedule_to_close_timeout,
+                            start_to_close_timeout=job_poll_start_to_close_timeout,
                             heartbeat_timeout=timedelta(seconds=30),
                             retry_policy=_activity_retry_policy,
                         )
@@ -329,7 +367,7 @@ async def _run_handler(handler: FaultHandlerSpec) -> HandlerExecutionResult:
                 status_updates: list[HandlerExecutionStatusUpdate] = [
                     HandlerExecutionStatusUpdate(
                         execution_id=r.execution_id,
-                        status="success" if r.status == "succeeded" else "failed",
+                        status=_handler_execution_db_status(r),
                         status_message=r.failure_reason,
                     )
                     for r in handler_results
diff --git a/fl_mcp_servers/generic/inspection_results_mcp.py b/fl_mcp_servers/generic/inspection_results_mcp.py
index 41fd534d..6c53aa0a 100644
--- a/fl_mcp_servers/generic/inspection_results_mcp.py
+++ b/fl_mcp_servers/generic/inspection_results_mcp.py
@@ -24,7 +24,8 @@
     python -m fl_mcp_servers.generic.inspection_results_mcp
 """
 
-# pylint: disable=duplicate-code
+# ruff: noqa: I001, RUF100
+# pylint: disable=duplicate-code,wrong-import-order
 from __future__ import annotations
 
 from collections.abc import AsyncGenerator
@@ -51,8 +52,8 @@
 )
 from hdlf_server.models import InspectionContext
 from hdlf_server.reader import InspectionReader
-from mcp.server.fastmcp import Context, FastMCP  # pylint: disable=wrong-import-order
-from mcp.server.fastmcp.exceptions import ToolError  # pylint: disable=wrong-import-order
+from mcp.server.fastmcp import Context, FastMCP
+from mcp.server.fastmcp.exceptions import ToolError
 
 from fl_mcp_servers.generic.settings import McpSettings
 
diff --git a/fl_mcp_servers/generic/pipeline_data_mcp.py b/fl_mcp_servers/generic/pipeline_data_mcp.py
index 7a4dd938..f3e33a20 100644
--- a/fl_mcp_servers/generic/pipeline_data_mcp.py
+++ b/fl_mcp_servers/generic/pipeline_data_mcp.py
@@ -38,7 +38,8 @@
     python -m fl_mcp_servers.generic.pipeline_data_mcp
 """
 
-# pylint: disable=duplicate-code
+# ruff: noqa: I001, RUF100
+# pylint: disable=duplicate-code,wrong-import-order
 from __future__ import annotations
 
 from collections.abc import AsyncGenerator
diff --git a/fl_mcp_servers/generic/settings.py b/fl_mcp_servers/generic/settings.py
index 3dae340e..a79b41de 100644
--- a/fl_mcp_servers/generic/settings.py
+++ b/fl_mcp_servers/generic/settings.py
@@ -1,8 +1,11 @@
 """MCP server configuration loaded from MCP_-prefixed environment variables."""
 
+# ruff: noqa: I001, RUF100
+# pylint: disable=wrong-import-order
+
 from fl_shared.hdlf_client import HdlfConnectionParams
-from pydantic import SecretStr, model_validator  # pylint: disable=wrong-import-order
-from pydantic_settings import BaseSettings  # pylint: disable=wrong-import-order
+from pydantic import SecretStr, model_validator
+from pydantic_settings import BaseSettings
 
 from fl_mcp_servers.generic.env_vars import (
     ENV_HDLF_CLIENT_CERTIFICATE,
diff --git a/tests/execution_engine/test_dispatcher.py b/tests/execution_engine/test_dispatcher.py
index baf7aa29..e6a1e74b 100644
--- a/tests/execution_engine/test_dispatcher.py
+++ b/tests/execution_engine/test_dispatcher.py
@@ -7,7 +7,6 @@
 from unittest.mock import AsyncMock, MagicMock, patch
 
 import pytest
-from kubernetes_asyncio.client.exceptions import ApiException
 
 from fl_control_plane.execution_engine import dispatcher
 from fl_shared.cr_models import FaultHandlerSpec
@@ -52,7 +51,7 @@ async def _dispatch(handler=None, hdlf_inspection_cert_secret_name=None, repo_ur
     created_job = MagicMock()
     created_job.metadata.uid = "job-uid"
     mock_batch.create_namespaced_job.return_value = created_job
-    with patch("dispatcher._load_k8s"), patch("dispatcher.client.BatchV1Api", return_value=mock_batch):
+    with patch("dispatcher.client.BatchV1Api", return_value=mock_batch):
         job_spec = dispatcher._make_job_spec(handler or _handler(), _RUN_ID, repo_url=repo_url)
         job_spec.hdlf_inspection_cert_secret_name = hdlf_inspection_cert_secret_name
         finding = await dispatcher._submit_job(job_spec)
@@ -241,10 +240,29 @@ async def test_custom_runtime_does_not_inject_agent_task_envs_or_aicore():
 
 async def test_job_has_timeout_and_ttl():
     _, job = await _dispatch()
-    assert job.spec.active_deadline_seconds == 3600
+    assert job.spec.active_deadline_seconds == 21600
     assert job.spec.ttl_seconds_after_finished == 3600
 
 
+async def test_custom_runtime_uses_shared_job_timeout():
+    """custom_runtime jobs use the same generous active deadline as agent tasks."""
+    h = FaultHandlerSpec.model_validate(
+        {
+            "fault_id": _FAULT_ID,
+            "execution": {
+                "type": "custom_runtime",
+                "image": "keppel.eu-de-1.cloud.sap/hana-qa-lenny/pipeline-fl-handlers-impl:latest",
+                "entrypoint": "python -m fl_handlers_impl.handlers.lint",
+            },
+            "applicability": {"failure_match": {"strategy": "pipeline_scoped"}},
+        }
+    )
+
+    _, job = await _dispatch(handler=h)
+
+    assert job.spec.active_deadline_seconds == 21600
+
+
 # --- HandlerExecution ---
 
 
@@ -255,53 +273,6 @@ async def test_dispatch_returns_finding_with_correct_fields():
     assert finding.job_name == job.metadata.name
 
 
-# --- Job status polling ---
-
-
-def _make_job_status(condition_type: str) -> MagicMock:
-    condition = MagicMock()
-    condition.type = condition_type
-    condition.status = "True"
-    job = MagicMock()
-    job.status.conditions = [condition]
-    return job
-
-
-def _mock_batch_api(return_value: MagicMock) -> AsyncMock:
-    """Return an AsyncMock BatchV1Api whose read_namespaced_job returns return_value."""
-    mock = AsyncMock()
-    mock.read_namespaced_job.return_value = return_value
-    return mock
-
-
-async def test_job_status_succeeded():
-    """_job_status returns 'succeeded' when the Job has a Complete condition."""
-    with patch("dispatcher.client.BatchV1Api", return_value=_mock_batch_api(_make_job_status("Complete"))):
-        assert await dispatcher._job_status("fl-job-abc") == "succeeded"
-
-
-async def test_job_status_failed():
-    """_job_status returns 'failed' when the Job has a Failed condition."""
-    with patch("dispatcher.client.BatchV1Api", return_value=_mock_batch_api(_make_job_status("Failed"))):
-        assert await dispatcher._job_status("fl-job-abc") == "failed"
-
-
-async def test_job_status_still_running():
-    """_job_status returns None when no terminal condition is present."""
-    job = MagicMock()
-    job.status.conditions = []
-    with patch("dispatcher.client.BatchV1Api", return_value=_mock_batch_api(job)):
-        assert await dispatcher._job_status("fl-job-abc") is None
-
-
-async def test_job_status_none_when_status_not_yet_set():
-    """_job_status returns None when job.status is None (freshly created job)."""
-    job = MagicMock()
-    job.status = None
-    with patch("dispatcher.client.BatchV1Api", return_value=_mock_batch_api(job)):
-        assert await dispatcher._job_status("fl-job-abc") is None
-
-
 async def test_job_has_configurable_backoff_limit():
     """backoff_limit on the Job spec matches settings.job_backoff_limit."""
     _, job = await _dispatch()
@@ -329,116 +300,3 @@ async def test_job_command_is_none_when_no_entrypoint():
     """V1Container.command is None for agent_task handlers (image default CMD is used)."""
     _, job = await _dispatch()
     assert job.spec.template.spec.containers[0].command is None
-
-
-# --- Image pull error detection ---
-
-
-def _make_pod_with_waiting_reason(reason: str | None) -> MagicMock:
-    cs = MagicMock()
-    cs.state.waiting.reason = reason
-    pod = MagicMock()
-    pod.status.container_statuses = [cs]
-    return pod
-
-
-async def test_check_for_image_pull_error_detected():
-    """_check_for_image_pull_error returns the reason when a container is in ImagePullBackOff."""
-    pod = _make_pod_with_waiting_reason("ImagePullBackOff")
-    mock_core = AsyncMock()
-    mock_core.list_namespaced_pod.return_value.items = [pod]
-    with patch("dispatcher.client.CoreV1Api", return_value=mock_core):
-        result = await dispatcher._check_for_image_pull_error("fl-job-abc")
-    assert result == "ImagePullBackOff"
-
-
-async def test_check_for_image_pull_error_detected_err_image_pull():
-    """_check_for_image_pull_error returns the reason for ErrImagePull too."""
-    pod = _make_pod_with_waiting_reason("ErrImagePull")
-    mock_core = AsyncMock()
-    mock_core.list_namespaced_pod.return_value.items = [pod]
-    with patch("dispatcher.client.CoreV1Api", return_value=mock_core):
-        result = await dispatcher._check_for_image_pull_error("fl-job-abc")
-    assert result == "ErrImagePull"
-
-
-async def test_check_for_image_pull_error_none_when_running():
-    """_check_for_image_pull_error returns None when container is running normally."""
-    cs = MagicMock()
-    cs.state.waiting = None
-    pod = MagicMock()
-    pod.status.container_statuses = [cs]
-    mock_core = AsyncMock()
-    mock_core.list_namespaced_pod.return_value.items = [pod]
-    with patch("dispatcher.client.CoreV1Api", return_value=mock_core):
-        result = await dispatcher._check_for_image_pull_error("fl-job-abc")
-    assert result is None
-
-
-async def test_check_for_image_pull_error_none_when_no_pods_yet():
-    """_check_for_image_pull_error returns None when no pods have been scheduled yet."""
-    mock_core = AsyncMock()
-    mock_core.list_namespaced_pod.return_value.items = []
-    with patch("dispatcher.client.CoreV1Api", return_value=mock_core):
-        result = await dispatcher._check_for_image_pull_error("fl-job-abc")
-    assert result is None
-
-
-# --- Pod log retrieval ---
-
-
-def _make_pod_with_name(name: str) -> MagicMock:
-    pod = MagicMock()
-    pod.metadata.name = name
-    return pod
-
-
-async def test_fetch_pod_logs_returns_tail_logs():
-    """_fetch_pod_logs returns the pod log tail for the Job's pod."""
-    mock_core = AsyncMock()
-    mock_core.list_namespaced_pod.return_value.items = [_make_pod_with_name("pod-one")]
-    mock_core.read_namespaced_pod_log.return_value = "handler output"
-
-    with patch("dispatcher.client.CoreV1Api", return_value=mock_core):
-        result = await dispatcher._fetch_pod_logs("fl-job-abc")
-
-    assert result == "handler output"
-    mock_core.read_namespaced_pod_log.assert_awaited_once_with(
-        "pod-one",
-        dispatcher.get_settings().namespace,
-        tail_lines=400,
-    )
-
-
-async def test_fetch_pod_logs_returns_none_for_missing_pod():
-    """_fetch_pod_logs returns None when Kubernetes reports the pod is gone."""
-    mock_core = AsyncMock()
-    mock_core.list_namespaced_pod.side_effect = ApiException(status=404, reason="Not Found")
-
-    with patch("dispatcher.client.CoreV1Api", return_value=mock_core):
-        result = await dispatcher._fetch_pod_logs("fl-job-abc")
-
-    assert result is None
-
-
-async def test_fetch_pod_logs_propagates_transient_api_error():
-    """_fetch_pod_logs lets transient Kubernetes API errors trigger activity retry."""
-    mock_core = AsyncMock()
-    mock_core.list_namespaced_pod.return_value.items = [_make_pod_with_name("pod-one")]
-    mock_core.read_namespaced_pod_log.side_effect = ApiException(status=503, reason="Unavailable")
-
-    with patch("dispatcher.client.CoreV1Api", return_value=mock_core):
-        with pytest.raises(ApiException) as error_info:
-            await dispatcher._fetch_pod_logs("fl-job-abc")
-
-    assert error_info.value.status == 503
-
-
-async def test_fetch_pod_logs_propagates_unexpected_error():
-    """_fetch_pod_logs does not hide unexpected client or parsing errors."""
-    mock_core = AsyncMock()
-    mock_core.list_namespaced_pod.side_effect = ValueError("bad pod response")
-
-    with patch("dispatcher.client.CoreV1Api", return_value=mock_core):
-        with pytest.raises(ValueError, match="bad pod response"):
-            await dispatcher._fetch_pod_logs("fl-job-abc")
diff --git a/tests/execution_engine/test_job_activity.py b/tests/execution_engine/test_job_activity.py
index a10f9f99..434fbefc 100644
--- a/tests/execution_engine/test_job_activity.py
+++ b/tests/execution_engine/test_job_activity.py
@@ -2,8 +2,6 @@
 
 from __future__ import annotations
 
-from collections.abc import AsyncIterator
-from contextlib import asynccontextmanager
 from typing import Any
 from unittest.mock import AsyncMock, patch
 
@@ -19,6 +17,7 @@
     HandlerJobSubmission,
     SubmitHandlerJobRequest,
 )
+from fl_control_plane.temporal.job_polling import K8sJobPollResult
 from fl_shared.cr_models import FaultHandlerSpec
 
 _ACTIVITY_MODULE = "fl_control_plane.execution_engine.job_activity"
@@ -46,25 +45,6 @@ def _submit_request() -> SubmitHandlerJobRequest:
     )
 
 
-class _HeartbeatProbe:
-    """Record whether k8s loading happens inside the heartbeat context."""
-
-    def __init__(self) -> None:
-        self.active = False
-        self.load_k8s_started_in_context = False
-
-    @asynccontextmanager
-    async def run_with_heartbeat(self) -> AsyncIterator[None]:
-        self.active = True
-        try:
-            yield
-        finally:
-            self.active = False
-
-    async def load_k8s(self) -> None:
-        self.load_k8s_started_in_context = self.active
-
-
 async def test_submit_handler_job_provisions_inspection_access_before_submission() -> None:
     """Handler submission injects the per-inspection HDLF cert Secret into the job spec."""
     provision_inspection_access = AsyncMock(return_value=f"fl-job-{_EXECUTION_ID}-hdlf-cert")
@@ -80,7 +60,7 @@ async def _submit_job(job_spec: Any) -> HandlerExecution:
         )
 
     with (
-        patch(f"{_ACTIVITY_MODULE}._load_k8s", new=AsyncMock()),
+        patch(f"{_ACTIVITY_MODULE}.load_k8s", new=AsyncMock()),
         patch(
             f"{_ACTIVITY_MODULE}.provision_inspection_access",
             new=provision_inspection_access,
@@ -107,7 +87,7 @@ async def test_submit_handler_job_fails_before_submission_when_access_config_mis
     )
 
     with (
-        patch(f"{_ACTIVITY_MODULE}._load_k8s", new=AsyncMock()),
+        patch(f"{_ACTIVITY_MODULE}.load_k8s", new=AsyncMock()),
         patch(
             f"{_ACTIVITY_MODULE}.provision_inspection_access",
             new=AsyncMock(side_effect=config_error),
@@ -122,24 +102,57 @@ async def test_submit_handler_job_fails_before_submission_when_access_config_mis
     submit_job.assert_not_awaited()
 
 
-async def test_poll_handler_job_loads_k8s_inside_heartbeat_context() -> None:
-    """Handler polling starts heartbeating before loading k8s credentials."""
-    heartbeat_probe = _HeartbeatProbe()
+async def test_poll_handler_job_maps_successful_poll_result() -> None:
+    """Handler polling maps the shared k8s result to handler fields."""
     submission = HandlerJobSubmission(
-        execution_id="11111111-2222-3333-4444-555555555555",
-        job_name="fl-job-11111111-2222-3333-4444-555555555555",
+        execution_id=_EXECUTION_ID,
+        job_name=f"fl-job-{_EXECUTION_ID}",
         fault_id="handler-one",
         handler_name="handler-one",
     )
+    poll_k8s_job_until_terminal = AsyncMock(return_value=K8sJobPollResult(status="succeeded", pod_logs="done"))
 
-    with (
-        patch(f"{_ACTIVITY_MODULE}.run_with_heartbeat", new=heartbeat_probe.run_with_heartbeat),
-        patch(f"{_ACTIVITY_MODULE}._load_k8s", new=heartbeat_probe.load_k8s),
-        patch(f"{_ACTIVITY_MODULE}._job_status", new=AsyncMock(return_value="succeeded")),
-        patch(f"{_ACTIVITY_MODULE}._check_for_image_pull_error", new=AsyncMock(return_value=None)),
-        patch(f"{_ACTIVITY_MODULE}._fetch_pod_logs", new=AsyncMock(return_value="done")),
-    ):
+    with patch(f"{_ACTIVITY_MODULE}.poll_k8s_job_until_terminal", new=poll_k8s_job_until_terminal):
         result = await poll_handler_job_activity(submission)
 
     assert result.status == "succeeded"
-    assert heartbeat_probe.load_k8s_started_in_context is True
+    assert result.execution_id == _EXECUTION_ID
+    assert result.fault_id == "handler-one"
+    assert result.handler_name == "handler-one"
+    assert result.pod_logs == "done"
+    poll_k8s_job_until_terminal.assert_awaited_once_with(
+        job_name=f"fl-job-{_EXECUTION_ID}",
+        job_description="job",
+        job_kind="handler",
+        log_context={
+            "execution_id": _EXECUTION_ID,
+            "fault_id": "handler-one",
+            "handler_name": "handler-one",
+        },
+    )
+
+
+async def test_poll_handler_job_maps_failed_poll_result() -> None:
+    """Handler polling preserves timeout logs and failure reason."""
+    submission = HandlerJobSubmission(
+        execution_id=_EXECUTION_ID,
+        job_name=f"fl-job-{_EXECUTION_ID}",
+        fault_id="handler-one",
+        handler_name="handler-one",
+    )
+    poll_k8s_job_until_terminal = AsyncMock(
+        return_value=K8sJobPollResult(
+            status="failed",
+            failure_reason="Client-side poll timeout after 4500s - k8s Job was suspended",
+            timed_out=True,
+            pod_logs="last logs",
+        )
+    )
+
+    with patch(f"{_ACTIVITY_MODULE}.poll_k8s_job_until_terminal", new=poll_k8s_job_until_terminal):
+        result = await poll_handler_job_activity(submission)
+
+    assert result.status == "failed"
+    assert result.failure_reason == "Client-side poll timeout after 4500s - k8s Job was suspended"
+    assert result.timed_out is True
+    assert result.pod_logs == "last logs"
diff --git a/tests/execution_engine/test_k8s_jobs.py b/tests/execution_engine/test_k8s_jobs.py
new file mode 100644
index 00000000..0394d78c
--- /dev/null
+++ b/tests/execution_engine/test_k8s_jobs.py
@@ -0,0 +1,188 @@
+"""Unit tests for generic Kubernetes Job helpers."""
+
+from __future__ import annotations
+
+from unittest.mock import AsyncMock, MagicMock, patch
+
+import pytest
+from kubernetes_asyncio.client.exceptions import ApiException
+
+from fl_control_plane.execution_engine import k8s_jobs
+
+_MODULE = "fl_control_plane.execution_engine.k8s_jobs"
+
+_mock_api_client_ctx = MagicMock()
+_mock_api_client_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
+_mock_api_client_ctx.__aexit__ = AsyncMock(return_value=False)
+
+
+@pytest.fixture(autouse=True)
+def _patch_api_client():
+    """Patch ApiClient so tests don't need a real k8s connection."""
+    with patch(f"{_MODULE}.client.ApiClient", return_value=_mock_api_client_ctx):
+        yield
+
+
+def _make_job_status(condition_type: str) -> MagicMock:
+    condition = MagicMock()
+    condition.type = condition_type
+    condition.status = "True"
+    job = MagicMock()
+    job.status.conditions = [condition]
+    return job
+
+
+def _mock_batch_api(return_value: MagicMock) -> AsyncMock:
+    """Return an AsyncMock BatchV1Api whose read_namespaced_job returns return_value."""
+    mock = AsyncMock()
+    mock.read_namespaced_job.return_value = return_value
+    return mock
+
+
+async def test_job_status_succeeded() -> None:
+    """job_status returns 'succeeded' when the Job has a Complete condition."""
+    with patch(f"{_MODULE}.client.BatchV1Api", return_value=_mock_batch_api(_make_job_status("Complete"))):
+        assert await k8s_jobs.job_status("fl-job-abc") == "succeeded"
+
+
+async def test_job_status_failed() -> None:
+    """job_status returns 'failed' when the Job has a Failed condition."""
+    with patch(f"{_MODULE}.client.BatchV1Api", return_value=_mock_batch_api(_make_job_status("Failed"))):
+        assert await k8s_jobs.job_status("fl-job-abc") == "failed"
+
+
+async def test_job_status_still_running() -> None:
+    """job_status returns None when no terminal condition is present."""
+    job = MagicMock()
+    job.status.conditions = []
+    with patch(f"{_MODULE}.client.BatchV1Api", return_value=_mock_batch_api(job)):
+        assert await k8s_jobs.job_status("fl-job-abc") is None
+
+
+async def test_job_status_none_when_status_not_yet_set() -> None:
+    """job_status returns None when job.status is None."""
+    job = MagicMock()
+    job.status = None
+    with patch(f"{_MODULE}.client.BatchV1Api", return_value=_mock_batch_api(job)):
+        assert await k8s_jobs.job_status("fl-job-abc") is None
+
+
+def _make_pod_with_waiting_reason(reason: str | None) -> MagicMock:
+    container_status = MagicMock()
+    container_status.state.waiting.reason = reason
+    pod = MagicMock()
+    pod.status.container_statuses = [container_status]
+    return pod
+
+
+async def test_check_for_image_pull_error_detected() -> None:
+    """check_for_image_pull_error returns ImagePullBackOff waiting reasons."""
+    pod = _make_pod_with_waiting_reason("ImagePullBackOff")
+    mock_core = AsyncMock()
+    mock_core.list_namespaced_pod.return_value.items = [pod]
+    with patch(f"{_MODULE}.client.CoreV1Api", return_value=mock_core):
+        result = await k8s_jobs.check_for_image_pull_error("fl-job-abc")
+    assert result == "ImagePullBackOff"
+
+
+async def test_check_for_image_pull_error_detected_err_image_pull() -> None:
+    """check_for_image_pull_error returns ErrImagePull waiting reasons."""
+    pod = _make_pod_with_waiting_reason("ErrImagePull")
+    mock_core = AsyncMock()
+    mock_core.list_namespaced_pod.return_value.items = [pod]
+    with patch(f"{_MODULE}.client.CoreV1Api", return_value=mock_core):
+        result = await k8s_jobs.check_for_image_pull_error("fl-job-abc")
+    assert result == "ErrImagePull"
+
+
+async def test_check_for_image_pull_error_none_when_running() -> None:
+    """check_for_image_pull_error returns None when containers are not waiting."""
+    container_status = MagicMock()
+    container_status.state.waiting = None
+    pod = MagicMock()
+    pod.status.container_statuses = [container_status]
+    mock_core = AsyncMock()
+    mock_core.list_namespaced_pod.return_value.items = [pod]
+    with patch(f"{_MODULE}.client.CoreV1Api", return_value=mock_core):
+        result = await k8s_jobs.check_for_image_pull_error("fl-job-abc")
+    assert result is None
+
+
+async def test_check_for_image_pull_error_none_when_no_pods_yet() -> None:
+    """check_for_image_pull_error returns None when no pods have been scheduled."""
+    mock_core = AsyncMock()
+    mock_core.list_namespaced_pod.return_value.items = []
+    with patch(f"{_MODULE}.client.CoreV1Api", return_value=mock_core):
+        result = await k8s_jobs.check_for_image_pull_error("fl-job-abc")
+    assert result is None
+
+
+async def test_suspend_job_patches_job_suspend_true() -> None:
+    """suspend_job patches the Job spec so k8s stops active pods but keeps the Job."""
+    mock_batch = AsyncMock()
+
+    with patch(f"{_MODULE}.client.BatchV1Api", return_value=mock_batch):
+        await k8s_jobs.suspend_job("fl-job-abc")
+
+    mock_batch.patch_namespaced_job.assert_awaited_once_with(
+        "fl-job-abc",
+        k8s_jobs.get_settings().namespace,
+        {"spec": {"suspend": True}},
+    )
+
+
+def _make_pod_with_name(name: str) -> MagicMock:
+    pod = MagicMock()
+    pod.metadata.name = name
+    return pod
+
+
+async def test_fetch_pod_logs_returns_tail_logs() -> None:
+    """fetch_pod_logs returns the pod log tail for the Job's pod."""
+    mock_core = AsyncMock()
+    mock_core.list_namespaced_pod.return_value.items = [_make_pod_with_name("pod-one")]
+    mock_core.read_namespaced_pod_log.return_value = "handler output"
+
+    with patch(f"{_MODULE}.client.CoreV1Api", return_value=mock_core):
+        result = await k8s_jobs.fetch_pod_logs("fl-job-abc")
+
+    assert result == "handler output"
+    mock_core.read_namespaced_pod_log.assert_awaited_once_with(
+        "pod-one",
+        k8s_jobs.get_settings().namespace,
+        tail_lines=400,
+    )
+
+
+async def test_fetch_pod_logs_returns_none_for_missing_pod() -> None:
+    """fetch_pod_logs returns None when Kubernetes reports the pod is gone."""
+    mock_core = AsyncMock()
+    mock_core.list_namespaced_pod.side_effect = ApiException(status=404, reason="Not Found")
+
+    with patch(f"{_MODULE}.client.CoreV1Api", return_value=mock_core):
+        result = await k8s_jobs.fetch_pod_logs("fl-job-abc")
+
+    assert result is None
+
+
+async def test_fetch_pod_logs_propagates_transient_api_error() -> None:
+    """fetch_pod_logs lets transient Kubernetes API errors trigger activity retry."""
+    mock_core = AsyncMock()
+    mock_core.list_namespaced_pod.return_value.items = [_make_pod_with_name("pod-one")]
+    mock_core.read_namespaced_pod_log.side_effect = ApiException(status=503, reason="Unavailable")
+
+    with patch(f"{_MODULE}.client.CoreV1Api", return_value=mock_core):
+        with pytest.raises(ApiException) as error_info:
+            await k8s_jobs.fetch_pod_logs("fl-job-abc")
+
+    assert error_info.value.status == 503
+
+
+async def test_fetch_pod_logs_propagates_unexpected_error() -> None:
+    """fetch_pod_logs does not hide unexpected client or parsing errors."""
+    mock_core = AsyncMock()
+    mock_core.list_namespaced_pod.side_effect = ValueError("bad pod response")
+
+    with patch(f"{_MODULE}.client.CoreV1Api", return_value=mock_core):
+        with pytest.raises(ValueError, match="bad pod response"):
+            await k8s_jobs.fetch_pod_logs("fl-job-abc")
diff --git a/tests/temporal/test_finalize_activity.py b/tests/temporal/test_finalize_activity.py
index e4a4f626..93acb0ce 100644
--- a/tests/temporal/test_finalize_activity.py
+++ b/tests/temporal/test_finalize_activity.py
@@ -31,6 +31,7 @@
     poll_finalizer_job_activity,
     submit_finalizer_job_activity,
 )
+from fl_control_plane.temporal.job_polling import K8sJobPollResult
 from fl_control_plane.temporal.models import (
     FinalizeInspectionRequest,
     FinalizerJobResult,
@@ -126,7 +127,7 @@ async def _submit_job(job_spec: Any) -> HandlerExecution:
         patch(f"{_ACTIVITY_MODULE}.async_session", return_value=_mock_session_context()),
         patch(f"{_ACTIVITY_MODULE}.should_dispatch", new=AsyncMock(return_value=(True, None))),
         patch(f"{_ACTIVITY_MODULE}.pick_finalizer", new=AsyncMock(return_value=_finalizer_row())),
-        patch(f"{_ACTIVITY_MODULE}._load_k8s", new=AsyncMock()),
+        patch(f"{_ACTIVITY_MODULE}.load_k8s", new=AsyncMock()),
         patch(
             f"{_ACTIVITY_MODULE}.provision_inspection_access",
             new=provision_inspection_access,
@@ -159,7 +160,7 @@ async def test_submit_finalizer_job_fails_when_inspection_access_config_missing(
         patch(f"{_ACTIVITY_MODULE}.async_session", return_value=_mock_session_context()),
         patch(f"{_ACTIVITY_MODULE}.should_dispatch", new=AsyncMock(return_value=(True, None))),
         patch(f"{_ACTIVITY_MODULE}.pick_finalizer", new=AsyncMock(return_value=_finalizer_row())),
-        patch(f"{_ACTIVITY_MODULE}._load_k8s", new=AsyncMock()),
+        patch(f"{_ACTIVITY_MODULE}.load_k8s", new=AsyncMock()),
         patch(f"{_ACTIVITY_MODULE}._submit_job", new=submit_job),
     ):
         with pytest.raises(ApplicationError) as error_info:
@@ -188,7 +189,7 @@ async def _submit_job(job_spec: Any) -> HandlerExecution:
         patch(f"{_ACTIVITY_MODULE}.should_dispatch", new=AsyncMock(return_value=(True, None))),
         patch(f"{_ACTIVITY_MODULE}.pick_finalizer", new=AsyncMock(return_value=_finalizer_row())),
         patch(f"{_ACTIVITY_MODULE}.run_with_heartbeat", new=heartbeat_probe.run_with_heartbeat),
-        patch(f"{_ACTIVITY_MODULE}._load_k8s", new=heartbeat_probe.load_k8s),
+        patch(f"{_ACTIVITY_MODULE}.load_k8s", new=heartbeat_probe.load_k8s),
         patch(
             f"{_ACTIVITY_MODULE}.provision_inspection_access",
             new=provision_inspection_access,
@@ -208,7 +209,7 @@ async def test_submit_finalizer_job_treats_existing_job_as_success() -> None:
         patch(f"{_ACTIVITY_MODULE}.async_session", return_value=_mock_session_context()),
         patch(f"{_ACTIVITY_MODULE}.should_dispatch", new=AsyncMock(return_value=(True, None))),
         patch(f"{_ACTIVITY_MODULE}.pick_finalizer", new=AsyncMock(return_value=_finalizer_row())),
-        patch(f"{_ACTIVITY_MODULE}._load_k8s", new=AsyncMock()),
+        patch(f"{_ACTIVITY_MODULE}.load_k8s", new=AsyncMock()),
         patch(
             f"{_ACTIVITY_MODULE}.provision_inspection_access",
             new=provision_inspection_access,
@@ -226,23 +227,17 @@ async def test_submit_finalizer_job_treats_existing_job_as_success() -> None:
     assert result.started_at is not None
 
 
-async def test_poll_finalizer_job_classifies_k8s_4xx_as_invalid_input() -> None:
-    """Kubernetes 4xx while polling becomes a non-retryable InvalidInput error."""
+async def test_poll_finalizer_job_propagates_poll_error() -> None:
+    """Finalizer polling propagates shared poll errors."""
     submission = FinalizerJobSubmission(
         inspection_id=_INSPECTION_ID,
         execution_id=_EXECUTION_ID,
         job_name=f"fl-job-{_EXECUTION_ID}",
         registry_id=_REGISTRY_ID,
     )
+    poll_error = ApplicationError("k8s 4xx reading finalizer job", type="InvalidInput", non_retryable=True)
 
-    with (
-        patch(f"{_ACTIVITY_MODULE}._load_k8s", new=AsyncMock()),
-        patch(
-            f"{_ACTIVITY_MODULE}._job_status",
-            new=AsyncMock(side_effect=ApiException(status=404, reason="Not Found")),
-        ),
-        patch(f"{_ACTIVITY_MODULE}._check_for_image_pull_error", new=AsyncMock(return_value=None)),
-    ):
+    with patch(f"{_ACTIVITY_MODULE}.poll_k8s_job_until_terminal", new=AsyncMock(side_effect=poll_error)):
         with pytest.raises(ApplicationError) as error_info:
             await poll_finalizer_job_activity(submission)
 
@@ -250,27 +245,64 @@ async def test_poll_finalizer_job_classifies_k8s_4xx_as_invalid_input() -> None:
     assert error_info.value.non_retryable is True
 
 
-async def test_poll_finalizer_job_loads_k8s_inside_heartbeat_context() -> None:
-    """Finalizer polling starts heartbeating before loading k8s credentials."""
-    heartbeat_probe = _HeartbeatProbe()
+async def test_poll_finalizer_job_maps_successful_poll_result() -> None:
+    """Finalizer polling maps the shared k8s result to finalizer fields."""
     submission = FinalizerJobSubmission(
         inspection_id=_INSPECTION_ID,
         execution_id=_EXECUTION_ID,
         job_name=f"fl-job-{_EXECUTION_ID}",
         registry_id=_REGISTRY_ID,
+        started_at="2026-01-02T03:04:05+00:00",
     )
+    poll_k8s_job_until_terminal = AsyncMock(return_value=K8sJobPollResult(status="succeeded", pod_logs="done"))
 
-    with (
-        patch(f"{_ACTIVITY_MODULE}.run_with_heartbeat", new=heartbeat_probe.run_with_heartbeat),
-        patch(f"{_ACTIVITY_MODULE}._load_k8s", new=heartbeat_probe.load_k8s),
-        patch(f"{_ACTIVITY_MODULE}._job_status", new=AsyncMock(return_value="succeeded")),
-        patch(f"{_ACTIVITY_MODULE}._check_for_image_pull_error", new=AsyncMock(return_value=None)),
-        patch(f"{_ACTIVITY_MODULE}._fetch_pod_logs", new=AsyncMock(return_value="done")),
-    ):
+    with patch(f"{_ACTIVITY_MODULE}.poll_k8s_job_until_terminal", new=poll_k8s_job_until_terminal):
         result = await poll_finalizer_job_activity(submission)
 
     assert result.status == "succeeded"
-    assert heartbeat_probe.load_k8s_started_in_context is True
+    assert result.execution_id == _EXECUTION_ID
+    assert result.registry_id == _REGISTRY_ID
+    assert result.started_at == "2026-01-02T03:04:05+00:00"
+    assert result.pod_logs == "done"
+    poll_k8s_job_until_terminal.assert_awaited_once_with(
+        job_name=f"fl-job-{_EXECUTION_ID}",
+        job_description="finalizer job",
+        job_kind="finalizer",
+        log_context={
+            "inspection_id": _INSPECTION_ID,
+            "execution_id": _EXECUTION_ID,
+        },
+    )
+
+
+async def test_poll_finalizer_job_maps_failed_poll_result() -> None:
+    """Finalizer polling preserves timeout logs."""
+    submission = FinalizerJobSubmission(
+        inspection_id=_INSPECTION_ID,
+        execution_id=_EXECUTION_ID,
+        job_name=f"fl-job-{_EXECUTION_ID}",
+        registry_id=_REGISTRY_ID,
+        started_at="2026-01-02T03:04:05+00:00",
+    )
+    poll_k8s_job_until_terminal = AsyncMock(
+        return_value=K8sJobPollResult(
+            status="failed",
+            failure_reason="Client-side poll timeout after 4500s - k8s Job was suspended",
+            timed_out=True,
+            pod_logs="finalizer logs",
+        )
+    )
+
+    with patch(f"{_ACTIVITY_MODULE}.poll_k8s_job_until_terminal", new=poll_k8s_job_until_terminal):
+        result = await poll_finalizer_job_activity(submission)
+
+    assert result.execution_id == _EXECUTION_ID
+    assert result.registry_id == _REGISTRY_ID
+    assert result.started_at == "2026-01-02T03:04:05+00:00"
+    assert result.status == "failed"
+    assert result.failure_reason == "Client-side poll timeout after 4500s - k8s Job was suspended"
+    assert result.timed_out is True
+    assert result.pod_logs == "finalizer logs"
 
 
 async def test_mark_inspection_terminal_uses_finalizer_submission_started_at() -> None:
@@ -331,3 +363,35 @@ async def test_mark_inspection_terminal_commits_finalizer_and_status_atomically(
     assert write_finalizer_execution.await_args.kwargs["session"] is session
     session.execute.assert_awaited_once()
     session.commit.assert_awaited_once()
+
+
+async def test_mark_inspection_terminal_writes_finalizer_failure_reason() -> None:
+    """finalizer_execution.status_message records poller failure detail."""
+    request = MarkInspectionTerminalRequest(
+        finalize_request=_request(),
+        job_result=FinalizerJobResult(
+            execution_id=_EXECUTION_ID,
+            registry_id=_REGISTRY_ID,
+            started_at="2026-01-02T03:04:05+00:00",
+            status="failed",
+            failure_reason="Client-side poll timeout after 4500s - k8s Job was suspended",
+            timed_out=True,
+            pod_logs="last logs",
+        ),
+    )
+
+    write_finalizer_execution = AsyncMock()
+    with (
+        patch(f"{_ACTIVITY_MODULE}.async_session", return_value=_mock_session_context()),
+        patch(
+            f"{_ACTIVITY_MODULE}.write_finalizer_execution",
+            new=write_finalizer_execution,
+        ),
+    ):
+        await mark_inspection_terminal_activity(request)
+
+    assert write_finalizer_execution.await_args.kwargs["status"] == "timed_out"
+    assert (
+        write_finalizer_execution.await_args.kwargs["status_message"]
+        == "Client-side poll timeout after 4500s - k8s Job was suspended"
+    )
diff --git a/tests/temporal/test_job_polling.py b/tests/temporal/test_job_polling.py
new file mode 100644
index 00000000..b6106537
--- /dev/null
+++ b/tests/temporal/test_job_polling.py
@@ -0,0 +1,221 @@
+"""Unit tests for shared Kubernetes Job polling helpers."""
+
+from __future__ import annotations
+
+from collections.abc import AsyncIterator
+from contextlib import asynccontextmanager
+from unittest.mock import AsyncMock, patch
+
+import pytest
+from kubernetes_asyncio.client.exceptions import ApiException
+from temporalio.exceptions import ApplicationError
+
+from fl_control_plane.execution_engine.config import Settings
+from fl_control_plane.temporal.job_polling import poll_k8s_job_until_terminal
+
+_JOB_NAME = "fl-job-11111111-2222-3333-4444-555555555555"
+_MODULE = "fl_control_plane.temporal.job_polling"
+
+
+class _HeartbeatProbe:
+    """Record whether k8s loading happens inside the heartbeat context."""
+
+    def __init__(self) -> None:
+        self.active = False
+        self.load_k8s_started_in_context = False
+
+    @asynccontextmanager
+    async def run_with_heartbeat(self) -> AsyncIterator[None]:
+        self.active = True
+        try:
+            yield
+        finally:
+            self.active = False
+
+    async def load_k8s(self) -> None:
+        self.load_k8s_started_in_context = self.active
+
+
+@asynccontextmanager
+async def _noop_heartbeat() -> AsyncIterator[None]:
+    yield
+
+
+def _settings(timeout_seconds: int = 30) -> Settings:
+    return Settings(
+        config_repo_url="https://github.example.com/config",
+        job_poll_timeout_seconds=timeout_seconds,
+        job_poll_interval_seconds=1,
+    )
+
+
+async def test_poll_k8s_job_starts_heartbeat_before_loading_k8s() -> None:
+    """Shared polling starts heartbeating before loading k8s credentials."""
+    heartbeat_probe = _HeartbeatProbe()
+
+    with (
+        patch(f"{_MODULE}.get_settings", return_value=_settings()),
+        patch(f"{_MODULE}.run_with_heartbeat", new=heartbeat_probe.run_with_heartbeat),
+        patch(f"{_MODULE}.load_k8s", new=heartbeat_probe.load_k8s),
+        patch(f"{_MODULE}.job_status", new=AsyncMock(return_value="succeeded")),
+        patch(f"{_MODULE}.check_for_image_pull_error", new=AsyncMock(return_value=None)),
+        patch(f"{_MODULE}.fetch_pod_logs", new=AsyncMock(return_value="done")),
+    ):
+        await poll_k8s_job_until_terminal(
+            job_name=_JOB_NAME,
+            job_description="job",
+            job_kind="handler",
+            log_context={"execution_id": "execution-one"},
+        )
+
+    assert heartbeat_probe.load_k8s_started_in_context is True
+
+
+async def test_poll_k8s_job_returns_terminal_status_and_logs() -> None:
+    """Shared polling returns the terminal k8s status with pod logs."""
+    fetch_pod_logs = AsyncMock(return_value="last handler output")
+
+    with (
+        patch(f"{_MODULE}.get_settings", return_value=_settings()),
+        patch(f"{_MODULE}.run_with_heartbeat", new=_noop_heartbeat),
+        patch(f"{_MODULE}.load_k8s", new=AsyncMock()),
+        patch(f"{_MODULE}.job_status", new=AsyncMock(return_value="failed")),
+        patch(f"{_MODULE}.check_for_image_pull_error", new=AsyncMock(return_value=None)),
+        patch(f"{_MODULE}.fetch_pod_logs", new=fetch_pod_logs),
+    ):
+        result = await poll_k8s_job_until_terminal(
+            job_name=_JOB_NAME,
+            job_description="job",
+            job_kind="handler",
+            log_context={"execution_id": "execution-one"},
+        )
+
+    assert result.status == "failed"
+    assert result.pod_logs == "last handler output"
+    assert result.failure_reason is None
+    fetch_pod_logs.assert_awaited_once_with(_JOB_NAME)
+
+
+async def test_poll_k8s_job_timeout_fetches_logs_then_suspends_job() -> None:
+    """Client-side timeout captures pod logs before suspending the live Job."""
+    call_order: list[str] = []
+
+    async def _fetch_pod_logs(job_name: str) -> str:
+        call_order.append(f"fetch:{job_name}")
+        return "last logs before cleanup"
+
+    async def _suspend_job(job_name: str) -> None:
+        call_order.append(f"suspend:{job_name}")
+
+    with (
+        patch(f"{_MODULE}.get_settings", return_value=_settings(timeout_seconds=0)),
+        patch(f"{_MODULE}.run_with_heartbeat", new=_noop_heartbeat),
+        patch(f"{_MODULE}.load_k8s", new=AsyncMock()),
+        patch(f"{_MODULE}.job_status", new=AsyncMock(return_value=None)),
+        patch(f"{_MODULE}.check_for_image_pull_error", new=AsyncMock(return_value=None)),
+        patch(f"{_MODULE}.fetch_pod_logs", new=_fetch_pod_logs),
+        patch(f"{_MODULE}.suspend_job", new=_suspend_job),
+    ):
+        result = await poll_k8s_job_until_terminal(
+            job_name=_JOB_NAME,
+            job_description="job",
+            job_kind="handler",
+            log_context={"execution_id": "execution-one"},
+        )
+
+    assert result.status == "failed"
+    assert result.pod_logs == "last logs before cleanup"
+    assert result.timed_out is True
+    assert result.failure_reason == "Client-side poll timeout after 0s - k8s Job was suspended"
+    assert call_order == [f"fetch:{_JOB_NAME}", f"suspend:{_JOB_NAME}"]
+
+
+async def test_poll_k8s_job_timeout_suspends_job_when_log_fetch_is_forbidden() -> None:
+    """Client-side timeout still suspends the Job when pod logs are unavailable."""
+    suspend_job = AsyncMock()
+
+    with (
+        patch(f"{_MODULE}.get_settings", return_value=_settings(timeout_seconds=0)),
+        patch(f"{_MODULE}.run_with_heartbeat", new=_noop_heartbeat),
+        patch(f"{_MODULE}.load_k8s", new=AsyncMock()),
+        patch(f"{_MODULE}.job_status", new=AsyncMock(return_value=None)),
+        patch(f"{_MODULE}.check_for_image_pull_error", new=AsyncMock(return_value=None)),
+        patch(
+            f"{_MODULE}.fetch_pod_logs",
+            new=AsyncMock(side_effect=ApiException(status=403, reason="Forbidden")),
+        ),
+        patch(f"{_MODULE}.suspend_job", new=suspend_job),
+    ):
+        result = await poll_k8s_job_until_terminal(
+            job_name=_JOB_NAME,
+            job_description="job",
+            job_kind="handler",
+            log_context={"execution_id": "execution-one"},
+        )
+
+    assert result.status == "failed"
+    assert result.pod_logs is None
+    assert result.timed_out is True
+    suspend_job.assert_awaited_once_with(_JOB_NAME)
+
+
+async def test_poll_k8s_job_converts_status_read_4xx_to_invalid_input() -> None:
+    """Kubernetes 4xx status reads become non-retryable InvalidInput errors."""
+    with (
+        patch(f"{_MODULE}.get_settings", return_value=_settings()),
+        patch(f"{_MODULE}.run_with_heartbeat", new=_noop_heartbeat),
+        patch(f"{_MODULE}.load_k8s", new=AsyncMock()),
+        patch(f"{_MODULE}.job_status", new=AsyncMock(side_effect=ApiException(status=404, reason="Not Found"))),
+        patch(f"{_MODULE}.check_for_image_pull_error", new=AsyncMock(return_value=None)),
+    ):
+        with pytest.raises(ApplicationError) as error_info:
+            await poll_k8s_job_until_terminal(
+                job_name=_JOB_NAME,
+                job_description="finalizer job",
+                job_kind="finalizer",
+                log_context={"inspection_id": "inspection-one"},
+            )
+
+    assert error_info.value.type == "InvalidInput"
+    assert error_info.value.non_retryable is True
+
+
+async def test_poll_k8s_job_converts_image_pull_error_to_invalid_input() -> None:
+    """Image pull failures become non-retryable InvalidInput errors."""
+    with (
+        patch(f"{_MODULE}.get_settings", return_value=_settings()),
+        patch(f"{_MODULE}.run_with_heartbeat", new=_noop_heartbeat),
+        patch(f"{_MODULE}.load_k8s", new=AsyncMock()),
+        patch(f"{_MODULE}.job_status", new=AsyncMock(return_value=None)),
+        patch(f"{_MODULE}.check_for_image_pull_error", new=AsyncMock(return_value="ImagePullBackOff")),
+    ):
+        with pytest.raises(ApplicationError) as error_info:
+            await poll_k8s_job_until_terminal(
+                job_name=_JOB_NAME,
+                job_description="job",
+                job_kind="handler",
+                log_context={"execution_id": "execution-one"},
+            )
+
+    assert error_info.value.type == "InvalidInput"
+    assert error_info.value.non_retryable is True
+
+
+async def test_poll_k8s_job_propagates_transient_status_read_errors() -> None:
+    """Kubernetes 5xx status reads propagate so Temporal can retry."""
+    with (
+        patch(f"{_MODULE}.get_settings", return_value=_settings()),
+        patch(f"{_MODULE}.run_with_heartbeat", new=_noop_heartbeat),
+        patch(f"{_MODULE}.load_k8s", new=AsyncMock()),
+        patch(f"{_MODULE}.job_status", new=AsyncMock(side_effect=ApiException(status=500, reason="Server Error"))),
+        patch(f"{_MODULE}.check_for_image_pull_error", new=AsyncMock(return_value=None)),
+    ):
+        with pytest.raises(ApiException) as error_info:
+            await poll_k8s_job_until_terminal(
+                job_name=_JOB_NAME,
+                job_description="job",
+                job_kind="handler",
+                log_context={"execution_id": "execution-one"},
+            )
+
+    assert error_info.value.status == 500
diff --git a/tests/temporal/test_workflow.py b/tests/temporal/test_workflow.py
index 53e42716..5d7ecc5f 100644
--- a/tests/temporal/test_workflow.py
+++ b/tests/temporal/test_workflow.py
@@ -1,5 +1,6 @@
 """Unit tests for PipelineInspectionWorkflow and extract_metadata_activity."""
 
+from datetime import timedelta
 from unittest.mock import AsyncMock, MagicMock, patch
 
 import pytest
@@ -33,7 +34,11 @@
     PipelineAnalysisResult,
     WorkflowResult,
 )
-from fl_control_plane.temporal.workflow import PipelineInspectionWorkflow
+from fl_control_plane.temporal.workflow import (
+    PipelineInspectionWorkflow,
+    _handler_execution_db_status,
+    _job_poll_activity_timeouts,
+)
 from fl_shared.cr_models import FaultHandlerSpec
 
 _INSPECTION_ID = "3f7c2a1e-8b4d-4e9f-a012-56789abcdef0"
@@ -105,6 +110,43 @@
 _HARDCODED_FINALIZE_RESULT = FinalizeInspectionResult(completion_text=None)
 
 
+def test_job_poll_activity_timeouts_use_request_defaults() -> None:
+    """Workflow poll activity timeouts use the request model defaults."""
+    schedule_to_close_timeout, start_to_close_timeout = _job_poll_activity_timeouts(_SAMPLE_REQUEST)
+
+    assert start_to_close_timeout == timedelta(seconds=4620)
+    assert schedule_to_close_timeout == timedelta(seconds=13860)
+
+
+def test_job_poll_activity_timeouts_use_captured_request_budget() -> None:
+    """New workflow inputs derive poll activity timeouts from the captured EE budget."""
+    request = _SAMPLE_REQUEST.model_copy(
+        update={
+            "job_poll_timeout_seconds": 120,
+            "job_poll_cleanup_grace_seconds": 30,
+        }
+    )
+
+    schedule_to_close_timeout, start_to_close_timeout = _job_poll_activity_timeouts(request)
+
+    assert start_to_close_timeout == timedelta(seconds=150)
+    assert schedule_to_close_timeout == timedelta(seconds=450)
+
+
+def test_handler_execution_db_status_maps_poll_timeout_to_timed_out() -> None:
+    """Handler client-side poll timeouts persist as timed_out DB statuses."""
+    result = HandlerExecutionResult(
+        execution_id="execution-one",
+        fault_id="fault-one",
+        handler_name="handler-one",
+        status="failed",
+        failure_reason="Client-side poll timeout after 120s - k8s Job was suspended",
+        timed_out=True,
+    )
+
+    assert _handler_execution_db_status(result) == "timed_out"
+
+
 def _make_activity_mocks(*, metadata_exists: bool = False) -> tuple:
     """Return (hdlf_settings_patch, hdlf_patch, jenkins_patch) context managers."""
     mock_hdlf_settings = MagicMock()
@@ -244,9 +286,9 @@ async def _fake_open_hdlf_client():
     with (
         patch("fl_control_plane.metadata_extractor.activity.open_hdlf_client", _fake_open_hdlf_client),
         patch("fl_control_plane.metadata_extractor.activity.async_session", return_value=mock_session_context),
-        patch("fl_control_plane.credentials.get_azure_devops_token", return_value="pat-token"),
+        patch("fl_control_plane.metadata_extractor.activity.get_azure_devops_token", return_value="pat-token"),
         patch(
-            "fl_control_plane.metadata_extractor.azure_devops.extract_azure_devops_metadata",
+            "fl_control_plane.metadata_extractor.activity.extract_azure_devops_metadata",
             new=ado_extractor,
         ),
     ):
diff --git a/tests/test_finalizer_agent_runner.py b/tests/test_finalizer_agent_runner.py
index ab055d91..c22ee04b 100644
--- a/tests/test_finalizer_agent_runner.py
+++ b/tests/test_finalizer_agent_runner.py
@@ -6,6 +6,7 @@
 import pytest
 
 pytest.importorskip("hana_program_synthesis", reason="internal SAP package not available in local dev venv")
+pytest.importorskip("mlflow", reason="hana_program_synthesis mlflow dependency not available in local dev venv")
 
 from finalizer_agent.agent_task_runner import _adjust_resource_requirements, run
 from finalizer_agent.models import FinalizerTaskRequest

```
