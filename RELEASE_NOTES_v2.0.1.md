# MAIW v2.0.1 — Release Notes (DRAFT — not tagged)

**Status:** release candidate after remediation round 3, pending a FOURTH
independent re-audit. Do not tag until that re-audit passes. `v2.0.0`
(`816ace73…`) is unchanged. The third independent re-audit (frozen candidate
`86f3004`) confirmed the nine earlier P1s closed and found two new P1s
(NEW3-P1-01, NEW3-P1-02) plus two release-critical gaps (N-1, N-2) and the
missing gateway step (N-9); round 3 addresses them — see "Round 3" below,
`docs/audits/MAIW_V2.0.1_REMEDIATION_ROUND3.md` and
`artifacts/audit/v2.0.1_remediation_round3.json`. Earlier rounds:
`docs/audits/MAIW_V2.0.1_REMEDIATION_ROUND2.md`,
`docs/audits/MAIW_V2.0.1_REMEDIATION_AUDIT.md`. This is a draft, not a PASS
claim.

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

## Round 3 (third re-audit: NEW3-P1-01, NEW3-P1-02, N-1, N-2, N-9)

### Sandbox / operational-write authentication boundary (NEW3-P1-01)
- Governed operational writes (`POST /api/v1/equipment/assign|release|maintenance`,
  and the new `/api/v1/executions` routes) require a **separate operator write
  credential** — `MAIW_OPERATOR_WRITE_TOKEN`, sent as `X-Maiw-Operator-Token`.
  It is checked (constant time) as a route dependency, before the body is read
  and before any agent, DecisionEngine, ActionExecutor or MCP call: no header →
  403 `OPERATOR_WRITE_CREDENTIAL_REQUIRED`, wrong value (including the
  sandbox's inference token) → 401 `INVALID_OPERATOR_WRITE_CREDENTIAL`, no usable
  token configured (unset, short, placeholder, or equal to the inference
  token) → 503 `OPERATOR_WRITE_AUTH_NOT_CONFIGURED`. A JWT user session alone
  never authorises a write. The DecisionEngine stays the authority decision
  after authentication.
- The sandbox holds only the inference token. `reference_sandbox.sh probe`
  fails unless every governed write is denied for every credential the sandbox
  holds and no host secret (operator token, provider key, DB password, JWT
  secret) is present in the sandbox environment (digest comparison).
- The OpenShell policy now uses an L7 REST rule: on the API host:port the
  sandbox may only send `POST /api/v1/inference` (was `access: full`). The
  application-layer credential check remains the authority boundary even if
  the policy is broadened (verified live with a deliberately broad policy).
- Executors are built only when the profile offers governed writes; in
  `reference` (even with an MCP URL set) the write routes answer 503
  `GOVERNED_WRITES_NOT_OFFERED`, matching readiness `not_offered`.
  `reference_governed` readiness requires the operator credential.
- UI: the browser never holds the credential; write failures are shown. A
  localhost-only development console may let the CRA dev proxy add it
  server-side (`MAIW_UI_OPERATOR_WRITE_TOKEN`, opt-in).

### Ambiguous MCP writes are UNKNOWN and reconciled in every profile (NEW3-P1-02)
- The MCP client records the dispatch phase of every failure: connect /
  handshake / open circuit → not dispatched (definite `failed`,
  `error_code=MCP_NOT_DISPATCHED`); anything after `tools/call` was sent
  (connection reset, server crash, read timeout, unreadable answer) →
  **`unknown`**, never "failed". The equipment routes return `202
  status=unknown executed=null reconciliation_required=true`.
- No blind retry: while a write to an asset is unresolved, every further
  write to it is refused with 409 `RECONCILIATION_REQUIRED` before any
  proposal, decision or write — also across restarts: a durable execution
  journal (`$MAIW_PERSISTENCE_ROOT/executions/`) is written before the MCP
  request is sent, and a write in flight when the process died reloads as
  UNKNOWN.
- Reconciliation outside demo mode: `POST /api/v1/executions/{id}/reconcile`
  (operator credential) re-reads authoritative state through the MCP read
  path → `confirmed_executed` / `confirmed_not_executed` / `indeterminate`,
  keeping the original execution, proposal, decision and trace identity.
- The MCP write tools forward `execution_id` to the backend (it was null).

### Provider identity fails closed (N-1)
- A provider answer with no / empty / non-string `model` is discarded: 502
  `MODEL_IDENTITY_UNVERIFIABLE`. A successful inference is always
  `identity_verified=true`.

### Routing-aware response cache (N-2)
- The NIM response cache key covers the exact prompt (no timestamp / UUID /
  date stripping), the dispatched physical model, the thinking mode and
  budget, and the routing intent (reasoning level, risk level, modality,
  role, generation). HIGH and LOW (and HIGH and MEDIUM) requests never share
  an entry.

### Reproducible OpenShell gateway (N-9)
- `scripts/setup/reference_gateway.sh start|status|stop` starts (managed:
  this deployment's own gateway on loopback with its own namespace, network,
  JWT key and state) or verifies (external) the gateway, and the runbook's
  clean-host procedure and reboot recovery use it.

### Round 3 test baseline (last code commit `608222f`)
- Python CORE CI: **2865 passed, 8 skipped, 0 failed** (two fresh runs; GitHub
  CI identical), and 0 failures in 11 alternative orders (pairwise
  permutations, reversed, ModelGateway / reliability / canonical / round-3
  first, two seeded shuffles). 60 new round-3 tests.
- UI: Jest 968/968, ESLint 0 errors, `tsc --noEmit` 0 errors, build OK
  (without `CI=true`); npm audit 0 critical / 50 high (toolchain only; no
  production-reachable high).
- Live (epg-tme-smc-h100-02, remediation-owned gateway, sandbox, DB, MCP
  backend): clean-shell runbook incl. the gateway step, full preflight 32/0
  with no skip, smoke 17/17 before and after restart; sandbox writes denied
  (proxy 403; app 403/401 with a deliberately broad policy; 0 DecisionEngine,
  0 MCP writes); MCP lost response → UNKNOWN → 409 → reconcile
  CONFIRMED_EXECUTED with exactly one write (also across `kill -9`); hosted
  Super and Lightning identity verified from the sandbox. Details:
  `docs/audits/MAIW_V2.0.1_REMEDIATION_ROUND3.md`.

## Round 2 (re-audit PR #144: NEW-P1-01..04, P2-01, P2-02)

### Final physical model enforcement (NEW-P1-01)
- One canonical approved-deployment table (`maiw_models/deployment.py`)
  binds each role to its physical model ID and generation; a small
  `DeploymentResolver` sits between PolicyFilter and provider dispatch and is
  the only source of the model ID the provider receives. The approved family
  stays Nemotron 3 / 3.5.
- `NEMOTRON_<ROLE>_MODEL` can only select the approved ID for that role.
  Anything else (unknown, look-alike, another role's ID) → `503
  MODEL_POLICY_VIOLATION` with zero provider calls, `/api/v1/ready` NOT_READY,
  preflight FAIL. `LLM_MODEL` / `MAIW_NIM_MODEL` are not dispatched.
- A provider that reports a different model than the one dispatched → `502
  MODEL_IDENTITY_MISMATCH`; the response is discarded, never relabelled. The
  inference route reports `provider_reported_model_id` and `identity_verified`.
- Preflight, smoke and status check the exact bindings the runtime
  dispatches (`scripts/lib/check_model_config.py`, same registry + resolver).
- Nano is disabled by default (hosted `nvidia/nemotron-3-nano-30b-a3b`
  returns HTTP 410); MEDIUM reasoning is served by Super (`fallback_used`).

### Reproducible reference deployment (NEW-P1-02, P2-01)
- One env loader for every lifecycle script, loaded before preflight;
  values parsed, never executed.
- Deployment identity (`runtime/maiw-api.instance`, `MAIW_INSTANCE_ID` on
  `/api/v1/live`): status/smoke/restart/stop act only on the verified
  instance; no `localhost:8001` fallback, no kill-by-port or kill-by-name.
  Restart preflights before stopping.
- New `scripts/setup/reference_db.sh`, `scripts/setup/reference_sandbox.sh`
  (committed OpenShell policy template: egress only to the API host:port),
  `scripts/validate_reference_runbook.sh`; the runbook lists every command of
  a clean-host deployment in order. `MAIW_API_PORT`, `MAIW_PERSISTENCE_ROOT`,
  `MAIW_PYTHON` are required (no defaults).

### Capability-aware readiness (NEW-P1-03)
- Deployment profiles `reference` (governed writes not offered),
  `reference_governed` (required MCP write domains must be configured,
  reachable and not circuit-open) and `demo`.
- MCP domains report READY / DEGRADED / CIRCUIT_OPEN / FAILED /
  NOT_CONFIGURED — never HEALTHY when unconfigured. Sandbox is critical when
  `MAIW_SANDBOX_MODE=required`. Readiness probes the data-path database
  (`PGHOST`/`PGPORT`), not `DATABASE_URL` (P2-19).

### Order-independent test isolation (NEW-P1-04)
- The CORE CI suite passes in CI, reversed, ModelGateway-first, demo-first,
  canonical-first, reliability-first and seeded shuffled file orders
  (event-loop misuse, sys.modules purges, in-place module reloads and
  unrestored globals fixed; documented singleton/env reset fixture;
  `PYTHON_DOTENV_DISABLED=1` in tests).

### Crash-safe governance resume (P2-02)
- The governance inbox persists the accepted outcome and an applied marker;
  `ProcedureHost.recover_accepted_governance` replays an accepted-but-unapplied
  resume exactly once after a crash and never re-runs one that already
  completed. Startup and `/api/v1/ready` report unapplied outcomes.

### Round 2 test baseline (last code commit `9c27c12`)
- Python CORE CI: **2805 passed, 8 skipped, 0 failed** (two fresh runs), and
  0 failures in 11 alternative orders (reversed, ModelGateway/demo/canonical/
  reliability first, two seeded shuffles). 87 new round-2 tests.
- UI: Jest 964/964, ESLint 0 errors, `tsc --noEmit` 0 errors, build OK
  (without `CI=true`; with it react-scripts turns the lint warnings into
  errors — CI does not run the build); npm audit 0 critical / 50 high
  (toolchain only).
- Live (epg-tme-smc-h100-02): clean-shell runbook reproduction; smoke 14/14
  before and after restart; Super, Lightning and in-sandbox inference with
  provider-reported model == resolved approved model. Host GPU driver
  mismatch: preflight GPU check fails (correctly), so start/restart used
  `--skip-preflight`.

## Changes (round 1)

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
  (`MAIW_API_PORT`; no default is assumed since round 2). There is no separate
  `:8020` server. Point `MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT` at
  `http://<HOST_IP>:<MAIW_API_PORT>/api/v1/inference`.
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
  demo mode) the database are unavailable. Provider state is reported but
  not critical; since round 2 the sandbox is critical when
  `MAIW_SANDBOX_MODE=required`. Liveness is unchanged.

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

## Known limitations (v2.0.1 candidate)
- `POST /api/v1/document/upload` and the legacy read routes are
  unauthenticated, rate limiting does not enforce, and a chunked upload can
  exceed the size limit; the API binds `MAIW_API_HOST` (`0.0.0.0` in
  `.env.example`). Run the reference deployment on a trusted network only.
- There is no HTTP route to start a procedure or submit governance;
  `ProcedureHost.recover_accepted_governance` has no production caller.
- `reference_governed` needs working MCP servers; the runbook does not ship a
  launch command for them.
- The managed OpenShell gateway is loopback-only with TLS off (single-node
  reference); use an external mTLS gateway on shared multi-user hosts.
- The execution journal and the unresolved-target guard are single-node.
- The legacy `src/api/services/llm/nim_client.py` (not used by the canonical
  ModelGateway path) keeps its old cache key.

## Upgrade notes
- Round 3: profile `reference_governed` requires `MAIW_OPERATOR_WRITE_TOKEN`
  (fresh, >= 32 chars, different from the inference token); callers of the
  equipment write routes must send `X-Maiw-Operator-Token`. Clients must
  handle `202 status=unknown` and `409 RECONCILIATION_REQUIRED`.
- Round 3: set `OPENSHELL_GATEWAY_ENDPOINT` and the
  `MAIW_OPENSHELL_GATEWAY_*` variables; run `reference_gateway.sh start`
  before creating the sandbox. Recreate sandboxes created under the round-2
  policy (`access: full`) so they get the L7 rule.
- Clients of `/api/v1/chat`, `/api/v1/reasoning/*` or legacy write routes
  must move to the governed APIs; those routes return 404/405.
- Sandbox endpoint moves from `:8020` to the API port.
- Ensure `MAIW_PERSISTENCE_ROOT` is writable by the service user, or
  `/api/v1/ready` will report `persistence` failed. For local development
  either set a writable root or `MAIW_PERSISTENCE_MODE=memory`.
- Nano is disabled by default (round 2). Re-enable it only with a working
  deployment of `nvidia/nemotron-3-nano-30b-a3b` (`NEMOTRON_NANO_ENABLED=true`).
- `NEMOTRON_<ROLE>_MODEL` must be unset or the approved ID for that role;
  any other value now fails closed.
- The document vision stage is unavailable: no multimodal Nemotron model is
  in the approved deployment table, so configuring `NEMOTRON_NANO_OMNI_MODEL`
  does not enable it (it fails closed). Adding one is a reviewed code change.
- Lifecycle scripts now require `MAIW_API_PORT`, `MAIW_PERSISTENCE_ROOT`,
  `MAIW_PYTHON` and `MAIW_DEPLOYMENT_PROFILE` in `.env`; see the runbook's
  clean-host procedure.
- `/api/v1/ready` in the `reference` profile reports
  `governed_write_path: not_offered`; use `reference_governed` with the MCP
  write domains configured to offer governed writes.

## Test baseline (round 1 — superseded by round 2, see the round-2 audit)
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
