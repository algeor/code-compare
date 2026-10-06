# 59ece7aefacfc969

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/28
Suggested label: 35%
File overlap: 1.0
Changed-line overlap: 0.0

## Suggested diff
```diff
--- a/tests/test_schema_isolation.py
+++ b/tests/test_schema_isolation.py
@@
+class TestEnsureHanaSchema:
+    """Validates the _ensure_hana_schema helper behavior in Alembic env."""
+
+    @patch("db.migrations.env.settings")
+    def test_set_schema_called_for_hana(self, mock_settings: MagicMock) -> None:
+        """SET SCHEMA is issued when dialect is hana and db_schema is set."""
+        mock_settings.db_schema = "my-namespace"
+
+        mock_connection = MagicMock()
+        mock_connection.dialect.name = "hana"
+
+        _ensure_hana_schema(mock_connection)
+
+        mock_connection.execute.assert_called()
+        call_args = mock_connection.execute.call_args[0]
+        assert 'SET SCHEMA "my-namespace"' in str(call_args[0])
+        mock_connection.commit.assert_called_once()
+
+    @patch("db.migrations.env.settings")
+    def test_no_op_for_sqlite(self, mock_settings: MagicMock) -> None:
+        """SQLite connections skip SET SCHEMA entirely."""
+        mock_settings.db_schema = "my-namespace"
+
+        mock_connection = MagicMock()
+        mock_connection.dialect.name = "sqlite"
+
+        _ensure_hana_schema(mock_connection)
+
+        mock_connection.execute.assert_not_called()
+
+    @patch("db.migrations.env.settings")
+    def test_no_op_when_schema_empty(self, mock_settings: MagicMock) -> None:
+        """No SET SCHEMA when db_schema is empty (single-tenant mode)."""
+        mock_settings.db_schema = ""
+
+        mock_connection = MagicMock()
+        mock_connection.dialect.name = "hana"
+
+        _ensure_hana_schema(mock_connection)
+
+        mock_connection.execute.assert_not_called()
+
+    @patch("db.migrations.env.settings")
+    def test_escapes_double_quotes_in_schema_name(self, mock_settings: MagicMock) -> None:
+        """Double quotes in schema names are escaped to prevent injection."""
+        mock_settings.db_schema = 'ns"injection'
+
+        mock_connection = MagicMock()
+        mock_connection.dialect.name = "hana"
+
+        _ensure_hana_schema(mock_connection)
+
+        mock_connection.execute.assert_called()
+        call_args = mock_connection.execute.call_args[0]
+        assert 'SET SCHEMA "ns""injection"' in str(call_args[0])
```

## Landed PR diff
```diff
diff --git a/Dockerfile b/Dockerfile
index 3927005d..e1c310a5 100644
--- a/Dockerfile
+++ b/Dockerfile
@@ -1,5 +1,6 @@
 FROM keppel.eu-de-1.cloud.sap/hana-qa-infrastructure/infra/sles15-sp6-app-pyenv-minimal-3.14 AS builder
 
+USER root
 WORKDIR /build
 
 COPY pyproject.toml ./
@@ -12,7 +13,7 @@ FROM keppel.eu-de-1.cloud.sap/hana-qa-infrastructure/infra/sles15-sp6-app-pyenv-
 
 WORKDIR /home/app/app
 
-COPY --from=builder /build/wheels/*.whl /tmp/
+COPY --from=builder --chown=app:app /build/wheels/*.whl /tmp/
 
 RUN WHEEL=$(ls /tmp/*.whl) \
     && pip install --no-cache-dir "${WHEEL}" \
@@ -24,6 +25,10 @@ RUN WHEEL=$(ls /tmp/*.whl) \
 COPY alembic.ini ./
 COPY db/ ./db/
 
+ENV PYTHONDONTWRITEBYTECODE=1
+
+USER 1001
+
 EXPOSE 8000
 
 CMD ["uvicorn", "fl_control_plane.ingestion_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
diff --git a/chart/templates/_helpers.tpl b/chart/templates/_helpers.tpl
new file mode 100644
index 00000000..e078b43b
--- /dev/null
+++ b/chart/templates/_helpers.tpl
@@ -0,0 +1,28 @@
+{{- define "fl-control-plane.name" -}}
+{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
+{{- end }}
+
+{{- define "fl-control-plane.fullname" -}}
+{{- if .Values.fullnameOverride }}
+{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
+{{- else }}
+{{- $name := default .Chart.Name .Values.nameOverride }}
+{{- if contains $name .Release.Name }}
+{{- .Release.Name | trunc 63 | trimSuffix "-" }}
+{{- else }}
+{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
+{{- end }}
+{{- end }}
+{{- end }}
+
+{{- define "fl-control-plane.selectorLabels" -}}
+app.kubernetes.io/name: {{ include "fl-control-plane.name" . }}
+app.kubernetes.io/instance: {{ .Release.Name }}
+{{- end }}
+
+{{- define "fl-control-plane.labels" -}}
+helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
+{{ include "fl-control-plane.selectorLabels" . }}
+app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
+app.kubernetes.io/managed-by: {{ .Release.Service }}
+{{- end }}
diff --git a/chart/templates/apirule.yaml b/chart/templates/apirule.yaml
index 4e4763ff..d5108f91 100644
--- a/chart/templates/apirule.yaml
+++ b/chart/templates/apirule.yaml
@@ -12,15 +12,15 @@
 apiVersion: gateway.kyma-project.io/v2
 kind: APIRule
 metadata:
-  name: {{ .Chart.Name }}
+  name: {{ include "fl-control-plane.fullname" . }}
   labels:
-    app: {{ .Chart.Name }}
+    {{- include "fl-control-plane.labels" . | nindent 4 }}
 spec:
   gateway: kyma-system/kyma-gateway
   hosts:
-    - {{ .Values.apirule.host }}
+    - {{ .Values.apirule.host }}-{{ .Release.Namespace }}
   service:
-    name: {{ .Chart.Name }}
+    name: {{ include "fl-control-plane.fullname" . }}
     port: {{ .Values.service.port }}
   rules:
     - path: /healthz
diff --git a/chart/templates/configmap.yaml b/chart/templates/configmap.yaml
new file mode 100644
index 00000000..39cadb5d
--- /dev/null
+++ b/chart/templates/configmap.yaml
@@ -0,0 +1,10 @@
+apiVersion: v1
+kind: ConfigMap
+metadata:
+  name: {{ include "fl-control-plane.fullname" . }}-config
+  labels:
+    {{- include "fl-control-plane.labels" . | nindent 4 }}
+data:
+  {{- range $key, $value := .Values.config }}
+  {{ $key }}: {{ $value | quote }}
+  {{- end }}
diff --git a/chart/templates/db-migrate-job.yaml b/chart/templates/db-migrate-job.yaml
new file mode 100644
index 00000000..fcf30e73
--- /dev/null
+++ b/chart/templates/db-migrate-job.yaml
@@ -0,0 +1,130 @@
+apiVersion: batch/v1
+kind: Job
+metadata:
+  name: {{ include "fl-control-plane.fullname" . }}-db-migrate
+  labels:
+    {{- include "fl-control-plane.labels" . | nindent 4 }}
+  annotations:
+    "helm.sh/hook": pre-install,pre-upgrade
+    "helm.sh/hook-weight": "1"
+    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
+spec:
+  backoffLimit: 3
+  activeDeadlineSeconds: 300
+  template:
+    metadata:
+      annotations:
+        sidecar.istio.io/inject: "false"
+      labels:
+        {{- include "fl-control-plane.selectorLabels" . | nindent 8 }}
+    spec:
+      {{- if .Values.database.serviceBinding.enabled }}
+      serviceAccountName: {{ include "fl-control-plane.fullname" . }}-wait
+      {{- end }}
+      {{- if .Values.imagePullSecret.name }}
+      imagePullSecrets:
+        - name: {{ .Values.imagePullSecret.name }}
+      {{- end }}
+      restartPolicy: Never
+      initContainers:
+        {{- if .Values.database.serviceBinding.enabled }}
+        - name: wait-for-secret
+          image: "{{ required "image.repository must be set" .Values.image.repository }}:{{ required "image.tag must be set" .Values.image.tag }}"
+          command:
+            - python3
+            - -c
+            - |
+              import http.client, ssl, sys, time
+              host = "kubernetes.default.svc"
+              token = open("/var/run/secrets/kubernetes.io/serviceaccount/token").read()
+              ca = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
+              ns = "{{ .Release.Namespace }}"
+              secret = "{{ .Values.database.secretName }}"
+              timeout = {{ .Values.database.serviceBinding.timeoutSeconds | default 300 }}
+              ctx = ssl.create_default_context(cafile=ca)
+              deadline = time.monotonic() + timeout
+              while time.monotonic() < deadline:
+                  conn = http.client.HTTPSConnection(host, context=ctx)
+                  conn.request("GET", f"/api/v1/namespaces/{ns}/secrets/{secret}", headers={"Authorization": f"Bearer {token}"})
+                  resp = conn.getresponse()
+                  if resp.status == 200:
+                      print(f"Secret {secret} available.")
+                      sys.exit(0)
+                  print(f"Waiting for BTP to provision secret/{secret}... (HTTP {resp.status})")
+                  conn.close()
+                  time.sleep(5)
+              print(f"Timed out after {timeout}s waiting for secret/{secret}.")
+              sys.exit(1)
+          securityContext:
+            runAsNonRoot: true
+            runAsUser: 1001
+            readOnlyRootFilesystem: true
+          resources:
+            requests:
+              cpu: 50m
+              memory: 128Mi
+            limits:
+              cpu: 100m
+              memory: 256Mi
+        {{- end }}
+      containers:
+        - name: db-migrate
+          image: "{{ required "image.repository must be set" .Values.image.repository }}:{{ required "image.tag must be set" .Values.image.tag }}"
+          imagePullPolicy: {{ .Values.image.pullPolicy | default "IfNotPresent" }}
+          workingDir: /home/app/app
+          command: ["alembic", "upgrade", "head"]
+          env:
+            - name: AUTH_DISABLED
+              value: "true"
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
+          securityContext:
+            runAsNonRoot: true
+            runAsUser: 1001
+            readOnlyRootFilesystem: true
+          volumeMounts:
+            - name: tmp
+              mountPath: /tmp
+            - name: hana-certs
+              mountPath: /etc/hana-certs
+              readOnly: true
+          resources:
+            requests:
+              cpu: 50m
+              memory: 128Mi
+            limits:
+              cpu: 200m
+              memory: 256Mi
+      volumes:
+        - name: tmp
+          emptyDir: {}
+        - name: hana-certs
+          secret:
+            secretName: {{ required "database.secretName must be set" .Values.database.secretName }}
+            items:
+              - key: certificate
+                path: ca.pem
+            optional: true
diff --git a/chart/templates/deployment.yaml b/chart/templates/deployment.yaml
index 5cf1f6d1..04abed8d 100644
--- a/chart/templates/deployment.yaml
+++ b/chart/templates/deployment.yaml
@@ -1,81 +1,112 @@
 apiVersion: apps/v1
 kind: Deployment
 metadata:
-  name: {{ .Chart.Name }}
+  name: {{ include "fl-control-plane.fullname" . }}
   labels:
-    app: {{ .Chart.Name }}
+    {{- include "fl-control-plane.labels" . | nindent 4 }}
 spec:
   replicas: {{ .Values.replicaCount }}
-  # Cap retained ReplicaSets so failed/superseded ones don't accumulate.
   revisionHistoryLimit: 3
   selector:
     matchLabels:
-      app: {{ .Chart.Name }}
+      {{- include "fl-control-plane.selectorLabels" . | nindent 6 }}
+  strategy:
+    type: RollingUpdate
+    rollingUpdate:
+      maxSurge: 1
+      maxUnavailable: 0
   template:
     metadata:
       labels:
-        app: {{ .Chart.Name }}
+        {{- include "fl-control-plane.selectorLabels" . | nindent 8 }}
     spec:
       {{- if .Values.imagePullSecret.name }}
       imagePullSecrets:
         - name: {{ .Values.imagePullSecret.name }}
       {{- end }}
-      initContainers:
-        # Run Alembic migrations against the configured DATABASE_URL before
-        # the API container starts. Reuses the same image so there is no
-        # second build artifact to maintain. AUTH_DISABLED=true because the
-        # migration container does not serve traffic and Settings would
-        # otherwise require IAS coordinates.
-        - name: db-migrate
-          image: "{{ required "image.repository must be set" .Values.image.repository }}:{{ required "image.tag must be set" .Values.image.tag }}"
-          imagePullPolicy: IfNotPresent
-          workingDir: /home/app/app
-          command: ["alembic", "upgrade", "head"]
-          env:
-            - name: AUTH_DISABLED
-              value: "true"
-            - name: DATABASE_URL
-              valueFrom:
-                secretKeyRef:
-                  name: {{ required "database.secretName must be set" .Values.database.secretName }}
-                  key: {{ required "database.secretKey must be set" .Values.database.secretKey }}
-          resources:
-            requests:
-              cpu: 50m
-              memory: 128Mi
-            limits:
-              cpu: 200m
-              memory: 256Mi
       containers:
         - name: {{ .Chart.Name }}
           image: "{{ required "image.repository must be set" .Values.image.repository }}:{{ required "image.tag must be set" .Values.image.tag }}"
+          imagePullPolicy: {{ .Values.image.pullPolicy | default "IfNotPresent" }}
           ports:
-            - containerPort: 8000
+            - name: http
+              containerPort: 8000
+              protocol: TCP
+          envFrom:
+            - configMapRef:
+                name: {{ include "fl-control-plane.fullname" . }}-config
           env:
-            - name: AUTH_DISABLED
-              value: {{ .Values.auth.authDisabled | quote }}
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
             - name: IAS_ISSUER_URL
               value: {{ .Values.auth.iasIssuerUrl | quote }}
             - name: IAS_JWKS_URI
               value: {{ .Values.auth.iasJwksUri | quote }}
             - name: IAS_AUDIENCE
               value: {{ .Values.auth.iasAudience | quote }}
-            - name: DATABASE_URL
-              valueFrom:
-                secretKeyRef:
-                  name: {{ required "database.secretName must be set" .Values.database.secretName }}
-                  key: {{ required "database.secretKey must be set" .Values.database.secretKey }}
+            - name: AUTH_DISABLED
+              value: {{ .Values.auth.authDisabled | quote }}
           livenessProbe:
             httpGet:
-              path: /healthz
-              port: 8000
-            initialDelaySeconds: 5
-            periodSeconds: 10
+              path: {{ .Values.probes.liveness.path }}
+              port: http
+            initialDelaySeconds: {{ .Values.probes.liveness.initialDelaySeconds }}
+            periodSeconds: {{ .Values.probes.liveness.periodSeconds }}
           readinessProbe:
             httpGet:
-              path: /readyz
-              port: 8000
-            initialDelaySeconds: 5
-            periodSeconds: 10
+              path: {{ .Values.probes.readiness.path }}
+              port: http
+            initialDelaySeconds: {{ .Values.probes.readiness.initialDelaySeconds }}
+            periodSeconds: {{ .Values.probes.readiness.periodSeconds }}
+          startupProbe:
+            httpGet:
+              path: {{ .Values.probes.startup.path }}
+              port: http
+            initialDelaySeconds: {{ .Values.probes.startup.initialDelaySeconds }}
+            periodSeconds: {{ .Values.probes.startup.periodSeconds }}
+            failureThreshold: {{ .Values.probes.startup.failureThreshold }}
           resources:
             {{- toYaml .Values.resources | nindent 12 }}
+          securityContext:
+            runAsNonRoot: true
+            runAsUser: 1001
+            readOnlyRootFilesystem: true
+          volumeMounts:
+            - name: tmp
+              mountPath: /tmp
+            - name: hana-certs
+              mountPath: /etc/hana-certs
+              readOnly: true
+      volumes:
+        - name: tmp
+          emptyDir: {}
+        - name: hana-certs
+          secret:
+            secretName: {{ required "database.secretName must be set" .Values.database.secretName }}
+            items:
+              - key: certificate
+                path: ca.pem
+            optional: true
diff --git a/chart/templates/hana-binding.yaml b/chart/templates/hana-binding.yaml
new file mode 100644
index 00000000..8ed27701
--- /dev/null
+++ b/chart/templates/hana-binding.yaml
@@ -0,0 +1,28 @@
+{{- if .Values.database.serviceBinding.enabled }}
+apiVersion: services.cloud.sap.com/v1
+kind: ServiceInstance
+metadata:
+  name: {{ include "fl-control-plane.fullname" . }}-db-schema
+  annotations:
+    "helm.sh/hook": pre-install,pre-upgrade
+    "helm.sh/hook-weight": "-1"
+    "helm.sh/hook-delete-policy": before-hook-creation
+spec:
+  serviceOfferingName: hana
+  servicePlanName: schema
+  externalName: {{ include "fl-control-plane.fullname" . }}-db-schema-{{ .Release.Namespace }}
+  parameters:
+    database_id: {{ required "database.hanaInstanceId must be set" .Values.database.hanaInstanceId }}
+---
+apiVersion: services.cloud.sap.com/v1
+kind: ServiceBinding
+metadata:
+  name: {{ include "fl-control-plane.fullname" . }}-db-binding
+  annotations:
+    "helm.sh/hook": pre-install,pre-upgrade
+    "helm.sh/hook-weight": "0"
+    "helm.sh/hook-delete-policy": before-hook-creation
+spec:
+  serviceInstanceName: {{ include "fl-control-plane.fullname" . }}-db-schema
+  secretName: {{ required "database.secretName must be set" .Values.database.secretName }}
+{{- end }}
diff --git a/chart/templates/pdb.yaml b/chart/templates/pdb.yaml
index 0f1e774d..8d4fcdf8 100644
--- a/chart/templates/pdb.yaml
+++ b/chart/templates/pdb.yaml
@@ -12,12 +12,12 @@
 apiVersion: policy/v1
 kind: PodDisruptionBudget
 metadata:
-  name: {{ .Chart.Name }}
+  name: {{ include "fl-control-plane.fullname" . }}
   labels:
-    app: {{ .Chart.Name }}
+    {{- include "fl-control-plane.labels" . | nindent 4 }}
 spec:
   minAvailable: 1
   selector:
     matchLabels:
-      app: {{ .Chart.Name }}
+      {{- include "fl-control-plane.selectorLabels" . | nindent 6 }}
 {{- end }}
diff --git a/chart/templates/secret.yaml b/chart/templates/secret.yaml
index 52a5e099..dedc11f0 100644
--- a/chart/templates/secret.yaml
+++ b/chart/templates/secret.yaml
@@ -17,6 +17,10 @@ apiVersion: v1
 kind: Secret
 metadata:
   name: {{ .Values.secret.name }}
+  annotations:
+    "helm.sh/hook": pre-install,pre-upgrade
+    "helm.sh/hook-weight": "-1"
+    "helm.sh/hook-delete-policy": before-hook-creation
 type: kubernetes.io/dockerconfigjson
 data:
   .dockerconfigjson: {{ .Values.secret.dockerconfigjson | quote }}
diff --git a/chart/templates/service.yaml b/chart/templates/service.yaml
index 6a4a9532..1646c76d 100644
--- a/chart/templates/service.yaml
+++ b/chart/templates/service.yaml
@@ -1,9 +1,9 @@
 apiVersion: v1
 kind: Service
 metadata:
-  name: {{ .Chart.Name }}
+  name: {{ include "fl-control-plane.fullname" . }}
   labels:
-    app: {{ .Chart.Name }}
+    {{- include "fl-control-plane.labels" . | nindent 4 }}
 spec:
   type: {{ .Values.service.type }}
   ports:
@@ -11,4 +11,4 @@ spec:
       targetPort: 8000
       protocol: TCP
   selector:
-    app: {{ .Chart.Name }}
+    {{- include "fl-control-plane.selectorLabels" . | nindent 4 }}
diff --git a/chart/templates/wait-for-secret-rbac.yaml b/chart/templates/wait-for-secret-rbac.yaml
new file mode 100644
index 00000000..65734224
--- /dev/null
+++ b/chart/templates/wait-for-secret-rbac.yaml
@@ -0,0 +1,47 @@
+{{- if .Values.database.serviceBinding.enabled }}
+apiVersion: v1
+kind: ServiceAccount
+metadata:
+  name: {{ include "fl-control-plane.fullname" . }}-wait
+  labels:
+    {{- include "fl-control-plane.labels" . | nindent 4 }}
+  annotations:
+    "helm.sh/hook": pre-install,pre-upgrade
+    "helm.sh/hook-weight": "0"
+    "helm.sh/hook-delete-policy": before-hook-creation
+---
+apiVersion: rbac.authorization.k8s.io/v1
+kind: Role
+metadata:
+  name: {{ include "fl-control-plane.fullname" . }}-wait
+  labels:
+    {{- include "fl-control-plane.labels" . | nindent 4 }}
+  annotations:
+    "helm.sh/hook": pre-install,pre-upgrade
+    "helm.sh/hook-weight": "0"
+    "helm.sh/hook-delete-policy": before-hook-creation
+rules:
+  - apiGroups: [""]
+    resources: ["secrets"]
+    resourceNames: [{{ .Values.database.secretName | quote }}]
+    verbs: ["get"]
+---
+apiVersion: rbac.authorization.k8s.io/v1
+kind: RoleBinding
+metadata:
+  name: {{ include "fl-control-plane.fullname" . }}-wait
+  labels:
+    {{- include "fl-control-plane.labels" . | nindent 4 }}
+  annotations:
+    "helm.sh/hook": pre-install,pre-upgrade
+    "helm.sh/hook-weight": "0"
+    "helm.sh/hook-delete-policy": before-hook-creation
+roleRef:
+  apiGroup: rbac.authorization.k8s.io
+  kind: Role
+  name: {{ include "fl-control-plane.fullname" . }}-wait
+subjects:
+  - kind: ServiceAccount
+    name: {{ include "fl-control-plane.fullname" . }}-wait
+    namespace: {{ .Release.Namespace }}
+{{- end }}
diff --git a/chart/values.yaml b/chart/values.yaml
index 762c01e9..ab4d6b4b 100644
--- a/chart/values.yaml
+++ b/chart/values.yaml
@@ -28,7 +28,7 @@ resources:
     cpu: "250m"
   requests:
     memory: "128Mi"
-    cpu: "100m"
+    cpu: "250m"
 
 auth:
   authDisabled: false
@@ -37,11 +37,32 @@ auth:
   iasAudience: b6477651-d4b4-4db8-8406-ed46f5e2f26c
 
 database:
-  secretName: pipeline-fl-control-plane-db
-  secretKey: url
+  secretName: "control-plane-db-credentials"
+  hanaInstanceId: "8d3fd65b-af2c-467f-8529-f8f1acfb9e33"
+  serviceBinding:
+    enabled: true
 
 apirule:
   enabled: true
   host: pipeline-fl-control-plane
   jwtIssuer: https://hanaqainfrastructure.accounts400.ondemand.com
   jwtJwksUri: https://hanaqainfrastructure.accounts400.ondemand.com/oauth2/certs
+
+probes:
+  liveness:
+    path: /healthz
+    initialDelaySeconds: 5
+    periodSeconds: 10
+  readiness:
+    path: /readyz
+    initialDelaySeconds: 10
+    periodSeconds: 5
+  startup:
+    path: /healthz
+    initialDelaySeconds: 5
+    periodSeconds: 5
+    failureThreshold: 30
+
+config:
+  LOG_LEVEL: "INFO"
+  DEBUG: "false"
diff --git a/db/migrations/env.py b/db/migrations/env.py
index 99e80ad7..fdb84a83 100644
--- a/db/migrations/env.py
+++ b/db/migrations/env.py
@@ -17,20 +17,21 @@
 from logging.config import fileConfig
 
 from alembic import context
+from sqlalchemy import text
 from sqlalchemy.engine import Connection
+from sqlalchemy.exc import DBAPIError
 from sqlalchemy.ext.asyncio import async_engine_from_config
 
 from fl_control_plane.config import settings
-from fl_control_plane.database import Base
+from fl_control_plane.database import Base, hana_set_schema_sql
 
 config = context.config
 
 if config.config_file_name is not None:
     fileConfig(config.config_file_name)
 
-# Programmatically set the URL from Settings. Must happen before
-# engine_from_config picks up the [alembic] section.
-config.set_main_option("sqlalchemy.url", settings.database_url)
+# configparser treats % as interpolation syntax — escape for literal use.
+config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
 
 target_metadata = Base.metadata
 
@@ -38,20 +39,41 @@
 def _is_sqlite_url(url: str) -> bool:
     return url.startswith("sqlite")
 
+def _ensure_hana_schema(connection: Connection) -> None:
+    """Activate the BTP-provisioned schema on HANA before running migrations."""
+    sql = hana_set_schema_sql(connection.dialect.name, settings.db_schema)
+    if sql is None:
+        return
+    try:
+        connection.execute(text(sql))
+        connection.execute(text("SELECT 1 FROM DUMMY"))
+    except DBAPIError as exc:
+        raise RuntimeError(
+            f'Schema "{settings.db_schema}" is not accessible. '
+            f"Ensure the BTP ServiceBinding provisioned it: {exc}"
+        ) from exc
+
 
 def _do_run_migrations(connection: Connection) -> None:
+    _ensure_hana_schema(connection)
+    is_sqlite = _is_sqlite_url(settings.database_url)
+    is_hana = connection.dialect.name == "hana"
     context.configure(
         connection=connection,
         target_metadata=target_metadata,
-        # CHECK / column-type / default diffs all matter for the FL schema.
         compare_type=True,
         compare_server_default=True,
-        # Batch mode is required on SQLite to alter CHECK / FK constraints,
-        # but emits unnecessary table-rebuild ops on HANA — gate on dialect.
-        render_as_batch=_is_sqlite_url(settings.database_url),
+        render_as_batch=is_sqlite,
+        # HANA auto-commits DDL — transactional wrapping silently loses the
+        # alembic_version INSERT after implicit DDL commits break the transaction.
+        transactional_ddl=not is_hana,
     )
-    with context.begin_transaction():
+    if is_hana:
         context.run_migrations()
+        connection.commit()
+    else:
+        with context.begin_transaction():
+            context.run_migrations()
 
 
 def run_migrations_offline() -> None:
diff --git a/fl_control_plane/config.py b/fl_control_plane/config.py
index 9630f538..a30619de 100644
--- a/fl_control_plane/config.py
+++ b/fl_control_plane/config.py
@@ -1,45 +1,80 @@
-from pydantic import SecretStr, model_validator
+"""Application configuration via Pydantic Settings."""
+import re
+from pathlib import Path
+from urllib.parse import quote
+
+from pydantic import SecretStr, model_validator, field_validator
 from pydantic_settings import BaseSettings
 
+_TLS_CERT_PATH = Path("/etc/hana-certs/ca.pem")
 
 class Settings(BaseSettings):
     # Application
     app_name: str = "FL Control Plane"
     debug: bool = False
+    log_level: str = "INFO"
 
     # Database — default points at the local SQLite sandbox at db/.
     # In production this is overridden by an env var pointing at HANA.
     database_url: str = "sqlite+aiosqlite:///./db/fl_control_plane.db"
+    db_schema: str = ""
+    db_host: str = ""
+    db_port: int = 443
+    db_user: str = ""
+    db_password: SecretStr = SecretStr("")
+    db_certificate: str = ""
+
+    # Vault / Jenkins credentials (consumed by credentials.py)
+    vault_credentials: SecretStr = SecretStr("")
+    fault_localization_env: str = ""
 
     auth_disabled: bool = False
     ias_issuer_url: str | None = None
     ias_jwks_uri: str | None = None
     ias_audience: str | None = None
 
-    # Vault / credentials
-    fault_localization_env: str = ""
-    vault_credentials: SecretStr | None = None
-
     # `extra="ignore"` is required because BaseSettings reads from os.environ
     # which contains many unrelated vars (PATH, HOME, ...). To catch typos in
     # FL-specific env vars use the `FL_` prefix (env_prefix="FL_") in the
     # future — that lets us safely flip to extra="forbid".
     model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}
 
+    @field_validator("db_schema")
+    @classmethod
+    def _validate_schema_name(cls, v: str) -> str:
+        """Schema is either a K8s namespace (lowercase) or HANA-generated (USR_*)."""
+        if not v:
+            return v
+        is_namespace = bool(re.match(r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?$", v))
+        is_hana_generated = bool(re.match(r"^[A-Z][A-Z0-9_]{0,127}$", v))
+        if not (is_namespace or is_hana_generated):
+            raise ValueError(
+                f"DB_SCHEMA must be a valid K8s namespace or HANA schema name, got: {v!r}"
+            )
+        return v
+
     @model_validator(mode="after")
-    def _require_vault_settings(self) -> "Settings":
-        """Fail fast if Vault credentials are missing."""
-        missing = [
-            name
-            for name, value in (
-                ("FAULT_LOCALIZATION_ENV", self.fault_localization_env),
-                ("VAULT_CREDENTIALS", self.vault_credentials),
+    def _assemble_hana_url(self) -> "Settings":
+        """Assemble DATABASE_URL from individual HANA fields when deployed to K8s."""
+        if self.db_host:
+            query = "encrypt=true&sslValidateCertificate=true"
+            if _TLS_CERT_PATH.exists():
+                query += f"&sslTrustStore={_TLS_CERT_PATH}"
+            self.database_url = (
+                f"hana+aiohdbcli://{quote(self.db_user, safe='')}:{quote(self.db_password.get_secret_value(), safe='')}"
+                f"@{self.db_host}:{self.db_port}/?{query}"
             )
-            if not value
-        ]
-        if missing:
+        return self
+
+    @model_validator(mode="after")
+    def _require_vault_settings(self) -> "Settings":
+        """Fail fast if Vault credentials are partially configured."""
+        has_env = bool(self.fault_localization_env)
+        has_creds = bool(self.vault_credentials and self.vault_credentials.get_secret_value())
+        # Both empty = Vault integration disabled (local dev). Only reject partial config.
+        if has_env != has_creds:
             raise ValueError(
-                f"Required Vault settings are unset: {', '.join(missing)}."
+                "FAULT_LOCALIZATION_ENV and VAULT_CREDENTIALS must both be set or both be empty."
             )
         return self
 
diff --git a/fl_control_plane/credentials.py b/fl_control_plane/credentials.py
index e68a18c4..e1b30b4e 100644
--- a/fl_control_plane/credentials.py
+++ b/fl_control_plane/credentials.py
@@ -53,10 +53,13 @@ class _JaasVaultMeta(BaseModel):
 
 
 def _mount_point() -> str:
-    return (
-        "pipeline3-fl-lithium-secrets"
-        if settings.fault_localization_env == "lithium"
-        else "pipeline3-fl-helium-secrets"
+    env = settings.fault_localization_env
+    if env == "production":
+        return "pipeline3-fl-lithium-secrets"
+    elif env == "development":
+        return "pipeline3-fl-helium-secrets"
+    raise RuntimeError(
+        f"FAULT_LOCALIZATION_ENV must be 'development' or 'production', got: {env!r}"
     )
 
 
diff --git a/fl_control_plane/database.py b/fl_control_plane/database.py
index ceb219d3..4462ef69 100644
--- a/fl_control_plane/database.py
+++ b/fl_control_plane/database.py
@@ -49,6 +49,24 @@ def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any)
         cursor.close()
 
 
+def hana_set_schema_sql(dialect_name: str, schema: str | None) -> str | None:
+    """Return SET SCHEMA SQL for HANA, or None if not applicable."""
+    if dialect_name != "hana" or not schema:
+        return None
+    escaped = schema.replace('"', '""')
+    return f'SET SCHEMA "{escaped}"'
+
+
+@event.listens_for(engine.sync_engine, "connect")
+def _set_hana_schema(dbapi_connection: Any, _connection_record: Any) -> None:
+    sql = hana_set_schema_sql(engine.dialect.name, settings.db_schema)
+    if sql is None:
+        return
+    cursor = dbapi_connection.cursor()
+    cursor.execute(sql)
+    cursor.close()
+
+
 # Inspection status values — see docs/design/db-architecture.md § "inspection".
 # The 4-state lifecycle is enforced both at the DB (CHECK constraint) and in
 # component code via predecessor-guarded UPDATEs.
diff --git a/fl_control_plane/ingestion_api/app.py b/fl_control_plane/ingestion_api/app.py
index 85bbad1c..eeedbf49 100644
--- a/fl_control_plane/ingestion_api/app.py
+++ b/fl_control_plane/ingestion_api/app.py
@@ -7,6 +7,9 @@
 production via Alembic when it lands).
 """
 
+from collections.abc import AsyncGenerator
+from contextlib import asynccontextmanager
+
 from fastapi import FastAPI
 
 from fl_control_plane.health import router as health_router
@@ -14,11 +17,17 @@
 from .router import router as ingestion_router
 
 
+@asynccontextmanager
+async def _lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
+    yield
+
+
 def create_app() -> FastAPI:
     app = FastAPI(
         title="FL Control Plane — Ingestion API",
         description="Receives pipeline failure events and schedules FL analysis runs",
         version="0.0.1",
+        lifespan=_lifespan,
     )
 
     app.include_router(health_router)
diff --git a/tests/data_extractor/test_data_extractor.py b/tests/data_extractor/test_data_extractor.py
index a266bb56..914f8e79 100644
--- a/tests/data_extractor/test_data_extractor.py
+++ b/tests/data_extractor/test_data_extractor.py
@@ -227,7 +227,7 @@ def test_config_no_env_no_arg_does_not_raise(monkeypatch):
 def test_config_ignores_unrelated_env_vars(monkeypatch):
     """Unrelated env vars do not break instantiation (extra='ignore')."""
     monkeypatch.setenv("VAULT_CREDENTIALS", '{"role_id":"x","secret_id":"y"}')
-    monkeypatch.setenv("FAULT_LOCALIZATION_ENV", "lithium")
+    monkeypatch.setenv("FAULT_LOCALIZATION_ENV", "production")
     DataExtractorSettings()  # no exception
 
 
diff --git a/tests/test_credentials.py b/tests/test_credentials.py
index ea8ac5e8..020e9f70 100644
--- a/tests/test_credentials.py
+++ b/tests/test_credentials.py
@@ -49,18 +49,25 @@ def _mock_urlopen(body: bytes) -> MagicMock:
 # ---------------------------------------------------------------------------
 
 class TestMountPoint:
-    def test_lithium_env_returns_lithium_mount(self, monkeypatch):
-        """FAULT_LOCALIZATION_ENV=lithium selects the lithium secrets mount."""
+    def test_production_env_returns_production_mount(self, monkeypatch):
+        """FAULT_LOCALIZATION_ENV=production selects the production secrets mount."""
         import fl_control_plane.credentials as creds_module
-        monkeypatch.setattr(creds_module.settings, "fault_localization_env", "lithium")
+        monkeypatch.setattr(creds_module.settings, "fault_localization_env", "production")
         assert _mount_point() == "pipeline3-fl-lithium-secrets"
 
-    def test_other_env_returns_helium_mount(self, monkeypatch):
-        """Any value other than 'lithium' selects the helium secrets mount."""
+    def test_development_env_returns_development_mount(self, monkeypatch):
+        """'development' selects the development secrets mount."""
         import fl_control_plane.credentials as creds_module
-        monkeypatch.setattr(creds_module.settings, "fault_localization_env", "")
+        monkeypatch.setattr(creds_module.settings, "fault_localization_env", "development")
         assert _mount_point() == "pipeline3-fl-helium-secrets"
 
+    def test_invalid_env_raises(self, monkeypatch):
+        """Unknown value raises RuntimeError."""
+        import fl_control_plane.credentials as creds_module
+        monkeypatch.setattr(creds_module.settings, "fault_localization_env", "")
+        with pytest.raises(RuntimeError, match="must be 'development' or 'production'"):
+            _mount_point()
+
 
 # ---------------------------------------------------------------------------
 # _approle_login
@@ -107,6 +114,7 @@ def test_returns_username_and_token(self, monkeypatch):
         """Happy path: two-hop Vault chain resolves to (username, token)."""
         import fl_control_plane.credentials as creds_module
         monkeypatch.setattr(creds_module.settings, "vault_credentials", SecretStr(_FL_CREDS_ENV))
+        monkeypatch.setattr(creds_module.settings, "fault_localization_env", "development")
         with patch("fl_control_plane.credentials._approle_login", side_effect=self._mock_approle), \
              patch("fl_control_plane.credentials._kv2_read", side_effect=self._mock_kv2):
             username, token = get_jenkins_credentials("https://jenkins.example.com/job/X/1/")
@@ -124,6 +132,7 @@ def test_invalid_jenkins_url_raises(self, monkeypatch):
         """ValueError is raised when the Jenkins URL has no extractable domain."""
         import fl_control_plane.credentials as creds_module
         monkeypatch.setattr(creds_module.settings, "vault_credentials", SecretStr(_FL_CREDS_ENV))
+        monkeypatch.setattr(creds_module.settings, "fault_localization_env", "development")
         with patch("fl_control_plane.credentials._approle_login", side_effect=self._mock_approle), \
              patch("fl_control_plane.credentials._kv2_read", side_effect=self._mock_kv2):
             with pytest.raises(ValueError, match="Cannot extract domain"):
diff --git a/tests/test_schema_isolation.py b/tests/test_schema_isolation.py
new file mode 100644
index 00000000..5f553846
--- /dev/null
+++ b/tests/test_schema_isolation.py
@@ -0,0 +1,50 @@
+"""Tests for per-namespace DB schema isolation (D6)."""
+
+import pytest
+
+from fl_control_plane.config import Settings
+
+
+class TestDbSchemaValidator:
+    """Validates the db_schema field accepts only DNS-label-safe names."""
+
+    def test_empty_schema_is_valid(self) -> None:
+        """Empty string means 'use default schema' — always valid."""
+        s = Settings(auth_disabled=True, db_schema="")
+        assert s.db_schema == ""
+
+    def test_valid_namespace_name(self) -> None:
+        """Standard K8s namespace names pass validation."""
+        s = Settings(auth_disabled=True, db_schema="my-namespace-01")
+        assert s.db_schema == "my-namespace-01"
+
+    def test_single_char_schema(self) -> None:
+        """Single character namespace names are valid."""
+        s = Settings(auth_disabled=True, db_schema="a")
+        assert s.db_schema == "a"
+
+    def test_hana_generated_schema(self) -> None:
+        """BTP-generated HANA schema names (USR_*) pass validation."""
+        s = Settings(auth_disabled=True, db_schema="USR_97ZKSDG08JVFERVRXJDEEU71V")
+        assert s.db_schema == "USR_97ZKSDG08JVFERVRXJDEEU71V"
+
+    def test_rejects_uppercase(self) -> None:
+        """Mixed-case names match neither K8s namespace nor HANA pattern."""
+        with pytest.raises(ValueError, match="DB_SCHEMA must be a valid K8s namespace or HANA schema name"):
+            Settings(auth_disabled=True, db_schema="MyNamespace")
+
+    def test_rejects_leading_hyphen(self) -> None:
+        """DNS labels cannot start with a hyphen."""
+        with pytest.raises(ValueError, match="DB_SCHEMA must be a valid K8s namespace or HANA schema name"):
+            Settings(auth_disabled=True, db_schema="-bad-name")
+
+    def test_rejects_special_characters(self) -> None:
+        """Only alphanumeric and hyphens allowed."""
+        with pytest.raises(ValueError, match="DB_SCHEMA must be a valid K8s namespace or HANA schema name"):
+            Settings(auth_disabled=True, db_schema="drop;schema")
+
+    def test_rejects_too_long(self) -> None:
+        """K8s namespace names are max 63 characters."""
+        with pytest.raises(ValueError, match="DB_SCHEMA must be a valid K8s namespace or HANA schema name"):
+            Settings(auth_disabled=True, db_schema="a" * 64)
+

```
