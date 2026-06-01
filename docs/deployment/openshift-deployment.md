# Deploying NVIDIA Multi-Agent Intelligent Warehouse on Red Hat OpenShift AI

## What We're Deploying

The Multi-Agent Intelligent Warehouse (WOSA) Blueprint is an AI-powered operations
assistant that combines multi-agent orchestration (LangGraph) with NVIDIA NIM inference
services to deliver intelligent warehouse management — operations, safety, equipment
tracking, demand forecasting, and document processing.

| Component | Image | GPU | Purpose |
|-----------|-------|-----|---------|
| **nim-llm** (NIM Operator) | `nvcr.io/nim/nvidia/llama-3.3-nemotron-super-49b-v1.5` | 2 | LLM inference via NIMService |
| **nim-embedding** (NIM Operator) | `nvcr.io/nim/nvidia/llama-nemotron-embed-vl-1b-v2` | 1 | Vector embedding via NIMService |
| **wosa-backend** | Internal or external registry | 0 | FastAPI multi-agent orchestration API |
| **wosa-frontend** | Internal or external registry | 0 | React web UI |
| **wosa-nginx** | `nginxinc/nginx-unprivileged:1.25-alpine` | 0 | Reverse proxy (Route entry point) |
| **wosa-timescaledb** | `timescale/timescaledb:2.15.2-pg16` | 0 | Time-series relational database |
| **wosa-redis** | `redis:7` | 0 | Caching and session storage |
| **wosa-milvus** | `milvusdb/milvus:v2.4.3` | 0 (optional 1) | Vector database for RAG |
| **wosa-etcd** | `quay.io/coreos/etcd:v3.5.9` | 0 | Milvus metadata store |
| **wosa-minio** | `minio/minio` | 0 | Milvus object storage |
| **wosa-kafka** | `apache/kafka:3.7.0` | 0 | Event streaming (KRaft) |

**Total:** 3 GPUs minimum (2 LLM + 1 embedding). Optional 4th GPU if `milvus.gpu.enabled=true`.

### NIM Operator Components

When deployed with the NIM Operator (recommended on OpenShift), each NIM inference
service is managed as a pair of custom resources:

- **NIMCache** — downloads and caches the model on a PVC. Annotated with
  `helm.sh/resource-policy: keep` to survive upgrades and uninstalls.
- **NIMService** — runs the inference server, references its NIMCache for model storage,
  manages replicas, GPU allocation, and health probes.

## Tested Hardware

| Parameter | Value |
|-----------|-------|
| Platform | Red Hat OpenShift AI (RHOAI) 4.14+ |
| GPU nodes | 1+ nodes with NVIDIA A100 80GB / H100 |
| GPUs per node | 1+ |
| Total GPUs | 3 (2 nim-llm + 1 nim-embedding); 4 if Milvus GPU enabled |
| VRAM | 80 GB+ per GPU (LLM requires 2× A100 80GB or H100) |
| CPU | 10+ cores across worker nodes |
| RAM | 32 GB+ |
| Storage | 638 GiB dynamically provisioned PVCs (500 GiB LLM + 100 GiB embedding) + 38 GiB for infrastructure PVCs |
| API keys | [NGC API key](https://org.ngc.nvidia.com/setup/api-keys) |

Minimum for reproduction: 3 × NVIDIA A100 80GB / H100 GPUs, 638 GiB storage. Add 1 GPU if `milvus.gpu.enabled=true`.

> **Important — always filter NIMCache downloads.** The `values-openshift.yaml` defaults
> to `precision=fp8`, `tensorParallelism=2` which fits L40S (48 GB), A100-80GB, and H100.
> Without filtering, the NIMCache downloads all 24 model profiles (~2.4 TB). These large
> sustained downloads frequently fail with network timeouts to NGC, causing the download
> pod to restart from scratch — in practice, unfiltered downloads may **never complete**.
> With filtering, only the matching profile is downloaded (~200 GB, ~10 minutes).
>
> Override for other GPUs:
> - A100-80GB / H100 (max accuracy): `--set nimOperator.llm.model.precision=bf16`
> - A100-40GB: `--set nimOperator.llm.model.precision=nvfp4`
>
> When overriding precision, wait for the NIMCache to become Ready, then pin the profile:
> ```bash
> oc get nimcache nim-llm-cache -n $NAMESPACE -o jsonpath='{.status.profiles[0].name}'
> ```
> Pass the result via `helm upgrade --set nimOperator.llm.model.profile=<hash>`.

## What's Different from Upstream

| Area | Upstream Default | OpenShift Deployment | Impact |
|------|------------------|----------------------|--------|
| NIM inference (LLM + embedding) | NVIDIA cloud API (`integrate.api.nvidia.com`) | NIM Operator (NIMCache + NIMService) | Self-hosted, air-gappable |
| External access | `kubectl port-forward` | OpenShift Route with TLS | Production-grade ingress |
| Security context | Default UIDs | Custom SCC + RoleBinding | Compatible with OpenShift SCC |
| Secrets | Manual `.env` file | Helm-managed via `--set` | Single `helm install` creates all secrets |
| Container images | Docker Compose bind mounts | OpenShift-compatible Dockerfiles | Non-root, no bind mounts |

> **Using the cloud API instead of NIM Operator:** Set `nimOperator.llm.enabled: false`
> and `nimOperator.embedding.enabled: false` in your values overlay. The backend will use
> the hosted NVIDIA endpoints (`integrate.api.nvidia.com/v1`) and no GPU nodes are
> required. Only the `NVIDIA_API_KEY` secret is needed.

## Deployment Files

All OpenShift customizations are in the `deploy/` folder. The upstream codebase is modified only where strictly necessary (env var fallbacks for DB connections and file paths).

- **`Dockerfile.backend-openshift`**, **`Dockerfile.frontend-openshift`** — OpenShift-compatible container images (non-root, no bind mounts).
- **`deploy/helm/wosa/`** — Full Helm chart: deployment templates for all services, hook jobs, monitoring, network policies, secrets, PVCs, OpenShift Route and SCC, NIMCache + NIMService templates for LLM and embedding (gated by `apps.nvidia.com/v1alpha1`), and conditional NIM URL resolution in the backend.
- **Source code changes** — Env var fallbacks (`PGHOST`, `PGPORT`, `REDIS_HOST`, `FORECAST_OUTPUT_DIR`) in 6 Python files, and configurable agent/graph/chat timeouts (`AGENT_TIMEOUT_SIMPLE`, `GRAPH_TIMEOUT_COMPLEX`, etc.) in 2 Python files. All changes preserve original defaults.

## Prerequisites

### CLI Tools

- `oc` (OpenShift CLI) logged into your cluster
- `helm` v3.12+
- `podman` (for building and pushing images to an external registry)

### Cluster Requirements

- Red Hat OpenShift 4.14+
- NVIDIA GPU Operator installed and configured
- NIM Operator installed (provides `apps.nvidia.com/v1alpha1` API)
- At least 3 GPUs available (can be on 1+ nodes)

### Verify GPU Availability

```bash
oc get nodes -l nvidia.com/gpu.present=true
oc describe node <gpu-node> | grep -A 5 "Allocatable"
```

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NGC_API_KEY` | Yes | — | NGC API key for image pulls, model downloads, and cloud NIM services |

### OpenShift Block (`openshift:`)

| Key | Default | Description |
|-----|---------|-------------|
| `openshift.enabled` | `false` | Master toggle for all OpenShift resources |
| `openshift.route.enabled` | `false` | Create an OpenShift Route for the UI |
| `openshift.route.host` | `""` | Hostname (auto-generated if empty) |
| `openshift.route.tls.termination` | `edge` | TLS termination strategy |
| `openshift.scc.create` | `false` | Create custom SCC + RoleBinding |
| `openshift.scc.priority` | `10` | SCC priority |
| `openshift.imageRegistryPull` | `false` | Grant SA permission to pull from internal registry |
| `openshift.ngcSecret.name` | `ngc-secret` | Name of the image pull secret |
| `openshift.ngcSecret.apiName` | `ngc-api` | Name of the NGC API secret |
| `openshift.ngcSecret.registry` | `nvcr.io` | Container registry for NGC images |
| `openshift.ngcSecret.username` | `$oauthtoken` | Registry username |
| `openshift.ngcSecret.password` | `""` | NGC API key (set at install time) |

### NIM Operator Block (`nimOperator:`)

Each NIM (`llm`, `embedding`) shares a common schema. The `model.*` keys apply to the LLM NIM only.

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `false` | Deploy this NIM via NIM Operator |
| `replicas` | `1` | Number of inference replicas |
| `service.name` | (per NIM) | Kubernetes service name (used for DNS) |
| `image.repository` | (per NIM) | NGC container image |
| `image.tag` | (per NIM) | Image version |
| `model.precision` | `"fp8"` | Filter NIMCache downloads by precision — LLM only (`bf16`, `fp8`, `nvfp4`) |
| `model.tensorParallelism` | `"2"` | Filter NIMCache downloads by tensor parallelism — LLM only (e.g. `2`, `4`) |
| `model.profile` | `""` | Pin NIMService to a specific cached profile hash — LLM only |
| `resources.limits.nvidia.com/gpu` | `2` (LLM) / `1` (embedding) | GPU allocation |
| `storage.pvc.size` | `500Gi` (LLM) / `100Gi` (embedding) | Model cache PVC size |
| `storage.pvc.storageClass` | `""` | StorageClass (uses cluster default if empty) |
| `expose.service.port` | `8000` | Service port |
| `tolerations` | `[]` | Node tolerations for GPU taints |
| `env` | (per NIM) | Environment variables |
| `startupProbe` | (per NIM) | Startup probe configuration |

## Deployment

### 1. Create Namespace

```bash
export NGC_API_KEY="<your-ngc-api-key>"
export NAMESPACE=wosa

oc new-project $NAMESPACE
```

### 2. Build Application Images

You have two options: use the internal OpenShift registry or push to an external registry.

#### Option A: Internal OpenShift Registry (oc start-build)

```bash
# Backend
oc new-build --binary --strategy=docker --name=wosa-backend -n $NAMESPACE
oc patch buildconfig wosa-backend -n $NAMESPACE \
  -p '{"spec":{"strategy":{"dockerStrategy":{"dockerfilePath":"Dockerfile.backend-openshift"}}}}'
oc start-build wosa-backend --from-dir=. --follow -n $NAMESPACE

# Frontend
oc new-build --binary --strategy=docker --name=wosa-frontend -n $NAMESPACE
oc patch buildconfig wosa-frontend -n $NAMESPACE \
  -p '{"spec":{"strategy":{"dockerStrategy":{"dockerfilePath":"Dockerfile.frontend-openshift"}}}}'
oc start-build wosa-frontend --from-dir=. --follow -n $NAMESPACE
```

The resulting images are available at
`image-registry.openshift-image-registry.svc:5000/$NAMESPACE/wosa-backend` and
`image-registry.openshift-image-registry.svc:5000/$NAMESPACE/wosa-frontend`.
These are the default image paths in `values-openshift.yaml` — no `--set` override needed.

#### Option B: External Registry (quay.io / Docker Hub)

```bash
# Build
podman build -f Dockerfile.backend-openshift -t quay.io/<org>/wosa-backend:latest .
podman build -f Dockerfile.frontend-openshift -t quay.io/<org>/wosa-frontend:latest .

# Push
podman login quay.io
podman push quay.io/<org>/wosa-backend:latest
podman push quay.io/<org>/wosa-frontend:latest
```

When using an external registry, override the image paths in step 3:

```bash
--set image.repository=quay.io/<org>/wosa-backend \
--set frontend.image.repository=quay.io/<org>/wosa-frontend
```

### 3. Install the Chart

All secrets — NGC image pull, NGC API, and application secrets — are created
automatically by the chart from a single `--set`:

```bash
helm install wosa deploy/helm/wosa/ \
  -n $NAMESPACE \
  -f deploy/helm/wosa/values-openshift.yaml \
  --set openshift.ngcSecret.password="$NGC_API_KEY"
```

> If using an external registry (Option B above), add the image overrides:
> ```bash
> helm install wosa deploy/helm/wosa/ \
>   -n $NAMESPACE \
>   -f deploy/helm/wosa/values-openshift.yaml \
>   --set openshift.ngcSecret.password="$NGC_API_KEY" \
>   --set image.repository=quay.io/<org>/wosa-backend \
>   --set frontend.image.repository=quay.io/<org>/wosa-frontend
> ```

**With optional features:**

```bash
helm install wosa deploy/helm/wosa/ \
  -n $NAMESPACE \
  -f deploy/helm/wosa/values-openshift.yaml \
  --set openshift.ngcSecret.password="$NGC_API_KEY" \
  --set demoData.enabled=true \
  --set demoDemand.enabled=true \
  --set monitoring.enabled=true
```

This creates:
- 2 x NIMCache (model download and caching)
- 2 x NIMService (inference servers)
- 1 x OpenShift Route (external UI access)
- 1 x Custom SCC + RoleBinding (allows NIM and app pods to run as image UIDs)
- All required secrets (NGC pull, NGC API, application credentials)
- WOSA application and supporting services (TimescaleDB, Redis, Milvus, Kafka, etc.)

### 4. Monitor Model Downloads

NIMCache resources download models from NGC. The default configuration filters
downloads to a single profile (~200 GB, ~10 minutes). See the [NIMCache filtering
note](#tested-hardware) for details on why filtering is critical.

```bash
oc get nimcache -n $NAMESPACE -w
```

Wait until all caches show `Ready`:

```
NAME                  STATUS   AGE
nim-llm-cache         Ready    30m
nim-embedding-cache   Ready    15m
```

## Verification

### Check NIMService Status

```bash
oc get nimservice -n $NAMESPACE
```

### Check Pods

```bash
oc get pods -n $NAMESPACE
```

All pods should reach `Running 1/1`. Infrastructure pods (TimescaleDB, Milvus) may take
1-2 minutes. NIM pods wait for their NIMCache to become Ready.

**Expected pods:**

| Pod | Purpose | Managed By |
|-----|---------|------------|
| `nim-llm` | LLM inference (Nemotron Super 49B) | NIM Operator |
| `nim-embedding` | Vector embedding | NIM Operator |
| `wosa-backend` | Multi-agent orchestration API | Helm |
| `wosa-frontend` | React web UI | Helm |
| `wosa-nginx` | Reverse proxy (Route entry point) | Helm |
| `wosa-timescaledb` | Time-series database | Helm |
| `wosa-redis` | Cache and sessions | Helm |
| `wosa-milvus` | Vector database | Helm |
| `wosa-etcd` | Milvus metadata store | Helm |
| `wosa-minio` | Milvus object storage | Helm |
| `wosa-kafka` | Event streaming | Helm |

### Health Endpoints

```bash
for svc in nim-llm nim-embedding; do
  echo -n "$svc: "
  oc exec -n $NAMESPACE deployment/$svc -- curl -s http://localhost:8000/v1/health/ready
  echo
done

# Backend health
ROUTE_HOST=$(oc get route -n $NAMESPACE -l app.kubernetes.io/component=nginx -o jsonpath='{.items[0].spec.host}')
curl -k https://$ROUTE_HOST/api/v1/health
```

## Accessing the UI

The Helm chart creates an OpenShift Route with TLS edge termination. Get the URL:

```bash
ROUTE_HOST=$(oc get route -n $NAMESPACE -l app.kubernetes.io/component=nginx -o jsonpath='{.items[0].spec.host}')
echo "https://$ROUTE_HOST"
```

Open `https://$ROUTE_HOST` in a browser. Default credentials: `admin` / `changeme`.

## Database Initialisation and Data Seeding

Schema migrations and post-deploy setup run automatically as Helm hooks on first install.

| Hook Job | Weight | Trigger | What it does |
|----------|--------|---------|-------------|
| `db-init-job` | 0 | post-install, post-upgrade | Applies all SQL migrations against TimescaleDB |
| `user-init-job` | 1 | post-install | Creates `admin` and `user` accounts |
| `demo-data-job` | 2 | post-install | Seeds inventory, tasks, safety incidents, equipment telemetry |
| `demo-demand-job` | 3 | post-install | Seeds 180 days of demand history for Forecasting |

**Enabled by default:** `db-init-job` (`dbInit.enabled`), `user-init-job` (`userInit.enabled`).
**Disabled by default:** `demo-data-job` (`--set demoData.enabled=true`), `demo-demand-job` (`--set demoDemand.enabled=true`).

## Monitoring

When `--set monitoring.enabled=true`, the chart deploys:

1. **ServiceMonitors** (4) — scrape targets for OpenShift's built-in Prometheus
2. **PrometheusRule** — 14 alert rules
3. **AlertmanagerConfig** — alert routing with email and webhook receivers
4. **Grafana Operator** — installed namespace-scoped via OLM
5. **Grafana instance** — with Route and Thanos Querier datasource
6. **GrafanaDashboard CRs** — 3 pre-built dashboards (Overview, Operations, Safety)

### Prerequisite (cluster-admin, one-time)

Enable user workload monitoring:

```bash
oc apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-monitoring-config
  namespace: openshift-monitoring
data:
  config.yaml: |
    enableUserWorkload: true
EOF
```

### Access Grafana

```bash
oc get route -n $NAMESPACE -l app.kubernetes.io/component=monitoring
# Default credentials: admin / changeme
```

## OpenShift-Specific Challenges and Solutions

### 1. Security Context Constraints

**What:** NIM containers and some infrastructure pods run as specific UIDs by default. OpenShift's `restricted-v2` SCC blocks this by forcing a random UID.

**Error:** `container has runAsNonRoot and image has non-numeric user`

**Services affected:** nim-llm, nim-embedding (NIM Operator managed).

**Fix:** The custom SCC (`wosa-nim`) sets `runAsUser: RunAsAny`, which allows containers to run as the UID defined in their image. The SCC is applied via RoleBinding to the necessary service accounts. It is created declaratively by the Helm chart when `openshift.scc.create: true`.

### 2. GPU Node Tolerations

**What:** GPU nodes carry `NoSchedule` taints. Without matching tolerations, pods stay `Pending`.

**Error:** `0/N nodes are available: N node(s) had untolerated taint`

**Services affected:** nim-llm, nim-embedding (all GPU pods).

**Fix:** Add tolerations in the values overlay for each NIM service:

```yaml
nimOperator:
  llm:
    tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
```

Check your taints with `oc describe node <gpu-node> | grep Taints`.

### 3. TOKENIZERS_PARALLELISM Race Condition

**What:** The HuggingFace tokenizers library has a thread pool race condition that can cause NIMs to crash or fail startup probes intermittently.

**Services affected:** nim-llm, nim-embedding.

**Fix:** All NIM Operator env blocks include `TOKENIZERS_PARALLELISM=false` as a preventive measure.

### 4. Hardcoded Connection Parameters

**What:** Several Python scripts hardcode `localhost` for database connections and local file paths for output, which only work in Docker Compose (all services share a network). On Kubernetes/OpenShift, each service runs in a separate pod.

**Services affected:** `advanced_forecasting.py`, `generate_historical_demand.py`, `rapids_gpu_forecasting.py`, `phase3_advanced_forecasting.py`, `rapids_forecasting_agent.py`, `phase1_phase2_forecasting_agent.py`.

**Fix:** Replaced hardcoded values with environment variables (`PGHOST`, `PGPORT`, `FORECAST_OUTPUT_DIR`) while preserving the original defaults for backward compatibility. Note: `phase1_phase2_forecasting_agent.py` uses `DB_HOST`/`DB_PORT` (upstream naming); both are set in the backend deployment template.

### 5. Container Images Require OpenShift Dockerfiles

**What:** The upstream Dockerfiles rely on Docker Compose bind-mounting the entire repository into the container (`volumes: [".:/app"]`). Without bind mounts, images are missing agent configs (`data/config/agents/`), SQL migrations (`data/postgres/`), scripts, and `README.md`. Additionally, `requirements.docker.txt` is missing packages (`tiktoken`, `psycopg`, `pandas`, `nemoguardrails`).

**Services affected:** wosa-backend, wosa-frontend.

**Fix:** Use `Dockerfile.backend-openshift` and `Dockerfile.frontend-openshift` which bundle all required files and dependencies into the image.

## Known Limitations

1. **RAPIDS GPU Forecasting.** The upstream `Dockerfile.rapids` depends on `nvcr.io/nvidia/rapidsai/rapidsai:24.02`, which was removed from NGC. The RAPIDS GPU training path cannot be built. Training works without RAPIDS — the backend automatically falls back to CPU-based scikit-learn models (RandomForest, XGBoost, GradientBoosting). All 38 SKUs train and forecast successfully on CPU.

2. **Milvus GPU Acceleration.** Full GPU support is implemented in the Helm chart (GPU image, CUDA env vars, resource requests, tolerations). However, the upstream codebase never wires it — `gpu_hybrid_retriever.py` exists but no agent imports it. All agents use the CPU `IVF_FLAT` index. The chart supports `milvus.gpu.enabled=true` at deploy time, but it has no effect until upstream imports `gpu_hybrid_retriever`.

3. **Monitoring Dashboard Coverage.** Business-logic Prometheus metrics are defined in `MetricsCollector` but only HTTP middleware metrics are called by the application. Infrastructure panels show real data; business-logic panels (tasks, equipment, safety, environmental) show "No data". Dashboards will display data once the application calls the existing `MetricsCollector` methods.

4. **Nano VL NIM.** The upstream blueprint includes a vision-language NIM (`llama-3.2-nv-nanoVL-1b-v1`) for document processing. The NGC image name contains uppercase letters (`VL`) which violates the OCI image specification (requires lowercase). This makes it incompatible with container runtimes. The Helm chart omits this NIM; document processing falls back to the hosted NVIDIA API via `LLAMA_NANO_VL_URL`.

## Cleanup

```bash
# Uninstall the Helm release
helm uninstall wosa -n $NAMESPACE

# NIMCache PVCs persist by default (helm.sh/resource-policy: keep).
# Delete manually if you want to reclaim storage:
oc delete nimcache --all -n $NAMESPACE
oc delete pvc -l app.nvidia.com/nim-cache -n $NAMESPACE

# Delete remaining PVCs
oc delete pvc -l app.kubernetes.io/instance=wosa -n $NAMESPACE
```

To remove build resources:

```bash
oc delete buildconfig wosa-backend wosa-frontend -n $NAMESPACE --ignore-not-found
oc delete imagestream wosa-backend wosa-frontend -n $NAMESPACE --ignore-not-found
```

To remove the namespace entirely:

```bash
oc delete project $NAMESPACE
```

If monitoring was enabled:

```bash
oc delete grafanas,grafanadatasources,grafanadashboards --all -n $NAMESPACE --ignore-not-found
oc delete subscription grafana-operator -n $NAMESPACE --ignore-not-found
oc get csv -n $NAMESPACE -o name | grep grafana-operator | xargs -r oc delete -n $NAMESPACE --ignore-not-found
oc delete clusterrolebinding wosa-${NAMESPACE}-grafana-monitoring-view --ignore-not-found
```
