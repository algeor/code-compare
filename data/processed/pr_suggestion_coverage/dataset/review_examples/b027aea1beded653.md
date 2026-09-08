# b027aea1beded653

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/40
Suggested label: 100%
File overlap: 1.0
Changed-line overlap: 1.0

## Suggested diff
```diff
--- a/tests/hdlf_server/test_handler_results_router.py
+++ b/tests/hdlf_server/test_handler_results_router.py
@@
+strategy=scope,
```

## Landed PR diff
```diff
diff --git a/.claude/commands/deploy.md b/.claude/commands/deploy.md
index 81d97b81..bb448c47 100644
--- a/.claude/commands/deploy.md
+++ b/.claude/commands/deploy.md
@@ -145,7 +145,7 @@ CLUSTER_ARCH=$(kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes -o jsonpath='{.
 ### 0e. Registry Discovery
 
 If `HAS_KYMA_REGISTRY=true`:
-- Push address: `localhost:5001/$CHART_NAME:latest` (via port-forward to registry service)
+- Push address: `localhost:5001/$CHART_NAME:<IMAGE_TAG>` (via port-forward to registry service)
 - Pull address: `localhost:32137/$CHART_NAME` (NodePort for in-cluster pulls)
 - Credentials: from `dockerregistry-config` secret in `docker-registry` namespace
 
@@ -229,7 +229,7 @@ Categorize all discovered values into:
 
 **Auto-resolved (never ask):**
 - `image.repository` → determined by registry type and chart name
-- `image.tag` → `latest` (or git short SHA if preferred)
+- `image.tag` → timestamp tag generated in Phase 1 (YYYYMMDDHHmmss format)
 - `secret.dockerconfigjson` → extracted from registry secret at deploy time
 - `controller.watchNamespace` → same as target namespace (if controller exists)
 - `apirule.host` → use the default from values.yaml (typically $CHART_NAME). Do NOT append the namespace — the chart template already appends `-{{ .Release.Namespace }}` to produce the final hostname.
@@ -280,6 +280,13 @@ If `.deploy-cache.yaml` is not in `.gitignore`, print a warning:
 
 ## PHASE 1 — Build
 
+### Generate timestamp tag
+
+```bash
+IMAGE_TAG=$(date +%Y%m%d%H%M%S)
+echo "[deploy] Using image tag: $IMAGE_TAG"
+```
+
 ### Determine target platform
 
 ```bash
@@ -295,15 +302,17 @@ fi
 ### Build
 
 ```bash
-LOCAL_TAG="$CHART_NAME-latest:latest"
+LOCAL_TAG="$CHART_NAME:$IMAGE_TAG"
 $CONTAINER_RUNTIME build $PLATFORM_FLAG -t "$LOCAL_TAG" -f "$DOCKERFILE" "$REPO_ROOT"
 ```
 
-On success: `[deploy] Build complete ($CONTAINER_RUNTIME, ${CLUSTER_ARCH:-native})`
+On success: `[deploy] Build complete ($CONTAINER_RUNTIME, ${CLUSTER_ARCH:-native}) — tag: $IMAGE_TAG`
 On failure: print build output and stop.
 
 ## PHASE 2 — Push
 
+**IMPORTANT: Run all of Phase 2 in a SINGLE Bash call.** Shell state (variables like `$PF_PID`, `$PODMAN_PORT`, `$IMAGE_TAG`, `$CHART_NAME`) does not persist between separate Bash invocations. Combine all steps into one compound script, re-declaring any variables from earlier phases that are needed.
+
 ### Strategy: Kyma in-cluster registry
 
 If `registry.type=kyma`:
@@ -327,7 +336,7 @@ PODMAN_USER=$(podman machine inspect --format '{{.SSHConfig.RemoteUsername}}')
 **2c. Tag image**
 
 ```bash
-PUSH_TAG="localhost:5001/$CHART_NAME:latest"
+PUSH_TAG="localhost:5001/$CHART_NAME:$IMAGE_TAG"
 $CONTAINER_RUNTIME tag "$LOCAL_TAG" "$PUSH_TAG"
 ```
 
@@ -401,13 +410,13 @@ ssh -o StrictHostKeyChecking=no \
     -i "$PODMAN_SSH_KEY" \
     -p "$PODMAN_PORT" \
     "$PODMAN_USER@localhost" \
-    "podman push --tls-verify=false localhost:5001/$CHART_NAME:latest"
+    "podman push --tls-verify=false localhost:5001/$CHART_NAME:$IMAGE_TAG"
 ```
 
 If docker (push directly):
 ```bash
 echo "$REG_PASS" | docker login --username "$REG_USER" --password-stdin localhost:5001
-docker push "localhost:5001/$CHART_NAME:latest"
+docker push "localhost:5001/$CHART_NAME:$IMAGE_TAG"
 ```
 
 If push fails with `use of closed network connection`: kill port-forward, restart from 2d, retry once.
@@ -424,7 +433,7 @@ Print: `[deploy] Push complete`
 
 If `registry.type=generic`:
 ```bash
-PUSH_TAG="$REGISTRY_PUSH_ADDRESS/$CHART_NAME:latest"
+PUSH_TAG="$REGISTRY_PUSH_ADDRESS/$CHART_NAME:$IMAGE_TAG"
 $CONTAINER_RUNTIME tag "$LOCAL_TAG" "$PUSH_TAG"
 $CONTAINER_RUNTIME push "$PUSH_TAG"
 ```
@@ -449,7 +458,7 @@ Start with auto-resolved values:
 ```bash
 SET_FLAGS=""
 SET_FLAGS="$SET_FLAGS --set image.repository=$REGISTRY_PULL_ADDRESS/$CHART_NAME"
-SET_FLAGS="$SET_FLAGS --set image.tag=latest"
+SET_FLAGS="$SET_FLAGS --set image.tag=$IMAGE_TAG"
 SET_FLAGS="$SET_FLAGS --set image.pullPolicy=Always"
 ```
 
@@ -500,7 +509,20 @@ if [ "$HAS_KYMA_APIRULE" = "true" ]; then
 fi
 ```
 
-### 3c. Dry-run mode
+### 3c. CRD installation (idempotent)
+
+CRDs are cluster-scoped. Helm's built-in CRD handling (the `crds/` directory) only installs on first `helm install` and **fails if the CRD already exists** (e.g. installed by another release in a different namespace). Apply them via kubectl instead — it's idempotent (creates if missing, updates if changed, no-op if identical).
+
+```bash
+if [ -d "$CHART_PATH/crds" ] && ls "$CHART_PATH/crds/"*.yaml >/dev/null 2>&1; then
+  echo "[deploy] Applying CRDs (idempotent)..."
+  kubectl --kubeconfig "$KUBECONFIG_PATH" apply -f "$CHART_PATH/crds/"
+fi
+```
+
+Then pass `--skip-crds` to helm in 3e below so it never attempts its own CRD install.
+
+### 3d. Dry-run mode
 
 If `PHASE=dry-run`:
 ```bash
@@ -520,7 +542,7 @@ echo "[deploy] Template rendering: OK"
 
 Print any template errors. Do NOT execute.
 
-### 3d. Helm upgrade
+### 3e. Helm upgrade
 
 ```bash
 RELEASE_NAME="${CHART_NAME}"
@@ -528,12 +550,13 @@ helm --kubeconfig "$KUBECONFIG_PATH" \
   upgrade --install "$RELEASE_NAME" \
   "$CHART_PATH" \
   -n "$NAMESPACE" \
+  --skip-crds \
   $SET_FLAGS \
   --timeout 10m \
   --wait
 ```
 
-### 3e. Wait for rollouts
+### 3f. Wait for rollouts
 
 Find all deployments created by this release:
 ```bash
@@ -548,7 +571,7 @@ for DEP in $DEPLOYMENTS; do
 done
 ```
 
-### 3f. Verify health (if external URL available)
+### 3g. Verify health (if external URL available)
 
 If `HAS_KYMA_APIRULE=true` and cache has `cluster.domain`:
 ```bash
@@ -584,6 +607,7 @@ Print: `[deploy] Deploy complete — $EXTERNAL_URL`
 | Push | `connection refused` on port 5001 | Port-forward not running | Kill stale listeners, restart port-forward |
 | Push | `use of closed network connection` | Port-forward dropped mid-upload | Restart port-forward, retry push once |
 | Deploy | Helm template error | `helm upgrade` exits before applying | Run `helm template` to see which `required()` failed |
+| Deploy | CRD already exists | `unable to continue with install: CustomResourceDefinition ... already exists` | CRDs are handled in step 3c via `kubectl apply` (idempotent). Ensure `--skip-crds` is passed to helm |
 | Deploy | Timeout on first deploy | BTP ServiceInstance provisioning (2-3 min) | Increase `--timeout`; check `kubectl get serviceinstance -n $NAMESPACE` |
 | Deploy | `no matches for kind "ServiceInstance"` | Chart enables BTP but cluster has no operator | Set `database.serviceBinding.enabled=false` |
 | Deploy | `no matches for kind "APIRule"` | Chart enables APIRule but no Kyma gateway | Set `apirule.enabled=false` |
@@ -599,7 +623,7 @@ Print: `[deploy] Deploy complete — $EXTERNAL_URL`
 
 - **Never modify the chart or values.yaml** — this skill only reads them
 - **Never delete namespaces** — only creates them
-- **Never force-push or overwrite** — image tags are `latest` (replaced by design)
+- **Never force-push or overwrite** — each build gets a unique timestamp tag
 - **Secrets in output**: mask DB passwords, registry passwords, tokens when printing
 - **Cache file**: warn if not gitignored, but do NOT auto-modify .gitignore
 - **First deploy confirmation**: on first run (no cache), show a dry-run summary and ask for confirmation before executing
@@ -610,4 +634,3 @@ Print: `[deploy] Deploy complete — $EXTERNAL_URL`
 - Does not manage multiple environments in one run (one namespace per invocation)
 - Does not auto-upgrade Helm chart dependencies from remote repos
 - Does not provision infrastructure outside Kubernetes (no Terraform, no BTP cockpit)
-
diff --git a/chart/templates/controller-clusterrole.yaml b/chart/templates/controller-clusterrole.yaml
index 26f4cbe3..c70f4047 100644
--- a/chart/templates/controller-clusterrole.yaml
+++ b/chart/templates/controller-clusterrole.yaml
@@ -2,7 +2,7 @@
 apiVersion: rbac.authorization.k8s.io/v1
 kind: ClusterRole
 metadata:
-  name: {{ include "fl-control-plane.fullname" . }}-controller
+  name: {{ include "fl-control-plane.fullname" . }}-controller-{{ .Release.Namespace }}
   labels:
     {{- include "fl-control-plane.labels" . | nindent 4 }}
     app.kubernetes.io/component: controller
@@ -17,14 +17,14 @@ rules:
 apiVersion: rbac.authorization.k8s.io/v1
 kind: ClusterRoleBinding
 metadata:
-  name: {{ include "fl-control-plane.fullname" . }}-controller
+  name: {{ include "fl-control-plane.fullname" . }}-controller-{{ .Release.Namespace }}
   labels:
     {{- include "fl-control-plane.labels" . | nindent 4 }}
     app.kubernetes.io/component: controller
 roleRef:
   apiGroup: rbac.authorization.k8s.io
   kind: ClusterRole
-  name: {{ include "fl-control-plane.fullname" . }}-controller
+  name: {{ include "fl-control-plane.fullname" . }}-controller-{{ .Release.Namespace }}
 subjects:
   - kind: ServiceAccount
     name: {{ include "fl-control-plane.fullname" . }}-controller
diff --git a/chart/templates/deployment-hdlf-server.yaml b/chart/templates/deployment-hdlf-server.yaml
index d80dd15e..73cf653d 100644
--- a/chart/templates/deployment-hdlf-server.yaml
+++ b/chart/templates/deployment-hdlf-server.yaml
@@ -37,6 +37,31 @@ spec:
           ports:
             - containerPort: 8000
           env:
+            - name: DB_HOST
+              valueFrom:
+                secretKeyRef:
+                  name: {{ required "database.secretName must be set" .Values.database.secretName }}
+                  key: host
+            - name: DB_PORT
+              valueFrom:
+                secretKeyRef:
+                  name: {{ required "database.secretName must be set" .Values.database.secretName }}
+                  key: port
+            - name: DB_USER
+              valueFrom:
+                secretKeyRef:
+                  name: {{ required "database.secretName must be set" .Values.database.secretName }}
+                  key: user
+            - name: DB_PASSWORD
+              valueFrom:
+                secretKeyRef:
+                  name: {{ required "database.secretName must be set" .Values.database.secretName }}
+                  key: password
+            - name: DB_SCHEMA
+              valueFrom:
+                secretKeyRef:
+                  name: {{ required "database.secretName must be set" .Values.database.secretName }}
+                  key: schema
             - name: HDLF_REST_API_HOST
               value: {{ required "hdlfServer.hdlf.restApiHost must be set" .Values.hdlfServer.hdlf.restApiHost | quote }}
             - name: HDLF_CONTAINER_ID
diff --git a/db/migrations/versions/0002_fault_handler_default_description.py b/db/migrations/versions/0002_fault_handler_default_description.py
new file mode 100644
index 00000000..f407b97a
--- /dev/null
+++ b/db/migrations/versions/0002_fault_handler_default_description.py
@@ -0,0 +1,36 @@
+"""fault_handler default_output_description
+
+Revision ID: c3a91b7d0f52
+Revises: 845384c95864
+Create Date: 2026-06-26 00:00:00.000000
+
+Adds the ``default_output_description`` column to ``fault_handlers``.
+Populated by the handler-orchestrator's CR-reconciliation loop from the
+new optional ``spec.description`` field in the FaultHandler CR.  Used by
+the handler-results write endpoint as the fallback value when a lean PUT
+body omits ``output_description``.
+
+The column is nullable; existing rows back-fill to NULL, and handler
+authors are not required to register a default.
+"""
+
+from typing import Sequence, Union
+
+import sqlalchemy as sa
+from alembic import op
+
+# revision identifiers, used by Alembic.
+revision: str = "c3a91b7d0f52"
+down_revision: Union[str, Sequence[str], None] = "845384c95864"
+branch_labels: Union[str, Sequence[str], None] = None
+depends_on: Union[str, Sequence[str], None] = None
+
+
+def upgrade() -> None:
+    with op.batch_alter_table("fault_handlers", schema=None) as batch_op:
+        batch_op.add_column(sa.Column("default_output_description", sa.Text(), nullable=True))
+
+
+def downgrade() -> None:
+    with op.batch_alter_table("fault_handlers", schema=None) as batch_op:
+        batch_op.drop_column("default_output_description")
diff --git a/db/migrations/versions/0002_remove_last_patched_phase.py b/db/migrations/versions/0002_remove_last_patched_phase.py
index 3ff1f4ca..32bb7113 100644
--- a/db/migrations/versions/0002_remove_last_patched_phase.py
+++ b/db/migrations/versions/0002_remove_last_patched_phase.py
@@ -1,39 +1,39 @@
 """remove last_patched_phase, add has_error
 
 Revision ID: a3f7c2d91e04
-Revises: 845384c95864
+Revises: c3a91b7d0f52
 Create Date: 2026-06-17 10:00:00.000000
 
 """
+
 from typing import Sequence, Union
 
-from alembic import op
 import sqlalchemy as sa
-
+from alembic import op
 
 # revision identifiers, used by Alembic.
-revision: str = 'a3f7c2d91e04'
-down_revision: Union[str, None] = '845384c95864'
+revision: str = "a3f7c2d91e04"
+down_revision: Union[str, None] = "c3a91b7d0f52"
 branch_labels: Union[str, Sequence[str], None] = None
 depends_on: Union[str, Sequence[str], None] = None
 
 
 def upgrade() -> None:
-    op.drop_column('fault_handlers', 'last_patched_phase')
+    op.drop_column("fault_handlers", "last_patched_phase")
     op.add_column(
-        'fault_handlers',
-        sa.Column('has_error', sa.Boolean(), nullable=False, server_default=sa.false()),
+        "fault_handlers",
+        sa.Column("has_error", sa.Boolean(), nullable=False, server_default=sa.false()),
     )
-    op.drop_column('controller_status', 'handlers_error')
+    op.drop_column("controller_status", "handlers_error")
 
 
 def downgrade() -> None:
     op.add_column(
-        'controller_status',
-        sa.Column('handlers_error', sa.Integer(), nullable=False, server_default=sa.literal_column('0')),
+        "controller_status",
+        sa.Column("handlers_error", sa.Integer(), nullable=False, server_default=sa.literal_column("0")),
     )
-    op.drop_column('fault_handlers', 'has_error')
+    op.drop_column("fault_handlers", "has_error")
     op.add_column(
-        'fault_handlers',
-        sa.Column('last_patched_phase', sa.String(length=20), nullable=True),
+        "fault_handlers",
+        sa.Column("last_patched_phase", sa.String(length=20), nullable=True),
     )
diff --git a/fl_control_plane/database.py b/fl_control_plane/database.py
index 5f65a26f..a88dcac8 100644
--- a/fl_control_plane/database.py
+++ b/fl_control_plane/database.py
@@ -11,8 +11,8 @@
 """
 
 import uuid
-from contextlib import asynccontextmanager
 from collections.abc import AsyncGenerator
+from contextlib import asynccontextmanager
 from datetime import datetime, timezone
 from typing import Any, Optional
 
@@ -36,9 +36,7 @@
 
 from fl_control_plane.config import settings
 
-engine = create_async_engine(
-    settings.database_url, echo=settings.debug, pool_pre_ping=True
-)
+engine = create_async_engine(settings.database_url, echo=settings.debug, pool_pre_ping=True)
 async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
 
 
@@ -53,6 +51,7 @@ def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any)
         cursor.execute("PRAGMA foreign_keys=ON")
         cursor.close()
 
+
 def hana_set_schema_sql(dialect_name: str, schema: str | None) -> str | None:
     """Return SET SCHEMA SQL for HANA, or None if not applicable."""
     if dialect_name != "hana" or not schema:
@@ -87,7 +86,7 @@ def _utc_now() -> datetime:
 
 
 class Base(DeclarativeBase):
-    pass
+    """SQLAlchemy declarative base for all ORM models in this project."""
 
 
 class Inspection(Base):
@@ -106,9 +105,7 @@ class Inspection(Base):
         ),
     )
 
-    id: Mapped[str] = mapped_column(
-        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
-    )
+    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
     """UUID4 identifier stored as a 36-character string.
 
     Stored as VARCHAR(36) to stay portable to HANA, which has no native UUID
@@ -116,21 +113,15 @@ class Inspection(Base):
     Response`) annotate this as `UUID4` and Pydantic v2 coerces the string
     to/from `uuid.UUID` at the API edge.
     """
-    status: Mapped[str] = mapped_column(
-        String(32), nullable=False, default="ACCEPTED", server_default="ACCEPTED"
-    )
+    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACCEPTED", server_default="ACCEPTED")
     pipeline_url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
-    github_repo_url: Mapped[Optional[str]] = mapped_column(
-        String(2048), nullable=True, index=True
-    )
+    github_repo_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True, index=True)
     repo_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
     commit_id: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
     triggered_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
     path_to_hdlf: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
     error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
-    created_at: Mapped[datetime] = mapped_column(
-        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
-    )
+    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
     updated_at: Mapped[Optional[datetime]] = mapped_column(
         DateTime(timezone=True), nullable=True, index=True, onupdate=_utc_now
     )
@@ -158,9 +149,7 @@ class FaultHandler(Base):
         Index("ix_fault_handlers_fault_id", "fault_id"),
     )
 
-    id: Mapped[str] = mapped_column(
-        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
-    )
+    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
     cr_id: Mapped[str] = mapped_column(String(253), nullable=False)
     cr_name: Mapped[str] = mapped_column(String(253), nullable=False)
     cr_namespace: Mapped[str] = mapped_column(String(253), nullable=False)
@@ -169,24 +158,15 @@ class FaultHandler(Base):
     strategy: Mapped[str] = mapped_column(String(20), nullable=False)
     ci_systems: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
     repo_patterns: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
-    trigger_scope: Mapped[str] = mapped_column(
-        String(20), nullable=False, default="all", server_default="all"
-    )
+    trigger_scope: Mapped[str] = mapped_column(String(20), nullable=False, default="all", server_default="all")
     merge_target_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
     spec_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
+    default_output_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
     resource_version: Mapped[str] = mapped_column(String(253), nullable=False)
-    has_error: Mapped[bool] = mapped_column(
-        Boolean, nullable=False, default=False, server_default=false()
-    )
-    is_active: Mapped[bool] = mapped_column(
-        Boolean, nullable=False, default=True, server_default=true()
-    )
-    registered_at: Mapped[datetime] = mapped_column(
-        DateTime(timezone=True), nullable=False, default=_utc_now
-    )
-    updated_at: Mapped[Optional[datetime]] = mapped_column(
-        DateTime(timezone=True), nullable=True, onupdate=_utc_now
-    )
+    has_error: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
+    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
+    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
+    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=_utc_now)
 
 
 class ControllerStatus(Base):
@@ -197,27 +177,15 @@ class ControllerStatus(Base):
     """
 
     __tablename__ = "controller_status"
-    __table_args__ = (
-        CheckConstraint("id = 1", name="ck_controller_status_single_row"),
-    )
+    __table_args__ = (CheckConstraint("id = 1", name="ck_controller_status_single_row"),)
 
     id: Mapped[int] = mapped_column(Integer, primary_key=True)
-    last_sync_time: Mapped[Optional[datetime]] = mapped_column(
-        DateTime(timezone=True), nullable=True
-    )
+    last_sync_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
     sync_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
-    handlers_active: Mapped[int] = mapped_column(
-        Integer, nullable=False, default=0, server_default="0"
-    )
-    handlers_inactive: Mapped[int] = mapped_column(
-        Integer, nullable=False, default=0, server_default="0"
-    )
-    circuit_breaker_active: Mapped[bool] = mapped_column(
-        Boolean, nullable=False, default=False, server_default=false()
-    )
-    updated_at: Mapped[Optional[datetime]] = mapped_column(
-        DateTime(timezone=True), nullable=True, onupdate=_utc_now
-    )
+    handlers_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
+    handlers_inactive: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
+    circuit_breaker_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
+    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=_utc_now)
 
 
 class HandlerExecution(Base):
@@ -233,9 +201,7 @@ class HandlerExecution(Base):
         Index("ix_handler_executions_status", "status"),
     )
 
-    id: Mapped[str] = mapped_column(
-        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
-    )
+    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
     inspection_id: Mapped[str] = mapped_column(
         String(36),
         ForeignKey(
@@ -260,15 +226,9 @@ class HandlerExecution(Base):
     status: Mapped[str] = mapped_column(String(20), nullable=False)
     status_message: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
     path_to_hdlf: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
-    created_at: Mapped[datetime] = mapped_column(
-        DateTime(timezone=True), nullable=False, default=_utc_now
-    )
-    updated_at: Mapped[Optional[datetime]] = mapped_column(
-        DateTime(timezone=True), nullable=True, onupdate=_utc_now
-    )
-    finished_at: Mapped[Optional[datetime]] = mapped_column(
-        DateTime(timezone=True), nullable=True
-    )
+    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
+    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=_utc_now)
+    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
 
 
 class AuditSecretsUsed(Base):
@@ -282,9 +242,7 @@ class AuditSecretsUsed(Base):
         ),
     )
 
-    id: Mapped[str] = mapped_column(
-        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
-    )
+    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
     execution_id: Mapped[str] = mapped_column(
         String(36),
         ForeignKey(
@@ -309,9 +267,7 @@ class FailedStage(Base):
         Index("ix_failed_stages_stage_created", "stage_name", "created_at"),
     )
 
-    id: Mapped[str] = mapped_column(
-        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
-    )
+    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
     inspection_id: Mapped[str] = mapped_column(
         String(36),
         ForeignKey(
@@ -324,9 +280,7 @@ class FailedStage(Base):
     )
     stage_name: Mapped[str] = mapped_column(String(255), nullable=False)
     error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
-    created_at: Mapped[datetime] = mapped_column(
-        DateTime(timezone=True), nullable=False, default=_utc_now
-    )
+    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
 
 
 class HandlerExecutionFailedStage(Base):
@@ -337,9 +291,7 @@ class HandlerExecutionFailedStage(Base):
     """
 
     __tablename__ = "handler_execution_failed_stages"
-    __table_args__ = (
-        Index("ix_hefs_failed_stage", "failed_stage_id"),
-    )
+    __table_args__ = (Index("ix_hefs_failed_stage", "failed_stage_id"),)
 
     handler_execution_id: Mapped[str] = mapped_column(
         String(36),
@@ -374,9 +326,7 @@ class HandlerAgentTelemetry(Base):
         Index("ix_handler_agent_telemetry_model_created", "model_name", "created_at"),
     )
 
-    id: Mapped[str] = mapped_column(
-        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
-    )
+    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
     execution_id: Mapped[str] = mapped_column(
         String(36),
         ForeignKey(
@@ -387,21 +337,11 @@ class HandlerAgentTelemetry(Base):
         ),
         nullable=False,
     )
-    input_tokens: Mapped[int] = mapped_column(
-        Integer, nullable=False, default=0, server_default="0"
-    )
-    output_tokens: Mapped[int] = mapped_column(
-        Integer, nullable=False, default=0, server_default="0"
-    )
-    total_tokens: Mapped[int] = mapped_column(
-        Integer, nullable=False, default=0, server_default="0"
-    )
+    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
+    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
+    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
     model_name: Mapped[str] = mapped_column(String(100), nullable=False)
-    created_at: Mapped[datetime] = mapped_column(
-        DateTime(timezone=True), nullable=False, default=_utc_now
-    )
-
-
+    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
 
 
 class FinalizerRegistry(Base):
@@ -414,9 +354,7 @@ class FinalizerRegistry(Base):
 
     __tablename__ = "finalizer_registry"
     __table_args__ = (
-        UniqueConstraint(
-            "finalizer_id", "finalizer_version", name="uq_finalizer_registry_id_version"
-        ),
+        UniqueConstraint("finalizer_id", "finalizer_version", name="uq_finalizer_registry_id_version"),
         CheckConstraint(
             "execution_type IN ('agent_task', 'custom_runtime')",
             name="ck_finalizer_registry_exec_type",
@@ -430,9 +368,7 @@ class FinalizerRegistry(Base):
         Index("ix_finalizer_registry_finalizer_id", "finalizer_id"),
     )
 
-    id: Mapped[str] = mapped_column(
-        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
-    )
+    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
     finalizer_id: Mapped[str] = mapped_column(String(255), nullable=False)
     finalizer_version: Mapped[str] = mapped_column(String(63), nullable=False)
     display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
@@ -441,15 +377,9 @@ class FinalizerRegistry(Base):
     prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
     skills_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
     mcps_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
-    is_active: Mapped[bool] = mapped_column(
-        Boolean, nullable=False, default=True, server_default=true()
-    )
-    registered_at: Mapped[datetime] = mapped_column(
-        DateTime(timezone=True), nullable=False, default=_utc_now
-    )
-    updated_at: Mapped[Optional[datetime]] = mapped_column(
-        DateTime(timezone=True), nullable=True, onupdate=_utc_now
-    )
+    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
+    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
+    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=_utc_now)
 
 
 class FinalizerExecution(Base):
@@ -465,9 +395,7 @@ class FinalizerExecution(Base):
         Index("ix_finalizer_execution_registry_id", "finalizer_registry_id"),
     )
 
-    id: Mapped[str] = mapped_column(
-        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
-    )
+    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
     inspection_id: Mapped[str] = mapped_column(
         String(36),
         ForeignKey(
@@ -488,23 +416,13 @@ class FinalizerExecution(Base):
         ),
         nullable=False,
     )
-    is_active: Mapped[bool] = mapped_column(
-        Boolean, nullable=False, default=True, server_default=true()
-    )
-    status: Mapped[str] = mapped_column(
-        String(20), nullable=False, default="planned", server_default="planned"
-    )
+    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
+    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned", server_default="planned")
     status_message: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
     path_to_hdlf: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
-    created_at: Mapped[datetime] = mapped_column(
-        DateTime(timezone=True), nullable=False, default=_utc_now
-    )
-    updated_at: Mapped[Optional[datetime]] = mapped_column(
-        DateTime(timezone=True), nullable=True, onupdate=_utc_now
-    )
-    finished_at: Mapped[Optional[datetime]] = mapped_column(
-        DateTime(timezone=True), nullable=True
-    )
+    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
+    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=_utc_now)
+    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
 
 
 class Feedback(Base):
@@ -517,17 +435,14 @@ class Feedback(Base):
             name="ck_feedback_source",
         ),
         CheckConstraint(
-            "assessment IN ('helpful', 'not_helpful', 'false_positive', "
-            "'correct_fix', 'wrong_fix')",
+            "assessment IN ('helpful', 'not_helpful', 'false_positive', 'correct_fix', 'wrong_fix')",
             name="ck_feedback_assessment",
         ),
         Index("ix_feedback_finalizer_execution", "finalizer_execution_id"),
         Index("ix_feedback_source_created", "source", "created_at"),
     )
 
-    id: Mapped[str] = mapped_column(
-        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
-    )
+    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
     finalizer_execution_id: Mapped[str] = mapped_column(
         String(36),
         ForeignKey(
@@ -541,16 +456,15 @@ class Feedback(Base):
     source: Mapped[str] = mapped_column(String(20), nullable=False)
     assessment: Mapped[str] = mapped_column(String(20), nullable=False)
     comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
-    created_at: Mapped[datetime] = mapped_column(
-        DateTime(timezone=True), nullable=False, default=_utc_now
-    )
+    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
 
 
 async def get_db() -> AsyncGenerator[AsyncSession, None]:
-    """FastAPI dependency that yields a database session."""
+    """Yield a database session for use as a FastAPI dependency."""
     async with async_session() as session:
         yield session
 
+
 @asynccontextmanager
 async def session_scope() -> AsyncGenerator[AsyncSession, None]:
     """Context manager that commits on success, rolls back on exception."""
@@ -576,8 +490,9 @@ async def verify_db_connection() -> None:
 
 async def ensure_tables() -> None:
     """Create all tables if using SQLite (local dev only).
+
     No-op on HANA — production schema is managed by Alembic migrations.
     """
     if engine.dialect.name == "sqlite":
         async with engine.begin() as conn:
-            await conn.run_sync(Base.metadata.create_all)
\ No newline at end of file
+            await conn.run_sync(Base.metadata.create_all)
diff --git a/fl_control_plane/execution_contracts.py b/fl_control_plane/execution_contracts.py
index e781c8e6..7d44ff0c 100644
--- a/fl_control_plane/execution_contracts.py
+++ b/fl_control_plane/execution_contracts.py
@@ -1,4 +1,5 @@
 """Shared contract models between the Handler Orchestrator and Execution Engine."""
+
 from __future__ import annotations
 
 from typing import Literal
@@ -35,10 +36,18 @@ class FaultHandlerSpec(BaseModel):
         fault_id: Logical identifier for the fault this handler addresses. Used as a
             label on the k8s Job. Falls back to metadata.name when absent.
         execution: Execution configuration for the handler job.
+        description: Optional human-readable description of what this handler's
+            output represents.  When set, the CR-reconciliation loop persists
+            this string into ``fault_handlers.default_output_description``.
+            The handler-results write endpoint reads that column as the fallback
+            when a lean PUT body omits ``output_description``.  ``None`` means
+            the author registered no default — handlers wanting a description
+            on their results must send it in the PUT body.
     """
 
     fault_id: str | None = None
     execution: FaultHandlerExecution = FaultHandlerExecution()
+    description: str | None = None
 
 
 class FaultHandlerMetadata(BaseModel):
diff --git a/fl_control_plane/handler_orchestrator/applicability.py b/fl_control_plane/handler_orchestrator/applicability.py
index 59c99c81..3cc63595 100644
--- a/fl_control_plane/handler_orchestrator/applicability.py
+++ b/fl_control_plane/handler_orchestrator/applicability.py
@@ -62,16 +62,11 @@ def filter_level2(handler: FaultHandler, ctx: PipelineContext) -> str | None:
     if repo_patterns and ctx.github_repo_url is not None:
         bare_url = ctx.github_repo_url.removeprefix("https://").removeprefix("http://")
         if not any(fnmatch.fnmatch(bare_url, pat) for pat in repo_patterns):
-            return (
-                f"repo '{ctx.github_repo_url}' matches none of repo_patterns {repo_patterns}"
-            )
+            return f"repo '{ctx.github_repo_url}' matches none of repo_patterns {repo_patterns}"
 
     if handler.merge_target_branch and ctx.pr_target_branch is not None:
         if ctx.pr_target_branch != handler.merge_target_branch:
-            return (
-                f"pr_target_branch '{ctx.pr_target_branch}' != "
-                f"merge_target_branch '{handler.merge_target_branch}'"
-            )
+            return f"pr_target_branch '{ctx.pr_target_branch}' != merge_target_branch '{handler.merge_target_branch}'"
 
     if ctx.is_pr is not None:
         if handler.trigger_scope == "pr_only" and not ctx.is_pr:
@@ -82,9 +77,7 @@ def filter_level2(handler: FaultHandler, ctx: PipelineContext) -> str | None:
     return None
 
 
-def match_stages(
-    criteria: StageMatchCriteria | None, stages: list[FailedStageContext]
-) -> list[str]:
+def match_stages(criteria: StageMatchCriteria | None, stages: list[FailedStageContext]) -> list[str]:
     """Return IDs of stages matching all supplied criteria.
 
     A stage matches when:
@@ -124,13 +117,13 @@ def compute_weight(handler: FaultHandler) -> float:
         weight += 1
     if handler.trigger_scope != "all":
         weight += 1
-    if handler.scope == "stage_scoped":
+    if handler.strategy == "stage_scoped":
         weight += 0.5
     return weight
 
 
 def select_versions(
-    candidates: list[tuple[FaultHandler, list[str]]]
+    candidates: list[tuple[FaultHandler, list[str]]],
 ) -> tuple[list[tuple[FaultHandler, list[str]]], list[tuple[FaultHandler, str]]]:
     """Select one handler per fault_id from the Level 2+3 candidates.
 
diff --git a/fl_control_plane/handler_orchestrator/defaults_resolver.py b/fl_control_plane/handler_orchestrator/defaults_resolver.py
new file mode 100644
index 00000000..70963cf6
--- /dev/null
+++ b/fl_control_plane/handler_orchestrator/defaults_resolver.py
@@ -0,0 +1,145 @@
+"""Resolves handler defaults from the control-plane DB for lean PUT requests.
+
+When a handler result PUT body omits ``output_description`` or ``scope``,
+the write endpoint falls back to the values registered on the
+``FaultHandler`` CR — retrieved via the most recent ``handler_executions``
+row for ``(inspection_id, fault_id)``.  This module owns that query, the
+disambiguation rule (latest execution by ``created_at``), and the
+transient-retry policy.
+
+The disambiguation rule mirrors the orchestrator's own ``select_versions``
+choice: when multiple executions exist for the same ``(inspection_id,
+fault_id)``, the most-recently-created one wins (D10 in design.md).
+"""
+
+from __future__ import annotations
+
+import sqlalchemy.exc
+import structlog
+import tenacity
+from sqlalchemy import select
+from sqlalchemy.ext.asyncio import AsyncSession
+
+from fl_control_plane.database import FaultHandler, HandlerExecution
+from fl_control_plane.inspection_results_repository import Scope
+
+log = structlog.get_logger(__name__)
+
+_RETRY_STOP = tenacity.stop_after_attempt(5)
+_RETRY_WAIT = tenacity.wait_exponential(multiplier=1, max=8)
+
+
+class HandlerExecutionNotFoundError(Exception):
+    """No ``handler_executions`` row exists for ``(inspection_id, fault_id)``.
+
+    Raised by :func:`resolve_handler_defaults` on a lean PUT (body omits
+    ``output_description`` or ``scope``) when the orchestrator has no
+    record of having scheduled this handler against this inspection.
+    Mapped to HTTP 400 by the write router.
+
+    The translation is structural ("FL doesn't know about this
+    execution"), not a policy rejection — a full-body PUT for the same
+    fault still succeeds because it does not query the database.  This
+    keeps the lifecycle/typo-detection debate (D6 in design.md) out of
+    the write path.
+    """
+
+
+async def resolve_handler_defaults(
+    session: AsyncSession,
+    inspection_id: str,
+    fault_id: str,
+) -> tuple[Scope | None, str | None]:
+    """Return ``(scope, default_output_description)`` for the latest execution.
+
+    Reads through ``handler_executions ⋈ fault_handlers`` on
+    ``(inspection_id, fault_id)``, picking the most recent matching
+    execution by ``HandlerExecution.created_at``.  This mirrors the
+    orchestrator's already-made disambiguation choice (D10 in design.md).
+
+    Args:
+        session: An active control-plane ``AsyncSession``.
+        inspection_id: UUID4 of the inspection (already validated).
+        fault_id: Already-validated handler identity.
+
+    Returns:
+        Tuple ``(scope, default_output_description)``.  Either or both
+        may be ``None`` when the joined ``FaultHandler.strategy`` /
+        ``default_output_description`` is NULL.
+
+    Raises:
+        HandlerExecutionNotFoundError: zero matching ``handler_executions``
+            rows.  Caller maps to HTTP 400.
+        sqlalchemy.exc.OperationalError: transient DB failure; use
+            :func:`resolve_handler_defaults_with_retry` to guard.
+        sqlalchemy.exc.InterfaceError: ditto.
+    """
+    stmt = (
+        select(FaultHandler.strategy, FaultHandler.default_output_description)
+        .join(HandlerExecution, HandlerExecution.fault_handler_id == FaultHandler.id)
+        .where(HandlerExecution.inspection_id == inspection_id)
+        .where(HandlerExecution.fault_id == fault_id)
+        .order_by(HandlerExecution.created_at.desc())
+        .limit(1)
+    )
+    result = await session.execute(stmt)
+    row = result.first()
+    if row is None:
+        raise HandlerExecutionNotFoundError(
+            f"No scheduled execution for fault_id={fault_id!r} in inspection {inspection_id!r}; "
+            "send a full body with output_description and scope to bypass DB resolution."
+        )
+    scope_value, description_value = row
+    if scope_value in ("stage_scoped", "pipeline_scoped"):
+        scope_validated: Scope | None = scope_value
+    else:
+        if scope_value is not None:
+            log.warning(
+                "unrecognised scope value in fault_handlers — writing null",
+                fault_id=fault_id,
+                scope=scope_value,
+            )
+        scope_validated = None
+    return scope_validated, description_value
+
+
+async def resolve_handler_defaults_with_retry(
+    session: AsyncSession,
+    inspection_id: str,
+    fault_id: str,
+) -> tuple[Scope | None, str | None]:
+    """Retry transient SQLAlchemy errors on the defaults lookup.
+
+    See D13 in design.md for the rationale: a short retry window catches
+    routine connection blips without bothering the caller, and past the
+    budget the call surfaces 503 — a clear operator signal that the
+    control-plane DB is degraded.
+
+    The retry predicate is narrow on purpose: only ``OperationalError``
+    and ``InterfaceError`` (the two transient SQLAlchemy categories) are
+    retried.  ``ProgrammingError``, ``IntegrityError``, and the rest
+    indicate a server-side bug and propagate unwrapped to the translator.
+
+    After each transient error, the session is explicitly rolled back so
+    its internal transaction state returns to ACTIVE before the next
+    attempt.  Without the rollback, SQLAlchemy 2.x marks the session as
+    DEACTIVE after the first ``OperationalError`` and subsequent
+    ``execute()`` calls raise ``InvalidRequestError`` — a non-transient
+    error that escapes the retry predicate and produces HTTP 500 instead
+    of the intended HTTP 503.
+    """
+    async for attempt in tenacity.AsyncRetrying(
+        retry=tenacity.retry_if_exception_type((sqlalchemy.exc.OperationalError, sqlalchemy.exc.InterfaceError)),
+        stop=_RETRY_STOP,
+        wait=_RETRY_WAIT,
+        reraise=False,
+    ):
+        with attempt:
+            try:
+                return await resolve_handler_defaults(session, inspection_id, fault_id)
+            except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.InterfaceError):
+                await session.rollback()
+                raise
+    # Unreachable: AsyncRetrying with reraise=False raises RetryError when
+    # the budget is exhausted.  The type checker still needs a fallback.
+    raise RuntimeError("AsyncRetrying exhausted without raising — unreachable")
diff --git a/fl_control_plane/handler_orchestrator/orchestrator.py b/fl_control_plane/handler_orchestrator/orchestrator.py
index 85b35555..1d0f6ea7 100644
--- a/fl_control_plane/handler_orchestrator/orchestrator.py
+++ b/fl_control_plane/handler_orchestrator/orchestrator.py
@@ -41,16 +41,12 @@
 
 async def _load_pipeline_context(inspection_id: str, db: AsyncSession) -> PipelineContext:
     """Load Inspection and FailedStage rows and assemble a PipelineContext."""
-    inspection_result = await db.execute(
-        select(Inspection).where(Inspection.id == inspection_id)
-    )
+    inspection_result = await db.execute(select(Inspection).where(Inspection.id == inspection_id))
     inspection = inspection_result.scalar_one_or_none()
     if inspection is None:
         raise KeyError(f"Inspection '{inspection_id}' not found")
 
-    stages_result = await db.execute(
-        select(FailedStage).where(FailedStage.inspection_id == inspection_id)
-    )
+    stages_result = await db.execute(select(FailedStage).where(FailedStage.inspection_id == inspection_id))
     failed_stages = [
         FailedStageContext(
             stage_id=stage.id,
@@ -74,9 +70,7 @@ async def _load_pipeline_context(inspection_id: str, db: AsyncSession) -> Pipeli
 
 async def _load_active_handlers(db: AsyncSession) -> list[FaultHandler]:
     """Load all active FaultHandler rows from the DB."""
-    result = await db.execute(
-        select(FaultHandler).where(FaultHandler.is_active.is_(True))
-    )
+    result = await db.execute(select(FaultHandler).where(FaultHandler.is_active.is_(True)))
     return list(result.scalars().all())
 
 
@@ -91,12 +85,12 @@ def _parse_spec(handler: FaultHandler) -> ParsedHandlerSpec | None:
     try:
         raw = json.loads(handler.spec_json)
         spec = ParsedHandlerSpec.model_validate(raw)
-        # DB scope column is authoritative; keep failure_match strategy in sync
-        if spec.failure_match.strategy != handler.scope:
+        # DB strategy column is authoritative; keep failure_match strategy in sync
+        if spec.failure_match.strategy != handler.strategy:
             spec = spec.model_copy(
                 update={
                     "failure_match": ParsedFailureMatch(
-                        strategy=handler.scope,  # type: ignore[arg-type]
+                        strategy=handler.strategy,  # type: ignore[arg-type]
                         match=spec.failure_match.match,
                     )
                 }
@@ -190,13 +184,15 @@ async def evaluate(inspection_id: str, db: AsyncSession) -> OrchestrationResult:
     for handler in handlers:
         spec = _parse_spec(handler)
         if spec is None:
-            decisions.append(ApplicabilityDecision(
-                handler_db_id=handler.id,
-                fault_id=handler.fault_id,
-                handler_name=handler.cr_name,
-                result="filtered_level2",
-                reason="spec_json missing or unparseable",
-            ))
+            decisions.append(
+                ApplicabilityDecision(
+                    handler_db_id=handler.id,
+                    fault_id=handler.fault_id,
+                    handler_name=handler.cr_name,
+                    result="filtered_level2",
+                    reason="spec_json missing or unparseable",
+                )
+            )
             continue
 
         matched_stage_ids, rejection = _evaluate_handler(handler, spec, ctx)
@@ -209,13 +205,15 @@ async def evaluate(inspection_id: str, db: AsyncSession) -> OrchestrationResult:
     selected_pairs, discarded = select_versions([(h, ids) for h, _, ids in candidates])
 
     for loser, reason in discarded:
-        decisions.append(ApplicabilityDecision(
-            handler_db_id=loser.id,
-            fault_id=loser.fault_id,
-            handler_name=loser.cr_name,
-            result="selected_out",
-            reason=reason,
-        ))
+        decisions.append(
+            ApplicabilityDecision(
+                handler_db_id=loser.id,
+                fault_id=loser.fault_id,
+                handler_name=loser.cr_name,
+                result="selected_out",
+                reason=reason,
+            )
+        )
 
     spec_by_handler_id = {h.id: spec for h, spec, _ in candidates}
 
@@ -223,14 +221,16 @@ async def evaluate(inspection_id: str, db: AsyncSession) -> OrchestrationResult:
     for handler, matched_stage_ids in selected_pairs:
         spec = spec_by_handler_id[handler.id]
         selected_handlers.append(_build_handler_cr(handler, spec))
-        decisions.append(ApplicabilityDecision(
-            handler_db_id=handler.id,
-            fault_id=handler.fault_id,
-            handler_name=handler.cr_name,
-            result="matched",
-            reason="passed all applicability levels",
-            matched_stage_ids=matched_stage_ids,
-        ))
+        decisions.append(
+            ApplicabilityDecision(
+                handler_db_id=handler.id,
+                fault_id=handler.fault_id,
+                handler_name=handler.cr_name,
+                result="matched",
+                reason="passed all applicability levels",
+                matched_stage_ids=matched_stage_ids,
+            )
+        )
         logger.info(
             "handler_matched",
             extra={"inspection_id": inspection_id, "fault_id": handler.fault_id, "handler": handler.cr_name},
@@ -238,7 +238,11 @@ async def evaluate(inspection_id: str, db: AsyncSession) -> OrchestrationResult:
 
     logger.info(
         "orchestration_complete",
-        extra={"inspection_id": inspection_id, "handlers_evaluated": len(handlers), "handlers_matched": len(selected_handlers)},
+        extra={
+            "inspection_id": inspection_id,
+            "handlers_evaluated": len(handlers),
+            "handlers_matched": len(selected_handlers),
+        },
     )
 
-    return OrchestrationResult(handlers=selected_handlers, decisions=decisions)
\ No newline at end of file
+    return OrchestrationResult(handlers=selected_handlers, decisions=decisions)
diff --git a/fl_control_plane/handler_orchestrator/seed.py b/fl_control_plane/handler_orchestrator/seed.py
index 8aff1d4d..1ed4d17c 100644
--- a/fl_control_plane/handler_orchestrator/seed.py
+++ b/fl_control_plane/handler_orchestrator/seed.py
@@ -111,7 +111,7 @@ def _utc_now() -> datetime:
     },
 }
 
-_SEED_HANDLERS: list[dict] = [
+_SEED_HANDLERS: list[dict[str, object]] = [
     {
         "cr_name": "hadolint-analysis",
         "cr_namespace": "fl-system",
@@ -123,6 +123,7 @@ def _utc_now() -> datetime:
         "trigger_scope": "all",
         "merge_target_branch": None,
         "spec_json": json.dumps(_HADOLINT_SPEC),
+        "default_output_description": "Hadolint Dockerfile lint analysis completed.",
         "resource_version": "seed-v1",
     },
     {
@@ -136,6 +137,7 @@ def _utc_now() -> datetime:
         "trigger_scope": "all",
         "merge_target_branch": None,
         "spec_json": json.dumps(_LANDSCAPE_ADO_SPEC),
+        "default_output_description": "Landscape ADO pipeline failure analysis completed.",
         "resource_version": "seed-v1",
     },
     {
@@ -149,6 +151,7 @@ def _utc_now() -> datetime:
         "trigger_scope": "all",
         "merge_target_branch": None,
         "spec_json": json.dumps(_JENKINS_BOUNDED_SPEC),
+        "default_output_description": "Jenkins pipeline failure analysis completed.",
         "resource_version": "seed-v1",
     },
 ]
@@ -160,9 +163,7 @@ async def seed_fault_handlers(db: AsyncSession) -> None:
     Idempotent: skips rows whose cr_name already exists in the table.
     """
     for definition in _SEED_HANDLERS:
-        existing = await db.execute(
-            select(FaultHandler).where(FaultHandler.cr_name == definition["cr_name"])
-        )
+        existing = await db.execute(select(FaultHandler).where(FaultHandler.cr_name == definition["cr_name"]))
         if existing.scalar_one_or_none() is not None:
             continue
 
@@ -173,12 +174,13 @@ async def seed_fault_handlers(db: AsyncSession) -> None:
             cr_namespace=definition["cr_namespace"],
             fault_id=definition["fault_id"],
             execution_type=definition["execution_type"],
-            scope=definition["scope"],
+            strategy=definition["scope"],
             ci_systems=definition["ci_systems"],
             repo_patterns=definition["repo_patterns"],
             trigger_scope=definition["trigger_scope"],
             merge_target_branch=definition["merge_target_branch"],
             spec_json=definition["spec_json"],
+            default_output_description=definition.get("default_output_description"),
             resource_version=definition["resource_version"],
             is_active=True,
             registered_at=_utc_now(),
diff --git a/fl_control_plane/inspection_results_repository/__init__.py b/fl_control_plane/inspection_results_repository/__init__.py
index 0b5b4ed8..9bb7c17d 100644
--- a/fl_control_plane/inspection_results_repository/__init__.py
+++ b/fl_control_plane/inspection_results_repository/__init__.py
@@ -8,8 +8,12 @@
     InspectionResultsError,
     InspectionResultsRepository,
     InspectionResultsTransientError,
+    InspectionResultsValidationError,
+    Scope,
     SuggestedCodeChanges,
     make_inspection_results_repository,
+    make_inspection_results_repository_from_client,
+    validate_fault_id,
 )
 
 __all__ = [
@@ -20,6 +24,10 @@
     "InspectionResultsError",
     "InspectionResultsRepository",
     "InspectionResultsTransientError",
+    "InspectionResultsValidationError",
+    "Scope",
     "SuggestedCodeChanges",
     "make_inspection_results_repository",
+    "make_inspection_results_repository_from_client",
+    "validate_fault_id",
 ]
diff --git a/fl_control_plane/inspection_results_repository/inspection_results_repository.py b/fl_control_plane/inspection_results_repository/inspection_results_repository.py
index 1b33747e..ee73fa4c 100644
--- a/fl_control_plane/inspection_results_repository/inspection_results_repository.py
+++ b/fl_control_plane/inspection_results_repository/inspection_results_repository.py
@@ -21,8 +21,10 @@
     InspectionResultsError                     — base of the exception hierarchy
         InspectionResultsConfigurationError    — non-retryable misconfiguration
         InspectionResultsTransientError        — retryable storage failure
+        InspectionResultsValidationError       — caller-supplied input rejected
         HandlerResultNotFoundError             — handler or diff not found
-    make_inspection_results_repository()       — factory returning the configured backend
+    make_inspection_results_repository()              — factory that opens its own HdlfClient
+    make_inspection_results_repository_from_client()  — factory that reuses a pre-built HdlfClient
 
 Backends must wrap their native exceptions in the three error types above so
 the MCP layer never has to know which storage is in use.
@@ -37,9 +39,10 @@
 from pydantic import BaseModel
 
 if TYPE_CHECKING:
-    from fl_shared.hdlf_client import HdlfConnectionParams
+    from fl_shared.hdlf_client import HdlfClient, HdlfConnectionParams
 
 _SCOPE = Literal["stage_scoped", "pipeline_scoped"]
+Scope = _SCOPE
 
 
 # ── Exceptions ──────────────────────────────────────────────────────────────
@@ -82,6 +85,57 @@ class HandlerResultNotFoundError(InspectionResultsError):
     """
 
 
+class InspectionResultsValidationError(InspectionResultsError):
+    """A caller-supplied argument violates the repository's input contract.
+
+    Raised by write methods (today only ``write_handler_result``) when an
+    identifier such as ``fault_id`` would be unsafe to splice into a
+    storage path — empty string, ``..`` segment, path separator, or NUL
+    byte.  The check is intentionally storage-agnostic and lives on every
+    backend so a future MCP/SDK caller cannot bypass the perimeter by
+    holding a repository reference directly.
+
+    Maps to HTTP 400 at the router translator.
+    """
+
+
+# ── Validation helpers ──────────────────────────────────────────────────────
+
+
+def validate_fault_id(fault_id: str) -> None:
+    r"""Reject fault_ids that could escape the per-handler storage subtree.
+
+    The denylist is deliberately security-focused rather than aesthetic:
+    real handler names span an open vocabulary, so an allowlist here would
+    be brittle.  Each rejected character has a concrete failure mode if
+    it reaches path construction:
+
+    * empty string — collapses ``<base>/handler_results/<fault_id>/...``
+      to ``<base>/handler_results//...`` and writes into the parent.
+    * ``..``       — classic traversal; one segment up escapes the
+      handler subtree entirely.
+    * ``/``        — splits one identifier into multiple path segments,
+      letting the caller write anywhere under ``handler_results/``.
+    * ``\\``       — DOS-style separator some C-level consumers normalise
+      to ``/`` after we've validated.
+    * ``\\x00``    — truncates the path at the NUL byte in C consumers,
+      bypassing every suffix in the constructed path.
+
+    This is defence in depth: the HTTP router applies a stricter
+    allowlist (``^[A-Za-z0-9._-]+$``) for perimeter requests, but every
+    backend must still validate so an in-process caller cannot smuggle a
+    bad value past the router.
+
+    Raises:
+        InspectionResultsValidationError: ``fault_id`` is empty or
+            contains ``..``, ``/``, ``\\``, or ``\\x00``.
+    """
+    if not fault_id:
+        raise InspectionResultsValidationError("fault_id must not be empty")
+    if fault_id == ".." or "/" in fault_id or "\\" in fault_id or "\x00" in fault_id:
+        raise InspectionResultsValidationError(f"fault_id contains a rejected character or segment: {fault_id!r}")
+
+
 # ── Data model ──────────────────────────────────────────────────────────────
 
 
@@ -96,19 +150,26 @@ class InspectionResultEntry(BaseModel):
     Attributes:
         fault_id:           Stable handler identity (e.g. "sonarqube-analysis").
         scope:              Whether the handler targeted a specific stage or the
-                            whole pipeline.
+                            whole pipeline.  ``None`` when neither the writer's
+                            body nor the orchestrator-derived default supplied a
+                            value at write time — recorded as JSON ``null`` in
+                            ``handler_metadata.json`` and parsed back as ``None``.
         addressed_stages:   Stage names the handler addressed.  None when scope is
                             "pipeline_scoped".
         output_description: Human-readable summary of what the handler did.
+                            ``None`` round-trips a write that supplied neither a
+                            body description nor an orchestrator default — the
+                            on-disk ``result_description.md`` is zero bytes in
+                            that case.
         output_json:        Parsed structured output payload.
         has_code_changes:   True when a diff/patch was produced; gate calls to
                             read_code_changes on this flag.
     """
 
     fault_id: str
-    scope: _SCOPE
+    scope: _SCOPE | None
     addressed_stages: list[str] | None
-    output_description: str
+    output_description: str | None
     output_json: dict[str, Any]
     has_code_changes: bool
 
@@ -195,23 +256,44 @@ async def write_handler_result(  # pylint: disable=too-many-arguments
         inspection_id: str,
         fault_id: str,
         result_json: dict[str, Any],
-        output_description: str,
-        scope: _SCOPE,
+        output_description: str | None,
+        scope: _SCOPE | None,
         addressed_stages: list[str] | None,
         code_changes: str | None = None,
     ) -> None:
         """Persist one handler's output.
 
+        Concrete backends MUST validate ``fault_id`` via
+        :func:`validate_fault_id` before constructing any storage path
+        or initiating I/O.
+
+        Semantics:
+
+        * ``output_description=None`` writes a zero-byte
+          ``result_description.md`` (no description registered).
+        * ``scope=None`` writes JSON ``null`` for ``scope`` in
+          ``handler_metadata.json`` (no scope registered).
+        * ``code_changes`` follows strict-PUT semantics: when ``None``,
+          the backend MUST guarantee that any pre-existing diff for the
+          same ``fault_id`` is removed.  A repeated PUT with the same
+          body is byte-level idempotent.
+
         Args:
             inspection_id:      UUID of the inspection.
-            fault_id:           Stable handler identity.
+            fault_id:           Stable handler identity.  Must pass
+                                ``validate_fault_id``.
             result_json:        Structured output payload.
-            output_description: Human-readable description.
-            scope:              "stage_scoped" or "pipeline_scoped".
-            addressed_stages:   Stage names addressed; None when pipeline_scoped.
-            code_changes:       Raw diff/patch; None when no changes were produced.
+            output_description: Human-readable description, or ``None``.
+            scope:              "stage_scoped", "pipeline_scoped", or
+                                ``None`` when no default was registered.
+            addressed_stages:   Stage names addressed; ``None`` when
+                                pipeline_scoped or unknown.
+            code_changes:       Raw diff/patch; ``None`` removes any
+                                previously stored diff.
 
         Raises:
+            InspectionResultsValidationError:    ``fault_id`` rejected by the
+                                                 perimeter-independent denylist.
             InspectionResultsConfigurationError: backend misconfigured.
             InspectionResultsTransientError:     transient storage failure.
         """
@@ -284,8 +366,12 @@ async def list_gate_results(self, inspection_id: str) -> list[GateResultEntry]:
 def make_inspection_results_repository(params: "HdlfConnectionParams") -> InspectionResultsRepository:
     """Build an HDLF-backed inspection-results repository from connection params.
 
-    The factory exists so the MCP layer never imports a concrete backend directly
-    and a different store (DB, S3, …) can be swapped in by editing this one place.
+    This factory opens its own ``HdlfClient`` and is the right entry point for
+    short-lived call sites that need an isolated session — MCP tool handlers,
+    Temporal activities, ad-hoc scripts.  For the long-lived ``hdlf_server``
+    process, prefer :func:`make_inspection_results_repository_from_client`,
+    which reuses the lifespan-managed client (one connection pool, one mTLS
+    handshake).
 
     Args:
         params: HDLF connection parameters produced by
@@ -315,3 +401,36 @@ def make_inspection_results_repository(params: "HdlfConnectionParams") -> Inspec
     except HdlfConfigurationError as exc:
         raise InspectionResultsConfigurationError(str(exc)) from exc
     return HdlfInspectionResultsRepository(client)
+
+
+def make_inspection_results_repository_from_client(
+    hdlf_client: "HdlfClient",
+) -> InspectionResultsRepository:
+    """Build an HDLF-backed inspection-results repository over a pre-built client.
+
+    Sibling of :func:`make_inspection_results_repository`.  The two factories
+    differ only in how they obtain the underlying ``HdlfClient``:
+
+    * :func:`make_inspection_results_repository` — constructs the client from
+      connection parameters, paying one mTLS handshake and opening a new
+      connection pool.  Right for short-lived callers (MCP tools, scripts).
+    * :func:`make_inspection_results_repository_from_client` — reuses a client
+      already opened by the caller (typically a FastAPI lifespan).  Right for
+      long-lived processes where doubling the connection pool would double
+      the handshake cost on every request.
+
+    Keeping ``hdlf_server`` on this entry point preserves the factory
+    abstraction — the server never imports the concrete backend class
+    directly, so a future swap of storage technology stays a one-file change.
+
+    Args:
+        hdlf_client: An already-constructed ``HdlfClient``.  The caller owns
+            its lifecycle; the returned repository's async context manager
+            enters and exits the supplied client.
+    """
+    # Lazy import — same rationale as the sibling factory above.
+    from fl_control_plane.inspection_results_repository.inspection_results_repository_hdlf import (  # pylint: disable=import-outside-toplevel
+        HdlfInspectionResultsRepository,
+    )
+
+    return HdlfInspectionResultsRepository(hdlf_client)
diff --git a/fl_control_plane/inspection_results_repository/inspection_results_repository_hdlf.py b/fl_control_plane/inspection_results_repository/inspection_results_repository_hdlf.py
index 56371715..4ef8747f 100644
--- a/fl_control_plane/inspection_results_repository/inspection_results_repository_hdlf.py
+++ b/fl_control_plane/inspection_results_repository/inspection_results_repository_hdlf.py
@@ -33,8 +33,11 @@
     InspectionResultsRepository,
     InspectionResultsTransientError,
     SuggestedCodeChanges,
+    validate_fault_id,
+)
+from fl_control_plane.inspection_results_repository.inspection_results_repository import (
+    _SCOPE,
 )
-from fl_control_plane.inspection_results_repository.inspection_results_repository import _SCOPE
 from fl_shared.hdlf_client import HdlfClient
 
 log = structlog.get_logger(__name__)
@@ -63,6 +66,7 @@ async def __aexit__(self, *args: object) -> None:
         await self._client.__aexit__(*args)
 
     def _handler_base(self, inspection_id: str, fault_id: str) -> str:
+        validate_fault_id(fault_id)
         return f"{inspection_id}/handler_results/{fault_id}"
 
     async def write_handler_result(  # pylint: disable=too-many-arguments
@@ -71,8 +75,8 @@ async def write_handler_result(  # pylint: disable=too-many-arguments
         inspection_id: str,
         fault_id: str,
         result_json: dict[str, Any],
-        output_description: str,
-        scope: _SCOPE,
+        output_description: str | None,
+        scope: _SCOPE | None,
         addressed_stages: list[str] | None,
         code_changes: str | None = None,
     ) -> None:
@@ -82,35 +86,49 @@ async def write_handler_result(  # pylint: disable=too-many-arguments
         """
         base = self._handler_base(inspection_id, fault_id)
         log.info(
-            "inspection_results_repository[hdlf]: writing result",
+            "writing result",
             fault_id=fault_id,
             inspection_id=inspection_id,
         )
 
         try:
             result_payload = json.dumps(result_json, indent=2, ensure_ascii=False).encode()
-            await self._client.put_object_atomic(f"{base}/result.json", result_payload)
 
-            await self._client.put_object_atomic(
-                f"{base}/result_description.md",
-                output_description.encode(),
-            )
+            # None → zero-byte file.  Read side parses an empty body back to
+            # None (see _read_text_or_empty + list_handler_results) so the
+            # write/read contract stays symmetric.
+            description_bytes = output_description.encode() if output_description is not None else b""
 
+            # scope=None is encoded as JSON null; json.dumps handles this
+            # natively, so the only change from the str path is the type.
             metadata = {"scope": scope, "addressed_stages": addressed_stages}
             metadata_payload = json.dumps(metadata, indent=2, ensure_ascii=False).encode()
-            await self._client.put_object_atomic(f"{base}/handler_metadata.json", metadata_payload)
+
+            await asyncio.gather(
+                self._client.put_object_atomic(f"{base}/result.json", result_payload),
+                self._client.put_object_atomic(f"{base}/result_description.md", description_bytes),
+                self._client.put_object_atomic(f"{base}/handler_metadata.json", metadata_payload),
+            )
 
             if code_changes is not None:
                 await self._client.put_object_atomic(
                     f"{base}/code_changes.diff",
                     code_changes.encode(),
                 )
+            else:
+                # Strict-PUT: the persisted resource state equals exactly the
+                # last PUT body.  Without this, a retry with a smaller body
+                # would silently leave a stale diff on disk — the kind of bug
+                # that's awful to debug.  delete_object already treats 404 as
+                # success at the HdlfClient layer, so no prior-existence
+                # probe is needed.
+                await self._client.delete_object(f"{base}/code_changes.diff")
         except IOError as exc:
             raise InspectionResultsTransientError(f"HDLF write failed: {exc}") from exc
         except RuntimeError as exc:
             raise InspectionResultsConfigurationError(str(exc)) from exc
 
-        log.info("inspection_results_repository[hdlf]: done", fault_id=fault_id, inspection_id=inspection_id)
+        log.info("done", fault_id=fault_id, inspection_id=inspection_id)
 
     async def list_handler_results(  # pylint: disable=too-many-locals
         self, inspection_id: str
@@ -170,7 +188,7 @@ async def list_handler_results(  # pylint: disable=too-many-locals
                 # fails we promote it to a transient error rather than lying
                 # to the caller with an empty list.
                 log.warning(
-                    "inspection_results_repository[hdlf]: transient error reading fault — skipping",
+                    "transient error reading fault — skipping",
                     fault_id=fault_id,
                     inspection_id=inspection_id,
                     error=str(outcome),
@@ -182,11 +200,11 @@ async def list_handler_results(  # pylint: disable=too-many-locals
             if outcome is not None:
                 results.append(outcome)
 
-        if observed_faults > 0 and per_fault_failures == observed_faults:
-            # All handler folders raised transient errors — surfacing this as
-            # success would silently drop every result.
+        if per_fault_failures > 0 and not results:
+            # At least one handler had a transient I/O error and nothing
+            # succeeded — returning [] would hide real storage failures.
             raise InspectionResultsTransientError(
-                f"All {observed_faults} handler result(s) failed to read due to transient errors"
+                f"{per_fault_failures} of {observed_faults} handler result(s) failed to read due to transient errors"
             )
 
         return results
@@ -204,7 +222,7 @@ async def _read_one_fault(self, base: str, fault_id: str, inspection_id: str) ->
             result_bytes = await self._client.get_object(result_path)
         except FileNotFoundError:
             log.debug(
-                "inspection_results_repository[hdlf]: no result.json for fault — skipping",
+                "no result.json for fault — skipping",
                 fault_id=fault_id,
                 inspection_id=inspection_id,
             )
@@ -216,7 +234,7 @@ async def _read_one_fault(self, base: str, fault_id: str, inspection_id: str) ->
             output_json: dict[str, Any] = json.loads(result_bytes)
         except (json.JSONDecodeError, ValueError) as exc:
             log.warning(
-                "inspection_results_repository[hdlf]: invalid result.json for fault — skipping",
+                "invalid result.json for fault — skipping",
                 fault_id=fault_id,
                 inspection_id=inspection_id,
                 error=str(exc),
@@ -228,7 +246,28 @@ async def _read_one_fault(self, base: str, fault_id: str, inspection_id: str) ->
             self._read_json_or_default(f"{base}/handler_metadata.json", {}),
             self._exists_or_raise(f"{base}/code_changes.diff"),
         )
-        scope: _SCOPE = metadata_raw.get("scope", "pipeline_scoped")
+        # An absent or zero-byte description means "no description registered".
+        # The write side stores zero bytes for ``output_description=None``;
+        # round-tripping that here as ``None`` keeps write/read symmetric.
+        description_or_none: str | None = description if description else None
+
+        # ``scope`` may legitimately be missing (legacy data) or JSON null
+        # (current writer when no default was registered).  Treat both as
+        # ``None``; only an unrecognised literal indicates corruption.
+        scope_raw = metadata_raw.get("scope", None)
+        scope: _SCOPE | None
+        if scope_raw is None:
+            scope = None
+        elif scope_raw in ("stage_scoped", "pipeline_scoped"):
+            scope = scope_raw
+        else:
+            log.warning(
+                "unrecognised scope value in handler_metadata.json — treating as None",
+                fault_id=fault_id,
+                inspection_id=inspection_id,
+                scope=scope_raw,
+            )
+            scope = None
         addressed_stages: list[str] | None = metadata_raw.get("addressed_stages")
 
         try:
@@ -236,13 +275,13 @@ async def _read_one_fault(self, base: str, fault_id: str, inspection_id: str) ->
                 fault_id=fault_id,
                 scope=scope,
                 addressed_stages=addressed_stages,
-                output_description=description,
+                output_description=description_or_none,
                 output_json=output_json,
                 has_code_changes=has_code_changes,
             )
         except ValidationError as exc:
             log.warning(
-                "inspection_results_repository[hdlf]: invalid handler_metadata.json for fault — skipping",
+                "invalid handler_metadata.json for fault — skipping",
                 fault_id=fault_id,
                 inspection_id=inspection_id,
                 error=str(exc),
@@ -308,7 +347,7 @@ async def list_gate_results(self, inspection_id: str) -> list[GateResultEntry]:
                 description_text = description_bytes.decode()
             except FileNotFoundError:
                 log.warning(
-                    "inspection_results_repository[hdlf]: could not read gate description: file not found",
+                    "could not read gate description: file not found",
                     file_path=file_path,
                     inspection_id=inspection_id,
                 )
@@ -328,7 +367,7 @@ async def list_gate_results(self, inspection_id: str) -> list[GateResultEntry]:
                 result_obj = {}
             except json.JSONDecodeError as exc:
                 log.warning(
-                    "inspection_results_repository[hdlf]: could not parse gate json",
+                    "could not parse gate json",
                     json_path=json_path,
                     inspection_id=inspection_id,
                     error=str(exc),
@@ -336,7 +375,7 @@ async def list_gate_results(self, inspection_id: str) -> list[GateResultEntry]:
                 result_obj = {}
             except IOError as exc:
                 log.warning(
-                    "inspection_results_repository[hdlf]: transient error reading gate json — using empty result",
+                    "transient error reading gate json — using empty result",
                     json_path=json_path,
                     inspection_id=inspection_id,
                     error=str(exc),
@@ -364,6 +403,8 @@ async def _read_text_or_empty(self, path: str) -> str:
             raise InspectionResultsTransientError(f"{path} is not valid UTF-8: {exc}") from exc
         except IOError as exc:
             raise InspectionResultsTransientError(f"Reading {path} failed: {exc}") from exc
+        except RuntimeError as exc:
+            raise InspectionResultsConfigurationError(str(exc)) from exc
 
     async def _read_json_or_default(self, path: str, default: dict[str, Any]) -> dict[str, Any]:
         """Read a JSON file; return default when absent or malformed. Transient I/O propagates."""
@@ -373,6 +414,8 @@ async def _read_json_or_default(self, path: str, default: dict[str, Any]) -> dic
             return default
         except IOError as exc:
             raise InspectionResultsTransientError(f"Reading {path} failed: {exc}") from exc
+        except RuntimeError as exc:
+            raise InspectionResultsConfigurationError(str(exc)) from exc
 
         try:
             parsed = json.loads(data)
@@ -386,3 +429,5 @@ async def _exists_or_raise(self, path: str) -> bool:
             return await self._client.exists(path)
         except IOError as exc:
             raise InspectionResultsTransientError(f"Could not check for existence of {path}: {exc}") from exc
+        except RuntimeError as exc:
+            raise InspectionResultsConfigurationError(str(exc)) from exc
diff --git a/fl_shared/hdlf_client/client.py b/fl_shared/hdlf_client/client.py
index 223bee98..751df951 100644
--- a/fl_shared/hdlf_client/client.py
+++ b/fl_shared/hdlf_client/client.py
@@ -283,15 +283,28 @@ async def put_object(self, path: str, data: bytes, overwrite: bool = True) -> No
             raise IOError(f"PUT {path} returned HTTP {status}")
 
     async def put_object_atomic(self, path: str, data: bytes) -> None:
-        """Write data atomically via .tmp + rename."""
+        """Write data atomically via .tmp + rename.
+
+        WebHDFS RENAME does not overwrite an existing destination — it
+        returns ``{"boolean": false}`` with HTTP 200 when the target
+        already exists, silently leaving stale content in place.  To
+        guarantee idempotent overwrites we delete the target before
+        renaming.  ``delete_object`` already treats 404 as success, so
+        this is safe for first-write and overwrite alike.
+        """
         log.debug("hdlf: put_object_atomic", path=path, bytes=len(data))
         tmp = path + ".tmp"
         await self.put_object(tmp, data, overwrite=True)
+        await self.delete_object(path)
         await self.rename(tmp, path)
         log.debug("hdlf: put_object_atomic complete", path=path)
 
     async def put_file_atomic(self, path: str, local_path: str) -> None:
-        """Upload a local file to HDLF atomically via .tmp + rename, streaming in chunks."""
+        """Upload a local file to HDLF atomically via .tmp + rename, streaming in chunks.
+
+        Same delete-before-rename strategy as :meth:`put_object_atomic` —
+        see its docstring for the WebHDFS RENAME overwrite caveat.
+        """
         if self._session is None:
             raise RuntimeError("HdlfClient must be used as an async context manager")
         file_size = os.path.getsize(local_path)
@@ -334,6 +347,7 @@ async def _chunks():
             ):
                 with attempt:
                     await _do_put()
+            await self.delete_object(path)
             await self.rename(tmp, path)
         except (RetryError, IOError, aiohttp.ClientError):
             await self._try_delete(tmp)
diff --git a/hdlf_server/app.py b/hdlf_server/app.py
index 1f86bda2..fb42e047 100644
--- a/hdlf_server/app.py
+++ b/hdlf_server/app.py
@@ -11,11 +11,13 @@
 from fastapi import FastAPI
 
 from hdlf_server.dependencies import lifespan
+from hdlf_server.handler_results_router import router as handler_results_router
 from hdlf_server.health import router as health_router
 from hdlf_server.router import router as inspection_router
 
 
 def create_app() -> FastAPI:
+    """Build and return the configured FastAPI application."""
     app = FastAPI(
         title="FL Control Plane — Handler SDK API",
         description=(
@@ -28,6 +30,7 @@ def create_app() -> FastAPI:
     )
     app.include_router(health_router)
     app.include_router(inspection_router, prefix="/api/v1")
+    app.include_router(handler_results_router, prefix="/api/v1")
     return app
 
 
diff --git a/hdlf_server/dependencies.py b/hdlf_server/dependencies.py
index e138c001..19bd9f70 100644
--- a/hdlf_server/dependencies.py
+++ b/hdlf_server/dependencies.py
@@ -5,19 +5,33 @@
 the normal aiohttp pattern (per-request sessions would defeat connection
 pooling and multiply the mTLS handshake cost).
 
+The same lifespan also opens an :class:`InspectionResultsRepository` over
+the shared client (write endpoints live in ``handler_results_router.py``).
+Reusing the client means one mTLS handshake and one connection pool serve
+both the read endpoints (via ``InspectionReader``) and the write endpoint
+(via the repository).
+
 Singleton storage uses ``app.state`` rather than module-level globals so
 that two FastAPI apps in the same process (a real one plus a test app,
 multi-tenant test runs) cannot trample each other. Tests that need to
-substitute the reader/client should use ``app.dependency_overrides``.
+substitute the reader/client/repository should use
+``app.dependency_overrides``.
 """
 
 from __future__ import annotations
 
 import logging
+from collections.abc import AsyncIterator
 from contextlib import asynccontextmanager
 
 from fastapi import FastAPI, Request
+from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
 
+from fl_control_plane.database import async_session
+from fl_control_plane.inspection_results_repository import (
+    InspectionResultsRepository,
+    make_inspection_results_repository_from_client,
+)
 from fl_shared.hdlf_client import HdlfClient, HdlfConfigurationError
 from fl_shared.hdlf_client.config import Settings
 from hdlf_server.reader import InspectionReader
@@ -26,12 +40,18 @@
 
 
 @asynccontextmanager
-async def lifespan(app: FastAPI):
+async def lifespan(app: FastAPI) -> AsyncIterator[None]:
     """Open the HDLF connection on startup, close it on shutdown.
 
-    Stores the live client and reader on ``app.state``. Each FastAPI app
-    has its own ``state`` namespace, so two apps in the same process
-    (e.g. real + test) get isolated singletons for free.
+    Stores the live client, reader, and inspection-results repository on
+    ``app.state``. Each FastAPI app has its own ``state`` namespace, so
+    two apps in the same process (e.g. real + test) get isolated
+    singletons for free.
+
+    The repository is entered as an async context manager *inside* the
+    same ``async with client`` block so its lifecycle is bound to the
+    client's — exit order is repository first, then client, matching how
+    they were opened.
     """
     cfg = Settings()
     log.info(
@@ -55,14 +75,26 @@ async def lifespan(app: FastAPI):
         log.exception("hdlf_server: HdlfClient configuration error during startup")
         raise
     async with client:
+        repository = make_inspection_results_repository_from_client(client)
+        # NOTE: we deliberately do NOT enter ``repository`` as a separate
+        # async context manager.  The repository's ``__aenter__`` would
+        # call ``client.__aenter__`` a second time — and HdlfClient's
+        # ``__aenter__`` unconditionally creates a fresh aiohttp session,
+        # leaking the one we just opened with the outer ``async with``.
+        # Binding lifecycles via the outer block is sufficient: the
+        # repository becomes unusable as soon as the client exits.
         app.state.hdlf_client = client
         app.state.inspection_reader = InspectionReader(client)
+        app.state.inspection_results_repository = repository
+        app.state.db_session_factory = async_session
         try:
             yield
         finally:
             log.info("hdlf_server: closing HdlfClient")
             del app.state.hdlf_client
             del app.state.inspection_reader
+            del app.state.inspection_results_repository
+            del app.state.db_session_factory
 
 
 def get_reader(request: Request) -> InspectionReader:
@@ -71,7 +103,7 @@ def get_reader(request: Request) -> InspectionReader:
     Raises RuntimeError if called before lifespan startup or after shutdown
     — that would indicate a wiring bug, not a runtime condition.
     """
-    reader = getattr(request.app.state, "inspection_reader", None)
+    reader: InspectionReader | None = getattr(request.app.state, "inspection_reader", None)
     if reader is None:
         raise RuntimeError("InspectionReader is not initialised — lifespan startup did not run")
     return reader
@@ -83,7 +115,35 @@ def get_client(request: Request) -> HdlfClient:
     Used by the local readiness probe to test HDLF reachability directly
     without going through the reader.
     """
-    client = getattr(request.app.state, "hdlf_client", None)
+    client: HdlfClient | None = getattr(request.app.state, "hdlf_client", None)
     if client is None:
         raise RuntimeError("HdlfClient is not initialised — lifespan startup did not run")
     return client
+
+
+def get_inspection_results_repository(request: Request) -> InspectionResultsRepository:
+    """FastAPI dependency that yields the singleton results repository.
+
+    Used by ``handler_results_router`` for the write endpoint.  Raises
+    ``RuntimeError`` outside lifespan for the same reason ``get_reader``
+    does — accessing the repository without startup is a wiring bug.
+    """
+    repo: InspectionResultsRepository | None = getattr(request.app.state, "inspection_results_repository", None)
+    if repo is None:
+        raise RuntimeError("InspectionResultsRepository is not initialised — lifespan startup did not run")
+    return repo
+
+
+async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
+    """FastAPI dependency that yields a control-plane DB session.
+
+    Reads the session factory off ``app.state`` rather than importing the
+    module-level singleton directly so tests can substitute a different
+    factory (the per-test in-memory SQLite engine from
+    ``tests/conftest.py``) via ``app.state.db_session_factory``.
+    """
+    factory: async_sessionmaker[AsyncSession] | None = getattr(request.app.state, "db_session_factory", None)
+    if factory is None:
+        raise RuntimeError("DB session factory is not initialised — lifespan startup did not run")
+    async with factory() as session:
+        yield session
diff --git a/hdlf_server/handler_results_router.py b/hdlf_server/handler_results_router.py
new file mode 100644
index 00000000..dfe82d05
--- /dev/null
+++ b/hdlf_server/handler_results_router.py
@@ -0,0 +1,292 @@
+"""HTTP write endpoints for handler results.
+
+Sibling of :mod:`hdlf_server.router`, which is read-only.  Splitting the
+write surface into its own module keeps each router file's responsibility
+statement honest: reads go through ``InspectionReader``, writes go through
+``InspectionResultsRepository``.  The two have different error hierarchies,
+so they also get distinct exception translators (``_raise_http_for_write``
+here vs ``_raise_http_for`` in ``router.py``).
+
+The single endpoint exposed today is::
+
+    PUT /api/v1/inspection/{inspection_id}/handler-results/{fault_id}
+
+It accepts one handler's output (result JSON, optional description, scope,
+addressed stages, optional code-changes diff) and persists it via the
+inspection-results repository.  Strict-PUT semantics: when the body omits
+``code_changes``, any pre-existing diff for the same ``fault_id`` is
+removed by the repository.
+
+Optional-field fallback: when ``output_description`` or ``scope`` is
+omitted (or ``null``) the endpoint resolves the missing field(s) from the
+control-plane database — most recent ``handler_executions`` row for
+``(inspection_id, fault_id)`` joined to ``fault_handlers``.  A lean PUT
+against a handler with no scheduled execution returns 400.  A full-body
+PUT never touches the database.
+"""
+
+from __future__ import annotations
+
+import logging
+import re
+from typing import Any, NoReturn
+from urllib.parse import unquote
+
+import sqlalchemy.exc
+import tenacity
+from fastapi import APIRouter, Depends, HTTPException, Path
+from pydantic import UUID4, BaseModel, Field
+from sqlalchemy.ext.asyncio import AsyncSession
+
+from fl_control_plane.handler_orchestrator.defaults_resolver import (
+    HandlerExecutionNotFoundError,
+    resolve_handler_defaults_with_retry,
+)
+from fl_control_plane.inspection_results_repository import (
+    InspectionResultsConfigurationError,
+    InspectionResultsRepository,
+    InspectionResultsTransientError,
+    InspectionResultsValidationError,
+    Scope,
+)
+from hdlf_server.dependencies import (
+    get_db_session,
+    get_inspection_results_repository,
+)
+from hdlf_server.exceptions import InvalidPathError
+
+_MAX_DECODE_ITERATIONS = 8
+
+log = logging.getLogger(__name__)
+
+router = APIRouter(tags=["handler-results"])
+
+_FAULT_ID_ALLOWLIST = re.compile(r"^[A-Za-z0-9._-]+$")
+
+
+# ── Request model ───────────────────────────────────────────────────────────
+
+
+class WriteHandlerResultRequest(BaseModel):
+    """Body of a PUT to ``/api/v1/inspection/{inspection_id}/handler-results/{fault_id}``.
+
+    Provenance: the body of a write request from a Fault Handler pod.
+
+    Both ``output_description`` and ``scope`` are optional with lazy DB
+    fallback: when either is absent (omitted or explicitly ``null``), the
+    endpoint resolves the missing field by joining
+    ``handler_executions ⋈ fault_handlers`` on
+    ``(inspection_id, fault_id)`` and reading the most recent execution's
+    joined ``FaultHandler.default_output_description`` /
+    ``FaultHandler.strategy``.  Body-supplied values always win over DB
+    values.  Full-body PUTs (both fields present) SHALL NOT query the
+    database — that keeps manual/SDK/curl callers working during DB
+    incidents.
+
+    ``addressed_stages`` is read verbatim from the body when present and
+    persisted as ``None`` when absent.  The endpoint never derives it
+    from orchestrator state — only the handler itself knows which stages
+    it actually addressed (D11 in design.md).
+
+    ``code_changes`` follows strict-PUT semantics in the repository:
+    when ``None`` (or omitted), any pre-existing diff for the same
+    ``fault_id`` is removed so the persisted state equals exactly what
+    the last body said.
+
+    Example (full body)::
+
+        WriteHandlerResultRequest(
+            result_json={"issues": 3, "severity": "high"},
+            output_description="SonarQube found 3 high-severity issues.",
+            scope="pipeline_scoped",
+            addressed_stages=None,
+            code_changes=None,
+        )
+
+    Example (lean body — fields resolved from DB)::
+
+        WriteHandlerResultRequest(
+            result_json={"finding": "missing FROM"},
+            addressed_stages=["build"],
+        )
+
+    Attributes:
+        result_json:        Structured handler output payload.  Required;
+                            stored verbatim as ``result.json``.
+        output_description: Human-readable summary, or ``None`` to fall
+                            back to ``FaultHandler.default_output_description``
+                            via the DB lookup.  When neither body nor DB
+                            has a value, the on-disk
+                            ``result_description.md`` is zero bytes.
+        scope:              ``"stage_scoped"`` or ``"pipeline_scoped"``,
+                            or ``None`` to fall back to
+                            ``FaultHandler.strategy``.  When neither body
+                            nor DB has a value, the persisted
+                            ``handler_metadata.json`` records
+                            ``"scope": null``.
+        addressed_stages:   Stage names the handler addressed.  Verbatim
+                            from the body; never derived.
+        code_changes:       Raw diff/patch.  ``None`` (or omitted)
+                            removes any previously stored diff for this
+                            ``fault_id``.
+    """
+
+    result_json: dict[str, Any] = Field(...)
+    output_description: str | None = None
+    scope: Scope | None = None
+    addressed_stages: list[str] | None = None
+    code_changes: str | None = None
+
+
+# ── Validation ──────────────────────────────────────────────────────────────
+
+
+def _validate_fault_id(fault_id: str) -> str:
+    """Reject perimeter ``fault_id`` values that fail the allowlist.
+
+    Strategy mirrors :func:`hdlf_server.reader._validate_subpath`'s
+    percent-decode loop so any chain of encodings collapses to its final
+    form (a single ``unquote`` only undoes one layer).  After decoding,
+    the value must match ``^[A-Za-z0-9._-]+$``.
+
+    This is the perimeter check — strict by design.  The repository
+    applies a denylist (``..``, ``/``, ``\\``, NUL, empty) so even
+    in-process callers can't smuggle a bad value past us; see D6 in
+    design.md.
+
+    Raises:
+        InvalidPathError: ``fault_id`` did not normalise or fell outside
+            the allowlist.  Translated to HTTP 400 by
+            :func:`_raise_http_for_write`.
+    """
+    decoded = fault_id
+    for _ in range(_MAX_DECODE_ITERATIONS):
+        once = unquote(decoded)
+        if once == decoded:
+            break
+        decoded = once
+    else:
+        raise InvalidPathError("fault_id has too many percent-encoding layers")
+    if not _FAULT_ID_ALLOWLIST.match(decoded):
+        raise InvalidPathError(f"fault_id must match ^[A-Za-z0-9._-]+$ after percent-decoding (got {fault_id!r})")
+    return decoded
+
+
+# ── Exception translator ────────────────────────────────────────────────────
+
+
+def _raise_http_for_write(exc: Exception) -> NoReturn:
+    """Translate write-path exceptions to FastAPI HTTPException.
+
+    Separate from ``router.py``'s ``_raise_http_for`` because the read
+    and write paths intentionally maintain distinct exception hierarchies
+    (``HdlfServerError`` vs ``InspectionResultsError``).  Mixing the two
+    translators would entangle the read- and write-side responsibilities
+    that splitting the router files was meant to keep apart.
+
+    Always raises — never returns. ``NoReturn`` lets type-checkers see
+    that code after a call to this helper is unreachable.
+
+    Mapping (see D8 in design.md):
+
+    * ``InvalidPathError``                        → 400 (perimeter check)
+    * ``InspectionResultsValidationError``        → 400 (repository denylist)
+    * ``HandlerExecutionNotFoundError``           → 400 (no scheduled execution)
+    * ``InspectionResultsTransientError``         → 502 (HDLF I/O failed)
+    * ``tenacity.RetryError``                     → 503 (DB retries exhausted)
+    * ``InspectionResultsConfigurationError``     → 500 (HDLF mTLS broken)
+    * ``sqlalchemy.exc.SQLAlchemyError``          → 500 (non-transient DB bug)
+    """
+    if isinstance(exc, InvalidPathError):
+        raise HTTPException(status_code=400, detail=str(exc))
+    if isinstance(exc, InspectionResultsValidationError):
+        raise HTTPException(status_code=400, detail=str(exc))
+    if isinstance(exc, HandlerExecutionNotFoundError):
+        raise HTTPException(status_code=400, detail=str(exc))
+    if isinstance(exc, InspectionResultsTransientError):
+        raise HTTPException(status_code=502, detail=str(exc))
+    if isinstance(exc, tenacity.RetryError):
+        raise HTTPException(
+            status_code=503,
+            detail="Control-plane database is degraded — exhausted retry budget while "
+            "resolving handler defaults.  Retry with a full body that supplies "
+            "output_description and scope to bypass the DB lookup.",
+        )
+    if isinstance(exc, InspectionResultsConfigurationError):
+        raise HTTPException(status_code=500, detail=str(exc))
+    if isinstance(exc, sqlalchemy.exc.SQLAlchemyError):
+        # Non-transient SQLAlchemy errors (ProgrammingError, IntegrityError,
+        # etc.) indicate a server-side bug — propagate as 500.  Transient
+        # errors are intercepted by the retry wrapper above and only reach
+        # this point as a RetryError.
+        # str(exc) embeds [SQL: ...] and [parameters: {...}] — log server-side
+        # only; never send raw SQL or bound params to the caller.
+        log.error("non-transient database error in write path", exc_info=exc)
+        raise HTTPException(status_code=500, detail="Database error")
+    raise exc
+
+
+# ── Endpoint ────────────────────────────────────────────────────────────────
+
+
+@router.put(
+    "/inspection/{inspection_id}/handler-results/{fault_id}",
+    status_code=204,
+    summary="Persist one handler's output for an inspection",
+)
+async def put_handler_result(
+    request: WriteHandlerResultRequest,
+    inspection_id: UUID4 = Path(..., description="UUID4 inspection identifier"),
+    fault_id: str = Path(..., description="Stable handler identity"),
+    repo: InspectionResultsRepository = Depends(get_inspection_results_repository),
+    session: AsyncSession = Depends(get_db_session),
+) -> None:
+    """Persist one handler's output via the inspection-results repository.
+
+    See the module docstring for the resolution / strict-PUT contract.
+    """
+    try:
+        validated_fault_id = _validate_fault_id(fault_id)
+    except InvalidPathError as exc:
+        _raise_http_for_write(exc)
+
+    # Branch on whether the body provides BOTH optional fields — only
+    # then can we skip the DB lookup.  If either is absent we have to
+    # resolve at least one default, and the DB query returns both
+    # cheaply, so we always merge.
+    scope_to_write = request.scope
+    description_to_write = request.output_description
+    needs_lookup = request.scope is None or request.output_description is None
+    if needs_lookup:
+        try:
+            db_scope, db_description = await resolve_handler_defaults_with_retry(
+                session, str(inspection_id), validated_fault_id
+            )
+        except (
+            HandlerExecutionNotFoundError,
+            tenacity.RetryError,
+            sqlalchemy.exc.SQLAlchemyError,
+        ) as exc:
+            _raise_http_for_write(exc)
+        # Body wins over DB — only fill the gaps.
+        if scope_to_write is None:
+            scope_to_write = db_scope
+        if description_to_write is None:
+            description_to_write = db_description
+
+    try:
+        await repo.write_handler_result(
+            inspection_id=str(inspection_id),
+            fault_id=validated_fault_id,
+            result_json=request.result_json,
+            output_description=description_to_write,
+            scope=scope_to_write,
+            addressed_stages=request.addressed_stages,
+            code_changes=request.code_changes,
+        )
+    except (
+        InspectionResultsValidationError,
+        InspectionResultsTransientError,
+        InspectionResultsConfigurationError,
+    ) as exc:
+        _raise_http_for_write(exc)
diff --git a/hdlf_server/router.py b/hdlf_server/router.py
index 7c1ddbf5..62032f84 100644
--- a/hdlf_server/router.py
+++ b/hdlf_server/router.py
@@ -4,6 +4,12 @@
 dependency: this service is reachable only through the NetworkPolicy
 that admits pods carrying the `pipeline-fl/faulthandler` label.
 
+This router is **read-only**.  Write endpoints for handler results live
+in the sibling :mod:`hdlf_server.handler_results_router` so each file's
+responsibility statement stays true and the read/write exception
+hierarchies (``HdlfServerError`` vs ``InspectionResultsError``) do not
+have to share a translator.
+
 UUIDs are validated as `UUID4` (Pydantic), which prevents path-traversal
 in the `{id}` segment. Subpath inputs (`stage_dir`, artifact `relative_path`,
 raw `path` query) flow through `_validate_subpath` in `reader.py`.
@@ -12,7 +18,7 @@
 from __future__ import annotations
 
 import logging
-from collections.abc import Callable, AsyncGenerator, Awaitable
+from collections.abc import AsyncGenerator, Awaitable, Callable
 from typing import Any, NoReturn
 
 from fastapi import APIRouter, Depends, HTTPException, Path, Query
@@ -72,6 +78,7 @@ async def get_metadata(
     inspection_id: UUID4 = Path(..., description="UUID4 inspection identifier"),
     reader: InspectionReader = Depends(get_reader),
 ) -> InspectionMetadata:
+    """Return metadata.json for the given inspection."""
     try:
         return await reader.get_metadata(str(inspection_id))
     except (InspectionNotFoundError, MalformedInspectionDataError) as exc:
@@ -87,6 +94,7 @@ async def get_manifest(
     inspection_id: UUID4 = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> ManifestSummary:
+    """Return manifest.json for the given inspection."""
     try:
         return await reader.get_manifest(str(inspection_id))
     except (
@@ -106,6 +114,7 @@ async def get_stage_tree(
     inspection_id: UUID4 = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> StageTree:
+    """Return the Blue Ocean stage tree for the given inspection."""
     try:
         return await reader.get_stage_tree(str(inspection_id))
     except (
@@ -125,6 +134,7 @@ async def list_stages(
     inspection_id: UUID4 = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> list[StageSummary]:
+    """Return per-stage subfolder summaries for the given inspection."""
     try:
         return await reader.list_stages(str(inspection_id))
     except InspectionNotFoundError as exc:
@@ -141,6 +151,7 @@ async def get_stage_steps(
     stage_dir: str = Path(..., description="Stage subfolder name"),
     reader: InspectionReader = Depends(get_reader),
 ) -> list[StepInfo]:
+    """Return step details for one stage in the given inspection."""
     try:
         return await reader.get_stage_steps(str(inspection_id), stage_dir)
     except (
@@ -161,6 +172,7 @@ async def list_artifacts(
     inspection_id: UUID4 = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> list[ArtifactEntry]:
+    """Return captured artefact entries derived from manifest.json."""
     try:
         return await reader.list_artifacts(str(inspection_id))
     except (
@@ -179,14 +191,13 @@ async def get_test_summary(
     inspection_id: UUID4 = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> dict[str, Any]:
+    """Return parsed JUnit summary from tests/junit_summary.json."""
     try:
         result = await reader.get_test_summary(str(inspection_id))
     except (InspectionNotFoundError, MalformedInspectionDataError) as exc:
         _raise_http_for(exc)
     if result is None:
-        raise HTTPException(
-            status_code=404, detail="tests/junit_summary.json not captured"
-        )
+        raise HTTPException(status_code=404, detail="tests/junit_summary.json not captured")
     return result
 
 
@@ -198,9 +209,8 @@ async def get_build_summary(
     inspection_id: UUID4 = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> dict[str, Any]:
-    return await _read_optional_json(
-        reader, str(inspection_id), reader.get_build_summary, "build_summary.json"
-    )
+    """Return parsed build_summary.json."""
+    return await _read_optional_json(reader, str(inspection_id), reader.get_build_summary, "build_summary.json")
 
 
 @router.get(
@@ -211,9 +221,8 @@ async def get_build_params(
     inspection_id: UUID4 = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> dict[str, Any]:
-    return await _read_optional_json(
-        reader, str(inspection_id), reader.get_build_params, "build_params.json"
-    )
+    """Return parsed build_params.json."""
+    return await _read_optional_json(reader, str(inspection_id), reader.get_build_params, "build_params.json")
 
 
 @router.get(
@@ -224,9 +233,8 @@ async def get_build_causes(
     inspection_id: UUID4 = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> dict[str, Any]:
-    return await _read_optional_json(
-        reader, str(inspection_id), reader.get_build_causes, "build_causes.json"
-    )
+    """Return parsed build_causes.json."""
+    return await _read_optional_json(reader, str(inspection_id), reader.get_build_causes, "build_causes.json")
 
 
 @router.get(
@@ -237,9 +245,8 @@ async def get_environment(
     inspection_id: UUID4 = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> dict[str, Any]:
-    return await _read_optional_json(
-        reader, str(inspection_id), reader.get_environment, "environment.json"
-    )
+    """Return parsed environment.json."""
+    return await _read_optional_json(reader, str(inspection_id), reader.get_environment, "environment.json")
 
 
 @router.get(
@@ -250,9 +257,8 @@ async def get_scm_changelog(
     inspection_id: UUID4 = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> dict[str, Any]:
-    return await _read_optional_json(
-        reader, str(inspection_id), reader.get_scm_changelog, "scm_changelog.json"
-    )
+    """Return parsed scm_changelog.json."""
+    return await _read_optional_json(reader, str(inspection_id), reader.get_scm_changelog, "scm_changelog.json")
 
 
 @router.get(
@@ -265,6 +271,7 @@ async def list_files(
     subpath: str = Query("", description="Folder relative to the inspection root"),
     reader: InspectionReader = Depends(get_reader),
 ) -> list[RawFileInfo]:
+    """List raw files under the inspection folder or a given subpath."""
     try:
         return await reader.list_files(str(inspection_id), subpath)
     except (InspectionNotFoundError, InvalidPathError) as exc:
@@ -280,9 +287,8 @@ async def stream_console_log(
     inspection_id: UUID4 = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> StreamingResponse:
-    return await _stream(
-        reader, str(inspection_id), reader.stream_console_log, "text/plain; charset=utf-8"
-    )
+    """Stream the full build console log."""
+    return await _stream(reader, str(inspection_id), reader.stream_console_log, "text/plain; charset=utf-8")
 
 
 @router.get(
@@ -295,6 +301,7 @@ async def stream_stage_log(
     stage_dir: str = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> StreamingResponse:
+    """Stream the per-stage console log."""
     return await _stream(
         reader,
         str(inspection_id),
@@ -314,6 +321,7 @@ async def stream_artifact(
     relative_path: str = Path(..., description="Path under artifacts/"),
     reader: InspectionReader = Depends(get_reader),
 ) -> StreamingResponse:
+    """Stream a captured artefact by its relative path."""
     return await _stream(
         reader,
         str(inspection_id),
@@ -332,9 +340,8 @@ async def stream_test_xml(
     inspection_id: UUID4 = Path(...),
     reader: InspectionReader = Depends(get_reader),
 ) -> StreamingResponse:
-    return await _stream(
-        reader, str(inspection_id), reader.stream_test_xml, "application/xml"
-    )
+    """Stream the JUnit XML report."""
+    return await _stream(reader, str(inspection_id), reader.stream_test_xml, "application/xml")
 
 
 @router.get(
@@ -347,6 +354,7 @@ async def stream_raw(
     path: str = Query(..., description="Path relative to the inspection folder"),
     reader: InspectionReader = Depends(get_reader),
 ) -> StreamingResponse:
+    """Stream any file under the inspection folder by relative path."""
     return await _stream(
         reader,
         str(inspection_id),
@@ -357,7 +365,7 @@ async def stream_raw(
 
 
 async def _read_optional_json(
-    reader: InspectionReader,
+    _reader: InspectionReader,
     inspection_id: str,
     method: Callable[[str], Awaitable[dict[str, Any] | None]],
     file_label: str,
@@ -381,14 +389,12 @@ async def _read_optional_json(
     ) as exc:
         _raise_http_for(exc)
     if result is None:
-        raise HTTPException(
-            status_code=404, detail=f"{file_label} not captured"
-        )
+        raise HTTPException(status_code=404, detail=f"{file_label} not captured")
     return result
 
 
 async def _stream(
-    reader: InspectionReader,
+    _reader: InspectionReader,
     inspection_id: str,
     method: Callable[..., AsyncGenerator[bytes, None]],
     media_type: str,
@@ -443,6 +449,6 @@ async def _peek_first(agen: AsyncGenerator[bytes, None]) -> bytes | None:
     Returns None if the iterator is empty.
     """
     try:
-        return await agen.__anext__()
+        return await anext(agen)
     except StopAsyncIteration:
         return None
diff --git a/openspec/changes/handler-results-write-endpoint/design.md b/openspec/changes/handler-results-write-endpoint/design.md
new file mode 100644
index 00000000..be74b228
--- /dev/null
+++ b/openspec/changes/handler-results-write-endpoint/design.md
@@ -0,0 +1,186 @@
+## Context
+
+`hdlf_server` is the HTTP facade over HDLF for Fault Handler pods. Today it exposes ~20 read endpoints (metadata, manifest, stage tree, logs, artefacts) routed through `InspectionReader`. Writing handler results, by contrast, is done by handlers themselves through `InspectionResultsRepository.write_handler_result`, which means each handler image carries its own `HdlfClient` and mTLS material. This change exposes the write over HTTP so handlers can drop the direct dependency.
+
+The repository already has a well-defined write surface — `result.json`, `result_description.md`, `handler_metadata.json`, optional `code_changes.diff` — that the HDLF backend writes via four atomic puts. The work is plumbing, plus a small set of correctness decisions around HTTP semantics and input validation.
+
+## Goals / Non-Goals
+
+**Goals:**
+- Expose one resource-oriented HTTP write endpoint that mirrors the read surface's URL conventions.
+- Reuse the existing `HdlfClient` connection pool instead of opening a second one.
+- Keep `router.py`'s read-only commitment intact by introducing a sibling router file.
+- Validate the path parameter against path traversal at both the router and repository layers (defence in depth) — the router stops obvious abuse with a positive allowlist, the repository stops every caller (HTTP, future SDK, in-process bug) with a security-focused denylist.
+- Make the endpoint's behaviour idempotent under retry by the byte-level guarantees already provided by `put_object_atomic`.
+
+**Non-Goals:**
+- Querying or rejecting unknown `fault_id`s against a `fault_handlers` table. Discussed and deferred — format validation alone covers the security threat model; typo and lifecycle enforcement, if it ever becomes a real operational pain, will be added as a separate change once the SLO and fail-open/closed semantics are known.
+- Migrating Fault Handler Jobs to use the new endpoint. That is a follow-up change in the handler-SDK repo.
+- Exposing list/delete operations for handler results over HTTP. The MCP layer already covers reads end-to-end.
+
+## Decisions
+
+### D1: PUT, not POST
+
+**Decision**: Use `PUT /api/v1/inspection/{inspection_id}/handler-results/{fault_id}`. The body carries the handler payload.
+
+**Rationale**: The repository write is byte-level idempotent — calling twice with the same body produces the same HDLF state — and the path identifies the resource (one handler's result for one inspection). PUT is the honest verb for "replace the resource state with the given representation". A retry under PUT is safe by construction; under POST a retry has to be reasoned about case by case.
+
+**Alternative considered**: POST as the JIRA literally requests. Rejected — the operation is replacement of a uniquely-addressable resource, not creation in a collection.
+
+### D2: Strict-PUT semantics for the optional `code_changes` field
+
+**Decision**: When the request body has `code_changes: null` (or the field absent), the endpoint guarantees that any pre-existing `code_changes.diff` for the same fault is removed. The persisted resource state equals exactly what the last PUT body said.
+
+**Rationale**: Lenient ("merge") PUT — leave the diff alone if `code_changes` is null — is one line of code shorter and matches today's repository behaviour, but lets stale state silently survive a retry with a smaller body. Debugging "why is there still a diff that nobody put there" is awful. Strict-PUT puts the burden on the caller to send the full intended state, which is the standard PUT contract.
+
+**Alternative considered**: Lenient PUT (today's behaviour). Rejected — the cost of the surprise outweighs the line saved.
+
+### D3: New sibling router file, not extending `router.py`
+
+**Decision**: Add `hdlf_server/handler_results_router.py`. Both routers are mounted under `/api/v1` in `app.py`.
+
+**Rationale**: `hdlf_server/router.py`'s module docstring commits to "maps `InspectionReader` methods to resource-oriented endpoints". A write that talks to `InspectionResultsRepository` is a different responsibility — different reader/repo, different error hierarchy, different HTTP-translation table. Splitting keeps each router file's responsibility statement true, makes test isolation cleaner, and gives future write endpoints (deletion, listing) a natural home.
+
+**Alternative considered**: Add the handler to `router.py`. Rejected — widens the file's responsibility from "read inspection data" to "everything FL handlers touch over HTTP", and forces the existing read-side translator and dependency to grow.
+
+### D4: Reuse the lifespan-managed `HdlfClient`
+
+**Decision**: Add `make_inspection_results_repository_from_client(HdlfClient) -> InspectionResultsRepository` next to the existing `make_inspection_results_repository(HdlfConnectionParams)` factory. The new function builds `HdlfInspectionResultsRepository` over a pre-built client. `dependencies.py` calls it during `lifespan` startup and stores the repository on `app.state` alongside the existing reader.
+
+**Rationale**: The existing factory `make_inspection_results_repository` opens its own `HdlfClient`. Calling it from `lifespan` would double the connection pool and double the mTLS handshake cost on every request. The HDLF backend's concrete class already accepts a client — exposing that path via a sibling factory keeps `hdlf_server` from importing the concrete backend directly (the factory abstraction's original goal).
+
+**Alternative considered**: Refactor the existing factory to accept an optional client. Rejected — overloading the factory's argument list muddles its responsibility. Two named factories, one per construction mode, is clearer.
+
+### D5: New exception `InspectionResultsValidationError`
+
+**Decision**: Add a new exception in `inspection_results_repository.py` alongside `InspectionResultsConfigurationError`, `InspectionResultsTransientError`, and `HandlerResultNotFoundError`. Raised by `write_handler_result` (and any future write methods) when `fault_id` fails validation.
+
+**Rationale**: The existing exception hierarchy was built so callers can switch on intent, not on storage technology. "You gave me a `fault_id` I refuse to write" is a distinct intent from "I/O failed" (transient) and "I'm misconfigured" (configuration). Reusing `ValueError` would force the router translator to discriminate by message text or type-check a non-domain exception; reusing one of the existing three would confuse intent.
+
+**Alternative considered**: `raise ValueError`. Rejected — CLAUDE.md endorses `ValueError` for precondition checks, but the repository's contract is that all errors are subclasses of `InspectionResultsError` so callers stay storage-agnostic. The exception family must stay closed.
+
+### D6: Defence-in-depth validation — router allowlist + repository denylist
+
+**Decision**:
+
+- **Router-side** (`handler_results_router.py`): apply a positive allowlist regex `^[A-Za-z0-9._-]+$` on `fault_id` plus the fixed-point percent-decode loop already used by `_validate_subpath`. Reject as HTTP 400 with `InvalidPathError` (or equivalent).
+- **Repository-side** (`inspection_results_repository.py`): apply a security-focused denylist (`..`, contains `/`, contains `\`, contains `\x00`, empty string) inside `write_handler_result` before constructing any path. Raise `InspectionResultsValidationError`. The router translator maps this to HTTP 400.
+
+**Rationale**: The router is the API perimeter and has the strictest information about what a *well-behaved* client sends — an allowlist is appropriate there. The repository must defend against every possible caller, including future SDKs and in-process code that splices user input into `fault_id`; an allowlist there would be brittle (real handler names are unbounded in principle), so a denylist focused on the security-relevant characters is the right level. The two layers catch different threat classes: the allowlist catches typos and Unicode lookalikes early; the denylist guarantees the path-construction code is safe regardless of how it was reached.
+
+**Alternative considered**: Validate only in the router, treat the repository as in-process and trusted. Rejected — once `write_handler_result` is in the public repository surface, any caller (including the existing in-process callers and any new MCP tool) can pass arbitrary `fault_id`; a single failure of the perimeter check would corrupt HDLF layout.
+
+**Alternative considered**: Query `fault_handlers` table for the active set of `fault_id`s and reject anything else. Rejected — couples the hot write path to a database, introduces a second failure mode (DB down → handlers can't persist results), and is hygiene rather than security. Revisit only if typo detection becomes a real operational problem.
+
+### D7: Status code 204 No Content on success
+
+**Decision**: Return HTTP 204 with no body on successful write. Same status for first-write and overwrite.
+
+**Rationale**: A first-vs-overwrite distinction (201 vs 200) requires an `exists` probe per request and adds no information the caller doesn't already have. 204 is the standard PUT-success status when no body needs to come back.
+
+### D8: HTTP error translation table
+
+| Exception | HTTP | Where raised |
+|---|---|---|
+| Pydantic body `ValidationError` | 422 | FastAPI auto |
+| Router-side fault_id allowlist failure | 400 | router `_validate_fault_id` |
+| `InspectionResultsValidationError` | 400 | repository |
+| `HandlerExecutionNotFoundError` | 400 | router (no orchestrator row for this `(inspection_id, fault_id)` on a lean PUT) |
+| `InspectionResultsTransientError` | 502 | repository (HDLF I/O failed) |
+| DB lookup retries exhausted (lean PUT) | 503 | router |
+| `InspectionResultsConfigurationError` | 500 | repository (HDLF mTLS/cert misconfigured) |
+
+The new translator `_raise_http_for_write` lives in `handler_results_router.py` next to the handler. It is intentionally separate from `_raise_http_for` in `router.py` because the two error hierarchies (`HdlfServerError` vs `InspectionResultsError`) are intentionally separate.
+
+### D9: Optional `output_description` and `scope` with DB fallback
+
+**Decision**: `output_description` and `scope` are optional in the request body (omitted-or-`null` are treated identically). When either is absent, the endpoint resolves it from the control-plane database. A body value always wins over the DB value; the lookup happens lazily — full-body PUTs never query the DB.
+
+**Rationale**: Handlers whose output classification is invariant per `fault_id` (the common case — `sonarqube-analysis` always means the same thing) shouldn't have to restate CR-derived metadata on every PUT. Dynamic handlers that emit different descriptions per invocation retain full control by sending the fields explicitly. The lazy lookup keeps the full-body path DB-independent, so manual/SDK/curl callers continue to work even during DB incidents.
+
+**Alternative considered**: Make both fields required (today's design). Rejected — it forces every handler image to carry its CR's static metadata or repeat it from configuration, defeating the simplification the lean body buys for the common case.
+
+**Alternative considered**: Always query the DB and merge (eager lookup). Rejected — breaks the DB-independence of full-body PUTs and adds a hot DB dependency that wasn't previously there for handlers that have nothing to gain from it.
+
+### D10: Source the fallback via `handler_executions ⋈ fault_handlers`, not `fault_handlers` alone
+
+**Decision**: The DB lookup is:
+
+```sql
+SELECT fh.scope, fh.default_output_description
+FROM handler_executions he
+JOIN fault_handlers fh ON he.fault_handler_id = fh.id
+WHERE he.inspection_id = :inspection_id
+  AND he.fault_id = :fault_id
+ORDER BY he.created_at DESC
+LIMIT 1
+```
+
+Zero rows → 400 ("no scheduled execution for this fault in this inspection"). One or more rows → use the most recent one's joined `FaultHandler`.
+
+**Rationale**: The `fault_handlers` table allows multiple `is_active=True` rows for the same `fault_id` (different `cr_id` / namespace / `resource_version`). The orchestrator's `select_versions` already disambiguates at planning time and records its choice in `handler_executions.fault_handler_id`. Reading through that join is the only way to be self-consistent with the orchestrator's decision without duplicating its disambiguation rule. The bonus: the join naturally rejects lean PUTs for handlers that were never scheduled, without re-opening the D6 lifecycle / typo-detection debate — the rejection is structural ("FL doesn't know about this execution"), not policy ("FL doesn't allow this fault_id"). A full-body PUT for the same fault still succeeds, so manual/debug callers retain a documented workaround.
+
+**Alternative considered**: `SELECT FROM fault_handlers WHERE fault_id AND is_active` with a tiebreaker (highest `resource_version` or latest `registered_at`). Rejected — duplicates orchestrator logic and silently drifts if `select_versions` ever changes.
+
+### D11: `addressed_stages` — body or `None`, never derived
+
+**Decision**: `addressed_stages` is read verbatim from the body when present, written as `None` when omitted. FL never infers it — not from orchestrator stage-pairing tables, not from CR config.
+
+**Rationale**: Only the handler itself knows which stages it actually addressed. A handler given three stages may have skipped one due to a transient failure or an early-exit condition; "stages addressed" claimed from orchestrator pairing would be a fabricated claim. `None` honestly records "the handler didn't tell us". Consumers (MCP, UI) treat `None` as unknown rather than "all" or "none".
+
+**Alternative considered**: For stage-scoped handlers with missing `addressed_stages`, default to "all stages this execution was paired with". Rejected — silent fabrication.
+
+**Alternative considered**: Require `addressed_stages` whenever `scope` resolves to `stage_scoped`, reject otherwise. Rejected — the handler may be running outside the orchestrator (debug / SDK) and the agreement check is fussier than the value it adds.
+
+### D12: New CR-derived column `fault_handlers.default_output_description`
+
+**Decision**: Add a nullable `default_output_description: TEXT` column to `fault_handlers`. The handler-orchestrator's CR-reconciliation loop populates it from a new optional `description` field in the FaultHandler CR spec. The hot-write-path lookup reads this column; the column is nullable because handler authors are not required to register a default.
+
+**Rationale**: The existing pattern in `fault_handlers` "promotes" CR fields used in hot paths into dedicated columns (`scope`, `ci_systems`, `repo_patterns`, `trigger_scope`) while keeping the rest in `spec_json`. The lean-PUT lookup is a hot path — extracting the default from a JSON blob on every write would double the query cost and complicate the SQL. A dedicated column is faster, simpler, and follows the established convention.
+
+**Alternative considered**: Derive a default from `cr_name` (e.g. "Handler `sonarqube-analysis` completed.") without a new column. Rejected — the default would be content-free, so handlers wanting a meaningful description would always have to send it in the body, defeating the lean-PUT benefit.
+
+**Alternative considered**: Read `spec_json.description` on each PUT. Rejected — hot path performance and consistency-with-pattern.
+
+### D13: DB-lookup retry policy and failure modes
+
+**Decision**: The lean-PUT DB lookup is wrapped in a tenacity retry: predicate `retry_if_exception_type((sqlalchemy.exc.OperationalError, sqlalchemy.exc.InterfaceError))`, 5 attempts, exponential backoff capped at ~8s per wait with a total wall-clock budget around 25s.
+
+Failure-mode table for lean PUTs:
+
+| Condition | HTTP |
+|---|---|
+| Lookup succeeds, row found | 204 (proceed with merged fields) |
+| Lookup succeeds, zero rows | 400 (`HandlerExecutionNotFoundError`) |
+| Lookup retries succeed within budget | 204 |
+| Lookup retries exhausted (transient DB failure) | 503 |
+| Non-transient DB error (e.g. `ProgrammingError`) | 500 (`InspectionResultsConfigurationError` — surfaced as a server bug, not retried) |
+
+**Rationale**: A short retry window catches connection blips and rolling restarts without bothering the caller. Past the budget, the call surfaces 503 — a clear operator signal that the control-plane DB is degraded. The handler job exits non-zero and the orchestrator's next reconciliation tick re-runs the handler.
+
+This trades a worker slot during the retry window for not losing handler results that cost real money to produce (LLM tokens for agent_task handlers). Without internal retry, a 5-second DB hiccup would lose every concurrent lean PUT's result, since the orchestrator does not currently reschedule individual handler-execution failures. With internal retry, those same hiccups are transparent; only sustained outages reach the orchestrator.
+
+**Alternative considered**: No internal retry; 503 on first DB failure. Rejected — silently lose results during routine DB blips even though a retry would have succeeded.
+
+**Alternative considered**: Persist `None` when the retry budget is exhausted (no 503). Rejected — without an operator-visible signal, a long DB outage would silently degrade every lean PUT's metadata. The 503 announces the degradation to monitoring; operators have the option to instruct handlers to send full bodies during the incident.
+
+### D14: Make `output_description` and `scope` `Optional` end-to-end
+
+**Decision**: `InspectionResultsRepository.write_handler_result` accepts `output_description: str | None` and `scope: _SCOPE | None`. The read model `InspectionResultEntry` exposes the same two fields as `Optional`. The HDLF backend writes the JSON `null` for either when the input is `None`; the read parser tolerates the `null` and yields `None` rather than raising `MalformedInspectionDataError`.
+
+**Rationale**: D9 + D12 admit a path where neither the body nor the DB has a value — the handler author registered no `default_output_description` and the body omitted the field, but the lookup did find an execution row. The system must round-trip that state. Loosening the fields end-to-end is the only consistent option: write-accepts-None-but-read-rejects-None would mean a write succeeds and a subsequent read fails on the same row, which is the worst kind of contract.
+
+**Alternative considered**: Reject the lean-PUT call when the default column is NULL and the body omits the field. Rejected — pushes a hygiene concern (handler authors filling out CRs) into the data path. A handler whose result is otherwise valuable shouldn't fail to persist because of a missing default.
+
+## Risks / Trade-offs
+
+- **Strict-PUT requires an extra `delete` call on every PUT with `code_changes=None`.** This is one HDLF round-trip per write where one didn't exist before. The HDLF backend's `delete_object` already exists; treat "not found" as success to keep the operation idempotent. Mitigation: an internal `_delete_if_exists` helper on the HDLF backend that swallows `FileNotFoundError`.
+- **Two validators of `fault_id` mean two places to keep in sync.** Mitigation: their *purposes* differ (allowlist vs denylist), so they intentionally drift over time — router's regex can tighten with no impact on the repository's invariant.
+- **Repository validator change is breaking for any current in-process caller that passes a `fault_id` with `/`.** Searching the codebase finds no such caller — `fault_id`s in tests are `"foo-handler"`, `"sonarqube-analysis"`, etc. Risk minimal.
+- **Lean PUTs add a hot DB dependency to the write path.** Mitigated by tenacity retry (D13) and by the lazy-lookup property (full-body PUTs are DB-independent). Operators can advise handlers to send full bodies during DB incidents.
+- **Lean-PUT idempotency depends on CR stability.** Two retries of the same lean PUT can produce different HDLF state if a FaultHandler CR is reconciled in between (different `scope` or `default_output_description`). Full-body PUTs remain unconditionally idempotent. This is acceptable because CR updates already trigger re-evaluation upstream in the orchestrator; the same retry concern exists for any config-derived behaviour.
+
+## Open Questions
+
+None — the additional decisions (D9–D14) are settled and consistent with the original four (verb, PUT semantics on null, validation exception type, status code).
diff --git a/openspec/changes/handler-results-write-endpoint/proposal.md b/openspec/changes/handler-results-write-endpoint/proposal.md
new file mode 100644
index 00000000..71dc975f
--- /dev/null
+++ b/openspec/changes/handler-results-write-endpoint/proposal.md
@@ -0,0 +1,37 @@
+## Why
+
+Fault Handler pods already read inspection data over HTTP from `hdlf_server` (the FastAPI service in front of HDLF), but to **write** their result they must construct their own `HdlfClient` — mTLS certs, host config, retry policy — and call `InspectionResultsRepository.write_handler_result` directly. The asymmetry forces every handler image to bundle the HDLF client and credentials, and widens the surface that has to be granted HDLF write access. Closing the asymmetry lets handlers persist results through the same NetworkPolicy-gated HTTP boundary they already use for reads.
+
+JIRA: [PIPELINE3-1429](https://jira.tools.sap/browse/PIPELINE3-1429).
+
+## What Changes
+
+- New HTTP endpoint `PUT /api/v1/inspection/{inspection_id}/handler-results/{fault_id}` on `hdlf_server` that persists one handler's output via `InspectionResultsRepository.write_handler_result`.
+- The endpoint follows strict-PUT semantics: the persisted resource state equals the request body exactly. When `code_changes` is `null` in the body, any pre-existing `code_changes.diff` for that fault is removed.
+- A new sibling router file `hdlf_server/handler_results_router.py` keeps `router.py`'s "read-only" responsibility intact.
+- A new factory `make_inspection_results_repository_from_client(HdlfClient)` reuses the lifespan-managed `HdlfClient` instead of opening a second connection pool.
+- The repository validates `fault_id` defensively on every call and raises a new `InspectionResultsValidationError`; the router applies a stricter allowlist-based check before reaching the repository (defence in depth).
+- A dedicated translator `_raise_http_for_write` maps repository-write exceptions to HTTP status codes, kept separate from the existing reader translator.
+- The request body's `output_description` and `scope` fields become **optional**. When omitted (or `null`), the endpoint resolves them via a join `handler_executions ⋈ fault_handlers` keyed by `(inspection_id, fault_id)`, defaulting `output_description` to the new `fault_handlers.default_output_description` column. Body values always win over DB defaults. `addressed_stages` continues to be taken verbatim from the body (or `None` when absent) — FL never derives it from orchestrator state.
+- The repository write contract and the read model (`InspectionResultEntry`) make `output_description` and `scope` `Optional` so the system can round-trip handlers whose CR did not register a `default_output_description` and whose body did not supply one.
+- A new schema migration adds `fault_handlers.default_output_description` (nullable text). The orchestrator's CR-reconciliation populates this column from a new optional `description` field in the FaultHandler CR spec.
+
+## Capabilities
+
+### New Capabilities
+
+- `handler-results-api`: HTTP write endpoint on `hdlf_server` that accepts `PUT` of one handler's output (result JSON, description, scope, addressed stages, optional code-changes diff), validates the path parameters against the path-traversal and allowlist rules, resolves optional body fields from the orchestrator's recorded execution when absent, persists via the repository, and translates repository errors to HTTP responses.
+- `fault-handler-registry`: a `default_output_description` column on `fault_handlers` populated from the FaultHandler CR by the handler-orchestrator's reconciliation loop. The handler-results write endpoint reads this column when the request body omits `output_description`.
+
+### Modified Capabilities
+
+- `inspection-results-repository`: `write_handler_result` gains an input-validation precondition on `fault_id` (rejecting `..`, `/`, `\`, NUL, empty string) raising a new `InspectionResultsValidationError`; it also implements strict-PUT semantics by deleting `code_changes.diff` when the caller passes `code_changes=None`. The `output_description` and `scope` parameters become `Optional`; the read model `InspectionResultEntry` makes the same fields `Optional` so reads round-trip the relaxed write contract. A new factory accepting a pre-built `HdlfClient` is added next to `make_inspection_results_repository`.
+
+## Impact
+
+- `hdlf_server/` — new `handler_results_router.py`, new request model, new dependency wiring in `dependencies.py`, registration in `app.py`. `router.py` and `reader.py` unchanged. The router gains a SQLAlchemy `AsyncSession` dependency for the lean-PUT lookup; the existing reader does not.
+- `fl_control_plane/inspection_results_repository/` — new exception class, new factory function, validation added to `write_handler_result`, strict-PUT behaviour added to the HDLF backend. `output_description` and `scope` accept `None` on both write and read.
+- `fl_control_plane/database.py` — new nullable column `fault_handlers.default_output_description` (alembic migration). `handler_orchestrator` reconciliation reads a new optional `description` field from the FaultHandler CR spec and writes it to the column.
+- Fault Handler Job images can drop the HDLF client dependency in a follow-up change (out of scope here).
+- Tests: new `tests/hdlf_server/test_handler_results_router.py`; expanded `tests/mcp_servers/test_inspection_results_repository.py` for validation and strict-PUT behaviour; new cases covering the DB-fallback path (lean PUT with execution row + default, lean PUT without execution row → 400, lean PUT with DB retry budget exhausted → 503, body overrides DB default).
+- No deployment topology or NetworkPolicy changes — the new endpoint sits on the same service and is reachable only by pods with the `pipeline-fl/faulthandler` label. The lean-PUT path adds a hot dependency on the control-plane database; full-body PUTs remain DB-independent.
diff --git a/openspec/changes/handler-results-write-endpoint/specs/fault-handler-registry/spec.md b/openspec/changes/handler-results-write-endpoint/specs/fault-handler-registry/spec.md
new file mode 100644
index 00000000..67ca7d4e
--- /dev/null
+++ b/openspec/changes/handler-results-write-endpoint/specs/fault-handler-registry/spec.md
@@ -0,0 +1,29 @@
+## ADDED Requirements
+
+### Requirement: Persist a default output description per registered fault handler
+The `fault_handlers` table SHALL include a nullable `default_output_description` column (text). The column SHALL be populated by the handler-orchestrator's CR-reconciliation loop from an optional `description` field in the FaultHandler CR spec. A NULL value SHALL be valid and SHALL mean "no default registered for this handler".
+
+#### Scenario: Column exists with the correct nullability
+- **WHEN** the alembic migrations are applied
+- **THEN** `fault_handlers.default_output_description` exists with type text and `nullable=True`
+
+#### Scenario: Reconciliation populates the column from CR description
+- **GIVEN** a FaultHandler CR with `spec.description="SonarQube analysis completed."` is reconciled
+- **THEN** the resulting `fault_handlers` row has `default_output_description="SonarQube analysis completed."`
+
+#### Scenario: Reconciliation leaves the column NULL when CR omits description
+- **GIVEN** a FaultHandler CR whose spec does not include `description`
+- **THEN** the resulting `fault_handlers` row has `default_output_description IS NULL`
+
+#### Scenario: Reconciliation updates the column when the CR description changes
+- **GIVEN** an existing `fault_handlers` row with `default_output_description="old description"`
+- **WHEN** the FaultHandler CR is reconciled with `spec.description="new description"`
+- **THEN** the row's `default_output_description` becomes `"new description"`
+
+### Requirement: Lookup-by-execution is available to read the default
+The control-plane database SHALL support efficient lookup of the joined `(handler_executions, fault_handlers)` tuple by `(inspection_id, fault_id)`. The existing composite index `ix_handler_executions_inspection_fault` SHALL cover the lookup; no additional index is required for this capability.
+
+#### Scenario: Join by (inspection_id, fault_id) returns scope and default_output_description
+- **GIVEN** a `handler_executions` row exists for `(inspection_id, fault_id)` referencing a `fault_handlers` row with `scope="stage_scoped"` and `default_output_description="X"`
+- **WHEN** a caller selects `fh.scope, fh.default_output_description` from `handler_executions he JOIN fault_handlers fh ON he.fault_handler_id = fh.id WHERE he.inspection_id = :i AND he.fault_id = :f`
+- **THEN** the result is exactly one row with `scope="stage_scoped"` and `default_output_description="X"`
diff --git a/openspec/changes/handler-results-write-endpoint/specs/handler-results-api/spec.md b/openspec/changes/handler-results-write-endpoint/specs/handler-results-api/spec.md
new file mode 100644
index 00000000..06ffd41c
--- /dev/null
+++ b/openspec/changes/handler-results-write-endpoint/specs/handler-results-api/spec.md
@@ -0,0 +1,149 @@
+## ADDED Requirements
+
+### Requirement: Expose HTTP write endpoint for handler results
+The `hdlf_server` service SHALL expose `PUT /api/v1/inspection/{inspection_id}/handler-results/{fault_id}` that persists one handler's output for the given inspection. The endpoint SHALL be reachable only by pods admitted by the same `pipeline-fl/faulthandler` NetworkPolicy as the existing read endpoints; the service SHALL NOT add any application-level authentication.
+
+#### Scenario: Valid PUT with all fields persists handler result
+- **WHEN** a client PUTs a body with `result_json`, `output_description`, `scope`, `addressed_stages`, and `code_changes` to `/api/v1/inspection/{uuid}/handler-results/{fault_id}` with a valid UUID4 and a `fault_id` matching the allowlist
+- **THEN** the service calls `InspectionResultsRepository.write_handler_result` with the body fields and responds with HTTP 204 No Content
+
+#### Scenario: Valid PUT without code_changes persists result and removes any stale diff
+- **WHEN** the client PUTs a body with `code_changes: null` (or the field absent) for a `fault_id` that previously had a `code_changes.diff`
+- **THEN** the service persists the other fields and the previously stored `code_changes.diff` is removed (strict-PUT semantics)
+- **AND** the response is HTTP 204
+
+#### Scenario: Repeated PUT with identical body is byte-level idempotent
+- **WHEN** the client issues the same PUT twice with the same body
+- **THEN** the persisted resource state after the second call is identical to the state after the first
+- **AND** both responses are HTTP 204
+
+### Requirement: Reject malformed request bodies
+The endpoint SHALL reject request bodies that do not conform to the documented schema (missing required field, wrong type, unknown field, invalid `scope` value) with HTTP 422. The required fields are `result_json`; `output_description`, `scope`, `addressed_stages`, and `code_changes` are optional (see "Resolve optional body fields …" below).
+
+#### Scenario: Missing required field rejected
+- **WHEN** the body omits `result_json`
+- **THEN** the service responds with HTTP 422 and does not call the repository
+
+#### Scenario: Invalid scope rejected
+- **WHEN** the body contains `scope: "global"` (not one of `stage_scoped` or `pipeline_scoped`)
+- **THEN** the service responds with HTTP 422 and does not call the repository
+
+### Requirement: Resolve optional body fields from the orchestrator's recorded execution
+When `output_description` or `scope` is absent from the request body (omitted or `null`), the endpoint SHALL resolve each missing field via a join of `handler_executions` (filtered by `inspection_id` and `fault_id`) with `fault_handlers` on `fault_handler_id`, taking the most recent matching execution's joined values. Body-supplied values SHALL always take precedence over DB values. When all four optional fields are present in the body, the endpoint SHALL NOT query the database. `addressed_stages` SHALL be taken verbatim from the body when present and SHALL be `None` when absent — the endpoint SHALL NOT derive it from orchestrator state.
+
+#### Scenario: Lean PUT with a scheduled execution succeeds using DB defaults
+- **GIVEN** a `handler_executions` row exists for `(inspection_id, fault_id)` whose joined `FaultHandler` has `scope="stage_scoped"` and `default_output_description="SonarQube analysis completed."`
+- **WHEN** the client PUTs a body containing only `result_json` and `addressed_stages=["build"]`
+- **THEN** the service writes a handler result with `scope="stage_scoped"`, `output_description="SonarQube analysis completed."`, and `addressed_stages=["build"]`
+- **AND** the response is HTTP 204
+
+#### Scenario: Body value wins over DB default
+- **GIVEN** a scheduled execution exists with joined `default_output_description="static description"`
+- **WHEN** the client PUTs a body with `output_description="dynamic per-run description"` and `scope` omitted
+- **THEN** the persisted `output_description` is `"dynamic per-run description"`
+- **AND** the persisted `scope` is taken from the DB
+
+#### Scenario: Full-body PUT bypasses the DB
+- **WHEN** the client PUTs a body with `result_json`, `output_description`, and `scope` all present
+- **THEN** the endpoint SHALL NOT query the database, even if no `handler_executions` row exists
+- **AND** the response is HTTP 204
+
+#### Scenario: Lean PUT for an un-scheduled execution returns 400
+- **GIVEN** no `handler_executions` row exists for `(inspection_id, fault_id)`
+- **WHEN** the client PUTs a body that omits `output_description` or `scope`
+- **THEN** the service responds with HTTP 400 with a message indicating no scheduled execution
+- **AND** the repository is not called
+
+#### Scenario: Lean PUT writes None when neither body nor DB has a value
+- **GIVEN** a `handler_executions` row exists whose joined `FaultHandler.default_output_description IS NULL`
+- **WHEN** the client PUTs a body that omits `output_description`
+- **THEN** the persisted `output_description` is `None` (recorded as JSON `null` in `handler_metadata.json` and `result_description.md` is written empty)
+- **AND** the response is HTTP 204
+
+#### Scenario: addressed_stages not derived
+- **WHEN** the client PUTs a lean body that omits `addressed_stages` and the joined `FaultHandler.scope` resolves to `stage_scoped`
+- **THEN** the persisted `addressed_stages` is `None` — the endpoint SHALL NOT populate it from orchestrator-paired stages
+
+### Requirement: Retry transient DB failures during optional-field resolution
+When the DB lookup raises a transient SQLAlchemy error (`OperationalError` or `InterfaceError`), the endpoint SHALL retry the lookup up to five times with exponential backoff capped at approximately eight seconds per wait and a total wall-clock budget around twenty-five seconds. If retries succeed within the budget, the call SHALL proceed normally and respond 204. If retries are exhausted, the endpoint SHALL respond with HTTP 503. Non-transient SQLAlchemy errors SHALL NOT be retried and SHALL surface as HTTP 500.
+
+#### Scenario: Transient DB blip is retried transparently
+- **GIVEN** the first two lookup attempts raise `OperationalError` but the third succeeds
+- **WHEN** the client PUTs a lean body
+- **THEN** the response is HTTP 204 and the write reflects the looked-up values
+
+#### Scenario: Exhausted retry budget returns 503
+- **GIVEN** every lookup attempt raises `OperationalError` until the budget is exhausted
+- **WHEN** the client PUTs a lean body
+- **THEN** the response is HTTP 503 and the HDLF write is not attempted
+
+#### Scenario: Full-body PUT unaffected by DB outage
+- **GIVEN** every DB lookup attempt would raise `OperationalError`
+- **WHEN** the client PUTs a full body (`output_description` and `scope` both present)
+- **THEN** the endpoint SHALL NOT query the database
+- **AND** the response is HTTP 204
+
+### Requirement: Validate path parameters at the perimeter
+The endpoint SHALL validate the `inspection_id` path parameter as a UUID4 and the `fault_id` path parameter against a fixed-point percent-decode loop followed by an allowlist regex `^[A-Za-z0-9._-]+$`. Invalid `inspection_id` SHALL respond with HTTP 422 (FastAPI's UUID4 validation). Invalid `fault_id` SHALL respond with HTTP 400 and SHALL NOT reach the repository.
+
+#### Scenario: Non-UUID4 inspection_id rejected
+- **WHEN** the URL contains `inspection_id=not-a-uuid`
+- **THEN** the service responds with HTTP 422
+
+#### Scenario: fault_id with traversal segment rejected
+- **WHEN** the URL contains `fault_id=..`
+- **THEN** the service responds with HTTP 400 and the repository is not called
+
+#### Scenario: fault_id with embedded slash rejected
+- **WHEN** the URL contains `fault_id=foo/bar` (or its percent-encoded form `foo%2Fbar`)
+- **THEN** the service responds with HTTP 400 and the repository is not called
+
+#### Scenario: Percent-encoded traversal rejected
+- **WHEN** the URL contains `fault_id=%2E%2E` (encoded `..`)
+- **THEN** the percent-decode loop produces `..`, the allowlist rejects it, and the service responds with HTTP 400
+
+#### Scenario: Well-formed fault_id accepted
+- **WHEN** the URL contains `fault_id=sonarqube-analysis` (only `A-Za-z0-9._-`)
+- **THEN** the path-parameter check passes and the repository is invoked
+
+### Requirement: Translate repository errors to HTTP status codes
+The endpoint SHALL translate exceptions raised by `InspectionResultsRepository.write_handler_result`, by the optional-field-resolution lookup, and by the path-validation step to HTTP responses through a dedicated translator separate from the reader endpoints' translator.
+
+#### Scenario: Validation error from the repository returns 400
+- **WHEN** the repository raises `InspectionResultsValidationError`
+- **THEN** the service responds with HTTP 400 and the error message in the body
+
+#### Scenario: Missing scheduled execution on a lean PUT returns 400
+- **WHEN** the optional-field-resolution lookup finds no `handler_executions` row for `(inspection_id, fault_id)` and the body omits at least one of `output_description` / `scope`
+- **THEN** the service responds with HTTP 400 with a message indicating no scheduled execution
+
+#### Scenario: Transient storage failure returns 502
+- **WHEN** the repository raises `InspectionResultsTransientError` (HDLF write retries exhausted)
+- **THEN** the service responds with HTTP 502
+
+#### Scenario: Transient DB failure on a lean PUT returns 503
+- **WHEN** the optional-field-resolution lookup retry budget is exhausted on a transient SQLAlchemy error
+- **THEN** the service responds with HTTP 503
+
+#### Scenario: Configuration error returns 500
+- **WHEN** the repository raises `InspectionResultsConfigurationError` (HDLF mTLS or container-ID misconfigured)
+- **THEN** the service responds with HTTP 500
+
+### Requirement: Reuse the lifespan-managed HdlfClient
+The endpoint SHALL share the `HdlfClient` opened at app startup with the existing read endpoints. The service SHALL NOT open a second HDLF connection pool for the write path.
+
+#### Scenario: Single HDLF connection pool serves both read and write
+- **WHEN** the app starts up and processes a mix of GET and PUT requests
+- **THEN** exactly one `HdlfClient` is constructed during `lifespan` and used for both routes
+- **AND** the repository for the write endpoint is built via a factory that accepts the pre-built `HdlfClient` (so the abstract repository surface is preserved and the concrete backend class is not imported by `hdlf_server` directly)
+
+### Requirement: Write endpoint lives in a sibling router file
+The write endpoint SHALL be defined in `hdlf_server/handler_results_router.py`, distinct from `hdlf_server/router.py` which remains read-only. Both routers SHALL be mounted under `/api/v1`.
+
+#### Scenario: Read endpoints unaffected by write endpoint code paths
+- **WHEN** the write router file is removed from the app's router registration
+- **THEN** all read endpoints continue to function and the read-side translator and dependencies are unchanged
+
+#### Scenario: `router.py` does not import write-side symbols
+- **WHEN** a static check scans `hdlf_server/router.py`
+- **THEN** it contains no references to `InspectionResultsRepository`, `WriteHandlerResultRequest`, or `_raise_http_for_write`
diff --git a/openspec/changes/handler-results-write-endpoint/specs/inspection-results-repository/spec.md b/openspec/changes/handler-results-write-endpoint/specs/inspection-results-repository/spec.md
new file mode 100644
index 00000000..8635a8f9
--- /dev/null
+++ b/openspec/changes/handler-results-write-endpoint/specs/inspection-results-repository/spec.md
@@ -0,0 +1,76 @@
+## ADDED Requirements
+
+### Requirement: Validate fault_id before any storage operation
+`InspectionResultsRepository.write_handler_result` SHALL validate its `fault_id` argument before constructing any storage path or invoking any I/O. The validation SHALL reject empty strings, the literal segment `..`, any string containing `/`, `\`, or `\x00`. On rejection it SHALL raise `InspectionResultsValidationError` — a new subclass of `InspectionResultsError` — and SHALL NOT perform any storage operation.
+
+#### Scenario: Empty fault_id rejected
+- **WHEN** `write_handler_result(fault_id="", ...)` is called
+- **THEN** `InspectionResultsValidationError` is raised before any HDLF call
+
+#### Scenario: fault_id containing path separator rejected
+- **WHEN** `write_handler_result(fault_id="foo/bar", ...)` is called
+- **THEN** `InspectionResultsValidationError` is raised before any HDLF call
+
+#### Scenario: fault_id containing traversal segment rejected
+- **WHEN** `write_handler_result(fault_id="..", ...)` is called
+- **THEN** `InspectionResultsValidationError` is raised before any HDLF call
+
+#### Scenario: fault_id containing NUL byte rejected
+- **WHEN** `write_handler_result(fault_id="foo\\x00bar", ...)` is called
+- **THEN** `InspectionResultsValidationError` is raised before any HDLF call
+
+#### Scenario: Well-formed fault_id accepted
+- **WHEN** `write_handler_result(fault_id="sonarqube-analysis", ...)` is called with otherwise valid arguments
+- **THEN** the call proceeds to storage
+
+### Requirement: Strict-PUT semantics for code_changes
+`InspectionResultsRepository.write_handler_result` SHALL guarantee that the post-write state of `code_changes.diff` reflects the `code_changes` argument exactly: when `code_changes` is a string the file SHALL contain that string; when `code_changes` is `None` the file SHALL NOT exist after the call regardless of whether a previous call left one behind.
+
+#### Scenario: First write with code_changes creates the diff file
+- **WHEN** `write_handler_result(fault_id="f", code_changes="--- a/...", ...)` is called for the first time
+- **THEN** `code_changes.diff` is written with the given content
+
+#### Scenario: Subsequent write with code_changes=None removes the diff
+- **WHEN** `write_handler_result(fault_id="f", code_changes="--- a/...", ...)` is followed by `write_handler_result(fault_id="f", code_changes=None, ...)`
+- **THEN** after the second call `code_changes.diff` no longer exists in storage
+
+#### Scenario: Write with code_changes=None when no prior diff exists succeeds
+- **WHEN** `write_handler_result(fault_id="f", code_changes=None, ...)` is called for a fault that has never had a diff
+- **THEN** the call returns normally without raising
+
+#### Scenario: Transient storage failure during diff deletion surfaces correctly
+- **WHEN** the underlying storage's delete-if-exists call raises an `IOError` other than not-found
+- **THEN** `write_handler_result` raises `InspectionResultsTransientError` with the storage error wrapped, consistent with the rest of the method
+
+### Requirement: Factory accepting a pre-built HdlfClient
+The module SHALL expose `make_inspection_results_repository_from_client(hdlf_client: HdlfClient) -> InspectionResultsRepository` as a sibling to the existing `make_inspection_results_repository(params: HdlfConnectionParams)` factory. The new factory SHALL construct the HDLF-backed repository over the supplied client without opening a new client.
+
+#### Scenario: Factory returns an HDLF-backed repository sharing the supplied client
+- **WHEN** `make_inspection_results_repository_from_client(existing_client)` is called
+- **THEN** the returned repository's underlying client is `existing_client` (no new mTLS handshake, no new connection pool)
+
+#### Scenario: Both factories produce instances satisfying the same abstract contract
+- **WHEN** a caller constructs the repository via either factory
+- **THEN** the returned object is an `InspectionResultsRepository` and exposes the same abstract methods identically
+
+### Requirement: Accept None for output_description and scope on write
+`InspectionResultsRepository.write_handler_result` SHALL accept `output_description: str | None` and `scope: Literal["stage_scoped", "pipeline_scoped"] | None`. When either is `None`, the HDLF backend SHALL write JSON `null` for `scope` in `handler_metadata.json` and SHALL write an empty `result_description.md` for a `None` `output_description`.
+
+#### Scenario: write_handler_result accepts None for both fields
+- **WHEN** `write_handler_result(..., output_description=None, scope=None, ...)` is called with otherwise valid arguments
+- **THEN** the call proceeds without raising
+- **AND** the stored `handler_metadata.json` contains `"scope": null`
+- **AND** the stored `result_description.md` is zero bytes
+
+#### Scenario: write_handler_result accepts None for scope only
+- **WHEN** `write_handler_result(..., output_description="ok", scope=None, ...)` is called
+- **THEN** the stored `handler_metadata.json` contains `"scope": null` and the description file contains `"ok"`
+
+### Requirement: Read model tolerates None for output_description and scope
+`InspectionResultEntry` SHALL declare `output_description: str | None` and `scope: Literal["stage_scoped", "pipeline_scoped"] | None`. The HDLF backend's `list_handler_results` SHALL NOT raise `MalformedInspectionDataError` when `handler_metadata.json` contains `"scope": null` or when `result_description.md` is empty — it SHALL yield an entry with the corresponding field set to `None`.
+
+#### Scenario: list_handler_results round-trips a handler written with None fields
+- **GIVEN** a previous `write_handler_result` call with `output_description=None` and `scope=None`
+- **WHEN** `list_handler_results(inspection_id)` is called
+- **THEN** the returned entry has `output_description=None` and `scope=None`
+- **AND** no exception is raised
diff --git a/openspec/changes/handler-results-write-endpoint/tasks.md b/openspec/changes/handler-results-write-endpoint/tasks.md
new file mode 100644
index 00000000..81996587
--- /dev/null
+++ b/openspec/changes/handler-results-write-endpoint/tasks.md
@@ -0,0 +1,98 @@
+## 1. Repository validation and strict-PUT
+
+- [x] 1.1 Add `InspectionResultsValidationError` to `fl_control_plane/inspection_results_repository/inspection_results_repository.py` alongside the existing three error subclasses; export it from the package `__init__.py`.
+- [x] 1.2 Add a module-level `_validate_fault_id(fault_id: str) -> None` helper in `inspection_results_repository.py` that raises `InspectionResultsValidationError` when `fault_id` is empty, contains `..`, contains `/`, contains `\`, or contains `\x00`. Document the *security* purpose in the docstring.
+- [x] 1.3 Call `_validate_fault_id` as the first line of `InspectionResultsRepository.write_handler_result` in the abstract base class? — actually keep it in concrete backends to preserve the ABC's purity; alternatively make it a concrete helper on the ABC. Decide during implementation. (Either way: every backend must validate before touching storage.)
+- [x] 1.4 In `inspection_results_repository_hdlf.py`, call `_validate_fault_id` at the top of `write_handler_result`.
+- [x] 1.5 Implement strict-PUT in `HdlfInspectionResultsRepository.write_handler_result`: when `code_changes is None`, attempt to delete `<base>/code_changes.diff` (treating `FileNotFoundError` as success); wrap any other `IOError` in `InspectionResultsTransientError` consistent with the rest of the method.
+- [x] 1.6 Update `write_handler_result`'s docstring in the abstract base to document (a) the `InspectionResultsValidationError` it can now raise and (b) the strict-PUT semantics for `code_changes`.
+
+## 2. Sibling factory
+
+- [x] 2.1 Add `make_inspection_results_repository_from_client(hdlf_client: HdlfClient) -> InspectionResultsRepository` in `inspection_results_repository.py` next to `make_inspection_results_repository`. Document why both factories exist (one builds its own client, one reuses an external one).
+- [x] 2.2 Export the new factory from `fl_control_plane.inspection_results_repository.__init__`.
+
+## 3. Router scaffolding
+
+- [x] 3.1 Create `hdlf_server/handler_results_router.py` with a module docstring stating its responsibility ("write endpoints for handler results; reads live in `router.py`") and `router = APIRouter(tags=["handler-results"])`.
+- [x] 3.2 Define the request model `WriteHandlerResultRequest(BaseModel)` with fields `result_json: dict[str, Any]`, `output_description: str`, `scope: Literal["stage_scoped", "pipeline_scoped"]`, `addressed_stages: list[str] | None = None`, `code_changes: str | None = None`. Include a full Pydantic docstring following the project convention.
+- [x] 3.3 Add a router-side `_validate_fault_id(fault_id: str) -> str` that fixed-point percent-decodes the input (mirroring `_validate_subpath`'s loop) and rejects anything not matching `^[A-Za-z0-9._-]+$`. Raise the existing `InvalidPathError` from `hdlf_server.exceptions` on rejection.
+- [x] 3.4 Add `_raise_http_for_write(exc: Exception) -> NoReturn` translating `InvalidPathError` → 400, `InspectionResultsValidationError` → 400, `InspectionResultsTransientError` → 502, `InspectionResultsConfigurationError` → 500.
+
+## 4. Endpoint
+
+- [x] 4.1 Implement `put_handler_result(...)` bound to `PUT /inspection/{inspection_id}/handler-results/{fault_id}` with `status_code=204`, validating `inspection_id` via `UUID4` and `fault_id` via `_validate_fault_id`, then calling `repo.write_handler_result(...)` with the body fields.
+- [x] 4.2 Catch the four expected exceptions from the repository call and route through `_raise_http_for_write`; let Pydantic body validation surface as 422 naturally.
+
+## 5. Lifespan wiring
+
+- [x] 5.1 In `hdlf_server/dependencies.py` lifespan, after creating the `HdlfClient`, call `make_inspection_results_repository_from_client(client)` and store the result on `app.state.inspection_results_repository`.
+- [x] 5.2 Enter and exit the repository as an async context manager inside the same `async with client` block, so its lifecycle is bound to the client's.
+- [x] 5.3 Add a `get_inspection_results_repository(request: Request) -> InspectionResultsRepository` FastAPI dependency mirroring `get_reader`/`get_client`, raising `RuntimeError` if accessed outside lifespan.
+
+## 6. App registration
+
+- [x] 6.1 In `hdlf_server/app.py`, import `handler_results_router` and include it under the same `/api/v1` prefix as the existing inspection router.
+
+## 7. Tests
+
+- [x] 7.1 Add `tests/mcp_servers/test_inspection_results_repository.py` cases:
+    - `_validate_fault_id` rejects `..`, `foo/bar`, `foo\\bar`, empty string, NUL-containing strings — each parametrized.
+    - `write_handler_result` raises `InspectionResultsValidationError` (the new exception) when `fault_id` is invalid, before touching the client.
+    - Strict-PUT: after a write with `code_changes="..."` followed by a write with `code_changes=None`, the `.diff` file is gone.
+    - Strict-PUT: a write with `code_changes=None` against a fault that has no prior diff succeeds (no spurious error).
+- [x] 7.2 Add `tests/hdlf_server/test_handler_results_router.py` cases:
+    - `PUT /inspection/{uuid}/handler-results/foo-handler` with valid body returns 204 and the underlying repository was called with matching args.
+    - `PUT` with `fault_id="../escape"` returns 400 and the repository was not called.
+    - `PUT` with `fault_id="foo/bar"` (percent-encoded as `%2F`) returns 400 — verifies the percent-decode loop catches the encoded form.
+    - `PUT` with a body missing `output_description` returns 422 (FastAPI auto).
+    - `PUT` where the repository raises `InspectionResultsTransientError` returns 502.
+    - `PUT` where the repository raises `InspectionResultsConfigurationError` returns 500.
+    - `PUT` against a non-UUID path segment returns 422.
+- [x] 7.3 Extend `tests/hdlf_server/conftest.py` to override `get_inspection_results_repository` with a repository over the existing `FakeHdlfClient`. Reuse the fixture across read and write tests.
+
+## 8. Documentation
+
+- [x] 8.1 Update `hdlf_server/router.py`'s module docstring if needed to make explicit that writes live in `handler_results_router.py`. (Currently says "Maps `InspectionReader` methods to resource-oriented endpoints" — adequate, but adding a one-line pointer prevents future confusion.)
+- [x] 8.2 No README updates expected in this repo (no public docs exist for `hdlf_server` endpoints yet). If a handler-SDK doc is added later it should reference the new endpoint.
+
+## 9. Optional body fields and DB fallback (D9–D14)
+
+- [x] 9.1 Relax `WriteHandlerResultRequest`: make `output_description: str | None = None` and `scope: Literal["stage_scoped", "pipeline_scoped"] | None = None`. Update the Pydantic docstring to document the lazy DB-fallback contract and that body values always win over DB values.
+- [x] 9.2 Loosen the abstract `InspectionResultsRepository.write_handler_result` signature: `output_description: str | None` and `scope: _SCOPE | None`. Update the docstring to describe the on-disk representation when either is `None` (JSON `null` in `handler_metadata.json`; empty `result_description.md`).
+- [x] 9.3 Loosen the `InspectionResultEntry` read model: `output_description: str | None` and `scope: _SCOPE | None`. Update the model docstring (Provenance + Attributes) to explain when each becomes `None`.
+- [x] 9.4 In `HdlfInspectionResultsRepository.write_handler_result`, accept `None` for the two fields. For `output_description=None`, write zero bytes to `result_description.md`. For `scope=None`, the `metadata` dict already json-encodes `None` as `null` — no logic change beyond the type signature.
+- [x] 9.5 In `HdlfInspectionResultsRepository.list_handler_results`, tolerate `scope: null` in `handler_metadata.json` and an empty `result_description.md`: parse to `None` rather than raising `MalformedInspectionDataError`.
+
+## 10. Schema migration and CR-reconciliation
+
+- [x] 10.1 Add `default_output_description: Optional[str] = mapped_column(Text, nullable=True)` to `FaultHandler` in `fl_control_plane/database.py`.
+- [x] 10.2 Generate an alembic migration `db/migrations/versions/000X_fault_handler_default_description.py` adding the column with `nullable=True`. No data backfill required — existing rows get NULL.
+- [x] 10.3 In the FaultHandler CR contract, document a new optional `spec.description` string field. Update `fl_control_plane/handler_orchestrator/seed.py` and the relevant CR-watcher reconciliation code to read `spec.description` and populate the new column on insert/update.
+- [x] 10.4 Add `description` to the three seeded handler dicts in `seed.py` (`landscape-ado-analysis`, `jenkins-bounded-analysis`, `hadolint-analysis`) with sensible defaults so dev/test runs exercise the populated path.
+
+## 11. DB lookup with retry in the router
+
+- [x] 11.1 Add a SQLAlchemy `AsyncSession` dependency to the new router. Use the project's existing session-factory pattern (do not open a new engine). Cross-check `fl_control_plane/database.py` and `fl_control_plane/handler_orchestrator/orchestrator.py` for the established pattern.
+- [x] 11.2 Implement `_resolve_handler_defaults(session, inspection_id, fault_id) -> tuple[_SCOPE | None, str | None]`. Returns the joined `(scope, default_output_description)` for the most recent matching `handler_executions` row, or raises `HandlerExecutionNotFoundError` (new local exception class — caught by the translator and mapped to 400) when zero rows match.
+- [x] 11.3 Wrap the lookup in a `tenacity.AsyncRetrying`-driven loop: predicate `retry_if_exception_type((sqlalchemy.exc.OperationalError, sqlalchemy.exc.InterfaceError))`, `stop_after_attempt(5)`, `wait_exponential(multiplier=1, max=8)`, total wall-clock bounded around 25s. Non-transient SQLAlchemy errors SHALL propagate unwrapped.
+- [x] 11.4 In the endpoint handler, branch on whether the body provides both `output_description` and `scope`. If yes, skip the DB call. If no, call `_resolve_handler_defaults` for the missing fields only and merge — body wins.
+- [x] 11.5 Extend `_raise_http_for_write`:
+    - `HandlerExecutionNotFoundError` → 400.
+    - `tenacity.RetryError` (or a sentinel wrapper raised when the retry budget is exhausted) → 503.
+    - Other SQLAlchemy errors → 500 (treated as configuration / server bug).
+
+## 12. Tests for the DB-fallback path
+
+- [x] 12.1 Repository tests in `tests/mcp_servers/test_inspection_results_repository.py`:
+    - `write_handler_result` with `output_description=None, scope=None` writes empty `result_description.md` and `"scope": null` in metadata JSON.
+    - `list_handler_results` round-trips an entry written with `None`s and returns the entry with both fields `None`.
+- [x] 12.2 Router tests in `tests/hdlf_server/test_handler_results_router.py`:
+    - Lean PUT with a `handler_executions` row whose joined `FaultHandler` has both `scope` and `default_output_description` populated → 204, persisted values match DB.
+    - Lean PUT where the body sets `output_description` but omits `scope` → 204, persisted `output_description` is body's value, persisted `scope` is DB's value.
+    - Lean PUT with no `handler_executions` row → 400, repository not called.
+    - Full-body PUT with no `handler_executions` row → 204 (DB not queried — assert via mocked session that no `execute` call was made).
+    - Lean PUT with `OperationalError` raised twice then succeeding → 204 (retries observable via call counter on a wrapped session).
+    - Lean PUT with `OperationalError` exhausting the budget → 503; HDLF write not attempted.
+    - Lean PUT with `ProgrammingError` → 500 (non-transient SQLAlchemy error is not retried).
+- [x] 12.3 Seed-data test: parametrise over the three seeded handlers and assert that each persists with a non-NULL `default_output_description` after migration + seed.
diff --git a/scripts/deploy-dev.sh b/scripts/deploy-dev.sh
index 3f69e6d2..115decb8 100755
--- a/scripts/deploy-dev.sh
+++ b/scripts/deploy-dev.sh
@@ -312,10 +312,22 @@ else
   )
 fi
 
+# ---------------------------------------------------------------------------
+# CRDs — applied idempotently via kubectl so they work regardless of whether
+# another Helm release already installed them. Helm's built-in CRD handling
+# only runs on first install and conflicts on multi-namespace deploys because
+# CRDs are cluster-scoped.
+# ---------------------------------------------------------------------------
+echo "==> Applying CRDs (idempotent)..."
+for crd_file in "${CHART_DIR}"/crds/*.yaml; do
+  [[ -f "$crd_file" ]] && _kubectl apply -f "$crd_file"
+done
+
 echo "==> Installing/upgrading ${RELEASE}..."
 _helm upgrade --install "$RELEASE" "$CHART_DIR" \
   --dependency-update \
   --namespace "$NAMESPACE" \
+  --skip-crds \
   --timeout 300s \
   --wait \
   --wait-for-jobs \
diff --git a/tests/handler_orchestrator/conftest.py b/tests/handler_orchestrator/conftest.py
index 518faa1e..77dac0d9 100644
--- a/tests/handler_orchestrator/conftest.py
+++ b/tests/handler_orchestrator/conftest.py
@@ -42,7 +42,7 @@ def _make_handler(
         cr_namespace="fl-system",
         fault_id=fault_id,
         execution_type="agent_task",
-        scope=scope,
+        strategy=scope,
         ci_systems=json.dumps(ci_systems) if ci_systems is not None else None,
         repo_patterns=json.dumps(repo_patterns) if repo_patterns is not None else None,
         trigger_scope=trigger_scope,
diff --git a/tests/handler_orchestrator/test_seed.py b/tests/handler_orchestrator/test_seed.py
new file mode 100644
index 00000000..b12418ee
--- /dev/null
+++ b/tests/handler_orchestrator/test_seed.py
@@ -0,0 +1,36 @@
+"""Tests for handler-orchestrator seed data.
+
+Asserts that each seeded FaultHandler persists with a non-NULL
+``default_output_description`` after migration + seed — the lean-PUT
+handler-results path relies on this column being populated so dev/test
+runs exercise the DB-fallback branch.
+"""
+
+from __future__ import annotations
+
+import pytest
+from sqlalchemy import select
+from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
+
+from fl_control_plane.database import FaultHandler
+from fl_control_plane.handler_orchestrator.seed import seed_fault_handlers
+
+_SEEDED_CR_NAMES = ("hadolint-analysis", "landscape-ado-analysis", "jenkins-bounded-analysis")
+
+
+@pytest.mark.asyncio
+@pytest.mark.parametrize("cr_name", _SEEDED_CR_NAMES)
+async def test_seeded_handler_has_default_output_description(
+    test_session_factory: async_sessionmaker[AsyncSession],
+    cr_name: str,
+) -> None:
+    """Each seeded FaultHandler row exposes a non-NULL default_output_description."""
+    async with test_session_factory() as session:
+        await seed_fault_handlers(session)
+
+    async with test_session_factory() as session:
+        result = await session.execute(select(FaultHandler).where(FaultHandler.cr_name == cr_name))
+        handler = result.scalar_one()
+
+    assert handler.default_output_description is not None
+    assert handler.default_output_description != ""
diff --git a/tests/hdlf_server/conftest.py b/tests/hdlf_server/conftest.py
index b5334610..aa421abd 100644
--- a/tests/hdlf_server/conftest.py
+++ b/tests/hdlf_server/conftest.py
@@ -10,27 +10,53 @@
 `fl_shared.hdlf_client.config.settings` constructs without raising
 at app import time. The values are dummies — the FakeHdlfClient is what
 actually serves data in tests.
+
+The same `client` fixture also overrides
+``get_inspection_results_repository`` and ``get_db_session`` so write-side
+tests (``test_handler_results_router.py``) reuse the same app, ASGI
+transport, and ``FakeHdlfClient`` as the read-side tests.  ``get_db_session``
+is left mapped to a default per-test in-memory SQLite session; individual
+write tests that need DB rows can ``app.dependency_overrides`` to supply
+their own session.
 """
 
 from __future__ import annotations
 
-import os
-
-# Must be set before any fl_shared.hdlf_client or hdlf_server import.
-os.environ.setdefault("HDLF_REST_API_HOST", "test.invalid")
-os.environ.setdefault("HDLF_CONTAINER_ID", "test-container")
-
 import json
+import os
 from collections.abc import AsyncIterator
 from dataclasses import dataclass
 
 import pytest
 import pytest_asyncio
 from httpx import ASGITransport, AsyncClient
+from sqlalchemy.ext.asyncio import AsyncSession
+
+# Must be set before any fl_shared.hdlf_client or hdlf_server import.
+# pylint: disable=wrong-import-position,wrong-import-order
+os.environ.setdefault("HDLF_REST_API_HOST", "test.invalid")
+os.environ.setdefault("HDLF_CONTAINER_ID", "test-container")
+
+from fl_control_plane.inspection_results_repository import (  # noqa: E402
+    make_inspection_results_repository_from_client,
+)
+from fl_shared.hdlf_client.client import FileStatus  # noqa: E402
+from hdlf_server.app import create_app  # noqa: E402
+from hdlf_server.dependencies import (  # noqa: E402
+    get_client,
+    get_db_session,
+    get_inspection_results_repository,
+    get_reader,
+)
+from hdlf_server.reader import InspectionReader  # noqa: E402
+
+# pylint: enable=wrong-import-position,wrong-import-order
 
 
 @dataclass
 class FakeFile:
+    """One entry in the FakeHdlfClient in-memory filesystem."""
+
     content: bytes
     is_directory: bool = False
     modification_time: int = 0
@@ -46,11 +72,13 @@ class FakeHdlfClient:
     """
 
     def __init__(self, files: dict[str, bytes] | None = None):
+        """Initialise with an optional pre-populated dict of path → bytes."""
         self.files: dict[str, FakeFile] = {}
         for path, content in (files or {}).items():
             self.files[path.lstrip("/")] = FakeFile(content=content)
 
     def put(self, path: str, content: bytes | str | dict | list) -> None:
+        """Write a file into the fake filesystem, encoding as needed."""
         if isinstance(content, (dict, list)):
             data = json.dumps(content).encode()
         elif isinstance(content, str):
@@ -62,6 +90,7 @@ def put(self, path: str, content: bytes | str | dict | list) -> None:
     # ── HdlfClient methods exercised by the reader ─────────────────────────
 
     async def exists(self, path: str) -> bool:
+        """Return True if the path is a file or a directory prefix."""
         clean = path.lstrip("/")
         if clean in self.files:
             return True
@@ -69,35 +98,34 @@ async def exists(self, path: str) -> bool:
         return any(p.startswith(clean + "/") for p in self.files)
 
     async def get_object(self, path: str) -> bytes:
+        """Return raw bytes for a file; raise FileNotFoundError if absent."""
         clean = path.lstrip("/")
         if clean not in self.files:
             raise FileNotFoundError(f"FakeHdlfClient: {path}")
         return self.files[clean].content
 
     async def get_object_parsed(self, path: str) -> dict:
+        """Return parsed JSON dict for a file; raise ValueError if not JSON."""
         body = await self.get_object(path)
         try:
             parsed = json.loads(body)
         except json.JSONDecodeError as exc:
             raise ValueError(f"FakeHdlfClient: {path} not JSON: {exc}") from exc
         if not isinstance(parsed, dict):
-            raise ValueError(
-                f"FakeHdlfClient: {path} not JSON object (got {type(parsed).__name__})"
-            )
+            raise ValueError(f"FakeHdlfClient: {path} not JSON object (got {type(parsed).__name__})")
         return parsed
 
     async def list_dir(self, path: str) -> list:
+        """Return FileStatus entries for direct children of the given path."""
         clean = path.lstrip("/").rstrip("/")
-        prefix = "" if clean == "" else clean + "/"
+        prefix = "" if not clean else clean + "/"
         seen_dirs: set[str] = set()
         results = []
-        # Local FileStatus shim — must mirror HdlfClient.FileStatus's attributes.
-        from fl_shared.hdlf_client.client import FileStatus
 
         for fpath, ff in self.files.items():
             if not fpath.startswith(prefix):
                 continue
-            tail = fpath[len(prefix):]
+            tail = fpath[len(prefix) :]
             if "/" in tail:
                 child = tail.split("/", 1)[0]
                 if child not in seen_dirs:
@@ -121,9 +149,8 @@ async def list_dir(self, path: str) -> list:
                 )
         return results
 
-    async def iter_object(
-        self, path: str, chunk_size: int = 1024
-    ) -> AsyncIterator[bytes]:
+    async def iter_object(self, path: str, chunk_size: int = 1024) -> AsyncIterator[bytes]:
+        """Yield chunks of a file's content; raise FileNotFoundError if absent."""
         clean = path.lstrip("/")
         if clean not in self.files:
             raise FileNotFoundError(f"FakeHdlfClient: {path}")
@@ -131,9 +158,26 @@ async def iter_object(
         for i in range(0, len(body), chunk_size):
             yield body[i : i + chunk_size]
 
+    # ── HdlfClient methods exercised by write paths ────────────────────────
+
+    async def put_object_atomic(self, path: str, data: bytes) -> None:
+        """Mirror HdlfClient.put_object_atomic — atomic overwrite, no-tmp shim.
+
+        The real HDLF backend stages to ``<path>.tmp`` and renames; we
+        skip the tmp step in tests because the repository code doesn't
+        observe the intermediate state and the fake doesn't need to
+        model atomicity.
+        """
+        self.files[path.lstrip("/")] = FakeFile(content=data)
+
+    async def delete_object(self, path: str) -> None:
+        """Mirror HdlfClient.delete_object — silent no-op when the file is absent."""
+        self.files.pop(path.lstrip("/"), None)
+
 
 @pytest.fixture
 def fake_hdlf_client() -> FakeHdlfClient:
+    """Return a fresh empty FakeHdlfClient for each test."""
     return FakeHdlfClient()
 
 
@@ -144,21 +188,39 @@ async def client(fake_hdlf_client: FakeHdlfClient) -> AsyncIterator[AsyncClient]
     The HdlfClient lifespan is bypassed: we override `get_reader` and
     `get_client` to return an `InspectionReader` wrapping the fake. The
     real HdlfClient never opens.
-    """
-    # Import *after* env vars are set at module import time.
-    from hdlf_server.app import create_app
-    from hdlf_server.dependencies import get_client, get_reader
-    from hdlf_server.reader import InspectionReader
 
+    The write router's dependencies are overridden too so the same
+    `FakeHdlfClient` serves both read and write tests.  The
+    inspection-results repository is built via
+    `make_inspection_results_repository_from_client` over the fake.  A
+    default `get_db_session` override yields `None` — write tests that
+    need a real session must override this themselves (see
+    `test_handler_results_router.py`).
+    """
     app = create_app()
     # Skip lifespan startup — it would try to open a real HdlfClient.
     # ASGITransport supports `lifespan="off"` via context manager parameter.
     reader = InspectionReader(fake_hdlf_client)  # type: ignore[arg-type]
+    repository = make_inspection_results_repository_from_client(fake_hdlf_client)  # type: ignore[arg-type]
     app.dependency_overrides[get_reader] = lambda: reader
     app.dependency_overrides[get_client] = lambda: fake_hdlf_client
+    app.dependency_overrides[get_inspection_results_repository] = lambda: repository
+
+    # Default DB session override yields None — write tests that need a
+    # session override this themselves.  We still install a stub so the
+    # endpoint signature resolves; the lean-PUT path that touches it
+    # will fail noisily if the test forgot to override.
+    async def _no_db_session() -> AsyncIterator[AsyncSession]:  # pragma: no cover
+        yield None  # type: ignore[misc]
+
+    app.dependency_overrides[get_db_session] = _no_db_session
 
     transport = ASGITransport(app=app)
     async with AsyncClient(transport=transport, base_url="http://testserver") as c:
+        # Expose the app on the client so individual write tests can
+        # patch their own DB-session override without re-creating the
+        # whole fixture.
+        c.app = app  # type: ignore[attr-defined]
         yield c
 
     app.dependency_overrides.clear()
diff --git a/tests/hdlf_server/test_handler_results_router.py b/tests/hdlf_server/test_handler_results_router.py
new file mode 100644
index 00000000..d5b97dce
--- /dev/null
+++ b/tests/hdlf_server/test_handler_results_router.py
@@ -0,0 +1,556 @@
+"""Integration tests for the hdlf_server write router (handler_results_router).
+
+Exercises ``PUT /api/v1/inspection/{inspection_id}/handler-results/{fault_id}``
+end-to-end:
+
+* Happy path with full body — 204, no DB lookup.
+* Lean PUTs with DB-resolved defaults — 204, body wins over DB.
+* Lean PUTs with no scheduled execution — 400.
+* Validation failures at the perimeter (UUID, fault_id) and in the
+  request body — 400 / 422.
+* Repository-side failure translations — 502 / 500.
+* DB retry behaviour — transparent retry succeeds; exhausted budget → 503;
+  non-transient errors → 500 without retry.
+"""
+
+from __future__ import annotations
+
+import json
+import uuid
+from collections.abc import AsyncIterator
+from contextlib import asynccontextmanager
+from datetime import datetime, timezone
+from typing import Any
+
+import pytest
+import pytest_asyncio
+import sqlalchemy.exc
+import tenacity
+from fastapi import FastAPI
+from httpx import AsyncClient
+from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
+
+import fl_control_plane.handler_orchestrator.defaults_resolver as _defaults_resolver
+from fl_control_plane.database import FaultHandler, HandlerExecution, Inspection
+from fl_control_plane.inspection_results_repository import (
+    InspectionResultsConfigurationError,
+    InspectionResultsTransientError,
+)
+from hdlf_server.dependencies import get_db_session, get_inspection_results_repository
+from tests.hdlf_server.conftest import FakeHdlfClient
+
+UUID = "11111111-1111-1111-1111-111111111111"
+
+
+# ── Fixtures: DB rows + session override ────────────────────────────────────
+
+
+@pytest_asyncio.fixture
+async def db_session_factory(
+    test_session_factory: async_sessionmaker[AsyncSession],
+) -> async_sessionmaker[AsyncSession]:
+    """Re-expose the project-level test session factory under a local name."""
+    return test_session_factory
+
+
+def _seed_handler_execution(  # pylint: disable=too-many-arguments
+    session: AsyncSession,
+    *,
+    inspection_id: str,
+    fault_id: str,
+    scope: str,
+    default_output_description: str | None,
+    created_at: datetime | None = None,
+) -> None:
+    """Insert a fault_handlers + inspection + handler_executions trio.
+
+    Synchronously builds ORM objects and adds them to ``session``; the
+    caller is responsible for committing.
+    """
+    handler_id = str(uuid.uuid4())
+    inspection_row = Inspection(
+        id=inspection_id,
+        status="IN_PROGRESS",
+        pipeline_url="https://ci.example/job/x/1/",
+    )
+    handler = FaultHandler(
+        id=handler_id,
+        cr_id=f"test/{fault_id}",
+        cr_name=fault_id,
+        cr_namespace="fl-system",
+        fault_id=fault_id,
+        execution_type="agent_task",
+        strategy=scope,
+        ci_systems=None,
+        repo_patterns=None,
+        trigger_scope="all",
+        merge_target_branch=None,
+        spec_json="{}",
+        default_output_description=default_output_description,
+        resource_version="v1",
+        is_active=True,
+        registered_at=datetime.now(timezone.utc),
+    )
+    execution = HandlerExecution(
+        id=str(uuid.uuid4()),
+        inspection_id=inspection_id,
+        fault_handler_id=handler_id,
+        fault_id=fault_id,
+        status="planned",
+        created_at=created_at or datetime.now(timezone.utc),
+    )
+    session.add(inspection_row)
+    session.add(handler)
+    session.add(execution)
+
+
+@pytest_asyncio.fixture
+async def client_with_db(
+    client: AsyncClient,
+    db_session_factory: async_sessionmaker[AsyncSession],
+) -> AsyncIterator[AsyncClient]:
+    """Like the ``client`` fixture, but with a real DB session override.
+
+    Lean-PUT tests need to query the in-memory SQLite from ``conftest.py``;
+    the default ``client`` fixture wires a no-op session that yields
+    ``None``.  We override ``get_db_session`` here to yield a real session.
+    """
+
+    async def _real_db_session() -> AsyncIterator[AsyncSession]:
+        async with db_session_factory() as session:
+            yield session
+
+    client.app.dependency_overrides[get_db_session] = _real_db_session  # type: ignore[attr-defined]
+    try:
+        yield client
+    finally:
+        # No need to restore — outer ``client`` fixture clears overrides.
+        pass
+
+
+# ── Happy paths ─────────────────────────────────────────────────────────────
+
+
+@pytest.mark.asyncio
+async def test_put_handler_result_full_body_returns_204(client: AsyncClient, fake_hdlf_client: FakeHdlfClient) -> None:
+    """A full-body PUT writes result.json, description, metadata, and (here) skips the DB."""
+    body: dict[str, Any] = {
+        "result_json": {"issues": 3},
+        "output_description": "3 issues found",
+        "scope": "pipeline_scoped",
+        "addressed_stages": None,
+        "code_changes": None,
+    }
+    resp = await client.put(f"/api/v1/inspection/{UUID}/handler-results/sonarqube", json=body)
+    assert resp.status_code == 204
+    # The four-file write left these in the FakeHdlfClient's filesystem.
+    files = fake_hdlf_client.files
+    base = f"{UUID}/handler_results/sonarqube"
+    assert f"{base}/result.json" in files
+    assert f"{base}/result_description.md" in files
+    assert f"{base}/handler_metadata.json" in files
+    assert f"{base}/code_changes.diff" not in files
+
+
+@pytest.mark.asyncio
+async def test_put_handler_result_strict_put_removes_existing_diff(
+    client: AsyncClient, fake_hdlf_client: FakeHdlfClient
+) -> None:
+    """A PUT with code_changes=null wipes any pre-existing diff for the same fault."""
+    base = f"{UUID}/handler_results/sonarqube"
+    fake_hdlf_client.put(f"{base}/code_changes.diff", b"--- old diff")
+
+    body: dict[str, Any] = {
+        "result_json": {},
+        "output_description": "",
+        "scope": "pipeline_scoped",
+    }
+    resp = await client.put(f"/api/v1/inspection/{UUID}/handler-results/sonarqube", json=body)
+    assert resp.status_code == 204
+    assert f"{base}/code_changes.diff" not in fake_hdlf_client.files
+
+
+# ── DB-fallback path ────────────────────────────────────────────────────────
+
+
+@pytest.mark.asyncio
+async def test_lean_put_resolves_scope_and_description_from_db(
+    client_with_db: AsyncClient,
+    db_session_factory: async_sessionmaker[AsyncSession],
+    fake_hdlf_client: FakeHdlfClient,
+) -> None:
+    """A lean body fills missing scope + description from handler_executions ⋈ fault_handlers."""
+    async with db_session_factory() as session:
+        _seed_handler_execution(
+            session,
+            inspection_id=UUID,
+            fault_id="sonarqube",
+            scope="stage_scoped",
+            default_output_description="SonarQube analysis completed.",
+        )
+        await session.commit()
+
+    body: dict[str, Any] = {
+        "result_json": {"finding": "missing FROM"},
+        "addressed_stages": ["build"],
+    }
+    resp = await client_with_db.put(f"/api/v1/inspection/{UUID}/handler-results/sonarqube", json=body)
+    assert resp.status_code == 204
+
+    base = f"{UUID}/handler_results/sonarqube"
+    meta = json.loads(fake_hdlf_client.files[f"{base}/handler_metadata.json"].content)
+    assert meta["scope"] == "stage_scoped"
+    assert meta["addressed_stages"] == ["build"]
+    assert fake_hdlf_client.files[f"{base}/result_description.md"].content == b"SonarQube analysis completed."
+
+
+@pytest.mark.asyncio
+async def test_lean_put_body_value_wins_over_db_default(
+    client_with_db: AsyncClient,
+    db_session_factory: async_sessionmaker[AsyncSession],
+    fake_hdlf_client: FakeHdlfClient,
+) -> None:
+    """When the body provides output_description, the DB's default is ignored."""
+    async with db_session_factory() as session:
+        _seed_handler_execution(
+            session,
+            inspection_id=UUID,
+            fault_id="sonarqube",
+            scope="stage_scoped",
+            default_output_description="static description",
+        )
+        await session.commit()
+
+    body: dict[str, Any] = {
+        "result_json": {},
+        "output_description": "dynamic per-run description",
+        # scope omitted — should fall back to DB
+    }
+    resp = await client_with_db.put(f"/api/v1/inspection/{UUID}/handler-results/sonarqube", json=body)
+    assert resp.status_code == 204
+
+    base = f"{UUID}/handler_results/sonarqube"
+    assert fake_hdlf_client.files[f"{base}/result_description.md"].content == b"dynamic per-run description"
+    meta = json.loads(fake_hdlf_client.files[f"{base}/handler_metadata.json"].content)
+    assert meta["scope"] == "stage_scoped"  # from DB
+
+
+@pytest.mark.asyncio
+async def test_lean_put_returns_400_when_no_handler_execution_row(
+    client_with_db: AsyncClient, fake_hdlf_client: FakeHdlfClient
+) -> None:
+    """A lean PUT for a fault that was never scheduled returns 400 and skips the write."""
+    body: dict[str, Any] = {
+        "result_json": {},
+        # output_description and scope both omitted
+    }
+    resp = await client_with_db.put(f"/api/v1/inspection/{UUID}/handler-results/never-scheduled", json=body)
+    assert resp.status_code == 400
+    # The repository was never reached — FakeHdlfClient's filesystem is empty.
+    base = f"{UUID}/handler_results/never-scheduled"
+    assert f"{base}/result.json" not in fake_hdlf_client.files
+
+
+@pytest.mark.asyncio
+async def test_full_body_put_bypasses_db(client_with_db: AsyncClient) -> None:
+    """A full-body PUT succeeds with 204 even when no handler_executions row exists."""
+    body: dict[str, Any] = {
+        "result_json": {},
+        "output_description": "x",
+        "scope": "pipeline_scoped",
+    }
+    resp = await client_with_db.put(f"/api/v1/inspection/{UUID}/handler-results/some-fault", json=body)
+    assert resp.status_code == 204
+
+
+@pytest.mark.asyncio
+async def test_lean_put_writes_none_when_db_default_is_null(
+    client_with_db: AsyncClient,
+    db_session_factory: async_sessionmaker[AsyncSession],
+    fake_hdlf_client: FakeHdlfClient,
+) -> None:
+    """When the joined FaultHandler.default_output_description is NULL, description is None."""
+    async with db_session_factory() as session:
+        _seed_handler_execution(
+            session,
+            inspection_id=UUID,
+            fault_id="no-default",
+            scope="pipeline_scoped",
+            default_output_description=None,
+        )
+        await session.commit()
+
+    body: dict[str, Any] = {"result_json": {"ok": True}}
+    resp = await client_with_db.put(f"/api/v1/inspection/{UUID}/handler-results/no-default", json=body)
+    assert resp.status_code == 204
+
+    base = f"{UUID}/handler_results/no-default"
+    # description file written as zero bytes
+    assert fake_hdlf_client.files[f"{base}/result_description.md"].content == b""
+
+
+# ── Validation paths ────────────────────────────────────────────────────────
+
+
+@pytest.mark.asyncio
+async def test_put_handler_result_traversal_fault_id_returns_400(
+    client: AsyncClient, fake_hdlf_client: FakeHdlfClient
+) -> None:
+    """fault_id='..' is rejected as 400 before the repository is touched.
+
+    The literal ``..`` is rewritten by httpx (and any compliant URL
+    library) to climb the path, so we send the percent-encoded form
+    ``%2E%2E`` — Starlette decodes that once to ``..``, which the
+    perimeter allowlist rejects.
+    """
+    body = {"result_json": {}, "output_description": "x", "scope": "pipeline_scoped"}
+    resp = await client.put(f"/api/v1/inspection/{UUID}/handler-results/%2E%2E", json=body)
+    assert resp.status_code == 400
+    # No files written.
+    assert not any(p.startswith(f"{UUID}/handler_results") for p in fake_hdlf_client.files)
+
+
+@pytest.mark.asyncio
+async def test_put_handler_result_percent_encoded_slash_returns_400(client: AsyncClient) -> None:
+    """fault_id='foo%2Fbar' is rejected at the perimeter (400 or 404 — both mean no write).
+
+    Starlette percent-decodes ``%2F`` before route matching, so the URL
+    effectively becomes ``handler-results/foo/bar`` which no longer
+    matches the single-segment ``{fault_id}`` pattern.  The result is
+    HTTP 404 from the router rather than 400 from our allowlist — both
+    are valid "rejected at the perimeter" answers and the practical
+    security contract (repository never called) is satisfied either way.
+    """
+    body = {"result_json": {}, "output_description": "x", "scope": "pipeline_scoped"}
+    resp = await client.put(f"/api/v1/inspection/{UUID}/handler-results/foo%2Fbar", json=body)
+    assert resp.status_code in (400, 404)
+
+
+@pytest.mark.asyncio
+async def test_put_handler_result_double_encoded_traversal_returns_400(client: AsyncClient) -> None:
+    """fault_id='%252E%252E' decodes to '%2E%2E' then to '..' — caught by the fixed-point loop."""
+    body = {"result_json": {}, "output_description": "x", "scope": "pipeline_scoped"}
+    resp = await client.put(f"/api/v1/inspection/{UUID}/handler-results/%252E%252E", json=body)
+    assert resp.status_code == 400
+
+
+@pytest.mark.asyncio
+async def test_put_handler_result_missing_result_json_returns_422(client: AsyncClient) -> None:
+    """Body without the required result_json field surfaces as 422 from Pydantic."""
+    body = {"output_description": "x", "scope": "pipeline_scoped"}
+    resp = await client.put(f"/api/v1/inspection/{UUID}/handler-results/sonarqube", json=body)
+    assert resp.status_code == 422
+
+
+@pytest.mark.asyncio
+async def test_put_handler_result_invalid_scope_returns_422(client: AsyncClient) -> None:
+    """Body with scope='global' fails Pydantic Literal validation as 422."""
+    body = {
+        "result_json": {},
+        "output_description": "x",
+        "scope": "global",
+    }
+    resp = await client.put(f"/api/v1/inspection/{UUID}/handler-results/sonarqube", json=body)
+    assert resp.status_code == 422
+
+
+@pytest.mark.asyncio
+async def test_put_handler_result_non_uuid_inspection_returns_422(client: AsyncClient) -> None:
+    """Non-UUID4 inspection_id surfaces as 422 from FastAPI's Pydantic validation."""
+    body = {"result_json": {}, "output_description": "x", "scope": "pipeline_scoped"}
+    resp = await client.put("/api/v1/inspection/not-a-uuid/handler-results/sonarqube", json=body)
+    assert resp.status_code == 422
+
+
+# ── Repository-side failure translation ─────────────────────────────────────
+
+
+@pytest.mark.asyncio
+async def test_put_handler_result_transient_repo_failure_returns_502(client: AsyncClient) -> None:
+    """An InspectionResultsTransientError from the repository surfaces as 502."""
+
+    class _FlakyRepo:
+        async def write_handler_result(self, **_kwargs: Any) -> None:
+            """Always raise InspectionResultsTransientError."""
+            raise InspectionResultsTransientError("HDLF unreachable")
+
+    client.app.dependency_overrides[  # type: ignore[attr-defined]
+        get_inspection_results_repository
+    ] = _FlakyRepo
+
+    body: dict[str, Any] = {"result_json": {}, "output_description": "x", "scope": "pipeline_scoped"}
+    resp = await client.put(f"/api/v1/inspection/{UUID}/handler-results/sonarqube", json=body)
+    assert resp.status_code == 502
+
+
+@pytest.mark.asyncio
+async def test_put_handler_result_configuration_error_returns_500(client: AsyncClient) -> None:
+    """An InspectionResultsConfigurationError from the repository surfaces as 500."""
+
+    class _MisconfiguredRepo:
+        async def write_handler_result(self, **_kwargs: Any) -> None:
+            """Always raise InspectionResultsConfigurationError."""
+            raise InspectionResultsConfigurationError("cert missing")
+
+    client.app.dependency_overrides[  # type: ignore[attr-defined]
+        get_inspection_results_repository
+    ] = _MisconfiguredRepo
+
+    body: dict[str, Any] = {"result_json": {}, "output_description": "x", "scope": "pipeline_scoped"}
+    resp = await client.put(f"/api/v1/inspection/{UUID}/handler-results/sonarqube", json=body)
+    assert resp.status_code == 500
+
+
+# ── DB retry behaviour ─────────────────────────────────────────────────────
+
+
+@pytest.fixture(autouse=True)
+def _patch_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
+    """Replace exponential backoff with no-wait so retry tests run instantly."""
+    monkeypatch.setattr(_defaults_resolver, "_RETRY_WAIT", tenacity.wait_none())
+
+
+class _CountingFlakySession:
+    """AsyncSession stand-in that raises OperationalError N times then delegates.
+
+    Tests the tenacity retry wrapper end-to-end without touching the real
+    DB.  Wraps a real session built from the in-memory engine so the
+    eventual successful execute returns realistic results.
+
+    The production retry loop calls ``session.rollback()`` after each
+    transient error to reset the session's transaction state.  This stub
+    implements a no-op ``rollback()`` so that call is accepted without
+    affecting the inner session (which was never used during the failure
+    phase and remains in a clean state).
+    """
+
+    def __init__(self, inner: AsyncSession, fail_times: int):
+        self._inner = inner
+        self._fail_times = fail_times
+        self.call_count = 0
+
+    async def execute(self, *args: Any, **kwargs: Any) -> Any:
+        """Fail _fail_times times then delegate to the real session."""
+        self.call_count += 1
+        if self._fail_times > 0:
+            self._fail_times -= 1
+            raise sqlalchemy.exc.OperationalError("flaky", None, Exception("flaky"))
+        return await self._inner.execute(*args, **kwargs)
+
+    async def rollback(self) -> None:
+        """No-op — inner session was never used on the failure path."""
+
+    async def __aenter__(self) -> _CountingFlakySession:
+        return self
+
+    async def __aexit__(self, *_args: Any) -> None:
+        return None
+
+
+@asynccontextmanager
+async def _override_with_flaky_session(
+    app: FastAPI,
+    db_session_factory: async_sessionmaker[AsyncSession],
+    fail_times: int,
+    exception: type[Exception] | None = None,
+) -> AsyncIterator[dict[str, _CountingFlakySession]]:
+    """Override get_db_session to yield a session that fails N times then succeeds.
+
+    Yields the counting wrapper so tests can assert on call_count.
+    """
+    holder: dict[str, _CountingFlakySession] = {}
+
+    async def _flaky() -> AsyncIterator[_CountingFlakySession]:
+        async with db_session_factory() as inner:
+            if exception is not None:
+                # Bespoke wrapper that raises a specific exception type once.
+                # SQLAlchemy DBAPIError subclasses require (statement,
+                # params, orig); we synthesise plausible values.
+                class _BadSession:
+                    def __init__(self) -> None:
+                        self.call_count = 0
+
+                    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
+                        """Always raise the configured exception type."""
+                        self.call_count += 1
+                        raise exception("synthetic", None, Exception("bad"))  # type: ignore[misc]
+
+                    async def rollback(self) -> None:
+                        """No-op."""
+
+                holder["session"] = _BadSession()  # type: ignore[assignment]
+                yield holder["session"]
+                return
+
+            wrapped = _CountingFlakySession(inner, fail_times)
+            holder["session"] = wrapped
+            yield wrapped
+
+    app.dependency_overrides[get_db_session] = _flaky
+    try:
+        yield holder
+    finally:
+        pass
+
+
+@pytest.mark.asyncio
+async def test_lean_put_with_transient_db_errors_retries_and_succeeds(
+    client: AsyncClient,
+    db_session_factory: async_sessionmaker[AsyncSession],
+) -> None:
+    """Two OperationalErrors followed by a successful query yields 204."""
+    async with db_session_factory() as session:
+        _seed_handler_execution(
+            session,
+            inspection_id=UUID,
+            fault_id="sonarqube",
+            scope="pipeline_scoped",
+            default_output_description="d",
+        )
+        await session.commit()
+
+    async with _override_with_flaky_session(
+        client.app,  # type: ignore[attr-defined]
+        db_session_factory,
+        fail_times=2,
+    ) as holder:
+        body: dict[str, Any] = {"result_json": {}}
+        resp = await client.put(f"/api/v1/inspection/{UUID}/handler-results/sonarqube", json=body)
+        assert resp.status_code == 204
+        # 2 failures + 1 success = 3 execute calls
+        assert holder["session"].call_count == 3
+
+
+@pytest.mark.asyncio
+async def test_lean_put_with_exhausted_retry_budget_returns_503(
+    client: AsyncClient,
+    db_session_factory: async_sessionmaker[AsyncSession],
+) -> None:
+    """Five consecutive OperationalErrors exhaust the retry budget → 503."""
+    async with _override_with_flaky_session(
+        client.app,  # type: ignore[attr-defined]
+        db_session_factory,
+        fail_times=10,  # > stop_after_attempt(5)
+    ):
+        body: dict[str, Any] = {"result_json": {}}
+        resp = await client.put(f"/api/v1/inspection/{UUID}/handler-results/sonarqube", json=body)
+        assert resp.status_code == 503
+
+
+@pytest.mark.asyncio
+async def test_lean_put_with_non_transient_db_error_returns_500(
+    client: AsyncClient,
+    db_session_factory: async_sessionmaker[AsyncSession],
+) -> None:
+    """ProgrammingError is not retried; surfaces as 500."""
+    async with _override_with_flaky_session(
+        client.app,  # type: ignore[attr-defined]
+        db_session_factory,
+        fail_times=0,
+        exception=sqlalchemy.exc.ProgrammingError,
+    ) as holder:
+        body: dict[str, Any] = {"result_json": {}}
+        resp = await client.put(f"/api/v1/inspection/{UUID}/handler-results/sonarqube", json=body)
+        assert resp.status_code == 500
+        # Only one attempt — non-transient errors are not retried.
+        assert holder["session"].call_count == 1
diff --git a/tests/mcp_servers/test_inspection_results_repository.py b/tests/mcp_servers/test_inspection_results_repository.py
index 4ffa1755..9e7ea209 100644
--- a/tests/mcp_servers/test_inspection_results_repository.py
+++ b/tests/mcp_servers/test_inspection_results_repository.py
@@ -1,6 +1,9 @@
 """Tests for HdlfInspectionResultsRepository read/write paths and exception wrapping."""
 
+from __future__ import annotations
+
 import json
+import re
 from unittest.mock import AsyncMock, MagicMock
 
 import pytest
@@ -9,7 +12,10 @@
     HandlerResultNotFoundError,
     InspectionResultsConfigurationError,
     InspectionResultsTransientError,
+    InspectionResultsValidationError,
     make_inspection_results_repository,
+    make_inspection_results_repository_from_client,
+    validate_fault_id,
 )
 from fl_control_plane.inspection_results_repository.inspection_results_repository_hdlf import (
     HdlfInspectionResultsRepository,
@@ -24,6 +30,7 @@ def _mock_hdlf_client() -> MagicMock:
     client.__aenter__ = AsyncMock(return_value=client)
     client.__aexit__ = AsyncMock(return_value=None)
     client.put_object_atomic = AsyncMock()
+    client.delete_object = AsyncMock()
     client.get_object = AsyncMock()
     client.list_dir = AsyncMock(return_value=[])
     client.exists = AsyncMock(return_value=True)
@@ -36,12 +43,12 @@ def _dir_entry(path: str) -> FileStatus:
 
 
 @pytest.fixture()
-def hdlf_client():
+def hdlf_client() -> MagicMock:
     """Provide a mock HdlfClient for each test."""
     return _mock_hdlf_client()
 
 
-async def test_write_handler_result_writes_all_files(hdlf_client):
+async def test_write_handler_result_writes_all_files(hdlf_client: MagicMock) -> None:
     """write_handler_result writes result.json, description, metadata, and no diff when code_changes is None."""
     written: dict[str, bytes] = {}
 
@@ -71,7 +78,7 @@ async def fake_put_atomic(path: str, data: bytes) -> None:
     assert f"{base}/code_changes.diff" not in written
 
 
-async def test_write_handler_result_writes_diff_when_provided(hdlf_client):
+async def test_write_handler_result_writes_diff_when_provided(hdlf_client: MagicMock) -> None:
     """write_handler_result writes code_changes.diff when code_changes is provided."""
     written: dict[str, bytes] = {}
 
@@ -94,7 +101,7 @@ async def fake_put_atomic(path: str, data: bytes) -> None:
     assert "insp-2/handler_results/lint-fix/code_changes.diff" in written
 
 
-async def test_write_handler_result_wraps_ioerror_as_transient(hdlf_client):
+async def test_write_handler_result_wraps_ioerror_as_transient(hdlf_client: MagicMock) -> None:
     """write_handler_result wraps HDLF IOError in InspectionResultsTransientError."""
     hdlf_client.put_object_atomic = AsyncMock(side_effect=IOError("connection reset"))
 
@@ -111,9 +118,9 @@ async def test_write_handler_result_wraps_ioerror_as_transient(hdlf_client):
             )
 
 
-async def test_list_handler_results_returns_completed_handlers(hdlf_client):
+async def test_list_handler_results_returns_completed_handlers(hdlf_client: MagicMock) -> None:
     """list_handler_results returns one entry per subfolder that has result.json."""
-    result_json = {"issues": []}
+    result_json: dict[str, object] = {"issues": []}
     metadata_json = {"scope": "stage_scoped", "addressed_stages": ["Build"]}
 
     hdlf_client.list_dir = AsyncMock(return_value=[_dir_entry("insp/handler_results/fault-a")])
@@ -143,7 +150,7 @@ async def fake_get_object(path: str) -> bytes:
     assert entry.has_code_changes is True
 
 
-async def test_list_handler_results_skips_folders_without_result_json(hdlf_client):
+async def test_list_handler_results_skips_folders_without_result_json(hdlf_client: MagicMock) -> None:
     """list_handler_results silently skips subfolders where result.json is absent."""
     hdlf_client.list_dir = AsyncMock(return_value=[_dir_entry("insp/handler_results/no-output")])
     hdlf_client.get_object = AsyncMock(side_effect=FileNotFoundError("no result.json"))
@@ -154,7 +161,7 @@ async def test_list_handler_results_skips_folders_without_result_json(hdlf_clien
     assert entries == []
 
 
-async def test_list_handler_results_empty_when_no_subfolders(hdlf_client):
+async def test_list_handler_results_empty_when_no_subfolders(hdlf_client: MagicMock) -> None:
     """list_handler_results returns empty list when handler_results/ has no subdirectories."""
     hdlf_client.list_dir = AsyncMock(return_value=[])
     hdlf_client.exists = AsyncMock(return_value=True)
@@ -165,7 +172,7 @@ async def test_list_handler_results_empty_when_no_subfolders(hdlf_client):
     assert entries == []
 
 
-async def test_list_handler_results_raises_when_inspection_folder_missing(hdlf_client):
+async def test_list_handler_results_raises_when_inspection_folder_missing(hdlf_client: MagicMock) -> None:
     """list_handler_results raises HandlerResultNotFoundError when the inspection folder does not exist."""
     hdlf_client.list_dir = AsyncMock(return_value=[])
     hdlf_client.exists = AsyncMock(return_value=False)
@@ -175,7 +182,7 @@ async def test_list_handler_results_raises_when_inspection_folder_missing(hdlf_c
             await repo.list_handler_results("nonexistent-uuid")
 
 
-async def test_list_handler_results_skips_one_failing_fault_when_others_succeed(hdlf_client):
+async def test_list_handler_results_skips_one_failing_fault_when_others_succeed(hdlf_client: MagicMock) -> None:
     """A single fault that raises IOError is skipped; healthy faults are returned."""
     good_json = {"ok": True}
     good_meta = {"scope": "pipeline_scoped", "addressed_stages": None}
@@ -208,7 +215,7 @@ async def fake_get_object(path: str) -> bytes:
     assert entries[0].fault_id == "good"
 
 
-async def test_list_handler_results_raises_when_every_handler_fails(hdlf_client):
+async def test_list_handler_results_raises_when_every_handler_fails(hdlf_client: MagicMock) -> None:
     """If every observed fault folder errors out, raise rather than return []."""
     hdlf_client.list_dir = AsyncMock(
         return_value=[
@@ -223,7 +230,29 @@ async def test_list_handler_results_raises_when_every_handler_fails(hdlf_client)
             await repo.list_handler_results("insp")
 
 
-async def test_list_handler_results_wraps_list_dir_ioerror(hdlf_client):
+async def test_list_handler_results_raises_on_mixed_transient_and_missing(hdlf_client: MagicMock) -> None:
+    """Mixed transient error + missing result.json with no successes raises rather than returns []."""
+    hdlf_client.list_dir = AsyncMock(
+        return_value=[
+            _dir_entry("insp/handler_results/a"),
+            _dir_entry("insp/handler_results/b"),
+            _dir_entry("insp/handler_results/c"),
+        ]
+    )
+
+    def _get_object_side_effect(path: str) -> bytes:
+        if "handler_results/c/" in path:
+            raise FileNotFoundError("no result.json")
+        raise IOError("storage down")
+
+    hdlf_client.get_object = AsyncMock(side_effect=_get_object_side_effect)
+
+    async with HdlfInspectionResultsRepository(hdlf_client) as repo:
+        with pytest.raises(InspectionResultsTransientError):
+            await repo.list_handler_results("insp")
+
+
+async def test_list_handler_results_wraps_list_dir_ioerror(hdlf_client: MagicMock) -> None:
     """list_dir failures surface as InspectionResultsTransientError."""
     hdlf_client.list_dir = AsyncMock(side_effect=IOError("unreachable"))
 
@@ -232,7 +261,7 @@ async def test_list_handler_results_wraps_list_dir_ioerror(hdlf_client):
             await repo.list_handler_results("insp")
 
 
-async def test_read_code_changes_returns_diff_content(hdlf_client):
+async def test_read_code_changes_returns_diff_content(hdlf_client: MagicMock) -> None:
     """read_code_changes returns a SuggestedCodeChanges with the diff for a handler that produced changes."""
     diff = "--- a/foo.py\n+++ b/foo.py\n"
     hdlf_client.get_object = AsyncMock(return_value=diff.encode())
@@ -244,7 +273,7 @@ async def test_read_code_changes_returns_diff_content(hdlf_client):
     assert result.code_changes == diff
 
 
-async def test_read_code_changes_raises_not_found_when_missing(hdlf_client):
+async def test_read_code_changes_raises_not_found_when_missing(hdlf_client: MagicMock) -> None:
     """read_code_changes raises HandlerResultNotFoundError when diff does not exist."""
     hdlf_client.get_object = AsyncMock(side_effect=FileNotFoundError("no diff"))
 
@@ -253,7 +282,7 @@ async def test_read_code_changes_raises_not_found_when_missing(hdlf_client):
             await repo.read_code_changes("insp", "no-diff-handler")
 
 
-async def test_read_code_changes_wraps_ioerror_as_transient(hdlf_client):
+async def test_read_code_changes_wraps_ioerror_as_transient(hdlf_client: MagicMock) -> None:
     """read_code_changes wraps HDLF IOError in InspectionResultsTransientError."""
     hdlf_client.get_object = AsyncMock(side_effect=IOError("network"))
 
@@ -262,7 +291,7 @@ async def test_read_code_changes_wraps_ioerror_as_transient(hdlf_client):
             await repo.read_code_changes("insp", "fault")
 
 
-def test_make_inspection_results_repository_wraps_config_errors():
+def test_make_inspection_results_repository_wraps_config_errors() -> None:
     """make_inspection_results_repository wraps missing-cert errors as InspectionResultsConfigurationError."""
     params = HdlfConnectionParams(
         rest_api_host="https://hdlf.example.com",
@@ -278,7 +307,7 @@ def _file_entry(path: str) -> FileStatus:
     return FileStatus(path=path, length=0, modification_time=0, is_directory=False)
 
 
-async def test_list_gate_results_empty_when_analyzer_folder_empty(hdlf_client):
+async def test_list_gate_results_empty_when_analyzer_folder_empty(hdlf_client: MagicMock) -> None:
     """list_gate_results returns [] when the pipeline_analyzer/ folder has no files."""
     hdlf_client.list_dir = AsyncMock(return_value=[])
 
@@ -288,7 +317,7 @@ async def test_list_gate_results_empty_when_analyzer_folder_empty(hdlf_client):
     assert entries == []
 
 
-async def test_list_gate_results_pairs_description_and_json(hdlf_client):
+async def test_list_gate_results_pairs_description_and_json(hdlf_client: MagicMock) -> None:
     """list_gate_results emits one entry per description file, pairing with its JSON sibling."""
     hdlf_client.list_dir = AsyncMock(
         return_value=[
@@ -315,7 +344,7 @@ async def fake_get_object(path: str) -> bytes:
     assert entries[0].result_description == "Coverage is 80%"
 
 
-async def test_list_gate_results_emits_empty_result_when_json_missing(hdlf_client):
+async def test_list_gate_results_emits_empty_result_when_json_missing(hdlf_client: MagicMock) -> None:
     """A gate with only a description file appears with an empty result dict."""
     hdlf_client.list_dir = AsyncMock(return_value=[_file_entry("insp/pipeline_analyzer/lint_description.md")])
 
@@ -335,7 +364,7 @@ async def fake_get_object(path: str) -> bytes:
     assert entries[0].result_description == "Lint clean"
 
 
-async def test_list_gate_results_wraps_list_dir_ioerror(hdlf_client):
+async def test_list_gate_results_wraps_list_dir_ioerror(hdlf_client: MagicMock) -> None:
     """list_dir failures surface as InspectionResultsTransientError."""
     hdlf_client.list_dir = AsyncMock(side_effect=IOError("unreachable"))
 
@@ -344,7 +373,7 @@ async def test_list_gate_results_wraps_list_dir_ioerror(hdlf_client):
             await repo.list_gate_results("insp")
 
 
-async def test_list_gate_results_continues_when_gate_json_raises_ioerror(hdlf_client):
+async def test_list_gate_results_continues_when_gate_json_raises_ioerror(hdlf_client: MagicMock) -> None:
     """A transient IOError on a gate's JSON file yields an empty result for that gate instead of aborting."""
     hdlf_client.list_dir = AsyncMock(
         return_value=[
@@ -374,3 +403,206 @@ async def fake_get_object(path: str) -> bytes:
     assert coverage.result == {}  # IOError → empty result, not dropped
     lint = next(e for e in entries if e.gate_name == "lint")
     assert lint.result == {"pass": True}
+
+
+# ── fault_id validation ─────────────────────────────────────────────────────
+
+
+@pytest.mark.parametrize(
+    "bad_fault_id",
+    [
+        "",
+        "..",
+        "foo/bar",
+        "foo\\bar",
+        "foo\x00bar",
+    ],
+)
+def test_validate_fault_id_rejects(bad_fault_id: str) -> None:
+    """validate_fault_id rejects empty, '..', '/', '\\', and NUL-containing strings."""
+    with pytest.raises(InspectionResultsValidationError):
+        validate_fault_id(bad_fault_id)
+
+
+def test_validate_fault_id_accepts_well_formed() -> None:
+    """validate_fault_id accepts the standard handler-name shape."""
+    validate_fault_id("sonarqube-analysis")
+    validate_fault_id("foo_bar")
+    validate_fault_id("a.b.c")
+
+
+def test_router_allowlist_is_subset_of_repo_denylist() -> None:
+    """Every fault_id that passes the router allowlist also passes the repo denylist.
+
+    The router applies ^[A-Za-z0-9._-]+$ at the HTTP perimeter; the repo applies
+    a denylist as defence-in-depth for in-process callers.  This test encodes the
+    invariant that the two are never contradictory: a value the router admits must
+    not be rejected by the repo.  If either rule changes and the relationship
+    breaks, this test catches it.
+    """
+    _allowlist = re.compile(r"^[A-Za-z0-9._-]+$")
+    candidates = [
+        "sonarqube",
+        "sonarqube-analysis",
+        "foo_bar",
+        "a.b.c",
+        "A1",
+        "Z-9.x_y",
+        "a" * 64,
+    ]
+    for value in candidates:
+        assert _allowlist.match(value), f"{value!r} should match the allowlist"
+        validate_fault_id(value)  # must not raise
+
+
+@pytest.mark.parametrize(
+    "bad_fault_id",
+    [
+        "",
+        "..",
+        "foo/bar",
+        "foo\\bar",
+        "foo\x00bar",
+    ],
+)
+async def test_write_handler_result_rejects_bad_fault_id_before_touching_storage(
+    hdlf_client: MagicMock, bad_fault_id: str
+) -> None:
+    """write_handler_result raises InspectionResultsValidationError without invoking the client."""
+    async with HdlfInspectionResultsRepository(hdlf_client) as repo:
+        with pytest.raises(InspectionResultsValidationError):
+            await repo.write_handler_result(
+                inspection_id="insp",
+                fault_id=bad_fault_id,
+                result_json={},
+                output_description="x",
+                scope="pipeline_scoped",
+                addressed_stages=None,
+                code_changes=None,
+            )
+    hdlf_client.put_object_atomic.assert_not_called()
+    hdlf_client.delete_object.assert_not_called()
+
+
+# ── strict-PUT for code_changes ─────────────────────────────────────────────
+
+
+async def test_write_handler_result_strict_put_deletes_existing_diff_when_none(hdlf_client: MagicMock) -> None:
+    """When code_changes is None, write_handler_result deletes any pre-existing diff."""
+    async with HdlfInspectionResultsRepository(hdlf_client) as repo:
+        await repo.write_handler_result(
+            inspection_id="insp-1",
+            fault_id="f",
+            result_json={},
+            output_description="",
+            scope="pipeline_scoped",
+            addressed_stages=None,
+            code_changes=None,
+        )
+    # The delete is unconditional (HdlfClient.delete_object already
+    # treats 404 as a no-op), so we assert the call shape rather than
+    # pre-seeding state.
+    hdlf_client.delete_object.assert_awaited_once_with("insp-1/handler_results/f/code_changes.diff")
+
+
+async def test_write_handler_result_strict_put_no_diff_no_error_when_absent(hdlf_client: MagicMock) -> None:
+    """write_handler_result with code_changes=None against a fault without a prior diff succeeds."""
+    # delete_object is already an AsyncMock that returns None by default,
+    # mirroring the HdlfClient behaviour where 404 is success.
+    async with HdlfInspectionResultsRepository(hdlf_client) as repo:
+        await repo.write_handler_result(
+            inspection_id="insp-2",
+            fault_id="never-had-diff",
+            result_json={},
+            output_description="",
+            scope="pipeline_scoped",
+            addressed_stages=None,
+            code_changes=None,
+        )
+
+
+async def test_write_handler_result_wraps_delete_ioerror_as_transient(hdlf_client: MagicMock) -> None:
+    """An IOError from delete_object during strict-PUT surfaces as InspectionResultsTransientError."""
+    hdlf_client.delete_object = AsyncMock(side_effect=IOError("delete failed"))
+
+    async with HdlfInspectionResultsRepository(hdlf_client) as repo:
+        with pytest.raises(InspectionResultsTransientError):
+            await repo.write_handler_result(
+                inspection_id="insp",
+                fault_id="f",
+                result_json={},
+                output_description="",
+                scope="pipeline_scoped",
+                addressed_stages=None,
+                code_changes=None,
+            )
+
+
+# ── None-tolerance on write + read round-trip ───────────────────────────────
+
+
+async def test_write_handler_result_accepts_none_for_description_and_scope(hdlf_client: MagicMock) -> None:
+    """Both output_description=None and scope=None are written as zero bytes / JSON null."""
+    written: dict[str, bytes] = {}
+
+    async def fake_put_atomic(path: str, data: bytes) -> None:
+        written[path] = data
+
+    hdlf_client.put_object_atomic = fake_put_atomic
+
+    async with HdlfInspectionResultsRepository(hdlf_client) as repo:
+        await repo.write_handler_result(
+            inspection_id="insp",
+            fault_id="f",
+            result_json={"ok": True},
+            output_description=None,
+            scope=None,
+            addressed_stages=None,
+            code_changes=None,
+        )
+
+    base = "insp/handler_results/f"
+    assert written[f"{base}/result_description.md"] == b""
+    meta = json.loads(written[f"{base}/handler_metadata.json"])
+    assert meta["scope"] is None
+    assert meta["addressed_stages"] is None
+
+
+async def test_list_handler_results_tolerates_none_scope_and_empty_description(hdlf_client: MagicMock) -> None:
+    """list_handler_results round-trips an entry whose metadata.scope is null and description is empty."""
+    result_json = {"ok": True}
+    metadata_json = {"scope": None, "addressed_stages": None}
+
+    hdlf_client.list_dir = AsyncMock(return_value=[_dir_entry("insp/handler_results/f")])
+
+    async def fake_get_object(path: str) -> bytes:
+        if path.endswith("/f/result.json"):
+            return json.dumps(result_json).encode()
+        if path.endswith("/f/result_description.md"):
+            return b""
+        if path.endswith("/f/handler_metadata.json"):
+            return json.dumps(metadata_json).encode()
+        raise FileNotFoundError(path)
+
+    hdlf_client.get_object = fake_get_object
+    hdlf_client.exists = AsyncMock(return_value=False)
+
+    async with HdlfInspectionResultsRepository(hdlf_client) as repo:
+        entries = await repo.list_handler_results("insp")
+
+    assert len(entries) == 1
+    assert entries[0].fault_id == "f"
+    assert entries[0].scope is None
+    assert entries[0].output_description is None
+
+
+# ── make_inspection_results_repository_from_client ──────────────────────────
+
+
+def test_make_repository_from_client_returns_repo_sharing_supplied_client() -> None:
+    """The factory does not open a new HdlfClient — it wraps the one supplied."""
+    fake_client = _mock_hdlf_client()
+    repo = make_inspection_results_repository_from_client(fake_client)
+    assert isinstance(repo, HdlfInspectionResultsRepository)
+    # pylint: disable=protected-access
+    assert repo._client is fake_client

```
