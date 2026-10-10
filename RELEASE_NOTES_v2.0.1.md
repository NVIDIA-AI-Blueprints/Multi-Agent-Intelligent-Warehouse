# MAIW v2.0.1 — Release Notes (DRAFT — not tagged)

**Status:** release candidate after remediation round 2, pending a THIRD
independent re-audit. Do not tag until that re-audit passes. `v2.0.0`
(`816ace73…`) is unchanged. The second independent re-audit (PR #144) failed
the round-1 candidate `785c420` with four new P1s; round 2 addresses them —
see "Round 2" below, `docs/audits/MAIW_V2.0.1_REMEDIATION_ROUND2.md` and
`artifacts/audit/v2.0.1_remediation_round2.json`. This is a draft, not a
PASS claim.

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
- UI: Jest 964/964, ESLint 0 errors, `tsc --noEmit` 0 errors, build OK;
  npm audit 0 critical / 50 high (toolchain only).
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
