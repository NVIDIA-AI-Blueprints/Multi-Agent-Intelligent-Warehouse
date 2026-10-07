# MAIW v2.0.1 — Release Notes (DRAFT — not tagged)

**Status:** release candidate, pending an independent re-audit. Do not tag
until that re-audit passes. `v2.0.0` (`816ace73…`) is unchanged.

## Why v2.0.1

An independent clean-room audit of the `v2.0.0` tag
(PR #142, `docs/audits/MAIW_V2_INDEPENDENT_POST_RELEASE_AUDIT.md`) confirmed
that MAIW's package-level safety architecture holds (authority boundary,
deny-by-default capability policy, SOP Engine validation, approved
Nemotron 3 / 3.5 family policy, live OpenShell isolation) but found five P1
gaps between those packages and **what the shipped application
(`maiw_api.app:app`) actually composes**. v2.0.1 closes those gaps on the
canonical app. Details and evidence:
`docs/audits/MAIW_V2.0.1_REMEDIATION_AUDIT.md`,
`artifacts/audit/v2.0.1_remediation.json`.

## Changes

### Canonical app alignment
- `apps/api/maiw_api/app.py` is the only release composition root. The
  start script, smoke test, status script, runbook, Dockerfile and
  qualification all target `uvicorn maiw_api.app:app`. `src/api/app.py` is a
  legacy development server only.

### Chat / write-path governance (audit P1-01)
- Legacy `POST /api/v1/chat` (LLM agent → ToolDiscoveryService → direct SQL
  `assign_equipment`) and `/api/v1/reasoning/*` are **no longer mounted**.
  Use `POST /api/v1/copilot/turn`.
- Legacy routers (inventory, WMS, IoT, ERP, scanning, attendance,
  migrations, forecasting, training) and the operations/safety SQL routers
  are mounted **read-only**. The only mutating routes are governed
  (proposal → DecisionEngine → ActionExecutor), demo-mode simulation
  controls, the bounded inference endpoint, identity management and
  document-workflow state — enforced by an exact route-inventory test.

### Inference endpoint (audit P1-02)
- `POST /api/v1/inference` is served by the canonical app on the API port
  (8001). There is no separate `:8020` server. Point
  `MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT` at `http://<HOST_IP>:8001/api/v1/inference`.
- Forbidden routing fields now return 422 (were 500); unknown fields are
  rejected with 422 (were silently ignored).

### Durable runtime wiring (audit P1-03)
- `maiw_api.persistence` builds `JsonFileProcedureStateStore` and
  `JsonFileGovernanceInbox` from `MAIW_PERSISTENCE_ROOT` (default
  `/var/lib/maiw`) at startup; `MAIW_PERSISTENCE_MODE=memory` is an explicit
  development/test opt-in.
- `maiw_api.procedure_host.ProcedureHost` binds the SOP Engine to those
  stores: procedures, revisions and retry/loop counters survive restart;
  governance outcomes are applied once and redeliveries are dropped, also
  across restarts. `GET /api/v1/procedures` is a read-only view.

### Readiness (audit P1-04)
- `GET /api/v1/ready` returns 503 `NOT_READY` with `failed_components` when
  persistence, ModelGateway, the governed write path, MCP domains or (outside
  demo mode) the database are unavailable. Provider and sandbox state are
  reported but not critical. Liveness is unchanged.

### Document pipeline through ModelGateway (audit P1-05)
- Every document model call goes through ModelGateway with an explicit
  modality; no provider URL, key or model id in the document path.
- Vision steps require an approved multimodal Nemotron model; with none
  enabled, documents fail with a typed `MODEL_UNAVAILABLE`. The approved
  family set was **not** widened.
- All mock / synthetic paths are removed. A provider, credential, eligibility
  or malformed-reply failure is a typed failure — never mock data, never a
  synthetic `APPROVE`. The judge's `decision` is labelled a model quality
  classification, not a governance approval.

### Operations and UI
- Lifecycle scripts: preflight disk check on a fresh root, stop script no
  longer kills processes by name pattern, restart/qualify count waiting
  procedures correctly.
- UI: `tsc --noEmit` error fixed and typecheck added to CI; non-breaking
  `npm audit fix` (critical 3 → 0, high 62 → 50; remaining highs are in the
  react-scripts build/test/dev-server toolchain).

## Upgrade notes
- Clients of `/api/v1/chat`, `/api/v1/reasoning/*` or legacy write routes
  must move to the governed APIs; those routes return 404/405.
- Sandbox endpoint moves from `:8020` to the API port.
- Ensure `MAIW_PERSISTENCE_ROOT` is writable by the service user, or
  `/api/v1/ready` will report `persistence` failed. For local development
  either set a writable root or `MAIW_PERSISTENCE_MODE=memory`.
- If the hosted endpoint does not serve a registry default model (e.g.
  `nvidia/nemotron-3-nano-30b-a3b` currently returns 410), disable that role
  (`NEMOTRON_NANO_ENABLED=false`); routing stays within the approved family.
- The document vision stage is unavailable until an approved multimodal
  Nemotron model is configured (`NEMOTRON_NANO_OMNI_MODEL`,
  `NEMOTRON_NANO_OMNI_ENABLED=true`).

## Test baseline
- Python CORE CI command: **2720 passed, 0 failed, 5 skipped** (two
  consecutive runs; v2.0.0 baseline 2667/0/3 + 53 canonical-app tests; the 2
  new skips are opt-in Postgres tests, run and passed locally against a
  disposable database).
- UI: Jest **963/963 (39 suites)**, ESLint **0 errors** (1041 warnings),
  `tsc --noEmit` **0 errors**, production build OK.
- Live (epg-tme-smc-h100-02, fresh sandbox, canonical app only): smoke
  13/13, `tests/real_sandbox` 51/51, Proof SOP A to WAITING_FOR_GOVERNANCE
  with approved Nemotron 3 Super through the sandbox, restart and governance
  replay, readiness and document failure injection — see the remediation
  audit.
