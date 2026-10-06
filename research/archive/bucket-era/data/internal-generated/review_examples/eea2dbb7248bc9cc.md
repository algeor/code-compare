# eea2dbb7248bc9cc

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/7
Suggested label: 35%
File overlap: 1.0
Changed-line overlap: 0.0

## Suggested diff
```diff
--- a/.gitignore
+++ b/.gitignore
@@
+# Ignore macOS files
```

## Landed PR diff
```diff
diff --git a/.gitignore b/.gitignore
new file mode 100644
index 00000000..18d69547
--- /dev/null
+++ b/.gitignore
@@ -0,0 +1,10 @@
+# Ignore IDE files
+.idea
+
+#Ignore macos files
+.DS_Store
+
+# AI assistant files
+.claude/
+.cline/
+.clinerules/
\ No newline at end of file
diff --git a/docs/design/FL_Architecture_Design.md b/docs/design/FL_Architecture_Design.md
index d3c19d2d..97709742 100644
--- a/docs/design/FL_Architecture_Design.md
+++ b/docs/design/FL_Architecture_Design.md
@@ -125,55 +125,70 @@ The FL team consumes the Agent API; it does not operate the agent runtime itself
                     Pipeline Failure Event
                             |
                             v
-                  +--------------------+
-                  |   FL Control Plane |
-                  |                    |
-                  |  +--------------+  |
-                  |  | Ingestion    |  |     CI Infrastructure
-                  |  | API          |<-------(Jenkins / GHA / Azure)
-                  |  +--------------+  |
-                  |         |          |
-                  |         v          |
-                  |  +--------------+  |
-                  |  | Pipeline     |  |     Platform Gates
-                  |  | Analyzer     |<-------(WIP detection, opt-in)
-                  |  +--------------+  |
-                  |         |          |
-                  |         v          |
-                  |  +--------------+  |
-                  |  | Check        |  |     FaultHandler CRs
-                  |  | Orchestrator |<-------(from Failure Checks Repo)
-                  |  +--------------+  |
-                  |         |          |
-                  |         v          |
-                  |  +--------------+  |
-                  |  | Execution    |  |     k8s Jobs
-                  |  | Engine       |-------> (AgentTask / CustomRuntime)
-                  |  +--------------+  |
-                  |         |          |
-                  |         v          |
-                  |  +--------------+  |
-                  |  | Result       |  |
-                  |  | Collector    |  |
-                  |  +--------------+  |
-                  +--------------------+
-                            |
-                            v
-                   Analysis Results
-                   (to Developer / CI)
+                  +-------------------------+
+                  |    FL Control Plane     |
+                  |                         |
+                  |  +-------------------+  |
+                  |  | Ingestion API     |<-------(Jenkins / GHA / Azure)
+                  |  | (mission UUID)    |  |
+                  |  +-------------------+  |
+                  |           |             |
+                  |           v             |
+                  |  +-------------------+  |
+                  |  | Metadata          |--+--> HDLF fl-active/<uuid>/
+                  |  | Extractor         |  |       metadata.json
+                  |  +-------------------+  |
+                  |           |             |
+                  |           v             |
+                  |  +-------------------+  |     Platform Gates
+                  |  | Pipeline Analyzer |<-------(WIP, opt-in, kill switch)
+                  |  +-------------------+  |
+                  |           |             |
+                  |           v             |
+                  |  +-------------------+  |
+                  |  | Data Extractor    |--+--> HDLF fl-active/<uuid>/
+                  |  | (sync wait)       |  |       stages/, artifacts/, ...
+                  |  +-------------------+  |       manifest.json (last)
+                  |           |             |
+                  |           v             |
+                  |  +-------------------+  |     FaultHandler CRs
+                  |  | Handler           |<-------(from Failure Checks Repo)
+                  |  | Orchestrator      |  |
+                  |  +-------------------+  |
+                  |           |             |
+                  |           v             |
+                  |  +-------------------+  |     k8s Jobs
+                  |  | Execution Engine  |------>(AgentTask / CustomRuntime)
+                  |  +-------------------+  |       reads via SDK from HDLF
+                  |           |             |
+                  |           v             |
+                  |  +-------------------+  |
+                  |  | Result Collector  |  |
+                  |  +-------------------+  |
+                  +-------------------------+
+                              |
+                              v
+                     Analysis Results
+                     (to Developer / CI)
+
+   HDLF containers:
+     fl-active     6-month TTL (default for all missions)
+     fl-preserved  no TTL (manual save-from-active)
 ```
 
 ### 4.1 FL Control Plane Components
 
 | Component | Responsibility |
 |---|---|
-| **Ingestion API** | Receives failure events; normalizes pipeline metadata across CI systems |
-| **Pipeline Analyzer** | Fetches failed stages and logs; evaluates platform-level gates |
-| **Handler Orchestrator** | Discovers registered FaultHandlers; evaluates applicability; produces execution plan |
+| **Ingestion API** | Receives failure events; generates the mission UUID; persists initial mission state (`ACCEPTED`) |
+| **Metadata Extractor** | Pre-Analyzer; pulls Jenkins URL, PR URL, commit ID; creates the per-mission HDLF folder; writes `metadata.json` (see `data-to-hdlf` change) |
+| **Pipeline Analyzer** | Evaluates platform-level gates; prepares the analysis context; triggers the Data Extractor on success |
+| **Data Extractor** | Synchronous bulk capture of pipeline data into the per-mission HDLF folder; writes `manifest.json` last (see `data-to-hdlf` change) |
+| **Handler Orchestrator** | Discovers registered FaultHandlers; evaluates applicability; schedules handler Jobs only after Data Extractor success |
 | **Execution Engine** | Schedules k8s Jobs for applicable handlers; mounts secrets; manages lifecycle |
 | **Result Collector** | Gathers findings from completed handlers; normalizes output |
-| **Admin UI** | CI instance registration; handler management; configuration; log viewing (see §12.7) |
-| **Pipeline Data API** | SDK/REST API for handlers to access pipeline data (see §7) |
+| **Admin UI** | CI instance registration; handler management; configuration; log viewing (see §12.7); manual mission preservation; manual mission retry |
+| **Pipeline Data API** | SDK/REST API for handlers to access pipeline data — reads exclusively from HDLF, no live-CI fallback (see §7) |
 
 ### 4.2 Runtime Environment
 
@@ -390,15 +405,15 @@ Activation is resolved hierarchically (higher overrides lower):
 
 ### 7.2 Tier 1 — Pipeline Data API
 
-Available to all handlers (AgentTask and CustomRuntime) via REST or SDK client.
+Available to all handlers (AgentTask and CustomRuntime) via REST or SDK client. All methods read from HDLF (`fl-active` first, falling back to `fl-preserved`); none of them call CI APIs.
 
 | Method | Returns | Notes |
 |---|---|---|
-| `get_pipeline_metadata()` | Repo URL, branch, commit, CI system, PR info | Always available |
-| `get_failed_stages()` | List of stage names + status | Pre-fetched by FL |
-| `get_stage_log(stage)` | Raw log text | |
-| `list_artifacts(pattern)` | Artifact paths matching glob | |
-| `get_artifact(path)` | Artifact content (binary or text) | |
+| `get_pipeline_metadata()` | Repo URL, branch, commit, CI system, PR info | Backed by `metadata.json` in the per-mission HDLF folder |
+| `get_failed_stages()` | List of stage names + status | Backed by the WFAPI describe payload captured by the Data Extractor |
+| `get_stage_log(stage)` | Raw log text | May be head+tail-truncated (with marker) for very large logs (see `data-extraction` spec) |
+| `list_artifacts(pattern)` | Artifact paths matching glob | Returns only artifacts present in the snapshot manifest |
+| `get_artifact(path)` | Artifact content (binary or text) | Raises `DataNotInSnapshot(reason)` if the manifest entry is `skipped_size` / `skipped_mission_cap` / `skipped_unreachable` / not present |
 
 ### 7.3 Source Code Access
 
@@ -906,33 +921,47 @@ These probes ensure that transient failures (e.g., a crashed worker, a lost data
 
 ## 15. Data Management and Retention
 
-### 15.1 Hot Storage — FL Database
+FL data lives in two places with separate lifecycles: the FL Database (HANA Cloud) for **structured analysis records**, and HDLF for **raw pipeline data**.
+
+### 15.1 FL Database — analysis records (HANA Cloud)
+
+Analysis results, handler execution records, mission state, and related metadata are stored in the FL Database (HANA Cloud). This is the primary store queried by the MCP server, Feedback UI, Admin UI, and alerting.
 
-Analysis results, handler execution records, and related metadata are stored in the FL Database (HANA Cloud) for active use. This is the primary store queried by the MCP server, Feedback UI, Admin UI, and alerting.
+The mission lifecycle is tracked by a `state` column on the missions row, with values `ACCEPTED → METADATA_EXTRACTOR → PIPELINE_ANALYZER → DATA_EXTRACTOR → HANDLERS → COMPLETED`, plus the terminal `FAILED` (see the `data-to-hdlf` change for the full state machine).
 
-### 15.2 Cold Storage — HDLF Archival
+### 15.2 HDLF — raw pipeline data per mission
 
-To bound the size of the FL Database, a **scheduled Kubernetes CronJob** runs periodically and moves analysis data older than **14 days** to an HDLF (SAP HANA Data Lake Files) container.
+Each mission's raw pipeline data (build metadata, stage logs, artifacts, test reports, WFAPI graph) is captured into a per-mission folder named after the mission UUID. The capture is performed by the Metadata Extractor (small structured fields up front) and the Data Extractor (everything else), as described in §4.1 and the `data-to-hdlf` change.
 
 ```
-FL CronJob (scheduled)
-    → Query FL Database for records older than 14 days
-    → Write records to HDLF container
-    → Delete archived records from FL Database
+hdlf://fl-active/<mission_uuid>/
+    metadata.json            ← Metadata Extractor
+    stages/<stage>/console.log
+    artifacts/<path>
+    tests/<file>
+    manifest.json            ← Data Extractor (final write; presence = "complete")
 ```
 
-Archived data in HDLF may be used for:
-- Reporting and trend analysis
-- Historical context for handlers (exact usage patterns to be defined in a later stage)
+Two HDLF containers, with different retention policies:
+
+| Container | Retention | Purpose |
+|---|---|---|
+| `fl-active` | Container-level auto-deletion at 6 months | Default for every mission |
+| `fl-preserved` | No auto-deletion | Manual save-from-active for missions worth keeping indefinitely |
+
+**Read order for any FL component or external reader (SDK, MCP, future tooling):** check `fl-active` first; if not present, fall back to `fl-preserved`; if not in either, surface "data not available."
+
+**Preservation:** an operator (or a future Admin UI button) runs the preservation script with a `mission_uuid`. The script recursively copies `fl-active/<uuid>/` into `fl-preserved/<uuid>/`. The original copy in `fl-active` is left to expire at the 6-month TTL; the preserved copy survives.
 
-The HDLF container is configured with an **automatic retention policy** that deletes data older than a configurable period (e.g., one year). The retention period is set by the FL team during operational setup.
+**HDLF authentication:** all FL pods that talk to HDLF mount the same `fl-hdlf-tls` k8s Secret as a folder containing `client.crt`, `client.key`, `ca.crt`. A single client identity is used across the platform.
 
 ### 15.3 Data Lifecycle Summary
 
 | Store | Contains | Retention |
 |---|---|---|
-| FL Database (HANA Cloud) | Active analysis results, handler execution records, feedback | 14 days (then archived) |
-| HDLF container | Archived analysis data | Configurable; default 1 year |
+| FL Database (HANA Cloud) | Mission state, analysis results, handler execution records, feedback | Driven by analysis-record lifecycle (TBD; not subject to a 14-day archival CronJob in the new model) |
+| HDLF `fl-active` | Per-mission raw pipeline data folder | 6-month container-level TTL |
+| HDLF `fl-preserved` | Per-mission folders explicitly preserved by an operator | No auto-deletion |
 
 ---
 
diff --git a/openspec/changes/data-to-hdlf/.openspec.yaml b/openspec/changes/data-to-hdlf/.openspec.yaml
new file mode 100644
index 00000000..231e3abc
--- /dev/null
+++ b/openspec/changes/data-to-hdlf/.openspec.yaml
@@ -0,0 +1,2 @@
+schema: spec-driven
+created: 2026-05-18
diff --git a/openspec/changes/data-to-hdlf/design.md b/openspec/changes/data-to-hdlf/design.md
new file mode 100644
index 00000000..1d1f2cc5
--- /dev/null
+++ b/openspec/changes/data-to-hdlf/design.md
@@ -0,0 +1,220 @@
+## Context
+
+The FL Control Plane processes ~500 missions/day. Today every component (Pipeline Analyzer, handlers via the Pipeline Data SDK) reads pipeline data live from the source CI system. Jenkins, in particular, has aggressive build retention (frequently configured to "keep last 10 builds") — by the time a developer wants to re-analyze a failure, or by the time an improved handler is rolled out, the underlying build data may be gone.
+
+This change introduces an upstream **capture step** for the raw pipeline data: each mission's data is pulled from Jenkins into a per-mission folder in HDLF (SAP HANA Data Lake Files) before handlers run. From that point on, every read goes against HDLF — handlers, MCP, future analytics. CI APIs are touched only by the two extraction components.
+
+**Volume baseline (Jenkins, today):** typical mission ≈ 20 MB raw (≈ 11 MB console log, ≈ 1 MB artifacts, plus stage info / WFAPI / metadata). At 500 missions/day uncompressed and unfiltered that is ≈ 3.65 TB/year. Not problematic at this scale; we accept the storage and defer compression.
+
+**Constraints:**
+- Synchronous pipeline: handlers must not start until the Data Extractor has succeeded.
+- HDLF access is via WebHDFS-style REST with mTLS (client cert + key + CA chain).
+- The FL Database (HANA) carries the mission lifecycle state machine; HDLF carries the bulk pipeline data.
+- The platform is Kyma; we have k8s primitives (Secrets, ConfigMaps, Jobs, CronJobs) available.
+
+**Stakeholders:** FL team (owns extractors, SDK changes, HDLF wiring), handler contributors (read from HDLF only), platform operators (manage HDLF cert, retention, preservation script).
+
+## Goals / Non-Goals
+
+**Goals:**
+- Decouple handler execution from CI-system retention: handlers only need HDLF.
+- Make a mission's pipeline data fully recoverable for ≥ 6 months by default and indefinitely on opt-in.
+- Resume an interrupted extraction without redoing completed work.
+- Bound memory usage during extraction (no GB-scale buffers in pod RSS).
+- Provide explicit completeness guarantees: a snapshot is "complete" iff `manifest.json` is present.
+- Provide a state machine that pinpoints which component holds the mission, for retry, observability, and operator action.
+
+**Non-Goals:**
+- Compression, deduplication, or columnar formats. Deferred until storage cost or read patterns demand it.
+- Parallel downloads inside a single Data Extractor invocation. v1 is serial; revisit if extraction wall-clock becomes a problem.
+- Auto-retry of perma-failed missions. v1 has manual retry only.
+- Persisting per-file capture history beyond what `manifest.json` records.
+- Streaming reads from HDLF for very large files in handlers (handlers fetch whole files via SDK).
+- A snapshot for non-Jenkins CI systems in v1. The component shapes are CI-neutral but only Jenkins is implemented now.
+
+## Decisions
+
+### D1: Per-mission folder, mission UUID as the path key
+
+**Decision:** Each mission gets a single HDLF folder named after its mission UUID (created by the Ingestion API). All extractors and downstream readers reference data only by mission UUID.
+
+```
+hdlf://fl-active/<mission_uuid>/
+   metadata.json            ← Metadata Extractor
+   manifest.json            ← Data Extractor (final write)
+   stages/<stage>/console.log
+   stages/<stage>/steps.json
+   artifacts/<path>
+   tests/<file>
+```
+
+**Rationale:** A folder per mission is the smallest atomic unit that fits the lifecycle (preservation, deletion, reads). Mission UUID is opaque, collision-free, and already generated upstream.
+
+**Alternatives considered:**
+- Date-partitioned (`/year=/month=/day=/build=...`): better for analytics-style scans, worse for the per-mission lookup pattern that drives FL.
+- Content-addressed dedup at file level: deferred — at our volume, dedup savings don't justify the complexity.
+
+### D2: Two extraction components — Metadata Extractor (pre-Analyzer) and Data Extractor (post-Analyzer)
+
+**Decision:** The Metadata Extractor runs immediately after the Ingestion API and before the Pipeline Analyzer; it captures only Jenkins URL, PR URL, and commit ID into `metadata.json`. The Data Extractor runs after the Pipeline Analyzer completes; it captures everything else and writes `manifest.json` last.
+
+**Rationale:** Splitting the two phases gives the Pipeline Analyzer cheap structured access to mission metadata via a small HDLF read, without paying the cost of a full extraction for missions that the Analyzer will reject. A failure in the Metadata Extractor cleanly fails the mission early; a failure in the Data Extractor fails the mission late but only after the Analyzer's decisions were free.
+
+**Alternatives considered:**
+- Single combined extractor before the Analyzer: pays full extraction cost for every accepted mission, including those the Analyzer would later reject. Worse latency.
+- Single extractor after the Analyzer: Analyzer would have no clean way to reach metadata it doesn't fetch from GitHub. Also defers mission-folder creation, complicating resume logic.
+- SDK-driven lazy capture: rejected — does not capture data nothing reads, defeating the durability goal.
+
+### D3: Synchronous wait between Data Extractor and handler scheduling
+
+**Decision:** The Handler Orchestrator schedules handler Jobs only after the Data Extractor has reported success (`manifest.json` written, mission state advanced to `HANDLERS`). If the Data Extractor fails, the mission is marked `FAILED`; no handlers run.
+
+**Rationale:** Eliminates the race between handler reads and capture progress. Removes the dual code path of "live fetch as fallback." Simplifies the SDK and the handler contract: data either is in HDLF or isn't, and the manifest tells the story.
+
+**Trade-off:** Adds the Data Extractor's wall-clock (~30 s typical) to per-mission latency. This is tolerable because FL's overall latency target is minutes and the agent execution dwarfs extraction time.
+
+**Alternatives considered:**
+- Async extraction with SDK fallback to live Jenkins: previous direction. Rejected by the FL team because (a) the dual path doubled the Jenkins call surface and (b) the manifest-vs-live divergence was a recurring source of subtle bugs.
+
+### D4: In-process today, k8s Job migration deferred
+
+**Decision:** The Data Extractor (and Metadata Extractor) ship in v1 as in-process Python modules invoked synchronously from the FL service. They are organized as self-contained packages (`fl/metadata_extractor/`, `fl/data_extractor/`) with a single public entry-point function each, so a future migration to a k8s Job is a wrapper change, not a logic change.
+
+**Rationale:** The project is in active build-out; the cost of standing up k8s Job infrastructure right now exceeds the operational benefit at low traffic. By keeping the extractor logic in its own module with a clean function signature, we preserve a near-trivial migration path: add a `__main__.py` entry point, wrap with `subprocess.run` or a Job spec, swap a single trigger call.
+
+**Trade-off:** Until migration, OOM in extraction can take down the FL pod and any concurrent missions on it. Mitigations:
+1. Strict per-mission size cap (250 MB).
+2. Streaming downloads with `.tmp` + rename, never buffering full files in memory.
+3. Honest revisit of the Job migration before production traffic.
+
+**Alternatives considered:**
+- Threads inside the FL service: same memory pool as the rest of FL; dangerous given mission size variance.
+- k8s Job from day one: more setup, more glue, more runtime cost; not justified at current traffic.
+- Subprocess (separate process, same pod): better than thread, worse than Job. Available as a swappable trigger if it becomes useful.
+
+### D5: Stream-to-disk download, never to memory
+
+**Decision:** All extractor downloads stream HTTP responses to a local file in an ephemeral disk (`emptyDir` volume), then upload to HDLF, then delete the local file. No file is ever held entirely in process memory. The HTTP `Content-Length` (when present) is checked pre-fetch and the request is aborted if it exceeds the per-file cap; if the header is missing, the stream is monitored and aborted mid-stream when the cap is reached.
+
+**Rationale:** A 5 GB console log buffered in memory OOMs the pod. Stream-to-disk caps memory at one HTTP buffer (kilobytes). Local disk is bounded by `emptyDir` size, which we provision generously and which is wiped between missions.
+
+### D6: Manifest is written last; its presence is the completion signal
+
+**Decision:** The Data Extractor writes per-file outputs as it goes. The very last write of a successful run is `manifest.json`. Its presence in the mission folder is the canonical signal "this snapshot is complete." Its absence means resume is required.
+
+**Rationale:** Object storage doesn't give us cheap atomic multi-file commits. A single sentinel write is the simplest correct alternative. It also gives readers a one-shot check before deciding what to do.
+
+### D7: Resume by listing the folder, skipping what's already there, cleaning up `.tmp`
+
+**Decision:** When the Data Extractor starts and finds the mission folder already exists but `manifest.json` does not, it:
+1. Lists the folder.
+2. Treats any `<name>.tmp` file as garbage from a prior interrupted run and deletes it.
+3. For each item in the capture plan, skips it if a same-named non-`.tmp` file already exists.
+4. Streams remaining items as `<name>.tmp`, then renames to `<name>` (atomic in WebHDFS via the `RENAME` op).
+5. Writes `manifest.json` last.
+
+**Rationale:** Avoids re-downloading already-captured content (cheap resume). The `.tmp`-rename pattern protects against partially-written files being mistaken for complete ones.
+
+**Trade-off:** A file completed in a previous run but corrupted (truncated by a long-since-killed process that didn't use rename) would be skipped. We accept this because rename is the standard atomic-commit pattern; if a non-tmp file is present, treat it as complete.
+
+### D8: Mission state as a single column with predecessor-only-advance
+
+**Decision:** `missions.state` is a string column with the values `ACCEPTED`, `METADATA_EXTRACTOR`, `PIPELINE_ANALYZER`, `DATA_EXTRACTOR`, `HANDLERS`, `COMPLETED`, `FAILED`. Each component, before writing its own state, performs a conditional `UPDATE ... WHERE state = '<predecessor>'`. If 0 rows update, the component refuses to proceed (someone else owns the mission, or the prior step never finished). `FAILED` is terminal until manual retry, which resets the state to the failed component's predecessor.
+
+**Rationale:** The smallest possible state model that captures "where is this mission now." Predecessor-only-advance gives strict ordering and a natural concurrency guard without locks. SQL-native — no extra coordination service needed.
+
+**Deferred:** Companion columns (`state_since`, `attempt`, `last_error`) — useful for stuck-mission detection and operator forensics — to be added when the schema is formally designed before production traffic.
+
+### D9: Two HDLF containers — `fl-active` (6mo TTL) and `fl-preserved` (manual)
+
+**Decision:** All missions land in `fl-active`, which has a container-level retention policy that auto-deletes mission folders older than 6 months. A separate container, `fl-preserved`, has no auto-deletion. Missions are promoted to `fl-preserved` by an explicit operator action — initially a manual script, later an Admin UI button — that copies the entire mission folder. The original copy in `fl-active` is left to expire naturally; the `fl-preserved` copy survives.
+
+**Read order:** Readers (SDK, MCP, future tooling) check `fl-active` first; if the mission folder is not present, fall back to `fl-preserved`; if not present in either, surface "not available."
+
+**Rationale:** Container-level retention is HDLF-native and cheap to operate (no per-file TTL bookkeeping). Two containers make "preserve forever" a one-line copy and unambiguous to reason about — there's no metadata-flag-on-an-active-mission complexity.
+
+**Trade-offs:**
+- A mission preserved on day 5 of its lifecycle exists in both containers for ~6 months. Slight storage duplication, judged acceptable.
+- "Move" instead of "copy" was rejected because it loses the natural cleanup of the active copy and complicates the read-order logic for in-flight queries.
+
+### D10: Per-file 100 MB cap, per-mission 250 MB cap, head+tail truncation for console logs
+
+**Decision:** Each individual file capture caps at 100 MB; total mission capture caps at 250 MB. When a file exceeds its cap:
+- **Console log:** truncated to the **first 50 MB + last 50 MB**, joined into a single file with the marker `[OMITTED N MB FROM ORIGINAL LOG]` between the two halves. Implemented as one file because tools (handlers, MCP) treat console logs as plain text streams.
+- **Other files:** replaced by a small placeholder JSON recording `original_size`, `sha256_if_obtainable`, `mtime`, `skipped: true`, `reason: "per_file_cap"`.
+
+When the per-mission total cap is approaching:
+- Items already in the **priority allowlist** (manifest.json itself, metadata.json, WFAPI describe, JUnit/test reports, stage logs) are captured first and never sacrificed.
+- Remaining items are processed in **mtime descending** order (latest first); items that don't fit get the placeholder treatment.
+
+**Rationale:** Failure context is overwhelmingly at the *end* of a console log; the first 50 MB still captures setup context that's often informative. mtime-descending preserves the most recent (and typically most relevant) artifacts when caps bite. Priority allowlist guarantees that the small structured items — the bulk of analytical value — always survive.
+
+### D11: Pipeline Data SDK reads exclusively from HDLF; manifest tells the truth
+
+**Decision:** The Pipeline Data SDK is rewired so handler-side reads (`get_stage_log`, `list_artifacts`, `get_artifact`, `get_pipeline_metadata`) go to HDLF, not Jenkins. The SDK reads `manifest.json` to determine each item's status:
+- `captured` → return content from HDLF.
+- `truncated` (console log) → return content from HDLF; the truncation marker is part of the data.
+- `skipped_size` / `skipped_unreachable` → raise `DataNotInSnapshot(reason)`. The SDK does **not** silently fall back to Jenkins.
+- Item not in manifest → raise `DataNotInSnapshot(reason="not_in_capture_plan")`.
+
+**Rationale:** A single source of truth (HDLF + manifest) eliminates the dual-path complexity of "live or cached?" Handlers get explicit error semantics that they can react to (degraded mode, alternative analysis paths) instead of silently doing the wrong thing.
+
+### D12: HDLF cert as a folder-mounted k8s Secret; same identity across components
+
+**Decision:** A k8s Secret named `fl-hdlf-tls` contains three keys: `client.crt`, `client.key`, `ca.crt`. It is mounted as a folder volume at a fixed path (proposed: `/etc/hdlf-tls/`) into every FL pod that talks to HDLF (Metadata Extractor, Data Extractor, Pipeline Data SDK consumers, MCP server, future Admin UI backend). All components use the same client identity.
+
+**Rationale:** Single identity = single audit surface = single rotation procedure. Folder mount keeps the cert/key/CA together and matches the SAP HANA Data Lake Files Python sample idiom (`ssl_context.load_cert_chain(certfile, keyfile)`). A k8s Secret is the standard rotation surface; rotation is a Secret update + pod roll.
+
+**Open:** Rotation cadence and ownership (manual? cert-manager? BTP-managed?) — to be defined operationally, not in code.
+
+### D13: Retry classes — retry transient HTTP errors, give up on client errors, manual retry only at the mission level
+
+**Decision:** Within the extractor, individual HTTP requests retry on the following codes/conditions: `408 Request Timeout`, `429 Too Many Requests`, `500/502/503/504`, network/timeout/connection-reset errors. Backoff is exponential with jitter; the `Retry-After` header is honored when present (especially for 429). Other 4xx codes are not retried (they indicate a client-side problem that won't resolve by repeating). Internal retry budget per request: default 3 attempts, configurable.
+
+At the **mission** level: when the Data Extractor exhausts retries and gives up, the mission is marked `FAILED`. There is no automatic retry of failed missions in v1. Operators (and eventually the Admin UI) can trigger a manual retry, which resets the mission state to the failed component's predecessor and re-invokes the component. Retry on the same `mission_uuid` reuses the existing mission folder via the resume logic (D7).
+
+**Rationale:** Auto-retrying perma-failed missions risks hammering a struggling Jenkins or HDLF endpoint; manual retry forces a human to look at the failure (a healthy operational signal) before re-spending capacity. Within a mission, transient errors are common enough that aggressive retry is the right default — the alternative is mission failures driven by 30-second Jenkins blips.
+
+## Risks / Trade-offs
+
+**[OOM during in-process extraction]** → A runaway log can exhaust the FL pod's memory and crash concurrent missions. Mitigation: Strict per-file cap (100 MB) and per-mission cap (250 MB) + stream-to-disk. Hard mitigation if it bites in practice: migrate the Data Extractor to a k8s Job (pre-designed in D4 as a swap, not a rewrite).
+
+**[Synchronous wait adds latency]** → Every mission pays the Data Extractor wall-clock before any handler starts. Mitigation: At ~30 s typical and a multi-minute end-to-end target, this is invisible. If a future use case demands sub-30s latency, the Data Extractor itself becomes the optimization target (parallelism, pre-fetch, etc.).
+
+**[Manifest as single point of failure]** → If `manifest.json` writes succeed but later HDLF state corrupts it, readers will treat a complete snapshot as incomplete or vice versa. Mitigation: Manifest is small (a few KB) and atomic to write; HDLF is highly durable. We do not engineer further fallbacks in v1.
+
+**[State machine concurrency]** → Two parallel attempts to advance state for the same mission are guarded by SQL conditional UPDATE; this is correct but lacks `state_since` until the schema lands, so a "wedged" mission cannot be auto-detected before then. Mitigation: For v1, operators monitor manually. Add `state_since` + stuck-mission CronJob before production traffic — explicitly tracked as deferred.
+
+**[Cert rotation]** → A bad rotation breaks all FL HDLF traffic at once (single identity). Mitigation: Standard k8s Secret rotation procedure with a canary pod; explicit operational runbook to be authored before production.
+
+**[`fl-active` 6-month TTL on the mission folder vs partial-write semantics]** → If a mission interrupts and resumes after >6 months, the folder may have been deleted. Mitigation: The 6-month window is far longer than any realistic resume interval; if the folder is gone, a fresh extraction starts.
+
+**[Storage growth]** → ~3.65 TB/year uncompressed at 500/day. Mitigation: Acceptable today; defer compression. If volume grows or scope expands (more CI systems), revisit and add gzip per-file (low complexity, ~75% savings on log-dominated content).
+
+**[Preservation discipline]** → Without a clear governance signal, missions worth preserving may auto-expire because no one ran the script. Mitigation: Document the preservation workflow; surface "preservable mission" prompts in the future Admin UI; eventually consider auto-preservation policies (e.g., "preserve all missions tagged `incident:`") — not in v1.
+
+## Migration Plan
+
+This change can land before the underlying `fl-control-plane-rearchitecture` is fully deployed; the new components and contracts are additive in code and replace specific Decisions in the parent change.
+
+1. **Update parent change (`fl-control-plane-rearchitecture`)** — adjust D10 to reference this change for raw-data lifecycle; note that `pipeline-data-sdk` no longer falls back to live CI; note that two new components sit before/after the Pipeline Analyzer.
+2. **Update `docs/design/FL_Architecture_Design.md`** — add Metadata Extractor and Data Extractor to the High-Level Architecture diagram; revise §15 (Data Management) to describe per-mission HDLF folders and the two-container model; revise §7 (Pipeline Data SDK) to note HDLF-only reads.
+3. **Provision HDLF containers** — `fl-active` with a 6-month container-level retention policy; `fl-preserved` with no retention. Provision the `fl-hdlf-tls` k8s Secret with client cert, key, CA chain.
+4. **Implement the modules** — `fl/metadata_extractor/` and `fl/data_extractor/` as in-process Python packages with a single entry function each. Wire into the FL request path: Ingestion API → Metadata Extractor → Pipeline Analyzer → Data Extractor → Handler Orchestrator.
+5. **Add the `missions.state` column** — initial values: ACCEPTED on Ingestion, advanced by each component via conditional UPDATE.
+6. **Rewire the Pipeline Data SDK** — reads only from HDLF; manifest-driven status; `DataNotInSnapshot` exception class.
+7. **Author the manual preservation script** — `scripts/preserve-mission.py <mission_uuid>` copies the folder from `fl-active` to `fl-preserved`.
+8. **End-to-end smoke test** — synthetic Jenkins build through the full pipeline; assert mission folder structure, manifest contents, handler reads.
+9. **Handler migration** — existing handlers (when ported as FaultHandler CRs) read via the SDK; no Jenkins calls remain in handler code.
+
+**Rollback:** Until step 9, both paths can be supported with a feature flag (handler reads from HDLF *or* live CI). Once step 9 lands and is verified, remove the live-CI code path. Rollback before step 9 is a feature-flag flip; after step 9, it requires a code revert and redeploy.
+
+## Open Questions
+
+1. **`state_since` schema details** — exact column name, datatype, and the stuck-mission detection threshold (default proposal: 30 minutes). To be locked in when the FL DB schema is formally designed, before production traffic.
+2. **HDLF cert rotation** — manual procedure vs. cert-manager vs. BTP-managed. Operational decision; not in code.
+3. **Admin UI integration points** — exact UX for the "preserve mission" button and the "retry failed mission" button. Belongs in the Admin UI design effort.
+4. **Stuck-mission CronJob** — when does it run, what does it do (alert vs. auto-FAIL vs. both), how is it tested? Defer until `state_since` lands.
+5. **Concrete `Retry-After` parsing nuances** — handling of HTTP-date vs. delta-seconds formats, capping max wait time. Implementation detail; documented when written.
+6. **Future: parallel downloads inside the Data Extractor** — currently serial. If extraction wall-clock becomes a bottleneck, introduce a bounded worker pool with a max-concurrent-requests-per-Jenkins-host setting to avoid hammering Jenkins.
+7. **Future: GHA / Azure DevOps capture adapters** — share the manifest format and lifecycle with the Jenkins capture; per-CI-system extractor implementations.
diff --git a/openspec/changes/data-to-hdlf/proposal.md b/openspec/changes/data-to-hdlf/proposal.md
new file mode 100644
index 00000000..ec9b1371
--- /dev/null
+++ b/openspec/changes/data-to-hdlf/proposal.md
@@ -0,0 +1,47 @@
+## Why
+
+FL today reads pipeline data live from Jenkins every time a handler runs. Jenkins build retention is short and operator-controlled — by the time someone wants to re-analyze a failure (a week later, three months later, with an improved handler) the data may already be gone. We want to capture each mission's pipeline data into HDLF before handlers run, so analysis is decoupled from Jenkins retention and historical missions remain available for re-analysis.
+
+## What Changes
+
+- **NEW** Metadata Extractor — runs immediately after Ingestion API, before the Pipeline Analyzer. Pulls a small set of high-value fields (Jenkins URL, PR URL, commit ID) from Jenkins and writes a `metadata.json` into a per-mission HDLF folder named after the mission UUID.
+- **NEW** Data Extractor — runs synchronously after the Pipeline Analyzer, before the Handler Orchestrator. Pulls the full set of Jenkins build artifacts and stage logs into the same per-mission HDLF folder. Writes a `manifest.json` last as the completion marker.
+- **NEW** Two HDLF containers: `fl-active` (6-month TTL, default for all missions) and `fl-preserved` (no TTL, manual save-from-active). Read order: active first, fall back to preserved.
+- **NEW** Resume-on-restart logic — if a mission folder exists in HDLF without a `manifest.json`, the Data Extractor lists the folder and skips files already present, retrying only the missing pieces. Atomic per-file writes via `.tmp` + rename.
+- **NEW** Per-file (100 MB) and per-mission (250 MB) safety caps with truncation policy: console logs use head-50MB + tail-50MB with a marker; other oversized items get a placeholder JSON with original metadata. Truncation order is mtime descending (latest-first).
+- **NEW** Mission state field in the FL database: a single column tracking which component is currently handling the mission (`ACCEPTED`, `METADATA_EXTRACTOR`, `PIPELINE_ANALYZER`, `DATA_EXTRACTOR`, `HANDLERS`, `COMPLETED`, `FAILED`). Each component may only advance the state if the current value is its predecessor's name. `FAILED` is terminal until manual retry.
+- **NEW** HDLF cert handling — k8s Secret mounted as a folder containing `client.crt`, `client.key`, `ca.crt`. Used by all FL components that talk to HDLF.
+- **NEW** Manual preservation script (and future Admin UI button) that copies a mission folder from `fl-active` to `fl-preserved` so it survives the 6-month TTL.
+- **MODIFIED** Pipeline Data SDK — handlers (and any other downstream reader) read pipeline data exclusively from HDLF. The SDK no longer falls back to live CI APIs for handler reads.
+- **MODIFIED** Handler Orchestrator — schedules handlers only after the Data Extractor has completed successfully. If Data Extractor fails, the mission fails.
+- **BREAKING** The previously specified "HANA hot, 14-day archival CronJob to HDLF" data-lifecycle is replaced by the per-mission folder model with TTL-based container retention. Active analysis records still live in HANA, but the **raw Jenkins data** has its own lifecycle in HDLF (`fl-active` 6mo / `fl-preserved` indefinite).
+- **BREAKING** Handlers can no longer assume CI infrastructure is live during their execution. They read from HDLF via the SDK; if a piece of data was not captured (snapshot truncated, request to a now-gone Jenkins URL skipped), the SDK surfaces that explicitly.
+
+## Capabilities
+
+### New Capabilities
+
+- `metadata-extraction`: Pre-analyzer extraction of high-value mission metadata into HDLF; creates the per-mission HDLF folder; writes `metadata.json`.
+- `data-extraction`: Post-analyzer bulk capture of Jenkins build data (logs, artifacts, test reports, stage info) into the per-mission HDLF folder; manifest written as final completion marker; resume-on-restart support.
+- `mission-state`: Single-column FL-database state machine tracking which component owns the mission, with predecessor-only-advance invariant; basis for retry, observability, and manual recovery.
+- `hdlf-storage`: Two-container HDLF layout (`fl-active` + `fl-preserved`); read fallback order; cert-folder mount pattern for FL components; preservation script (and future Admin UI control).
+
+### Modified Capabilities
+
+None directly modified by this change. The parent change `fl-control-plane-rearchitecture` is not yet archived; its draft spec deltas will be updated in place (outside the OpenSpec MODIFIED workflow) to reflect the integration points described in §Impact below — specifically:
+
+- `pipeline-data-sdk` will read exclusively from HDLF (no live-CI fallback for handler-side reads).
+- `handler-orchestrator` will schedule handlers only after Data Extractor success.
+- `data-lifecycle` raw-pipeline-data lifecycle is delegated to this change.
+- `pipeline-analyzer` will trigger the Data Extractor after its own work completes.
+- `ingestion-api` will generate the mission UUID and write the initial `ACCEPTED` mission-state row.
+
+## Impact
+
+- **FL Control Plane**: Two new components in the request path (Metadata Extractor before Analyzer, Data Extractor after Analyzer). Synchronous wait between Data Extractor completion and handler scheduling.
+- **FL Database (HANA)**: New `missions.state` column (and supporting timestamps when the schema lands); new transitions written by each component; CronJob (later) for stuck-mission detection.
+- **HDLF**: Two new containers (`fl-active`, `fl-preserved`) with retention policies. Per-mission folder layout. Cert files provisioned and mounted into FL pods.
+- **Handlers**: No more direct or SDK-mediated calls to Jenkins. All reads go through SDK → HDLF. Handlers become truly portable across CI systems because the SDK is the only data interface.
+- **Operators**: New mission states visible in dashboards/Admin UI. New manual preservation workflow. New stuck-mission detection (post-DB-schema).
+- **Latency**: ~30 seconds typical added per mission (Data Extractor synchronous wait). Acceptable given multi-minute end-to-end FL latency targets.
+- **Existing fl-control-plane-rearchitecture change**: This change supersedes its `data-lifecycle` decision (D10) for the *raw pipeline data* lifecycle and adjusts `pipeline-data-sdk`, `pipeline-analyzer`, and `handler-orchestrator` accordingly.
\ No newline at end of file
diff --git a/openspec/changes/data-to-hdlf/specs/data-extraction/spec.md b/openspec/changes/data-to-hdlf/specs/data-extraction/spec.md
new file mode 100644
index 00000000..d33560f2
--- /dev/null
+++ b/openspec/changes/data-to-hdlf/specs/data-extraction/spec.md
@@ -0,0 +1,103 @@
+## ADDED Requirements
+
+### Requirement: Data Extractor runs after Pipeline Analyzer and before handlers
+The Data Extractor SHALL execute after the Pipeline Analyzer has reported success and before any handler is scheduled. The Handler Orchestrator SHALL NOT schedule any handler Job for a mission until the Data Extractor has reported success for that mission.
+
+#### Scenario: Successful data extraction precedes handler scheduling
+- **WHEN** the Pipeline Analyzer reports success for a mission and accepts the mission for handler dispatch
+- **THEN** the Data Extractor is invoked next, no handler Jobs are scheduled, and handler scheduling proceeds only after the Data Extractor reports success
+
+#### Scenario: Data Extractor failure fails the mission
+- **WHEN** the Data Extractor exhausts its internal retries and cannot complete extraction
+- **THEN** the mission is marked `FAILED`, no handlers are scheduled, and the failure is surfaced in the mission status
+
+### Requirement: Data Extractor captures Jenkins build data into the per-mission HDLF folder
+The Data Extractor SHALL capture, into the same per-mission HDLF folder created by the Metadata Extractor, the following Jenkins data: build summary metadata, parameters, environment, SCM changelog, Jenkinsfile, WFAPI pipeline graph, per-stage status, per-stage console logs, JUnit/test reports, and all build artifacts that are not excluded by safety caps.
+
+#### Scenario: Standard mission capture
+- **WHEN** the Data Extractor processes a Jenkins-sourced mission with build summary, two stages, JUnit results, and 30 small artifacts
+- **THEN** `fl-active/<uuid>/` contains build metadata, per-stage console logs, the WFAPI describe payload, the JUnit reports, and all 30 artifacts, each as captured files
+
+### Requirement: Data Extractor uses streaming downloads with per-file and per-mission size caps
+The Data Extractor SHALL not buffer downloaded HTTP responses entirely in memory. It SHALL stream each HTTP body to a local ephemeral disk, then upload from disk to HDLF, then delete the local file. Per-file capture is capped at 100 MB by default. Total per-mission capture is capped at 250 MB by default. Both caps SHALL be configurable.
+
+#### Scenario: Pre-flight Content-Length over the per-file cap
+- **WHEN** the Data Extractor issues an HTTP request whose `Content-Length` exceeds the per-file cap and the file is not the console log
+- **THEN** the request is aborted before the body is fetched, and the manifest entry for that item is `skipped_size` with `original_size` recorded
+
+#### Scenario: Mid-stream cap exceeded with no Content-Length
+- **WHEN** an HTTP response has no `Content-Length` and the streamed bytes received exceed the per-file cap during the download
+- **THEN** the stream is aborted, any partial local file is deleted, and the manifest entry for that item is `skipped_size`
+
+#### Scenario: Per-mission cap reached
+- **WHEN** the cumulative captured size for a mission reaches the per-mission cap and there are still pending items
+- **THEN** the remaining items are recorded as `skipped_mission_cap` placeholders in the manifest and no further HTTP fetches for the mission are attempted
+
+### Requirement: Console log truncation uses head plus tail
+The Data Extractor SHALL apply head-plus-tail truncation when a console log exceeds the per-file cap: it SHALL store the first 50 MB of the log, followed by the marker text `[OMITTED N MB FROM ORIGINAL LOG]` (with `N` replaced by the omitted byte count converted to MB), followed by the last 50 MB of the log. The output SHALL be a single file at the same path that an untruncated console log would occupy.
+
+#### Scenario: Console log over the cap
+- **WHEN** the Data Extractor encounters a console log whose original size is 320 MB
+- **THEN** the captured file is approximately 100 MB, contains the first 50 MB of the original, then a single `[OMITTED 220 MB FROM ORIGINAL LOG]` marker line, then the last 50 MB; the manifest entry status is `truncated`
+
+### Requirement: Priority allowlist captured first; remaining items in mtime descending order
+The Data Extractor SHALL process its capture plan in two passes: items matching the priority allowlist (manifest.json itself, metadata.json, WFAPI describe, JUnit/test reports, per-stage console logs, coverage reports) SHALL be captured first, in their natural order. Remaining items SHALL be captured in `mtime` descending order (latest first).
+
+#### Scenario: Priority items survive even when caps are tight
+- **WHEN** a mission would exceed the per-mission cap if all artifacts were captured
+- **THEN** the priority allowlist is captured to completion before any non-priority artifact is attempted, and only non-priority items are converted into `skipped_mission_cap` placeholders
+
+#### Scenario: Latest-first ordering for non-priority items
+- **WHEN** non-priority artifacts are processed and the per-mission cap is approached
+- **THEN** the artifacts captured are those with the most recent `mtime` values; the older artifacts are recorded as `skipped_mission_cap`
+
+### Requirement: Atomic per-file writes via .tmp + rename
+The Data Extractor SHALL upload each captured item first as `<final_name>.tmp` and then rename it to `<final_name>` using HDLF's rename operation. A reader SHALL never observe a partially written non-`.tmp` file.
+
+#### Scenario: Crash during upload of a single file
+- **WHEN** the Data Extractor crashes after creating `foo.tmp` but before renaming it
+- **THEN** on resume, `foo.tmp` is detected as garbage from the previous run and is deleted before the file is re-fetched
+
+### Requirement: Resume on restart when manifest.json is absent
+When the Data Extractor starts for a mission and finds the per-mission folder already exists but `manifest.json` is absent, the extractor SHALL list the folder, delete any `<name>.tmp` files, skip any non-`.tmp` files already present (treating them as previously captured), and capture only the missing items.
+
+#### Scenario: Resume after interruption
+- **WHEN** the Data Extractor is invoked for a mission whose folder contains 18 already-captured non-`.tmp` files, 1 stale `.tmp` file, and no `manifest.json`
+- **THEN** the extractor deletes the `.tmp` file, skips the 18 captured files, captures the remaining items in the plan, and writes `manifest.json` last
+
+#### Scenario: No resume needed when manifest is present
+- **WHEN** the Data Extractor is invoked for a mission whose folder already contains a `manifest.json`
+- **THEN** the extractor reports success immediately without re-fetching anything
+
+### Requirement: Manifest written last; presence is the completion signal
+The Data Extractor SHALL write `manifest.json` as the last write of a successful run. The manifest SHALL list every item that was part of the capture plan, each with one of the following statuses: `captured`, `truncated`, `skipped_size`, `skipped_mission_cap`, `skipped_unreachable`. The presence of `manifest.json` in a mission folder SHALL be the canonical signal that the snapshot is complete; its absence SHALL mean the snapshot is incomplete.
+
+#### Scenario: Successful run produces manifest
+- **WHEN** the Data Extractor completes successfully for a mission with 50 capture-plan items
+- **THEN** `fl-active/<uuid>/manifest.json` exists and lists all 50 items with their statuses
+
+#### Scenario: Failed run does not produce manifest
+- **WHEN** the Data Extractor exhausts retries and gives up before completing capture
+- **THEN** `manifest.json` does not exist in the mission folder, and the mission is marked `FAILED`
+
+### Requirement: HTTP retry classes
+The Data Extractor SHALL retry an individual HTTP request when the response is `408 Request Timeout`, `429 Too Many Requests`, `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout`, or when the request fails with a network/timeout/connection-reset error. It SHALL NOT retry other 4xx responses. Retries SHALL use exponential backoff with jitter; when the response includes a `Retry-After` header, the extractor SHALL respect it.
+
+#### Scenario: 503 response retried
+- **WHEN** Jenkins returns 503 for an artifact request
+- **THEN** the request is retried with exponential backoff; if it eventually succeeds within the per-request retry budget, the file is captured
+
+#### Scenario: 404 response not retried
+- **WHEN** Jenkins returns 404 for an expected stage log
+- **THEN** the request is not retried, the manifest entry for the stage log is `skipped_unreachable`, and the extractor proceeds to the next item
+
+#### Scenario: 429 with Retry-After
+- **WHEN** Jenkins returns 429 with a `Retry-After: 5` header
+- **THEN** the extractor waits at least 5 seconds before retrying
+
+### Requirement: HDLF authentication via shared cert mount
+The Data Extractor SHALL use the `fl-hdlf-tls` k8s Secret (mounted as a folder containing `client.crt`, `client.key`, `ca.crt`) for all HDLF requests. It SHALL NOT load HDLF credentials from any other source.
+
+#### Scenario: Cert mount missing
+- **WHEN** the Data Extractor starts and the expected HDLF cert files are not present at the configured mount path
+- **THEN** the extractor fails fast with a configuration error and does not attempt any HDLF request
\ No newline at end of file
diff --git a/openspec/changes/data-to-hdlf/specs/hdlf-storage/spec.md b/openspec/changes/data-to-hdlf/specs/hdlf-storage/spec.md
new file mode 100644
index 00000000..463f78a3
--- /dev/null
+++ b/openspec/changes/data-to-hdlf/specs/hdlf-storage/spec.md
@@ -0,0 +1,75 @@
+## ADDED Requirements
+
+### Requirement: Two HDLF containers — `fl-active` (6-month TTL) and `fl-preserved` (no TTL)
+The FL platform SHALL provision two HDLF containers: `fl-active` with a container-level retention policy that auto-deletes mission folders older than 6 months, and `fl-preserved` with no auto-deletion policy. All new mission folders SHALL be created in `fl-active`.
+
+#### Scenario: New mission lands in fl-active
+- **WHEN** the Metadata Extractor creates the per-mission folder for a new mission
+- **THEN** the folder exists at `fl-active/<mission_uuid>/` and not in `fl-preserved`
+
+#### Scenario: Active retention deletes old missions
+- **WHEN** a mission folder in `fl-active` is older than 6 months
+- **THEN** the folder is deleted by the HDLF container-level retention policy without any FL action required
+
+#### Scenario: Preserved container ignores time
+- **WHEN** a mission folder has been in `fl-preserved` for 18 months
+- **THEN** the folder still exists; HDLF retention does not delete it
+
+### Requirement: Mission preservation copies the entire folder from `fl-active` to `fl-preserved`
+Promoting a mission to long-term retention SHALL be implemented as a recursive copy of the entire mission folder from `fl-active` to `fl-preserved`. The original copy in `fl-active` SHALL NOT be moved or deleted by the preservation operation; it is left to expire by the active container's retention policy. The preservation operation SHALL be idempotent: re-running it on an already-preserved mission SHALL leave both copies unchanged.
+
+#### Scenario: Preservation copies the folder
+- **WHEN** an operator runs the preservation script (or invokes the future Admin UI button) for mission `<uuid>`
+- **THEN** all files under `fl-active/<uuid>/` are copied to `fl-preserved/<uuid>/`, the original `fl-active` copy is unchanged, and the script reports success
+
+#### Scenario: Preservation is idempotent
+- **WHEN** the preservation operation is invoked twice for the same mission
+- **THEN** the second invocation completes without error and the contents of `fl-preserved/<uuid>/` are byte-identical to those after the first invocation
+
+#### Scenario: Preservation of an unknown mission
+- **WHEN** the preservation operation is invoked for a `mission_uuid` not present in `fl-active`
+- **THEN** the operation fails with a clear error and no folder is created in `fl-preserved`
+
+### Requirement: Read order — `fl-active` first, then `fl-preserved` fallback
+Any FL component or external reader (Pipeline Data SDK, MCP server, future tooling) reading a mission's data SHALL check `fl-active` first; if the mission folder does not exist there, it SHALL fall back to `fl-preserved`. If the folder is absent in both, the reader SHALL report "data not available" without further fallback.
+
+#### Scenario: Recently-active mission found in fl-active
+- **WHEN** a reader requests data for a mission whose folder exists in `fl-active`
+- **THEN** the reader returns data from `fl-active` and does not query `fl-preserved`
+
+#### Scenario: Aged-out mission found in fl-preserved
+- **WHEN** a reader requests data for a mission whose folder no longer exists in `fl-active` but does exist in `fl-preserved`
+- **THEN** the reader returns data from `fl-preserved`
+
+#### Scenario: Mission not in either container
+- **WHEN** a reader requests data for a `mission_uuid` not present in either container
+- **THEN** the reader reports "not available" and does not consult any other source
+
+### Requirement: HDLF cert mount for FL components
+HDLF authentication SHALL use a single k8s Secret named `fl-hdlf-tls` containing exactly three keys: `client.crt`, `client.key`, `ca.crt`. The Secret SHALL be mounted as a folder volume at a fixed path into every FL pod that talks to HDLF (Metadata Extractor, Data Extractor, Pipeline Data SDK consumers, MCP server, Admin UI backend). All FL components SHALL use the same client identity for HDLF.
+
+#### Scenario: Cert files available at the configured path
+- **WHEN** an FL pod that talks to HDLF starts
+- **THEN** the configured mount path contains exactly the files `client.crt`, `client.key`, and `ca.crt`, sourced from the `fl-hdlf-tls` Secret
+
+#### Scenario: Cert rotation
+- **WHEN** the `fl-hdlf-tls` Secret is updated with new cert/key/CA contents and pods are rolled
+- **THEN** subsequent HDLF requests from the rolled pods use the new credentials, with no FL code change
+
+### Requirement: Per-mission folder layout is uniform across containers
+A preserved mission's folder layout in `fl-preserved` SHALL be byte-identical to its source layout in `fl-active`. No FL component SHALL rely on container-specific layout differences.
+
+#### Scenario: Layout consistency after preservation
+- **WHEN** a mission has been preserved
+- **THEN** for every file present at `fl-active/<uuid>/<path>` at the moment of preservation, the same file is present at `fl-preserved/<uuid>/<path>` with the same content
+
+### Requirement: Manual preservation script as the v1 entry point
+The FL platform SHALL provide a manual preservation script (e.g., `scripts/preserve-mission.py`) that an operator can invoke with a `mission_uuid` argument to perform the preservation operation. The script SHALL implement the requirements above (copy semantics, idempotency, error reporting). An Admin UI surface for the same operation MAY be added later but is not required for v1.
+
+#### Scenario: Operator runs the script successfully
+- **WHEN** an operator runs `scripts/preserve-mission.py <uuid>` for a known active mission
+- **THEN** the script preserves the mission per the above requirements and exits with status 0
+
+#### Scenario: Operator passes an unknown UUID
+- **WHEN** an operator runs the script with a `mission_uuid` not present in `fl-active`
+- **THEN** the script exits non-zero with a clear error message and does not modify either container
\ No newline at end of file
diff --git a/openspec/changes/data-to-hdlf/specs/metadata-extraction/spec.md b/openspec/changes/data-to-hdlf/specs/metadata-extraction/spec.md
new file mode 100644
index 00000000..877f535e
--- /dev/null
+++ b/openspec/changes/data-to-hdlf/specs/metadata-extraction/spec.md
@@ -0,0 +1,48 @@
+## ADDED Requirements
+
+### Requirement: Metadata Extractor runs before Pipeline Analyzer
+The Metadata Extractor SHALL execute as the first FL component invoked after the Ingestion API for every mission. It SHALL run before the Pipeline Analyzer is invoked. The Pipeline Analyzer SHALL NOT be invoked until the Metadata Extractor has reported success.
+
+#### Scenario: Successful metadata extraction precedes analyzer
+- **WHEN** a mission is accepted by the Ingestion API and reaches the `ACCEPTED` state
+- **THEN** the Metadata Extractor is invoked next, the Pipeline Analyzer is not yet invoked, and the Pipeline Analyzer is invoked only after the Metadata Extractor reports success
+
+#### Scenario: Metadata Extractor failure stops the mission
+- **WHEN** the Metadata Extractor cannot extract or persist metadata for a mission
+- **THEN** the mission is marked `FAILED`, the Pipeline Analyzer is not invoked, and no further FL components for that mission run until a manual retry is triggered
+
+### Requirement: Metadata Extractor creates the per-mission HDLF folder
+The Metadata Extractor SHALL create an HDLF folder named after the mission UUID inside the `fl-active` container. All subsequent FL components writing data for the mission SHALL write into this folder.
+
+#### Scenario: Folder created on first execution
+- **WHEN** the Metadata Extractor processes mission UUID `<uuid>`
+- **THEN** an HDLF folder `fl-active/<uuid>/` exists by the time the Metadata Extractor reports success
+
+#### Scenario: Folder reused on retry
+- **WHEN** the Metadata Extractor is re-invoked for a mission whose folder already exists in `fl-active`
+- **THEN** it reuses the existing folder and does not create a duplicate
+
+### Requirement: Metadata Extractor writes metadata.json with the mission's high-value identifiers
+The Metadata Extractor SHALL write a file named `metadata.json` inside the per-mission folder. The file SHALL include at minimum: Jenkins URL, PR URL, commit ID. Additional fields MAY be added in future without breaking existing readers.
+
+#### Scenario: metadata.json contains required identifiers
+- **WHEN** the Metadata Extractor reports success for a Jenkins-sourced mission
+- **THEN** `fl-active/<uuid>/metadata.json` exists and contains the Jenkins URL, the PR URL (if available from the event), and the commit ID
+
+#### Scenario: Missing optional fields do not fail extraction
+- **WHEN** the source event does not provide a PR URL (e.g., a non-PR build)
+- **THEN** the Metadata Extractor still writes `metadata.json` with the fields available; the absent field is recorded as `null` and the extractor reports success
+
+### Requirement: Metadata Extractor uses streaming downloads with safety caps
+The Metadata Extractor SHALL not buffer downloaded HTTP responses entirely in memory. It SHALL stream to a local ephemeral disk and then upload to HDLF. Per-file size caps defined for the Data Extractor (D10) apply to any HTTP fetch the Metadata Extractor performs.
+
+#### Scenario: Pre-flight Content-Length over the cap
+- **WHEN** the Metadata Extractor issues an HTTP request whose `Content-Length` exceeds the per-file cap
+- **THEN** the request is aborted before the body is fetched, and the extractor records the failure with reason `per_file_cap`
+
+### Requirement: Metadata Extractor authenticates to HDLF via the shared cert mount
+The Metadata Extractor SHALL use the `fl-hdlf-tls` k8s Secret (mounted as a folder containing `client.crt`, `client.key`, `ca.crt`) for all HDLF requests. It SHALL NOT load HDLF credentials from any other source.
+
+#### Scenario: Cert mount missing
+- **WHEN** the Metadata Extractor starts and the expected HDLF cert files are not present at the configured mount path
+- **THEN** the extractor fails fast with a configuration error and does not attempt any HDLF request
\ No newline at end of file
diff --git a/openspec/changes/data-to-hdlf/specs/mission-state/spec.md b/openspec/changes/data-to-hdlf/specs/mission-state/spec.md
new file mode 100644
index 00000000..9552a24d
--- /dev/null
+++ b/openspec/changes/data-to-hdlf/specs/mission-state/spec.md
@@ -0,0 +1,59 @@
+## ADDED Requirements
+
+### Requirement: Mission state column with explicit allowed values
+The FL database SHALL store a `state` field on each mission. The allowed values SHALL be exactly: `ACCEPTED`, `METADATA_EXTRACTOR`, `PIPELINE_ANALYZER`, `DATA_EXTRACTOR`, `HANDLERS`, `COMPLETED`, `FAILED`. No other values SHALL be written.
+
+#### Scenario: Initial state on Ingestion
+- **WHEN** a mission is accepted by the Ingestion API
+- **THEN** the mission row exists in the database with `state = 'ACCEPTED'`
+
+#### Scenario: Reject unrecognized state value
+- **WHEN** any code path attempts to write a `state` value not in the allowed set
+- **THEN** the write SHALL fail (database constraint or application-level validation)
+
+### Requirement: Predecessor-only-advance invariant
+A component SHALL only advance a mission's state if the current value equals the component's predecessor in the pipeline. The advance SHALL be implemented atomically (e.g., a conditional `UPDATE ... WHERE state = '<predecessor>'`). If the conditional update affects 0 rows, the component SHALL refuse to proceed and SHALL NOT process the mission.
+
+The expected predecessor for each state is:
+
+| Component / new state | Allowed predecessor |
+|---|---|
+| `METADATA_EXTRACTOR` | `ACCEPTED` |
+| `PIPELINE_ANALYZER` | `METADATA_EXTRACTOR` |
+| `DATA_EXTRACTOR` | `PIPELINE_ANALYZER` |
+| `HANDLERS` | `DATA_EXTRACTOR` |
+| `COMPLETED` | `HANDLERS` |
+
+#### Scenario: Pipeline Analyzer advances state correctly
+- **WHEN** the Pipeline Analyzer begins processing a mission whose current state is `METADATA_EXTRACTOR`
+- **THEN** the conditional `UPDATE missions SET state = 'PIPELINE_ANALYZER' WHERE mission_uuid = ? AND state = 'METADATA_EXTRACTOR'` succeeds and the analyzer proceeds
+
+#### Scenario: Component refuses to act when state has not been advanced from its predecessor
+- **WHEN** the Data Extractor is invoked for a mission whose current state is `ACCEPTED` (the Pipeline Analyzer was skipped)
+- **THEN** the conditional UPDATE for `DATA_EXTRACTOR` affects 0 rows and the Data Extractor refuses to proceed without modifying any mission data
+
+#### Scenario: Concurrent advance attempts are serialized
+- **WHEN** two parallel invocations of the same component attempt to advance the same mission's state
+- **THEN** at most one of the conditional UPDATE statements affects 1 row; the other affects 0 rows and the second invocation refuses to proceed
+
+### Requirement: FAILED is terminal until manual retry
+The `FAILED` state SHALL be terminal: no automatic transition out of `FAILED` is permitted. A manual retry SHALL be the only path out of `FAILED`. A manual retry SHALL reset the state to the predecessor of the failed component (e.g., a Data Extractor failure resets to `PIPELINE_ANALYZER`) before re-invoking the failed component.
+
+#### Scenario: Mission stays FAILED until acted upon
+- **WHEN** a mission's state becomes `FAILED`
+- **THEN** no FL component automatically advances the state, and the mission remains `FAILED` until a manual retry is performed
+
+#### Scenario: Manual retry resets to the failed component's predecessor
+- **WHEN** an operator triggers a manual retry of a mission that failed in the Data Extractor
+- **THEN** the mission's `state` is set to `PIPELINE_ANALYZER` and the Data Extractor is re-invoked
+
+### Requirement: Any FL component may write the FAILED state on its own scope
+A component SHALL set a mission's state to `FAILED` only when it is itself the current owner of the mission (i.e., the current `state` value is the component's name). Setting `FAILED` SHALL be implemented as a conditional UPDATE constrained to the component's own state value.
+
+#### Scenario: Data Extractor marks FAILED on exhaustion
+- **WHEN** the Data Extractor exhausts retries while the mission state is `DATA_EXTRACTOR`
+- **THEN** the conditional `UPDATE ... SET state = 'FAILED' WHERE mission_uuid = ? AND state = 'DATA_EXTRACTOR'` succeeds and the mission is marked failed
+
+#### Scenario: Component cannot mark another component's mission FAILED
+- **WHEN** the Data Extractor attempts to set `FAILED` for a mission whose state is `HANDLERS`
+- **THEN** the conditional UPDATE affects 0 rows and the state remains `HANDLERS`
\ No newline at end of file
diff --git a/openspec/changes/data-to-hdlf/tasks.md b/openspec/changes/data-to-hdlf/tasks.md
new file mode 100644
index 00000000..bc0033ae
--- /dev/null
+++ b/openspec/changes/data-to-hdlf/tasks.md
@@ -0,0 +1,110 @@
+## 1. Infrastructure provisioning
+
+- [ ] 1.1 Provision the `fl-active` HDLF container with a 6-month container-level retention policy
+- [ ] 1.2 Provision the `fl-preserved` HDLF container with no auto-deletion
+- [ ] 1.3 Provision the `fl-hdlf-tls` k8s Secret containing `client.crt`, `client.key`, `ca.crt`
+- [ ] 1.4 Add the Secret folder mount to FL Helm chart for components that talk to HDLF (Metadata Extractor, Data Extractor, SDK consumers, MCP server, Admin UI backend)
+- [ ] 1.5 Document the operational runbook for HDLF cert rotation
+
+## 2. Shared HDLF client library
+
+- [ ] 2.1 Create `fl/hdlf_client/` module wrapping WebHDFS REST with mTLS using the mounted certs
+- [ ] 2.2 Implement `put_object`, `put_object_atomic` (`.tmp` + rename), `get_object`, `delete_object`, `list_dir`, `exists`, `copy_recursive`, `head` with retry on 408/429/5xx and `Retry-After` handling
+- [ ] 2.3 Unit test the client against a fake WebHDFS responder (httpx mock or similar)
+- [ ] 2.4 Implement read order helper: `read_with_fallback(uuid, path)` that checks `fl-active` then `fl-preserved`
+
+## 3. Mission state schema
+
+- [ ] 3.1 Add the `state` column to the `missions` table (Alembic migration)
+- [ ] 3.2 Add an enum/check constraint to the column for the seven allowed values
+- [ ] 3.3 Implement `mission_state.advance(uuid, expected_predecessor, new_state)` helper backed by a conditional UPDATE
+- [ ] 3.4 Implement `mission_state.mark_failed(uuid, expected_current)` helper backed by a conditional UPDATE
+- [ ] 3.5 Unit test the advance / mark_failed helpers (including 0-row outcomes and concurrent attempts)
+
+## 4. Ingestion API integration
+
+- [ ] 4.1 Generate `mission_uuid` on accept; insert the missions row with `state = 'ACCEPTED'`
+- [ ] 4.2 Hand off to the Metadata Extractor only after the row is committed
+- [ ] 4.3 Smoke test: an accepted mission has a row with the right state
+
+## 5. Metadata Extractor module
+
+- [ ] 5.1 Create `fl/metadata_extractor/` package with a single public entry function `extract_metadata(mission_uuid, source_event) -> Result`
+- [ ] 5.2 Implement state advance from `ACCEPTED` to `METADATA_EXTRACTOR` at the start
+- [ ] 5.3 Create the per-mission folder in `fl-active` (idempotent on retry)
+- [ ] 5.4 Pull Jenkins URL, PR URL (nullable), commit ID from the source event / Jenkins API
+- [ ] 5.5 Write `metadata.json` atomically (`.tmp` + rename) into the folder
+- [ ] 5.6 On failure, mark the mission `FAILED` (conditional update)
+- [ ] 5.7 Unit tests: happy path, missing-PR-URL path, HDLF write error, predecessor mismatch
+
+## 6. Data Extractor module
+
+- [ ] 6.1 Create `fl/data_extractor/` package with a single public entry function `extract_data(mission_uuid) -> Result`
+- [ ] 6.2 Implement state advance from `PIPELINE_ANALYZER` to `DATA_EXTRACTOR` at the start
+- [ ] 6.3 Build the capture plan: build summary, params, env, SCM changelog, Jenkinsfile, WFAPI describe, per-stage status, per-stage console logs, JUnit/test reports, all artifacts
+- [ ] 6.4 Implement the priority allowlist (manifest, metadata, WFAPI, JUnit, stage logs, coverage)
+- [ ] 6.5 Implement the streaming downloader: HEAD pre-flight + stream-to-disk + abort on cap
+- [ ] 6.6 Implement per-file (100 MB) and per-mission (250 MB) caps; both configurable
+- [ ] 6.7 Implement console-log head+tail truncation with the `[OMITTED N MB FROM ORIGINAL LOG]` marker
+- [ ] 6.8 Implement non-priority ordering: mtime descending
+- [ ] 6.9 Implement resume logic: list folder, delete `.tmp` files, skip existing non-`.tmp` files
+- [ ] 6.10 Write `manifest.json` last with per-item statuses (`captured`, `truncated`, `skipped_size`, `skipped_mission_cap`, `skipped_unreachable`)
+- [ ] 6.11 On exhausted retries / unrecoverable error, mark the mission `FAILED`
+- [ ] 6.12 Unit tests: capture plan generation, cap behaviors, console-log truncation, resume logic, manifest correctness, retry classes
+
+## 7. Pipeline Analyzer wiring
+
+- [ ] 7.1 Advance state from `METADATA_EXTRACTOR` to `PIPELINE_ANALYZER` at the start
+- [ ] 7.2 On success, invoke the Data Extractor synchronously; on Data Extractor success, advance state to `HANDLERS`
+- [ ] 7.3 On Pipeline Analyzer failure, mark the mission `FAILED` without invoking the Data Extractor
+
+## 8. Handler Orchestrator wiring
+
+- [ ] 8.1 Refuse to schedule handler Jobs unless the mission state is `HANDLERS`
+- [ ] 8.2 On all handlers reaching terminal state, advance to `COMPLETED`
+- [ ] 8.3 If any required precondition is missing (e.g., manifest absent), refuse to schedule and mark `FAILED`
+
+## 9. Pipeline Data SDK rewiring
+
+- [ ] 9.1 Replace handler-side reads (`get_pipeline_metadata`, `get_failed_stages`, `get_stage_log`, `list_artifacts`, `get_artifact`) with HDLF reads via the shared HDLF client
+- [ ] 9.2 Implement manifest-driven status: `captured` → return data; `truncated` → return data; `skipped_*` → raise `DataNotInSnapshot(reason)`; not-in-manifest → raise `DataNotInSnapshot(reason="not_in_capture_plan")`
+- [ ] 9.3 Use the active-then-preserved read order (D9)
+- [ ] 9.4 Remove handler-side fallback to live Jenkins
+- [ ] 9.5 Update SDK unit tests; add tests for the new exception class and read-order behavior
+
+## 10. Manual preservation script
+
+- [ ] 10.1 Implement `scripts/preserve_mission.py <mission_uuid>` using the HDLF client `copy_recursive`
+- [ ] 10.2 Idempotency: re-running the script for an already-preserved mission is a no-op success
+- [ ] 10.3 Error handling: unknown UUID exits non-zero with a clear message; partial copies are detectable on retry
+- [ ] 10.4 Document the script in the operations README
+
+## 11. Documentation updates
+
+- [ ] 11.1 Update `docs/design/FL_Architecture_Design.md`: add Metadata Extractor and Data Extractor to the high-level diagram and component table; revise §7 (Pipeline Data SDK) for HDLF-only reads; revise §15 (Data Management) for the per-mission HDLF folder model and two-container retention; add the mission-state field to the data model section
+- [ ] 11.2 Update `openspec/changes/fl-control-plane-rearchitecture/design.md`: revise D10 to delegate raw-pipeline-data lifecycle to this change; add a brief D14 (or update D9) describing Metadata Extractor and Data Extractor placement; note the SDK behavior change in D9
+- [ ] 11.3 Update `openspec/changes/fl-control-plane-rearchitecture/specs/data-lifecycle/spec.md`: keep HANA-related requirements; remove or revise the HANA→HDLF CronJob requirement (it does not apply to raw pipeline data captured by this change)
+- [ ] 11.4 Update `openspec/changes/fl-control-plane-rearchitecture/specs/pipeline-data-sdk/spec.md`: requirement that handlers do not call CI directly remains; reads now go to HDLF; new error semantics for missing data
+- [ ] 11.5 Update `openspec/changes/fl-control-plane-rearchitecture/specs/handler-orchestrator/spec.md`: handlers scheduled only after Data Extractor success
+- [ ] 11.6 Update `openspec/changes/fl-control-plane-rearchitecture/specs/pipeline-analyzer/spec.md`: triggers Data Extractor on success; advances mission state
+- [ ] 11.7 Update `openspec/changes/fl-control-plane-rearchitecture/specs/ingestion-api/spec.md`: generates mission UUID and writes `ACCEPTED` state row
+
+## 12. End-to-end validation
+
+- [ ] 12.1 Wire a synthetic Jenkins fixture (recorded responses) into a smoke test that drives Ingestion API → Metadata Extractor → Pipeline Analyzer → Data Extractor → handler scheduling
+- [ ] 12.2 Assert: per-mission folder exists in `fl-active` with metadata.json, manifest.json, and the expected captured items
+- [ ] 12.3 Assert: handler Jobs are scheduled exactly once, after the manifest is present
+- [ ] 12.4 Run a failure injection: HDLF unavailable mid-extraction → mission state ends in `FAILED`; manual retry resets state and resumes the extractor
+- [ ] 12.5 Run a failure injection: Pipeline Analyzer fails → no Data Extractor run, no handlers scheduled, state `FAILED`
+- [ ] 12.6 Run the preservation script in the test environment; assert the folder appears in `fl-preserved` and survives a forced retention sweep on `fl-active`
+
+## 13. Deferred items tracked for follow-up
+
+- [ ] 13.1 Add `state_since`, `attempt`, `last_error` columns to `missions` (before production traffic)
+- [ ] 13.2 Implement stuck-mission detection CronJob (after 13.1 lands)
+- [ ] 13.3 Admin UI: "preserve mission" button (when Admin UI is built)
+- [ ] 13.4 Admin UI: "retry failed mission" button (when Admin UI is built)
+- [ ] 13.5 Evaluate adding gzip per-file compression once volumes warrant it
+- [ ] 13.6 Evaluate moving the Data Extractor to a k8s Job once traffic or memory pressure warrants it
+- [ ] 13.7 GitHub Actions extractor adapter (when GHA support is required)
+- [ ] 13.8 Azure DevOps extractor adapter (when ADO support is required)
\ No newline at end of file
diff --git a/openspec/changes/fl-control-plane-rearchitecture/design.md b/openspec/changes/fl-control-plane-rearchitecture/design.md
index 12e3e0b7..413fbe95 100644
--- a/openspec/changes/fl-control-plane-rearchitecture/design.md
+++ b/openspec/changes/fl-control-plane-rearchitecture/design.md
@@ -106,11 +106,23 @@ The re-architecture makes FL a standalone Kyma/Kubernetes application with a dec
 
 **Rationale:** Without abstraction, every handler needs three CI-system implementations. The SDK centralizes and amortizes CI integration complexity. It also enforces the secret model (CI credentials are FL-managed, not handler-managed).
 
-### D10: HANA Cloud primary + HDLF archival, 14-day hot retention
+### D10: HANA Cloud primary; raw pipeline data lifecycle delegated
 
-**Decision:** Active analysis data lives in HANA Cloud. A scheduled CronJob moves records older than 14 days to HDLF. HDLF has a configurable retention (default: 1 year).
+**Decision:** Active analysis records (handler executions, findings, decision rationale, feedback) live in HANA Cloud. The lifecycle of the **raw pipeline data** that handlers analyze (logs, artifacts, test reports, build metadata) is delegated to the `data-to-hdlf` change, which captures it into per-mission HDLF folders with a 6-month auto-deletion `fl-active` container and a manual `fl-preserved` container for indefinite retention.
 
-**Rationale:** Bounds HANA Cloud database size without losing historical data for analytics and handler improvement.
+**Rationale:** HANA Cloud is the right place for structured analysis records that the MCP, Feedback UI, Admin UI, and alerting query directly. HDLF is the right place for the bulk pipeline data that handlers consume but rarely re-query after analysis. The earlier "14-day HANA → HDLF CronJob" model is superseded for raw pipeline data; analysis records still live in HANA but are not subject to that CronJob.
+
+### D11: Two new components in the request path — Metadata Extractor and Data Extractor
+
+**Decision:** Two new FL components are inserted in the per-mission request path: a Metadata Extractor between the Ingestion API and the Pipeline Analyzer (small, structured fields into `metadata.json`), and a Data Extractor between the Pipeline Analyzer and the Handler Orchestrator (full pipeline data, `manifest.json` written last). See the `data-to-hdlf` change for full requirements.
+
+**Rationale:** Separating "lightweight metadata before gates" from "bulk capture after gates pass" avoids paying full-extraction cost for missions the Pipeline Analyzer would reject, while still ensuring the Pipeline Analyzer has structured access to mission identifiers before it runs.
+
+### D12: Pipeline Data SDK reads exclusively from HDLF (no live-CI fallback)
+
+**Decision:** After the `data-to-hdlf` change lands, handlers (and the SDK in general) read pipeline data exclusively from HDLF. The SDK never falls back to live CI APIs for handler-side reads. The Data Extractor is the single source of truth for what's available to handlers, expressed via the manifest.
+
+**Rationale:** A single source of truth eliminates the dual-path complexity of "live or cached?" and gives handlers explicit error semantics (`DataNotInSnapshot(reason)`) when data is missing. CI APIs are touched by the extraction components only.
 
 ## Risks / Trade-offs
 

```
