# ba90af434cdbbbd8

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/18
Suggested label: 35%
File overlap: 1.0
Changed-line overlap: 0.0

## Suggested diff
```diff
--- a/.github/workflows/piper-oss-ppms.yaml
+++ b/.github/workflows/piper-oss-ppms.yaml
@@
+uses: project-piper/piper-pipeline-github/.github/workflows/sap-oss-ppms-workflow.yml@v1.46.0
```

## Landed PR diff
```diff
diff --git a/.github/workflows/piper-oss-ppms.yaml b/.github/workflows/piper-oss-ppms.yaml
new file mode 100644
index 00000000..154d4a6d
--- /dev/null
+++ b/.github/workflows/piper-oss-ppms.yaml
@@ -0,0 +1,13 @@
+name: Piper OSS workflow
+
+on:
+  workflow_dispatch:
+  pull_request:
+  push:
+    branches:
+    - "main"
+
+jobs:
+    piper:
+        uses: "project-piper/piper-pipeline-github/.github/workflows/sap-oss-ppms-workflow.yml@v1.46.0"
+        secrets: inherit
\ No newline at end of file

```
