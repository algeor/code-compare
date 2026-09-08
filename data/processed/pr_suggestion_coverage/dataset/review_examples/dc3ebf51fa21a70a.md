# dc3ebf51fa21a70a

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/35
Suggested label: 35%
File overlap: 1.0
Changed-line overlap: 0.0

## Suggested diff
```diff
--- a/fl_control_plane/execution_contracts.py
+++ b/fl_control_plane/execution_contracts.py
@@
+skill_paths: list[str] = Field(default_factory=list)
+    mcp_config_paths: list[str] = Field(default_factory=list)
```

## Landed PR diff
```diff
diff --git a/fl_control_plane/execution_contracts.py b/fl_control_plane/execution_contracts.py
new file mode 100644
index 00000000..e781c8e6
--- /dev/null
+++ b/fl_control_plane/execution_contracts.py
@@ -0,0 +1,82 @@
+"""Shared contract models between the Handler Orchestrator and Execution Engine."""
+from __future__ import annotations
+
+from typing import Literal
+
+from pydantic import BaseModel
+
+
+class FaultHandlerExecution(BaseModel):
+    """The execution block from a FaultHandler CR spec.
+
+    Attributes:
+        type: Execution strategy. "agent_task" launches an LLM agent; "custom_runtime"
+            runs an arbitrary container image with a custom entrypoint.
+        task: Agent prompt passed as TASK_TEXT. Ignored when type is "custom_runtime".
+        image: Container image override. Falls back to settings.agent_image when None.
+        entrypoint: Command override for the container (splits into argv). None means
+            the image default CMD is used — typical for agent_task handlers.
+        skill_paths: Paths within the config repo to skill files injected into the agent.
+        mcp_config_paths: Paths within the config repo to MCP config files for the agent.
+    """
+
+    type: Literal["agent_task", "custom_runtime"] = "agent_task"
+    task: str = ""
+    image: str | None = None
+    entrypoint: str | None = None
+    skill_paths: list[str] = []
+    mcp_config_paths: list[str] = []
+
+
+class FaultHandlerSpec(BaseModel):
+    """The spec block from a FaultHandler CR.
+
+    Attributes:
+        fault_id: Logical identifier for the fault this handler addresses. Used as a
+            label on the k8s Job. Falls back to metadata.name when absent.
+        execution: Execution configuration for the handler job.
+    """
+
+    fault_id: str | None = None
+    execution: FaultHandlerExecution = FaultHandlerExecution()
+
+
+class FaultHandlerMetadata(BaseModel):
+    """The metadata block from a FaultHandler CR.
+
+    Attributes:
+        name: CR name — used as the handler identifier when fault_id is absent.
+    """
+
+    name: str = "unknown"
+
+
+class FaultHandlerCR(BaseModel):
+    """A FaultHandler custom resource as passed to the execution engine.
+
+    This is not a raw k8s CR — it is the subset of CR fields the execution engine
+    needs. The Handler Orchestrator is responsible for selecting applicable handlers
+    and constructing these objects before calling dispatch_all().
+
+    Example::
+
+        FaultHandlerCR(
+            metadata=FaultHandlerMetadata(name="jenkins-bounded-analysis"),
+            spec=FaultHandlerSpec(
+                fault_id="jenkins-bounded-analysis",
+                execution=FaultHandlerExecution(
+                    type="agent_task",
+                    task="Analyze the failed Jenkins pipeline run ...",
+                    skill_paths=[],
+                    mcp_config_paths=[],
+                ),
+            ),
+        )
+
+    Attributes:
+        metadata: CR metadata — currently only name is used.
+        spec: Handler specification including execution config.
+    """
+
+    metadata: FaultHandlerMetadata = FaultHandlerMetadata()
+    spec: FaultHandlerSpec = FaultHandlerSpec()

```
