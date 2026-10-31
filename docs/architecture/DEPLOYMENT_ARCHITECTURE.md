# MAIW v2 Deployment Architecture

**Phase 20C-C: Deployment Operationalization** — Phase 20C-B LIVE_SANDBOX_QUALIFIED (PR #135, 2026-10-05)

---

## Reference Deployment Topology (Phase 20C-C)

The qualified single-node reference deployment topology:

```
HOST (single node — epg-tme-smc-h100-02, 4×H100 NVL)
├── MAIW API (port 8001)
│   ├── ModelGateway ──→ PolicyFilter (nemotron-3 / nemotron-3.5 ONLY)
│   │                ──→ ModelRouter ──→ NIMProvider ──→ NIM endpoint
│   ├── POST /api/v1/inference  (auth-required: X-Maiw-Internal-Token)
│   ├── DecisionEngine → ActionExecutor (governed writes)
│   ├── ProcedureHost: SOP Engine + JsonFileGovernanceInbox (restart-safe, v2.0.1)
│   ├── ActionExecutor (write path — host only, never sandbox)
│   ├── SOP Engine (ProcedureStateStore: JsonFileProcedureStateStore)
│   └── MCP domain clients (Inventory/Equipment/Labor/Wave)
│
├── Approved Nemotron 3 / 3.5 deployments (v2.1.0 defaults)
│   ├── lightning  nvidia/nemotron-3.5-lightning-30b-a3b  (nemotron-3.5; LOW + MEDIUM)
│   ├── ultra      nvidia/nemotron-3-ultra-550b-a55b      (nemotron-3; HIGH + CRITICAL)
│   ├── super      nvidia/nemotron-3-super-120b-a12b      (nemotron-3, DISABLED: hosted EOL 2026-10-19)
│   └── endpoint   Hosted: https://integrate.api.nvidia.com/v1  (NVIDIA cloud)
│                  OR Local NIM: http://localhost:8000/v1
│
└── NemoClaw/OpenShell sandbox runtime
    ├── SandboxedAgentRuntime + SOP Engine (agent-side)
    ├── RuntimeCapabilityPolicy (deny-by-default; WRITE always denied)
    ├── MAIWHTTPModelGatewayClient → POST http://<HOST_IP>:8001/api/v1/inference  (canonical app, v2.0.1)
    └── NEVER holds: NIM credentials, warehouse write credentials, ApprovalStore

Persistence root: /var/lib/maiw/
├── procedures/   JsonFileProcedureStateStore (atomic .json per procedure)
├── governance/   JsonFileGovernanceInbox (governance_inbox.jsonl, append-only)
└── runtime/      maiw-api.pid, maiw-api.log
```

### Version Matrix (Qualified)

| Component | Pinned Version | Status |
|---|---|---|
| NemoClaw | 0.0.124 | QUALIFIED |
| OpenShell | 0.0.116 | QUALIFIED |
| Python (host) | 3.12.3 | QUALIFIED |
| nvidia/nemotron-3-super-120b-a12b | gen=nemotron-3 | QUALIFIED 2026-10-05 (historical — Super has been disabled by default since v2.1.0; hosted endpoint retired 2026-10-19) |
| Approved generations | nemotron-3, nemotron-3.5 | PolicyFilter enforced |

The v2.1.0 model defaults (Lightning for LOW/MEDIUM, Ultra for HIGH/CRITICAL) are
described in [`docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md`](../operations/REFERENCE_DEPLOYMENT_RUNBOOK.md).

### Trust Boundaries

- **Sandbox cannot call ActionExecutor, ApprovalStore, or warehouse MCP directly**
- **Sandbox cannot hold NIM credentials or warehouse write credentials**
- **Sandbox reaches inference ONLY via POST /api/v1/inference (auth-required)**
- **PolicyFilter enforces approved model generations at the host level**
- **GovernanceInbox deduplication is host-side — sandbox cannot bypass it**

### Restart / Rollback Semantics

- Procedure state: file-backed, atomic write, survives process crash
- Governance inbox: file-backed, append-only, duplicate-safe across restarts
- Rollback: stop → restore previous app → preserve durable state → start
- DO NOT delete procedure/governance state as a rollback strategy

---

## Service Boundaries

```
                        ┌─────────────────────────┐
                        │   Users / MAIW Frontend │
                        │   (React, port 3001)     │
                        └───────────┬─────────────┘
                                    │ HTTP (all /api/v1/*)
                        ┌───────────▼─────────────┐
                        │        MAIW API          │
                        │  maiw_api.app:app        │
                        │  port 8001               │
                        │  Dockerfile.backend      │
                        └──┬──────────────────┬───┘
                           │ MCP 2.0 HTTP      │ SQL / async
              ┌────────────▼──────────┐   ┌───▼────────────┐
              │   MCP Domain Servers  │   │   TimescaleDB  │
              │  (stateless HTTP)     │   │   port 5435    │
              ├───────────────────────┤   └────────────────┘
              │ Inventory   port 8765 │
              │ Equipment   port 8766 │   ┌────────────────┐
              │ Labor       port 8767 │   │     Redis      │
              │ Wave        port 8768 │   │   port 6379    │
              └───────────────────────┘   └────────────────┘

External:
  NIM endpoints (LLM_NIM_URL — hosted or on-prem GPU cluster)
  Milvus         port 19530 (optional vector store)
```

---

## Services

### MAIW API (`wosa-backend`)

| Field | Value |
|---|---|
| Dockerfile | `Dockerfile.backend` (published as `bpf-maiw-backend`) |
| Base image | `python:3.13.x-slim-trixie` (Debian 13), pinned by digest |
| Entrypoint | `uvicorn maiw_api.app:app --host 0.0.0.0 --port 8001` |
| Port | `8001` |
| Healthcheck | `GET /api/v1/health` (Python stdlib; the image ships no curl) |
| Liveness | `GET /api/v1/live` |
| Readiness | `GET /api/v1/ready` |
| User | `appuser` (non-root) |

Packages installed in the image: `maiw-contracts`, `maiw-world`, `maiw-mcp`,
`maiw-state`, `maiw-decision`, `maiw-models`, `maiw-skills`, `maiw-execution`,
`maiw-agents` (editable install of `apps/api`). The image also carries
`mcp_servers/` and the canonical `data/worlds/` DataPack for the demo profile.
The runtime stage applies `apt-get upgrade` and installs no extra OS packages
(no curl, git, poppler-utils) and no pip/setuptools/wheel. PDF page rendering
(`pdf2image` + poppler) is not part of this image.

The API is the **only service that external clients call**. MCP domain servers
are internal infrastructure — they are not exposed through the ingress.

### MCP Domain Servers

Four domain servers live in `mcp_servers/`. Each supports three transports
controlled by `MAIW_MCP_TRANSPORT`:

| Domain | Default port | Transport env var |
|---|---|---|
| Inventory | 8765 | `MAIW_MCP_INVENTORY_PORT` / `MAIW_MCP_INVENTORY_HOST` |
| Equipment | 8766 | `MAIW_MCP_EQUIPMENT_PORT` / `MAIW_MCP_EQUIPMENT_HOST` |
| Labor     | 8767 | `MAIW_MCP_LABOR_PORT` / `MAIW_MCP_LABOR_HOST` |
| Wave      | 8768 | `MAIW_MCP_WAVE_PORT` / `MAIW_MCP_WAVE_HOST` |

Transport values: `streamable-http` (default for network deployments),
`sse`, `stdio`.

`streamable-http` is started with `stateless_http=True`, which means **no
session affinity is required** — MCP domain servers are horizontally
scalable. See [Stateless MCP Invariant](#stateless-mcp-invariant).

### MAIW Frontend (`wosa-frontend`)

| Field | Value |
|---|---|
| Dockerfile | `Dockerfile.frontend` (published as `bpf-maiw-frontend`) |
| Build stage | `node:22.x-alpine` — `npm ci` + `npm run build` (not shipped) |
| Runtime image | `nginxinc/nginx-unprivileged:1.30.x-alpine` (non-root, no Node.js/npm) |
| Container port | `8080` (compose publishes `3001:8080`) |
| API dependency | nginx proxies `/api/` to `MAIW_API_UPSTREAM` (default `http://backend:8001`) |
| Healthcheck | `GET /healthz` |

The image serves the static production build with SPA fallback (deep links
return `index.html`). It never holds or adds the operator write credential
(`X-Maiw-Operator-Token`) and strips it from browser requests, so governed
equipment writes from this UI are refused by the API (`403`, or `503` when no
operator credential is configured) — by design. The hot-reload development
server (`npm start` in `src/ui/web`, port 3001, `src/setupProxy.js`) is run
from a checkout, not from this image.

### Infrastructure Services

| Container | Image | Port(s) | Purpose |
|---|---|---|---|
| `wosa-timescaledb` | `timescale/timescaledb:2.15.2-pg16` | 5435→5432 | Primary operational database |
| `wosa-redis` | `redis:7` | 6379 | Caching / session state |
| `wosa-milvus` | `milvusdb/milvus:v2.4.3` | 19530, 9091 | Optional vector store |
| `wosa-etcd` | `quay.io/coreos/etcd:v3.5.9` | 2379 | Milvus coordination |
| `wosa-minio` | `pgsty/minio` (RELEASE.2026-08-04, digest-pinned) | 9000, 9001 | Milvus object storage |
| `wosa-kafka` | `apache/kafka:3.7.0` | 9092 | Event streaming |
| `wosa-nginx` | `nginx:1.25.3-alpine` | 3000→80 | Reverse proxy (dev) |
| `wosa-llm-nim` | `nvcr.io/nim/nvidia/nemotron-3-super-120b-a12b:latest` | 8000 | GPU profile only |

In `deploy/compose/docker-compose.dev.yaml` every published port binds `127.0.0.1`.
nginx (3000), frontend (3001) and the API (8001) follow `MAIW_PUBLISH_ADDRESS`
(default `127.0.0.1`); datastores and the MCP servers (8765–8768) are loopback-only.

### Optional: RAPIDS Forecasting Agent

| Field | Value |
|---|---|
| Dockerfile | `Dockerfile.rapids` |
| Base | `nvcr.io/nvidia/rapidsai/rapidsai:24.02-cuda12.0` |
| Port | 8002 |
| Purpose | GPU-accelerated demand forecasting |

---

## Application Libraries (Not Services)

The following packages are **application libraries** — they are installed into
the API container, not run as separate processes:

- `maiw-state` — WarehouseStateProvider, snapshot models
- `maiw-decision` — DecisionEngine
- `maiw-skills` — read/proposal/execution skill implementations
- `maiw-execution` — BaseActionExecutor, domain executors
- `maiw-agents` — EquipmentAssetOperationsAgent, OperationsCoordinationAgent, SafetyComplianceAgent
- `maiw-models` — ModelGateway, NIMProvider, NIMClient
- `maiw-mcp` — shared MCP client, CapabilityRegistry, contracts

---

## Sandbox Topology (Phase 20A — optional)

The agent runtime may be moved out of the API container into an OpenShell
sandbox. The sandbox is a **leaf**: it reaches only the MAIW API, and nothing
reaches it.

```
            ┌─────────────────────────────┐
            │        MAIW API (8001)       │
            │  DecisionEngine              │
            │  ActionExecutor              │
            │  ApprovalStore               │
            │  ModelGateway                │
            │  ProcedureStateStore (auth.) │
            │  boundary validators         │
            └──┬────────────────────┬──────┘
               │ MCP 2.0 (incl.      │  inference  +  read capabilities
               │ write capabilities) │  (the ONLY two routes in)
   ┌───────────▼──────────┐    ┌─────▼──────────────────────────┐
   │  MCP Domain Servers  │    │  OpenShell sandbox             │
   │  8765–8768           │    │   SOP Engine + AgentRuntime    │
   │  NEVER reachable     │    │   network: deny-by-default     │
   │  from the sandbox    │    │   fs: /workspace/* only        │
   └──────────────────────┘    │   credentials: none            │
                               └────────────────────────────────┘
```

Three topology facts do the work:

- **MCP servers are not exposed to the sandbox at all.** `mcp_servers/equipment`
  serves `get_status` (read) and `assign` (write) on the same port 8766;
  exposing it for its reads would expose its writes. Reads arrive through the
  MAIW read endpoint instead.
- **The sandbox holds no credentials.** No `NVIDIA_API_KEY`, no `DATABASE_URL`,
  no MCP token. `container_run_args()` emits no `--env` flags.
- **Only `/workspace/procedure_state` is writable**, and it is a working copy —
  authoritative procedure state stays in the host `ProcedureStateStore`, so a
  sandbox that dies mid-procedure loses nothing.

### Sandbox environment variables (host-side only)

Read on the host, before the sandbox exists. None of these can widen a
capability policy — policies are built from `AgentDefinition` and
`SOPDefinition`, never from the environment.

| Variable | Default | Description |
|---|---|---|
| `MAIW_SANDBOX_MODE` | `disabled` | `disabled` \| `required` \| `preferred`. An unrecognised value **raises** rather than defaulting |
| `MAIW_SANDBOX_RUNTIME` | `none` | `none` \| `openshell` \| `container` |
| `MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT` | `http://maiw-api:8000/api/v1/inference` | host inference route (live — `POST /api/v1/inference`, Phase 20C-A/20C-B qualified) |
| `MAIW_SANDBOX_READ_ENDPOINT` | `http://maiw-api:8000/api/v1/capabilities/read` | host read-capability route (not yet implemented) |
| `MAIW_SANDBOX_IMAGE` | *(unset)* | pinned agent image reference |
| `MAIW_NEMOCLAW_VERSION` | *(unset)* | version qualified against; unset ⇒ `CONFIGURATION_PENDING` |
| `MAIW_OPENSHELL_VERSION` | *(unset)* | version qualified against |

`MAIW_SANDBOX_MODE=required` with no sandbox available **fails every task**.
That is intended: a deployment claiming containment on a host that cannot
provide it should not run.

See [NEMOCLAW_OPENSHELL_INTEGRATION.md](NEMOCLAW_OPENSHELL_INTEGRATION.md).

---

## Environment Variables

### API / Runtime

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | Runtime environment label |
| `MAIW_APP_TITLE` | `Multi-Agent Intelligent Warehouse API` | OpenAPI title |
| `MAIW_APP_VERSION` | `0.1.0` | Version string |
| `MAIW_CORS_ORIGINS` | `*` | CORS origin allowlist |
| `MAIW_API_HOST` | `0.0.0.0` | Uvicorn bind address |
| `SECRET_KEY` | — | Auth token signing key |

### ModelGateway / NIM

| Variable | Description |
|---|---|
| `LLM_NIM_URL` | NIM inference base URL (e.g. `https://integrate.api.nvidia.com/v1`) |
| `NVIDIA_API_KEY` | NGC/NIM API key — **secret** |

### MCP Server URLs (consumed by the API)

| Variable | Default | Description |
|---|---|---|
| `MAIW_MCP_SERVER_INVENTORY_URL` | — | Inventory MCP server base URL |
| `MAIW_MCP_SERVER_EQUIPMENT_URL` | — | Equipment MCP server base URL |
| `MAIW_MCP_SERVER_LABOR_URL` | — | Labor MCP server base URL |
| `MAIW_MCP_SERVER_WAVE_URL` | — | Wave MCP server base URL |

### MCP Server Configuration (consumed by each server)

| Variable | Description |
|---|---|
| `MAIW_MCP_TRANSPORT` | `streamable-http` / `sse` / `stdio` |
| `MAIW_MCP_INVENTORY_PORT` / `_HOST` | Inventory server bind (default 8765) |
| `MAIW_MCP_EQUIPMENT_PORT` / `_HOST` | Equipment server bind (default 8766) |
| `MAIW_MCP_LABOR_PORT` / `_HOST` | Labor server bind (default 8767) |
| `MAIW_MCP_WAVE_PORT` / `_HOST` | Wave server bind (default 8768) |

### Database

| Variable | Description |
|---|---|
| `POSTGRES_USER` | TimescaleDB user |
| `POSTGRES_PASSWORD` | TimescaleDB password — **secret** |
| `POSTGRES_DB` | Database name |
| `DB_HOST` | Hostname (default `timescaledb` in compose) |
| `DB_PORT` | Port (default 5432 inside compose) |
| `DATABASE_URL` | Full asyncpg URL (overrides individual vars if set) |

### Optional Infrastructure

| Variable | Description |
|---|---|
| `REDIS_HOST` / `REDIS_PORT` | Redis coordinates |
| `MILVUS_HOST` / `MILVUS_PORT` | Milvus coordinates |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka brokers |

---

## Stateless MCP Invariant

All four MCP domain servers are started with `stateless_http=True` (MCP 2.0
Streamable HTTP). This means:

- No `Mcp-Session-Id` routing required
- No sticky sessions in load balancers or ingress
- Horizontally scalable — multiple replicas behind a standard load balancer
- Kubernetes deployments do not need `sessionAffinity: ClientIP`

This is a deliberate architectural constraint and must be preserved in all
deployment manifests.

---

## Health and Readiness

| Endpoint | Semantic | Dependencies |
|---|---|---|
| `GET /api/v1/live` | Process alive | None |
| `GET /api/v1/ready` | Deployment profile can do its work (503 `NOT_READY` otherwise) | Profile valid; runtime assembled; persistence writable; ModelGateway built with every enabled role bound to an approved model; governed write path (`demo` / `reference_governed` only); required MCP domains; DB when the profile requires it; sandbox when `MAIW_SANDBOX_MODE=required` |
| `GET /api/v1/health` | Comprehensive status | DB + Redis + Milvus (degraded, not 503) |
| `GET /api/v1/health/simple` | Lightweight DB check | TimescaleDB |
| `GET /api/v1/runtime/status` | MAIWRuntime component availability | None (reflects startup state) |

Liveness (`/live`) must **never** fail because an optional MCP domain is
offline. Health (`/health`) returns `status: "degraded"` when optional services
are unavailable — it does not return a non-2xx code.

---

## Secrets

The following values are secrets and must never be committed, logged, or
exposed through health/status endpoints:

- `NVIDIA_API_KEY` — NIM inference
- `POSTGRES_PASSWORD` — database credentials
- `SECRET_KEY` — auth signing key
- Any `MINIO_ROOT_PASSWORD` / `MINIO_SECRET_KEY`

In CI, these are injected via GitHub Actions `secrets`. In production,
use Kubernetes `Secret` references or an external secret manager.

---

## Kubernetes / Helm Target Architecture

No Kubernetes manifests currently exist in this repository. The target
conceptual architecture for a future Helm chart:

```
Ingress (NGINX or Istio)
    │
    ▼
MAIW API Deployment (port 8001)
HPA: horizontal, no sticky sessions
    │
    ├── Inventory MCP  Deployment (port 8765) — stateless, scalable
    ├── Equipment MCP  Deployment (port 8766) — stateless, scalable
    ├── Labor MCP      Deployment (port 8767) — stateless, scalable
    └── Wave MCP       Deployment (port 8768) — stateless, scalable

External / managed:
    TimescaleDB (StatefulSet or managed PG)
    Redis (StatefulSet or managed cache)
    Milvus (optional, StatefulSet)
    NIM endpoints (external URL or on-prem Deployment)
```

ConfigMaps: non-secret configuration per service
Secrets: `NVIDIA_API_KEY`, `POSTGRES_PASSWORD`, `SECRET_KEY`
