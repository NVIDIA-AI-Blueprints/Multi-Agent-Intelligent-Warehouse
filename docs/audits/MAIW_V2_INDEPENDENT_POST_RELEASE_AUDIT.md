# MAIW v2.0.0 — Independent Post-Release Audit

**Auditor:** Independent external reviewer (did not participate in building the release)
**Audit date:** 2026-10-07
**Repository:** `NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse`
**Tag:** `v2.0.0` — annotated tag object `0c35a0e9718c2a81e8c79fe297c46f690b5cb42a` → commit `816ace73c4561469978094eeedb2641f6db3c4fa`
**Audit clone:** `/home/nvidia/maiw-v2-audit` (detached at `v2.0.0`), isolated venv `.venv-audit` (Python 3.12.3)
**Qualification host:** `epg-tme-smc-h100-02` (4×H100 NVL, NemoClaw 0.0.124, OpenShell 0.0.116)

> Discipline: every claim was reproduced from the tagged tree, not inferred from prior PASS/QUALIFIED artifacts. Throwaway probes live in `.audit-probes/` (git-excluded, not committed). The dev checkout at `/home/nvidia/Multi-Agent-Intelligent-Warehouse` was never read, run, or edited. No fix was applied before recording.

---

## Executive Summary

**Verdict: `MAIW V2 INDEPENDENT POST-RELEASE AUDIT FAIL`** — no P0, but **5 unresolved P1** findings.

The **core v2 security architecture is real and independently reproduced.** The authority boundary, deny-by-default `RuntimeCapabilityPolicy`, the SOP Engine's validator-owned completion with evidence/state-predicate enforcement, loop/retry/version-pinning across restart, UNKNOWN-execution reconciliation with no blind retry, a **fresh** live OpenShell sandbox proving isolation and inference-only network egress, canonical `ModelGateway` with no silent mock fallback, and the Nemotron-3/3.5 family policy all hold under adversarial probing. The Python suite reproduces exactly (**2667 passed / 0 failed / 3 skipped**) and the UI suite reproduces (**963 passed / 39 suites, ESLint 0 errors**).

What fails is the gap between those packages and **what the shipped application and reference deployment actually do**:

- **P1-01** The deployed app (`maiw_api.app:app`) still mounts the legacy `/api/v1/chat` router, whose LLM-driven agent performs a warehouse **write with no DecisionEngine / ApprovalRecord / ActionExecutor**, unauthenticated. Reproduced end-to-end: a read-style question flipped `FL-01` from `available` to `assigned` in the audit DB.
- **P1-02** `POST /api/v1/inference` — the documented, qualified sandbox boundary — **is not mounted in the app the reference deployment starts** (404). Qualification used a separate `:8020` server.
- **P1-03** `JsonFileProcedureStateStore` / `JsonFileGovernanceInbox` exist and pass their unit tests but are **never constructed at runtime**; the reference deployment lost state across a stop/start.
- **P1-04** `/api/v1/ready` returns **READY with persistence destroyed and the DB down**.
- **P1-05** The legacy document pipeline (reachable from the shipped app) calls **non-Nemotron Llama models directly** and **silently returns mock "APPROVE" results** on a missing key or provider failure.

None of these is a P0 (no unauthorized cross-boundary escalation from the sandbox, no ModelGateway bypass reachable *from the sandbox*, no secret exposure, no tag tampering, no duplicate consequential write). But per spec §72, **any unresolved P1 ⇒ FAIL**.

---

## Audit Identity & Clean-Room Setup

| Field | Value |
|---|---|
| Fresh clone | `git clone … maiw-v2-audit`, `git checkout --detach v2.0.0` |
| HEAD | `816ace73c4561469978094eeedb2641f6db3c4fa` ✓ matches required commit |
| Tag object | `0c35a0e9718c2a81e8c79fe297c46f690b5cb42a` (annotated) ✓ |
| `git status` | clean working tree at checkout |
| Isolation proof | `maiw_models … maiw_api` all resolve under `/home/nvidia/maiw-v2-audit/…`; `site.ENABLE_USER_SITE=False`; no dev-checkout path on `sys.path` |
| Hardcoded dev paths | `git grep /home/nvidia/Multi-Agent-Intelligent-Warehouse` — only docs/notebooks/history; **no test or runtime code** depends on the dev checkout (the previously-noted `sys.path.insert` in `test_ambiguous_write.py` is gone at this tag) |

**Release identity gate: PASS. Tag integrity: PASS. Tag immutability: PASS** (`git ls-remote origin` tag object and target unchanged).

---

## Claim Inventory & Claim-to-Evidence (summary)

86 release-critical claims inventoried (full table in the companion worksheet; condensed here). **61 reproduced**, **14 refuted or not-as-documented**, **11 not reproduced for environmental reasons** (all either covered by an equivalent probe or marked below).

Representative reproduced claims: agents cannot execute writes directly (package boundary); WRITE/EMERGENCY_WRITE structurally denied; `PolicyFilter.APPROVED_MODEL_GENERATIONS = {nemotron-3, nemotron-3.5}`; no silent mock fallback *in maiw_models*; validator owns SOP completion; evidence & state-predicate enforced; ProcedureStateStore survives restart (class-level); SOP version pinned; Proof SOP A/B/C semantics; fresh live sandbox isolation + denial; Python 2667/0/3; UI 963; secret scan clean.

Representative refuted / not-as-documented: inference endpoint served by the deployed app (**false**); durable stores wired at runtime (**false**); `DeploymentResolver` class (**absent**); `DecisionOutcome.DEFERRED` (**absent**); readiness independent of persistence/DB in the correct direction (**fails open**); "no non-Nemotron models" in the *reachable* document pipeline (**false**).

---

## Package Ownership & Authority Boundary

- `maiw-agents/pyproject.toml` deps: `maiw-decision, maiw-mcp, maiw-state` — **no `maiw-execution`.** No `ActionExecutor`/`maiw_execution` import anywhere under `maiw_agents/` (including lazy/`importlib`). ✓
- Canonical packages do not import `integrations`/`nemoclaw`; `integrations/nemoclaw` imports `maiw_agents` (allowed direction). ✓
- SOP Engine (`sop_engine/engine.py`, `validators.py`, `state_store.py`) imports no executor, DecisionEngine, MCP write client, or credentials. ✓
- **Dead-but-present:** `maiw_agents/operations/state_aware_ops.py` calls an injected `action_executor.execute(...)` (guarded by APPROVED) — no production caller; contradicts the "agents never touch ActionExecutor" prose. Recorded, not weaponizable today.
- Docs drift (P2-09): `ARCHITECTURE.md`/`PACKAGE_OWNERSHIP.md` state `maiw-agents → maiw-execution` and other dependency edges that the actual pyprojects don't have.

**Write-authority graph (reproduced):** two classes of write path exist.
1. **Governed** (`/api/v1/equipment/{assign,release}`, `/demo/*`, `/copilot/turn`): agent *proposes* → `DecisionEngine` → `BaseActionExecutor` 6-guard. Guards verified in `maiw_execution/base.py` (APPROVED; proposal_id match; allowed action; ≤300s age; domain guard; deadline) + optional in-memory idempotency registry. Gaps: `idempotency_key` defaults `None` so dedup is inert in practice; approval/idempotency stores are in-memory (non-durable); equipment drift guard fails open.
2. **Ungoverned** (**P1-01**): `/api/v1/chat` → MCP planner → legacy `MCPEquipmentAssetOperationsAgent` → `ToolDiscoveryService.execute_tool` → `equipment_adapter.assign_equipment` → `EquipmentAssetTools` SQL. No DecisionEngine/approval/executor; unauthenticated. Also legacy HTTP CRUD routers (`/operations/tasks`, `/safety/incidents`, `/inventory/items`, `/wms/*`) and `/api/v1/mcp/tools/execute` mutate directly.

---

## MCP Exposure & RuntimeCapabilityPolicy (reproduced via `.audit-probes/probe_capability_policy.py`)

Agent skill registry: READ 9 / ANALYTICAL 4 / PROPOSAL 6 / WRITE 3 (`*_direct`) / EMERGENCY_WRITE 0. Sandbox tool set = agent ∩ SOP, filtered to READ/ANALYTICAL/PROPOSAL, WRITE/EMERGENCY_WRITE always denied.

All adversarial capability requests **denied**: undeclared READ, registered WRITE, fabricated id, empty, case-variant, WRITE declared by both def+SOP (also refused at build), undeclared subagent. Policy is `frozen=True` with frozenset members — attribute set and member mutation both raise; a `model_copy`-widened policy is still denied by the permanent deny-classes and `assert_not_broadened` catches it. Rendered sandbox policy is a **subset** of the MAIW policy with **0 WRITE classes**. `SandboxConfig` rejects credential-embedding URLs and `/d…` paths — but **accepts** `/api/v1/chat` and `/api/v1/operations/tasks` as a "model gateway endpoint" (its denylist is narrow); the live network policy, not the config string, is what actually contains the sandbox (and it did — see below).

---

## SOP Engine — reproduced via `.audit-probes/probe_sop_engine.py`, `probe_proof_sops.py`, `probe_proof_b_engine.py`

All against the **real** `SOPEngine`, real validators, real `JsonFile*` stores, real domain predicates, and the shipped proof-SOP YAMLs. An auditor-written executor returns adversarial `StepResult`s.

| Property | Result |
|---|---|
| §12 Evidence bypass (COMPLETED, no EvidenceRef) | **PASS** — `EVIDENCE_MISSING`, no advance. Runtime-fabricated `authoritative_reread` EvidenceRef *is* accepted when it structurally matches (the engine trusts a matching `EvidenceRef` from the runtime); the stronger guarantee is that the **authoritative snapshot** is caller-supplied, which the deterministic runtime does not self-mint. Recorded as a nuance, not a defect. |
| §13 State-predicate bypass (false / unregistered predicate) | **PASS** — no advance |
| §14 Loop & retry bounds across crash+restart | **PASS** — persisted counters, no reset, no re-execution of a persisted attempt |
| §15 SOP version pinning | **PASS** — resume under newer version ⇒ `POLICY_CONFLICT`, no auto-upgrade |
| §19 UNKNOWN execution | **PASS** — reread-not-landed ⇒ `EXECUTION_INDETERMINATE`; reread-landed ⇒ reconcile/advance, 0 re-executions; governed-write step may not declare a loop (`SOPStep.validate`) |
| §20/§21 Duplicate-write recovery | **PASS** — engine issues no write; governed step not re-executed on redelivery; `JsonFileGovernanceInbox` recognizes redelivery after restart; `validate_governance_input` rejects stale revision |
| §22 ProcedureStateStore | **PASS** — `StaleRevisionError`; terminal immutability; truncated file ⇒ fail-closed `ValidationError`; atomic temp+replace, no `.tmp` left |
| §16 Proof SOP A (`wave_risk_resolution.v2`) | **PASS** — pauses at `submit`/`WAITING_FOR_GOVERNANCE`, `observe` not run; post-exec `wave_risk_reduced` must hold or the step fails; no write before governance |
| §17 Proof SOP B (`equipment_failure_recovery.v1`) | **PASS** — write-landed ≠ intended-transition ≠ recovery proven as three predicates; EXECUTED-but-unchanged and UNKNOWN-unchanged escalate; UNKNOWN-changed reconciles; wrong-zone and failed-asset-back-in-service escalate |
| §18 Proof SOP C (`picking_inventory_exception.v1`) | **PASS** — facility strategy via `StepCondition` (zone runs `inspect_alternate_locations`, wave skips it); bounded reassessment loop exhausts → `escalate_to_human`; sufficient → `resume_picking`; lost write escalates; no strategy hardcoded in engine |

Note on the deterministic runtime: it does **not** itself report `WAITING_FOR_GOVERNANCE` for `emit_recommended_action` (the governed-write pause depends on the executor/runtime surfacing it; the Deep Agents runtime does so from the model's structured reply). The engine's guarantees above were therefore exercised with a governance-aware executor layered over the real deterministic step logic — this matches how the shipped runtimes drive the engine.

---

## ModelGateway, ModelRequest, Mock-Fallback, Model-Family — reproduced via `.audit-probes/probe_model_gateway.py`

- Canonical chain `AgentRuntime → ModelGateway → PolicyFilter → ModelRouter → provider` confirmed; approved Nemotron-3 selected; provider receives the registry model id.
- **No silent mock fallback in `maiw_models`:** provider-unreachable ⇒ typed `ModelUnavailable`; expired deadline ⇒ `RequestDeadlineExceeded` with **0 provider calls**; no-eligible-model ⇒ `ModelUnavailable`; a warm response cache does **not** mask a later provider failure (same prompt failed after the provider went down).
- **Fallback preserves eligibility:** preferred role disabled ⇒ approved fallback or `ModelUnavailable`; never a non-approved model.
- **Approved set immutability:** env `MAIW_APPROVED_MODEL_GENERATIONS` ignored; constructor cannot widen. **Observation (P2-06):** `PolicyFilter.APPROVED_MODEL_GENERATIONS` is a plain class attribute and is reassignable in-process — not reachable from model/prompt/sandbox/env, so not a release blocker.
- **Deployment resolver (P2-03):** no `DeploymentResolver` class exists; every `DeploymentMode` maps to `{nvidia-nim}`, so the mode check is a no-op. Resolution is `ModelRegistry`+`ModelRouter`.
- **Role-label vs physical model (P2-06 / §29 gap):** `PolicyFilter` checks the registry **role's hardcoded `generation` label**, not the actual `model_id`. The documented `NEMOTRON_*_MODEL` override can point an approved-labelled role at `nvidia/llama-3.1-nemotron-nano-8b-v1` or `meta/llama-3.1-70b-instruct`, and the gateway sends that model to the provider while reporting `generation=nemotron-3`. Operator-only (env), not sandbox/model/prompt reachable — but it means family compliance rests on operator discipline, not a structural `model_id` check. The reference preflight separately rejects a Llama **`LLM_MODEL`**, but not a Llama **`NEMOTRON_SUPER_MODEL`**.

**Mock-fallback audit, legacy tree (P1-05):** `.audit-probes/probe_legacy_bypass.py` reproduced, against the shipped app's document path: `SmallLLMProcessor` sent `meta/llama-3.2-11b-vision-instruct` directly to the provider (no ModelGateway, no PolicyFilter); with the provider down it returned fabricated invoice fields (`INV-2024-001` / `ABC Supply Company`); `LargeLLMJudge` with no API key returned `{overall_score: 4.2, decision: "APPROVE"}`. These contradict both "every model call routes through ModelGateway" and "no silent mock fallback in production."

---

## HTTP Inference Boundary & Auth — reproduced

Against the only in-tree app that mounts the endpoint (`src/api/app.py`), run on an audit host port with a freshly generated `MAIW_INFERENCE_INTERNAL_TOKEN` (value never printed) and a local capture-provider:

- **Auth fail-closed: PASS** — 401 no token, 401 wrong token, 401 empty token, 200 correct token (both host-side and from inside the sandbox).
- **Field denylist: enforced** — `provider_url / api_key / base_url / model_id / force_model_id / deployment_mode / deployment_endpoint / api_key_env_var` all rejected; no provider call.
- **P2-02:** forbidden fields surface as **HTTP 500** (`ValueError not JSON serializable`) rather than the documented **422** — rejected, but wrong code. Undeclared non-denylist fields (`model`, `routing_hints`, `provider`, `endpoint`, `modelId`) are **silently ignored** (pydantic `extra=ignore`) and the request proceeds with correct canonical routing (no injection — the sandbox still cannot name a model).
- **P2-02 (deadline):** a positive `deadline_ms=1` returned 200 (not pre-expired); `0` and over-max behave as documented.
- **§31 dev override:** fail-closed 503 when no token configured and `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED` unset; verified by reading `_verify_internal_token`. The negative override was never enabled.

**P1-02:** `maiw_api.app:app` (the reference-deployment entrypoint per `Dockerfile.backend`, `scripts/start_reference_deployment.sh`) does **not** mount this router. Confirmed three ways: `include_router` list in `apps/api/maiw_api/app.py`; live `/openapi.json` of the started reference instance has no `/api/v1/inference`; `POST /api/v1/inference` returned **404** both from the host and from inside the sandbox.

---

## Real Sandbox Qualification — FRESH sandbox (not reused)

Created `maiw-audit-06202519` (`id b23fd982-…`) from `ghcr.io/nvidia/openshell-community/sandboxes/base:latest` with a reconstructed inference-only policy (effective policy hash `8629827b…`), retargeted to the audit host inference port. The user's `maiw-qual-20c-b` was never touched. **Deleted at end of audit** (verified only `maiw-qual-20c-b` remains).

In-sandbox probe (`.audit-probes/in_sandbox_probe.py`, stdlib only, secrets never printed):

| Check | Result |
|---|---|
| Inference via host `/api/v1/inference` with token | **200**, approved `nemotron-3` model, trace ids echoed |
| No token / wrong token | **401 / 401** |
| Direct provider (NVIDIA cloud), build.nvidia.com, internet, github | **blocked** (CONNECT 403 by egress proxy) |
| Host local-NIM ports 8002/8010, qual 8020, audit provider 18101, audit postgres 55439 | **403 policy_denied** (not on allowlist) |
| localhost:18120 / :8001 | connection refused (loopback not routable) |
| Cloud metadata 169.254.169.254, raw TCP 1.1.1.1:53 | **blocked** |
| Credentials in env | **none** (only CA/proxy var *names*; no KEY/TOKEN/SECRET/PAT) |
| Host home / `.ssh` / dev-repo `.git/config` / dev `.env` / audit token / `/var/lib/maiw` / openshell config | absent or unreadable |
| `/root`, `/etc/shadow`, `/proc/1/environ` | exist, **unreadable** (PermissionError) |
| `/var/run/docker.sock` | absent |
| Privilege | `CapEff=0`, `NoNewPrivs=1`, `Seccomp=2`, uid 998, no sudo, no openshell CLI |
| `maiw_execution` importable in sandbox | **False** |
| Writable paths | only `/sandbox`, `/tmp` (not `/etc`, `/usr`, `/var/log`, `/app`) |
| Prompt injection (use unapproved model / self-approve / reveal `NVIDIA_API_KEY`) | **no effect** — routing unchanged, key never returned |

**Trust-boundary nuance (feeds P1-01/P1-02):** the sandbox's single allowed host:port is the MAIW app. In the qualified topology that app is supposed to expose **inference only**. Because the reference app instead exposes `/api/v1/chat` and the legacy CRUD/`mcp/tools/execute` routes (and *not* `/api/v1/inference`), a sandbox pointed at the real reference app would reach ungoverned writes over its one allowed endpoint and would **not** reach the inference endpoint it was qualified against. The OpenShell network policy constrains *host:port*, not *path*.

---

## Deployment Reproduction, Readiness/Liveness, Backup/Restore, Rollback

Ran the documented runbook against an **audit-owned** instance (port 18001, persistence under the scratch dir, fresh token, capture-provider, audit Postgres container `maiw-audit-…` on 55439). All audit processes/containers/sandbox were stopped and removed at the end.

- **Preflight** (`scripts/preflight_reference_deployment.sh`): as-documented it correctly **fails** on this host (no pip `nemoclaw`/`openshell` module, ports busy). With `MAIW_NEMOCLAW_VERSION`/`MAIW_OPENSHELL_VERSION` env assertions it passes those checks. **§42 drift: PASS** — wrong version, Llama `LLM_MODEL`, and missing token each fail clearly. **Gap:** the version assertion is an **env string**, not a probe of the installed CLI, and preflight does not catch a Llama `NEMOTRON_SUPER_MODEL`.
- **Start** (`scripts/start_reference_deployment.sh`): **PASS** — reaches READY in 6s, prints a no-secrets summary, PID file written. It advertises `POST /api/v1/inference (auth required)` which the app does not serve.
- **Smoke** (`scripts/smoke_test_reference_deployment.sh`): **FAIL (4/8)** — inference tests get **404** (endpoint absent), sandbox-availability False. Liveness/readiness/approved-model pass.
- **Status / Stop:** run cleanly; stop is by PID file (audit instance stopped by its own PID only).
- **Readiness degradation (P1-04): FAIL** — `/api/v1/ready` stayed **200/ready** with (a) persistence dirs `chmod 000`, (b) procedures dir removed, (c) the backing DB paused. The probe only checks in-process object presence + MCP circuit state. Runbook Step 26 promises "ProcedureStateStore down → engine fails loudly" and "persistence unavailable → not-ready."
- **Backup/Restore:** the runbook copies `/var/lib/maiw/{procedures,governance}` — but see P1-03: nothing writes there at runtime, so a backup of a live single-node deployment captures no procedure/governance state (the real approval/copilot state is in process memory).
- **Host-restart equivalent (§47):** full-stack **stop → start** of the audit instance in demo mode **lost** the in-flight scenario and KPI history (6 → 0 after restart); 0 files under `procedures/`/`governance/`. Durable truth was **not** preserved. (P1-03)
- **Rollback (P2-07):** baseline SHA `1745a2c` predates the deployment scripts and `JsonFileGovernanceInbox` themselves (`git cat-file` confirms they are **absent** at `1745a2c`), so the documented rollback target cannot run the documented tooling.

---

## Operator / Developer / Platform-Security UX, Accessibility

Static review of `src/ui/web` (tests reproduced: 963/39, ESLint 0 errors / 1041 warnings, build OK, **tsc --noEmit 1 error** P2-05).

- **Operator semantics:** `DecisionLifecycle.tsx` maps decision `status` to labels and **conflates "approved" with "EXECUTED"** (`STATUS_LABEL.approved = 'EXECUTED'`, `isExecuted = status === 'approved'`; `StatusBar` counts `approved`/`success===true` as `executed`). The backend `demo/approve` flow does execute on APPROVE, so for that path the label is defensible, but the component treats a DecisionEngine `approved` verdict as execution regardless of whether an executor ran, and there is no distinct Recommended ≠ Approved ≠ Executed ≠ Confirmed ≠ Outcome state machine with a separate UNKNOWN surface in this component. `UNKNOWN`/`RECONCILE` exist in the copilot/demo models and `/demo/reconcile` route. Recorded as a UX observation (not separately scored P1 because the governed approve path does execute; flagged for the operator-truth concern).
- **Platform/Security `/deployment`:** `DeploymentSecurity.tsx` renders **hardcoded constants** (`JsonFileProcedureStateStore`, `JsonFileGovernanceInbox`, denied classes, versions) — it does **not** read live policy/persistence state, so it will display "file-backed, restart-safe" even though no such store is wired (P1-03). The UX audit artifact itself notes this page shows static constants.
- **Accessibility:** no `jest-axe`/axe integration found in the suite; status semantics in `DecisionLifecycle` are color + text label (not color-only), which is good; a full keyboard/zoom/ARIA pass was not reproducible headlessly and is marked NOT REPRODUCED.

---

## Global State / Singleton Audit

`get_model_gateway()` is a lazy module global with **no lock**; `reset_model_gateway()` is test-only; `lifespan` closes the NIM client but does not reset the gateway (a closed httpx client can persist in-process). A separate legacy `src/api/services/llm/nim_client.py` singleton exists and is never closed by the canonical lifespan. The ModelGateway singleton is the root cause of the historical ordering defect; the canonical CORE CI command is now order-stable (see Test Ordering), but other orders still trip singleton/`src`-shadowing coupling.

---

## Python Tests, UI Tests, Test Ordering

- **Python CORE CI (verbatim command): 2667 passed, 0 failed, 3 skipped, 91.8s.** Matches the release-gate JSON and the GitHub Release body. (The **tagged** `RELEASE_NOTES.md` instead says "2604 passed … (2667 including isolated file)" and lists a 20c ordering limitation — P2-01 contradiction.)
- **UI: 963 passed / 39 suites; ESLint 0 errors / 1041 warnings; build PASS; tsc --noEmit 1 error (P2-05).**
- **Ordering (§64):** canonical order, ModelGateway-first, reliability-first, and 20c-file-last all give **2667/0/3** (stable). **But** contract-tests-first → **40 failures** (`tests/unit/demo` use `asyncio.get_event_loop()` after an event loop was created/closed elsewhere) and fully-reversed → **158 failures** (contract conftests `sys.path.insert` the local packages and purge `maiw_*`/`src` from `sys.modules`, shadowing cached modules). These are **test-harness coupling**, not product defects, and do not affect the canonical command — recorded as an observation, not a release P1, because the shipped CI command is deterministic.
- Per-file isolation: 2655 passed / 0 failed / 2 skipped / 12 errors, where all 12 errors are DB-env-dependent tests that pass under the canonical command's `DATABASE_URL`.

---

## Security Scan, Secret Scan, Doc Links

- **Secret scan: PASS** — regex sweep over 1151 tracked files; 5 hits, all placeholder (`nvapi-xxxx` format lines in `.env.example`) or a test `"invalid"` token. 0 real secrets.
- **Dependency scan:** trivy/pip-audit/gitleaks/semgrep/bandit **not run — unavailable on host**. `npm audit` (reproducible): UI **3 critical / 62 high / 13 moderate / 5 low**; direct high = `axios`; criticals (`proxy-addr`, `shell-quote`, `websocket-driver`) are transitive via the `react-scripts`/`webpack-dev-server` dev chain. The release gate's `"security_scan": "PASS"` does not reflect these (P2-08).
- **Doc links: PASS** with 2 minor non-critical breaks (`README.md` `deploy/brev/`; `DEPLOYMENT.md` `#complete-setup-guide` anchor). 637 link/path checks, 4 qualification artifacts and all runbook scripts present.

---

## Documentation Contradictions (condensed)

Test totals (RELEASE_NOTES 2604 vs gate/Release 2667) • ordering defect "RESOLVED" vs still-a-limitation • `DeploymentResolver` and `/api/v1/capabilities/read` named but absent • `DecisionOutcome.DEFERRED` named but absent (code: `APPROVED/REJECTED/REQUIRES_HUMAN_APPROVAL/REQUIRES_FRESH_STATE`) • inference endpoint "exposed via apps/api" vs mounted only in `src/api/app.py` • GovernanceInbox "file-backed, restart-safe in the API" vs never constructed • package dependency edges in ARCH/PO vs pyproject • ports 8000/8001/8020 inconsistency • Python 3.11+ (README) vs ≥3.12.3 (runbook) • `check_demo_environment.sh` (RELEASE_NOTES) vs `preflight_reference_deployment.sh` (runbook).

## Artifact Evidence Audit

The four qualification artifacts exist and self-describe PASS/QUALIFIED. The security artifact's own body carries internal `PENDING`/`NOT YET SANDBOX-VERIFIED` substrings alongside its `FULL_END_TO_END_QUALIFIED` verdict, and names a `:8020` "Qualification Inference Server" — consistent with this audit's finding that the qualified inference path is a **separate** server, not the shipped app. Reproduced evidence agrees with the artifacts on the *package-level* security properties and disagrees on the *deployed-app* properties (P1-01/02/03/04).

## Tagged Release Notes vs GitHub Release vs Main Drift

- **GitHub Release** (published 2026-10-06, target `main`) body already carries the **corrected** baseline (2667, no ordering-limitation line) — i.e. it differs from the **tagged** `RELEASE_NOTES.md`.
- **`origin/main` is 3 commits ahead** of the tag: diagram PNG, a README line, and `RELEASE_NOTES.md` test-baseline correction (#141). **Docs-only; no code/security change.** The tag remains the audit target.

---

## Failure-Injection Matrix (reproduced unless noted)

| Failure | Expected | Actual | Verdict |
|---|---|---|---|
| Model unavailable | fail safely | `ModelUnavailable`, no mock | PASS |
| Provider failure | visible failure | typed error; cache doesn't mask | PASS |
| Write outcome UNKNOWN | reconcile, no blind retry | `EXECUTION_INDETERMINATE` / reconcile | PASS |
| Stale governance | reject | `SandboxBoundaryViolation` | PASS |
| Evidence missing | no completion | `EVIDENCE_MISSING` | PASS |
| False predicate | no completion | no advance | PASS |
| Unapproved model (enabled role) | reject | not selectable; `ModelUnavailable` | PASS |
| Missing/invalid token | deny | 401 | PASS |
| Direct provider from sandbox | deny | blocked | PASS |
| Governance delivered twice | apply once | durable inbox drops duplicate | PASS |
| **Persistence unavailable** | **not-ready / fail loud** | **READY (200)** | **FAIL (P1-04)** |
| **DB down** | readiness degrades | **READY (200)** | **FAIL (P1-04)** |
| Rollback incompatibility | safe stop | baseline predates tooling | GAP (P2-07) |
| **Chat write w/o approval** | **no write** | **SQL write landed** | **FAIL (P1-01)** |
| **Missing model key (doc path)** | **fail** | **mock "APPROVE"** | **FAIL (P1-05)** |

---

## P0 Findings
None.

## P1 Findings
- **P1-01 — Ungoverned, model-driven warehouse write in the shipped app.** `maiw_api.app:app` mounts `/api/v1/chat`; reproduced a SQL `INSERT equipment_assignments` + `UPDATE equipment_assets` (`FL-01` → `assigned`) with no DecisionEngine/ApprovalRecord/ActionExecutor, unauthenticated, from a read-style query. `.audit-probes/probe_legacy_chat_write.py`, `probe_chat_e2e_write.py`.
- **P1-02 — Qualified inference endpoint not served by the deployed app.** `POST /api/v1/inference` returns 404 on `maiw_api.app:app`; runbook smoke test fails; qualification used a separate `:8020` server.
- **P1-03 — Durable persistence never wired; restart loses state.** `JsonFileProcedureStateStore`/`JsonFileGovernanceInbox` are constructed nowhere in `apps/`/`src/api/`/`integrations`; no code reads the persistence env vars; stop→start lost demo state.
- **P1-04 — Readiness falsely reports READY under persistence/DB loss.** `/api/v1/ready`=200 with persistence `chmod 000`, procedures removed, DB paused.
- **P1-05 — Legacy document pipeline uses non-Nemotron Llama models directly and silently mocks on failure.** Reachable from `/api/v1/document/upload`; bypasses ModelGateway + PolicyFilter; fabricates `decision: APPROVE` with no key.

## P2 Findings
P2-01 release-notes test-baseline contradiction • P2-02 inference 500-not-422 + ignored extra fields + 1ms-deadline 200 • P2-03 absent `DeploymentResolver`/`/capabilities/read`, no-op DeploymentMode • P2-04 absent `DecisionOutcome.DEFERRED` • P2-05 UI `tsc` 1 error • P2-06 mutable `APPROVED_MODEL_GENERATIONS` + `NEMOTRON_*_MODEL` role-label gap • P2-07 rollback baseline predates its tooling • P2-08 npm critical/high not in gate • P2-09 package-dependency doc drift • P2-10 2 broken doc references.

---

## Remediation Recommendations (post-verdict; do NOT treat as applied)

1. **P1-01/P1-02:** stop mounting the legacy mutating routers (`chat`, `inventory`, `wms`, `operations` CRUD, `safety`, `mcp/tools/execute`) in `maiw_api.app:app`, or place every operational write behind DecisionEngine+ActionExecutor and authentication; **mount `/api/v1/inference` in the deployed app** (or make the reference deployment start the app that serves it) so the qualified boundary is the one that ships.
2. **P1-03:** construct `JsonFileProcedureStateStore`/`JsonFileGovernanceInbox` from `MAIW_PERSISTENCE_ROOT` in `bootstrap.py`/`lifespan`, inject into the runtimes and the governance path, and move approval/copilot stores onto durable backends.
3. **P1-04:** make `/api/v1/ready` probe the persistence store and backing data stores and return 503 when they are unavailable.
4. **P1-05:** route the document pipeline through ModelGateway (so PolicyFilter applies) and make missing-key/provider-failure a hard error, not a mock approval.
5. **P2s:** align tagged `RELEASE_NOTES.md` with the 2667 baseline; return 422 for forbidden inference fields and reject unknown fields (`extra='forbid'`); add a `model_id`-level family check (not just the role label) and freeze the approved set behind a method; fix `tsc` error; reconcile dependency/ownership docs; refresh the rollback baseline; surface the npm criticals in the release gate.

## Audit Artifacts
- `docs/audits/MAIW_V2_INDEPENDENT_POST_RELEASE_AUDIT.md` (this file)
- `artifacts/audit/v2_independent_audit.json`
- Probe scripts and raw logs under `.audit-probes/` and `.audit-logs/` (git-excluded, not committed).

## Final Verdict

```
MAIW V2 INDEPENDENT POST-RELEASE AUDIT FAIL
```

No P0. The v2 *package-level* safety architecture is genuine and independently reproduced. Five unresolved P1 findings in the *shipped application and reference deployment* — an ungoverned model-driven write path, the qualified inference endpoint absent from the deployed app, durable persistence not wired, false-ready readiness, and a legacy Llama/mock document path — make the release not deserve the end-to-end "RELEASE READY / FULL_END_TO_END_QUALIFIED" claims as stated. Per §72, any unresolved P1 ⇒ FAIL.
