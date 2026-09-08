# a0a7b69ab1eb64ab

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/16
Suggested label: 100%
File overlap: 1.0
Changed-line overlap: 1.0

## Suggested diff
```diff
--- a/openspec/changes/cluster-automation/specs/cluster-bootstrap/spec.md
+++ b/openspec/changes/cluster-automation/specs/cluster-bootstrap/spec.md
@@
+#### Scenario: Bootstrap is idempotent
+- **WHEN** `bootstrap.sh` is run against a cluster that already exists and has ArgoCD installed
+- **THEN** the script completes without error, makes no destructive changes, and the root Application CR exists pointing at the correct `cluster-config/<env>/` path
```

## Landed PR diff
```diff
diff --git a/openspec/changes/cluster-automation/.openspec.yaml b/openspec/changes/cluster-automation/.openspec.yaml
new file mode 100644
index 00000000..af43829c
--- /dev/null
+++ b/openspec/changes/cluster-automation/.openspec.yaml
@@ -0,0 +1,2 @@
+schema: spec-driven
+created: 2026-05-21
diff --git a/openspec/changes/cluster-automation/design.md b/openspec/changes/cluster-automation/design.md
new file mode 100644
index 00000000..a259f94d
--- /dev/null
+++ b/openspec/changes/cluster-automation/design.md
@@ -0,0 +1,95 @@
+## Context
+
+FL runs on Gardener-provisioned Kyma clusters in the SAP internal network (SAP Converged Cloud, OpenStack). One cluster has been created and configured manually: the Shoot CR was created via the Gardener dashboard, five Kyma module operators were installed individually via `kubectl apply` following the kyma-project.io quick install guide, and BTP Cloud Logging integration was configured by hand.
+
+The goal is to make this repeatable — both for the core team standing up dev/test/prod clusters and for contributors who want an identical cluster for testing.
+
+Kyma Lifecycle Manager is not available for self-managed Gardener clusters (it is BTP-only infrastructure). Each module must be managed independently.
+
+## Goals / Non-Goals
+
+**Goals:**
+- Automate Gardener Shoot creation through a script
+- Declare all cluster configuration (Kyma modules, BTP integrations) in Git
+- Use ArgoCD for continuous reconciliation of cluster state
+- Support per-environment module version overrides (e.g. test a new istio version on dev only)
+- Enable contributors to provision an identical cluster with minimal steps
+
+**Non-Goals:**
+- Automating the `sap-btp-manager` secret seeding (contains Service Manager credentials — must remain outside Git)
+- Managing application deployments (handled separately by the app Helm chart)
+- Multi-region or multi-cloud support
+- Kyma Lifecycle Manager adoption (not available for this setup)
+
+## Decisions
+
+### Decision 1: ArgoCD manages cluster config, bootstrap script handles the rest
+
+**Choice:** Split responsibility between a one-time `bootstrap.sh` and ArgoCD continuous reconciliation.
+
+Bootstrap script does:
+1. `kubectl apply` Shoot CR → wait for cluster ready
+2. Get kubeconfig via gardenctl
+3. Seed `sap-btp-manager` secret (manual input or CI secret)
+4. `helm upgrade --install argocd argo/argo-cd --namespace argocd --create-namespace --version <pinned>`
+5. `kubectl apply` root ArgoCD Application CR
+
+ArgoCD does everything after that: Kyma modules, BTP integrations, future additions.
+
+**Why not script everything?** Scripts are not idempotent by default and don't detect drift. ArgoCD continuously reconciles — if someone accidentally deletes the LogPipeline, it comes back automatically.
+
+**Why not ArgoCD for bootstrap too?** ArgoCD needs a cluster to run on. The chicken-and-egg problem is solved by the bootstrap script installing ArgoCD itself.
+
+### Decision 2: Kyma module operators referenced by URL in kustomization.yaml, not downloaded
+
+**Choice:** `kustomization.yaml` references pinned GitHub release URLs directly:
+```
+https://github.com/kyma-project/istio/releases/download/v1.2.3/istio-manager.yaml
+```
+
+**Why not download and commit?** These are large upstream manifests (~500-2000 lines each) that we don't modify. Committing them creates noise in PRs and no added value — we never hand-edit them.
+
+**Why not `releases/latest`?** Unpredictable. A new upstream release would automatically apply to all clusters on next ArgoCD sync without a PR.
+
+**Trade-off:** Network dependency at ArgoCD sync time. GitHub release assets are stable (immutable once published) and highly available — acceptable risk for this scale.
+
+**Version upgrade workflow:** Edit the URL version in `dev/kustomization.yaml`, open PR, merge → ArgoCD applies to dev cluster. When stable, promote to `base/kustomization.yaml`.
+
+### Decision 3: Own CRs (CLS integration) committed to Git
+
+**Choice:** `cls-instance.yaml`, `cls-binding.yaml`, `log-pipeline.yaml` are committed as files, not referenced by URL.
+
+**Why:** These are our own configuration, not upstream releases. They change infrequently but when they do, we want the full diff visible in the PR. They are not sensitive (the ServiceBinding creates a secret as output — no secrets in the files themselves).
+
+### Decision 4: Kustomize base/overlay for per-environment differences
+
+```
+cluster-config/
+├── base/
+│   ├── kustomization.yaml        ← module URLs at stable versions
+│   ├── cls-instance.yaml
+│   ├── cls-binding.yaml
+│   └── log-pipeline.yaml
+├── dev/
+│   └── kustomization.yaml        ← extends base, can override module URLs
+└── prod/
+    └── kustomization.yaml        ← extends base
+```
+
+For a dev-only module version bump: the dev `kustomization.yaml` replaces the base URL for that module with the new version URL. When promoted, base is updated and the dev override removed.
+
+### Decision 5: Same repo (cluster-config/ folder in this repo)
+
+**Why not separate repo?** 2-3 clusters, small team. One repo, one place to look, contributors clone one thing. Can extract later if separation becomes painful.
+
+## Risks / Trade-offs
+
+- **Network dependency at sync time** → GitHub release assets are immutable once published and highly available. Acceptable at this scale.
+- **sap-btp-manager secret is manual** → Must be documented clearly in bootstrap runbook. Without it, or if incorrect credentials are provided, ServiceInstance never reconciles and CLS integration is silently broken. Runbook must include a verification step (e.g. check BTP operator pod logs and ServiceInstance status after seeding).
+- **ArgoCD sync waves needed for ordering** → BTP operator must be ready before ServiceInstance is applied; telemetry must be ready before LogPipeline. ArgoCD sync wave annotations handle this.
+- **Module operator upgrades require PR** → This is intentional — upgrades are deliberate, not automatic. Acceptable operational overhead for 5 modules.
+
+## Open Questions
+
+- What is the garden cluster kubeconfig/endpoint for non-interactive gardenctl use in bootstrap? (needed before bootstrap script can be implemented)
+- Should prod use a dedicated CLS instance or continue sharing dev's reference instance? (referenced GUID `cc3b5fc4-483f-435a-a5b2-1b3a96c24d4c` is currently dev-only)
diff --git a/openspec/changes/cluster-automation/proposal.md b/openspec/changes/cluster-automation/proposal.md
new file mode 100644
index 00000000..7991f38d
--- /dev/null
+++ b/openspec/changes/cluster-automation/proposal.md
@@ -0,0 +1,31 @@
+## Why
+
+Standing up a new Kyma cluster for FL currently requires a series of manual steps — creating the Shoot via the Gardener dashboard, installing five Kyma module operators one by one, configuring BTP Cloud Logging integration, and waiting for each step to complete. This is error-prone, undocumented, and impossible to reproduce consistently, especially for contributors who want to provision their own test clusters.
+
+## What Changes
+
+- A `cluster-config/` folder is added to this repo containing all declarative cluster configuration
+- A `bootstrap.sh` script automates Shoot creation, kubeconfig retrieval, ArgoCD installation, and initial cluster wiring
+- Kyma module operators (istio, api-gateway, sap-btp-operator, telemetry, docker-registry) are declared via Kustomize `kustomization.yaml` files referencing pinned GitHub release URLs — no files downloaded
+- BTP Cloud Logging integration (ServiceInstance, ServiceBinding, LogPipeline) is declared as committed YAML files managed by ArgoCD
+- Module versions are controlled per environment via `kustomization.yaml` — changing a URL in dev and merging triggers ArgoCD to apply the new version on the dev cluster only
+- ArgoCD is installed as part of bootstrap and continuously reconciles all cluster config from Git
+
+## Capabilities
+
+### New Capabilities
+
+- `cluster-bootstrap`: One-script automation of Gardener Shoot creation through ArgoCD installation and initial wiring
+- `cluster-gitops-config`: ArgoCD-managed cluster configuration covering Kyma modules and BTP integrations, with per-environment version control via Kustomize
+
+### Modified Capabilities
+
+None.
+
+## Impact
+
+- New top-level `cluster-config/` directory in this repo
+- `bootstrap.sh` depends on: `kubectl`, `helm`, `gardenctl`, access to the garden cluster kubeconfig
+- One manual step remains outside Git: seeding the `sap-btp-manager` secret in `kyma-system` (BTP Service Manager credentials) — required before BTP operator can provision ServiceInstances
+- Shared dev CLS instance referenced by GUID (`cc3b5fc4-483f-435a-a5b2-1b3a96c24d4c`) — prod will use a separate instance
+- No changes to the application Helm chart or existing source code
diff --git a/openspec/changes/cluster-automation/specs/cluster-bootstrap/spec.md b/openspec/changes/cluster-automation/specs/cluster-bootstrap/spec.md
new file mode 100644
index 00000000..c10a6fb0
--- /dev/null
+++ b/openspec/changes/cluster-automation/specs/cluster-bootstrap/spec.md
@@ -0,0 +1,38 @@
+## ADDED Requirements
+
+### Requirement: Bootstrap script creates a fully wired cluster from zero
+The `bootstrap.sh` script SHALL provision a new Gardener Shoot and leave it with ArgoCD installed and watching the cluster-config Git directory, requiring no further manual steps except seeding the `sap-btp-manager` secret.
+
+#### Scenario: Successful bootstrap of a new dev cluster
+- **WHEN** a user runs `./cluster-config/bootstrap/bootstrap.sh fl-dev dev` with valid garden cluster credentials
+- **THEN** a new Shoot named `fl-dev` is created in `garden-pipelinefl`, ArgoCD is installed at the pinned version, and the root ArgoCD Application CR is applied pointing at `cluster-config/dev/`
+
+#### Scenario: Bootstrap is idempotent
+- **WHEN** `bootstrap.sh` is run against a cluster that already exists and has ArgoCD installed
+- **THEN** the script completes without error, makes no destructive changes, and the root Application CR exists pointing at the correct `cluster-config/<env>/` path
+
+### Requirement: Bootstrap script accepts environment as a parameter
+The script SHALL accept a cluster name and environment (`dev`, `test`, `prod`) and apply the correct ArgoCD root Application CR for that environment.
+
+#### Scenario: Environment determines ArgoCD root app
+- **WHEN** `bootstrap.sh` is run with environment `prod`
+- **THEN** ArgoCD is pointed at `cluster-config/prod/` kustomization
+
+### Requirement: Shoot CR is parameterized from a template
+The bootstrap script SHALL derive the Shoot CR from a committed template, substituting only cluster name, purpose, and hibernation schedule — all other fields are fixed.
+
+#### Scenario: Dev cluster gets hibernation schedule
+- **WHEN** bootstrap creates a dev/test cluster
+- **THEN** the Shoot CR includes a weekday hibernation schedule (18:30 Europe/Sofia)
+
+#### Scenario: Prod cluster has no hibernation
+- **WHEN** bootstrap creates a prod cluster
+- **THEN** the Shoot CR has no hibernation schedule and purpose is set to `production`
+
+### Requirement: Bootstrap documents the manual secret step
+The bootstrap script SHALL print a clear, actionable message instructing the operator to apply the `sap-btp-manager` secret before proceeding.
+
+#### Scenario: Operator is informed of manual step
+- **WHEN** the cluster is ready and kubeconfig is obtained
+- **THEN** the script prints instructions for seeding the `sap-btp-manager` secret in `kyma-system` and waits for confirmation before continuing
+- **AND** ArgoCD installation and root Application CR apply occur only after the operator confirms
diff --git a/openspec/changes/cluster-automation/specs/cluster-gitops-config/spec.md b/openspec/changes/cluster-automation/specs/cluster-gitops-config/spec.md
new file mode 100644
index 00000000..e1bf713a
--- /dev/null
+++ b/openspec/changes/cluster-automation/specs/cluster-gitops-config/spec.md
@@ -0,0 +1,42 @@
+## ADDED Requirements
+
+### Requirement: Kyma module operators are declared at pinned versions per environment
+The `kustomization.yaml` for each environment SHALL reference Kyma module operator manifests via pinned GitHub release URLs. Changing the URL version in Git and merging SHALL trigger ArgoCD to apply the new version on the target cluster.
+
+#### Scenario: Dev-only module version upgrade
+- **WHEN** a PR updates the istio URL in `cluster-config/dev/kustomization.yaml` from `v1.2.3` to `v1.2.4` and is merged
+- **THEN** ArgoCD on the dev cluster applies the new istio-manager manifest within the next sync cycle
+- **AND** the prod cluster continues running `v1.2.3`
+
+#### Scenario: Promoting a module version to all clusters
+- **WHEN** the base `kustomization.yaml` URL is updated to `v1.2.4` and the dev override is removed
+- **THEN** all clusters converge to `v1.2.4` on their next ArgoCD sync
+
+### Requirement: BTP Cloud Logging integration is fully declarative
+The ServiceInstance, ServiceBinding, and LogPipeline CRs SHALL be committed to Git and managed by ArgoCD. No manual `kubectl apply` SHALL be required after bootstrap.
+
+#### Scenario: CLS integration reconciles automatically
+- **WHEN** the LogPipeline CR is accidentally deleted from the cluster
+- **THEN** ArgoCD re-creates it within the next sync cycle without human intervention
+
+#### Scenario: Dev clusters use shared CLS reference instance
+- **WHEN** ArgoCD applies `cls-instance.yaml` on a dev or test cluster
+- **THEN** the ServiceInstance references the shared CLS instance by GUID (`cc3b5fc4-483f-435a-a5b2-1b3a96c24d4c`) via `servicePlanName: reference-instance`
+
+### Requirement: ArgoCD sync waves enforce module ordering
+ArgoCD sync wave annotations SHALL ensure Kyma module operators are ready before dependent resources are applied.
+
+#### Scenario: BTP operator ready before ServiceInstance
+- **WHEN** ArgoCD syncs a freshly bootstrapped cluster
+- **THEN** the sap-btp-operator deployment reaches ready state before the ServiceInstance CR is applied
+
+#### Scenario: Telemetry ready before LogPipeline
+- **WHEN** ArgoCD syncs a freshly bootstrapped cluster
+- **THEN** the telemetry-manager deployment reaches ready state before the LogPipeline CR is applied
+
+### Requirement: Cluster configuration lives in this repository
+All cluster configuration SHALL reside under `cluster-config/` in this repository. No separate repository is required for cluster config.
+
+#### Scenario: Contributor can find all cluster config in one place
+- **WHEN** a contributor clones this repository
+- **THEN** all files needed to provision and configure a cluster are present under `cluster-config/`
diff --git a/openspec/changes/cluster-automation/tasks.md b/openspec/changes/cluster-automation/tasks.md
new file mode 100644
index 00000000..425aa586
--- /dev/null
+++ b/openspec/changes/cluster-automation/tasks.md
@@ -0,0 +1,35 @@
+## 1. Repository Structure
+
+- [ ] 1.1 Create `cluster-config/` directory structure: `base/`, `dev/`, `prod/`, `bootstrap/`
+- [ ] 1.2 Add `cluster-config/base/kustomization.yaml` referencing the five Kyma module operator URLs at current pinned versions
+- [ ] 1.3 Add `cluster-config/dev/kustomization.yaml` extending base (initially identical, ready for version overrides)
+- [ ] 1.4 Add `cluster-config/prod/kustomization.yaml` extending base
+
+## 2. BTP Cloud Logging Integration
+
+- [ ] 2.1 Add `cluster-config/base/cls-instance.yaml` (ServiceInstance, `reference-instance` plan, shared CLS GUID)
+- [ ] 2.2 Add `cluster-config/base/cls-binding.yaml` (ServiceBinding with credentials rotation policy)
+- [ ] 2.3 Add `cluster-config/base/log-pipeline.yaml` (LogPipeline referencing the binding secret)
+- [ ] 2.4 Add ArgoCD sync wave annotations (wave 0) to Kyma module operator resources in `base/kustomization.yaml`
+- [ ] 2.5 Add ArgoCD sync wave annotations (wave 1) to CLS and LogPipeline resources to enforce ordering after module operators are ready
+
+## 3. ArgoCD Setup
+
+- [ ] 3.1 Add `cluster-config/bootstrap/root-app-dev.yaml` — ArgoCD Application CR pointing at `cluster-config/dev/`
+- [ ] 3.2 Add `cluster-config/bootstrap/root-app-prod.yaml` — ArgoCD Application CR pointing at `cluster-config/prod/`
+- [ ] 3.3 Pin the ArgoCD Helm chart version in bootstrap script
+
+## 4. Bootstrap Script
+
+- [ ] 4.1 Add `cluster-config/bootstrap/shoot-template.yaml` derived from the existing Shoot export, parameterized for name, purpose, and hibernation schedule
+- [ ] 4.2 Write `cluster-config/bootstrap/bootstrap.sh` covering: Shoot creation, poll until ready, gardenctl kubeconfig retrieval, operator-secret prompt, ArgoCD helm install, root app apply
+- [ ] 4.3 Make bootstrap script idempotent (safe to re-run against an existing cluster)
+- [ ] 4.4 Add operator-secret step: script prints instructions and waits for confirmation before continuing
+
+## 5. Verify End-to-End
+
+- [ ] 5.1 Run bootstrap against a new cluster name in dev to verify full flow
+- [ ] 5.2 Confirm ArgoCD syncs all Kyma modules and reaches healthy state
+- [ ] 5.3 Confirm ServiceInstance and ServiceBinding reconcile (BTP operator creates the CLS secret)
+- [ ] 5.4 Confirm LogPipeline reaches running state and logs appear in CLS
+- [ ] 5.5 Test a dev-only module version override: bump one module URL in `dev/kustomization.yaml`, verify ArgoCD applies it only to dev

```
