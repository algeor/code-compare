# 8adfeceaeb2c0745

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/29
Suggested label: 50%
File overlap: 0.0
Changed-line overlap: 0.7692

## Suggested diff
```diff
--- a/fl_control_plane/hdlf_client/client.py
+++ b/fl_control_plane/hdlf_client/client.py
@@
+resp: aiohttp.ClientResponse | None = None
+        try:
+            async for attempt in AsyncRetrying(
+                retry=retry_if_exception_type(
+                    (_HdlfTransientError, aiohttp.ClientError, asyncio.TimeoutError)
+                ),
+                stop=stop_after_attempt(self._max_retries),
+                wait=wait_combine(
+                    wait_exception(_retry_after_wait),
+                    wait_exponential(multiplier=1.0, min=1.0, max=60.0),
+                ),
+                reraise=True,
+            ):
+                with attempt:
+                    resp = await _open()
+        except RetryError as exc:
+            # reraise=True surfaces the underlying exception, but pin to IOError
+            # in case tenacity ever wraps it.
+            raise IOError(f"iter_object {path} failed after retries") from exc
+
+        if resp is None:
+            raise IOError(f"iter_object {path} failed after retries")
+
+        # Phase 2: stream — release the response when the generator is closed
+        # (consumer break, or natural completion).
+        try:
+            async for chunk in resp.content.iter_chunked(chunk_size):
+                yield chunk
+        finally:
+            resp.release()
```

## Landed PR diff
```diff
diff --git a/Dockerfile b/Dockerfile
index 8a4caf2a..5427372c 100644
--- a/Dockerfile
+++ b/Dockerfile
@@ -8,6 +8,8 @@ WORKDIR /home/app/build
 
 COPY --chown=app:app pyproject.toml ./
 COPY --chown=app:app fl_control_plane/ ./fl_control_plane/
+COPY --chown=app:app hdlf_server/ ./hdlf_server/
+COPY --chown=app:app fl_shared/ ./fl_shared/
 
 RUN pip install --no-cache-dir hatchling \
     && hatchling build -t wheel -d /home/app/build/wheels
diff --git a/chart/templates/deployment-hdlf-server.yaml b/chart/templates/deployment-hdlf-server.yaml
new file mode 100644
index 00000000..d80dd15e
--- /dev/null
+++ b/chart/templates/deployment-hdlf-server.yaml
@@ -0,0 +1,85 @@
+{{- if .Values.hdlfServer.enabled -}}
+apiVersion: apps/v1
+kind: Deployment
+metadata:
+  name: {{ .Chart.Name }}-hdlf-server
+  labels:
+    app: {{ .Chart.Name }}-hdlf-server
+    pipeline-fl/component: hdlf-server
+spec:
+  replicas: {{ .Values.hdlfServer.replicaCount }}
+  revisionHistoryLimit: 3
+  selector:
+    matchLabels:
+      app: {{ .Chart.Name }}-hdlf-server
+  template:
+    metadata:
+      labels:
+        app: {{ .Chart.Name }}-hdlf-server
+        pipeline-fl/component: hdlf-server
+    spec:
+      {{- if .Values.imagePullSecret.name }}
+      imagePullSecrets:
+        - name: {{ .Values.imagePullSecret.name }}
+      {{- end }}
+      containers:
+        - name: hdlf-server
+          image: "{{ required "image.repository must be set" .Values.image.repository }}:{{ required "image.tag must be set" .Values.image.tag }}"
+          # Reuse the existing image; override the entrypoint to start the
+          # hdlf_server FastAPI app instead of the Ingestion API.
+          command:
+            - uvicorn
+            - hdlf_server.app:app
+            - --host
+            - 0.0.0.0
+            - --port
+            - "8000"
+          ports:
+            - containerPort: 8000
+          env:
+            - name: HDLF_REST_API_HOST
+              value: {{ required "hdlfServer.hdlf.restApiHost must be set" .Values.hdlfServer.hdlf.restApiHost | quote }}
+            - name: HDLF_CONTAINER_ID
+              value: {{ required "hdlfServer.hdlf.containerId must be set" .Values.hdlfServer.hdlf.containerId | quote }}
+            - name: HDLF_CERT_DIR
+              value: /home/app/app/certs
+            - name: AUTH_DISABLED
+              value: "true"
+            - name: FAULT_LOCALIZATION_ENV
+              value: {{ .Values.hdlfServer.faultLocalizationEnv | default "prod" | quote }}
+            - name: VAULT_CREDENTIALS
+              value: "unused"
+          volumeMounts:
+            - name: hdlf-tls
+              mountPath: /home/app/app/certs
+              readOnly: true
+          # startupProbe gates liveness/readiness during cold start. The
+          # first /readyz call performs a full mTLS handshake against
+          # HDLF (port 443, real network), which a 5 s initialDelaySeconds
+          # cannot reliably cover — failures tripped Helm's `--wait
+          # --atomic` and rolled back the deploy. With a startupProbe the
+          # pod has up to 60 s (12 × 5 s) to come ready; afterwards the
+          # liveness/readiness probes resume at their normal cadence.
+          startupProbe:
+            httpGet:
+              path: /readyz
+              port: 8000
+            failureThreshold: 12
+            periodSeconds: 5
+          livenessProbe:
+            httpGet:
+              path: /healthz
+              port: 8000
+            periodSeconds: 10
+          readinessProbe:
+            httpGet:
+              path: /readyz
+              port: 8000
+            periodSeconds: 10
+          resources:
+            {{- toYaml .Values.hdlfServer.resources | nindent 12 }}
+      volumes:
+        - name: hdlf-tls
+          secret:
+            secretName: {{ required "hdlfServer.hdlf.tlsSecretName must be set" .Values.hdlfServer.hdlf.tlsSecretName }}
+{{- end }}
diff --git a/chart/templates/networkpolicy-hdlf-server.yaml b/chart/templates/networkpolicy-hdlf-server.yaml
new file mode 100644
index 00000000..63beb779
--- /dev/null
+++ b/chart/templates/networkpolicy-hdlf-server.yaml
@@ -0,0 +1,25 @@
+{{- if and .Values.hdlfServer.enabled .Values.hdlfServer.networkPolicy.enabled -}}
+apiVersion: networking.k8s.io/v1
+kind: NetworkPolicy
+metadata:
+  name: {{ .Chart.Name }}-hdlf-server
+  labels:
+    app: {{ .Chart.Name }}-hdlf-server
+    pipeline-fl/component: hdlf-server
+spec:
+  podSelector:
+    matchLabels:
+      app: {{ .Chart.Name }}-hdlf-server
+  policyTypes:
+    - Ingress
+
+  ingress:
+    - from:
+        - podSelector:
+            matchExpressions:
+              - key: {{ required "hdlfServer.networkPolicy.faultHandlerLabelKey must be set" .Values.hdlfServer.networkPolicy.faultHandlerLabelKey | quote }}
+                operator: Exists
+      ports:
+        - protocol: TCP
+          port: 8000
+{{- end }}
diff --git a/chart/templates/pdb-hdlf-server.yaml b/chart/templates/pdb-hdlf-server.yaml
new file mode 100644
index 00000000..5c3af2aa
--- /dev/null
+++ b/chart/templates/pdb-hdlf-server.yaml
@@ -0,0 +1,25 @@
+{{- /*
+  PodDisruptionBudget for hdlf-server — same protection rationale as
+  the Ingestion API's PDB (chart/templates/pdb.yaml). hdlf-server runs
+  with replicaCount: 2 by default; without a PDB, a single node drain
+  during cluster upgrade can take both pods down at once and leave the
+  Fault Handler / Custom Runtime fleet unable to read inspection data.
+
+  Separate manifest from pdb.yaml because the selector targets the
+  hdlf-server label (`{{ .Chart.Name }}-hdlf-server`), not the
+  Ingestion API's (`{{ .Chart.Name }}`).
+*/}}
+{{- if and .Values.hdlfServer.enabled (gt (int .Values.hdlfServer.replicaCount) 1) }}
+apiVersion: policy/v1
+kind: PodDisruptionBudget
+metadata:
+  name: {{ .Chart.Name }}-hdlf-server
+  labels:
+    app: {{ .Chart.Name }}-hdlf-server
+    pipeline-fl/component: hdlf-server
+spec:
+  minAvailable: 1
+  selector:
+    matchLabels:
+      app: {{ .Chart.Name }}-hdlf-server
+{{- end }}
diff --git a/chart/templates/service-hdlf-server.yaml b/chart/templates/service-hdlf-server.yaml
new file mode 100644
index 00000000..abd59a35
--- /dev/null
+++ b/chart/templates/service-hdlf-server.yaml
@@ -0,0 +1,17 @@
+{{- if .Values.hdlfServer.enabled -}}
+apiVersion: v1
+kind: Service
+metadata:
+  name: {{ .Chart.Name }}-hdlf-server
+  labels:
+    app: {{ .Chart.Name }}-hdlf-server
+    pipeline-fl/component: hdlf-server
+spec:
+  type: ClusterIP
+  ports:
+    - port: 8000
+      targetPort: 8000
+      protocol: TCP
+  selector:
+    app: {{ .Chart.Name }}-hdlf-server
+{{- end }}
diff --git a/chart/values.yaml b/chart/values.yaml
index 5d93053e..4bb0120d 100644
--- a/chart/values.yaml
+++ b/chart/values.yaml
@@ -168,3 +168,33 @@ temporal:
   # Retention is set via a post-install/post-upgrade hook Job, not via the
   # namespace bootstrap, to avoid accidental reset on helm upgrade.
   namespaceRetention: "336h"
+
+# Handler SDK API — the second deployment in this chart. Reads inspection
+# data from HDLF and exposes it over HTTP. Reachable in-cluster only:
+# the NetworkPolicy admits traffic only from pods carrying the configured
+# label key (default: `pipeline-fl/faulthandler`).
+hdlfServer:
+  enabled: true
+  replicaCount: 2
+  # Passed to FAULT_LOCALIZATION_ENV in the container — required by the
+  # shared Settings validator even though this service does not consume it.
+  faultLocalizationEnv: prod
+  resources:
+    requests:
+      cpu: 50m
+      memory: 128Mi
+    limits:
+      cpu: 250m
+      memory: 256Mi
+  hdlf:
+    # HDLF coordinates for the test landscape. Once Piper-from-Vault wiring
+    # for these is in place, blank these out and let Piper inject them.
+    # The TLS secret named below must already exist in the namespace.
+    restApiHost: c072e62e-3bdd-445d-9e90-98fc5375bee8.files.hdl.cc.hc-eu01can.hanacloud.ondemand.com
+    containerId: c072e62e-3bdd-445d-9e90-98fc5375bee8
+    # mTLS Secret with client.crt + client.key inside (mounted at
+    # /home/app/app/certs to match HdlfClient's default cert_dir).
+    tlsSecretName: fl-hdlf-tls
+  networkPolicy:
+    enabled: true
+    faultHandlerLabelKey: pipeline-fl/faulthandler
diff --git a/fl_control_plane/data_extractor/capture_plan.py b/fl_control_plane/data_extractor/capture_plan.py
index d5a0d257..d27c14ba 100644
--- a/fl_control_plane/data_extractor/capture_plan.py
+++ b/fl_control_plane/data_extractor/capture_plan.py
@@ -39,6 +39,7 @@
 
 from fl_control_plane.data_extractor.jenkins_client import JenkinsAPIClient
 from fl_control_plane.data_extractor.models import CaptureItem
+from fl_shared.inspection_layout import safe_name
 
 log = logging.getLogger(__name__)
 
@@ -140,7 +141,7 @@ def _blue_ocean_stage_items(
             continue
 
         raw_name = node.get("displayName", "unknown")
-        safe = _safe_name(raw_name)
+        safe = safe_name(raw_name)
         count = seen_names.get(safe, 0)
         seen_names[safe] = count + 1
         stage_dir = f"{safe}_{node_id}" if count > 0 else safe
@@ -205,7 +206,7 @@ async def _wfapi_stage_items(
             status = stage.get("status", "")
             if status in ("SUCCESS", "NOT_EXECUTED"):
                 continue
-            stage_name = _safe_name(stage.get("name", "unknown"))
+            stage_name = safe_name(stage.get("name", "unknown"))
             node_id = stage.get("id", "")
             priority.append(CaptureItem(
                 key=f"stages/{stage_name}/console.log",
@@ -328,7 +329,3 @@ async def build_capture_plan(
         inspection_uuid, total, len(priority), len(non_priority) + 1,
     )
     return priority + non_priority + [build_console]
-
-
-def _safe_name(name: str) -> str:
-    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name).strip("_") or "stage"
diff --git a/fl_control_plane/data_extractor/downloader.py b/fl_control_plane/data_extractor/downloader.py
index b4ca6774..46a18621 100644
--- a/fl_control_plane/data_extractor/downloader.py
+++ b/fl_control_plane/data_extractor/downloader.py
@@ -51,7 +51,7 @@
     DownloaderConfig,
     ItemStatus,
 )
-from fl_control_plane.hdlf_client import HdlfClient
+from fl_shared.hdlf_client import HdlfClient
 
 log = logging.getLogger(__name__)
 
diff --git a/fl_control_plane/data_extractor/extractor.py b/fl_control_plane/data_extractor/extractor.py
index e33ee1c2..e5f2691d 100644
--- a/fl_control_plane/data_extractor/extractor.py
+++ b/fl_control_plane/data_extractor/extractor.py
@@ -29,7 +29,7 @@
     ExtractionResult,
     ItemStatus,
 )
-from fl_control_plane.hdlf_client import HdlfClient
+from fl_shared.hdlf_client import HdlfClient
 
 log = logging.getLogger(__name__)
 
diff --git a/fl_control_plane/hdlf_client/__init__.py b/fl_control_plane/hdlf_client/__init__.py
deleted file mode 100644
index b0fb6136..00000000
--- a/fl_control_plane/hdlf_client/__init__.py
+++ /dev/null
@@ -1,3 +0,0 @@
-from fl_control_plane.hdlf_client.client import HdlfClient, FileStatus, CapExceededError, read_with_fallback
-
-__all__ = ["HdlfClient", "FileStatus", "CapExceededError", "read_with_fallback"]
diff --git a/fl_control_plane/metadata_extractor/extractor.py b/fl_control_plane/metadata_extractor/extractor.py
index ab463ad4..ff0c75aa 100644
--- a/fl_control_plane/metadata_extractor/extractor.py
+++ b/fl_control_plane/metadata_extractor/extractor.py
@@ -27,7 +27,7 @@
 from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
 
 from fl_control_plane.database import Inspection
-from fl_control_plane.hdlf_client import HdlfClient
+from fl_shared.hdlf_client import HdlfClient
 
 log = logging.getLogger(__name__)
 
diff --git a/fl_shared/__init__.py b/fl_shared/__init__.py
new file mode 100644
index 00000000..e69de29b
diff --git a/fl_shared/hdlf_client/__init__.py b/fl_shared/hdlf_client/__init__.py
new file mode 100644
index 00000000..c1a0cf3f
--- /dev/null
+++ b/fl_shared/hdlf_client/__init__.py
@@ -0,0 +1,3 @@
+from fl_shared.hdlf_client.client import CapExceededError, FileStatus, HdlfClient, read_with_fallback
+
+__all__ = ["HdlfClient", "FileStatus", "CapExceededError", "read_with_fallback"]
diff --git a/fl_control_plane/hdlf_client/client.py b/fl_shared/hdlf_client/client.py
similarity index 69%
rename from fl_control_plane/hdlf_client/client.py
rename to fl_shared/hdlf_client/client.py
index 9f7de82e..4d44809a 100644
--- a/fl_control_plane/hdlf_client/client.py
+++ b/fl_shared/hdlf_client/client.py
@@ -13,6 +13,7 @@
 import os
 import ssl
 import tempfile
+from collections.abc import AsyncIterator
 from dataclasses import dataclass
 from typing import Any
 from urllib.parse import quote
@@ -259,47 +260,166 @@ async def stream_to_file(
 
         If cap_bytes is set, stops and raises CapExceededError when the cap is hit
         (partial local file is deleted on raise).
+
+        Retry policy matches `iter_object` and `_request`: tenacity-driven
+        exponential back-off honouring `Retry-After` on transient HTTP
+        errors and network failures. Per-attempt failures release the
+        response and remove any partial local file before retrying so a
+        retried attempt starts from a clean state.
+        """
+        if self._session is None:
+            raise RuntimeError("HdlfClient must be used as an async context manager")
+        url = self._url(path, "OPEN")
+
+        async def _do_one_attempt() -> int:
+            """Run a single GET → write attempt; raise on transient/network errors."""
+            async with self._session.get(url, headers=self._headers()) as resp:  # type: ignore[union-attr]
+                if resp.status in _RETRY_ON_STATUS:
+                    retry_after: float | None = None
+                    if resp.status == 429:
+                        val = resp.headers.get("Retry-After")
+                        if val:
+                            try:
+                                retry_after = float(val)
+                            except ValueError:
+                                pass
+                    log.warning(
+                        "HTTP %s from HDLF (stream_to_file) — will retry", resp.status
+                    )
+                    raise _HdlfTransientError(resp.status, retry_after)
+                if resp.status == 404:
+                    raise FileNotFoundError(f"HDLF path not found: {path}")
+                if resp.status != 200:
+                    body = await resp.read()
+                    raise IOError(
+                        f"GET {path} returned HTTP {resp.status}: {body[:200]!r}"
+                    )
+                written = 0
+                try:
+                    async with aiofiles.open(local_dest, "wb") as f:
+                        async for chunk in resp.content.iter_chunked(_CHUNK):
+                            await f.write(chunk)
+                            written += len(chunk)
+                            if cap_bytes is not None and written > cap_bytes:
+                                raise CapExceededError(written)
+                except CapExceededError:
+                    if os.path.exists(local_dest):
+                        os.unlink(local_dest)
+                    raise
+                return written
+
+        try:
+            async for attempt in AsyncRetrying(
+                retry=retry_if_exception_type(
+                    (_HdlfTransientError, aiohttp.ClientError, asyncio.TimeoutError)
+                ),
+                stop=stop_after_attempt(self._max_retries),
+                wait=wait_combine(
+                    wait_exception(_retry_after_wait),
+                    wait_exponential(multiplier=1.0, min=1.0, max=60.0),
+                ),
+                reraise=True,
+            ):
+                with attempt:
+                    return await _do_one_attempt()
+        except _HdlfTransientError as exc:
+            raise IOError(
+                f"stream_to_file {path} failed after retries: HTTP {exc.args[0]}"
+            ) from exc
+        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
+            raise IOError(
+                f"stream_to_file {path} failed after retries: "
+                f"{type(exc).__name__}: {exc}"
+            ) from exc
+        # Unreachable: AsyncRetrying with reraise=True either returns or raises.
+        raise IOError(f"stream_to_file {path} failed after retries")
+
+    async def iter_object(
+        self, path: str, chunk_size: int = _CHUNK
+    ) -> AsyncIterator[bytes]:
+        """Stream an HDLF object as an async iterator of byte chunks.
+
+        Used by callers (e.g. hdlf_server) that need to relay HDLF content
+        to a downstream consumer without buffering the whole object in memory.
+
+        Raises:
+            FileNotFoundError:  HDLF returned 404.
+            IOError:            HDLF returned an unexpected status, or all
+                                connection attempts were exhausted.
+            RuntimeError:       Client is not inside an `async with` block.
         """
         if self._session is None:
             raise RuntimeError("HdlfClient must be used as an async context manager")
         url = self._url(path, "OPEN")
-        last_exc: Exception | None = None
 
-        for attempt in range(self._max_retries):
+        async def _open() -> aiohttp.ClientResponse:
+            resp = await self._session.get(url, headers=self._headers())
+            if resp.status in _RETRY_ON_STATUS:
+                retry_after: float | None = None
+                if resp.status == 429:
+                    val = resp.headers.get("Retry-After")
+                    if val:
+                        try:
+                            retry_after = float(val)
+                        except ValueError:
+                            pass
+                resp.release()
+                log.warning("HTTP %s from HDLF (iter_object) — will retry", resp.status)
+                raise _HdlfTransientError(resp.status, retry_after)
+            if resp.status == 404:
+                resp.release()
+                raise FileNotFoundError(f"HDLF path not found: {path}")
+            if resp.status != 200:
+                body = await resp.read()
+                resp.release()
+                raise IOError(
+                    f"GET {path} returned HTTP {resp.status}: {body[:200]!r}"
+                )
+            return resp
+
+        resp: aiohttp.ClientResponse | None = None
+        try:
             try:
-                async with self._session.get(url, headers=self._headers()) as resp:
-                    if resp.status in _RETRY_ON_STATUS:
-                        wait = self._backoff(resp, attempt)
-                        log.warning("HTTP %s from HDLF, retry in %.1fs", resp.status, wait)
-                        await asyncio.sleep(wait)
-                        last_exc = IOError(f"HTTP {resp.status}")
-                        continue
-                    if resp.status == 404:
-                        raise FileNotFoundError(f"HDLF path not found: {path}")
-                    if resp.status != 200:
-                        body = await resp.read()
-                        raise IOError(f"GET {path} returned HTTP {resp.status}: {body[:200]}")
-                    written = 0
-                    try:
-                        async with aiofiles.open(local_dest, "wb") as f:
-                            async for chunk in resp.content.iter_chunked(_CHUNK):
-                                await f.write(chunk)
-                                written += len(chunk)
-                                if cap_bytes is not None and written > cap_bytes:
-                                    raise CapExceededError(written)
-                    except CapExceededError:
-                        if os.path.exists(local_dest):
-                            os.unlink(local_dest)
-                        raise
-                    return written
-            except (FileNotFoundError, IOError, CapExceededError):
-                raise
-            except aiohttp.ClientError as exc:
-                wait = self._backoff(None, attempt)
-                log.warning("Network error: %s, retry in %.1fs", exc, wait)
-                await asyncio.sleep(wait)
-                last_exc = exc
-        raise last_exc or IOError(f"stream_to_file {path} failed after retries")
+                async for attempt in AsyncRetrying(
+                        retry=retry_if_exception_type(
+                            (_HdlfTransientError, aiohttp.ClientError, asyncio.TimeoutError)
+                        ),
+                        stop=stop_after_attempt(self._max_retries),
+                        wait=wait_combine(
+                            wait_exception(_retry_after_wait),
+                            wait_exponential(multiplier=1.0, min=1.0, max=60.0),
+                        ),
+                        reraise=True,
+                ):
+                    with attempt:
+                        resp = await _open()
+            except _HdlfTransientError as exc:
+                raise IOError(
+                    f"iter_object {path} failed after retries: HTTP {exc.args[0]}"
+                ) from exc
+            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
+                raise IOError(
+                    f"iter_object {path} failed after retries: {type(exc).__name__}: {exc}"
+                ) from exc
+            if resp is None:
+                # Defensive: AsyncRetrying with reraise=True either returns or
+                # raises — this path is unreachable but the type checker
+                # cannot see that.
+                raise IOError(f"iter_object {path} failed after retries")
+
+            async for chunk in resp.content.iter_chunked(chunk_size):
+                yield chunk
+        finally:
+            # Single outer finally so the response is released no matter
+            # how the generator exits — normal completion, exception
+            # mid-stream, or `aclose()` fired by the consumer (e.g.
+            # FastAPI closing a StreamingResponse on client disconnect).
+            # Without this, a cancellation between `_open()` returning
+            # and the iter_chunked loop starting would leak `resp` back
+            # to aiohttp's connection pool, only to be reaped non-
+            # deterministically by GC on a possibly-different event loop.
+            if resp is not None:
+                resp.release()
 
     async def delete_object(self, path: str) -> None:
         url = self._url(path, "DELETE")
diff --git a/fl_control_plane/hdlf_client/config.py b/fl_shared/hdlf_client/config.py
similarity index 100%
rename from fl_control_plane/hdlf_client/config.py
rename to fl_shared/hdlf_client/config.py
diff --git a/fl_shared/inspection_layout.py b/fl_shared/inspection_layout.py
new file mode 100644
index 00000000..4156a9d8
--- /dev/null
+++ b/fl_shared/inspection_layout.py
@@ -0,0 +1,30 @@
+"""Conventions for the on-disk layout of inspection folders in HDLF.
+
+This module is the single source of truth for the *contract* between the
+Data Extractor (writer) and the hdlf_server `InspectionReader` (reader).
+Anything that needs to round-trip — a stage display name turned into a
+directory name and back, a manifest key, a path under `stages/` — belongs
+here so both sides agree on the encoding.
+
+Keeping these helpers in a neutral module avoids forcing one consumer to
+import from the other (the reader has no business depending on the
+data_extractor, and vice versa).
+"""
+
+from __future__ import annotations
+
+
+def safe_name(name: str) -> str:
+    """Sanitise a Jenkins stage display name for use as an HDLF directory name.
+
+    Replaces every character that is not alphanumeric, ``-``, ``_``, or ``.``
+    with ``_``, strips leading/trailing underscores, and falls back to
+    ``"stage"`` if the result is empty.
+
+    The transformation is *not* invertible — multiple display names can map
+    to the same safe name ("Build #1" and "Build_1" both become "Build_1").
+    The Data Extractor handles collisions by appending the Blue Ocean node
+    id as a suffix (`{safe_name}_{node_id}`); see
+    ``data_extractor.capture_plan`` for the writer side.
+    """
+    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name).strip("_") or "stage"
diff --git a/hdlf_server/__init__.py b/hdlf_server/__init__.py
new file mode 100644
index 00000000..4b36aa34
--- /dev/null
+++ b/hdlf_server/__init__.py
@@ -0,0 +1,44 @@
+"""Handler SDK API — read inspection data captured to HDLF.
+
+`InspectionReader` is the in-process Python API used by the Handler
+Orchestrator. The same surface is exposed over HTTP by `app.py` for the
+AgentTask executors and Custom Runtime containers.
+"""
+
+from hdlf_server.exceptions import (
+    HdlfServerError,
+    InspectionFileNotFoundError,
+    InspectionNotFoundError,
+    InvalidPathError,
+    MalformedInspectionDataError,
+)
+from hdlf_server.models import (
+    ArtifactEntry,
+    InspectionMetadata,
+    ManifestSummary,
+    RawFileInfo,
+    StageNode,
+    StageSummary,
+    StageTree,
+    StepInfo,
+    WfapiStage,
+)
+from hdlf_server.reader import InspectionReader
+
+__all__ = [
+    "ArtifactEntry",
+    "HdlfServerError",
+    "InspectionFileNotFoundError",
+    "InspectionMetadata",
+    "InspectionNotFoundError",
+    "InspectionReader",
+    "InvalidPathError",
+    "MalformedInspectionDataError",
+    "ManifestSummary",
+    "RawFileInfo",
+    "StageNode",
+    "StageSummary",
+    "StageTree",
+    "StepInfo",
+    "WfapiStage",
+]
diff --git a/hdlf_server/app.py b/hdlf_server/app.py
new file mode 100644
index 00000000..1f86bda2
--- /dev/null
+++ b/hdlf_server/app.py
@@ -0,0 +1,34 @@
+"""Standalone FastAPI application for the Handler SDK API (hdlf_server).
+
+Run with:
+    uvicorn hdlf_server.app:app --host 0.0.0.0 --port 8000
+
+Network access is restricted by Kubernetes NetworkPolicy to pods carrying
+the `pipeline-fl/faulthandler` label. This service has no auth dependency
+of its own.
+"""
+
+from fastapi import FastAPI
+
+from hdlf_server.dependencies import lifespan
+from hdlf_server.health import router as health_router
+from hdlf_server.router import router as inspection_router
+
+
+def create_app() -> FastAPI:
+    app = FastAPI(
+        title="FL Control Plane — Handler SDK API",
+        description=(
+            "Read inspection metadata, stage tree, logs, and artefacts captured "
+            "to HDLF by the Data Extractor. Used by Fault Handlers and the "
+            "Handler Orchestrator."
+        ),
+        version="0.0.1",
+        lifespan=lifespan,
+    )
+    app.include_router(health_router)
+    app.include_router(inspection_router, prefix="/api/v1")
+    return app
+
+
+app = create_app()
diff --git a/hdlf_server/dependencies.py b/hdlf_server/dependencies.py
new file mode 100644
index 00000000..130ef5d5
--- /dev/null
+++ b/hdlf_server/dependencies.py
@@ -0,0 +1,82 @@
+"""FastAPI dependencies for the hdlf_server (Handler SDK API).
+
+A single `HdlfClient` is opened at app startup and shared across requests.
+HdlfClient owns one aiohttp ClientSession; sharing it across requests is
+the normal aiohttp pattern (per-request sessions would defeat connection
+pooling and multiply the mTLS handshake cost).
+
+Singleton storage uses ``app.state`` rather than module-level globals so
+that two FastAPI apps in the same process (a real one plus a test app,
+multi-tenant test runs) cannot trample each other. Tests that need to
+substitute the reader/client should use ``app.dependency_overrides``.
+"""
+
+from __future__ import annotations
+
+import logging
+from contextlib import asynccontextmanager
+
+from fastapi import FastAPI, Request
+
+from fl_shared.hdlf_client import HdlfClient
+from fl_shared.hdlf_client.config import settings as hdlf_settings
+from hdlf_server.reader import InspectionReader
+
+log = logging.getLogger(__name__)
+
+
+@asynccontextmanager
+async def lifespan(app: FastAPI):
+    """Open the HDLF connection on startup, close it on shutdown.
+
+    Stores the live client and reader on ``app.state``. Each FastAPI app
+    has its own ``state`` namespace, so two apps in the same process
+    (e.g. real + test) get isolated singletons for free.
+    """
+    log.info(
+        "hdlf_server: opening HdlfClient host=%s container=%s",
+        hdlf_settings.hdlf_rest_api_host,
+        hdlf_settings.hdlf_container_id,
+    )
+    client = HdlfClient(
+        rest_api_host=hdlf_settings.hdlf_rest_api_host,  # type: ignore[arg-type]
+        container_id=hdlf_settings.hdlf_container_id,  # type: ignore[arg-type]
+        cert_dir=hdlf_settings.hdlf_cert_dir,
+    )
+    async with client:
+        app.state.hdlf_client = client
+        app.state.inspection_reader = InspectionReader(client)
+        try:
+            yield
+        finally:
+            log.info("hdlf_server: closing HdlfClient")
+            del app.state.hdlf_client
+            del app.state.inspection_reader
+
+
+def get_reader(request: Request) -> InspectionReader:
+    """FastAPI dependency that yields the singleton reader.
+
+    Raises RuntimeError if called before lifespan startup or after shutdown
+    — that would indicate a wiring bug, not a runtime condition.
+    """
+    reader = getattr(request.app.state, "inspection_reader", None)
+    if reader is None:
+        raise RuntimeError(
+            "InspectionReader is not initialised — lifespan startup did not run"
+        )
+    return reader
+
+
+def get_client(request: Request) -> HdlfClient:
+    """FastAPI dependency that yields the underlying HdlfClient.
+
+    Used by the local readiness probe to test HDLF reachability directly
+    without going through the reader.
+    """
+    client = getattr(request.app.state, "hdlf_client", None)
+    if client is None:
+        raise RuntimeError(
+            "HdlfClient is not initialised — lifespan startup did not run"
+        )
+    return client
diff --git a/hdlf_server/exceptions.py b/hdlf_server/exceptions.py
new file mode 100644
index 00000000..172af81b
--- /dev/null
+++ b/hdlf_server/exceptions.py
@@ -0,0 +1,64 @@
+"""Exceptions raised by `InspectionReader`.
+
+A small custom hierarchy so the FastAPI router can map domain errors to
+HTTP status codes without leaking HDLF/IO specifics to the client.
+"""
+
+from __future__ import annotations
+
+
+class HdlfServerError(Exception):
+    """Base class for inspection-reader errors."""
+
+
+class InspectionNotFoundError(HdlfServerError):
+    """The inspection folder for the requested UUID does not exist in HDLF."""
+
+    def __init__(self, inspection_uuid: str):
+        super().__init__(f"Inspection {inspection_uuid!r} not found")
+        self.inspection_uuid = inspection_uuid
+
+
+class InspectionFileNotFoundError(HdlfServerError):
+    """A specific file inside an existing inspection folder is missing.
+
+    Distinct from InspectionNotFoundError so the router can return 404 with
+    a more specific body and the caller can tell apart "wrong UUID" from
+    "this part wasn't captured".
+    """
+
+    def __init__(self, inspection_uuid: str, relative_path: str):
+        super().__init__(
+            f"Inspection {inspection_uuid!r}: file {relative_path!r} not found"
+        )
+        self.inspection_uuid = inspection_uuid
+        self.relative_path = relative_path
+
+
+class InvalidPathError(HdlfServerError):
+    """A caller-supplied subpath escapes the inspection folder.
+
+    Raised by `_validate_subpath` when the input contains `..`, a leading
+    `/`, or is otherwise not a normal relative path. Maps to HTTP 400.
+    """
+
+
+class MalformedInspectionDataError(HdlfServerError):
+    """A file in HDLF exists but does not match the expected schema.
+
+    Maps to HTTP 502 — HDLF is reachable but the data the Data Extractor
+    wrote there is unusable. Distinguishes operator errors (HDLF outage)
+    from data-quality errors (extractor bug or partial write).
+    """
+
+
+class HdlfUnreachableError(HdlfServerError):
+    """HDLF returned a transient failure that survived all retries.
+
+    Maps to HTTP 502 — HDLF is the dependency that failed, so the
+    semantically correct status is "bad gateway", not 500. Raised by
+    the reader when the underlying ``HdlfClient`` returns ``IOError``
+    after exhausting tenacity's retry budget; without this the router's
+    fall-through path would emit a generic 500 and oncall would have to
+    read the pod logs to discover the failure was downstream.
+    """
diff --git a/hdlf_server/health.py b/hdlf_server/health.py
new file mode 100644
index 00000000..6fd81f5d
--- /dev/null
+++ b/hdlf_server/health.py
@@ -0,0 +1,42 @@
+"""Health probes for the hdlf_server.
+
+The shared `fl_control_plane.health` module's /readyz checks the database,
+which this service does not use. We register a minimal local set instead:
+- /healthz: process liveness
+- /readyz:  HDLF reachability via a cheap GETFILESTATUS on the container root
+"""
+
+from __future__ import annotations
+
+import asyncio
+import logging
+
+import aiohttp
+from fastapi import APIRouter, Depends, HTTPException, status
+
+from fl_shared.hdlf_client import HdlfClient
+from hdlf_server.dependencies import get_client
+
+log = logging.getLogger(__name__)
+
+router = APIRouter(tags=["health"])
+
+
+@router.get("/healthz", summary="Liveness probe")
+async def healthz() -> dict[str, str]:
+    return {"status": "alive"}
+
+
+@router.get("/readyz", summary="Readiness probe — HDLF reachability")
+async def readyz(
+    client: HdlfClient = Depends(get_client),
+) -> dict[str, str]:
+    try:
+        await client.exists("")
+    except (aiohttp.ClientError, asyncio.TimeoutError, IOError, OSError) as exc:
+        log.error("hdlf_server: readiness check failed: %s", exc)
+        raise HTTPException(
+            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
+            detail="not_ready",
+        )
+    return {"status": "ready"}
diff --git a/hdlf_server/models.py b/hdlf_server/models.py
new file mode 100644
index 00000000..6fa44400
--- /dev/null
+++ b/hdlf_server/models.py
@@ -0,0 +1,404 @@
+"""Pydantic output models for the Handler SDK API.
+
+These are the shapes returned by `InspectionReader` and serialised by the
+FastAPI router. They are deliberately permissive (most fields nullable)
+because the underlying HDLF JSON files were produced from heterogeneous
+Jenkins API responses that may legitimately omit fields for certain build
+types (PR vs branch, declarative vs scripted, builds without tests, etc.).
+"""
+
+from __future__ import annotations
+
+from typing import Any, Literal
+
+from pydantic import BaseModel, Field
+
+class InspectionMetadata(BaseModel):
+    """Typed view over `<uuid>/metadata.json` written by the Metadata Extractor.
+
+    Provenance: produced by `fl.metadata_extractor.extractor.extract_metadata`
+    and read back by `InspectionReader.get_metadata`. The shape is a flat
+    union of (a) source-event-derived fields and (b) Jenkins-enriched fields;
+    when Jenkins enrichment failed the (b) fields will be None / empty but
+    the file is still considered well-formed.
+
+    Attributes:
+        jenkins_url:        Jenkins build URL (single source of truth — taken
+                            from the inspection DB row, not the source event).
+        canonical_url:      Build URL as Jenkins reported it. May differ from
+                            jenkins_url when the build URL was a redirect.
+        commit_id:          Full or short SHA of the commit under test.
+        commit_url:         Web URL to view the commit. Often None — Jenkins
+                            does not always populate it; consumers should
+                            fall back to constructing one from git_repos.
+        pr_url / pr_number / pr_title / pr_author:
+                            PR fields — None on non-PR builds. pr_number can
+                            also be None when the build is a PR but Jenkins
+                            did not expose pull-request metadata.
+        build_number:       Jenkins integer build number; None when enrichment
+                            failed.
+        full_display_name:  Jenkins human-readable name (e.g. "foo » PR-1 #42").
+        result / state:     Jenkins build result ("SUCCESS"|"FAILURE"|"UNSTABLE"
+                            |"ABORTED"|None) and Blue Ocean state ("FINISHED"|
+                            "RUNNING"|...). None means "unknown" not "running".
+        building:           True iff Jenkins reported the build was still in
+                            progress when metadata was captured.
+        duration_ms:        Build duration in milliseconds. 0 for in-progress.
+        start_time / end_time: ISO 8601 timestamps; end_time is None for builds
+                            that were still running.
+        git_repos:          One entry per Git repo Jenkins built from. Empty
+                            list when the BuildData action was missing.
+        changesets:         Up to 20 commits in the build's change set, in
+                            Jenkins's reported order.
+        parameters:         Build parameters as a flat dict {name: value}.
+                            Values are whatever Jenkins reported (str/int/bool).
+        extracted_at:       ISO 8601 timestamp when metadata.json was written.
+
+    Example (truncated):
+        {
+          "jenkins_url": "https://ci.example.com/job/foo/job/PR-1/42/",
+          "canonical_url": "https://ci.example.com/job/foo/job/PR-1/42/",
+          "commit_id": "abc12345",
+          "pr_url": "https://github.com/o/r/pull/1",
+          "pr_number": 1,
+          "build_number": 42,
+          "result": "FAILURE",
+          "state": "FINISHED",
+          "building": false,
+          "duration_ms": 123456,
+          "git_repos": [{"repo_url": "https://github.com/o/r.git",
+                         "commit": "abc12345...", "branch": "PR-1"}],
+          "changesets": [...],
+          "parameters": {"BRANCH_NAME": "PR-1"},
+          "extracted_at": "2026-06-09T10:00:00+00:00"
+        }
+    """
+
+    jenkins_url: str
+    canonical_url: str | None = None
+    commit_id: str | None = None
+    commit_url: str | None = None
+    pr_url: str | None = None
+    pr_number: int | None = None
+    build_number: int | None = None
+    pr_title: str | None = None
+    pr_author: str | None = None
+    full_display_name: str | None = None
+    result: str | None = None
+    state: str | None = None
+    building: bool | None = None
+    duration_ms: int | None = None
+    start_time: str | None = None
+    end_time: str | None = None
+    git_repos: list[dict[str, Any]] = Field(default_factory=list)
+    changesets: list[dict[str, Any]] = Field(default_factory=list)
+    parameters: dict[str, Any] = Field(default_factory=dict)
+    extracted_at: str | None = None
+
+    # Tolerate extra fields so the model survives extractor schema additions
+    # without a coordinated rollout.
+    model_config = {"extra": "allow"}
+
+
+class ManifestItem(BaseModel):
+    """One row in `<uuid>/manifest.json`'s `items` array.
+
+    Provenance: assembled by `data_extractor.extractor._write_manifest` from
+    `DownloadResult` records.
+
+    Attributes:
+        key:            HDLF path suffix relative to the inspection folder
+                        (e.g. "console.log", "stages/Build/console.log",
+                        "artifacts/foo.zip"). Use as input to the reader's
+                        streaming methods.
+        status:         One of "captured"|"truncated"|"skipped_size"|
+                        "skipped_inspection_cap"|"skipped_unreachable".
+                        ⚠️ Items with skipped_* status do NOT exist in HDLF.
+                        Callers must check status before requesting the file.
+        original_size:  Server-reported size before any truncation, or None
+                        when not known (e.g. unreachable items).
+        captured_size:  Bytes actually written to HDLF. None for skipped_*.
+        error:          Diagnostic for skipped_unreachable; absent otherwise.
+    """
+
+    key: str
+    status: str
+    original_size: int | None = None
+    captured_size: int | None = None
+    error: str | None = None
+
+
+class ManifestSummary(BaseModel):
+    """Typed view over `<uuid>/manifest.json`.
+
+    Provenance: written by `data_extractor.extractor._write_manifest` after
+    every item in the capture plan has been processed. The presence of this
+    file is the completion signal for an inspection capture.
+
+    Attributes:
+        version:                 Manifest schema version (currently 1).
+        inspection_folder:       The inspection UUID — same as the folder name.
+        jenkins_url:             Mirror of metadata.json's jenkins_url for
+                                 consumers that only fetch the manifest.
+        created_at:              ISO 8601 timestamp when the manifest was
+                                 written (i.e. when capture completed).
+        total_captured_bytes:    Sum of captured_size across CAPTURED and
+                                 TRUNCATED items.
+        total_captured_size:     Same number, human-readable ("123.4 MB").
+        items:                   One ManifestItem per capture-plan entry. The
+                                 list is the authoritative inventory of what
+                                 exists in HDLF for this inspection.
+    """
+
+    version: int = 1
+    inspection_folder: str
+    jenkins_url: str | None = None
+    created_at: str | None = None
+    total_captured_bytes: int = 0
+    total_captured_size: str | None = None
+    items: list[ManifestItem] = Field(default_factory=list)
+
+    model_config = {"extra": "allow"}
+
+
+class StageNode(BaseModel):
+    """One node from Blue Ocean `pipeline_tree.json` (`/nodes/?...`).
+
+    Provenance: subset of the Blue Ocean node response, kept thin enough to
+    serialise back to handlers cheaply but rich enough to reconstruct the
+    stage graph. JSON keys use Blue Ocean's mixedCase naming
+    (`displayName`, `durationInMillis`, `parentNodes`); the Python
+    attributes are snake_case and Pydantic aliases handle the mapping in
+    both directions (so both `model_validate(blue_ocean_dict)` and
+    `model_dump(by_alias=True)` round-trip the original keys).
+
+    Attributes:
+        id:                Node id used in HDLF stage subfolder names.
+        display_name:      Human-readable stage name as Jenkins shows it.
+        type:              Blue Ocean node type ("STAGE"|"PARALLEL"|"STEP"|...).
+        result:            Per-node result ("SUCCESS"|"FAILURE"|"UNSTABLE"|
+                           "ABORTED"|"NOT_EXECUTED"|"UNKNOWN"|None).
+        state:             Run state ("FINISHED"|"RUNNING"|...). None when
+                           Blue Ocean did not report it.
+        duration_ms:       Per-node duration in milliseconds (Blue Ocean key:
+                           `durationInMillis`). None when not measured.
+        parent_nodes:      IDs of predecessor nodes (Blue Ocean key:
+                           `parentNodes`). Sequential dependencies.
+        edges:             Outgoing edges as Blue Ocean reports them.
+    """
+
+    id: str
+    display_name: str | None = Field(default=None, alias="displayName")
+    type: str | None = None
+    result: str | None = None
+    state: str | None = None
+    duration_ms: int | None = Field(default=None, alias="durationInMillis")
+    parent_nodes: list[str] = Field(default_factory=list, alias="parentNodes")
+    edges: list[dict[str, Any]] = Field(default_factory=list)
+
+    model_config = {"extra": "allow", "populate_by_name": True}
+
+
+class WfapiStage(BaseModel):
+    """One stage from `<uuid>/wfapi_describe.json`'s `stages` array.
+
+    Provenance: subset of Jenkins WFAPI's `/wfapi/describe` response, kept
+    deliberately distinct from `StageNode` because WFAPI and Blue Ocean
+    describe pipelines with non-overlapping schemas — collapsing them into
+    one model would force half the fields to be nullable for each source
+    and erase the "which source produced this?" signal that consumers
+    rely on.
+
+    Why a model and not `dict[str, Any]`: project convention forbids
+    untyped dicts at API output boundaries (CLAUDE.md "Pydantic API
+    Boundary Pattern"). A schema drift in WFAPI now fails at
+    `model_validate` time and the router translates it into HTTP 502 —
+    same failure mode as `StageNode` and `ManifestSummary`.
+
+    Attributes:
+        id:                  Flow node id of the stage's start node.
+                             ⚠️ NOT comparable to a Blue Ocean
+                             `StageNode.id`. Use as the path segment in
+                             `{build_url}/execution/node/{id}/wfapi/...`.
+        name:                Human-readable stage name as Jenkins shows it.
+        status:              WFAPI status string —
+                             "SUCCESS"|"FAILED"|"UNSTABLE"|"ABORTED"|
+                             "NOT_EXECUTED"|"IN_PROGRESS"|"PAUSED_PENDING_INPUT"|
+                             "QUEUED"|None. Note "FAILED" not "FAILURE"
+                             (Blue Ocean uses "FAILURE") — different
+                             vocabularies, do not unify.
+        exec_node:           Jenkins node label the stage ran on; "" when
+                             WFAPI did not report it. Mapped from WFAPI's
+                             `execNode` key.
+        start_time_millis:   Stage start time as ms-since-epoch (WFAPI key:
+                             `startTimeMillis`). None when not reported.
+        duration_millis:     Stage wall-clock duration in ms (WFAPI key:
+                             `durationMillis`). Includes pause time;
+                             subtract `pause_duration_millis` for run time.
+        pause_duration_millis: Time spent paused waiting for input
+                             (WFAPI key: `pauseDurationMillis`). 0 for
+                             stages with no manual gates.
+        stage_flow_nodes:    Flow node ids contained in this stage (WFAPI
+                             key: `stageFlowNodes`). Each entry has a
+                             flow-node id usable with the per-node WFAPI
+                             endpoints. Kept as raw dicts because the
+                             flow-node schema is consumed only by the
+                             writer (capture_plan), not by API consumers.
+    """
+
+    id: str
+    name: str | None = None
+    status: str | None = None
+    exec_node: str | None = Field(default=None, alias="execNode")
+    start_time_millis: int | None = Field(default=None, alias="startTimeMillis")
+    duration_millis: int | None = Field(default=None, alias="durationMillis")
+    pause_duration_millis: int | None = Field(
+        default=None, alias="pauseDurationMillis"
+    )
+    stage_flow_nodes: list[dict[str, Any]] = Field(
+        default_factory=list, alias="stageFlowNodes"
+    )
+
+    # `extra=allow` to survive WFAPI schema additions; `populate_by_name`
+    # so tests and code can construct via either snake_case or alias.
+    model_config = {"extra": "allow", "populate_by_name": True}
+
+
+class StageTree(BaseModel):
+    """Combined Blue Ocean + WFAPI stage tree for an inspection.
+
+    Provenance: assembled by `InspectionReader.get_stage_tree`. Source
+    selection (primary → fallback):
+      1. `<uuid>/pipeline_tree.json` (Blue Ocean nodes endpoint)
+      2. `<uuid>/wfapi_describe.json` (WFAPI describe — used when Blue Ocean
+         was unavailable at capture time).
+
+    Attributes:
+        source:         Which source produced `nodes` — "blue_ocean" or
+                        "wfapi". Consumers that need fine-grained step
+                        results should fall back to per-stage `steps.json`
+                        when source is "wfapi" since WFAPI does not
+                        expose step-level results.
+        nodes:          Parsed Blue Ocean nodes (when source is
+                        "blue_ocean"). Empty list when the source is
+                        WFAPI.
+        wfapi_stages:   Parsed WFAPI stages. Always populated when
+                        wfapi_describe.json exists, regardless of source
+                        — Blue Ocean primary still surfaces WFAPI as a
+                        secondary view so consumers can correlate node
+                        ids across the two systems.
+    """
+
+    source: Literal["blue_ocean", "wfapi"]
+    nodes: list[StageNode] = Field(default_factory=list)
+    wfapi_stages: list[WfapiStage] = Field(default_factory=list)
+
+
+class StageSummary(BaseModel):
+    """One entry per subfolder of `<uuid>/stages/`.
+
+    Provenance: produced by `InspectionReader.list_stages` from a single
+    `list_dir` of the stages folder, cross-referenced with the manifest to
+    determine which artefacts were actually captured for the stage.
+
+    Attributes:
+        name:               Display name reconstructed from `dir` (the
+                            extractor uses `fl_shared.inspection_layout.safe_name()`
+                            on the Jenkins displayName, so this is a
+                            best-effort reverse — it may differ from the
+                            original on stages whose names contained
+                            characters that were sanitised).
+        dir:                The stage subfolder name as it appears in HDLF
+                            (e.g. "Build", "Build_42" when the same name was
+                            seen twice, "stage" when extraction failed to
+                            produce a usable name). Use this with
+                            `get_stage_steps` and `stream_stage_log`.
+        has_console_log:    True if `stages/<dir>/console.log` exists. False
+                            for NOT_EXECUTED stages and for stages where all
+                            steps succeeded (only_failed_steps=True drops
+                            empty logs).
+        has_steps_json:     True if `stages/<dir>/steps.json` exists.
+        has_wfapi_describe: True if `stages/<dir>/wfapi_describe.json` exists.
+        result:             Best-effort result from the stage tree, when one
+                            could be matched. None when no match was possible.
+    """
+
+    name: str
+    dir: str
+    has_console_log: bool = False
+    has_steps_json: bool = False
+    has_wfapi_describe: bool = False
+    result: str | None = None
+
+
+class StepInfo(BaseModel):
+    """One step from a Blue Ocean `<uuid>/stages/<dir>/steps.json`.
+
+    Provenance: parsed by `InspectionReader.get_stage_steps`. Items in
+    `steps.json` carry every step Blue Ocean knows about for the parent
+    stage, regardless of result. JSON keys are Blue Ocean's mixedCase;
+    Pydantic aliases map them to snake_case on the Python side.
+
+    Attributes:
+        id:                 Step node id.
+        display_name:       Human-readable step name (Blue Ocean key:
+                            `displayName`).
+        result:             Per-step result ("SUCCESS"|"FAILURE"|...|None).
+        state:              Run state ("FINISHED"|"RUNNING"|...|None).
+        duration_ms:        Step duration in milliseconds (Blue Ocean key:
+                            `durationInMillis`). None when Blue Ocean did
+                            not report.
+    """
+
+    id: str
+    display_name: str | None = Field(default=None, alias="displayName")
+    result: str | None = None
+    state: str | None = None
+    duration_ms: int | None = Field(default=None, alias="durationInMillis")
+
+    model_config = {"extra": "allow", "populate_by_name": True}
+
+
+class ArtifactEntry(BaseModel):
+    """One captured Jenkins artefact.
+
+    Provenance: derived by `InspectionReader.list_artifacts` from the manifest's
+    items whose key starts with "artifacts/". Items with skipped_* status are
+    INCLUDED so consumers can see what was attempted but not stored — check
+    `status` before requesting the bytes.
+
+    Attributes:
+        relative_path:  Path of the artefact relative to the artifacts/ folder
+                        (i.e. with "artifacts/" stripped). Use this with
+                        `stream_artifact`.
+        status:         Same value as the manifest item's status.
+        original_size:  See ManifestItem.original_size.
+        captured_size:  See ManifestItem.captured_size.
+    """
+
+    relative_path: str
+    status: str
+    original_size: int | None = None
+    captured_size: int | None = None
+
+
+class RawFileInfo(BaseModel):
+    """A single file or directory inside the inspection folder.
+
+    Provenance: produced by `InspectionReader.list_files` from
+    `HdlfClient.list_dir`. Returned as-is to API callers who need to discover
+    files outside the documented capture-plan layout.
+
+    Attributes:
+        path:               HDLF path relative to the inspection folder
+                            (e.g. "stages/Build/console.log"). Suitable as
+                            input to `stream_raw`.
+        length:             File size in bytes; 0 for directories.
+        modification_time:  HDLF-reported mtime in milliseconds since epoch.
+        is_directory:       True for directories.
+    """
+
+    path: str
+    length: int
+    modification_time: int
+    is_directory: bool
diff --git a/hdlf_server/reader.py b/hdlf_server/reader.py
new file mode 100644
index 00000000..0bc665c0
--- /dev/null
+++ b/hdlf_server/reader.py
@@ -0,0 +1,452 @@
+"""InspectionReader — domain-aware reader over HDLF inspection folders.
+
+Wraps `HdlfClient` to expose the inspection-folder layout produced by
+`fl.data_extractor` (see capture_plan.py docstring for the canonical
+layout). Exposes typed reads for the well-known files plus an escape
+hatch (`list_files`, `stream_raw`) for unstructured discovery.
+
+Lifecycle: this class does not own the HdlfClient. Callers must enter
+the `async with HdlfClient(...)` block themselves and pass the live
+client into `InspectionReader(client)`. This matches how the FastAPI
+app keeps a single connection pool open for the lifetime of the process.
+"""
+
+from __future__ import annotations
+
+import json
+import logging
+from collections.abc import AsyncGenerator
+from typing import Any
+from urllib.parse import unquote
+
+from pydantic import ValidationError
+
+from fl_shared.hdlf_client import HdlfClient
+from fl_shared.inspection_layout import safe_name
+from hdlf_server.exceptions import (
+    HdlfUnreachableError,
+    InspectionFileNotFoundError,
+    InspectionNotFoundError,
+    InvalidPathError,
+    MalformedInspectionDataError,
+)
+from hdlf_server.models import (
+    ArtifactEntry,
+    InspectionMetadata,
+    ManifestSummary,
+    RawFileInfo,
+    StageNode,
+    StageSummary,
+    StageTree,
+    StepInfo,
+    WfapiStage,
+)
+
+log = logging.getLogger(__name__)
+
+# Iteration cap for `_validate_subpath`'s fixed-point unquote loop.
+# Real attacker payloads nest at most one or two layers; the cap rejects
+# pathological inputs without admitting untrusted state.
+_MAX_DECODE_ITERATIONS = 8
+
+
+def _validate_subpath(subpath: str) -> str:
+    """Reject inputs that could escape the inspection folder.
+
+    Strategy: percent-decode to a fixed point before running checks, so
+    any chain of encodings collapses to its final form. A single
+    ``unquote`` only undoes one layer — ``%252e%252e`` would decode to
+    ``%2e%2e`` and pass the ``..`` check. The fixed-point loop catches
+    arbitrary nesting (``%25252e`` → ``%252e`` → ``%2e`` → ``.``).
+
+    Defensive against:
+      - absolute paths (leading ``/``)
+      - ``..`` / ``.`` segments
+      - backslashes (DOS-style separators)
+      - percent-encoded variants of the above, at any nesting depth
+      - empty segments (``a//b``, leading or trailing ``/``)
+      - NUL bytes (``\\x00``) which truncate paths in some C-level
+        consumers.
+
+    Raises:
+        InvalidPathError: subpath does not pass any of the above checks.
+    """
+    if not isinstance(subpath, str):
+        raise InvalidPathError(f"subpath must be a string, got {type(subpath).__name__}")
+    decoded = subpath
+    for _ in range(_MAX_DECODE_ITERATIONS):
+        once = unquote(decoded)
+        if once == decoded:
+            break
+        decoded = once
+    else:
+        # Reached the iteration cap without converging. An input that
+        # still changes after this many passes is either pathological or
+        # malicious — reject rather than admit untrusted state.
+        raise InvalidPathError("subpath has too many percent-encoding layers")
+    if decoded.startswith("/"):
+        raise InvalidPathError("subpath must not be absolute")
+    if "\\" in decoded:
+        raise InvalidPathError("subpath must not contain backslashes")
+    if "\x00" in decoded:
+        raise InvalidPathError("subpath must not contain NUL bytes")
+    parts = decoded.split("/")
+    if any(p in ("..", ".") for p in parts):
+        raise InvalidPathError("subpath must not contain '.' or '..' segments")
+    if any(p == "" for p in parts):
+        raise InvalidPathError("subpath must not contain empty segments")
+    return subpath
+
+
+class InspectionReader:
+    """Read inspection data captured to HDLF by the Data Extractor."""
+
+    def __init__(self, hdlf_client: HdlfClient):
+        self._client = hdlf_client
+
+    async def _require_inspection(self, inspection_uuid: str) -> None:
+        """Raise InspectionNotFoundError unless the inspection folder exists.
+
+        We probe metadata.json rather than the folder itself: list_dir on a
+        non-existent folder returns []; an empty folder is indistinguishable
+        from a missing one without an extra call. metadata.json is written
+        first by the Metadata Extractor so its absence reliably signals
+        "no such inspection".
+        """
+        if not await self._client.exists(f"{inspection_uuid}/metadata.json"):
+            raise InspectionNotFoundError(inspection_uuid)
+
+    async def _read_json_optional(
+        self, inspection_uuid: str, relative_path: str
+    ) -> dict[str, Any] | None:
+        """Return parsed JSON, or None if the file does not exist.
+
+        Used for files that are not guaranteed to be present (e.g.
+        wfapi_describe.json may be absent on builds where WFAPI failed).
+        """
+        path = f"{inspection_uuid}/{relative_path}"
+        try:
+            return await self._client.get_object_parsed(path)
+        except FileNotFoundError:
+            return None
+        except ValueError as exc:
+            raise MalformedInspectionDataError(
+                f"{path}: {exc}"
+            ) from exc
+
+    async def _read_json_list_optional(
+        self, inspection_uuid: str, relative_path: str
+    ) -> list[Any] | None:
+        """Return parsed JSON list, or None if the file does not exist.
+
+        get_object_parsed enforces dict; capture-plan items like steps.json
+        and pipeline_tree.json are JSON arrays — needed separately.
+        """
+        path = f"{inspection_uuid}/{relative_path}"
+        try:
+            body = await self._client.get_object(path)
+        except FileNotFoundError:
+            return None
+        try:
+            parsed = json.loads(body)
+        except json.JSONDecodeError as exc:
+            raise MalformedInspectionDataError(
+                f"{path}: invalid JSON: {exc}"
+            ) from exc
+        if not isinstance(parsed, list):
+            raise MalformedInspectionDataError(
+                f"{path}: expected JSON array, got {type(parsed).__name__}"
+            )
+        return parsed
+
+    async def _read_json_required(
+        self, inspection_uuid: str, relative_path: str
+    ) -> dict[str, Any]:
+        """Return parsed JSON dict; raise InspectionFileNotFoundError if missing."""
+        result = await self._read_json_optional(inspection_uuid, relative_path)
+        if result is None:
+            raise InspectionFileNotFoundError(inspection_uuid, relative_path)
+        return result
+
+    async def get_metadata(self, inspection_uuid: str) -> InspectionMetadata:
+        """Return parsed metadata.json. Raises InspectionNotFoundError if missing."""
+        try:
+            data = await self._client.get_object_parsed(
+                f"{inspection_uuid}/metadata.json"
+            )
+        except FileNotFoundError:
+            raise InspectionNotFoundError(inspection_uuid) from None
+        except ValueError as exc:
+            raise MalformedInspectionDataError(
+                f"{inspection_uuid}/metadata.json: {exc}"
+            ) from exc
+        return InspectionMetadata.model_validate(data)
+
+    async def get_manifest(self, inspection_uuid: str) -> ManifestSummary:
+        await self._require_inspection(inspection_uuid)
+        data = await self._read_json_optional(inspection_uuid, "manifest.json")
+        if data is None:
+            raise InspectionFileNotFoundError(inspection_uuid, "manifest.json")
+        try:
+            return ManifestSummary.model_validate(data)
+        except ValidationError as exc:
+            raise MalformedInspectionDataError(
+                f"{inspection_uuid}/manifest.json: {exc}"
+            ) from exc
+
+    async def get_stage_tree(self, inspection_uuid: str) -> StageTree:
+        """Return Blue Ocean stage tree, or fall back to WFAPI describe."""
+        await self._require_inspection(inspection_uuid)
+        nodes_raw = await self._read_json_list_optional(
+            inspection_uuid, "pipeline_tree.json"
+        )
+        wfapi = await self._read_json_optional(
+            inspection_uuid, "wfapi_describe.json"
+        )
+        wfapi_stages: list[WfapiStage] = []
+        if wfapi is not None:
+            stages_raw = wfapi.get("stages", [])
+            if isinstance(stages_raw, list):
+                # Validate at the boundary — schema drift here surfaces as
+                # MalformedInspectionDataError → HTTP 502 instead of being
+                # silently passed through to consumers.
+                try:
+                    wfapi_stages = [WfapiStage.model_validate(s) for s in stages_raw]
+                except ValidationError as exc:
+                    raise MalformedInspectionDataError(
+                        f"{inspection_uuid}/wfapi_describe.json: {exc}"
+                    ) from exc
+
+        if nodes_raw is not None:
+            nodes = [StageNode.model_validate(n) for n in nodes_raw]
+            return StageTree(source="blue_ocean", nodes=nodes, wfapi_stages=wfapi_stages)
+        if wfapi_stages:
+            return StageTree(source="wfapi", nodes=[], wfapi_stages=wfapi_stages)
+        raise InspectionFileNotFoundError(
+            inspection_uuid, "pipeline_tree.json or wfapi_describe.json"
+        )
+
+    async def list_stages(self, inspection_uuid: str) -> list[StageSummary]:
+        await self._require_inspection(inspection_uuid)
+        entries = await self._client.list_dir(f"{inspection_uuid}/stages")
+
+        # The extractor names stage directories `safe_name(displayName)`,
+        # optionally suffixed with `_{node_id}` when the same display
+        # name appears more than once (see
+        # capture_plan.py:_blue_ocean_stage_items). Blue Ocean numeric
+        # node ids never appear in the directory name for unique stage
+        # names, so they cannot be used as the join key — we mirror the
+        # extractor's naming logic here to reconstruct the directory
+        # name → result mapping.
+        result_by_dir: dict[str, str] = {}
+        try:
+            tree = await self.get_stage_tree(inspection_uuid)
+        except InspectionFileNotFoundError:
+            tree = None
+        if tree is not None:
+            seen: dict[str, int] = {}
+            for node in tree.nodes:
+                if not (node.display_name and node.id):
+                    continue
+                safe = safe_name(node.display_name)
+                count = seen.get(safe, 0)
+                seen[safe] = count + 1
+                dir_name = f"{safe}_{node.id}" if count > 0 else safe
+                if node.result:
+                    result_by_dir[dir_name] = node.result
+
+        summaries: list[StageSummary] = []
+        for entry in entries:
+            if not entry.is_directory:
+                continue
+            dir_name = entry.path.rstrip("/").rsplit("/", 1)[-1]
+            child_paths = {
+                e.path.rsplit("/", 1)[-1]
+                for e in await self._client.list_dir(entry.path)
+            }
+
+            # Reconstruct the display name from the directory name by
+            # stripping the `_<node_id>` collision suffix only when the
+            # trailing segment is actually a numeric Blue Ocean id.
+            # Preserves names like "Integration_Test" or "Build_Backend"
+            # that legitimately contain underscores.
+            display = dir_name
+            if "_" in dir_name:
+                head, _, tail = dir_name.rpartition("_")
+                if tail.isdigit():
+                    display = head
+
+            summaries.append(
+                StageSummary(
+                    name=display,
+                    dir=dir_name,
+                    has_console_log="console.log" in child_paths,
+                    has_steps_json="steps.json" in child_paths,
+                    has_wfapi_describe="wfapi_describe.json" in child_paths,
+                    result=result_by_dir.get(dir_name),
+                )
+            )
+        return summaries
+
+    async def get_stage_steps(
+        self, inspection_uuid: str, stage_dir: str
+    ) -> list[StepInfo]:
+        _validate_subpath(stage_dir)
+        await self._require_inspection(inspection_uuid)
+        steps_raw = await self._read_json_list_optional(
+            inspection_uuid, f"stages/{stage_dir}/steps.json"
+        )
+        if steps_raw is None:
+            raise InspectionFileNotFoundError(
+                inspection_uuid, f"stages/{stage_dir}/steps.json"
+            )
+        return [StepInfo.model_validate(s) for s in steps_raw]
+
+    async def stream_console_log(
+        self, inspection_uuid: str
+    ) -> AsyncGenerator[bytes, None]:
+        await self._require_inspection(inspection_uuid)
+        async for chunk in self._stream_or_404(
+            inspection_uuid, "console.log"
+        ):
+            yield chunk
+
+    async def stream_stage_log(
+        self, inspection_uuid: str, stage_dir: str
+    ) -> AsyncGenerator[bytes, None]:
+        _validate_subpath(stage_dir)
+        await self._require_inspection(inspection_uuid)
+        async for chunk in self._stream_or_404(
+            inspection_uuid, f"stages/{stage_dir}/console.log"
+        ):
+            yield chunk
+
+    async def stream_artifact(
+        self, inspection_uuid: str, relative_path: str
+    ) -> AsyncGenerator[bytes, None]:
+        _validate_subpath(relative_path)
+        await self._require_inspection(inspection_uuid)
+        async for chunk in self._stream_or_404(
+            inspection_uuid, f"artifacts/{relative_path}"
+        ):
+            yield chunk
+
+    async def stream_test_xml(
+        self, inspection_uuid: str
+    ) -> AsyncGenerator[bytes, None]:
+        await self._require_inspection(inspection_uuid)
+        async for chunk in self._stream_or_404(
+            inspection_uuid, "tests/junit_report.xml"
+        ):
+            yield chunk
+
+    async def stream_raw(
+        self, inspection_uuid: str, relative_path: str
+    ) -> AsyncGenerator[bytes, None]:
+        _validate_subpath(relative_path)
+        await self._require_inspection(inspection_uuid)
+        async for chunk in self._stream_or_404(inspection_uuid, relative_path):
+            yield chunk
+
+    async def _stream_or_404(
+        self, inspection_uuid: str, relative_path: str
+    ) -> AsyncGenerator[bytes, None]:
+        """Translate HdlfClient errors to domain exceptions.
+
+        ``FileNotFoundError`` becomes ``InspectionFileNotFoundError`` (404).
+        ``IOError`` becomes ``HdlfUnreachableError`` (502) — HdlfClient
+        wraps an exhausted retry budget in ``IOError`` so the original
+        HTTP status is preserved in the message; without this translation
+        the router would fall through to a generic 500 instead of the
+        bad-gateway status that signals "downstream failed".
+
+        Done in a helper because async generators cannot wrap try/except
+        around their own first chunk in a way that translates the exception
+        cleanly — we have to consume the first part of the iterator here.
+        """
+        _validate_subpath(relative_path)
+        try:
+            async for chunk in self._client.iter_object(
+                f"{inspection_uuid}/{relative_path}"
+            ):
+                yield chunk
+        except FileNotFoundError:
+            raise InspectionFileNotFoundError(inspection_uuid, relative_path) from None
+        except IOError as exc:
+            raise HdlfUnreachableError(
+                f"HDLF stream failed for {inspection_uuid}/{relative_path}: {exc}"
+            ) from exc
+
+    async def list_artifacts(self, inspection_uuid: str) -> list[ArtifactEntry]:
+        manifest = await self.get_manifest(inspection_uuid)
+        prefix = "artifacts/"
+        artifacts: list[ArtifactEntry] = []
+        for item in manifest.items:
+            if not item.key.startswith(prefix):
+                continue
+            artifacts.append(
+                ArtifactEntry(
+                    relative_path=item.key[len(prefix):],
+                    status=item.status,
+                    original_size=item.original_size,
+                    captured_size=item.captured_size,
+                )
+            )
+        return artifacts
+
+    async def get_build_summary(
+        self, inspection_uuid: str
+    ) -> dict[str, Any] | None:
+        await self._require_inspection(inspection_uuid)
+        return await self._read_json_optional(inspection_uuid, "build_summary.json")
+
+    async def get_build_params(
+        self, inspection_uuid: str
+    ) -> dict[str, Any] | None:
+        await self._require_inspection(inspection_uuid)
+        return await self._read_json_optional(inspection_uuid, "build_params.json")
+
+    async def get_build_causes(
+        self, inspection_uuid: str
+    ) -> dict[str, Any] | None:
+        await self._require_inspection(inspection_uuid)
+        return await self._read_json_optional(inspection_uuid, "build_causes.json")
+
+    async def get_environment(
+        self, inspection_uuid: str
+    ) -> dict[str, Any] | None:
+        await self._require_inspection(inspection_uuid)
+        return await self._read_json_optional(inspection_uuid, "environment.json")
+
+    async def get_scm_changelog(
+        self, inspection_uuid: str
+    ) -> dict[str, Any] | None:
+        await self._require_inspection(inspection_uuid)
+        return await self._read_json_optional(inspection_uuid, "scm_changelog.json")
+
+    async def get_test_summary(
+        self, inspection_uuid: str
+    ) -> dict[str, Any] | None:
+        await self._require_inspection(inspection_uuid)
+        return await self._read_json_optional(
+            inspection_uuid, "tests/junit_summary.json"
+        )
+
+    async def list_files(
+        self, inspection_uuid: str, subpath: str = ""
+    ) -> list[RawFileInfo]:
+        if subpath:
+            _validate_subpath(subpath)
+        await self._require_inspection(inspection_uuid)
+        full = inspection_uuid if not subpath else f"{inspection_uuid}/{subpath}"
+        entries = await self._client.list_dir(full)
+        prefix_len = len(inspection_uuid.rstrip("/")) + 1
+        return [
+            RawFileInfo(
+                path=e.path[prefix_len:] if e.path.startswith(inspection_uuid) else e.path,
+                length=e.length,
+                modification_time=e.modification_time,
+                is_directory=e.is_directory,
+            )
+            for e in entries
+        ]
diff --git a/hdlf_server/router.py b/hdlf_server/router.py
new file mode 100644
index 00000000..7c1ddbf5
--- /dev/null
+++ b/hdlf_server/router.py
@@ -0,0 +1,448 @@
+"""HTTP router for the Handler SDK API.
+
+Maps `InspectionReader` methods to resource-oriented endpoints. No auth
+dependency: this service is reachable only through the NetworkPolicy
+that admits pods carrying the `pipeline-fl/faulthandler` label.
+
+UUIDs are validated as `UUID4` (Pydantic), which prevents path-traversal
+in the `{id}` segment. Subpath inputs (`stage_dir`, artifact `relative_path`,
+raw `path` query) flow through `_validate_subpath` in `reader.py`.
+"""
+
+from __future__ import annotations
+
+import logging
+from collections.abc import Callable, AsyncGenerator, Awaitable
+from typing import Any, NoReturn
+
+from fastapi import APIRouter, Depends, HTTPException, Path, Query
+from fastapi.responses import StreamingResponse
+from pydantic import UUID4
+
+from hdlf_server.dependencies import get_reader
+from hdlf_server.exceptions import (
+    HdlfUnreachableError,
+    InspectionFileNotFoundError,
+    InspectionNotFoundError,
+    InvalidPathError,
+    MalformedInspectionDataError,
+)
+from hdlf_server.models import (
+    ArtifactEntry,
+    InspectionMetadata,
+    ManifestSummary,
+    RawFileInfo,
+    StageSummary,
+    StageTree,
+    StepInfo,
+)
+from hdlf_server.reader import InspectionReader
+
+log = logging.getLogger(__name__)
+
+router = APIRouter(tags=["inspection-data"])
+
+
+def _raise_http_for(exc: Exception) -> NoReturn:
+    """Translate reader exceptions to FastAPI HTTPException.
+
+    Always raises — never returns. ``NoReturn`` lets type-checkers see that
+    code after a call to this helper is unreachable, so individual handler
+    bodies don't need an explicit ``return`` after the ``except`` block.
+    """
+    if isinstance(exc, InspectionNotFoundError):
+        raise HTTPException(status_code=404, detail=str(exc))
+    if isinstance(exc, InspectionFileNotFoundError):
+        raise HTTPException(status_code=404, detail=str(exc))
+    if isinstance(exc, InvalidPathError):
+        raise HTTPException(status_code=400, detail=str(exc))
+    if isinstance(exc, MalformedInspectionDataError):
+        raise HTTPException(status_code=502, detail=str(exc))
+    if isinstance(exc, HdlfUnreachableError):
+        raise HTTPException(status_code=502, detail=str(exc))
+    raise exc
+
+
+@router.get(
+    "/inspection/{inspection_id}/metadata",
+    response_model=InspectionMetadata,
+    summary="Inspection metadata (metadata.json)",
+)
+async def get_metadata(
+    inspection_id: UUID4 = Path(..., description="UUID4 inspection identifier"),
+    reader: InspectionReader = Depends(get_reader),
+) -> InspectionMetadata:
+    try:
+        return await reader.get_metadata(str(inspection_id))
+    except (InspectionNotFoundError, MalformedInspectionDataError) as exc:
+        _raise_http_for(exc)
+
+
+@router.get(
+    "/inspection/{inspection_id}/manifest",
+    response_model=ManifestSummary,
+    summary="Capture manifest (manifest.json)",
+)
+async def get_manifest(
+    inspection_id: UUID4 = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> ManifestSummary:
+    try:
+        return await reader.get_manifest(str(inspection_id))
+    except (
+        InspectionNotFoundError,
+        InspectionFileNotFoundError,
+        MalformedInspectionDataError,
+    ) as exc:
+        _raise_http_for(exc)
+
+
+@router.get(
+    "/inspection/{inspection_id}/stage-tree",
+    response_model=StageTree,
+    summary="Stage tree (Blue Ocean nodes; falls back to WFAPI)",
+)
+async def get_stage_tree(
+    inspection_id: UUID4 = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> StageTree:
+    try:
+        return await reader.get_stage_tree(str(inspection_id))
+    except (
+        InspectionNotFoundError,
+        InspectionFileNotFoundError,
+        MalformedInspectionDataError,
+    ) as exc:
+        _raise_http_for(exc)
+
+
+@router.get(
+    "/inspection/{inspection_id}/stages",
+    response_model=list[StageSummary],
+    summary="List per-stage subfolders captured under stages/",
+)
+async def list_stages(
+    inspection_id: UUID4 = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> list[StageSummary]:
+    try:
+        return await reader.list_stages(str(inspection_id))
+    except InspectionNotFoundError as exc:
+        _raise_http_for(exc)
+
+
+@router.get(
+    "/inspection/{inspection_id}/stages/{stage_dir}/steps",
+    response_model=list[StepInfo],
+    summary="Steps for one stage (stages/<dir>/steps.json)",
+)
+async def get_stage_steps(
+    inspection_id: UUID4 = Path(...),
+    stage_dir: str = Path(..., description="Stage subfolder name"),
+    reader: InspectionReader = Depends(get_reader),
+) -> list[StepInfo]:
+    try:
+        return await reader.get_stage_steps(str(inspection_id), stage_dir)
+    except (
+        InspectionNotFoundError,
+        InspectionFileNotFoundError,
+        InvalidPathError,
+        MalformedInspectionDataError,
+    ) as exc:
+        _raise_http_for(exc)
+
+
+@router.get(
+    "/inspection/{inspection_id}/artifacts",
+    response_model=list[ArtifactEntry],
+    summary="List captured artefacts derived from manifest.json",
+)
+async def list_artifacts(
+    inspection_id: UUID4 = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> list[ArtifactEntry]:
+    try:
+        return await reader.list_artifacts(str(inspection_id))
+    except (
+        InspectionNotFoundError,
+        InspectionFileNotFoundError,
+        MalformedInspectionDataError,
+    ) as exc:
+        _raise_http_for(exc)
+
+
+@router.get(
+    "/inspection/{inspection_id}/tests/summary",
+    summary="Parsed JUnit summary (tests/junit_summary.json)",
+)
+async def get_test_summary(
+    inspection_id: UUID4 = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> dict[str, Any]:
+    try:
+        result = await reader.get_test_summary(str(inspection_id))
+    except (InspectionNotFoundError, MalformedInspectionDataError) as exc:
+        _raise_http_for(exc)
+    if result is None:
+        raise HTTPException(
+            status_code=404, detail="tests/junit_summary.json not captured"
+        )
+    return result
+
+
+@router.get(
+    "/inspection/{inspection_id}/build/summary",
+    summary="Parsed build_summary.json",
+)
+async def get_build_summary(
+    inspection_id: UUID4 = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> dict[str, Any]:
+    return await _read_optional_json(
+        reader, str(inspection_id), reader.get_build_summary, "build_summary.json"
+    )
+
+
+@router.get(
+    "/inspection/{inspection_id}/build/params",
+    summary="Parsed build_params.json",
+)
+async def get_build_params(
+    inspection_id: UUID4 = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> dict[str, Any]:
+    return await _read_optional_json(
+        reader, str(inspection_id), reader.get_build_params, "build_params.json"
+    )
+
+
+@router.get(
+    "/inspection/{inspection_id}/build/causes",
+    summary="Parsed build_causes.json",
+)
+async def get_build_causes(
+    inspection_id: UUID4 = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> dict[str, Any]:
+    return await _read_optional_json(
+        reader, str(inspection_id), reader.get_build_causes, "build_causes.json"
+    )
+
+
+@router.get(
+    "/inspection/{inspection_id}/build/environment",
+    summary="Parsed environment.json",
+)
+async def get_environment(
+    inspection_id: UUID4 = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> dict[str, Any]:
+    return await _read_optional_json(
+        reader, str(inspection_id), reader.get_environment, "environment.json"
+    )
+
+
+@router.get(
+    "/inspection/{inspection_id}/build/scm-changelog",
+    summary="Parsed scm_changelog.json",
+)
+async def get_scm_changelog(
+    inspection_id: UUID4 = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> dict[str, Any]:
+    return await _read_optional_json(
+        reader, str(inspection_id), reader.get_scm_changelog, "scm_changelog.json"
+    )
+
+
+@router.get(
+    "/inspection/{inspection_id}/files",
+    response_model=list[RawFileInfo],
+    summary="List raw files under the inspection folder (or a subpath)",
+)
+async def list_files(
+    inspection_id: UUID4 = Path(...),
+    subpath: str = Query("", description="Folder relative to the inspection root"),
+    reader: InspectionReader = Depends(get_reader),
+) -> list[RawFileInfo]:
+    try:
+        return await reader.list_files(str(inspection_id), subpath)
+    except (InspectionNotFoundError, InvalidPathError) as exc:
+        _raise_http_for(exc)
+
+
+@router.get(
+    "/inspection/{inspection_id}/console-log",
+    summary="Full build console log (console.log)",
+    response_class=StreamingResponse,
+)
+async def stream_console_log(
+    inspection_id: UUID4 = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> StreamingResponse:
+    return await _stream(
+        reader, str(inspection_id), reader.stream_console_log, "text/plain; charset=utf-8"
+    )
+
+
+@router.get(
+    "/inspection/{inspection_id}/stages/{stage_dir}/log",
+    summary="Per-stage console log (stages/<dir>/console.log)",
+    response_class=StreamingResponse,
+)
+async def stream_stage_log(
+    inspection_id: UUID4 = Path(...),
+    stage_dir: str = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> StreamingResponse:
+    return await _stream(
+        reader,
+        str(inspection_id),
+        reader.stream_stage_log,
+        "text/plain; charset=utf-8",
+        stage_dir,
+    )
+
+
+@router.get(
+    "/inspection/{inspection_id}/artifacts/{relative_path:path}",
+    summary="Stream a captured artefact",
+    response_class=StreamingResponse,
+)
+async def stream_artifact(
+    inspection_id: UUID4 = Path(...),
+    relative_path: str = Path(..., description="Path under artifacts/"),
+    reader: InspectionReader = Depends(get_reader),
+) -> StreamingResponse:
+    return await _stream(
+        reader,
+        str(inspection_id),
+        reader.stream_artifact,
+        "application/octet-stream",
+        relative_path,
+    )
+
+
+@router.get(
+    "/inspection/{inspection_id}/tests/xml",
+    summary="JUnit XML (tests/junit_report.xml)",
+    response_class=StreamingResponse,
+)
+async def stream_test_xml(
+    inspection_id: UUID4 = Path(...),
+    reader: InspectionReader = Depends(get_reader),
+) -> StreamingResponse:
+    return await _stream(
+        reader, str(inspection_id), reader.stream_test_xml, "application/xml"
+    )
+
+
+@router.get(
+    "/inspection/{inspection_id}/raw",
+    summary="Stream any file under the inspection folder by path",
+    response_class=StreamingResponse,
+)
+async def stream_raw(
+    inspection_id: UUID4 = Path(...),
+    path: str = Query(..., description="Path relative to the inspection folder"),
+    reader: InspectionReader = Depends(get_reader),
+) -> StreamingResponse:
+    return await _stream(
+        reader,
+        str(inspection_id),
+        reader.stream_raw,
+        "application/octet-stream",
+        path,
+    )
+
+
+async def _read_optional_json(
+    reader: InspectionReader,
+    inspection_id: str,
+    method: Callable[[str], Awaitable[dict[str, Any] | None]],
+    file_label: str,
+) -> dict[str, Any]:
+    """Translate `_read_json_optional`-style results to HTTP.
+
+    Catches the same four reader exceptions as ``_stream`` for symmetry —
+    the methods routed through here can only raise two of them today
+    (``InspectionNotFoundError`` from ``_require_inspection``,
+    ``MalformedInspectionDataError`` from JSON parsing), but a future
+    addition that takes a user subpath would also be covered without
+    changing this helper.
+    """
+    try:
+        result = await method(inspection_id)
+    except (
+        InspectionNotFoundError,
+        InspectionFileNotFoundError,
+        InvalidPathError,
+        MalformedInspectionDataError,
+    ) as exc:
+        _raise_http_for(exc)
+    if result is None:
+        raise HTTPException(
+            status_code=404, detail=f"{file_label} not captured"
+        )
+    return result
+
+
+async def _stream(
+    reader: InspectionReader,
+    inspection_id: str,
+    method: Callable[..., AsyncGenerator[bytes, None]],
+    media_type: str,
+    *args: str,
+) -> StreamingResponse:
+    """Build a StreamingResponse, prefetching the first chunk so 404/400 from
+    the reader is translated into the HTTP response *before* StreamingResponse
+    starts the body. Without this, exceptions raised mid-stream would be
+    surfaced as a connection reset rather than a clean status code.
+    """
+    agen = method(inspection_id, *args)
+    try:
+        first = await _peek_first(agen)
+    except (
+        HdlfUnreachableError,
+        InspectionNotFoundError,
+        InspectionFileNotFoundError,
+        InvalidPathError,
+        MalformedInspectionDataError,
+    ) as exc:
+        # Close the underlying async generator before re-raising so any
+        # aiohttp.ClientResponse opened inside `iter_object` is released
+        # immediately, instead of waiting for non-deterministic GC to
+        # finalise it. Async-generator finalisers can run on the wrong
+        # event loop after the request task is gone — explicit aclose()
+        # avoids that surprise.
+        await agen.aclose()
+        _raise_http_for(exc)
+
+    async def _gen():
+        # Mirror of the error-path aclose: even on the happy path the
+        # consumer can disconnect mid-stream (Starlette closes _gen on
+        # client cancellation). The try/finally ensures the wrapped
+        # `agen` — and through it, the HDLF response — is closed
+        # promptly rather than implicitly via the async-generator
+        # finalizer chain. This survives future refactors that might
+        # break the implicit chain.
+        try:
+            if first is not None:
+                yield first
+            async for chunk in agen:
+                yield chunk
+        finally:
+            await agen.aclose()
+
+    return StreamingResponse(_gen(), media_type=media_type)
+
+
+async def _peek_first(agen: AsyncGenerator[bytes, None]) -> bytes | None:
+    """Pull the first chunk so any reader exception fires before streaming.
+
+    Returns None if the iterator is empty.
+    """
+    try:
+        return await agen.__anext__()
+    except StopAsyncIteration:
+        return None
diff --git a/pyproject.toml b/pyproject.toml
index 3db611f2..9eb7af46 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -44,7 +44,7 @@ requires = ["hatchling"]
 build-backend = "hatchling.build"
 
 [tool.hatch.build.targets.wheel]
-packages = ["fl_control_plane"]
+packages = ["fl_control_plane", "fl_shared", "hdlf_server"]
 
 [tool.ruff]
 target-version = "py311"
diff --git a/tests/data_extractor/test_data_extractor.py b/tests/data_extractor/test_data_extractor.py
index 31df1cf2..c522f9f1 100644
--- a/tests/data_extractor/test_data_extractor.py
+++ b/tests/data_extractor/test_data_extractor.py
@@ -45,8 +45,8 @@
     _range_probe,
     _parse_content_range_total,
 )
-from fl_control_plane.hdlf_client import HdlfClient
-from fl_control_plane.hdlf_client.client import FileStatus
+from fl_shared.hdlf_client import HdlfClient
+from fl_shared.hdlf_client.client import FileStatus
 
 
 # Dummy Basic auth token used across test fixtures — encodes "test:test".
@@ -128,15 +128,6 @@ def _cfg(**kwargs):
 # Model unit tests
 # ---------------------------------------------------------------------------
 
-def test_models_capture_item_defaults():
-    """CaptureItem field defaults match the original dataclass."""
-    ci = CaptureItem(key="k", source_url="u")
-    assert ci.is_console_log is False
-    assert ci.is_priority is False
-    assert ci.content_length is None
-    assert ci.node_steps_url is None
-
-
 def test_models_capture_item_is_frozen():
     """CaptureItem instances are immutable."""
     ci = CaptureItem(key="k", source_url="u")
@@ -144,12 +135,6 @@ def test_models_capture_item_is_frozen():
         ci.key = "x"
 
 
-def test_models_download_result_round_trip():
-    """DownloadResult preserves ItemStatus enum value."""
-    dr = DownloadResult(key="k", status=ItemStatus.CAPTURED)
-    assert dr.status is ItemStatus.CAPTURED
-
-
 def test_models_downloader_config_defaults():
     """DownloaderConfig defaults match the original dataclass values."""
     cfg = DownloaderConfig()
@@ -167,34 +152,6 @@ def test_models_downloader_config_accepts_auth_header():
     assert cfg.jenkins_auth_header == "Basic abc"
 
 
-def test_models_extraction_result_defaults():
-    """ExtractionResult defaults match the original dataclass values."""
-    r = ExtractionResult(success=True)
-    assert r.error is None
-    assert r.items_captured == 0
-    assert r.items_skipped == 0
-
-
-def test_models_item_status_str_enum():
-    """ItemStatus preserves str enum behaviour."""
-    assert ItemStatus.CAPTURED.value == "captured"
-    assert ItemStatus.TRUNCATED.value == "truncated"
-    assert ItemStatus.SKIPPED_SIZE.value == "skipped_size"
-    assert ItemStatus.SKIPPED_INSPECTION_CAP.value == "skipped_inspection_cap"
-    assert ItemStatus.SKIPPED_UNREACHABLE.value == "skipped_unreachable"
-
-
-def test_models_import_all_symbols():
-    """All five model symbols import cleanly from fl_control_plane.data_extractor.models."""
-    from fl_control_plane.data_extractor.models import (  # noqa: F401
-        CaptureItem,
-        DownloadResult,
-        DownloaderConfig,
-        ExtractionResult,
-        ItemStatus,
-    )
-
-
 # ---------------------------------------------------------------------------
 # DataExtractorSettings
 # ---------------------------------------------------------------------------
@@ -263,8 +220,10 @@ async def test_priority_before_non_priority(self):
         plan = await build_capture_plan("u1", "https://jenkins.example.com/job/X/1/", jc)
         indices_p = [i for i, x in enumerate(plan) if x.is_priority]
         indices_np = [i for i, x in enumerate(plan) if not x.is_priority]
-        if indices_p and indices_np:
-            assert max(indices_p) < min(indices_np)
+        # Both groups must be present — otherwise the ordering assertion is vacuous.
+        assert indices_p, "expected at least one priority item"
+        assert indices_np, "expected at least one non-priority item"
+        assert max(indices_p) < min(indices_np)
 
     async def test_artifacts_included_in_plan(self):
         jc = _jenkins(artifacts=[
@@ -553,28 +512,17 @@ async def test_already_captured_files_excluded_from_plan(self, mock_dl):
             },
         )
         await extract_data("uuid-r2", hdlf, _jenkins())
-        if mock_dl.call_args:
-            pending_items = mock_dl.call_args[0][0]
-            pending_keys = [item.key for item in pending_items]
-            assert "wfapi_describe.json" not in pending_keys
+        # download_items must have been invoked — otherwise the assertion below is vacuous.
+        assert mock_dl.call_args is not None, "extract_data did not call download_items"
+        pending_items = mock_dl.call_args[0][0]
+        pending_keys = [item.key for item in pending_items]
+        assert "wfapi_describe.json" not in pending_keys
 
 
 # ---------------------------------------------------------------------------
 # DownloaderConfig construction
 # ---------------------------------------------------------------------------
 
-class TestDownloaderConfigStepConcurrency:
-    def test_max_step_concurrency_default_is_ten(self):
-        """DownloaderConfig defaults max_step_concurrency to 10."""
-        cfg = DownloaderConfig()
-        assert cfg.max_step_concurrency == 10
-
-    def test_max_step_concurrency_is_overridable(self):
-        """DownloaderConfig accepts a custom max_step_concurrency value."""
-        cfg = DownloaderConfig(max_step_concurrency=25)
-        assert cfg.max_step_concurrency == 25
-
-
 class TestDownloaderConfigMutation:
     async def test_extract_data_sets_auth_header_when_config_omitted(self):
         """extract_data populates jenkins_auth_header when caller passes config=None."""
@@ -665,8 +613,10 @@ async def test_manifest_written_last(self, mock_dl):
         order = []
         hdlf.put_object_atomic = AsyncMock(side_effect=lambda p, _d: order.append(p))
         await extract_data("uuid-m", hdlf, _jenkins())
-        if order:
-            assert order[-1] == "uuid-m/manifest.json"
+        # At least the manifest write must have happened — otherwise the assertion
+        # would silently pass on a regression that skipped the manifest entirely.
+        assert order, "no put_object_atomic calls — manifest was not written"
+        assert order[-1] == "uuid-m/manifest.json"
 
     @patch("fl_control_plane.data_extractor.extractor.download_items", new_callable=AsyncMock, return_value=[
         DownloadResult(key="console.log", status=ItemStatus.CAPTURED, captured_size=100),
@@ -1317,10 +1267,6 @@ def test_raw_artifact_validates_and_converts(self):
         }).to_artifact()
         assert artifact == Artifact(relative_path="out/x.zip", file_name="x.zip", display_path="out/x.zip")
 
-    def test_output_models_are_importable_from_package(self):
-        """BlueOceanNode, BlueOceanStep, Artifact are importable from fl_control_plane.data_extractor."""
-        from fl_control_plane.data_extractor import BlueOceanNode, BlueOceanStep, Artifact  # noqa: F401
-
 
 # ---------------------------------------------------------------------------
 # JenkinsAPIClient list_nodes / list_steps / list_artifacts / get_stage_steps
@@ -1458,11 +1404,6 @@ async def _list_steps_side_effect(r, node_id):
         assert result_21 == steps_21
         assert client.list_steps.call_count == 2
 
-    def test_steps_cache_initialized_in_init(self):
-        """JenkinsAPIClient._steps_cache is an empty dict immediately after construction."""
-        client = JenkinsAPIClient(username="u", token="t")
-        assert client._steps_cache == {}
-
     async def test_methods_raise_outside_async_context(self):
         """list_nodes raises RuntimeError when called without entering the async context manager."""
         client = JenkinsAPIClient(username="u", token="t")
diff --git a/tests/hdlf_client/test_hdlf_client.py b/tests/hdlf_client/test_hdlf_client.py
index c6e816db..c5167657 100644
--- a/tests/hdlf_client/test_hdlf_client.py
+++ b/tests/hdlf_client/test_hdlf_client.py
@@ -11,7 +11,7 @@
 
 import pytest
 
-from fl_control_plane.hdlf_client.client import HdlfClient, CapExceededError, FileStatus, read_with_fallback
+from fl_shared.hdlf_client.client import HdlfClient, CapExceededError, FileStatus, read_with_fallback
 
 
 # ---------------------------------------------------------------------------
@@ -23,7 +23,7 @@ def _make_client(tmp_path) -> HdlfClient:
     cert_dir = str(tmp_path)
     for name in ("client.crt", "client.key"):
         open(os.path.join(cert_dir, name), "w").close()
-    with patch("fl_control_plane.hdlf_client.client.ssl.create_default_context"):
+    with patch("fl_shared.hdlf_client.client.ssl.create_default_context"):
         return HdlfClient("hdlf.example.sap", "my-container", cert_dir, max_retries=2)
 
 
@@ -59,17 +59,18 @@ async def test_success(self, tmp_path):
         client = _make_client(tmp_path)
         client._session = _make_session(_fake_response(201))
         await client.put_object("/inspections/abc/meta.json", b'{"ok":1}')
+        assert client._session.request.call_count == 1
 
     async def test_retries_on_503(self, tmp_path):
         client = _make_client(tmp_path)
         client._session = _make_session(_fake_response(503), _fake_response(201))
-        with patch("fl_control_plane.hdlf_client.client.asyncio.sleep", new_callable=AsyncMock):
+        with patch("fl_shared.hdlf_client.client.asyncio.sleep", new_callable=AsyncMock):
             await client.put_object("/x", b"data")
 
     async def test_raises_after_max_retries(self, tmp_path):
         client = _make_client(tmp_path)
         client._session = _make_session(_fake_response(503), _fake_response(503))
-        with patch("fl_control_plane.hdlf_client.client.asyncio.sleep", new_callable=AsyncMock):
+        with patch("fl_shared.hdlf_client.client.asyncio.sleep", new_callable=AsyncMock):
             with pytest.raises(IOError):
                 await client.put_object("/x", b"data")
 
@@ -120,11 +121,13 @@ async def test_success(self, tmp_path):
             _fake_response(200, json.dumps({"boolean": True}).encode())
         )
         await client.delete_object("/inspections/abc/old.tmp")
+        assert client._session.request.call_count == 1
 
     async def test_404_is_noop(self, tmp_path):
         client = _make_client(tmp_path)
         client._session = _make_session(_fake_response(404))
         await client.delete_object("/nonexistent")  # should not raise
+        assert client._session.request.call_count == 1
 
 
 # ---------------------------------------------------------------------------
@@ -205,7 +208,7 @@ async def test_respects_retry_after_header(self, tmp_path):
         ok = _fake_response(200, b"data")
         client._session = _make_session(fail, ok)
         slept = []
-        with patch("fl_control_plane.hdlf_client.client.asyncio.sleep", new_callable=AsyncMock, side_effect=lambda x: slept.append(x)):
+        with patch("fl_shared.hdlf_client.client.asyncio.sleep", new_callable=AsyncMock, side_effect=lambda x: slept.append(x)):
             await client.get_object("/x")
         assert slept[0] >= 3.0
 
@@ -297,7 +300,7 @@ async def test_retries_on_503_then_succeeds(self, tmp_path):
         session.request.side_effect = [_make_cm(_fake_response(201))]  # rename
         client._session = session
 
-        with patch("fl_control_plane.hdlf_client.client.asyncio.sleep", new_callable=AsyncMock):
+        with patch("fl_shared.hdlf_client.client.asyncio.sleep", new_callable=AsyncMock):
             await client.put_file_atomic("/folder/file.bin", local)
         assert session.put.call_count == 2
 
@@ -317,7 +320,7 @@ async def test_raises_after_max_retries(self, tmp_path):
         session.request.side_effect = [_make_cm(_fake_response(200, b'{"boolean":true}'))]
         client._session = session
 
-        with patch("fl_control_plane.hdlf_client.client.asyncio.sleep", new_callable=AsyncMock):
+        with patch("fl_shared.hdlf_client.client.asyncio.sleep", new_callable=AsyncMock):
             with pytest.raises(IOError):
                 await client.put_file_atomic("/folder/file.bin", local)
 
diff --git a/tests/hdlf_server/__init__.py b/tests/hdlf_server/__init__.py
new file mode 100644
index 00000000..e69de29b
diff --git a/tests/hdlf_server/conftest.py b/tests/hdlf_server/conftest.py
new file mode 100644
index 00000000..b5334610
--- /dev/null
+++ b/tests/hdlf_server/conftest.py
@@ -0,0 +1,164 @@
+"""hdlf_server-specific fixtures.
+
+Two layers of mocking:
+- `mock_hdlf_client`: an in-memory fake HdlfClient with a settable filesystem
+  dict; consumed directly by reader unit tests.
+- `client`: an HTTPX async client wired to the FastAPI app, with
+  `dependencies.get_reader` overridden to a reader that wraps the fake.
+
+The `HDLF_REST_API_HOST` and `HDLF_CONTAINER_ID` env vars are set so that
+`fl_shared.hdlf_client.config.settings` constructs without raising
+at app import time. The values are dummies — the FakeHdlfClient is what
+actually serves data in tests.
+"""
+
+from __future__ import annotations
+
+import os
+
+# Must be set before any fl_shared.hdlf_client or hdlf_server import.
+os.environ.setdefault("HDLF_REST_API_HOST", "test.invalid")
+os.environ.setdefault("HDLF_CONTAINER_ID", "test-container")
+
+import json
+from collections.abc import AsyncIterator
+from dataclasses import dataclass
+
+import pytest
+import pytest_asyncio
+from httpx import ASGITransport, AsyncClient
+
+
+@dataclass
+class FakeFile:
+    content: bytes
+    is_directory: bool = False
+    modification_time: int = 0
+
+
+class FakeHdlfClient:
+    """In-memory replacement for `HdlfClient` that the reader sees as real.
+
+    Files live in a flat dict keyed by path with a leading "/" stripped.
+    Directories are inferred from path prefixes — there is no explicit
+    mkdirs. This matches how `HdlfClient.list_dir` returns FileStatus
+    entries derived from the WebHDFS LISTSTATUS response.
+    """
+
+    def __init__(self, files: dict[str, bytes] | None = None):
+        self.files: dict[str, FakeFile] = {}
+        for path, content in (files or {}).items():
+            self.files[path.lstrip("/")] = FakeFile(content=content)
+
+    def put(self, path: str, content: bytes | str | dict | list) -> None:
+        if isinstance(content, (dict, list)):
+            data = json.dumps(content).encode()
+        elif isinstance(content, str):
+            data = content.encode()
+        else:
+            data = content
+        self.files[path.lstrip("/")] = FakeFile(content=data)
+
+    # ── HdlfClient methods exercised by the reader ─────────────────────────
+
+    async def exists(self, path: str) -> bool:
+        clean = path.lstrip("/")
+        if clean in self.files:
+            return True
+        # Directory existence: any file under the prefix counts.
+        return any(p.startswith(clean + "/") for p in self.files)
+
+    async def get_object(self, path: str) -> bytes:
+        clean = path.lstrip("/")
+        if clean not in self.files:
+            raise FileNotFoundError(f"FakeHdlfClient: {path}")
+        return self.files[clean].content
+
+    async def get_object_parsed(self, path: str) -> dict:
+        body = await self.get_object(path)
+        try:
+            parsed = json.loads(body)
+        except json.JSONDecodeError as exc:
+            raise ValueError(f"FakeHdlfClient: {path} not JSON: {exc}") from exc
+        if not isinstance(parsed, dict):
+            raise ValueError(
+                f"FakeHdlfClient: {path} not JSON object (got {type(parsed).__name__})"
+            )
+        return parsed
+
+    async def list_dir(self, path: str) -> list:
+        clean = path.lstrip("/").rstrip("/")
+        prefix = "" if clean == "" else clean + "/"
+        seen_dirs: set[str] = set()
+        results = []
+        # Local FileStatus shim — must mirror HdlfClient.FileStatus's attributes.
+        from fl_shared.hdlf_client.client import FileStatus
+
+        for fpath, ff in self.files.items():
+            if not fpath.startswith(prefix):
+                continue
+            tail = fpath[len(prefix):]
+            if "/" in tail:
+                child = tail.split("/", 1)[0]
+                if child not in seen_dirs:
+                    seen_dirs.add(child)
+                    results.append(
+                        FileStatus(
+                            path=f"{prefix}{child}" if prefix else child,
+                            length=0,
+                            modification_time=0,
+                            is_directory=True,
+                        )
+                    )
+            else:
+                results.append(
+                    FileStatus(
+                        path=fpath,
+                        length=len(ff.content),
+                        modification_time=ff.modification_time,
+                        is_directory=False,
+                    )
+                )
+        return results
+
+    async def iter_object(
+        self, path: str, chunk_size: int = 1024
+    ) -> AsyncIterator[bytes]:
+        clean = path.lstrip("/")
+        if clean not in self.files:
+            raise FileNotFoundError(f"FakeHdlfClient: {path}")
+        body = self.files[clean].content
+        for i in range(0, len(body), chunk_size):
+            yield body[i : i + chunk_size]
+
+
+@pytest.fixture
+def fake_hdlf_client() -> FakeHdlfClient:
+    return FakeHdlfClient()
+
+
+@pytest_asyncio.fixture
+async def client(fake_hdlf_client: FakeHdlfClient) -> AsyncIterator[AsyncClient]:
+    """HTTPX async client backed by the FastAPI app + FakeHdlfClient.
+
+    The HdlfClient lifespan is bypassed: we override `get_reader` and
+    `get_client` to return an `InspectionReader` wrapping the fake. The
+    real HdlfClient never opens.
+    """
+    # Import *after* env vars are set at module import time.
+    from hdlf_server.app import create_app
+    from hdlf_server.dependencies import get_client, get_reader
+    from hdlf_server.reader import InspectionReader
+
+    app = create_app()
+    # Skip lifespan startup — it would try to open a real HdlfClient.
+    # ASGITransport supports `lifespan="off"` via context manager parameter.
+    reader = InspectionReader(fake_hdlf_client)  # type: ignore[arg-type]
+    app.dependency_overrides[get_reader] = lambda: reader
+    app.dependency_overrides[get_client] = lambda: fake_hdlf_client
+
+    transport = ASGITransport(app=app)
+    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
+        yield c
+
+    app.dependency_overrides.clear()
diff --git a/tests/hdlf_server/test_reader.py b/tests/hdlf_server/test_reader.py
new file mode 100644
index 00000000..cae358ad
--- /dev/null
+++ b/tests/hdlf_server/test_reader.py
@@ -0,0 +1,541 @@
+"""Unit tests for InspectionReader.
+
+Mocks HdlfClient at its boundary (the FakeHdlfClient in conftest.py).
+Each test puts a minimal set of files into the fake and asserts the
+reader returns the expected typed object or raises the expected
+exception.
+"""
+
+from __future__ import annotations
+
+import pytest
+
+from hdlf_server.exceptions import (
+    InspectionFileNotFoundError,
+    InspectionNotFoundError,
+    InvalidPathError,
+    MalformedInspectionDataError,
+)
+from hdlf_server.reader import InspectionReader, _validate_subpath
+from tests.hdlf_server.conftest import FakeHdlfClient
+
+UUID = "11111111-1111-1111-1111-111111111111"
+
+
+# ── _validate_subpath ────────────────────────────────────────────────────────
+
+def test_validate_subpath_accepts_relative():
+    """Plain relative paths pass through unchanged."""
+    assert _validate_subpath("a/b/c") == "a/b/c"
+
+
+@pytest.mark.parametrize("bad", ["/abs", "..", "a/..", "../b", "a/./b", "a\\b"])
+def test_validate_subpath_rejects_dangerous(bad: str):
+    """Absolute, '..'/'.', and backslash inputs are rejected."""
+    with pytest.raises(InvalidPathError):
+        _validate_subpath(bad)
+
+
+@pytest.mark.parametrize(
+    "bad",
+    [
+        # percent-encoded `..`
+        "%2e%2e/etc/passwd",
+        "%2E%2E/foo",
+        "a/%2e%2e/b",
+        # percent-encoded `/`
+        "..%2fetc",
+        "a%2F..%2Fb",
+        # percent-encoded `\`
+        "a%5cb",
+        # empty segments (would slip past a `"/" in subpath` check)
+        "a//b",
+        "a/",
+        "/a",
+        # NUL byte truncation
+        "a\x00.log",
+    ],
+)
+def test_validate_subpath_rejects_encoded_and_empty(bad: str):
+    """Percent-encoded traversal forms, empty segments, and NUL bytes are rejected.
+
+    These cases protect query-parameter inputs (where Starlette does not
+    decode `%XX` for us) and add defence in depth on path-converter inputs.
+    """
+    with pytest.raises(InvalidPathError):
+        _validate_subpath(bad)
+
+
+@pytest.mark.parametrize(
+    "bad",
+    [
+        # `%252e%252e` -> `%2e%2e` -> `..` (two layers of encoding)
+        "%252e%252e/etc/passwd",
+        # mixed casing across layers — first decode produces `%2E%2e`,
+        # second decode produces `..`
+        "%252E%252e/foo",
+        # `%252f` -> `%2f` -> `/` — outer-encoded slash
+        "a%252f..%252fb",
+        # nested encoding of NUL byte
+        "a%2500.log",
+    ],
+)
+def test_validate_subpath_rejects_double_encoded(bad: str):
+    """Multi-layer percent-encoding is reduced before validation.
+
+    Without the fixed-point decode loop, `%252e%252e` would decode once
+    to `%2e%2e` and pass the `..` check — silently allowing path
+    traversal if any downstream caller decoded the result a second time.
+    """
+    with pytest.raises(InvalidPathError):
+        _validate_subpath(bad)
+
+
+@pytest.mark.parametrize(
+    "good",
+    [
+        # `%25` decodes to a literal `%` — common in real filenames
+        # (Jenkins build URLs, URL-encoded artifact names).
+        "report-50%25.csv",
+        "build-100%25-success.log",
+        # encoded letters that decode to safe characters
+        "%41%42%43.txt",  # decodes to "ABC.txt"
+        # `%` followed by non-hex stays literal
+        "100%pass.txt",
+    ],
+)
+def test_validate_subpath_accepts_literal_percent(good: str):
+    """Filenames with legitimate `%` are NOT rejected by the encoded-decode check.
+
+    Strategy is decode-then-validate, so `%25` (literal `%`) and `%41` (`A`)
+    decode to safe characters — only sequences that decode to the actual
+    forbidden metacharacters (`..`, `/`, `\\`, NUL) trigger rejection.
+    """
+    assert _validate_subpath(good) == good
+
+
+# ── get_metadata ─────────────────────────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_get_metadata_happy_path():
+    """metadata.json is parsed into the typed model."""
+    fake = FakeHdlfClient()
+    fake.put(
+        f"{UUID}/metadata.json",
+        {"jenkins_url": "https://ci/job/foo/42/", "commit_id": "abc"},
+    )
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    md = await reader.get_metadata(UUID)
+    assert md.jenkins_url == "https://ci/job/foo/42/"
+    assert md.commit_id == "abc"
+
+
+@pytest.mark.asyncio
+async def test_get_metadata_missing_inspection():
+    """Missing metadata.json is reported as InspectionNotFoundError carrying the UUID."""
+    fake = FakeHdlfClient()
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    with pytest.raises(InspectionNotFoundError) as exc_info:
+        await reader.get_metadata(UUID)
+    # Lock the contract: the exception must name the UUID we asked for,
+    # not some unrelated thing. Catches a regression where the reader
+    # raises InspectionNotFoundError for the wrong reason (e.g. a typo
+    # in the metadata.json path probe).
+    assert exc_info.value.inspection_uuid == UUID
+
+
+@pytest.mark.asyncio
+async def test_get_metadata_malformed():
+    """Non-JSON content is surfaced as MalformedInspectionDataError."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", b"not json at all")
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    with pytest.raises(MalformedInspectionDataError):
+        await reader.get_metadata(UUID)
+
+
+# ── get_manifest ─────────────────────────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_get_manifest_happy_path():
+    """manifest.json is parsed and items round-trip."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(
+        f"{UUID}/manifest.json",
+        {
+            "version": 1,
+            "inspection_folder": UUID,
+            "items": [
+                {"key": "console.log", "status": "captured", "captured_size": 100},
+                {"key": "artifacts/foo.zip", "status": "skipped_size"},
+            ],
+            "total_captured_bytes": 100,
+        },
+    )
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    manifest = await reader.get_manifest(UUID)
+    assert manifest.inspection_folder == UUID
+    assert len(manifest.items) == 2
+    assert manifest.items[1].status == "skipped_size"
+
+
+@pytest.mark.asyncio
+async def test_get_manifest_inspection_exists_but_no_manifest():
+    """An inspection that hasn't finished extraction returns 404 for manifest specifically."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    with pytest.raises(InspectionFileNotFoundError) as exc_info:
+        await reader.get_manifest(UUID)
+    # The exception must point at manifest.json, not some other missing
+    # file — otherwise a regression that 404s the metadata probe would
+    # silently keep this test green.
+    assert exc_info.value.relative_path == "manifest.json"
+    assert exc_info.value.inspection_uuid == UUID
+
+
+# ── stage tree ───────────────────────────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_get_stage_tree_blue_ocean_primary():
+    """When pipeline_tree.json exists it is the source of truth."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(
+        f"{UUID}/pipeline_tree.json",
+        [{"id": "5", "displayName": "Build", "result": "FAILURE"}],
+    )
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    tree = await reader.get_stage_tree(UUID)
+    assert tree.source == "blue_ocean"
+    assert len(tree.nodes) == 1
+    assert tree.nodes[0].result == "FAILURE"
+
+
+@pytest.mark.asyncio
+async def test_get_stage_tree_wfapi_fallback():
+    """Without pipeline_tree.json, WFAPI is used as the fallback source."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(
+        f"{UUID}/wfapi_describe.json",
+        {"stages": [{"id": "5", "name": "Build", "status": "FAILED"}]},
+    )
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    tree = await reader.get_stage_tree(UUID)
+    assert tree.source == "wfapi"
+    assert tree.nodes == []
+    assert len(tree.wfapi_stages) == 1
+
+
+@pytest.mark.asyncio
+async def test_get_stage_tree_both_sources_blue_ocean_wins():
+    """When both files exist, Blue Ocean is primary AND wfapi_stages is still populated.
+
+    The previous tests only covered "blue_ocean only" and "wfapi only" —
+    neither verified that the Blue Ocean preference does NOT throw away
+    the WFAPI data when both are present. The reader's documented
+    contract (StageTree docstring) says wfapi_stages is "always
+    populated when wfapi_describe.json exists, regardless of source".
+    """
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(
+        f"{UUID}/pipeline_tree.json",
+        [{"id": "5", "displayName": "Build", "result": "FAILURE"}],
+    )
+    fake.put(
+        f"{UUID}/wfapi_describe.json",
+        {"stages": [{"id": "5", "name": "Build", "status": "FAILED"}]},
+    )
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    tree = await reader.get_stage_tree(UUID)
+    assert tree.source == "blue_ocean"
+    assert len(tree.nodes) == 1
+    # The assertion the existing tests miss — both sources land in the response.
+    assert len(tree.wfapi_stages) == 1
+    assert tree.wfapi_stages[0].id == "5"
+
+
+@pytest.mark.asyncio
+async def test_get_stage_tree_neither_present():
+    """If neither tree file is present we 404 the file, not the inspection."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    with pytest.raises(InspectionFileNotFoundError) as exc_info:
+        await reader.get_stage_tree(UUID)
+    # The exception must mention BOTH candidate files. A regression that
+    # only mentions one (e.g. the WFAPI fallback was dropped from the
+    # message) would otherwise pass.
+    assert "pipeline_tree.json" in exc_info.value.relative_path
+    assert "wfapi_describe.json" in exc_info.value.relative_path
+
+
+@pytest.mark.asyncio
+async def test_get_stage_tree_wfapi_malformed_raises_502():
+    """A WFAPI stage missing the required `id` raises MalformedInspectionDataError.
+
+    Guards the boundary contract: schema drift on the WFAPI side must
+    surface as a 502 (router translation), not as untyped data
+    flowing through to consumers. Without WfapiStage, this would have
+    silently returned a stage with no `id` and a downstream KeyError.
+    """
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(
+        f"{UUID}/wfapi_describe.json",
+        {"stages": [{"name": "Build", "status": "FAILED"}]},  # no `id`
+    )
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    with pytest.raises(MalformedInspectionDataError):
+        await reader.get_stage_tree(UUID)
+
+
+# ── list_stages ──────────────────────────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_list_stages_happy_path():
+    """Each stage subfolder is reported with the files it actually contains."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(f"{UUID}/stages/Build/console.log", b"x")
+    fake.put(f"{UUID}/stages/Build/steps.json", b"[]")
+    fake.put(f"{UUID}/stages/Test/wfapi_describe.json", b"{}")
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    stages = await reader.list_stages(UUID)
+    by_dir = {s.dir: s for s in stages}
+    assert by_dir["Build"].has_console_log is True
+    assert by_dir["Build"].has_steps_json is True
+    assert by_dir["Build"].has_wfapi_describe is False
+    assert by_dir["Test"].has_wfapi_describe is True
+
+
+@pytest.mark.asyncio
+async def test_list_stages_populates_result_from_blue_ocean_tree():
+    """`result` field is populated by joining stage dirs with pipeline_tree.json.
+
+    Regression test for the bug where `result_by_id` was keyed by Blue
+    Ocean numeric node ids (e.g. "5") but the lookup used directory names
+    (e.g. "Build"), so `result` was always None for unique stage names.
+    The reader now mirrors the extractor's naming logic to produce keys
+    that actually match what the extractor wrote to disk.
+    """
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(
+        f"{UUID}/pipeline_tree.json",
+        [
+            {"id": "5", "displayName": "Build", "result": "SUCCESS"},
+            {"id": "7", "displayName": "Test", "result": "FAILURE"},
+        ],
+    )
+    fake.put(f"{UUID}/stages/Build/console.log", b"x")
+    fake.put(f"{UUID}/stages/Test/console.log", b"x")
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    stages = await reader.list_stages(UUID)
+    by_dir = {s.dir: s for s in stages}
+    assert by_dir["Build"].result == "SUCCESS"
+    assert by_dir["Test"].result == "FAILURE"
+
+
+@pytest.mark.asyncio
+async def test_list_stages_handles_collision_suffix():
+    """Duplicate display names get `_<node_id>` suffixes; each gets its own result.
+
+    The extractor names the second occurrence of "Deploy" as
+    `Deploy_21` (where 21 is the Blue Ocean node id). The reader must
+    return the correct per-instance result for each.
+    """
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(
+        f"{UUID}/pipeline_tree.json",
+        [
+            {"id": "20", "displayName": "Deploy", "result": "SUCCESS"},
+            {"id": "21", "displayName": "Deploy", "result": "FAILURE"},
+        ],
+    )
+    fake.put(f"{UUID}/stages/Deploy/console.log", b"x")
+    fake.put(f"{UUID}/stages/Deploy_21/console.log", b"x")
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    stages = await reader.list_stages(UUID)
+    by_dir = {s.dir: s for s in stages}
+    assert by_dir["Deploy"].result == "SUCCESS"
+    assert by_dir["Deploy_21"].result == "FAILURE"
+
+
+@pytest.mark.asyncio
+async def test_list_stages_preserves_underscores_in_name():
+    """A stage display name with a literal underscore is NOT mistaken for a collision suffix.
+
+    Regression test for the previous heuristic that did
+    `dir_name.split("_", 1)[0]`, which turned "Integration_Test" into
+    "Integration". The new logic only strips a trailing `_<digits>`
+    segment, so "Integration_Test" survives intact and the legitimate
+    underscore-bearing name is preserved.
+    """
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(
+        f"{UUID}/pipeline_tree.json",
+        [{"id": "9", "displayName": "Integration_Test", "result": "SUCCESS"}],
+    )
+    fake.put(f"{UUID}/stages/Integration_Test/console.log", b"x")
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    stages = await reader.list_stages(UUID)
+    by_dir = {s.dir: s for s in stages}
+    # `name` reconstruction must preserve the underscore.
+    assert by_dir["Integration_Test"].name == "Integration_Test"
+    # And the result join must still succeed.
+    assert by_dir["Integration_Test"].result == "SUCCESS"
+
+
+# ── get_stage_steps ──────────────────────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_get_stage_steps_rejects_traversal():
+    """Path traversal attempts in stage_dir hit InvalidPathError."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    with pytest.raises(InvalidPathError):
+        await reader.get_stage_steps(UUID, "../escape")
+
+
+@pytest.mark.asyncio
+async def test_get_stage_steps_happy_path():
+    """steps.json is parsed into a list of StepInfo."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(
+        f"{UUID}/stages/Build/steps.json",
+        [{"id": "9", "displayName": "compile", "result": "SUCCESS"}],
+    )
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    steps = await reader.get_stage_steps(UUID, "Build")
+    assert len(steps) == 1
+    assert steps[0].display_name == "compile"
+
+
+# ── streaming ────────────────────────────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_stream_console_log_returns_bytes():
+    """stream_console_log emits bytes from the underlying file."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(f"{UUID}/console.log", b"hello world")
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    chunks = [c async for c in reader.stream_console_log(UUID)]
+    assert b"".join(chunks) == b"hello world"
+
+
+@pytest.mark.asyncio
+async def test_stream_console_log_missing():
+    """Missing console.log surfaces as InspectionFileNotFoundError naming the file."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    gen = reader.stream_console_log(UUID)
+    with pytest.raises(InspectionFileNotFoundError) as exc_info:
+        await gen.__anext__()
+    # Must specifically blame console.log, not e.g. metadata.json — guards
+    # against the existence-probe path being misreported as the streamed
+    # file.
+    assert exc_info.value.relative_path == "console.log"
+
+
+@pytest.mark.asyncio
+async def test_stream_artifact_rejects_traversal():
+    """Path traversal in artifact relative_path is rejected."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    gen = reader.stream_artifact(UUID, "../etc/passwd")
+    with pytest.raises(InvalidPathError):
+        await gen.__anext__()
+
+
+# ── list_artifacts ───────────────────────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_list_artifacts_filters_manifest():
+    """Only artifacts/ keys are surfaced; status and size fields flow through."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(
+        f"{UUID}/manifest.json",
+        {
+            "inspection_folder": UUID,
+            "items": [
+                {"key": "console.log", "status": "captured"},
+                {"key": "artifacts/build.log", "status": "captured", "captured_size": 5},
+                {"key": "artifacts/foo.zip", "status": "skipped_size"},
+            ],
+        },
+    )
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    artifacts = await reader.list_artifacts(UUID)
+    by_path = {a.relative_path: a for a in artifacts}
+    # Lock the contract: artefacts/ prefix stripped, console.log filtered out.
+    assert set(by_path) == {"build.log", "foo.zip"}
+    # Captured items keep their status and size.
+    assert by_path["build.log"].status == "captured"
+    assert by_path["build.log"].captured_size == 5
+    # Skipped items must still appear (consumer needs to see what was
+    # attempted but not stored), with status preserved and size None.
+    assert by_path["foo.zip"].status == "skipped_size"
+    assert by_path["foo.zip"].captured_size is None
+
+
+# ── list_files ──────────────────────────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_list_files_returns_relative_paths():
+    """Paths in the response are relative to the inspection folder."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(f"{UUID}/console.log", b"x")
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    files = await reader.list_files(UUID)
+    paths = {f.path for f in files}
+    assert "metadata.json" in paths
+    assert "console.log" in paths
+    assert all(not p.startswith(UUID) for p in paths)
+
+
+@pytest.mark.asyncio
+async def test_list_files_subpath():
+    """Listing a subpath returns its direct children."""
+    fake = FakeHdlfClient()
+    fake.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake.put(f"{UUID}/stages/Build/console.log", b"x")
+    fake.put(f"{UUID}/stages/Build/steps.json", b"[]")
+    reader = InspectionReader(fake)  # type: ignore[arg-type]
+
+    files = await reader.list_files(UUID, "stages/Build")
+    paths = {f.path for f in files}
+    assert paths == {"stages/Build/console.log", "stages/Build/steps.json"}
diff --git a/tests/hdlf_server/test_router.py b/tests/hdlf_server/test_router.py
new file mode 100644
index 00000000..0bdca742
--- /dev/null
+++ b/tests/hdlf_server/test_router.py
@@ -0,0 +1,362 @@
+"""Integration tests for the hdlf_server FastAPI app.
+
+Exercises endpoints end-to-end against a FakeHdlfClient via the `client`
+fixture in conftest.py.
+"""
+
+from __future__ import annotations
+
+import pytest
+from httpx import AsyncClient
+
+UUID = "11111111-1111-1111-1111-111111111111"
+MISSING_UUID = "22222222-2222-2222-2222-222222222222"
+
+
+# ── /healthz ────────────────────────────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_healthz(client: AsyncClient):
+    """Liveness probe is unauthenticated and always 200."""
+    resp = await client.get("/healthz")
+    assert resp.status_code == 200
+    assert resp.json() == {"status": "alive"}
+
+
+# ── /api/v1/inspection/{id}/metadata ────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_get_metadata_happy(client: AsyncClient, fake_hdlf_client):
+    """Metadata round-trips as JSON."""
+    fake_hdlf_client.put(
+        f"{UUID}/metadata.json",
+        {"jenkins_url": "https://ci/job/x/1/", "commit_id": "abc"},
+    )
+    resp = await client.get(f"/api/v1/inspection/{UUID}/metadata")
+    assert resp.status_code == 200
+    body = resp.json()
+    assert body["jenkins_url"] == "https://ci/job/x/1/"
+
+
+@pytest.mark.asyncio
+async def test_get_metadata_404(client: AsyncClient):
+    """Missing inspection returns 404."""
+    resp = await client.get(f"/api/v1/inspection/{MISSING_UUID}/metadata")
+    assert resp.status_code == 404
+
+
+@pytest.mark.asyncio
+async def test_get_metadata_invalid_uuid(client: AsyncClient):
+    """Non-UUID path segment is rejected by FastAPI as 422."""
+    resp = await client.get("/api/v1/inspection/not-a-uuid/metadata")
+    assert resp.status_code == 422
+
+
+# ── /manifest, /stage-tree, /stages, /steps ──────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_get_manifest(client: AsyncClient, fake_hdlf_client):
+    """Manifest items round-trip with their statuses."""
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake_hdlf_client.put(
+        f"{UUID}/manifest.json",
+        {
+            "inspection_folder": UUID,
+            "items": [{"key": "console.log", "status": "captured"}],
+        },
+    )
+    resp = await client.get(f"/api/v1/inspection/{UUID}/manifest")
+    assert resp.status_code == 200
+    assert resp.json()["items"][0]["status"] == "captured"
+
+
+@pytest.mark.asyncio
+async def test_get_stage_tree(client: AsyncClient, fake_hdlf_client):
+    """Stage tree is returned with source=blue_ocean when nodes file exists."""
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake_hdlf_client.put(
+        f"{UUID}/pipeline_tree.json", [{"id": "5", "result": "FAILURE"}]
+    )
+    resp = await client.get(f"/api/v1/inspection/{UUID}/stage-tree")
+    assert resp.status_code == 200
+    body = resp.json()
+    assert body["source"] == "blue_ocean"
+    assert body["nodes"][0]["id"] == "5"
+
+
+@pytest.mark.asyncio
+async def test_list_stages(client: AsyncClient, fake_hdlf_client):
+    """Each stage subfolder is listed with its file presence flags."""
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake_hdlf_client.put(f"{UUID}/stages/Build/console.log", b"x")
+    fake_hdlf_client.put(f"{UUID}/stages/Build/steps.json", b"[]")
+
+    resp = await client.get(f"/api/v1/inspection/{UUID}/stages")
+    assert resp.status_code == 200
+    body = resp.json()
+    by_dir = {s["dir"]: s for s in body}
+    assert by_dir["Build"]["has_console_log"] is True
+    assert by_dir["Build"]["has_steps_json"] is True
+
+
+@pytest.mark.asyncio
+async def test_get_stage_steps(client: AsyncClient, fake_hdlf_client):
+    """Steps for a stage are parsed and returned."""
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake_hdlf_client.put(
+        f"{UUID}/stages/Build/steps.json",
+        [{"id": "9", "displayName": "compile"}],
+    )
+    resp = await client.get(f"/api/v1/inspection/{UUID}/stages/Build/steps")
+    assert resp.status_code == 200
+    # FastAPI/Pydantic serialises with aliases — keys are Blue Ocean's
+    # camelCase (matches the JSON the Data Extractor wrote in steps.json).
+    assert resp.json()[0]["displayName"] == "compile"
+
+
+# ── streaming ────────────────────────────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_stream_console_log(client: AsyncClient, fake_hdlf_client):
+    """The full console log streams back as text/plain."""
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake_hdlf_client.put(f"{UUID}/console.log", b"line1\nline2\n")
+
+    resp = await client.get(f"/api/v1/inspection/{UUID}/console-log")
+    assert resp.status_code == 200
+    assert resp.headers["content-type"].startswith("text/plain")
+    assert resp.content == b"line1\nline2\n"
+
+
+@pytest.mark.asyncio
+async def test_stream_console_log_404(client: AsyncClient, fake_hdlf_client):
+    """Missing console.log surfaces as 404 *before* streaming starts."""
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    resp = await client.get(f"/api/v1/inspection/{UUID}/console-log")
+    assert resp.status_code == 404
+
+
+@pytest.mark.asyncio
+async def test_stream_artifact(client: AsyncClient, fake_hdlf_client):
+    """Artefacts stream as application/octet-stream."""
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake_hdlf_client.put(f"{UUID}/artifacts/build.log", b"hello")
+
+    resp = await client.get(f"/api/v1/inspection/{UUID}/artifacts/build.log")
+    assert resp.status_code == 200
+    assert resp.headers["content-type"] == "application/octet-stream"
+    assert resp.content == b"hello"
+
+
+@pytest.mark.asyncio
+async def test_stream_raw_path_traversal_rejected(
+    client: AsyncClient, fake_hdlf_client
+):
+    """Traversal in the `path` query is rejected with 400."""
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    resp = await client.get(
+        f"/api/v1/inspection/{UUID}/raw", params={"path": "../escape"}
+    )
+    assert resp.status_code == 400
+
+
+# ── /artifacts list ──────────────────────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_list_artifacts(client: AsyncClient, fake_hdlf_client):
+    """Artefact entries are derived from manifest items."""
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake_hdlf_client.put(
+        f"{UUID}/manifest.json",
+        {
+            "inspection_folder": UUID,
+            "items": [
+                {"key": "console.log", "status": "captured"},
+                {"key": "artifacts/foo.zip", "status": "captured", "captured_size": 9},
+            ],
+        },
+    )
+    resp = await client.get(f"/api/v1/inspection/{UUID}/artifacts")
+    assert resp.status_code == 200
+    assert resp.json() == [
+        {
+            "relative_path": "foo.zip",
+            "status": "captured",
+            "original_size": None,
+            "captured_size": 9,
+        }
+    ]
+
+
+# ── /files ───────────────────────────────────────────────────────────────────
+
+@pytest.mark.asyncio
+async def test_list_files_root(client: AsyncClient, fake_hdlf_client):
+    """The inspection root lists known files with paths relative to the folder."""
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake_hdlf_client.put(f"{UUID}/console.log", b"x")
+
+    resp = await client.get(f"/api/v1/inspection/{UUID}/files")
+    assert resp.status_code == 200
+    paths = {f["path"] for f in resp.json()}
+    assert paths == {"metadata.json", "console.log"}
+
+
+# ── Path-traversal hardening (CR-02) ─────────────────────────────────────────
+
+@pytest.mark.asyncio
+@pytest.mark.parametrize(
+    "encoded",
+    [
+        "%2E%2E%2Fmetadata.json",   # ../metadata.json
+        "%2e%2e/metadata.json",     # mixed case
+        "..%2Fmetadata.json",       # encoded slash only
+    ],
+)
+async def test_stream_raw_rejects_percent_encoded_traversal(
+    client: AsyncClient, fake_hdlf_client, encoded: str
+):
+    """Percent-encoded traversal in the `path` query is rejected with 400.
+
+    Query-string values are not decoded by Starlette before reaching the
+    handler, so the validator must catch the encoded forms itself.
+    """
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    resp = await client.get(
+        f"/api/v1/inspection/{UUID}/raw", params={"path": encoded}
+    )
+    assert resp.status_code == 400
+
+
+@pytest.mark.asyncio
+@pytest.mark.parametrize(
+    "encoded",
+    [
+        "%2E%2E%2Fmetadata.json",
+        "..%2Fescape",
+        "a%5Cb",
+    ],
+)
+async def test_list_files_rejects_percent_encoded_traversal(
+    client: AsyncClient, fake_hdlf_client, encoded: str
+):
+    """The `subpath` query parameter on /files is hardened against encoded traversal."""
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    resp = await client.get(
+        f"/api/v1/inspection/{UUID}/files", params={"subpath": encoded}
+    )
+    assert resp.status_code == 400
+
+
+@pytest.mark.asyncio
+async def test_stream_artifact_rejects_percent_encoded_traversal(
+    client: AsyncClient, fake_hdlf_client
+):
+    """Encoded `..` in the artefact path is rejected by the validator with 400.
+
+    Starlette decodes the path segment before route matching, so the
+    decoded form (`../metadata.json`) reaches the handler — at which
+    point ``_validate_subpath`` rejects it. We assert exactly 400 so a
+    regression that quietly turns this into a 404 (route mismatch) or a
+    500 (unhandled exception) fails the test.
+    """
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    resp = await client.get(
+        f"/api/v1/inspection/{UUID}/artifacts/%2E%2E%2Fmetadata.json"
+    )
+    assert resp.status_code == 400
+
+
+@pytest.mark.asyncio
+async def test_stage_dir_rejects_percent_encoded_slash(
+    client: AsyncClient, fake_hdlf_client
+):
+    """Encoded slash inside stage_dir cannot be used to escape the stage subfolder.
+
+    On Starlette/uvicorn, ``%2F`` inside a single-segment path parameter is
+    NOT decoded before route matching, so the URL
+    ``/stages/..%2F..%2Fmetadata.json/steps`` does not match the
+    ``/stages/{stage_dir}/steps`` route — the request 404s before reaching
+    the validator. The security property we care about is "did not leak
+    metadata.json", which 404 satisfies; locking the assertion to 404
+    means a regression that DID start matching the route (and failed to
+    reject the embedded slash) would fail the test instead of silently
+    masquerading as the same loose-bounded result.
+    """
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    resp = await client.get(
+        f"/api/v1/inspection/{UUID}/stages/..%2F..%2Fmetadata.json/steps"
+    )
+    assert resp.status_code == 404
+
+
+@pytest.mark.asyncio
+async def test_get_stage_tree_wfapi_malformed_returns_502(client: AsyncClient, fake_hdlf_client):
+    """A WFAPI stage missing the required `id` surfaces as HTTP 502 (malformed data)."""
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    fake_hdlf_client.put(
+        f"{UUID}/wfapi_describe.json",
+        {"stages": [{"name": "Build", "status": "FAILED"}]},  # no `id`
+    )
+    resp = await client.get(f"/api/v1/inspection/{UUID}/stage-tree")
+    assert resp.status_code == 502
+
+
+@pytest.mark.asyncio
+async def test_stream_returns_502_when_hdlf_unreachable(client: AsyncClient, fake_hdlf_client):
+    """An IOError from HdlfClient (exhausted retries) surfaces as HTTP 502, not 500.
+
+    Simulates the failure mode of `iter_object` when tenacity gives up:
+    HdlfClient raises `IOError("... failed after retries: HTTP 503")`.
+    The reader translates that to `HdlfUnreachableError`, which the
+    router maps to 502. Without the translation the router falls
+    through to the generic 500 handler — indistinguishable from a
+    programming bug.
+    """
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+
+    async def _broken_iter(path: str, chunk_size: int = 1024):
+        # Match the real HdlfClient.iter_object signature: an async
+        # generator. Raising before the first yield exercises the
+        # exception path that `_peek_first` is designed to catch.
+        raise IOError(f"iter_object {path} failed after retries: HTTP 503")
+        yield b""  # unreachable; required to make this an async generator
+
+    fake_hdlf_client.iter_object = _broken_iter  # type: ignore[method-assign]
+
+    resp = await client.get(f"/api/v1/inspection/{UUID}/console-log")
+    assert resp.status_code == 502
+
+
+@pytest.mark.asyncio
+async def test_stream_aclose_called_on_error_path(client: AsyncClient, fake_hdlf_client):
+    """When the streaming endpoint errors before yielding, the underlying generator is closed.
+
+    Without the explicit `await agen.aclose()` in `_stream`'s except
+    block, the wrapping reader generator (and any HDLF response it
+    holds) would only be cleaned up by non-deterministic GC. This
+    test instruments `iter_object` to record close events and asserts
+    one is observed when the request fails with a translatable
+    exception.
+    """
+    fake_hdlf_client.put(f"{UUID}/metadata.json", {"jenkins_url": "u"})
+    close_count = {"n": 0}
+
+    async def _failing_then_observable(path: str, chunk_size: int = 1024):
+        try:
+            # Raise immediately so `_peek_first` triggers the error
+            # branch in `_stream`. The reader's `_stream_or_404` wraps
+            # this into HdlfUnreachableError → HTTP 502.
+            raise IOError(f"iter_object {path} failed after retries: HTTP 503")
+            yield b""  # unreachable; required to make this a generator
+        finally:
+            # `_stream`'s aclose() drains the generator → finally block
+            # runs → counter ticks. Without the aclose() call this only
+            # fires on GC, which is non-deterministic in tests.
+            close_count["n"] += 1
+
+    fake_hdlf_client.iter_object = _failing_then_observable  # type: ignore[method-assign]
+
+    resp = await client.get(f"/api/v1/inspection/{UUID}/console-log")
+    assert resp.status_code == 502
+    assert close_count["n"] == 1, "expected `agen.aclose()` to run exactly once"
diff --git a/tests/metadata_extractor/test_metadata_extractor.py b/tests/metadata_extractor/test_metadata_extractor.py
index b828fb2c..7670f260 100644
--- a/tests/metadata_extractor/test_metadata_extractor.py
+++ b/tests/metadata_extractor/test_metadata_extractor.py
@@ -12,7 +12,7 @@
 
 import pytest
 
-from fl_control_plane.hdlf_client import HdlfClient
+from fl_shared.hdlf_client import HdlfClient
 from fl_control_plane.metadata_extractor import extract_metadata, ExtractionResult
 from fl_control_plane.metadata_extractor.extractor import _fetch_build_info
 

```
