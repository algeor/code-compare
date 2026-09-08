# 0cfb1add02fdf7d9

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/80
Suggested label: 35%
File overlap: 1.0
Changed-line overlap: 0.0

## Suggested diff
```diff
--- a/chart/templates/deployment.yaml
+++ b/chart/templates/deployment.yaml
@@
+value: {{ printf "%s/pipeline-fl-engineering_agent:%s" $registryOrg ($agentTag | toString) | quote }}
```

## Landed PR diff
```diff
diff --git a/chart/templates/deployment.yaml b/chart/templates/deployment.yaml
index 603e1b07..21f6124c 100644
--- a/chart/templates/deployment.yaml
+++ b/chart/templates/deployment.yaml
@@ -190,8 +190,9 @@ spec:
               value: {{ .Release.Namespace | quote }}
             - name: EE_AGENT_IMAGE
               {{- $agentTag := required "image.pipeline_fl_control_plane_engineering_agent.tag must be set" .Values.image.pipeline_fl_control_plane_engineering_agent.tag }}
-              {{- $agentRepo := required "image.pipeline_fl_control_plane_engineering_agent.repository must be set" .Values.image.pipeline_fl_control_plane_engineering_agent.repository }}
-              value: {{ printf "%s:%s" $agentRepo ($agentTag | toString) | quote }}
+              {{- $injectedRepo := required "image.pipeline_fl_control_plane_engineering_agent.repository must be set" .Values.image.pipeline_fl_control_plane_engineering_agent.repository }}
+              {{- $registryOrg := $injectedRepo | splitList "/" | initial | join "/" }}
+              value: {{ printf "%s/pipeline-fl-engineering_agent:%s" $registryOrg $agentTag | quote }}
             - name: EE_AGENT_IMAGE_PULL_POLICY
               value: {{ .Values.executionEngine.agentImagePullPolicy | default "IfNotPresent" | quote }}
             - name: EE_IMAGE_PULL_SECRET_NAME

```
