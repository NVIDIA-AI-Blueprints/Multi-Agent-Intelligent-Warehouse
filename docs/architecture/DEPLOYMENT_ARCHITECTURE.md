# MAIW v2 Deployment Architecture

<!-- Phase 10 — documents current behavior, not target assumptions -->

## Service Boundaries

```
                        ┌─────────────────────────┐
                        │   Users / Command Center │
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
| Dockerfile | `Dockerfile.backend` |
| Entrypoint | `uvicorn maiw_api.app:app --host 0.0.0.0 --port 8001` |
| Port | `8001` |
| Healthcheck | `GET /api/v1/health` |
| Liveness | `GET /api/v1/live` |
| Readiness | `GET /api/v1/ready` |

Packages installed in the image: `maiw-mcp`, `maiw-state`, `maiw-decision`,
`maiw-models`, `maiw-skills`, `maiw-execution`, `maiw-agents` (editable install
of `apps/api`).

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

### Command Center / Frontend (`wosa-frontend`)

| Field | Value |
|---|---|
| Dockerfile | `Dockerfile.frontend` |
| Entrypoint | `npm start` |
| Port | `3001` |
| API dependency | `REACT_APP_API_URL=http://localhost:8001` |

### Infrastructure Services

| Container | Image | Port(s) | Purpose |
|---|---|---|---|
| `wosa-timescaledb` | `timescale/timescaledb:2.15.2-pg16` | 5435→5432 | Primary operational database |
| `wosa-redis` | `redis:7` | 6379 | Caching / session state |
| `wosa-milvus` | `milvusdb/milvus:v2.4.3` | 19530, 9091 | Optional vector store |
| `wosa-etcd` | `quay.io/coreos/etcd:v3.5.9` | 2379 | Milvus coordination |
| `wosa-minio` | `minio/minio` (2024-03-15) | 9000, 9001 | Milvus object storage |
| `wosa-kafka` | `apache/kafka:3.7.0` | 9092 | Event streaming |
| `wosa-nginx` | `nginx:1.25.3-alpine` | 3000→80 | Reverse proxy (dev) |
| `wosa-llm-nim` | `nvcr.io/nim/nvidia/nemotron-3-super-120b-a12b:latest` | 8000 | GPU profile only |

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

## Environment Variables

### API / Runtime

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | Runtime environment label |
| `MAIW_APP_TITLE` | `MAIW API` | OpenAPI title |
| `MAIW_APP_VERSION` | `0.0.0-dev` | Version string |
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
| `GET /api/v1/ready` | Runtime initialized + DB reachable | TimescaleDB |
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
