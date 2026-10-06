# 6d335ddaa5c1edfc

PR: https://github.tools.sap/Lenny/pipeline-fl-control-plane/pull/55
Suggested label: 57%
File overlap: 1.0
Changed-line overlap: 0.3333

## Suggested diff
```diff
--- a/.github/workflows/build-and-deploy.yaml
+++ b/.github/workflows/build-and-deploy.yaml
@@
+NS="${{ steps.vars.outputs.namespace }}"
+          echo "### Undeployment complete for namespace: \`$NS\`" >> "$GITHUB_STEP_SUMMARY"
+          echo "Namespace '$NS' cleanup complete."
```

## Landed PR diff
```diff
diff --git a/.github/workflows/build-and-deploy.yaml b/.github/workflows/build-and-deploy.yaml
new file mode 100644
index 00000000..fc34f881
--- /dev/null
+++ b/.github/workflows/build-and-deploy.yaml
@@ -0,0 +1,346 @@
+name: Build and Deploy FL Control Plane To Namespace / Undeploy FL Control Plane from Namespace
+
+on:
+  workflow_dispatch:
+    inputs:
+      action:
+        description: "deploy or undeploy"
+        required: true
+        default: deploy
+        type: choice
+        options:
+          - deploy
+          - undeploy
+      branch:
+        description: "Branch to deploy (defaults to the triggering branch)"
+        required: false
+        default: ""
+      namespace:
+        description: "Target namespace (default: derived from branch name)"
+        required: false
+        default: ""
+      kubeconfig_b64:
+        description: "Base64-encoded kubeconfig (produced by gardenlogin on the developer's machine)"
+        required: true
+      image_tag:
+        description: "Image tag to use (default: short git SHA of branch tip)"
+        required: false
+        default: ""
+
+jobs:
+  deploy:
+    if: ${{ github.event.inputs.action == 'deploy' }}
+    runs-on: ubuntu-latest
+    # ubuntu-latest runners are x86_64 — no emulation needed for linux/amd64 images.
+    env:
+      REGISTRY_NODEPORT: "localhost:32137"
+      REGISTRY_LOCAL_PORT: "15000"
+      RELEASE: "pipeline-fl-control-plane"
+      CHART_DIR: "chart"
+
+    steps:
+      - name: Checkout branch
+        uses: actions/checkout@v4
+        with:
+          ref: ${{ github.event.inputs.branch != '' && github.event.inputs.branch || github.ref }}
+          fetch-depth: 1
+
+      # -----------------------------------------------------------------------
+      # Resolve runtime values: namespace, image tag, and registry credentials
+      # -----------------------------------------------------------------------
+      - name: Resolve namespace and image tag
+        id: vars
+        run: |
+          BRANCH="${{ github.event.inputs.branch }}"
+          if [[ -z "$BRANCH" ]]; then
+            BRANCH="${GITHUB_REF_NAME}"
+          fi
+
+          NS="${{ github.event.inputs.namespace }}"
+          if [[ -z "$NS" ]]; then
+            # Derive namespace: lowercase, replace non-alnum with -, trim to 53 chars
+            # (Kubernetes namespace max is 63 chars; leaving room for any suffix).
+            NS=$(echo "$BRANCH" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/-\+/-/g' | sed 's/^-//;s/-$//' | cut -c1-53)
+          fi
+
+          TAG="${{ github.event.inputs.image_tag }}"
+          if [[ -z "$TAG" ]]; then
+            TAG=$(git rev-parse --short HEAD)
+          fi
+
+          echo "namespace=$NS" >> "$GITHUB_OUTPUT"
+          echo "tag=$TAG" >> "$GITHUB_OUTPUT"
+          echo "Namespace : $NS"
+          echo "Image tag : $TAG"
+
+      - name: Write kubeconfig
+        run: |
+          mkdir -p "$HOME/.kube"
+          echo "${{ github.event.inputs.kubeconfig_b64 }}" | base64 -d > "$HOME/.kube/test-cluster.yaml"
+          chmod 600 "$HOME/.kube/test-cluster.yaml"
+          echo "KUBECONFIG=$HOME/.kube/test-cluster.yaml" >> "$GITHUB_ENV"
+
+      - name: Verify cluster connectivity
+        run: kubectl cluster-info
+
+      # -----------------------------------------------------------------------
+      # Build both images in parallel using Docker's --platform flag.
+      # The runner is x86_64 so no emulation is needed.
+      # -----------------------------------------------------------------------
+      - name: Set up Docker Buildx
+        uses: docker/setup-buildx-action@v3
+
+      - name: Build control-plane image
+        run: |
+          docker build \
+            --platform linux/amd64 \
+            --build-arg BUILDPLATFORM=linux/amd64 \
+            -t "pipeline-fl-control-plane:${{ steps.vars.outputs.tag }}" \
+            -f Dockerfile \
+            .
+
+      - name: Build engineering-agent image
+        run: |
+          docker build \
+            --platform linux/amd64 \
+            --build-arg BUILDPLATFORM=linux/amd64 \
+            -t "pipeline-fl-engineering-agent:${{ steps.vars.outputs.tag }}" \
+            -f engineering_agent/Dockerfile \
+            .
+
+      # -----------------------------------------------------------------------
+      # Port-forward the in-cluster registry and push both images in parallel.
+      # -----------------------------------------------------------------------
+      - name: Install kubectl / helm
+        uses: azure/setup-kubectl@v4
+        with:
+          version: "latest"
+
+      - name: Install helm
+        uses: azure/setup-helm@v4
+        with:
+          version: "latest"
+
+      - name: Port-forward in-cluster Docker registry
+        run: |
+          # Wait for the registry pod to be Ready before port-forwarding.
+          kubectl wait --for=condition=Ready pod \
+            -l app=docker-registry \
+            -n docker-registry \
+            --timeout=60s
+
+          REGISTRY_POD=$(kubectl get pod -n docker-registry -l app=docker-registry \
+            -o jsonpath='{.items[0].metadata.name}')
+          kubectl port-forward --address 127.0.0.1 \
+            -n docker-registry "pod/${REGISTRY_POD}" \
+            "${{ env.REGISTRY_LOCAL_PORT }}:5000" &
+          echo "PORT_FORWARD_PID=$!" >> "$GITHUB_ENV"
+
+          # Wait for the local port to accept connections.
+          for i in $(seq 1 30); do
+            if curl -sf "http://127.0.0.1:${{ env.REGISTRY_LOCAL_PORT }}/v2/" &>/dev/null; then
+              echo "Registry port-forward ready."
+              break
+            fi
+            if [[ $i -eq 30 ]]; then
+              echo "ERROR: Registry port-forward did not become ready after 30s." >&2
+              exit 1
+            fi
+            sleep 1
+          done
+
+      - name: Extract registry credentials and log in
+        run: |
+          REGISTRY_USER=$(kubectl get secret dockerregistry-config \
+            -n docker-registry \
+            -o jsonpath='{.data.\.dockerconfigjson}' \
+            | base64 -d \
+            | python3 -c "
+          import sys, json, base64
+          d = json.load(sys.stdin)
+          auth = list(d['auths'].values())[0]['auth']
+          user, pw = base64.b64decode(auth).decode().split(':', 1)
+          print(user)
+          ")
+          REGISTRY_PASS=$(kubectl get secret dockerregistry-config \
+            -n docker-registry \
+            -o jsonpath='{.data.\.dockerconfigjson}' \
+            | base64 -d \
+            | python3 -c "
+          import sys, json, base64
+          d = json.load(sys.stdin)
+          auth = list(d['auths'].values())[0]['auth']
+          user, pw = base64.b64decode(auth).decode().split(':', 1)
+          print(pw)
+          ")
+          echo "${REGISTRY_PASS}" | docker login \
+            "127.0.0.1:${{ env.REGISTRY_LOCAL_PORT }}" \
+            --username "${REGISTRY_USER}" \
+            --password-stdin
+
+      - name: Push images in parallel
+        run: |
+          TAG="${{ steps.vars.outputs.tag }}"
+
+          # Tag both images for the local registry.
+          docker tag "pipeline-fl-control-plane:${TAG}" \
+            "127.0.0.1:${{ env.REGISTRY_LOCAL_PORT }}/pipeline-fl-control-plane:${TAG}"
+          docker tag "pipeline-fl-engineering-agent:${TAG}" \
+            "127.0.0.1:${{ env.REGISTRY_LOCAL_PORT }}/pipeline-fl-engineering-agent:${TAG}"
+
+          # Push both in parallel; wait for both before proceeding.
+          docker push "127.0.0.1:${{ env.REGISTRY_LOCAL_PORT }}/pipeline-fl-control-plane:${TAG}" &
+          PID1=$!
+
+          docker push "127.0.0.1:${{ env.REGISTRY_LOCAL_PORT }}/pipeline-fl-engineering-agent:${TAG}" &
+          PID2=$!
+
+          wait "$PID1" || { echo "ERROR: control-plane push failed"; exit 1; }
+          wait "$PID2" || { echo "ERROR: engineering-agent push failed"; exit 1; }
+
+          echo "Both images pushed successfully."
+
+      - name: Stop port-forward
+        if: always()
+        run: kill "${PORT_FORWARD_PID}" 2>/dev/null || true
+
+      # -----------------------------------------------------------------------
+      # Ensure namespace exists with required labels, then deploy the chart.
+      # -----------------------------------------------------------------------
+      - name: Ensure namespace
+        run: |
+          NS="${{ steps.vars.outputs.namespace }}"
+          if ! kubectl get namespace "$NS" &>/dev/null; then
+            kubectl create namespace "$NS"
+            kubectl label namespace "$NS" \
+              app.kubernetes.io/managed-by=Helm \
+              istio-injection=enabled
+            kubectl annotate namespace "$NS" \
+              "meta.helm.sh/release-name=${{ env.RELEASE }}" \
+              "meta.helm.sh/release-namespace=$NS"
+            echo "Namespace '$NS' created."
+          else
+            echo "Namespace '$NS' already exists — will upgrade the release."
+          fi
+
+      - name: Copy image pull secret into namespace
+        run: |
+          NS="${{ steps.vars.outputs.namespace }}"
+          kubectl get secret dockerregistry-config \
+            -n docker-registry \
+            -o json \
+          | python3 -c "
+          import sys, json
+          s = json.load(sys.stdin)
+          s['metadata'] = {'name': s['metadata']['name'], 'namespace': '$NS'}
+          print(json.dumps(s))
+          " | kubectl apply -f -
+
+      - name: Apply CRDs (idempotent)
+        run: |
+          for f in chart/crds/*.yaml; do
+            [[ -f "$f" ]] && kubectl apply -f "$f"
+          done
+
+      - name: Deploy via Helm
+        run: |
+          NS="${{ steps.vars.outputs.namespace }}"
+          TAG="${{ steps.vars.outputs.tag }}"
+
+          helm upgrade --install "${{ env.RELEASE }}" "${{ env.CHART_DIR }}" \
+            --dependency-update \
+            --namespace "$NS" \
+            --skip-crds \
+            --timeout 300s \
+            --wait \
+            --wait-for-jobs \
+            --set "image.pipeline_fl_control_plane.repository=${{ env.REGISTRY_NODEPORT }}/pipeline-fl-control-plane" \
+            --set "image.pipeline_fl_control_plane.tag=${TAG}" \
+            --set "image.pipeline_fl_control_plane_engineering_agent.repository=${{ env.REGISTRY_NODEPORT }}/pipeline-fl-engineering-agent" \
+            --set "image.pipeline_fl_control_plane_engineering_agent.tag=${TAG}" \
+            --set "secret.enabled=false" \
+            --set "imagePullSecret.name=dockerregistry-config" \
+            --set "hanaDb.enabled=true"
+
+      - name: Print deployment summary
+        run: |
+          NS="${{ steps.vars.outputs.namespace }}"
+          TAG="${{ steps.vars.outputs.tag }}"
+          echo ""
+          echo "============================================================"
+          echo "  Deployment successful"
+          echo "============================================================"
+          echo "  Namespace : $NS"
+          echo "  Release   : ${{ env.RELEASE }}"
+          echo "  Tag       : $TAG"
+          echo ""
+          echo "  Useful commands (run locally):"
+          echo "    # App API"
+          echo "    kubectl --kubeconfig=<kubeconfig> port-forward -n $NS svc/${{ env.RELEASE }} 8000:8000"
+          echo "    # Temporal UI"
+          echo "    kubectl --kubeconfig=<kubeconfig> port-forward -n $NS svc/${{ env.RELEASE }}-temporal-web 8080:8080"
+          echo "============================================================"
+          echo ""
+          echo "### Deployed to namespace: \`$NS\`" >> "$GITHUB_STEP_SUMMARY"
+
+  undeploy:
+    if: ${{ github.event.inputs.action == 'undeploy' }}
+    runs-on: ubuntu-latest
+    env:
+      RELEASE: "pipeline-fl-control-plane"
+
+    steps:
+      - name: Write kubeconfig
+        run: |
+          mkdir -p "$HOME/.kube"
+          echo "${{ github.event.inputs.kubeconfig_b64 }}" | base64 -d > "$HOME/.kube/test-cluster.yaml"
+          chmod 600 "$HOME/.kube/test-cluster.yaml"
+          echo "KUBECONFIG=$HOME/.kube/test-cluster.yaml" >> "$GITHUB_ENV"
+
+      - name: Install kubectl / helm
+        uses: azure/setup-kubectl@v4
+        with:
+          version: "latest"
+
+      - name: Install helm
+        uses: azure/setup-helm@v4
+        with:
+          version: "latest"
+
+      - name: Resolve namespace
+        id: vars
+        run: |
+          NS="${{ github.event.inputs.namespace }}"
+          if [[ -z "$NS" ]]; then
+            BRANCH="${{ github.event.inputs.branch }}"
+            if [[ -z "$BRANCH" ]]; then
+              BRANCH="${GITHUB_REF_NAME}"
+            fi
+            NS=$(echo "$BRANCH" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/-\+/-/g' | sed 's/^-//;s/-$//' | cut -c1-53)
+          fi
+          echo "namespace=$NS" >> "$GITHUB_OUTPUT"
+          echo "Namespace : $NS"
+
+      - name: Uninstall Helm release
+        run: |
+          NS="${{ steps.vars.outputs.namespace }}"
+          if helm status "${{ env.RELEASE }}" -n "$NS" &>/dev/null; then
+            helm uninstall "${{ env.RELEASE }}" -n "$NS"
+            echo "Release uninstalled."
+          else
+            echo "Release not found in namespace '$NS' — skipping uninstall."
+          fi
+
+      - name: Delete namespace
+        run: |
+          NS="${{ steps.vars.outputs.namespace }}"
+          if kubectl get namespace "$NS" &>/dev/null; then
+            kubectl delete namespace "$NS" --timeout=120s
+            echo "Namespace '$NS' deleted."
+          else
+            echo "Namespace '$NS' not found — nothing to delete."
+          fi
+
+      - name: Summary
+        run: |
+          echo "Namespace '${{ steps.vars.outputs.namespace }}' has been removed."

```
