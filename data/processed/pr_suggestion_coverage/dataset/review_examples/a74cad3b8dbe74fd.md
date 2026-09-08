# a74cad3b8dbe74fd

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/60
Suggested label: 0%
File overlap: 0.0
Changed-line overlap: 0.0

## Suggested diff
```diff
--- a/fl_control_plane/temporal/finalize_activity.py
+++ b/fl_control_plane/temporal/finalize_activity.py
@@

```

## Landed PR diff
```diff
diff --git a/fl_control_plane/data_extractor/models.py b/fl_control_plane/data_extractor/models.py
index 89eb1988..bf874a3d 100644
--- a/fl_control_plane/data_extractor/models.py
+++ b/fl_control_plane/data_extractor/models.py
@@ -9,7 +9,7 @@
 
 from enum import StrEnum
 
-from pydantic import BaseModel, ConfigDict
+from pydantic import BaseModel, ConfigDict, Field
 
 # Cap defaults (bytes) — kept here so DownloaderConfig defaults resolve
 # without importing downloader.py (which would create a cycle once
@@ -166,9 +166,13 @@ class ExtractionResult(BaseModel):
         items_captured:     Count of items with status CAPTURED or TRUNCATED
                             (plus already-captured items found via resume).
         items_skipped:      Count of items with any SKIPPED_* status.
+        failed_stages:      (stage_name, error_message) pairs discovered during
+                            stage traversal. Caller is responsible for persisting
+                            these to the database.
     """
 
     success: bool
     error: str | None = None
     items_captured: int = 0
     items_skipped: int = 0
+    failed_stages: list[tuple[str, str | None]] = Field(default_factory=list)
diff --git a/fl_control_plane/handler_orchestrator/activity.py b/fl_control_plane/handler_orchestrator/activity.py
index deef2f4f..f57cdce3 100644
--- a/fl_control_plane/handler_orchestrator/activity.py
+++ b/fl_control_plane/handler_orchestrator/activity.py
@@ -14,6 +14,9 @@
     OrchestrateHandlersRequest,
     OrchestrateHandlersResult,
 )
+from fl_shared.hdlf_client import HdlfClient, HdlfConfigurationError
+from fl_shared.hdlf_client.config import Settings as HdlfSettings
+from hdlf_server.reader import InspectionReader
 
 log = structlog.get_logger(__name__)
 
@@ -41,27 +44,46 @@ async def orchestrate_handlers_activity(
 
     Raises:
         ApplicationError: Non-retryable (``type="InvalidInput"``) when the
-            Inspection row is not found — the inspection must exist before this
-            activity is scheduled.
+            Inspection row is not found or HDLF configuration is invalid.
         ApplicationError: Retryable (``type="TransientFailure"``) when a
             transient database error prevents loading pipeline context or
             handler rows.
     """
+    _hdlf_cfg = HdlfSettings()
+    assert _hdlf_cfg.hdlf_rest_api_host is not None  # enforced by Settings validator
+    assert _hdlf_cfg.hdlf_container_id is not None  # enforced by Settings validator
+    try:
+        hdlf_client = HdlfClient(
+            _hdlf_cfg.hdlf_rest_api_host,
+            _hdlf_cfg.hdlf_container_id,
+            cert_dir=_hdlf_cfg.hdlf_cert_dir,
+            client_certificate=_hdlf_cfg.hdlf_client_certificate,
+            client_key=_hdlf_cfg.hdlf_client_key,
+        )
+    except HdlfConfigurationError as exc:
+        raise ApplicationError(
+            f"HDLF client configuration error: {exc}",
+            type="InvalidInput",
+            non_retryable=True,
+        ) from exc
+
     async with run_with_heartbeat():
-        async with async_session() as db:
-            try:
-                result = await evaluate(request.inspection_id, db)
-            except KeyError as exc:
-                raise ApplicationError(
-                    str(exc),
-                    type="InvalidInput",
-                    non_retryable=True,
-                ) from exc
-            except SQLAlchemyError as exc:
-                raise ApplicationError(
-                    f"Transient database error during handler orchestration: {exc}",
-                    type="TransientFailure",
-                ) from exc
+        async with hdlf_client:
+            reader = InspectionReader(hdlf_client)
+            async with async_session() as db:
+                try:
+                    result = await evaluate(request.inspection_id, db, reader)
+                except KeyError as exc:
+                    raise ApplicationError(
+                        str(exc),
+                        type="InvalidInput",
+                        non_retryable=True,
+                    ) from exc
+                except SQLAlchemyError as exc:
+                    raise ApplicationError(
+                        f"Transient database error during handler orchestration: {exc}",
+                        type="TransientFailure",
+                    ) from exc
 
     log.info(
         "orchestrate_handlers_activity_complete",
diff --git a/fl_control_plane/handler_orchestrator/applicability.py b/fl_control_plane/handler_orchestrator/applicability.py
index cfbebf85..5d5ff1ec 100644
--- a/fl_control_plane/handler_orchestrator/applicability.py
+++ b/fl_control_plane/handler_orchestrator/applicability.py
@@ -2,13 +2,14 @@
 
 Implements the two handler-level evaluation stages:
   Level 2 — Infrastructure Filter (CI system, repo patterns, trigger scope, target branch)
-  Level 3 — Failure Matching (stage_scoped stage/log matching; pipeline_scoped pass-through)
+  Level 3 — Failure Matching (stage_scoped stage/log matching; pipeline_scoped log matching)
 
 Also provides weight computation and version selection for handlers that share a fault_id.
 """
 
 import fnmatch
 import json
+import re
 
 from fl_control_plane.database import FaultHandler
 from fl_control_plane.pipeline_url_validators import VALIDATORS
@@ -78,28 +79,117 @@ def filter_level2(handler: FaultHandler, ctx: PipelineContext) -> str | None:
     return None
 
 
-def match_stages(criteria: FailureMatch | None, stages: list[FailedStageContext]) -> list[str]:
-    """Return IDs of stages matching all supplied criteria.
+def compile_log_contains(pattern: str) -> re.Pattern[str] | None:
+    """Compile a log_contains regex pattern.
 
-    A stage matches when:
-      - stage_name pattern is absent OR fnmatch matches the stage's name
-      - log_contains is absent OR the substring appears in the stage's error_message
+    Returns:
+        Compiled pattern, or None if the pattern string is invalid regex.
+    """
+    try:
+        return re.compile(pattern)
+    except re.error:
+        return None
+
+
+def match_stages(
+    criteria_list: list[FailureMatch] | None,
+    stages: list[FailedStageContext],
+    stage_logs: dict[str, str],
+) -> tuple[list[str], str | None]:
+    """Return matched stage IDs and an optional rejection reason for Level 3.
+
+    Evaluates each failed stage against all entries in ``criteria_list`` using
+    OR semantics: a stage matches as soon as any single entry's conditions are
+    satisfied.
 
-    Returns an empty list when no stages match.
+    For each entry:
+      - ``stage_name`` glob (if present) must match the stage's display name.
+      - ``log_contains`` regex (if present) must find at least one match in the
+        stage's full log content from ``stage_logs``.  Stages whose log is absent
+        from ``stage_logs`` are treated as non-matching for that entry.
+
+    Args:
+        criteria_list: Match criteria from the CR, or ``None`` / empty list to
+            match every stage unconditionally (pipeline_scoped pass-through).
+        stages: Failed stages for this inspection.
+        stage_logs: Pre-fetched log content keyed by ``stage_id``.  Fetching is
+            the caller's responsibility; entries may be absent when the log could
+            not be retrieved.
+
+    Returns:
+        A tuple of ``(matched_stage_ids, rejection_reason)``.  When a
+        ``log_contains`` pattern fails to compile, ``matched_stage_ids`` is empty
+        and ``rejection_reason`` names the offending pattern.  When no stages
+        match, ``matched_stage_ids`` is empty and ``rejection_reason`` is
+        ``None`` (the caller records the miss separately).
     """
+    if not criteria_list:
+        return [stage.stage_id for stage in stages], None
+
+    for entry in criteria_list:
+        if entry.log_contains is not None:
+            if compile_log_contains(entry.log_contains) is None:
+                return [], f"log_contains pattern is not valid regex: {entry.log_contains!r}"
+
     matched: list[str] = []
     for stage in stages:
-        if criteria is not None:
-            if criteria.stage_name is not None:
-                if not fnmatch.fnmatch(stage.stage_name, criteria.stage_name):
-                    continue
-            if criteria.log_contains is not None:
-                message = stage.error_message or ""
-                if criteria.log_contains not in message:
-                    continue
-            # TODO: evaluate 'relevance' score from architecture once defined
-        matched.append(stage.stage_id)
-    return matched
+        if _stage_matches_any(criteria_list, stage, stage_logs):
+            matched.append(stage.stage_id)
+    return matched, None
+
+
+def _stage_matches_any(
+    criteria_list: list[FailureMatch],
+    stage: FailedStageContext,
+    stage_logs: dict[str, str],
+) -> bool:
+    """Return True if the stage satisfies at least one entry in criteria_list."""
+    for entry in criteria_list:
+        if entry.stage_name is not None:
+            if not fnmatch.fnmatch(stage.stage_name, entry.stage_name):
+                continue
+        if entry.log_contains is not None:
+            log_content = stage_logs.get(stage.stage_id, "")
+            if not re.search(entry.log_contains, log_content):
+                continue
+        return True
+    return False
+
+
+def match_pipeline(
+    criteria_list: list[FailureMatch] | None,
+    pipeline_log: str | None,
+) -> tuple[bool, str | None]:
+    """Return whether the pipeline log matches and an optional rejection reason.
+
+    Args:
+        criteria_list: Match criteria from the CR, or ``None`` / empty list to
+            match unconditionally.
+        pipeline_log: Full pipeline console log, or ``None`` when unavailable.
+
+    Returns:
+        A tuple of ``(matched, rejection_reason)``.  ``rejection_reason`` is set
+        when a ``log_contains`` pattern fails to compile; in that case ``matched``
+        is ``False``.  When the log is unavailable, ``matched`` is ``False`` and
+        ``rejection_reason`` names the missing-log cause.
+    """
+    if not criteria_list:
+        return True, None
+
+    for entry in criteria_list:
+        if entry.log_contains is not None:
+            if compile_log_contains(entry.log_contains) is None:
+                return False, f"log_contains pattern is not valid regex: {entry.log_contains!r}"
+
+    if pipeline_log is None:
+        return False, "pipeline log unavailable"
+
+    for entry in criteria_list:
+        if entry.log_contains is not None:
+            if re.search(entry.log_contains, pipeline_log):
+                return True, None
+
+    return False, None
 
 
 def compute_weight(handler: FaultHandler) -> float:
diff --git a/fl_control_plane/handler_orchestrator/models.py b/fl_control_plane/handler_orchestrator/models.py
index 279916fd..cd1a752c 100644
--- a/fl_control_plane/handler_orchestrator/models.py
+++ b/fl_control_plane/handler_orchestrator/models.py
@@ -8,10 +8,20 @@
 
 
 class FailedStageContext(BaseModel):
-    """A single failed stage within an inspection, as loaded from the DB."""
+    """A single failed stage within an inspection, as loaded from the DB.
+
+    Attributes:
+        stage_dir: HDLF subdirectory name for this stage, derived via
+            ``safe_name(stage_name)``.  Pass to ``InspectionReader.stream_stage_log``.
+            May differ from ``stage_name`` when the display name contained
+            special characters or when the Data Extractor appended a node-id
+            suffix to resolve collisions — in those cases the log may not be
+            found and the handler will be treated as non-matching.
+    """
 
     stage_id: str
     stage_name: str
+    stage_dir: str
     error_message: str | None
 
 
@@ -43,19 +53,37 @@ class ApplicabilityDecision(BaseModel):
     Attributes:
         result:
             "matched"         — handler passed all levels and will be executed.
-            "filtered_level2" — rejected by infrastructure filter.
-            "filtered_level3" — no failed stages matched (stage_scoped only).
+            "filtered_infrastructure" — rejected by infrastructure filter.
+            "filtered_log_match" — no failed stages matched (stage_scoped only).
             "selected_out"    — superseded by a higher-weight CR with same fault_id.
     """
 
     handler_db_id: str
     fault_id: str
     handler_name: str
-    result: Literal["matched", "filtered_level2", "filtered_level3", "selected_out"]
+    result: Literal["matched", "filtered_infrastructure", "filtered_log_match", "selected_out"]
     reason: str
     matched_stage_ids: list[str] = []
 
 
+class HandlerEvalResult(BaseModel):
+    """Result of evaluating a single handler's applicability.
+
+    Attributes:
+        is_matched: True when the handler passed all filters.
+        scope: "pipeline" for pipeline_scoped handlers, "stage" for stage_scoped.
+        matched_stages: Stage IDs matched for stage_scoped handlers. Empty for
+            pipeline_scoped handlers (they match at the pipeline level, not per stage).
+        rejection: Set when is_matched is False — describes why the handler was excluded.
+            None when is_matched is True.
+    """
+
+    is_matched: bool
+    scope: Literal["pipeline", "stage"]
+    matched_stages: list[str] = []
+    rejection: ApplicabilityDecision | None = None
+
+
 class OrchestrationResult(BaseModel):
     """The output of the Handler Orchestrator for one inspection.
 
diff --git a/fl_control_plane/handler_orchestrator/orchestrator.py b/fl_control_plane/handler_orchestrator/orchestrator.py
index 68e28295..1011e383 100644
--- a/fl_control_plane/handler_orchestrator/orchestrator.py
+++ b/fl_control_plane/handler_orchestrator/orchestrator.py
@@ -5,24 +5,32 @@
 not write any database rows.
 """
 
+import asyncio
 import json
 import logging
 
+from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
+
 from sqlalchemy import select
 from sqlalchemy.ext.asyncio import AsyncSession
 
 from fl_control_plane.database import FailedStage, FaultHandler, Inspection
 from fl_shared.cr_models import FailureMatch, FaultHandlerSpec
+from fl_shared.inspection_layout import safe_name
+from hdlf_server.exceptions import HdlfUnreachableError, InspectionFileNotFoundError
+from hdlf_server.reader import InspectionReader
 
 from .applicability import (
     detect_ci_system,
     filter_level2,
+    match_pipeline,
     match_stages,
     select_versions,
 )
 from .models import (
     ApplicabilityDecision,
     FailedStageContext,
+    HandlerEvalResult,
     OrchestrationResult,
     PipelineContext,
 )
@@ -44,6 +52,7 @@ async def _load_pipeline_context(inspection_id: str, db: AsyncSession) -> Pipeli
         FailedStageContext(
             stage_id=stage.id,
             stage_name=stage.stage_name,
+            stage_dir=safe_name(stage.stage_name),
             error_message=stage.error_message,
         )
         for stage in stages_result.scalars().all()
@@ -63,7 +72,9 @@ async def _load_pipeline_context(inspection_id: str, db: AsyncSession) -> Pipeli
 
 async def _load_active_handlers(db: AsyncSession) -> list[FaultHandler]:
     """Load all active FaultHandler rows from the DB."""
-    result = await db.execute(select(FaultHandler).where(FaultHandler.is_active == True)) # noqa: E712 - SAP HANA does not support `IS true`
+    result = await db.execute(
+        select(FaultHandler).where(FaultHandler.is_active == True)  # noqa: E712 # pylint: disable=singleton-comparison
+    )
     return list(result.scalars().all())
 
 
@@ -90,49 +101,80 @@ def _evaluate_handler(
     handler: FaultHandler,
     spec: FaultHandlerSpec,
     ctx: PipelineContext,
-) -> tuple[list[str], ApplicabilityDecision | None]:
+    stage_logs: dict[str, str],
+    pipeline_log: str | None,
+) -> HandlerEvalResult:
     """Apply Level 2 and Level 3 filters to a single handler.
 
+    Args:
+        stage_logs: Pre-fetched log content keyed by stage_id, for stage_scoped evaluation.
+        pipeline_log: Pre-fetched full pipeline console log, or None if unavailable.
+
     Returns:
-        (matched_stage_ids, rejection_decision) — if rejected, matched_stage_ids
-        is empty and rejection_decision is set. If accepted, rejection_decision is None.
+        HandlerEvalResult with is_matched=True when the handler passed all filters,
+        or is_matched=False with rejection set explaining why it was excluded.
     """
     level2_reason = filter_level2(handler, ctx)
     if level2_reason is not None:
-        return [], ApplicabilityDecision(
-            handler_db_id=handler.id,
-            fault_id=handler.fault_id,
-            handler_name=handler.cr_name,
-            result="filtered_level2",
-            reason=level2_reason,
+        return HandlerEvalResult(
+            is_matched=False,
+            scope="pipeline",
+            rejection=ApplicabilityDecision(
+                handler_db_id=handler.id,
+                fault_id=handler.fault_id,
+                handler_name=handler.cr_name,
+                result="filtered_infrastructure",
+                reason=level2_reason,
+            ),
         )
 
     failure_match = spec.applicability and spec.applicability.failure_match
     strategy = (failure_match and failure_match.strategy) or handler.strategy
+    criteria_list: list[FailureMatch] | None = failure_match.match if failure_match else None
 
     if strategy == "pipeline_scoped":
-        return [], None
-
-    match_criteria = failure_match.match if failure_match else None
-    # controller writes match as a list; match_stages expects a single entry
-    if isinstance(match_criteria, list):
-        match_criteria_narrowed: FailureMatch | None = match_criteria[0] if match_criteria else None
-    elif isinstance(match_criteria, FailureMatch):
-        match_criteria_narrowed = match_criteria
-    else:
-        match_criteria_narrowed = None
-
-    matched_stage_ids = match_stages(match_criteria_narrowed, ctx.failed_stages)
+        matched, reason = match_pipeline(criteria_list, pipeline_log)
+        if not matched:
+            return HandlerEvalResult(
+                is_matched=False,
+                scope="pipeline",
+                rejection=ApplicabilityDecision(
+                    handler_db_id=handler.id,
+                    fault_id=handler.fault_id,
+                    handler_name=handler.cr_name,
+                    result="filtered_log_match",
+                    reason=reason or "pipeline log did not match handler's log_contains criteria",
+                ),
+            )
+        return HandlerEvalResult(is_matched=True, scope="pipeline")
+
+    matched_stage_ids, reason = match_stages(criteria_list, ctx.failed_stages, stage_logs)
+    if reason is not None:
+        return HandlerEvalResult(
+            is_matched=False,
+            scope="stage",
+            rejection=ApplicabilityDecision(
+                handler_db_id=handler.id,
+                fault_id=handler.fault_id,
+                handler_name=handler.cr_name,
+                result="filtered_log_match",
+                reason=reason,
+            ),
+        )
     if not matched_stage_ids:
-        return [], ApplicabilityDecision(
-            handler_db_id=handler.id,
-            fault_id=handler.fault_id,
-            handler_name=handler.cr_name,
-            result="filtered_level3",
-            reason="no failed stages matched handler's match criteria",
+        return HandlerEvalResult(
+            is_matched=False,
+            scope="stage",
+            rejection=ApplicabilityDecision(
+                handler_db_id=handler.id,
+                fault_id=handler.fault_id,
+                handler_name=handler.cr_name,
+                result="filtered_log_match",
+                reason="no failed stages matched handler's log_contains or stage_name criteria",
+            ),
         )
 
-    return matched_stage_ids, None
+    return HandlerEvalResult(is_matched=True, scope="stage", matched_stages=matched_stage_ids)
 
 
 def _build_handler_cr(handler: FaultHandler, spec: FaultHandlerSpec) -> FaultHandlerSpec:
@@ -140,65 +182,193 @@ def _build_handler_cr(handler: FaultHandler, spec: FaultHandlerSpec) -> FaultHan
     return spec.model_copy(update={"fault_id": handler.fault_id})
 
 
-# pylint: disable=too-many-locals
-async def evaluate(inspection_id: str, db: AsyncSession) -> OrchestrationResult:
-    """Evaluate all active FaultHandlers and return an OrchestrationResult.
+@retry(
+    retry=retry_if_exception_type(HdlfUnreachableError),
+    stop=stop_after_attempt(3),
+    wait=wait_exponential(multiplier=1, max=8),
+)
+async def _fetch_stage_log(
+    reader: InspectionReader,
+    inspection_id: str,
+    stage: FailedStageContext,
+) -> str | None:
+    """Fetch and return the full log for a single stage, or None on failure.
+
+    Retries up to 3 times on HdlfUnreachableError (transient HDLF failures).
+    Returns None on InspectionFileNotFoundError or after retries are exhausted.
+    """
+    try:
+        chunks: list[bytes] = []
+        async for chunk in reader.stream_stage_log(inspection_id, stage.stage_dir):
+            chunks.append(chunk)
+        return b"".join(chunks).decode("utf-8", errors="replace")
+    except InspectionFileNotFoundError:
+        logger.warning(
+            "stage_log_not_found",
+            extra={"inspection_id": inspection_id, "stage_id": stage.stage_id, "stage_dir": stage.stage_dir},
+        )
+        return None
 
-    Read-only — does not write any database rows.
 
-    Usage:
-        result = await evaluate(inspection_id, db)
-        # The workflow submits and polls each selected handler.
+@retry(
+    retry=retry_if_exception_type(HdlfUnreachableError),
+    stop=stop_after_attempt(3),
+    wait=wait_exponential(multiplier=1, max=8),
+)
+async def _fetch_pipeline_log(
+    reader: InspectionReader,
+    inspection_id: str,
+) -> str | None:
+    """Fetch and return the full pipeline console log, or None on failure.
+
+    Retries up to 3 times on HdlfUnreachableError (transient HDLF failures).
+    Returns None on InspectionFileNotFoundError or after retries are exhausted.
+    """
+    try:
+        chunks: list[bytes] = []
+        async for chunk in reader.stream_console_log(inspection_id):
+            chunks.append(chunk)
+        return b"".join(chunks).decode("utf-8", errors="replace")
+    except InspectionFileNotFoundError:
+        logger.warning(
+            "pipeline_log_not_found",
+            extra={"inspection_id": inspection_id},
+        )
+        return None
 
-    Args:
-        inspection_id: UUID of the inspection to evaluate.
-        db: Active async database session.
 
-    Raises:
-        KeyError: No inspection row found for inspection_id.
+def _needed_logs(
+    ctx: PipelineContext,
+    handlers: list[tuple[FaultHandler, FaultHandlerSpec]],
+) -> tuple[set[str], bool]:
+    """Return (needed_stage_ids, needs_pipeline_log) for a set of candidate handlers."""
+    needs_pipeline_log = False
+    needed_stage_ids: set[str] = set()
+
+    for handler, spec in handlers:
+        failure_match = spec.applicability and spec.applicability.failure_match
+        strategy = (failure_match and failure_match.strategy) or handler.strategy
+        criteria_list = failure_match.match if failure_match else None
+
+        if strategy == "pipeline_scoped":
+            if criteria_list and any(e.log_contains for e in criteria_list):
+                needs_pipeline_log = True
+        else:
+            if criteria_list and any(e.log_contains for e in criteria_list):
+                for stage in ctx.failed_stages:
+                    needed_stage_ids.add(stage.stage_id)
+
+    return needed_stage_ids, needs_pipeline_log
+
+
+async def _prefetch_logs(
+    reader: InspectionReader,
+    inspection_id: str,
+    ctx: PipelineContext,
+    handlers: list[tuple[FaultHandler, FaultHandlerSpec]],
+) -> tuple[dict[str, str], str | None]:
+    """Fetch each required log at most once across all candidate handlers.
+
+    Returns:
+        stage_logs: dict mapping stage_id → log text for stages whose log was needed
+            and successfully fetched.
+        pipeline_log: Full pipeline console log text, or None if not needed or unavailable.
     """
-    ctx = await _load_pipeline_context(inspection_id, db)
-    handlers = await _load_active_handlers(db)
+    needed_stage_ids, needs_pipeline_log = _needed_logs(ctx, handlers)
+    stage_by_id = {stage.stage_id: stage for stage in ctx.failed_stages}
+
+    stage_log_tasks = {
+        stage_id: asyncio.create_task(_fetch_stage_log(reader, inspection_id, stage_by_id[stage_id]))
+        for stage_id in needed_stage_ids
+    }
+    pipeline_log_task = asyncio.create_task(_fetch_pipeline_log(reader, inspection_id)) if needs_pipeline_log else None
+
+    stage_logs: dict[str, str] = {}
+    for stage_id, task in stage_log_tasks.items():
+        try:
+            result = await task
+        except HdlfUnreachableError:
+            logger.warning(
+                "stage_log_fetch_failed_after_retries",
+                extra={"inspection_id": inspection_id, "stage_id": stage_id},
+            )
+            result = None
+        if result is not None:
+            stage_logs[stage_id] = result
+
+    pipeline_log: str | None = None
+    if pipeline_log_task is not None:
+        try:
+            pipeline_log = await pipeline_log_task
+        except HdlfUnreachableError:
+            logger.warning(
+                "pipeline_log_fetch_failed_after_retries",
+                extra={"inspection_id": inspection_id},
+            )
 
-    decisions: list[ApplicabilityDecision] = []
-    candidates: list[_Candidate] = []
+    return stage_logs, pipeline_log
 
+
+def _parse_handlers(
+    handlers: list[FaultHandler],
+) -> tuple[list[tuple[FaultHandler, FaultHandlerSpec]], list[FaultHandler]]:
+    """Parse spec_json for each handler, returning (parsed, unparseable).
+
+    Args:
+        handlers: Active FaultHandler rows to parse.
+
+    Returns:
+        parsed: Handlers whose spec_json was successfully parsed.
+        unparseable: Handlers whose spec_json was missing or malformed.
+    """
+    parsed: list[tuple[FaultHandler, FaultHandlerSpec]] = []
+    unparseable: list[FaultHandler] = []
     for handler in handlers:
         spec = _parse_spec(handler)
         if spec is None:
-            decisions.append(
-                ApplicabilityDecision(
-                    handler_db_id=handler.id,
-                    fault_id=handler.fault_id,
-                    handler_name=handler.cr_name,
-                    result="filtered_level2",
-                    reason="spec_json missing or unparseable",
-                )
-            )
-            continue
+            unparseable.append(handler)
+        else:
+            parsed.append((handler, spec))
+    return parsed, unparseable
 
-        matched_stage_ids, rejection = _evaluate_handler(handler, spec, ctx)
-        if rejection is not None:
-            decisions.append(rejection)
-            continue
 
-        candidates.append((handler, spec, matched_stage_ids))
+def _filter_candidates(
+    parsed: list[tuple[FaultHandler, FaultHandlerSpec]],
+    ctx: PipelineContext,
+    stage_logs: dict[str, str],
+    pipeline_log: str | None,
+) -> dict[str, HandlerEvalResult]:
+    """Evaluate each handler against Level 2+3 filters.
 
-    selected_pairs, discarded = select_versions([(h, ids) for h, _, ids in candidates])
+    Returns a dict mapping handler.id → HandlerEvalResult for every handler,
+    so callers can look up the outcome for any handler in one place.
+    """
+    return {handler.id: _evaluate_handler(handler, spec, ctx, stage_logs, pipeline_log) for handler, spec in parsed}
 
-    for loser, reason in discarded:
-        decisions.append(
-            ApplicabilityDecision(
-                handler_db_id=loser.id,
-                fault_id=loser.fault_id,
-                handler_name=loser.cr_name,
-                result="selected_out",
-                reason=reason,
-            )
-        )
 
+def _build_selected(
+    candidates: list[_Candidate],
+    inspection_id: str,
+) -> tuple[list[FaultHandlerSpec], list[ApplicabilityDecision]]:
+    """Run version selection and return (selected_handlers, all_decisions).
+
+    Decisions include both selected_out and matched entries — callers
+    can distinguish them via ApplicabilityDecision.result.
+    """
+    selected_pairs, discarded = select_versions([(h, ids) for h, _, ids in candidates])
     spec_by_handler_id = {h.id: spec for h, spec, _ in candidates}
 
+    decisions: list[ApplicabilityDecision] = [
+        ApplicabilityDecision(
+            handler_db_id=loser.id,
+            fault_id=loser.fault_id,
+            handler_name=loser.cr_name,
+            result="selected_out",
+            reason=reason,
+        )
+        for loser, reason in discarded
+    ]
+
     selected_handlers: list[FaultHandlerSpec] = []
     for handler, matched_stage_ids in selected_pairs:
         spec = spec_by_handler_id[handler.id]
@@ -218,6 +388,69 @@ async def evaluate(inspection_id: str, db: AsyncSession) -> OrchestrationResult:
             extra={"inspection_id": inspection_id, "fault_id": handler.fault_id, "handler": handler.cr_name},
         )
 
+    return selected_handlers, decisions
+
+
+def _collect_candidates(
+    parsed: list[tuple[FaultHandler, FaultHandlerSpec]],
+    eval_results: dict[str, HandlerEvalResult],
+) -> tuple[list[_Candidate], list[ApplicabilityDecision]]:
+    """Split eval results into matched candidates and rejection decisions."""
+    spec_by_id = {handler.id: spec for handler, spec in parsed}
+    candidates: list[_Candidate] = []
+    rejections: list[ApplicabilityDecision] = []
+    for handler, _ in parsed:
+        result = eval_results[handler.id]
+        if result.is_matched:
+            candidates.append((handler, spec_by_id[handler.id], result.matched_stages))
+        elif result.rejection is not None:
+            rejections.append(result.rejection)
+    return candidates, rejections
+
+
+def _unparseable_decision(handler: FaultHandler) -> ApplicabilityDecision:
+    """Build a rejection decision for a handler whose spec_json could not be parsed."""
+    return ApplicabilityDecision(
+        handler_db_id=handler.id,
+        fault_id=handler.fault_id,
+        handler_name=handler.cr_name,
+        result="filtered_infrastructure",
+        reason="spec_json missing or unparseable",
+    )
+
+
+async def evaluate(  # pylint: disable=too-many-locals
+    inspection_id: str,
+    db: AsyncSession,
+    reader: InspectionReader,
+) -> OrchestrationResult:
+    """Evaluate all active FaultHandlers and return an OrchestrationResult.
+
+    Read-only — does not write any database rows.
+
+    Usage:
+        result = await evaluate(inspection_id, db, reader)
+        # The workflow submits and polls each selected handler.
+
+    Args:
+        inspection_id: UUID of the inspection to evaluate.
+        db: Active async database session.
+        reader: Open InspectionReader for fetching stage and pipeline logs.
+
+    Raises:
+        KeyError: No inspection row found for inspection_id.
+    """
+    ctx = await _load_pipeline_context(inspection_id, db)
+    handlers = await _load_active_handlers(db)
+
+    parsed, unparseable = _parse_handlers(handlers)
+    stage_logs, pipeline_log = await _prefetch_logs(reader, inspection_id, ctx, parsed)
+    eval_results = _filter_candidates(parsed, ctx, stage_logs, pipeline_log)
+    candidates, filter_rejections = _collect_candidates(parsed, eval_results)
+    selected_handlers, selection_decisions = _build_selected(candidates, inspection_id)
+
+    decisions = [_unparseable_decision(h) for h in unparseable] + filter_rejections + selection_decisions
+
     logger.info(
         "orchestration_complete",
         extra={
diff --git a/fl_control_plane/temporal/models.py b/fl_control_plane/temporal/models.py
index 5f66d47a..75ec5a04 100644
--- a/fl_control_plane/temporal/models.py
+++ b/fl_control_plane/temporal/models.py
@@ -532,7 +532,7 @@ class OrchestrateHandlersResult(BaseModel):
                 {
                     "handler_db_id": "...", "fault_id": "hadolint-analysis",
                     "handler_name": "hadolint-analysis",
-                    "result": "filtered_level3", "reason": "no failed stages matched handler's match criteria",
+                    "result": "filtered_log_match", "reason": "no failed stages matched handler's match criteria",
                     "matched_stage_ids": []
                 }
             ]
diff --git a/openspec/changes/fl-control-plane-rearchitecture/specs/observability/spec.md b/openspec/changes/fl-control-plane-rearchitecture/specs/observability/spec.md
index 85c303c6..85c9dcca 100644
--- a/openspec/changes/fl-control-plane-rearchitecture/specs/observability/spec.md
+++ b/openspec/changes/fl-control-plane-rearchitecture/specs/observability/spec.md
@@ -42,4 +42,4 @@ For every analysis run, FL SHALL store a decision record for each evaluated hand
 
 #### Scenario: Rationale visible in Admin UI and audit log
 - **WHEN** an operator inspects an analysis run in the Admin UI
-- **THEN** they can see for each handler: `matched`, `filtered_level2: ci_system_mismatch`, `filtered_level3: no_matching_stages`, or `executed`, with the specific reason
+- **THEN** they can see for each handler: `matched`, `filtered_infrastructure: ci_system_mismatch`, `filtered_log_match: no_matching_stages`, or `executed`, with the specific reason
diff --git a/tests/handler_orchestrator/test_applicability.py b/tests/handler_orchestrator/test_applicability.py
index 5bdb55d1..ada29b08 100644
--- a/tests/handler_orchestrator/test_applicability.py
+++ b/tests/handler_orchestrator/test_applicability.py
@@ -6,6 +6,7 @@
     compute_weight,
     detect_ci_system,
     filter_level2,
+    match_pipeline,
     match_stages,
     select_versions,
 )
@@ -43,9 +44,15 @@ def _ctx(
 def _stage(
     stage_id: str = "s1",
     stage_name: str = "build",
+    stage_dir: str = "build",
     error_message: str | None = None,
 ) -> FailedStageContext:
-    return FailedStageContext(stage_id=stage_id, stage_name=stage_name, error_message=error_message)
+    return FailedStageContext(
+        stage_id=stage_id,
+        stage_name=stage_name,
+        stage_dir=stage_dir,
+        error_message=error_message,
+    )
 
 
 # ---------------------------------------------------------------------------
@@ -197,56 +204,287 @@ def test_filter_level2_merge_target_branch_skipped_when_target_unknown():
 
 
 # ---------------------------------------------------------------------------
-# match_stages
+# match_stages — no criteria (pipeline_scoped pass-through)
 # ---------------------------------------------------------------------------
 
 
-def test_match_stages_pipeline_scoped_returns_all():
-    """None criteria (pipeline_scoped) matches every stage."""
+def test_match_stages_none_criteria_returns_all_stages():
+    """None criteria (pipeline_scoped pass-through) matches every stage."""
+    stages = [_stage("s1", "build"), _stage("s2", "test")]
+    ids, reason = match_stages(None, stages, {})
+    assert set(ids) == {"s1", "s2"}
+    assert reason is None
+
+
+def test_match_stages_empty_criteria_list_returns_all_stages():
+    """Empty criteria list matches every stage unconditionally."""
     stages = [_stage("s1", "build"), _stage("s2", "test")]
-    assert set(match_stages(None, stages)) == {"s1", "s2"}
+    ids, reason = match_stages([], stages, {})
+    assert set(ids) == {"s1", "s2"}
+    assert reason is None
+
+
+def test_match_stages_no_stages_returns_empty():
+    """Returns empty list when inspection has no failed stages."""
+    ids, reason = match_stages(None, [], {})
+    assert ids == []
+    assert reason is None
+
+
+# ---------------------------------------------------------------------------
+# match_stages — stage_name glob
+# ---------------------------------------------------------------------------
 
 
 def test_match_stages_stage_name_glob_matches():
     """stage_name glob matches matching stages only."""
-    stages = [_stage("s1", "sonarqube-scan"), _stage("s2", "build"), _stage("s3", "sonarqube-gate")]
-    matched = match_stages(StageMatchCriteria(stage_name="sonarqube*"), stages)
-    assert set(matched) == {"s1", "s3"}
+    stages = [
+        _stage("s1", "sonarqube-scan"),
+        _stage("s2", "build"),
+        _stage("s3", "sonarqube-gate"),
+    ]
+    ids, reason = match_stages([StageMatchCriteria(stage_name="sonarqube*")], stages, {})
+    assert set(ids) == {"s1", "s3"}
+    assert reason is None
+
+
+def test_match_stages_stage_name_glob_no_match_returns_empty():
+    """Returns empty list when stage_name glob matches no stage."""
+    stages = [_stage("s1", "build")]
+    ids, reason = match_stages([StageMatchCriteria(stage_name="sonarqube*")], stages, {})
+    assert ids == []
+    assert reason is None
 
 
-def test_match_stages_log_contains_matches():
-    """log_contains substring matches stages with that text in error_message."""
+# ---------------------------------------------------------------------------
+# match_stages — log_contains regex
+# ---------------------------------------------------------------------------
+
+
+def test_match_stages_log_contains_regex_matches():
+    """log_contains regex matches stages whose log contains text matching the pattern."""
     stages = [
-        _stage("s1", "build", error_message="error: piper sonarExecuteScan failed"),
-        _stage("s2", "build", error_message="error: unit test failure"),
+        _stage("s1", "build"),
+        _stage("s2", "build"),
     ]
-    matched = match_stages(StageMatchCriteria(log_contains="sonarExecuteScan"), stages)
-    assert matched == ["s1"]
+    stage_logs = {
+        "s1": "error: npm ERR! ENOSPC: no space left on device",
+        "s2": "error: unit test failure",
+    }
+    ids, reason = match_stages(
+        [StageMatchCriteria(log_contains=r"npm ERR! ENOSPC[^\n]*no space left on device")],
+        stages,
+        stage_logs,
+    )
+    assert ids == ["s1"]
+    assert reason is None
 
 
-def test_match_stages_both_criteria_must_match():
+def test_match_stages_log_contains_regex_no_match_returns_empty():
+    """Returns empty list when log_contains regex matches no stage log."""
+    stages = [_stage("s1", "build")]
+    stage_logs = {"s1": "everything is fine"}
+    ids, reason = match_stages(
+        [StageMatchCriteria(log_contains="OOMKilled")],
+        stages,
+        stage_logs,
+    )
+    assert ids == []
+    assert reason is None
+
+
+def test_match_stages_log_contains_missing_log_treated_as_no_match():
+    """Stage whose log is absent from stage_logs is treated as non-matching."""
+    stages = [_stage("s1", "build")]
+    ids, reason = match_stages(
+        [StageMatchCriteria(log_contains="OOMKilled")],
+        stages,
+        {},  # no log available for s1
+    )
+    assert ids == []
+    assert reason is None
+
+
+def test_match_stages_stage_name_and_log_contains_both_must_match():
     """Both stage_name and log_contains must match — neither alone is sufficient."""
     stages = [
         _stage("s1", "sonarqube", error_message="unrelated error"),
         _stage("s2", "build", error_message="sonarExecuteScan failed"),
         _stage("s3", "sonarqube", error_message="sonarExecuteScan failed"),
     ]
-    matched = match_stages(
-        StageMatchCriteria(stage_name="sonarqube*", log_contains="sonarExecuteScan"),
+    stage_logs = {
+        "s1": "unrelated error",
+        "s2": "sonarExecuteScan failed",
+        "s3": "sonarExecuteScan failed",
+    }
+    ids, reason = match_stages(
+        [StageMatchCriteria(stage_name="sonarqube*", log_contains="sonarExecuteScan")],
+        stages,
+        stage_logs,
+    )
+    assert ids == ["s3"]
+    assert reason is None
+
+
+# ---------------------------------------------------------------------------
+# match_stages — OR semantics across entries
+# ---------------------------------------------------------------------------
+
+
+def test_match_stages_or_semantics_any_entry_can_match():
+    """A stage matches when any single entry's conditions are satisfied."""
+    stages = [
+        _stage("s1", "build"),
+        _stage("s2", "test"),
+    ]
+    stage_logs = {
+        "s1": "npm ERR! ENOSPC: no space left on device",
+        "s2": "junit test failure",
+    }
+    ids, reason = match_stages(
+        [
+            StageMatchCriteria(log_contains="ENOSPC"),
+            StageMatchCriteria(log_contains="junit"),
+        ],
         stages,
+        stage_logs,
     )
-    assert matched == ["s3"]
+    assert set(ids) == {"s1", "s2"}
+    assert reason is None
 
 
-def test_match_stages_no_match_returns_empty():
-    """Returns empty list when no stages match."""
+def test_match_stages_or_semantics_first_entry_matches_stage():
+    """Stage matched by the first entry is included even when the second would not match."""
     stages = [_stage("s1", "build")]
-    assert not match_stages(StageMatchCriteria(stage_name="sonarqube*"), stages)
+    stage_logs = {"s1": "ENOSPC error occurred"}
+    ids, reason = match_stages(
+        [
+            StageMatchCriteria(log_contains="ENOSPC"),
+            StageMatchCriteria(log_contains="OOMKilled"),
+        ],
+        stages,
+        stage_logs,
+    )
+    assert ids == ["s1"]
+    assert reason is None
 
 
-def test_match_stages_no_stages_returns_empty():
-    """Returns empty list when inspection has no failed stages."""
-    assert not match_stages(None, [])
+# ---------------------------------------------------------------------------
+# match_stages — invalid regex
+# ---------------------------------------------------------------------------
+
+
+def test_match_stages_invalid_regex_returns_rejection_reason():
+    """Invalid log_contains regex causes rejection with a reason describing the error."""
+    stages = [_stage("s1", "build")]
+    ids, reason = match_stages(
+        [StageMatchCriteria(log_contains="[invalid(regex")],
+        stages,
+        {},
+    )
+    assert ids == []
+    assert reason is not None
+    assert "[invalid(regex" in reason
+
+
+def test_match_stages_invalid_regex_in_one_entry_rejects_entire_handler():
+    """Even one invalid regex in the list rejects the handler immediately."""
+    stages = [_stage("s1", "build")]
+    stage_logs = {"s1": "ENOSPC error"}
+    ids, reason = match_stages(
+        [
+            StageMatchCriteria(log_contains="ENOSPC"),  # valid
+            StageMatchCriteria(log_contains="[bad"),  # invalid
+        ],
+        stages,
+        stage_logs,
+    )
+    assert ids == []
+    assert reason is not None
+
+
+# ---------------------------------------------------------------------------
+# match_pipeline
+# ---------------------------------------------------------------------------
+
+
+def test_match_pipeline_no_criteria_always_matches():
+    """None criteria list matches unconditionally regardless of log content."""
+    matched, reason = match_pipeline(None, "any log content")
+    assert matched is True
+    assert reason is None
+
+
+def test_match_pipeline_empty_criteria_always_matches():
+    """Empty criteria list matches unconditionally."""
+    matched, reason = match_pipeline([], "any log content")
+    assert matched is True
+    assert reason is None
+
+
+def test_match_pipeline_log_contains_matches():
+    """Pipeline log containing the regex pattern results in a match."""
+    matched, reason = match_pipeline(
+        [StageMatchCriteria(log_contains="OOMKilled")],
+        "pod was OOMKilled during build",
+    )
+    assert matched is True
+    assert reason is None
+
+
+def test_match_pipeline_log_contains_no_match():
+    """Pipeline log not matching the regex results in no match."""
+    matched, reason = match_pipeline(
+        [StageMatchCriteria(log_contains="OOMKilled")],
+        "build failed: timeout exceeded",
+    )
+    assert matched is False
+    assert reason is None
+
+
+def test_match_pipeline_log_unavailable_not_matched():
+    """When the pipeline log is None (unavailable), the handler does not match."""
+    matched, reason = match_pipeline(
+        [StageMatchCriteria(log_contains="OOMKilled")],
+        None,
+    )
+    assert matched is False
+    assert reason is not None
+    assert "unavailable" in reason
+
+
+def test_match_pipeline_or_semantics_any_entry_matches():
+    """Pipeline matches when any entry's log_contains pattern matches."""
+    matched, reason = match_pipeline(
+        [
+            StageMatchCriteria(log_contains="OOMKilled"),
+            StageMatchCriteria(log_contains="ENOSPC"),
+        ],
+        "npm ERR! ENOSPC: no space left on device",
+    )
+    assert matched is True
+    assert reason is None
+
+
+def test_match_pipeline_invalid_regex_returns_reason():
+    """Invalid log_contains regex is rejected with a reason."""
+    matched, reason = match_pipeline(
+        [StageMatchCriteria(log_contains="[invalid")],
+        "some log content",
+    )
+    assert matched is False
+    assert reason is not None
+    assert "[invalid" in reason
+
+
+def test_match_pipeline_entry_without_log_contains_is_skipped():
+    """An entry with no log_contains is skipped — only None/empty criteria_list matches unconditionally."""
+    matched, reason = match_pipeline(
+        [StageMatchCriteria(log_contains=None)],
+        "any log",
+    )
+    assert matched is False
+    assert reason is None
 
 
 # ---------------------------------------------------------------------------
diff --git a/tests/handler_orchestrator/test_orchestrator.py b/tests/handler_orchestrator/test_orchestrator.py
index 606ef676..8298e358 100644
--- a/tests/handler_orchestrator/test_orchestrator.py
+++ b/tests/handler_orchestrator/test_orchestrator.py
@@ -1,6 +1,7 @@
 """Integration tests for orchestrator.evaluate() — uses the in-memory test DB."""
 
 import uuid
+from unittest.mock import MagicMock
 
 import pytest
 import pytest_asyncio
@@ -19,6 +20,21 @@ async def session(
         yield s
 
 
+def _make_reader(*, stage_log: str = "", pipeline_log: str = "") -> MagicMock:
+    """Build a minimal InspectionReader mock that returns empty logs by default."""
+
+    async def _stream_stage(inspection_id: str, stage_dir: str):
+        yield stage_log.encode()
+
+    async def _stream_console(inspection_id: str):
+        yield pipeline_log.encode()
+
+    reader = MagicMock()
+    reader.stream_stage_log = _stream_stage
+    reader.stream_console_log = _stream_console
+    return reader
+
+
 async def _insert(session: AsyncSession, *objects) -> None:
     for obj in objects:
         session.add(obj)
@@ -41,7 +57,7 @@ async def test_evaluate_empty_handlers_returns_empty_result(session: AsyncSessio
     inspection = _make_inspection()
     await _insert(session, inspection)
 
-    result = await evaluate(inspection.id, session)
+    result = await evaluate(inspection.id, session, _make_reader())
 
     assert result.handlers == []
     assert result.decisions == []
@@ -58,7 +74,7 @@ async def test_evaluate_single_matching_handler_in_result(session: AsyncSession)
     handler = _make_handler(fault_id="general-check", ci_systems=["jenkins"])
     await _insert(session, inspection, handler)
 
-    result = await evaluate(inspection.id, session)
+    result = await evaluate(inspection.id, session, _make_reader())
 
     assert len(result.handlers) == 1
     assert result.handlers[0].fault_id == "general-check"
@@ -70,7 +86,7 @@ async def test_evaluate_single_matching_handler_decision_is_matched(session: Asy
     handler = _make_handler()
     await _insert(session, inspection, handler)
 
-    result = await evaluate(inspection.id, session)
+    result = await evaluate(inspection.id, session, _make_reader())
 
     assert len(result.decisions) == 1
     assert result.decisions[0].result == "matched"
@@ -90,7 +106,7 @@ async def test_evaluate_writes_no_db_rows(session: AsyncSession):
     handler = _make_handler()
     await _insert(session, inspection, handler)
 
-    await evaluate(inspection.id, session)
+    await evaluate(inspection.id, session, _make_reader())
 
     he_count = (await session.execute(text("SELECT COUNT(*) FROM handler_executions"))).scalar()
     jn_count = (await session.execute(text("SELECT COUNT(*) FROM handler_execution_failed_stages"))).scalar()
@@ -103,29 +119,29 @@ async def test_evaluate_writes_no_db_rows(session: AsyncSession):
 # ---------------------------------------------------------------------------
 
 
-async def test_evaluate_wrong_ci_system_is_filtered_level2(session: AsyncSession):
+async def test_evaluate_wrong_ci_system_is_filtered_infrastructure(session: AsyncSession):
     """Handler whose ci_systems does not include the pipeline's CI is filtered at Level 2."""
     inspection = _make_inspection(pipeline_url="https://jenkins.example.com/job/proj/job/main/1/")
     handler = _make_handler(fault_id="ado-only", ci_systems=["azure_devops"])
     await _insert(session, inspection, handler)
 
-    result = await evaluate(inspection.id, session)
+    result = await evaluate(inspection.id, session, _make_reader())
 
     assert result.handlers == []
     assert len(result.decisions) == 1
-    assert result.decisions[0].result == "filtered_level2"
+    assert result.decisions[0].result == "filtered_infrastructure"
 
 
-async def test_evaluate_repo_pattern_mismatch_is_filtered_level2(session: AsyncSession):
+async def test_evaluate_repo_pattern_mismatch_is_filtered_infrastructure(session: AsyncSession):
     """Handler whose repo_patterns do not match the repo URL is filtered at Level 2."""
     inspection = _make_inspection(github_repo_url="https://github.tools.sap/otherorg/otherrepo")
     handler = _make_handler(repo_patterns=["github.tools.sap/myorg/*"])
     await _insert(session, inspection, handler)
 
-    result = await evaluate(inspection.id, session)
+    result = await evaluate(inspection.id, session, _make_reader())
 
     assert result.handlers == []
-    assert result.decisions[0].result == "filtered_level2"
+    assert result.decisions[0].result == "filtered_infrastructure"
 
 
 # ---------------------------------------------------------------------------
@@ -133,7 +149,7 @@ async def test_evaluate_repo_pattern_mismatch_is_filtered_level2(session: AsyncS
 # ---------------------------------------------------------------------------
 
 
-async def test_evaluate_stage_scoped_no_matching_stages_is_filtered_level3(
+async def test_evaluate_stage_scoped_no_matching_stages_is_filtered_log_match(
     session: AsyncSession,
 ):
     """stage_scoped handler with no matching failed stages is filtered at Level 3."""
@@ -153,27 +169,73 @@ async def test_evaluate_stage_scoped_no_matching_stages_is_filtered_level3(
     handler = _make_handler(fault_id="sonar-check", strategy="stage_scoped", spec_json=spec_json)
     await _insert(session, inspection, stage, handler)
 
-    result = await evaluate(inspection.id, session)
+    result = await evaluate(inspection.id, session, _make_reader())
 
     assert result.handlers == []
-    assert result.decisions[0].result == "filtered_level3"
+    assert result.decisions[0].result == "filtered_log_match"
 
 
 # ---------------------------------------------------------------------------
-# pipeline_scoped — always matches
+# pipeline_scoped — always matches (no log_contains)
 # ---------------------------------------------------------------------------
 
 
 async def test_evaluate_pipeline_scoped_matches(session: AsyncSession):
-    """pipeline_scoped handler matches regardless of stage names."""
+    """pipeline_scoped handler with no log_contains matches regardless of stage names."""
     inspection = _make_inspection()
     stage = _make_failed_stage(inspection_id=inspection.id)
     handler = _make_handler(strategy="pipeline_scoped")
     await _insert(session, inspection, stage, handler)
 
-    result = await evaluate(inspection.id, session)
+    result = await evaluate(inspection.id, session, _make_reader())
+
+    assert len(result.handlers) == 1
+
+
+async def test_evaluate_pipeline_scoped_log_contains_match(session: AsyncSession):
+    """pipeline_scoped handler with log_contains is included when the pipeline log matches."""
+    inspection = _make_inspection()
+    spec_json = {
+        "fault_id": "oom-check",
+        "execution": {"type": "agent_task", "task": "analyze", "skills": [], "mcps": []},
+        "applicability": {
+            "failure_match": {
+                "strategy": "pipeline_scoped",
+                "match": [{"log_contains": "OOMKilled"}],
+            },
+        },
+    }
+    handler = _make_handler(fault_id="oom-check", strategy="pipeline_scoped", spec_json=spec_json)
+    await _insert(session, inspection, handler)
+
+    result = await evaluate(inspection.id, session, _make_reader(pipeline_log="container OOMKilled"))
 
     assert len(result.handlers) == 1
+    assert result.handlers[0].fault_id == "oom-check"
+
+
+async def test_evaluate_pipeline_scoped_log_contains_no_match_filtered_log_match(
+    session: AsyncSession,
+):
+    """pipeline_scoped handler whose log_contains does not match the pipeline log is filtered."""
+    inspection = _make_inspection()
+    spec_json = {
+        "fault_id": "oom-check",
+        "execution": {"type": "agent_task", "task": "analyze", "skills": [], "mcps": []},
+        "applicability": {
+            "failure_match": {
+                "strategy": "pipeline_scoped",
+                "match": [{"log_contains": "OOMKilled"}],
+            },
+        },
+    }
+    handler = _make_handler(fault_id="oom-check", strategy="pipeline_scoped", spec_json=spec_json)
+    await _insert(session, inspection, handler)
+
+    result = await evaluate(inspection.id, session, _make_reader(pipeline_log="build failed: timeout"))
+
+    assert result.handlers == []
+    assert result.decisions[0].result == "filtered_log_match"
 
 
 # ---------------------------------------------------------------------------
@@ -195,7 +257,7 @@ async def test_evaluate_specific_handler_wins_over_default(session: AsyncSession
     )
     await _insert(session, inspection, default_handler, specific_handler)
 
-    result = await evaluate(inspection.id, session)
+    result = await evaluate(inspection.id, session, _make_reader())
 
     assert len(result.handlers) == 1
     assert result.handlers[0].fault_id == "general-check"
@@ -212,7 +274,7 @@ async def test_evaluate_two_different_fault_ids_both_selected(session: AsyncSess
     handler_b = _make_handler(cr_name="check-b", fault_id="check-b")
     await _insert(session, inspection, handler_a, handler_b)
 
-    result = await evaluate(inspection.id, session)
+    result = await evaluate(inspection.id, session, _make_reader())
 
     assert len(result.handlers) == 2
     assert _fault_ids(result) == {"check-a", "check-b"}
@@ -241,7 +303,7 @@ async def test_evaluate_handler_dict_structure(session: AsyncSession):
     handler = _make_handler(cr_name="my-handler", fault_id="my-check", spec_json=spec_json)
     await _insert(session, inspection, handler)
 
-    result = await evaluate(inspection.id, session)
+    result = await evaluate(inspection.id, session, _make_reader())
 
     assert len(result.handlers) == 1
     d = result.handlers[0]
@@ -261,4 +323,86 @@ async def test_evaluate_handler_dict_structure(session: AsyncSession):
 async def test_evaluate_unknown_inspection_raises(session: AsyncSession):
     """evaluate raises KeyError when the inspection_id does not exist."""
     with pytest.raises(KeyError, match="not found"):
-        await evaluate(str(uuid.uuid4()), session)
+        await evaluate(str(uuid.uuid4()), session, _make_reader())
+
+
+# ---------------------------------------------------------------------------
+# Log fetching optimisation — logs only fetched when log_contains is present
+# ---------------------------------------------------------------------------
+
+
+async def test_evaluate_stage_name_only_criteria_does_not_fetch_stage_log(session: AsyncSession):
+    """stage_scoped handler with only stage_name (no log_contains) does not fetch any logs."""
+    inspection = _make_inspection()
+    stage = _make_failed_stage(inspection_id=inspection.id, stage_name="sonarqube")
+
+    spec_json = {
+        "fault_id": "sonar-check",
+        "execution": {"type": "agent_task", "task": "analyze", "skills": [], "mcps": []},
+        "applicability": {
+            "failure_match": {
+                "strategy": "stage_scoped",
+                "match": [{"stage_name": "sonarqube*", "log_contains": None}],
+            },
+        },
+    }
+    handler = _make_handler(fault_id="sonar-check", strategy="stage_scoped", spec_json=spec_json)
+    await _insert(session, inspection, stage, handler)
+
+    stream_calls = []
+
+    async def _stream_stage(inspection_id: str, stage_dir: str):
+        stream_calls.append(stage_dir)
+        yield b""
+
+    reader = MagicMock()
+    reader.stream_stage_log = _stream_stage
+    reader.stream_console_log = MagicMock()
+
+    await evaluate(inspection.id, session, reader)
+
+    assert stream_calls == [], "stage log should not be fetched when criteria has no log_contains"
+
+
+# ---------------------------------------------------------------------------
+# Tenacity retries on HdlfUnreachableError
+# ---------------------------------------------------------------------------
+
+
+async def test_evaluate_retries_on_hdlf_unreachable(session: AsyncSession):
+    """Stage log fetch is retried on HdlfUnreachableError and succeeds on second attempt."""
+    from hdlf_server.exceptions import HdlfUnreachableError
+
+    inspection = _make_inspection()
+    stage = _make_failed_stage(inspection_id=inspection.id, stage_name="build")
+
+    spec_json = {
+        "fault_id": "test-check",
+        "execution": {"type": "agent_task", "task": "analyze", "skills": [], "mcps": []},
+        "applicability": {
+            "failure_match": {
+                "strategy": "stage_scoped",
+                "match": [{"log_contains": "ERROR"}],
+            },
+        },
+    }
+    handler = _make_handler(fault_id="test-check", strategy="stage_scoped", spec_json=spec_json)
+    await _insert(session, inspection, stage, handler)
+
+    call_count = 0
+
+    async def _stream_stage(inspection_id: str, stage_dir: str):
+        nonlocal call_count
+        call_count += 1
+        if call_count == 1:
+            raise HdlfUnreachableError("transient")
+        yield b"ERROR: something failed"
+
+    reader = MagicMock()
+    reader.stream_stage_log = _stream_stage
+    reader.stream_console_log = MagicMock()
+
+    result = await evaluate(inspection.id, session, reader)
+
+    assert call_count == 2, "should have retried once"
+    assert result.decisions[0].result == "matched"

```
