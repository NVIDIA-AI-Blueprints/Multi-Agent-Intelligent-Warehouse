# API Documentation

## Overview

The MAIW API is a FastAPI application. The only release composition root is
`apps/api/maiw_api/app.py`, started with:

```bash
uvicorn maiw_api.app:app --port 8001
```

(`src/api/app.py` is a legacy development server and is never deployed.)

The live OpenAPI description is the authoritative reference for request and
response schemas. This page lists what the release app mounts and the rules that
are not visible from the schema alone.

- **Swagger UI**: `http://localhost:8001/docs`
- **ReDoc**: `http://localhost:8001/redoc`
- **OpenAPI JSON**: `http://localhost:8001/openapi.json`

## Base URL

- **Local development**: `http://localhost:8001` (the UI dev server on
  `http://localhost:3001` proxies `/api` to it)

## Authentication

There are three separate credentials. They are different authority domains and
none of them substitutes for another.

| Credential | Header | Authorises |
|---|---|---|
| User session (JWT) | `Authorization: Bearer <jwt>` | Identity endpoints under `/api/v1/auth/*` |
| Operator write token (`MAIW_OPERATOR_WRITE_TOKEN`, ≥ 32 chars) | `X-Maiw-Operator-Token` | Operational writes: the governed equipment write routes and `/api/v1/executions/*` |
| Inference internal token (`MAIW_INFERENCE_INTERNAL_TOKEN`) | `X-Maiw-Internal-Token` | Only `POST /api/v1/inference` (the sandbox inference boundary) |

A JWT alone never authorises an operational write.

### Operator write credential

Every governed equipment write route runs two checks before the request body is
read and before any agent, `DecisionEngine`, `ActionExecutor` or MCP call
(`apps/api/maiw_api/write_auth.py`):

1. `require_operator_write` — the `X-Maiw-Operator-Token` header:

   | Condition | Status | `code` |
   |---|---|---|
   | Server has no usable token (unset, < 32 chars, the `.env.example` placeholder, or equal to `MAIW_INFERENCE_INTERNAL_TOKEN`) | 503 | `OPERATOR_WRITE_AUTH_NOT_CONFIGURED` |
   | Header missing | 403 | `OPERATOR_WRITE_CREDENTIAL_REQUIRED` |
   | Header does not match | 401 | `INVALID_OPERATOR_WRITE_CREDENTIAL` |

2. `require_governed_writes_offered` — the active deployment profile must offer
   governed writes (`demo`, or `MAIW_DEPLOYMENT_PROFILE=reference_governed`).
   Otherwise: 503 `GOVERNED_WRITES_NOT_OFFERED`. The default `reference` profile
   does not offer governed writes.

These denials return a typed body:

```json
{
  "error": true,
  "code": "OPERATOR_WRITE_CREDENTIAL_REQUIRED",
  "message": "operational writes require the X-Maiw-Operator-Token credential; ...",
  "status_code": 403
}
```

The production UI image never holds the operator token and strips the header
from browser requests, so governed writes from that UI are refused by design.

### Identity endpoints

`/api/v1/auth/*` (from `src/api/routers/auth.py`) is mounted in full, including
`POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `GET /api/v1/auth/me`,
`GET /api/v1/auth/users` (admin) and the public
`GET /api/v1/auth/users/public` (active users' `id`, `username`, `full_name`,
`role`, for login dropdowns).

## Endpoints mounted by the release app

### Health and status

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/live` | Liveness — process alive |
| GET | `/api/v1/ready` | Readiness for the active deployment profile (503 `NOT_READY` otherwise) |
| GET | `/api/v1/health` | Comprehensive status; `degraded`, not non-2xx, when optional services are down |
| GET | `/api/v1/health/simple` | Lightweight DB check |
| GET | `/api/v1/version`, `/api/v1/version/detailed` | Build / version information |
| GET | `/api/v1/runtime/status` | MAIW runtime component availability |
| GET | `/api/v1/mcp/status`, `/api/v1/mcp/capabilities` | MCP domain status and registered capabilities |

### Copilot

`POST /api/v1/copilot/turn` — one operator turn (ASK / ANALYZE / ACT /
OBSERVE_OUTCOME; intent is classified server-side). Returns 503 unless the
Copilot service is available (`MAIW_DEMO_MODE=true`).

Request (`CopilotTurnRequest`):

```json
{
  "conversation_id": null,
  "message": "What is the current wave risk?",
  "warehouse_id": "DC-47",
  "scenario_name": ""
}
```

`message` is required (1–2000 chars); omit `conversation_id` to start a new
conversation. The response (`CopilotTurnResponse`) always carries
`conversation_id`, `turn_id`, `trace_id`, `intent` and `status`, plus
intent-specific fields (for example `answer`, `evidence`, and the model routing
provenance `model_id`, `requested_role`, `selected_role`, `fallback_from`). See
`/openapi.json` for the full schema.

### Equipment

Reads:

| Method | Path |
|---|---|
| GET | `/api/v1/equipment` |
| GET | `/api/v1/equipment/assignments` |
| GET | `/api/v1/equipment/maintenance/schedule` |
| GET | `/api/v1/equipment/{asset_id}` |
| GET | `/api/v1/equipment/{asset_id}/telemetry` |
| GET | `/api/v1/equipment/{asset_id}/status` |

Governed writes (operator write credential + governed profile required, see
above). Each one builds an `ActionProposal` and evaluates it with
`DecisionEngine`; nothing executes unless the decision is `approved`:

| Method | Path | Body (`apps/api/maiw_api/routers/equipment.py`) | Executes? |
|---|---|---|---|
| POST | `/api/v1/equipment/assign` | `AssignmentRequest`: `asset_id`, `assignee`, `assignment_type` (default `"task"`), optional `task_id`, `duration_hours`, `notes`, `warehouse_id` | Only if approved (assignment is MEDIUM risk, so normally `requires_human_approval`) |
| POST | `/api/v1/equipment/release` | `ReleaseRequest`: `asset_id`, `released_by`, optional `notes`, `warehouse_id` | If approved (release is LOW risk) |
| POST | `/api/v1/equipment/maintenance` | `MaintenanceRequest`: `asset_id`, `maintenance_type`, `description`, `scheduled_by`, `scheduled_for`, `estimated_duration_minutes` (default 60), `priority` (default `"medium"`), optional `warehouse_id` | Never — proposal only |

Response (assign / release):

```json
{
  "status": "requires_human_approval",
  "action": "warehouse.equipment.assign",
  "proposal_id": "<uuid>",
  "decision_id": "<uuid>",
  "reason": "<explanation>",
  "executed": false
}
```

`status` is the decision outcome (`requires_human_approval`, `rejected`,
`requires_fresh_state`, …) or, after an approved decision, the execution outcome
(`executed`, `no_op`, `deferred`, `conflict`, `failed` with HTTP 200, or `unknown`).
Optional headers: `X-Trace-Id` (propagated end to end) and `Idempotency-Key` (a
replay never writes twice). An ambiguous write (`unknown`, `executed: null`)
returns HTTP 202 and is never retried automatically: a further write to the same
asset is refused with 409 `RECONCILIATION_REQUIRED` until it is reconciled
through `/api/v1/executions/{execution_id}/reconcile`.

### Executions

All routes require the operator write credential.

| Method | Path |
|---|---|
| GET | `/api/v1/executions` |
| GET | `/api/v1/executions/{execution_id}` |
| POST | `/api/v1/executions/{execution_id}/reconcile` |

### Operations and safety (read-only)

Only the read routes are mounted; the SQL task / incident writes have no governed
path and are not shipped.

| Method | Path |
|---|---|
| GET | `/api/v1/operations/tasks`, `/api/v1/operations/tasks/{task_id}` |
| GET | `/api/v1/operations/workforce` |
| GET | `/api/v1/safety/incidents`, `/api/v1/safety/incidents/{incident_id}` |
| GET | `/api/v1/safety/policies`, `/api/v1/safety/policies/{policy_id}` |

### World, agents, procedures, Model Lab

All read-only:

- `/api/v1/world/*` — Warehouse World explorer (see
  [WAREHOUSE_WORLD.md](../architecture/WAREHOUSE_WORLD.md#world-api))
- `/api/v1/agent-tasks`, `/api/v1/agent-tasks/{task_id}`, `/api/v1/agent-tasks/{task_id}/sop`
- `/api/v1/procedures`, `/api/v1/procedures/{procedure_id}`
- `/api/v1/model-lab/runs`, `/api/v1/model-lab/runs/{run_id}`, `/api/v1/model-lab/runs/{run_id}/cases`,
  `/api/v1/model-lab/runs/{run_id}/cases/{case_id}`, `/api/v1/model-lab/model-status`

### Demo

`/api/v1/demo/*` (scenarios, `analyze`, `approve`, `reject`, `reconcile`,
`counterfactual/result`) and `/api/v1/events/stream` drive the demo UI
(`MAIW_DEMO_MODE=true`). See `/openapi.json` for the exact routes.

### Sandbox inference

`POST /api/v1/inference` — the bounded inference boundary for sandboxed
runtimes. Requires `X-Maiw-Internal-Token` (503 if
`MAIW_INFERENCE_INTERNAL_TOKEN` is not configured). The body accepts only a
strict field allowlist (`task`, `messages`, `reasoning`, `risk_level`, `modality`,
`deadline_ms` and trace / task / procedure identifiers); unknown fields
such as a model or provider override are rejected with 422. The host-side
`ModelGateway` selects the model. See
[MODEL_GATEWAY.md](../architecture/MODEL_GATEWAY.md).

### Legacy routers (read-only)

From `src/api/routers/`, mounted with only their GET routes: `/api/v1/inventory/*`,
`/api/v1/wms/*`, `/api/v1/iot/*`, `/api/v1/erp/*`, `/api/v1/scanning/*`,
`/api/v1/attendance/*`, `/api/v1/migrations/*`, `/api/v1/forecasting/*`,
`/api/v1/training/*`.

`/api/v1/document/*` is mounted read-only except `POST /api/v1/document/upload`,
`POST /api/v1/document/approve/{document_id}` and
`POST /api/v1/document/reject/{document_id}`; `/search`, `/validate` and
`/analytics` are not shipped.

### Not mounted

`/api/v1/chat`, `/api/v1/reasoning`, every POST/PUT/PATCH/DELETE of the legacy
routers above other than the three document routes (including
`POST /api/v1/migrations/migrate`), and `/api/v1/metrics`
(served only by the legacy `src/api/app.py`). There is no WebSocket endpoint.

## Rate limiting

Requests are rate limited per client (`src/api/services/security/rate_limiter.py`;
Redis-backed, with an in-memory fallback). Defaults: 100 requests/minute, with
tighter limits on `POST /api/v1/auth/login` (5/min) and
`POST /api/v1/document/upload` (10/min). A limited request receives HTTP 429 with
a `Retry-After` header. `RATE_LIMIT_FAIL_MODE` controls what happens when the
limiter itself fails. `/api/v1/health`, `/api/v1/health/simple`, `/docs` and
`/openapi.json` are exempt.

## Support

- **Issues**: [https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues)
