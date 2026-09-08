# d9d8ac55ea3efbbf

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/110
Suggested label: 35%
File overlap: 1.0
Changed-line overlap: 0.0

## Suggested diff
```diff
--- a/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/tasks.md
+++ b/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/tasks.md
@@
+- [x] 2.2 Add stat panels: Total Inspections, Currently Running (`status IN ('ACCEPTED', 'IN_PROGRESS')`), Active Fault Handlers (`is_active=TRUE`), Active Handler Executions (`status='running'`)
```

## Landed PR diff
```diff
diff --git a/dashboards/lenny-pipeline-doctor-inspection-overview.json b/dashboards/lenny-pipeline-doctor-inspection-overview.json
new file mode 100644
index 00000000..03e3192e
--- /dev/null
+++ b/dashboards/lenny-pipeline-doctor-inspection-overview.json
@@ -0,0 +1,614 @@
+{
+  "uid": "lenny-pd-inspection-overview",
+  "title": "Lenny Pipeline Doctor - Inspection Overview",
+  "description": "Operational and live inspection state for the Lenny Pipeline Doctor (FL) platform.\n\nShows current system activity: how many inspections are running, their status distribution, the most recently executed inspections, which pipeline stages fail most often, and which fault handlers are currently active.",
+  "id": null,
+  "schemaVersion": 42,
+  "version": 1,
+  "refresh": "5m",
+  "time": {
+    "from": "now-30d",
+    "to": "now"
+  },
+  "timezone": "utc",
+  "tags": [
+    "fault-localization",
+    "lenny-pipeline-doctor"
+  ],
+  "annotations": {
+    "list": [
+      {
+        "builtIn": 1,
+        "datasource": {
+          "type": "grafana",
+          "uid": "-- Grafana --"
+        },
+        "enable": true,
+        "hide": true,
+        "iconColor": "rgba(0, 211, 255, 1)",
+        "name": "Annotations & Alerts",
+        "type": "dashboard"
+      }
+    ]
+  },
+  "templating": {
+    "list": []
+  },
+  "panels": [
+    {
+      "id": 1,
+      "type": "stat",
+      "title": "Total Inspections",
+      "description": "Total inspections created in the selected time range.",
+      "gridPos": { "x": 0, "y": 0, "w": 4, "h": 4 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "colorMode": "value",
+        "graphMode": "none",
+        "justifyMode": "auto",
+        "orientation": "auto",
+        "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false },
+        "textMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": { "mode": "thresholds" },
+          "mappings": [],
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [{ "color": "blue", "value": 0 }]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT COUNT(*) AS \"Total Inspections\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\")",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 2,
+      "type": "stat",
+      "title": "Currently Running",
+      "description": "Inspections currently in progress: ACCEPTED (queued, not yet executing) or IN_PROGRESS (actively executing).",
+      "gridPos": { "x": 4, "y": 0, "w": 4, "h": 4 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "colorMode": "background",
+        "graphMode": "none",
+        "justifyMode": "auto",
+        "orientation": "auto",
+        "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false },
+        "textMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": { "mode": "thresholds" },
+          "mappings": [],
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              { "color": "green", "value": 0 },
+              { "color": "yellow", "value": 20 },
+              { "color": "red", "value": 50 }
+            ]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT COUNT(*) AS \"Currently Running\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\") AND \"STATUS\" IN ('ACCEPTED', 'IN_PROGRESS')",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 12,
+      "type": "stat",
+      "title": "Successful Inspections",
+      "description": "Inspections that completed successfully (status = COMPLETED) in the selected time range.",
+      "gridPos": { "x": 8, "y": 0, "w": 4, "h": 4 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "colorMode": "background",
+        "graphMode": "none",
+        "justifyMode": "auto",
+        "orientation": "auto",
+        "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false },
+        "textMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": { "mode": "thresholds" },
+          "mappings": [],
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [{ "color": "green", "value": 0 }]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT COUNT(*) AS \"Successful\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\") AND \"STATUS\" = 'COMPLETED'",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 13,
+      "type": "stat",
+      "title": "Failed Inspections",
+      "description": "Inspections that failed (status = FAILED) in the selected time range.",
+      "gridPos": { "x": 12, "y": 0, "w": 4, "h": 4 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "colorMode": "background",
+        "graphMode": "none",
+        "justifyMode": "auto",
+        "orientation": "auto",
+        "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false },
+        "textMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": { "mode": "thresholds" },
+          "mappings": [],
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              { "color": "green", "value": 0 },
+              { "color": "red", "value": 1 }
+            ]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT COUNT(*) AS \"Failed\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\") AND \"STATUS\" = 'FAILED'",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 3,
+      "type": "stat",
+      "title": "Active Fault Handlers",
+      "description": "Number of fault handlers that are currently active (is_active = TRUE).",
+      "gridPos": { "x": 16, "y": 0, "w": 4, "h": 4 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "colorMode": "value",
+        "graphMode": "none",
+        "justifyMode": "auto",
+        "orientation": "auto",
+        "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false },
+        "textMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": { "mode": "thresholds" },
+          "mappings": [],
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [{ "color": "green", "value": 0 }]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT COUNT(*) AS \"Active Fault Handlers\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"FAULT_HANDLERS\" WHERE \"IS_ACTIVE\" = TRUE",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 4,
+      "type": "stat",
+      "title": "Active Handler Executions",
+      "description": "Handler executions currently running (status = 'running').",
+      "gridPos": { "x": 20, "y": 0, "w": 4, "h": 4 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "colorMode": "background",
+        "graphMode": "none",
+        "justifyMode": "auto",
+        "orientation": "auto",
+        "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false },
+        "textMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": { "mode": "thresholds" },
+          "mappings": [],
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              { "color": "green", "value": 0 },
+              { "color": "yellow", "value": 5 },
+              { "color": "red", "value": 15 }
+            ]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT COUNT(*) AS \"Active Handler Executions\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_EXECUTIONS\" WHERE \"STATUS\" = 'running'",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 5,
+      "type": "piechart",
+      "title": "Inspection Status Breakdown",
+      "description": "Distribution of inspection statuses. Only the four real statuses are shown: ACCEPTED, IN_PROGRESS, COMPLETED, FAILED.",
+      "gridPos": { "x": 0, "y": 4, "w": 12, "h": 8 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "pieType": "pie",
+        "legend": { "displayMode": "table", "placement": "right", "showLegend": true },
+        "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": true },
+        "sort": "desc",
+        "tooltip": { "mode": "single", "sort": "none" }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": { "mode": "palette-classic" },
+          "mappings": []
+        },
+        "overrides": [
+          { "matcher": { "id": "byName", "options": "COMPLETED" }, "properties": [{ "id": "color", "value": { "fixedColor": "green", "mode": "fixed" } }] },
+          { "matcher": { "id": "byName", "options": "FAILED" }, "properties": [{ "id": "color", "value": { "fixedColor": "red", "mode": "fixed" } }] },
+          { "matcher": { "id": "byName", "options": "IN_PROGRESS" }, "properties": [{ "id": "color", "value": { "fixedColor": "blue", "mode": "fixed" } }] },
+          { "matcher": { "id": "byName", "options": "ACCEPTED" }, "properties": [{ "id": "color", "value": { "fixedColor": "yellow", "mode": "fixed" } }] }
+        ]
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT \"STATUS\", COUNT(*) AS \"COUNT\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\") AND \"STATUS\" IN ('ACCEPTED', 'IN_PROGRESS', 'COMPLETED', 'FAILED') GROUP BY \"STATUS\" ORDER BY \"STATUS\"",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 6,
+      "type": "piechart",
+      "title": "Handler Execution Status Breakdown",
+      "description": "Distribution of handler execution statuses: planned, running, success, failed, timed_out.",
+      "gridPos": { "x": 12, "y": 4, "w": 12, "h": 8 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "pieType": "pie",
+        "legend": { "displayMode": "table", "placement": "right", "showLegend": true },
+        "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": true },
+        "sort": "desc",
+        "tooltip": { "mode": "single", "sort": "none" }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": { "mode": "palette-classic" },
+          "mappings": []
+        },
+        "overrides": [
+          { "matcher": { "id": "byName", "options": "success" }, "properties": [{ "id": "color", "value": { "fixedColor": "green", "mode": "fixed" } }] },
+          { "matcher": { "id": "byName", "options": "failed" }, "properties": [{ "id": "color", "value": { "fixedColor": "red", "mode": "fixed" } }] },
+          { "matcher": { "id": "byName", "options": "timed_out" }, "properties": [{ "id": "color", "value": { "fixedColor": "orange", "mode": "fixed" } }] },
+          { "matcher": { "id": "byName", "options": "running" }, "properties": [{ "id": "color", "value": { "fixedColor": "blue", "mode": "fixed" } }] },
+          { "matcher": { "id": "byName", "options": "planned" }, "properties": [{ "id": "color", "value": { "fixedColor": "yellow", "mode": "fixed" } }] }
+        ]
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT \"STATUS\", COUNT(*) AS \"COUNT\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_EXECUTIONS\" WHERE $__timeFilter(\"CREATED_AT\") GROUP BY \"STATUS\" ORDER BY \"STATUS\"",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 7,
+      "type": "table",
+      "title": "Currently Running Inspections",
+      "description": "All inspections currently queued (ACCEPTED) or executing (IN_PROGRESS), ordered oldest first to surface stuck runs.",
+      "gridPos": { "x": 0, "y": 12, "w": 24, "h": 8 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "cellHeight": "sm",
+        "showHeader": true,
+        "sortBy": [{ "desc": false, "displayName": "Created At" }]
+      },
+      "fieldConfig": {
+        "defaults": {
+          "custom": {
+            "align": "auto",
+            "cellOptions": { "type": "auto" },
+            "filterable": true,
+            "inspect": false
+          },
+          "mappings": [],
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [{ "color": "green", "value": 0 }, { "color": "red", "value": 80 }]
+          }
+        },
+        "overrides": [
+          {
+            "matcher": { "id": "byName", "options": "ID" },
+            "properties": [
+              { "id": "displayName", "value": "Inspection ID" },
+              { "id": "custom.width", "value": 300 }
+            ]
+          },
+          {
+            "matcher": { "id": "byName", "options": "CREATED_AT" },
+            "properties": [
+              { "id": "displayName", "value": "Created At" },
+              { "id": "custom.width", "value": 180 }
+            ]
+          },
+          {
+            "matcher": { "id": "byName", "options": "CI_SYSTEM" },
+            "properties": [
+              { "id": "displayName", "value": "CI System" },
+              { "id": "links", "value": [{ "targetBlank": true, "title": "Open in CI", "url": "${__data.fields.PIPELINE_URL}" }] }
+            ]
+          },
+          {
+            "matcher": { "id": "byName", "options": "PIPELINE_URL" },
+            "properties": [{ "id": "custom.hideFrom.viz", "value": true }]
+          },
+          {
+            "matcher": { "id": "byName", "options": "REPO_NAME" },
+            "properties": [
+              { "id": "displayName", "value": "Repository" },
+              { "id": "links", "value": [{ "targetBlank": true, "title": "Open Repository", "url": "${__data.fields.GITHUB_REPO_URL}" }] }
+            ]
+          },
+          {
+            "matcher": { "id": "byName", "options": "GITHUB_REPO_URL" },
+            "properties": [{ "id": "custom.hideFrom.viz", "value": true }]
+          }
+        ]
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT \"ID\", \"CREATED_AT\", \"CI_SYSTEM\", \"PIPELINE_URL\", \"REPO_NAME\", \"GITHUB_REPO_URL\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE \"STATUS\" IN ('ACCEPTED', 'IN_PROGRESS') ORDER BY \"CREATED_AT\" ASC",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 8,
+      "type": "table",
+      "title": "Last Executed Inspections",
+      "description": "Most recently completed or failed inspections (up to 25), ordered newest first.",
+      "gridPos": { "x": 0, "y": 20, "w": 24, "h": 8 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "cellHeight": "sm",
+        "showHeader": true
+      },
+      "fieldConfig": {
+        "defaults": {
+          "custom": {
+            "align": "auto",
+            "cellOptions": { "type": "auto" },
+            "filterable": true,
+            "inspect": false
+          },
+          "mappings": [],
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [{ "color": "green", "value": 0 }, { "color": "red", "value": 80 }]
+          }
+        },
+        "overrides": [
+          {
+            "matcher": { "id": "byName", "options": "ID" },
+            "properties": [
+              { "id": "displayName", "value": "Inspection ID" },
+              { "id": "custom.width", "value": 300 }
+            ]
+          },
+          {
+            "matcher": { "id": "byName", "options": "STATUS" },
+            "properties": [
+              { "id": "displayName", "value": "Status" },
+              {
+                "id": "mappings",
+                "value": [
+                  { "type": "value", "options": { "COMPLETED": { "color": "green", "index": 0 } } },
+                  { "type": "value", "options": { "FAILED": { "color": "red", "index": 1 } } }
+                ]
+              }
+            ]
+          },
+          {
+            "matcher": { "id": "byName", "options": "CREATED_AT" },
+            "properties": [
+              { "id": "displayName", "value": "Created At" },
+              { "id": "custom.width", "value": 180 }
+            ]
+          },
+          {
+            "matcher": { "id": "byName", "options": "DURATION_S" },
+            "properties": [
+              { "id": "displayName", "value": "Duration" },
+              { "id": "unit", "value": "s" },
+              { "id": "custom.width", "value": 120 }
+            ]
+          },
+          {
+            "matcher": { "id": "byName", "options": "ACTIVATED_HANDLERS" },
+            "properties": [
+              { "id": "displayName", "value": "Activated Fault Handlers" },
+              { "id": "custom.width", "value": 180 }
+            ]
+          },
+          {
+            "matcher": { "id": "byName", "options": "CI_SYSTEM" },
+            "properties": [
+              { "id": "displayName", "value": "CI System" },
+              { "id": "links", "value": [{ "targetBlank": true, "title": "Open in CI", "url": "${__data.fields.PIPELINE_URL}" }] }
+            ]
+          },
+          {
+            "matcher": { "id": "byName", "options": "PIPELINE_URL" },
+            "properties": [{ "id": "custom.hideFrom.viz", "value": true }]
+          },
+          {
+            "matcher": { "id": "byName", "options": "REPO_NAME" },
+            "properties": [
+              { "id": "displayName", "value": "Repository" },
+              { "id": "links", "value": [{ "targetBlank": true, "title": "Open Repository", "url": "${__data.fields.GITHUB_REPO_URL}" }] }
+            ]
+          },
+          {
+            "matcher": { "id": "byName", "options": "GITHUB_REPO_URL" },
+            "properties": [{ "id": "custom.hideFrom.viz", "value": true }]
+          }
+        ]
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT TOP 25 i.\"ID\", i.\"CREATED_AT\", i.\"STATUS\", SECONDS_BETWEEN(i.\"CREATED_AT\", i.\"FINISHED_AT\") AS \"DURATION_S\", (SELECT COUNT(*) FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_EXECUTIONS\" he WHERE he.\"INSPECTION_ID\" = i.\"ID\") AS \"ACTIVATED_HANDLERS\", i.\"CI_SYSTEM\", i.\"PIPELINE_URL\", i.\"REPO_NAME\", i.\"GITHUB_REPO_URL\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" i WHERE i.\"STATUS\" NOT IN ('ACCEPTED', 'IN_PROGRESS') ORDER BY i.\"CREATED_AT\" DESC",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 9,
+      "type": "barchart",
+      "title": "Most Common Failed Stages (Top 20)",
+      "description": "The 20 most frequently failing pipeline stage names across all inspections in the selected time range.",
+      "gridPos": { "x": 0, "y": 28, "w": 12, "h": 8 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "barWidth": 0.97,
+        "groupWidth": 0.7,
+        "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true },
+        "orientation": "horizontal",
+        "tooltip": { "mode": "single", "sort": "none" },
+        "xTickLabelRotation": 0
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": { "mode": "palette-classic" },
+          "mappings": [],
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [{ "color": "green", "value": 0 }, { "color": "red", "value": 80 }]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT TOP 20 \"STAGE_NAME\", COUNT(*) AS \"Failures\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"FAILED_STAGES\" WHERE $__timeFilter(\"CREATED_AT\") GROUP BY \"STAGE_NAME\" ORDER BY COUNT(*) DESC",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 10,
+      "type": "timeseries",
+      "title": "Failed Stages Over Time",
+      "description": "Total number of failed stage records created per hour.",
+      "gridPos": { "x": 12, "y": 28, "w": 12, "h": 8 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true },
+        "tooltip": { "mode": "single", "sort": "none" }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": { "mode": "palette-classic" },
+          "custom": { "lineWidth": 1, "fillOpacity": 10 },
+          "mappings": [],
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [{ "color": "green", "value": 0 }, { "color": "red", "value": 80 }]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT TO_TIMESTAMP(ADD_SECONDS('1970-01-01', FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 3600) * 3600)) AS \"TIME\", COUNT(*) AS \"Failed Stages\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"FAILED_STAGES\" WHERE $__timeFilter(\"CREATED_AT\") GROUP BY FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 3600) ORDER BY 1",
+          "refId": "A",
+          "format": 0
+        }
+      ]
+    },
+    {
+      "id": 11,
+      "type": "table",
+      "title": "Activated Fault Handlers",
+      "description": "All fault handlers that are currently active (is_active = TRUE), showing their registration metadata.",
+      "gridPos": { "x": 0, "y": 36, "w": 24, "h": 8 },
+      "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+      "options": {
+        "cellHeight": "sm",
+        "showHeader": true
+      },
+      "fieldConfig": {
+        "defaults": {
+          "custom": {
+            "align": "auto",
+            "cellOptions": { "type": "auto" },
+            "filterable": true,
+            "inspect": false
+          },
+          "mappings": [],
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [{ "color": "green", "value": 0 }, { "color": "red", "value": 80 }]
+          }
+        },
+        "overrides": [
+          {
+            "matcher": { "id": "byName", "options": "REGISTERED_AT" },
+            "properties": [{ "id": "custom.width", "value": 180 }]
+          }
+        ]
+      },
+      "targets": [
+        {
+          "datasource": { "type": "grafana-saphana-datasource", "uid": "cfucydbdfo1dsc" },
+          "rawSql": "SELECT \"FAULT_ID\", \"EXECUTION_TYPE\", \"STRATEGY\", \"CI_SYSTEMS\", \"REGISTERED_AT\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"FAULT_HANDLERS\" WHERE \"IS_ACTIVE\" = TRUE ORDER BY \"REGISTERED_AT\" DESC",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    }
+  ]
+}
diff --git a/dashboards/lenny-pipeline-doctor-performance.json b/dashboards/lenny-pipeline-doctor-performance.json
new file mode 100644
index 00000000..4d4cea3a
--- /dev/null
+++ b/dashboards/lenny-pipeline-doctor-performance.json
@@ -0,0 +1,492 @@
+{
+  "id": null,
+  "uid": "lenny-pd-performance",
+  "title": "Lenny Pipeline Doctor - Performance",
+  "description": "Business KPIs for the Lenny Pipeline Doctor (FL) platform.\n\nMetric semantics (post-rearchitecture):\n- Success Rate: workflow completion only \u2014 inspection status = COMPLETED. This is NOT proposal quality or fix accuracy.\n- Avg Resolution Time: wall-clock elapsed time from inspection.created_at to inspection.finished_at, including agent scheduling latency (Doit scheduling can add minutes before execution begins). This is NOT pure analysis time.\n\nDeferred KPIs (not shown \u2014 no data source yet):\n- Satisfaction: requires feedback table to be populated by the platform. Currently no writes occur.\n- Proposal Accuracy: requires feedback.assessment = 'correct_fix'/'wrong_fix' population. Currently no writes occur.",
+  "schemaVersion": 38,
+  "version": 1,
+  "refresh": "5m",
+  "time": {
+    "from": "now-30d",
+    "to": "now"
+  },
+  "timezone": "utc",
+  "tags": [
+    "fault-localization",
+    "lenny-pipeline-doctor"
+  ],
+  "annotations": {
+    "list": [
+      {
+        "builtIn": 1,
+        "datasource": {
+          "type": "grafana",
+          "uid": "-- Grafana --"
+        },
+        "enable": true,
+        "hide": true,
+        "iconColor": "rgba(0, 211, 255, 1)",
+        "name": "Annotations & Alerts",
+        "type": "dashboard"
+      }
+    ]
+  },
+  "templating": {
+    "list": []
+  },
+  "panels": [
+    {
+      "id": 1,
+      "type": "stat",
+      "title": "Inspection Volume",
+      "description": "Total number of inspections in the selected time range.",
+      "gridPos": {
+        "x": 0,
+        "y": 0,
+        "w": 6,
+        "h": 4
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "reduceOptions": {
+          "calcs": [
+            "lastNotNull"
+          ]
+        },
+        "orientation": "auto",
+        "textMode": "auto",
+        "colorMode": "value",
+        "graphMode": "none",
+        "justifyMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "mode": "thresholds"
+          },
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              {
+                "color": "green",
+                "value": null
+              }
+            ]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT COUNT(*) AS \"Inspection Volume\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\")",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 2,
+      "type": "stat",
+      "title": "Success Rate %",
+      "description": "Percentage of inspections that completed successfully (status = COMPLETED) among all finished inspections in the selected time range.",
+      "gridPos": {
+        "x": 6,
+        "y": 0,
+        "w": 6,
+        "h": 4
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "reduceOptions": {
+          "calcs": [
+            "lastNotNull"
+          ]
+        },
+        "orientation": "auto",
+        "textMode": "auto",
+        "colorMode": "background",
+        "graphMode": "none",
+        "justifyMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "unit": "percent",
+          "min": 0,
+          "max": 100,
+          "color": {
+            "mode": "thresholds"
+          },
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              {
+                "color": "red",
+                "value": null
+              },
+              {
+                "color": "yellow",
+                "value": 70
+              },
+              {
+                "color": "green",
+                "value": 90
+              }
+            ]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT ROUND(100.0 * SUM(CASE WHEN \"STATUS\" = 'COMPLETED' THEN 1 ELSE 0 END) / COUNT(*), 2) AS \"Success Rate %\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\") AND \"FINISHED_AT\" IS NOT NULL",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 3,
+      "type": "stat",
+      "title": "Avg Resolution Time",
+      "description": "Average wall-clock time from inspection creation to finish, including agent scheduling latency. Only completed inspections are included.",
+      "gridPos": {
+        "x": 12,
+        "y": 0,
+        "w": 6,
+        "h": 4
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "reduceOptions": {
+          "calcs": [
+            "lastNotNull"
+          ]
+        },
+        "orientation": "auto",
+        "textMode": "auto",
+        "colorMode": "value",
+        "graphMode": "none",
+        "justifyMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "unit": "s",
+          "color": {
+            "mode": "thresholds"
+          },
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              {
+                "color": "green",
+                "value": null
+              }
+            ]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT AVG(SECONDS_BETWEEN(\"CREATED_AT\", \"FINISHED_AT\")) AS \"Avg Resolution Time (s)\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\") AND \"FINISHED_AT\" IS NOT NULL AND \"STATUS\" = 'COMPLETED'",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 4,
+      "type": "stat",
+      "title": "Active Repositories",
+      "description": "Number of distinct repositories that have triggered at least one inspection in the selected time range.",
+      "gridPos": {
+        "x": 18,
+        "y": 0,
+        "w": 6,
+        "h": 4
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "reduceOptions": {
+          "calcs": [
+            "lastNotNull"
+          ]
+        },
+        "orientation": "auto",
+        "textMode": "auto",
+        "colorMode": "value",
+        "graphMode": "none",
+        "justifyMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "mode": "thresholds"
+          },
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              {
+                "color": "green",
+                "value": null
+              }
+            ]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT COUNT(DISTINCT \"REPO_NAME\") AS \"Active Repositories\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\") AND \"REPO_NAME\" IS NOT NULL",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 5,
+      "type": "timeseries",
+      "title": "Inspection Volume Over Time",
+      "description": "Number of inspections created per hour.",
+      "gridPos": {
+        "x": 0,
+        "y": 4,
+        "w": 12,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "tooltip": {
+          "mode": "single",
+          "sort": "none"
+        },
+        "legend": {
+          "displayMode": "list",
+          "placement": "bottom"
+        }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "mode": "palette-classic"
+          },
+          "custom": {
+            "lineWidth": 1,
+            "fillOpacity": 10
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT TO_TIMESTAMP(ADD_SECONDS('1970-01-01', FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 3600) * 3600)) AS \"TIME\", COUNT(*) AS \"Inspections\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\") GROUP BY FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 3600) ORDER BY 1",
+          "refId": "A",
+          "format": 0
+        }
+      ]
+    },
+    {
+      "id": 6,
+      "type": "timeseries",
+      "title": "Success Rate Over Time",
+      "description": "Percentage of inspections completing successfully (status = COMPLETED) among all finished inspections, per hour.",
+      "gridPos": {
+        "x": 12,
+        "y": 4,
+        "w": 12,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "tooltip": {
+          "mode": "single",
+          "sort": "none"
+        },
+        "legend": {
+          "displayMode": "list",
+          "placement": "bottom"
+        }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "unit": "percent",
+          "min": 0,
+          "max": 100,
+          "color": {
+            "mode": "thresholds"
+          },
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              {
+                "color": "red",
+                "value": null
+              },
+              {
+                "color": "yellow",
+                "value": 70
+              },
+              {
+                "color": "green",
+                "value": 90
+              }
+            ]
+          },
+          "custom": {
+            "lineWidth": 1,
+            "fillOpacity": 10
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT TO_TIMESTAMP(ADD_SECONDS('1970-01-01', FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 3600) * 3600)) AS \"TIME\", ROUND(100.0 * SUM(CASE WHEN \"STATUS\" = 'COMPLETED' THEN 1 ELSE 0 END) / COUNT(*), 2) AS \"Success Rate %\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\") AND \"FINISHED_AT\" IS NOT NULL GROUP BY FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 3600) ORDER BY 1",
+          "refId": "A",
+          "format": 0
+        }
+      ]
+    },
+    {
+      "id": 7,
+      "type": "timeseries",
+      "title": "Avg Resolution Time Over Time",
+      "description": "Average wall-clock resolution time per hour for completed inspections.",
+      "gridPos": {
+        "x": 0,
+        "y": 12,
+        "w": 12,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "tooltip": {
+          "mode": "single",
+          "sort": "none"
+        },
+        "legend": {
+          "displayMode": "list",
+          "placement": "bottom"
+        }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "unit": "s",
+          "color": {
+            "mode": "palette-classic"
+          },
+          "custom": {
+            "lineWidth": 1,
+            "fillOpacity": 10
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT TO_TIMESTAMP(ADD_SECONDS('1970-01-01', FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 3600) * 3600)) AS \"TIME\", AVG(SECONDS_BETWEEN(\"CREATED_AT\", \"FINISHED_AT\")) AS \"Avg Resolution Time (s)\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\") AND \"FINISHED_AT\" IS NOT NULL AND \"STATUS\" = 'COMPLETED' GROUP BY FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 3600) ORDER BY 1",
+          "refId": "A",
+          "format": 0
+        }
+      ]
+    },
+    {
+      "id": 8,
+      "type": "timeseries",
+      "title": "Repository Adoption Growth (Weekly)",
+      "description": "Number of distinct repositories triggering inspections per week.",
+      "gridPos": {
+        "x": 12,
+        "y": 12,
+        "w": 12,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "tooltip": {
+          "mode": "single",
+          "sort": "none"
+        },
+        "legend": {
+          "displayMode": "list",
+          "placement": "bottom"
+        }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "mode": "palette-classic"
+          },
+          "custom": {
+            "lineWidth": 1,
+            "fillOpacity": 10
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT TO_TIMESTAMP(ADD_SECONDS('1970-01-01', FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 604800) * 604800)) AS \"TIME\", COUNT(DISTINCT \"REPO_NAME\") AS \"Active Repositories\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"INSPECTION\" WHERE $__timeFilter(\"CREATED_AT\") AND \"REPO_NAME\" IS NOT NULL GROUP BY FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 604800) ORDER BY 1",
+          "refId": "A",
+          "format": 0
+        }
+      ]
+    }
+  ]
+}
\ No newline at end of file
diff --git a/dashboards/lenny-pipeline-doctor-platform-operations.json b/dashboards/lenny-pipeline-doctor-platform-operations.json
new file mode 100644
index 00000000..25a57860
--- /dev/null
+++ b/dashboards/lenny-pipeline-doctor-platform-operations.json
@@ -0,0 +1,1254 @@
+{
+  "id": null,
+  "uid": "lenny-pd-platform-ops",
+  "title": "Lenny Pipeline Doctor - Platform Operations",
+  "description": "FL operator internals for the Lenny Pipeline Doctor platform.\n\nCovers: AI token usage by handler agents, handler execution health, pipeline-analyzer decisions (STOP/CONTINUE), finalizer execution status, handler controller health (circuit breaker state, last sync latency), and secret resolution sources.",
+  "schemaVersion": 38,
+  "version": 1,
+  "refresh": "5m",
+  "time": {
+    "from": "now-30d",
+    "to": "now"
+  },
+  "timezone": "utc",
+  "tags": [
+    "fault-localization",
+    "lenny-pipeline-doctor"
+  ],
+  "annotations": {
+    "list": [
+      {
+        "builtIn": 1,
+        "datasource": {
+          "type": "grafana",
+          "uid": "-- Grafana --"
+        },
+        "enable": true,
+        "hide": true,
+        "iconColor": "rgba(0, 211, 255, 1)",
+        "name": "Annotations & Alerts",
+        "type": "dashboard"
+      }
+    ]
+  },
+  "templating": {
+    "list": []
+  },
+  "panels": [
+    {
+      "id": 7,
+      "type": "row",
+      "title": "Handler Execution Health",
+      "gridPos": {
+        "x": 0,
+        "y": 0,
+        "w": 24,
+        "h": 1
+      },
+      "collapsed": false
+    },
+    {
+      "id": 8,
+      "type": "timeseries",
+      "title": "Handler Executions Over Time",
+      "description": "Number of handler executions created per hour.",
+      "gridPos": {
+        "x": 0,
+        "y": 1,
+        "w": 12,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "tooltip": {
+          "mode": "single",
+          "sort": "none"
+        },
+        "legend": {
+          "displayMode": "list",
+          "placement": "bottom"
+        }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "mode": "palette-classic"
+          },
+          "custom": {
+            "lineWidth": 1,
+            "fillOpacity": 10
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT TO_TIMESTAMP(ADD_SECONDS('1970-01-01', FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 3600) * 3600)) AS \"TIME\", COUNT(*) AS \"Executions\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_EXECUTIONS\" WHERE $__timeFilter(\"CREATED_AT\") GROUP BY FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 3600) ORDER BY 1",
+          "refId": "A",
+          "format": 0
+        }
+      ]
+    },
+    {
+      "id": 9,
+      "type": "barchart",
+      "title": "Executions by Fault ID",
+      "description": "Total handler executions grouped by fault_id in the selected time range.",
+      "gridPos": {
+        "x": 12,
+        "y": 1,
+        "w": 12,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "orientation": "horizontal",
+        "tooltip": {
+          "mode": "single",
+          "sort": "none"
+        },
+        "legend": {
+          "displayMode": "list",
+          "placement": "bottom"
+        }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "mode": "palette-classic"
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT \"FAULT_ID\", COUNT(*) AS \"Executions\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_EXECUTIONS\" WHERE $__timeFilter(\"CREATED_AT\") GROUP BY \"FAULT_ID\" ORDER BY COUNT(*) DESC",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 10,
+      "type": "barchart",
+      "title": "Handler Failures by Fault ID",
+      "description": "Number of handler executions with status = 'failed' or 'timed_out', grouped by fault_id.",
+      "gridPos": {
+        "x": 0,
+        "y": 9,
+        "w": 12,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "orientation": "horizontal",
+        "tooltip": {
+          "mode": "single",
+          "sort": "none"
+        },
+        "legend": {
+          "displayMode": "list",
+          "placement": "bottom"
+        }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "fixedColor": "red",
+            "mode": "fixed"
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT \"FAULT_ID\", COUNT(*) AS \"Failures\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_EXECUTIONS\" WHERE $__timeFilter(\"CREATED_AT\") AND \"STATUS\" IN ('failed', 'timed_out') GROUP BY \"FAULT_ID\" ORDER BY COUNT(*) DESC",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 11,
+      "type": "barchart",
+      "title": "Avg Handler Duration by Fault ID (seconds)",
+      "description": "Average wall-clock duration of completed handler executions, grouped by fault_id.",
+      "gridPos": {
+        "x": 12,
+        "y": 9,
+        "w": 12,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "orientation": "horizontal",
+        "tooltip": {
+          "mode": "single",
+          "sort": "none"
+        },
+        "legend": {
+          "displayMode": "list",
+          "placement": "bottom"
+        }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "unit": "s",
+          "color": {
+            "mode": "palette-classic"
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT \"FAULT_ID\", AVG(SECONDS_BETWEEN(\"CREATED_AT\", \"FINISHED_AT\")) AS \"Avg Duration (s)\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_EXECUTIONS\" WHERE $__timeFilter(\"CREATED_AT\") AND \"FINISHED_AT\" IS NOT NULL GROUP BY \"FAULT_ID\" ORDER BY AVG(SECONDS_BETWEEN(\"CREATED_AT\", \"FINISHED_AT\")) DESC",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 12,
+      "type": "stat",
+      "title": "Handler Success Rate %",
+      "description": "Percentage of completed handler executions that succeeded (status = 'success') in the selected time range.",
+      "gridPos": {
+        "x": 0,
+        "y": 17,
+        "w": 6,
+        "h": 4
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "reduceOptions": {
+          "calcs": [
+            "lastNotNull"
+          ]
+        },
+        "orientation": "auto",
+        "textMode": "auto",
+        "colorMode": "background",
+        "graphMode": "none",
+        "justifyMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "unit": "percent",
+          "min": 0,
+          "max": 100,
+          "color": {
+            "mode": "thresholds"
+          },
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              {
+                "color": "red",
+                "value": null
+              },
+              {
+                "color": "yellow",
+                "value": 70
+              },
+              {
+                "color": "green",
+                "value": 90
+              }
+            ]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT ROUND(100.0 * SUM(CASE WHEN \"STATUS\" = 'success' THEN 1 ELSE 0 END) / COUNT(*), 2) AS \"Handler Success Rate %\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_EXECUTIONS\" WHERE $__timeFilter(\"CREATED_AT\") AND \"STATUS\" IN ('success', 'failed', 'timed_out')",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 13,
+      "type": "row",
+      "title": "Pipeline Analyzer",
+      "gridPos": {
+        "x": 0,
+        "y": 21,
+        "w": 24,
+        "h": 1
+      },
+      "collapsed": false
+    },
+    {
+      "id": 14,
+      "type": "piechart",
+      "title": "Pipeline Analyzer: Stop vs Continue",
+      "description": "Distribution of analysis decisions (STOP / CONTINUE) in the selected time range.",
+      "gridPos": {
+        "x": 0,
+        "y": 22,
+        "w": 12,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "pieType": "pie",
+        "tooltip": {
+          "mode": "single",
+          "sort": "none"
+        },
+        "legend": {
+          "displayMode": "table",
+          "placement": "right"
+        }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "mode": "palette-classic"
+          }
+        },
+        "overrides": [
+          {
+            "matcher": {
+              "id": "byName",
+              "options": "STOP"
+            },
+            "properties": [
+              {
+                "id": "color",
+                "value": {
+                  "fixedColor": "red",
+                  "mode": "fixed"
+                }
+              }
+            ]
+          },
+          {
+            "matcher": {
+              "id": "byName",
+              "options": "CONTINUE"
+            },
+            "properties": [
+              {
+                "id": "color",
+                "value": {
+                  "fixedColor": "green",
+                  "mode": "fixed"
+                }
+              }
+            ]
+          }
+        ]
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT \"ANALYSIS_DECISION\", COUNT(*) AS \"COUNT\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"PIPELINE_ANALYZER_RESULTS\" WHERE $__timeFilter(\"CREATED_AT\") GROUP BY \"ANALYSIS_DECISION\"",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 15,
+      "type": "barchart",
+      "title": "Pipeline Analyzer: Stops by Gate",
+      "description": "Number of STOP decisions per gate name in the selected time range.",
+      "gridPos": {
+        "x": 12,
+        "y": 22,
+        "w": 12,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "orientation": "horizontal",
+        "tooltip": {
+          "mode": "single",
+          "sort": "none"
+        },
+        "legend": {
+          "displayMode": "list",
+          "placement": "bottom"
+        }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "fixedColor": "red",
+            "mode": "fixed"
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT \"GATE\", COUNT(*) AS \"Stops\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"PIPELINE_ANALYZER_RESULTS\" WHERE $__timeFilter(\"CREATED_AT\") AND \"ANALYSIS_DECISION\" = 'STOP' GROUP BY \"GATE\" ORDER BY COUNT(*) DESC",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 16,
+      "type": "row",
+      "title": "Finalizer Execution",
+      "gridPos": {
+        "x": 0,
+        "y": 30,
+        "w": 24,
+        "h": 1
+      },
+      "collapsed": false
+    },
+    {
+      "id": 17,
+      "type": "piechart",
+      "title": "Finalizer Execution Status",
+      "description": "Distribution of finalizer execution statuses in the selected time range: planned, running, success, failed, timed_out.",
+      "gridPos": {
+        "x": 0,
+        "y": 31,
+        "w": 12,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "pieType": "pie",
+        "tooltip": {
+          "mode": "single",
+          "sort": "none"
+        },
+        "legend": {
+          "displayMode": "table",
+          "placement": "right"
+        },
+        "reduceOptions": {
+          "calcs": [
+            "lastNotNull"
+          ],
+          "fields": "",
+          "values": true
+        }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "mode": "palette-classic"
+          }
+        },
+        "overrides": [
+          {
+            "matcher": {
+              "id": "byName",
+              "options": "success"
+            },
+            "properties": [
+              {
+                "id": "color",
+                "value": {
+                  "fixedColor": "green",
+                  "mode": "fixed"
+                }
+              }
+            ]
+          },
+          {
+            "matcher": {
+              "id": "byName",
+              "options": "failed"
+            },
+            "properties": [
+              {
+                "id": "color",
+                "value": {
+                  "fixedColor": "red",
+                  "mode": "fixed"
+                }
+              }
+            ]
+          },
+          {
+            "matcher": {
+              "id": "byName",
+              "options": "timed_out"
+            },
+            "properties": [
+              {
+                "id": "color",
+                "value": {
+                  "fixedColor": "orange",
+                  "mode": "fixed"
+                }
+              }
+            ]
+          },
+          {
+            "matcher": {
+              "id": "byName",
+              "options": "running"
+            },
+            "properties": [
+              {
+                "id": "color",
+                "value": {
+                  "fixedColor": "blue",
+                  "mode": "fixed"
+                }
+              }
+            ]
+          },
+          {
+            "matcher": {
+              "id": "byName",
+              "options": "planned"
+            },
+            "properties": [
+              {
+                "id": "color",
+                "value": {
+                  "fixedColor": "yellow",
+                  "mode": "fixed"
+                }
+              }
+            ]
+          }
+        ]
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT \"STATUS\", COUNT(*) AS \"COUNT\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"FINALIZER_EXECUTION\" WHERE $__timeFilter(\"CREATED_AT\") GROUP BY \"STATUS\" ORDER BY \"STATUS\"",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 18,
+      "type": "row",
+      "title": "Handler Controller Health",
+      "gridPos": {
+        "x": 0,
+        "y": 39,
+        "w": 24,
+        "h": 1
+      },
+      "collapsed": false
+    },
+    {
+      "id": 19,
+      "type": "stat",
+      "title": "Handler Controller: Circuit Breaker Active",
+      "description": "Whether the handler controller's circuit breaker is currently active (TRUE = halted). Reads controller_status.circuit_breaker_active.",
+      "gridPos": {
+        "x": 0,
+        "y": 40,
+        "w": 8,
+        "h": 4
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "reduceOptions": {
+          "calcs": [
+            "lastNotNull"
+          ],
+          "fields": "/^Circuit Breaker Active$/"
+        },
+        "orientation": "auto",
+        "textMode": "auto",
+        "colorMode": "background",
+        "graphMode": "none",
+        "justifyMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "mappings": [
+            {
+              "type": "value",
+              "options": {
+                "0": {
+                  "text": "Inactive",
+                  "color": "green",
+                  "index": 0
+                },
+                "false": {
+                  "text": "Inactive",
+                  "color": "green",
+                  "index": 1
+                }
+              }
+            },
+            {
+              "type": "value",
+              "options": {
+                "1": {
+                  "text": "ACTIVE",
+                  "color": "red",
+                  "index": 2
+                },
+                "true": {
+                  "text": "ACTIVE",
+                  "color": "red",
+                  "index": 3
+                }
+              }
+            }
+          ],
+          "color": {
+            "mode": "thresholds"
+          },
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              {
+                "color": "green",
+                "value": null
+              }
+            ]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT \"CIRCUIT_BREAKER_ACTIVE\" AS \"Circuit Breaker Active\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"CONTROLLER_STATUS\" WHERE \"ID\" = 1",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 20,
+      "type": "stat",
+      "title": "Last Sync Duration (ms)",
+      "description": "Duration of the handler orchestrator's most recent reconciliation cycle in milliseconds.",
+      "gridPos": {
+        "x": 8,
+        "y": 40,
+        "w": 8,
+        "h": 4
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "reduceOptions": {
+          "calcs": [
+            "lastNotNull"
+          ]
+        },
+        "orientation": "auto",
+        "textMode": "auto",
+        "colorMode": "value",
+        "graphMode": "none",
+        "justifyMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "unit": "ms",
+          "color": {
+            "mode": "thresholds"
+          },
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              {
+                "color": "green",
+                "value": null
+              },
+              {
+                "color": "yellow",
+                "value": 5000
+              },
+              {
+                "color": "red",
+                "value": 30000
+              }
+            ]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT \"SYNC_DURATION_MS\" AS \"Last Sync Duration (ms)\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"CONTROLLER_STATUS\" WHERE \"ID\" = 1",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 21,
+      "type": "stat",
+      "title": "Last Sync Time",
+      "description": "Timestamp of the handler orchestrator's most recent reconciliation cycle.",
+      "gridPos": {
+        "x": 16,
+        "y": 40,
+        "w": 8,
+        "h": 4
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "reduceOptions": {
+          "calcs": [
+            "diff"
+          ],
+          "fields": "/^Last Sync Time$/",
+          "values": true
+        },
+        "orientation": "auto",
+        "textMode": "auto",
+        "colorMode": "value",
+        "graphMode": "none",
+        "justifyMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "mode": "thresholds"
+          },
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              {
+                "color": "green",
+                "value": null
+              }
+            ]
+          },
+          "unit": "dateTimeFromNow"
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT \"LAST_SYNC_TIME\" AS \"Last Sync Time\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"CONTROLLER_STATUS\" WHERE \"ID\" = 1",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 22,
+      "type": "row",
+      "title": "Secret Resolution",
+      "gridPos": {
+        "x": 0,
+        "y": 44,
+        "w": 24,
+        "h": 1
+      },
+      "collapsed": false
+    },
+    {
+      "id": 23,
+      "type": "piechart",
+      "title": "Secret Resolution Sources",
+      "description": "Distribution of secret resolution sources (pipeline / platform / unavailable) for handler executions in the selected time range. Time-filtered via join to handler_executions.created_at (audit_secrets_used has no timestamp column).",
+      "gridPos": {
+        "x": 0,
+        "y": 45,
+        "w": 12,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "pieType": "pie",
+        "tooltip": {
+          "mode": "single",
+          "sort": "none"
+        },
+        "legend": {
+          "displayMode": "table",
+          "placement": "right"
+        }
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "mode": "palette-classic"
+          }
+        },
+        "overrides": [
+          {
+            "matcher": {
+              "id": "byName",
+              "options": "pipeline"
+            },
+            "properties": [
+              {
+                "id": "color",
+                "value": {
+                  "fixedColor": "green",
+                  "mode": "fixed"
+                }
+              }
+            ]
+          },
+          {
+            "matcher": {
+              "id": "byName",
+              "options": "platform"
+            },
+            "properties": [
+              {
+                "id": "color",
+                "value": {
+                  "fixedColor": "blue",
+                  "mode": "fixed"
+                }
+              }
+            ]
+          },
+          {
+            "matcher": {
+              "id": "byName",
+              "options": "unavailable"
+            },
+            "properties": [
+              {
+                "id": "color",
+                "value": {
+                  "fixedColor": "red",
+                  "mode": "fixed"
+                }
+              }
+            ]
+          }
+        ]
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT \"RESOLUTION_SOURCE\", COUNT(*) AS \"COUNT\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"AUDIT_SECRETS_USED\" WHERE \"EXECUTION_ID\" IN (SELECT \"ID\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_EXECUTIONS\" WHERE $__timeFilter(\"CREATED_AT\")) GROUP BY \"RESOLUTION_SOURCE\" ORDER BY \"RESOLUTION_SOURCE\"",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 24,
+      "type": "stat",
+      "title": "Unavailable Secrets",
+      "description": "Total number of secret resolution attempts that resulted in 'unavailable' in the selected time range.",
+      "gridPos": {
+        "x": 12,
+        "y": 45,
+        "w": 6,
+        "h": 8
+      },
+      "datasource": {
+        "type": "grafana-saphana-datasource",
+        "uid": "cfucydbdfo1dsc"
+      },
+      "options": {
+        "reduceOptions": {
+          "calcs": [
+            "lastNotNull"
+          ]
+        },
+        "orientation": "auto",
+        "textMode": "auto",
+        "colorMode": "background",
+        "graphMode": "none",
+        "justifyMode": "auto"
+      },
+      "fieldConfig": {
+        "defaults": {
+          "color": {
+            "mode": "thresholds"
+          },
+          "thresholds": {
+            "mode": "absolute",
+            "steps": [
+              {
+                "color": "green",
+                "value": null
+              },
+              {
+                "color": "yellow",
+                "value": 1
+              },
+              {
+                "color": "red",
+                "value": 10
+              }
+            ]
+          }
+        },
+        "overrides": []
+      },
+      "targets": [
+        {
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "rawSql": "SELECT COUNT(*) AS \"Unavailable Secrets\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"AUDIT_SECRETS_USED\" WHERE \"EXECUTION_ID\" IN (SELECT \"ID\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_EXECUTIONS\" WHERE $__timeFilter(\"CREATED_AT\")) AND \"RESOLUTION_SOURCE\" = 'unavailable'",
+          "refId": "A",
+          "format": 1
+        }
+      ]
+    },
+    {
+      "id": 1,
+      "type": "row",
+      "title": "AI Token Usage",
+      "gridPos": {
+        "x": 0,
+        "y": 54,
+        "w": 24,
+        "h": 1
+      },
+      "collapsed": true,
+      "panels": [
+        {
+          "id": 2,
+          "type": "stat",
+          "title": "Total Input Tokens",
+          "description": "Sum of input tokens consumed by all handler agent executions in the selected time range.",
+          "gridPos": {
+            "x": 0,
+            "y": 1,
+            "w": 6,
+            "h": 4
+          },
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "options": {
+            "reduceOptions": {
+              "calcs": [
+                "lastNotNull"
+              ]
+            },
+            "orientation": "auto",
+            "textMode": "auto",
+            "colorMode": "value",
+            "graphMode": "none",
+            "justifyMode": "auto"
+          },
+          "fieldConfig": {
+            "defaults": {
+              "color": {
+                "mode": "thresholds"
+              },
+              "thresholds": {
+                "mode": "absolute",
+                "steps": [
+                  {
+                    "color": "blue",
+                    "value": null
+                  }
+                ]
+              }
+            },
+            "overrides": []
+          },
+          "targets": [
+            {
+              "datasource": {
+                "type": "grafana-saphana-datasource",
+                "uid": "cfucydbdfo1dsc"
+              },
+              "rawSql": "SELECT SUM(\"INPUT_TOKENS\") AS \"Total Input Tokens\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_AGENT_TELEMETRY\" WHERE $__timeFilter(\"CREATED_AT\")",
+              "refId": "A",
+              "format": 1
+            }
+          ]
+        },
+        {
+          "id": 3,
+          "type": "stat",
+          "title": "Total Output Tokens",
+          "description": "Sum of output tokens produced by all handler agent executions in the selected time range.",
+          "gridPos": {
+            "x": 6,
+            "y": 1,
+            "w": 6,
+            "h": 4
+          },
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "options": {
+            "reduceOptions": {
+              "calcs": [
+                "lastNotNull"
+              ]
+            },
+            "orientation": "auto",
+            "textMode": "auto",
+            "colorMode": "value",
+            "graphMode": "none",
+            "justifyMode": "auto"
+          },
+          "fieldConfig": {
+            "defaults": {
+              "color": {
+                "mode": "thresholds"
+              },
+              "thresholds": {
+                "mode": "absolute",
+                "steps": [
+                  {
+                    "color": "purple",
+                    "value": null
+                  }
+                ]
+              }
+            },
+            "overrides": []
+          },
+          "targets": [
+            {
+              "datasource": {
+                "type": "grafana-saphana-datasource",
+                "uid": "cfucydbdfo1dsc"
+              },
+              "rawSql": "SELECT SUM(\"OUTPUT_TOKENS\") AS \"Total Output Tokens\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_AGENT_TELEMETRY\" WHERE $__timeFilter(\"CREATED_AT\")",
+              "refId": "A",
+              "format": 1
+            }
+          ]
+        },
+        {
+          "id": 4,
+          "type": "stat",
+          "title": "Avg Tokens / Execution",
+          "description": "Average total tokens consumed per handler agent execution in the selected time range.",
+          "gridPos": {
+            "x": 12,
+            "y": 1,
+            "w": 6,
+            "h": 4
+          },
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "options": {
+            "reduceOptions": {
+              "calcs": [
+                "lastNotNull"
+              ]
+            },
+            "orientation": "auto",
+            "textMode": "auto",
+            "colorMode": "value",
+            "graphMode": "none",
+            "justifyMode": "auto"
+          },
+          "fieldConfig": {
+            "defaults": {
+              "color": {
+                "mode": "thresholds"
+              },
+              "thresholds": {
+                "mode": "absolute",
+                "steps": [
+                  {
+                    "color": "green",
+                    "value": null
+                  }
+                ]
+              }
+            },
+            "overrides": []
+          },
+          "targets": [
+            {
+              "datasource": {
+                "type": "grafana-saphana-datasource",
+                "uid": "cfucydbdfo1dsc"
+              },
+              "rawSql": "SELECT ROUND(AVG(\"TOTAL_TOKENS\"), 0) AS \"Avg Tokens / Execution\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_AGENT_TELEMETRY\" WHERE $__timeFilter(\"CREATED_AT\")",
+              "refId": "A",
+              "format": 1
+            }
+          ]
+        },
+        {
+          "id": 5,
+          "type": "timeseries",
+          "title": "AI Token Usage Over Time (Input vs Output)",
+          "description": "Hourly input and output token totals across all handler agent executions.",
+          "gridPos": {
+            "x": 0,
+            "y": 5,
+            "w": 12,
+            "h": 8
+          },
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "options": {
+            "tooltip": {
+              "mode": "multi",
+              "sort": "none"
+            },
+            "legend": {
+              "displayMode": "list",
+              "placement": "bottom"
+            }
+          },
+          "fieldConfig": {
+            "defaults": {
+              "color": {
+                "mode": "palette-classic"
+              },
+              "custom": {
+                "lineWidth": 1,
+                "fillOpacity": 10
+              }
+            },
+            "overrides": []
+          },
+          "targets": [
+            {
+              "datasource": {
+                "type": "grafana-saphana-datasource",
+                "uid": "cfucydbdfo1dsc"
+              },
+              "rawSql": "SELECT TO_TIMESTAMP(ADD_SECONDS('1970-01-01', FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 3600) * 3600)) AS \"TIME\", SUM(\"INPUT_TOKENS\") AS \"Input Tokens\", SUM(\"OUTPUT_TOKENS\") AS \"Output Tokens\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_AGENT_TELEMETRY\" WHERE $__timeFilter(\"CREATED_AT\") GROUP BY FLOOR(SECONDS_BETWEEN('1970-01-01', \"CREATED_AT\") / 3600) ORDER BY 1",
+              "refId": "A",
+              "format": 0
+            }
+          ]
+        },
+        {
+          "id": 6,
+          "type": "barchart",
+          "title": "Token Usage by Model",
+          "description": "Total tokens consumed broken down by model name.",
+          "gridPos": {
+            "x": 12,
+            "y": 5,
+            "w": 12,
+            "h": 8
+          },
+          "datasource": {
+            "type": "grafana-saphana-datasource",
+            "uid": "cfucydbdfo1dsc"
+          },
+          "options": {
+            "orientation": "horizontal",
+            "tooltip": {
+              "mode": "single",
+              "sort": "none"
+            },
+            "legend": {
+              "displayMode": "list",
+              "placement": "bottom"
+            }
+          },
+          "fieldConfig": {
+            "defaults": {
+              "color": {
+                "mode": "palette-classic"
+              }
+            },
+            "overrides": []
+          },
+          "targets": [
+            {
+              "datasource": {
+                "type": "grafana-saphana-datasource",
+                "uid": "cfucydbdfo1dsc"
+              },
+              "rawSql": "SELECT \"MODEL_NAME\", SUM(\"TOTAL_TOKENS\") AS \"Total Tokens\" FROM \"USR_E51KMDYETKUR577C31VYQ80TA\".\"HANDLER_AGENT_TELEMETRY\" WHERE $__timeFilter(\"CREATED_AT\") GROUP BY \"MODEL_NAME\" ORDER BY SUM(\"TOTAL_TOKENS\") DESC",
+              "refId": "A",
+              "format": 1
+            }
+          ]
+        }
+      ]
+    }
+  ]
+}
diff --git a/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/.openspec.yaml b/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/.openspec.yaml
new file mode 100644
index 00000000..84cfc124
--- /dev/null
+++ b/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/.openspec.yaml
@@ -0,0 +1,2 @@
+schema: spec-driven
+created: 2026-08-06
diff --git a/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/design.md b/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/design.md
new file mode 100644
index 00000000..2280c455
--- /dev/null
+++ b/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/design.md
@@ -0,0 +1,55 @@
+## Context
+
+See proposal.md — Why. FL was rearchitected off Thinktank onto the `inspection` model. An interim combined dashboard (`dashboards/pipeline-fl-control-plane.json`, 30 panels) exists but renders "No data" (wrong datasource UID) and was never curated (it queries at least one non-existent column). The specs define the behavior contract for three focused replacement dashboards; this document records the technical decisions needed to build them.
+
+Fixed constraints that shape the approach:
+- **Datasource:** "Lenny Pipeline Doctor Production", type `grafana-saphana-datasource`, UID `cfucydbdfo1dsc`. DB user `USR_E51KMDYETKUR577C31VYQ80TA` (`dashboards/grafana-datasource-fl-prod.yaml:15`).
+- **Authoritative schema:** `fl_control_plane/database.py`. Real inspection statuses are `ACCEPTED / IN_PROGRESS / COMPLETED / FAILED`. `controller_status.circuit_breaker_active` (line 205) — not `circuit_breaker`. `audit_secrets_used` has no timestamp column.
+- **Provisioning is manual** for this project: the deliverable is JSON files in `dashboards/`, imported by hand.
+- **Legacy dashboards must not be touched** (different UID + datasource `aehkkc60fd69sc`).
+
+## Goals / Non-Goals
+
+**Goals:**
+- Three working, audience-split dashboards bound to `cfucydbdfo1dsc`, each backed by real `fl_control_plane` columns.
+- Reuse the surviving panels' SQL/styling from the combined board verbatim where they pass curation; change only datasource UID, grouping, and per-panel bug fixes.
+- Encode the documented metric semantics (success = completion, resolution time = wall-clock) in each dashboard's `description`.
+
+**Non-Goals (design-level):**
+- No automated Grafana provisioning; no datasource secret handling (user-provisioned from k8s secret).
+- No new application code, migration, or API — read-only visualization.
+- No CI-system breakdown panel (dropped as low-value; the column is already visible in Overview tables).
+
+## Decisions
+
+**Schema qualifier.** SQL keeps qualifier `"USR_E51KMDYETKUR577C31VYQ80TA"`. A HANA user's default schema is its own username, and the datasource connects as that user — high confidence. If a panel errors "invalid schema/table" at import, run `SELECT COUNT(*) FROM "USR_E51KMDYETKUR577C31VYQ80TA"."inspection"` in Grafana Explore and find/replace the qualifier across the three files.
+
+**Three files, split by audience** (over one combined board): matches the user's explicit split and keeps each audience's board scannable.
+- `dashboards/lenny-pipeline-doctor-performance.json` — business KPIs + trends: Inspection Volume, Success Rate %, Avg Resolution Time, Active Repositories (`COUNT(DISTINCT repo_name)`); trends for each (volume/success-rate/duration over time, weekly repository-adoption growth).
+- `dashboards/lenny-pipeline-doctor-inspection-overview.json` — live/operational: Total, Currently Running (`status='IN_PROGRESS'`), Active Fault Handlers (`is_active=TRUE`), Active Handler Executions (`status='running'`); status breakdowns; **Currently Running Inspections** table (`ORDER BY created_at ASC` — oldest first surfaces stuck runs); **Last Executed Inspections** table (`ORDER BY created_at DESC LIMIT 25`); Most Common Failed Stages (top-20 barchart) + over-time; Activated Fault Handlers table.
+- `dashboards/lenny-pipeline-doctor-platform-operations.json` — operator internals: AI token usage (in/out/total/avg/by-model), handler health (executions over time, by fault_id, failures, avg duration, success rate), pipeline-analyzer (stop vs continue, stops by gate), finalizer status, orchestrator health + last sync, secret resolution pie + unavailable count.
+
+**Metric semantics live in `description`** (over renaming panels): "Success Rate" = `status='COMPLETED'` = workflow completion, not proposal quality; "Avg Resolution Time" = `SECONDS_BETWEEN(created_at, finished_at)` = wall-clock including agent scheduling latency (design doc notes Doit scheduling can take minutes).
+
+**Omit Satisfaction & Proposal Accuracy** (over shipping empty panels): the `feedback` table exists (`database.py:448–479`; `assessment` maps cleanly) but nothing writes to it yet. Listed as documented gaps in the Performance `description` so the follow-up is obvious once feedback is wired.
+
+**Fix the orchestrator panel:** `circuit_breaker` → `circuit_breaker_active`.
+
+**HANA SQL idioms** (reused verbatim): `SECONDS_BETWEEN(a,b)`; hourly bucket `TO_TIMESTAMP(ADD_SECONDS('1970-01-01', FLOOR(SECONDS_BETWEEN('1970-01-01', "col") / 3600) * 3600))`; daily `/86400`; weekly `/604800`; Grafana `$__timeFilter("col")`. `audit_secrets_used` has no timestamp, so time-filter via join to `handler_executions.created_at` on `execution_id`.
+
+**Common envelope** for all three: `schemaVersion: 38`, `refresh: "5m"`, `time: now-30d`, `timezone: "utc"`, tags `["fault-localization","lenny-pipeline-doctor"]`, standard annotations block. `gridPos` recomputed sequentially per file; panel `id`s reassigned uniquely per file.
+
+## Risks / Trade-offs
+
+- **Schema qualifier wrong at import** → single find/replace across three files; verification query documented above. Low blast radius.
+- **Empty/near-empty tables** (feedback omitted; telemetry/finalizer may be sparse early) → panels show 0/empty rather than error; acceptable and honest. No fabricated data.
+- **Manual import drift** (three files can diverge or be partially imported) → mitigated by identical envelope and a post-import checklist confirming each panel binds to `cfucydbdfo1dsc` with no "Datasource not found".
+- **`SECONDS_BETWEEN` on NULL `finished_at`** (in-progress rows) → duration/resolution queries must filter `finished_at IS NOT NULL` (and typically `status='COMPLETED'`) to avoid skew.
+
+## Migration Plan
+
+1. Create the three JSON files; validate each with `python -m json.tool`.
+2. Grep to confirm no residual `eew5mat39t4aob`/`aehkkc60fd69sc` and no bare `circuit_breaker` (only `circuit_breaker_active`).
+3. Delete `dashboards/pipeline-fl-control-plane.json`.
+4. Manually import each JSON into Grafana; confirm binding to `cfucydbdfo1dsc` and that panels render.
+5. **Rollback:** dashboards are additive JSON; revert by removing the imported dashboards. Legacy Photon dashboards are never touched, so there is nothing to restore there.
diff --git a/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/proposal.md b/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/proposal.md
new file mode 100644
index 00000000..ac2b2412
--- /dev/null
+++ b/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/proposal.md
@@ -0,0 +1,31 @@
+## Why
+
+The Grafana dashboards for Fault Localization were built for the Thinktank-era `MISSION` model and point at the legacy Photon datasource. After the rearchitecture onto the new `inspection` schema, an interim combined dashboard (`dashboards/pipeline-fl-control-plane.json`) was created but renders "No data" (wrong datasource UID) and was never carefully curated — it contains at least one panel querying a non-existent column. Operators and stakeholders currently have no working monitoring for the rearchitected platform.
+
+## What Changes
+
+- Introduce three focused, working Grafana dashboards bound to the new "Lenny Pipeline Doctor Production" datasource (UID `cfucydbdfo1dsc`), following the naming convention `Pipeline3-Fault-Localization…` → `Lenny Pipeline Doctor…`:
+  - **Performance** — business KPIs (inspection volume, success rate, resolution time, repository adoption) and their trends.
+  - **Inspection Overview** — operational/live state (status breakdown, currently running, last executed, most common failed stages, activated fault handlers).
+  - **Platform Operations** — FL-operator internals (AI token usage, handler health, pipeline-analyzer decisions, finalizer status, orchestrator health, secret resolution).
+- All panel queries target the new schema (`inspection`, `handler_executions`, `fault_handlers`, `handler_agent_telemetry`, `pipeline_analyzer_results`, `finalizer_execution`, `failed_stages`, `controller_status`, `audit_secrets_used`).
+- Fix the broken orchestrator-health panel (`circuit_breaker` → `circuit_breaker_active`).
+- Retire the interim combined dashboard file.
+- Document metric semantics that changed with the rearchitecture: "Success Rate" now means workflow completion (`status='COMPLETED'`), not proposal quality; "Resolution Time" is wall-clock including agent scheduling latency.
+- **Out of scope:** Satisfaction and Proposal Accuracy KPIs (the `feedback` table exists but nothing writes to it yet — documented as gaps); organization adoption (no `org` column); the legacy dashboards (must remain untouched); automated Grafana provisioning; datasource secret handling.
+
+## Capabilities
+
+### New Capabilities
+- `observability-dashboards`: The set of Grafana dashboards that visualize FL platform state from the FL Database — which dashboards exist, their audience, the KPIs/panels each must present, the datasource binding contract, and the metric-semantics documentation requirements.
+
+### Modified Capabilities
+<!-- None. No existing spec's requirements change. -->
+
+## Impact
+
+- **New files:** `dashboards/lenny-pipeline-doctor-performance.json`, `dashboards/lenny-pipeline-doctor-inspection-overview.json`, `dashboards/lenny-pipeline-doctor-platform-operations.json`.
+- **Removed file:** `dashboards/pipeline-fl-control-plane.json` (interim combined dashboard).
+- **Datasource dependency:** the pre-provisioned "Lenny Pipeline Doctor Production" HANA datasource (`cfucydbdfo1dsc`); DB schema `USR_E51KMDYETKUR577C31VYQ80TA`.
+- **No application code change.** Read-only visualization over the existing `fl_control_plane` schema; no migrations, no API changes.
+- **Deployment:** dashboards are imported manually into Grafana (provisioning is manual for this project).
diff --git a/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/specs/observability-dashboards/spec.md b/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/specs/observability-dashboards/spec.md
new file mode 100644
index 00000000..1abc5075
--- /dev/null
+++ b/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/specs/observability-dashboards/spec.md
@@ -0,0 +1,93 @@
+## Purpose
+
+Define the set of Grafana dashboards that visualize Fault Localization ("Lenny Pipeline Doctor") platform state from the FL Database — which dashboards exist, their audience, the KPIs and panels each must present, the datasource-binding contract, and the metric-semantics documentation that must accompany each dashboard.
+
+## ADDED Requirements
+
+### Requirement: Dashboards bind to the Lenny Pipeline Doctor datasource
+
+Every panel in every FL dashboard SHALL query the pre-provisioned "Lenny Pipeline Doctor Production" HANA datasource (UID `cfucydbdfo1dsc`). No panel SHALL reference the legacy Photon datasource (`aehkkc60fd69sc`) or any interim placeholder datasource UID. All SQL SHALL qualify tables with the FL Database schema so queries resolve against the FL `inspection` model rather than the Thinktank `MISSION` model.
+
+#### Scenario: Panel resolves against the new datasource
+
+- **WHEN** any FL dashboard panel is loaded in Grafana
+- **THEN** the panel's datasource UID is `cfucydbdfo1dsc`
+- **AND** no panel references `aehkkc60fd69sc` or any placeholder UID
+- **AND** the panel query targets a table in the FL Database schema (e.g. `inspection`, `handler_executions`, `fault_handlers`)
+
+#### Scenario: Legacy dashboards remain untouched
+
+- **WHEN** the new FL dashboards are introduced
+- **THEN** the existing Thinktank-era "Pipeline3-Fault-Localization…" dashboards are not modified
+- **AND** those legacy dashboards continue to reference their original datasource `aehkkc60fd69sc` and the `MISSION` model
+
+### Requirement: Performance dashboard presents business KPIs and trends
+
+A dashboard named "Lenny Pipeline Doctor - Performance" SHALL present platform-level business KPIs and their trends over time. It SHALL include: inspection volume, success rate, resolution time, and repository adoption, each as a current-value indicator and as a trend over the selected time range.
+
+#### Scenario: Performance KPIs are present
+
+- **WHEN** the Performance dashboard is loaded
+- **THEN** it shows inspection volume, success rate, resolution time, and repository adoption as current-value indicators
+- **AND** it shows a time-series trend for each of those KPIs across the selected time range
+
+### Requirement: Inspection Overview dashboard presents operational and live state
+
+A dashboard named "Lenny Pipeline Doctor - Inspection Overview" SHALL present operational and live inspection state. It SHALL include: total inspection count, a status breakdown across the four inspection statuses (ACCEPTED, IN_PROGRESS, COMPLETED, FAILED), a list of currently running inspections, a list of the most recently executed inspections, the most common failed stages, and the currently activated fault handlers.
+
+#### Scenario: Operational panels are present
+
+- **WHEN** the Inspection Overview dashboard is loaded
+- **THEN** it shows the total inspection count and a status breakdown limited to ACCEPTED, IN_PROGRESS, COMPLETED, and FAILED
+- **AND** it shows a list of currently running inspections and a list of the most recently executed inspections
+- **AND** it shows the most common failed stages and the currently activated fault handlers
+
+#### Scenario: Status breakdown uses only real statuses
+
+- **WHEN** the inspection status breakdown is rendered
+- **THEN** it presents exactly the four persisted inspection statuses
+- **AND** it does not present invented statuses such as "Unresolvable" or "No-Result"
+
+### Requirement: Platform Operations dashboard presents FL-operator internals
+
+A dashboard named "Lenny Pipeline Doctor - Platform Operations" SHALL present platform internals for FL operators. It SHALL include: AI token usage, handler execution health, pipeline-analyzer decisions, finalizer execution status, handler-orchestrator health, and secret resolution sources.
+
+#### Scenario: Operator internals are present
+
+- **WHEN** the Platform Operations dashboard is loaded
+- **THEN** it shows AI token usage, handler execution health, pipeline-analyzer decisions, finalizer execution status, orchestrator health, and secret resolution sources
+
+#### Scenario: Orchestrator health queries the real column
+
+- **WHEN** the orchestrator-health panel queries controller status
+- **THEN** it reads the `circuit_breaker_active` column
+- **AND** it does not reference a non-existent `circuit_breaker` column
+
+### Requirement: Dashboards document metric semantics that changed with the rearchitecture
+
+Each dashboard that presents success rate or resolution time SHALL document, in its description, what the metric now means under the FL `inspection` model. Success rate SHALL be documented as workflow completion (inspection status COMPLETED), not proposal quality. Resolution time SHALL be documented as wall-clock elapsed time from inspection creation to finish, including agent scheduling latency, not pure analysis time.
+
+#### Scenario: Metric semantics are documented
+
+- **WHEN** a dashboard presenting success rate or resolution time is loaded
+- **THEN** its description states that success rate means workflow completion (status COMPLETED), not proposal quality
+- **AND** its description states that resolution time is wall-clock including agent scheduling latency
+
+### Requirement: Deferred KPIs are documented, not fabricated
+
+Satisfaction and Proposal Accuracy KPIs SHALL NOT be presented with fabricated or empty data while no data source populates them. Because the feedback data is not yet written by the platform, these KPIs SHALL be documented as known gaps in the relevant dashboard description rather than shown as panels.
+
+#### Scenario: Satisfaction and Proposal Accuracy are omitted with a documented gap
+
+- **WHEN** the Performance dashboard is loaded
+- **THEN** it does not present Satisfaction or Proposal Accuracy panels
+- **AND** its description records these as deferred KPIs pending feedback data being populated
+
+### Requirement: The interim combined dashboard is retired
+
+The interim combined dashboard file SHALL be removed once the three focused dashboards exist, so there is exactly one working set of FL dashboards and no broken combined dashboard remains.
+
+#### Scenario: Combined dashboard is removed
+
+- **WHEN** the three focused dashboards are in place
+- **THEN** the interim combined dashboard file `dashboards/pipeline-fl-control-plane.json` no longer exists
diff --git a/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/tasks.md b/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/tasks.md
new file mode 100644
index 00000000..1b6b0f7d
--- /dev/null
+++ b/openspec/changes/archive/2026-08-13-lenny-pipeline-doctor-dashboards/tasks.md
@@ -0,0 +1,35 @@
+## 1. Performance dashboard
+
+- [x] 1.1 Create `dashboards/lenny-pipeline-doctor-performance.json` with the common envelope (schemaVersion 38, refresh 5m, time now-30d, timezone utc, tags, annotations) and datasource UID `cfucydbdfo1dsc` on every panel
+- [x] 1.2 Add KPI stat panels: Inspection Volume, Success Rate %, Avg Resolution Time, Active Repositories (`COUNT(DISTINCT repo_name)`)
+- [x] 1.3 Add trend timeseries: Inspection Volume Over Time, Success Rate Over Time (0–100, thresholds 70/90), Avg Resolution Time Over Time, weekly Repository Adoption Growth
+- [x] 1.4 Filter duration/success queries on `finished_at IS NOT NULL` (and `status='COMPLETED'` where appropriate) to avoid NULL skew
+- [x] 1.5 Write the dashboard `description`: Success Rate = workflow completion (not proposal quality); Resolution Time = wall-clock incl. scheduling latency; Satisfaction & Proposal Accuracy documented as deferred gaps
+
+## 2. Inspection Overview dashboard
+
+- [x] 2.1 Create `dashboards/lenny-pipeline-doctor-inspection-overview.json` with the common envelope and datasource UID `cfucydbdfo1dsc`
+- [x] 2.2 Add stat panels: Total Inspections, Currently Running (`status='IN_PROGRESS'`), Active Fault Handlers (`is_active=TRUE`), Active Handler Executions (`status='running'`)
+- [x] 2.3 Add status breakdowns: Inspection Status (only ACCEPTED/IN_PROGRESS/COMPLETED/FAILED) and Handler Execution Status
+- [x] 2.4 Add Currently Running Inspections table (`status='IN_PROGRESS' ORDER BY created_at ASC`; cols created_at, ci_system, repo_name, triggered_by, age)
+- [x] 2.5 Add Last Executed Inspections table (`ORDER BY created_at DESC LIMIT 25`; cols created_at, finished_at, status, ci_system, repo_name, triggered_by; status color-mapped)
+- [x] 2.6 Add Most Common Failed Stages barchart (top-20 by `stage_name`) and Failed Stages Over Time
+- [x] 2.7 Add Activated Fault Handlers table (`fault_handlers WHERE is_active=TRUE`; cols fault_id, execution_type, strategy, ci_systems, registered_at)
+
+## 3. Platform Operations dashboard
+
+- [x] 3.1 Create `dashboards/lenny-pipeline-doctor-platform-operations.json` with the common envelope and datasource UID `cfucydbdfo1dsc`
+- [x] 3.2 Add AI token usage panels: input/output over time, total input, total output, avg tokens/exec, by model
+- [x] 3.3 Add handler health panels: executions over time, by fault_id, failures by fault_id, avg duration by fault_id, success rate
+- [x] 3.4 Add pipeline-analyzer panels: Stop vs Continue, Stops by Gate
+- [x] 3.5 Add Finalizer Execution Status panel
+- [x] 3.6 Add orchestrator panels: Handler Orchestrator Health using `circuit_breaker_active` (not `circuit_breaker`), Last Sync ms
+- [x] 3.7 Add secret panels: Secret Resolution Sources pie and Unavailable Secrets count, time-filtered via join `audit_secrets_used.execution_id → handler_executions.created_at`
+
+## 4. Retire combined dashboard and verify
+
+- [x] 4.1 Delete `dashboards/pipeline-fl-control-plane.json`
+- [x] 4.2 Validate all three files with `python -m json.tool`
+- [x] 4.3 Grep to confirm no residual `eew5mat39t4aob`/`aehkkc60fd69sc` UIDs and no bare `circuit_breaker` (only `circuit_breaker_active`)
+- [ ] 4.4 Manually import each dashboard into Grafana; confirm every panel binds to `cfucydbdfo1dsc` with no "Datasource not found" and panels render
+- [ ] 4.5 Confirm legacy "Pipeline3-Fault-Localization…" dashboards are unchanged (still on datasource `aehkkc60fd69sc`)
diff --git a/openspec/specs/observability-dashboards/spec.md b/openspec/specs/observability-dashboards/spec.md
new file mode 100644
index 00000000..736384fc
--- /dev/null
+++ b/openspec/specs/observability-dashboards/spec.md
@@ -0,0 +1,93 @@
+## Purpose
+
+Define the set of Grafana dashboards that visualize Fault Localization ("Lenny Pipeline Doctor") platform state from the FL Database — which dashboards exist, their audience, the KPIs and panels each must present, the datasource-binding contract, and the metric-semantics documentation that must accompany each dashboard.
+
+## Requirements
+
+### Requirement: Dashboards bind to the Lenny Pipeline Doctor datasource
+
+Every panel in every FL dashboard SHALL query the pre-provisioned "Lenny Pipeline Doctor Production" HANA datasource (UID `cfucydbdfo1dsc`). No panel SHALL reference the legacy Photon datasource (`aehkkc60fd69sc`) or any interim placeholder datasource UID. All SQL SHALL qualify tables with the FL Database schema so queries resolve against the FL `inspection` model rather than the Thinktank `MISSION` model.
+
+#### Scenario: Panel resolves against the new datasource
+
+- **WHEN** any FL dashboard panel is loaded in Grafana
+- **THEN** the panel's datasource UID is `cfucydbdfo1dsc`
+- **AND** no panel references `aehkkc60fd69sc` or any placeholder UID
+- **AND** the panel query targets a table in the FL Database schema (e.g. `inspection`, `handler_executions`, `fault_handlers`)
+
+#### Scenario: Legacy dashboards remain untouched
+
+- **WHEN** the new FL dashboards are introduced
+- **THEN** the existing Thinktank-era "Pipeline3-Fault-Localization…" dashboards are not modified
+- **AND** those legacy dashboards continue to reference their original datasource `aehkkc60fd69sc` and the `MISSION` model
+
+### Requirement: Performance dashboard presents business KPIs and trends
+
+A dashboard named "Lenny Pipeline Doctor - Performance" SHALL present platform-level business KPIs and their trends over time. It SHALL include: inspection volume, success rate, resolution time, and repository adoption, each as a current-value indicator and as a trend over the selected time range.
+
+#### Scenario: Performance KPIs are present
+
+- **WHEN** the Performance dashboard is loaded
+- **THEN** it shows inspection volume, success rate, resolution time, and repository adoption as current-value indicators
+- **AND** it shows a time-series trend for each of those KPIs across the selected time range
+
+### Requirement: Inspection Overview dashboard presents operational and live state
+
+A dashboard named "Lenny Pipeline Doctor - Inspection Overview" SHALL present operational and live inspection state. It SHALL include: total inspection count, a status breakdown across the four inspection statuses (ACCEPTED, IN_PROGRESS, COMPLETED, FAILED), a list of currently running inspections, a list of the most recently executed inspections, the most common failed stages, and the currently activated fault handlers.
+
+#### Scenario: Operational panels are present
+
+- **WHEN** the Inspection Overview dashboard is loaded
+- **THEN** it shows the total inspection count and a status breakdown limited to ACCEPTED, IN_PROGRESS, COMPLETED, and FAILED
+- **AND** it shows a list of currently running inspections and a list of the most recently executed inspections
+- **AND** it shows the most common failed stages and the currently activated fault handlers
+
+#### Scenario: Status breakdown uses only real statuses
+
+- **WHEN** the inspection status breakdown is rendered
+- **THEN** it presents exactly the four persisted inspection statuses
+- **AND** it does not present invented statuses such as "Unresolvable" or "No-Result"
+
+### Requirement: Platform Operations dashboard presents FL-operator internals
+
+A dashboard named "Lenny Pipeline Doctor - Platform Operations" SHALL present platform internals for FL operators. It SHALL include: AI token usage, handler execution health, pipeline-analyzer decisions, finalizer execution status, handler-orchestrator health, and secret resolution sources.
+
+#### Scenario: Operator internals are present
+
+- **WHEN** the Platform Operations dashboard is loaded
+- **THEN** it shows AI token usage, handler execution health, pipeline-analyzer decisions, finalizer execution status, orchestrator health, and secret resolution sources
+
+#### Scenario: Orchestrator health queries the real column
+
+- **WHEN** the orchestrator-health panel queries controller status
+- **THEN** it reads the `circuit_breaker_active` column
+- **AND** it does not reference a non-existent `circuit_breaker` column
+
+### Requirement: Dashboards document metric semantics that changed with the rearchitecture
+
+Each dashboard that presents success rate or resolution time SHALL document, in its description, what the metric now means under the FL `inspection` model. Success rate SHALL be documented as workflow completion (inspection status COMPLETED), not proposal quality. Resolution time SHALL be documented as wall-clock elapsed time from inspection creation to finish, including agent scheduling latency, not pure analysis time.
+
+#### Scenario: Metric semantics are documented
+
+- **WHEN** a dashboard presenting success rate or resolution time is loaded
+- **THEN** its description states that success rate means workflow completion (status COMPLETED), not proposal quality
+- **AND** its description states that resolution time is wall-clock including agent scheduling latency
+
+### Requirement: Deferred KPIs are documented, not fabricated
+
+Satisfaction and Proposal Accuracy KPIs SHALL NOT be presented with fabricated or empty data while no data source populates them. Because the feedback data is not yet written by the platform, these KPIs SHALL be documented as known gaps in the relevant dashboard description rather than shown as panels.
+
+#### Scenario: Satisfaction and Proposal Accuracy are omitted with a documented gap
+
+- **WHEN** the Performance dashboard is loaded
+- **THEN** it does not present Satisfaction or Proposal Accuracy panels
+- **AND** its description records these as deferred KPIs pending feedback data being populated
+
+### Requirement: The interim combined dashboard is retired
+
+The interim combined dashboard file SHALL be removed once the three focused dashboards exist, so there is exactly one working set of FL dashboards and no broken combined dashboard remains.
+
+#### Scenario: Combined dashboard is removed
+
+- **WHEN** the three focused dashboards are in place
+- **THEN** the interim combined dashboard file `dashboards/pipeline-fl-control-plane.json` no longer exists

```
