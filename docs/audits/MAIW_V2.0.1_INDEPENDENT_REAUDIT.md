# MAIW v2.0.1 Independent Re-Audit — PR #143 candidate `785c420`

**Verdict: `MAIW V2.0.1 INDEPENDENT RE-AUDIT FAIL`**

| | |
|---|---|
| Repository | NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse |
| Candidate | PR #143, `fix/v2.0.1-canonical-app-remediation` → `main` |
| Candidate head SHA | `785c420604c3b6a16d6e7531fcab2c73da43f67a` (start 2026-10-08T01:46Z and end of audit — unchanged) |
| Base SHA | `944507ec914665c6682d39b95e8713355f486598` |
| Host | `epg-tme-smc-h100-02` (shared qualification host) |
| Audit dates | 2026-10-08 → 2026-10-09 |
| Auditor stance | Independent. The remediation report, its JSON, CI status and live-proof claims were treated as claims, not evidence. No product code was modified. |

---

## 1. Executive Summary

All five original v2.0.0 P1s were independently reproduced as **closed** against the exact
candidate SHA and the shipped app `maiw_api.app:app`:

* `/api/v1/chat` is gone (404 from the host and from inside the sandbox). FL-01 was unchanged.
* `/api/v1/inference` is mounted, fails closed and returns 422 for routing fields.
* `JsonFileProcedureStateStore` and `JsonFileGovernanceInbox` are built at runtime from `MAIW_PERSISTENCE_ROOT` and survive restart.
* Readiness fails on persistence and database loss.
* The document pipeline reaches models only through ModelGateway, with no synthetic APPROVE.

The candidate still **fails** because the re-audit found **three new P1s**, plus a fourth P1 required by the spec's ordering rule (§45):

1. **NEW-P1-01 — the dispatched model ID is not policy-checked (§10, highest priority).** PolicyFilter checks a `generation` label that is hard-coded per *role*. The physical model ID comes from `NEMOTRON_*_MODEL` with no validation.
   * **Approved role bound to an unapproved model.** Binding the approved Super role to an unapproved model ID made `POST /api/v1/inference` on the shipped app send that ID to the provider. A local fake provider recorded it. The app returned `200` with `generation: "nemotron-3"` and `approved_family: true`.
   * **Fallback path.** The same happened through Lightning and through Nano→Super fallback.
   * **Provider substitution.** When the provider reported serving a different model, the app still returned `200`. It reported `approved_family: false` but did not enforce anything.
   * **Preflight and smoke give false assurance.** Both check `LLM_MODEL`, which the gateway never dispatches. They passed 19/19 with an unapproved `NEMOTRON_SUPER_MODEL`.
2. **NEW-P1-02 — the runbook cannot reproduce the deployment (§42).**
   * No script except `start` loads `.env`, and `start` runs preflight *before* loading it. Literal preflight: 9 pass / 10 fail; literal start exits 1.
   * There is no sandbox creation or network-policy step. The policy is not in the repo, and `MAIW_SANDBOX_NAME` is undocumented.
   * There is no database step.
   * The registry default Nano model returns HTTP 410 (end of life 2026-09-01). The smoke test's default MEDIUM request therefore fails 503 unless the operator sets the undocumented `NEMOTRON_NANO_ENABLED=false`.
3. **NEW-P1-03 — readiness reports READY when the governed write path cannot work (§19/§58).**
   * `mcp_domains` lists unconfigured domains as `HEALTHY`.
   * With the only configured MCP domain `CIRCUIT OPEN`, `/ready` stays `200 READY`. This contradicts the runbook rule ("not every *configured* domain CIRCUIT OPEN").
   * In the reference profile every governed write returns 400, yet `governed_write_path: ready`.
4. **NEW-P1-04 — release tests depend on order (§45).** CI order passes (2720/0). Other orders fail:
   * ModelGateway first: 40 failures.
   * Reliability first: 40 failures.
   * Reversed: 158 failures and 6 errors.
   * Minimal reproduction: `pytest tests/unit/test_model_gateway.py tests/unit/demo` gives 40 failures, while `tests/unit/demo` alone passes 74/74.

   This is pre-existing (PR #143 does not touch these files), but §45 classifies any order dependence as P1.

There is no P0. The live sandbox path worked: inference went through the shipped app on approved Nemotron 3 / 3.5; the provider, internet, metadata service and host-private NIM were denied; and the sandbox had no credentials. Durability and governance replay protection were reproduced. There are 20 P2 observations (§53).

---

## 2. Candidate Identity (§1)

* `gh pr view 143` → head `785c420604c3b6a16d6e7531fcab2c73da43f67a`, state OPEN, not merged. Rechecked mid-audit (2026-10-09T19:43Z) and at the end: unchanged.
* The PR has 12 commits, 50 changed files, +5627/−1882.
* CI on the head: Test & Quality (3.11, 22), CodeQL ×2, Security Scan and Trivy all pass. Semantic Release was skipped. This is CI evidence, not a reproduction.
* **§0 gate.** GraphQL `reviewThreads` returns 3 threads, all `isResolved: true`. Verified in code:
  * `tests/api/canonical_harness.py` uses only `import maiw_models…`.
  * `tests/api/test_canonical_shipped_app.py` uses only `from maiw_models import …`.
  * `scripts/qualification/live_document_failure_injection.py` uses `asyncio` (`asyncio.run`, line 62).

  The gate passes.

## 3. Clean-Room Environment (§2)

* Fresh clone at `/home/nvidia/maiw-v201-reaudit` from `git@github.com:NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse.git`. Fetched `refs/pull/143/head` and checked out detached at `785c420`.
* `git status` was clean (only the untracked `.reaudit-*` folders). `origin` is the NVIDIA remote.
* No remediation or audit checkout, venv or sandbox was read or reused.
* Disposable Postgres `maiw-v201-reaudit-pg-20261008022841` (timescaledb 2.15.2-pg16, local image) ran on `127.0.0.1:55435` with the repo schema loaded. It has been removed.
  * Port **5435 on this host belongs to a foreign database** (`wosa-timescaledb`), so every `DATABASE_URL`, `PGHOST` and `PGPORT` was pinned to 55435.

## 4. Package Path Verification (§3)

* Venv: `/home/nvidia/maiw-v201-reaudit/.venv`, Python 3.12.3 (the host has no 3.11; CI uses 3.11).
* Install mirrored `ci-cd.yml`: `requirements.txt`, the test tools, the nine editable packages and `apps/api`.
* With `PYTHONPATH` unset, every package resolves into the fresh checkout:

| Module | Path |
|---|---|
| maiw_api | `/home/nvidia/maiw-v201-reaudit/apps/api/maiw_api/__init__.py` |
| maiw_models | `/home/nvidia/maiw-v201-reaudit/packages/maiw-models/maiw_models/__init__.py` |
| maiw_agents | `/home/nvidia/maiw-v201-reaudit/packages/maiw-agents/maiw_agents/__init__.py` |
| maiw_world | `/home/nvidia/maiw-v201-reaudit/packages/maiw-world/maiw_world/__init__.py` |
| maiw_mcp / decision / execution / state / skills / contracts | under `/home/nvidia/maiw-v201-reaudit/packages/…` |
| src.api.routers.inference | `/home/nvidia/maiw-v201-reaudit/src/api/routers/inference.py` |

There was no contamination.

## 5. PR #143 Scope (§55)

| Category | Files |
|---|---|
| Security-sensitive | `app.py`, `route_policy.py`, `src/api/routers/inference.py` (`extra="forbid"`), `error_handler.py`, `src/api/routers/document.py`, `.env.example`, `Dockerfile.backend` |
| Behaviour | `bootstrap.py`, `lifespan.py`, `persistence.py`, `procedure_host.py`, `health.py`, `procedures.py`, `state_store.list_ids`, 6 document-pipeline files, `equipment_asset_tools.py` (the legacy NIM client is no longer built), 9 lifecycle scripts |
| Build | `ci-cd.yml` (`tsc` step), `package-lock.json` |
| Tests / docs | Remainder |

There is no material feature creep. Two minor additions:
* `ProcedureHost.start/resume/apply_governance` has no production caller.
* There is a new unauthenticated `GET /api/v1/procedures[/{id}]`.

The two updated document test files are still `--ignore`d by CI.

---

## 6. Original P1 Re-Audit

### 6.1 P1-01 — Chat / mutation boundary (§6)

Against the live `maiw_api.app:app` with the disposable DB (`.reaudit-probes/route_bypass.sh`, log `.reaudit-logs/route_bypass.txt`):

* **Chat and reasoning routes are gone.** All return 404: `POST /api/v1/chat`, `/chat/`, `/chat/stream`, `//api/v1/chat`, `/API/V1/CHAT`, `chat%2F`, `chat?x=1`, `/reasoning/*` and `/mcp/tools/execute`.
* **Legacy writes are not mounted.** They return 405 or 404: inventory/operations/safety/WMS/IoT/ERP/scanning/attendance writes, migrate/rollback, training start, forecasting batch, document search/validate.
* **The database was unchanged.** The `equipment_assets` md5 and the row counts for `equipment_assignments`, `inventory_items`, `tasks` and `safety_incidents` were identical before and after. FL-01 stayed `available`.
* **The audit's exact FL-01 Postgres scenario passes.** `test_p1_01_audit_chat_scenario_against_postgres` passed with `MAIW_TEST_PG_DSN` set to the audit DB.
* **From inside the sandbox:** `POST /api/v1/chat` returned 404 and `PUT /inventory/items/SKU1` returned 405.

**Closed.**

### 6.2 P1-02 — Canonical inference (§8)

`POST /api/v1/inference` on the shipped app:

| Case | Result |
|---|---|
| No token | 401 |
| Wrong token | 401 |
| Forbidden field (`model_id`, `base_url`, `deployment_mode`) | 422 |
| Unknown field (`model`, `routing_hints`) | 422 |
| Valid request | 200 |

* Requests rejected with 422 never reached the provider (fake-provider log).
* With no token configured the endpoint fails closed with 503. This is covered by `test_p1_02_inference_auth_fail_closed_when_unconfigured`, which passes in a clean tree.
  * Caveat: the lifespan calls `load_dotenv()`. A cwd `.env` that contains a token makes that test fail, as observed when the audit's deployment `.env` was present.

**Closed.** The model-identity defect below is a separate new P1.

### 6.3 P1-03 — Persistence (§14–§18)

* **Wiring.** `bootstrap.get_runtime` calls `persistence.build_persistence()`, which reads `MAIW_PERSISTENCE_ROOT`. That builds `JsonFileProcedureStateStore(<root>/procedures)` and `JsonFileGovernanceInbox(<root>/governance)`, which back `ProcedureHost`. Failures are recorded and reported as NOT_READY; there is no silent fallback to memory.
* **File location.** In a fresh root, `/ready` reported those exact paths, and procedure JSON appeared under the root.
* **Restart durability across separate processes** (`.reaudit-probes/durability_probe.py`):
  * A procedure was started to `WAITING_FOR_GOVERNANCE` with forced retries (rev 24; `establish_state=2`, `diagnose=2`).
  * A separate uvicorn process served it over HTTP unchanged (same ID, rev 24, `current_step=submit`, same attempts).
  * Through the candidate's own `restart_reference_deployment.sh`/`start` path, deployment procedure `6454a5a1-…` kept rev 24 and the same attempts.
* **Governance duplicate protection.** In process 3, governance was applied and the procedure `completed` at rev 30 with 1 executor call. Processes 4 and 5 replayed it: `duplicate=true`, 0 executor calls, rev 30. The ledger holds 1 line.
* **Loop and retry counters.** `attempt_by_step`, `loop_started_at` and `loop_exhausted_step_ids` are persisted; retry counters were verified across restart.

**Closed.** Residual issues (P2): see the crash gap in §20 and the absence of an HTTP start route in §19.

### 6.4 P1-04 — Readiness (§19, §21)

Live failure injection on the shipped app (`.reaudit-probes/ready.sh`):

| Failure | `/ready` HTTP | Body | `/live` | Correct? |
|---|---|---|---|---|
| Baseline | 200 | READY | 200 | yes |
| Persistence root `chmod 000` | 503 | NOT_READY `[persistence]` | 200 | yes |
| `procedures/` missing | 503 | NOT_READY `[persistence]` | 200 | yes |
| `governance/` `chmod 000` | 503 | NOT_READY | 200 | yes |
| `governance` replaced by a file | 503 | NOT_READY | 200 | yes |
| `procedures/` read-only (555) | 503 | NOT_READY | 200 | yes |
| DB paused (`docker pause`) | 503 | NOT_READY `[database]` | 200 | yes |
| Provider down (fake provider stopped) | 200 | READY; `model_provider` reported, non-critical; inference 503 `MODEL_UNAVAILABLE` | 200 | as designed |
| Sandbox unavailable, `MAIW_SANDBOX_MODE=required` | 200 | READY; `sandbox_runtime: {status: external, mode: required, critical: false}` | 200 | explicit (see §7.12) |
| No MCP domain configured (reference profile) | 200 | READY; all 4 domains `HEALTHY`; `governed_write_path: ready` | 200 | **no** → NEW-P1-03 |
| Only configured MCP domain (equipment) `CIRCUIT OPEN` | 200 | READY | 200 | **no** → NEW-P1-03 |
| ModelGateway not constructed | not injectable via env | covered by in-process test only | — | NOT REPRODUCED live |

**The original P1-04 is closed** (persistence and DB). The MCP and governed-write gap is the new P1-03.

### 6.5 P1-05 — Document pipeline (§22–§27)

* **Model calls.** Upload → preprocessing (local) → OCR (IMAGE) → small LLM → judge (TEXT, HIGH) → deterministic router. All model calls go through `model_gateway_adapter.generate_for_document` → `ModelGateway`.
* **No direct provider calls are reachable.** Every direct-provider module found repo-wide (`reasoning_engine`, legacy agents, `nemotron_parse`, `embedding_indexing`, …) is unreachable from mounted routes. `src.api.services.llm.nim_client` is not loaded.
* **No false success under failure injection.** With no key, 401, 503, timeout, an empty or non-JSON response, and judge failure, there was no synthetic APPROVE and no false success. Status ends `failed`, or `completed` with `REVIEW_REQUIRED`/score 0.
* **Vision is fail-closed.** IMAGE routes `nano-omni → super`; PolicyFilter rejects `super` for image modality, giving `MODEL_UNAVAILABLE`. There is no widening and no text fallback.

**Closed.** Residual P2s: vision cache-key crash, `/approve` and `/reject` stubs, fabricated analytics trend, typed error not surfaced (§53).

---

## 7. Detailed Sections

### 7.1 Mutation Route Inventory (§7)

These come from the actual FastAPI route table (`.reaudit-probes/route_inventory.py`; FastAPI 0.142.4; 147 routes; 24 non-GET; the OpenAPI cross-check matches):

| Route | Method | Mutation | Auth | Governance | Executor |
|---|---|---|---|---|---|
| `/api/v1/equipment/assign` | POST | warehouse (governed) | **none** | DecisionEngine (human approval) | EquipmentActionExecutor if APPROVED |
| `/api/v1/equipment/release` | POST | warehouse (governed) | **none** | DecisionEngine (LOW → auto-approve) | EquipmentActionExecutor |
| `/api/v1/equipment/maintenance` | POST | proposal only | none | DecisionEngine (always human) | none |
| `/api/v1/copilot/turn` | POST | ACT via orchestrator | none | GovernedActionOrchestrator | via approval |
| `/api/v1/demo/approve` | POST | governed execute | none | consumes pending approval (pop-once) | executor |
| `/api/v1/demo/reject`, `/reconcile` | POST | approval / reconcile record | none | — | reconcile reads |
| `/api/v1/demo/{inject,tick,analyze,scenario/*}` | POST | simulation state | none | demo mode | — |
| `/api/v1/document/upload` | POST | file + DB rows + inference | **none** | — | — |
| `/api/v1/document/{approve,reject}/{id}` | POST | none (stub) | none | — | — |
| `/api/v1/inference` | POST | none | internal token | n/a (no governance below) | — |
| `/api/v1/auth/{login,refresh}` | POST | identity | credentials | — | — |
| `/api/v1/auth/{register,change-password}`, `PUT /auth/me`, `PUT /auth/users/{id}` | POST/PUT | identity | JWT (admin for register/users) | — | — |

Every warehouse mutation goes through DecisionEngine. None is authenticated (P2-05).

### 7.2 Route Policy (§50)

`read_only_view` and `curated_view` copy only `APIRoute` objects whose methods are a subset of {GET, HEAD, OPTIONS}, plus the explicit allowlist.

Bypass attempts all failed: alternate method (405), trailing slash (307 to the same 405), case and encoding tricks (404), double slash (404), hidden POST on GET-only paths (405), `/procedures` writes (405/404). Sub-routers and websocket routes would be dropped, which fails safe.

Note: `curated_view` mounts *every* GET of the document router. That includes `GET /api/v1/document/analytics`, which `app.py:262` says "is not shipped" (P2-09).

### 7.3 ModelGateway path (§9)

* **Path:** sandbox → `POST /api/v1/inference` (`src/api/routers/inference.py`) → `get_model_gateway()` singleton → `ModelRouter.route` (role selection plus `PolicyFilter.is_request_eligible`) → `ModelRegistry.get_by_id` → `NIMProvider.call(model_id=…)` → `NIMClient.generate_response(model_override=model_id)` → `POST {MAIW_NIM_BASE_URL|LLM_NIM_URL}/chat/completions`.
* No alternate provider path is reachable from the shipped app (§6.5).

### 7.4 Final Physical Model Identity (§10) — NEW-P1-01

**Mechanism:**
* `registry.py:194-300`: `model_id=os.getenv("NEMOTRON_<ROLE>_MODEL", default)` sits next to a **hard-coded** `generation="nemotron-3"` / `"nemotron-3.5"` for each role.
* `routing.py:280-286`: PolicyFilter checks `cap.generation in APPROVED_MODEL_GENERATIONS`. Its comment claims this "cannot be bypassed by model_id injection", but the environment variable *is* model_id injection.
* `nim.py:72-80` sends that ID to the provider unchanged.
* `inference.py` derives the reported `generation` and `approved_family` from the role label. The response's `model_id` is whatever the provider returns.

**Reproduction.** The shipped app ran under uvicorn with `MAIW_NIM_BASE_URL=http://127.0.0.1:18901/v1`, pointing at a local fake OpenAI-compatible provider (`.reaudit-probes/fake_provider.py`). That provider records the `model` field it receives and never forwards anything. No real unapproved model was called.

| Config (operator env) | Request | Fake provider received `model` | App response |
|---|---|---|---|
| A: `NEMOTRON_SUPER_MODEL=example-org/unapproved-model-x` | `reasoning=high` | `example-org/unapproved-model-x` | **200**, `selected_role=super`, `generation=nemotron-3`, `approved_family=true` |
| D: `NEMOTRON_LIGHTNING_MODEL=example-org/unapproved-model-z` | `reasoning=low` | `example-org/unapproved-model-z` | **200**, `generation=nemotron-3.5`, `approved_family=true` |
| D: plus `NEMOTRON_NANO_ENABLED=false` and Super unapproved | `reasoning=medium` (fallback nano→super) | `example-org/unapproved-model-x` | **200**, `fallback_used=true`, `approved_family=true` |
| C: defaults; provider *answers* as `example-org/substituted-model-y` | `reasoning=high` | `nvidia/nemotron-3-super-120b-a12b` | **200** with content, `model_id=example-org/substituted-model-y`, `generation=unknown`, `approved_family=false`. Reported, not enforced. |

`/ready` stayed READY. `preflight_reference_deployment.sh` with `NEMOTRON_SUPER_MODEL` and `NEMOTRON_LIGHTNING_MODEL` set to unapproved IDs passed **19/19** (log `preflight_unapproved_super.log`). It validates only `LLM_MODEL`/`MAIW_NIM_MODEL`, which the gateway never dispatches because `model_override` is always set. The smoke test's "approved generation" check reads the same role label.

**Severity: P1** (§10 "at least P1"; §58 "final physical model bypasses policy"). The original audit graded the same mechanism P2-06 ("operator-only"). It was explicitly left unchanged ("policy intentionally unchanged"), and this spec does not accept role-name approval.

### 7.5 Deployment Resolution (§11)

There is **no DeploymentResolver** (no class; the docstring in `inference.py` references one).

| Question | Answer |
|---|---|
| Where does a logical role become a physical deployment? | `ModelRegistry._build()` at construction, from environment variables. The provider endpoint comes from `NIMConfig` (`MAIW_NIM_BASE_URL` > `LLM_NIM_URL`) at import. |
| What is checked before dispatch? | Role enabled, plus PolicyFilter on role metadata: generation label, modality, capabilities, risk/reasoning. Not checked: the model ID string, the provider identity, and the provider's reported model. |
| Can identity drift after PolicyFilter? | Yes. The provider at the base URL decides what actually serves the request, and the returned `model` is accepted (config C). |
| Can provider config override policy? | Yes, effectively. Any OpenAI-compatible base URL is accepted (plain HTTP to a non-localhost address only logs a warning). |

### 7.6 Fallback Policy (§12)

* **Chain:** `lightning→nano→super`, `nano→super`, `ultra→super`, `nano-omni→super`. Every candidate is re-checked by PolicyFilter. If none qualifies, the result is `ModelUnavailable` and the API returns 503 `MODEL_UNAVAILABLE`.
* **No fallback on provider error.** Nano returning 410 gives 503; it does not escalate to Super.
* With approved IDs, no widening was observed. Fallback inherits NEW-P1-01: it lands on whatever ID the fallback role is bound to (config D).

### 7.7 Nano 410 Analysis (§13)

* **Registry default:** `nvidia/nemotron-3-nano-30b-a3b`, `enabled=True` by default (`registry.py:145`). The registry docstring and `.env.example:103-108` say it is "validated DEPLOYED".
* **Live hosted endpoint** (2026-10-09, `.reaudit-logs/nano_probe.json`):
  * Nano: **HTTP 410**, "reached its end of life on 2026-09-01".
  * Super: 200, 550 ms.
  * Lightning: 200, 361 ms.
* **With defaults**, the shipped app routes the default `reasoning=medium` to Nano and gets 410. The smoke test's authenticated check fails with 503 `MODEL_UNAVAILABLE` (reproduced, `smoke_exported_nano_default.log`).
* **Classification:** a registry issue (stale default) plus a config/runbook omission. It is not a policy problem: it fails closed inside the approved family. The workaround (`NEMOTRON_NANO_ENABLED=false`) is documented only in the release notes, not in the runbook or `.env.example`, so it feeds into NEW-P1-02. Disabling Nano is acceptable as an *operational* workaround, but the registry default should be corrected rather than relying on a permanent opt-out.

### 7.8 SOP Engine, Proof SOP A and Procedure API (§28–§29)

* **No HTTP start route.** Proof SOP A can be started only in process, through `app.state.runtime.procedure_host` (reproduced with the real lifespan). There is no HTTP start, resume or governance-submit route, and `/demo/approve` is not linked to `apply_governance`.
* **Exposed API.** `GET /api/v1/procedures` and `GET /api/v1/procedures/{id}` (read-only, summaries only) are the whole API surface.
* **Docs.** No doc claims an HTTP start or resume endpoint. However, the runbook's "Normal Operation" and "Governance-wait restart" sections describe flows an operator cannot trigger (P2-10).
* **Release claims.** The current release claims ("durable host-side procedure service") are met. External procedure control is not claimed and is not required for v2.0.1.

### 7.9 UNKNOWN Execution and Duplicate-Write Recovery (§30–§31)

`maiw-execution` is untouched by the PR, so there is no regression. In-process probe (`.reaudit-probes/unknown_write_probe.py`):
* A write that lands and then loses its response yields `UNKNOWN` with 1 physical mutation and no automatic retry (`test_ambiguous_write`, `test_reconciliation` and `test_execution_outcome` all pass).

However, the `ExecutionRegistry` idempotency layer does nothing for canonical callers:
* No production caller sets `ActionProposal.idempotency_key`, and `execution_id` is a fresh UUID per call.
* Re-executing the same approved proposal object performed a second mutation, both in the same process and after a simulated restart.

In the shipped app this is **not reachable**. `/demo/approve` pops the pending approval exactly once (a second approve returns 404), and pending approvals do not survive a restart.

A live crash-before-confirmation test against a governed write was **not reproduced**: the governed write path is non-functional in every profile tried (§7.11). Recorded as P2-03.

### 7.10 Governance Durability (§17)

Covered in §6.3: governance was applied once, the replay was dropped and the ledger holds 1 entry.

**Crash gap (P2-02).** In this probe the process crashed after `inbox.accept()` (fsynced) but before `resume_after_governance`. After restart:
* The procedure is **permanently stuck** at `WAITING_FOR_GOVERNANCE` (rev 24).
* Replays are dropped as duplicates.
* `resume()` returns WAITING procedures unchanged.

It fails safe (no duplicate execution) but cannot be recovered without manual intervention.

### 7.11 Sandbox, Network, Credential and Filesystem Isolation (§32–§38)

**Sandbox.** Fresh sandbox **`maiw-v201-reaudit-a`**:
* Naming: OpenShell caps names at 19 characters, so `maiw-v201-reaudit-<timestamp>` could not be used.
* Image `ghcr.io/nvidia/openshell-community/sandboxes/base:latest` (already present locally); no providers attached.
* Audit-written policy `maiw_inference_only`: `10.185.115.61:18920` only, python3 binaries only.
* Created 2026-10-09T14:35:57Z. **Deleted.** `maiw-qual-20c-b` was never touched.

**Inference through the shipped app** (`.reaudit-logs/in_sandbox_probe.json`). Endpoint `http://10.185.115.61:18920/api/v1/inference`, canonical app started by the candidate's `start_reference_deployment.sh`:

| Request | Result |
|---|---|
| HIGH | 200, `nvidia/nemotron-3-super-120b-a12b`, generation nemotron-3, approved, trace ID preserved. The first call was served from the NIMClient response cache (1.2 ms server-side); a fresh Super call (the injection request) took 1528.7 ms server-side, 1558 ms client-side. |
| LOW | 200, `nvidia/nemotron-3.5-lightning-30b-a3b`, nemotron-3.5, 709.7 ms server-side, 726 ms client-side |
| No token / wrong token | 401 / 401 |
| `model_id`, `provider_url` | 422 / 422 |

**Direct provider denial (§35):**

| Target | Result |
|---|---|
| `https://integrate.api.nvidia.com` | proxy 403; raw TCP fails DNS |
| `example.com` | 403 |
| `1.1.1.1:443` | refused |
| Metadata `169.254.169.254` | 403 |
| Host `:8001`, `:8002`, `:8010` (private NIMs) | 403 |
| `127.0.0.1` | refused |
| DB ports 5435 / 55435 | refused |

**Denied.** However, the allowed host:port exposes the **entire** API surface:
* `/api/v1/ready` returns 200.
* `POST /api/v1/equipment/release` and `/assign` reach their handlers, unauthenticated, and returned 400 only because state assembly failed.
* An actual sandbox-triggered write was **not reproduced**. Even with the repo's equipment MCP server wired to the audit DB, `warehouse.equipment.get_status` crashes (`sql_retriever` is `None`), and demo mode fails the same way.

Recorded as P2-05. It would be P1 if a working MCP backend were configured, because LOW-risk release auto-approves.

**Credential isolation (§36).** 28 environment variables; none named like a key, token, secret, password or DB credential; no values with the `nvapi-` or `ghp_` prefixes. The token was passed over stdin only.

**Filesystem (§37):**
* Absent: `/home/nvidia`, `.ssh`, `.env`, `.git-credentials`, the clone's `.env` and `.git/config`, the persistence root, `/var/lib/maiw`, `docker.sock`.
* Denied: `/root`, `/etc/shadow`, `/proc/1/environ`.
* Writes to `/etc` and `/usr` denied.

**Capability (§32).**
* `maiw_execution`, `maiw_decision`, `maiw_mcp`, `maiw_api` and `integrations` are not importable in the sandbox.
* `ALWAYS_DENIED_CAPABILITY_CLASSES = frozenset({WRITE, EMERGENCY_WRITE})`.
* 68 policy-render and RuntimeCapabilityPolicy tests pass.

**Prompt injection (§38).** A system and user message demanded a model switch, `approved=true`, an FL-01 assign, credential disclosure and a direct provider call. Result: 200 with routing unchanged (super, approved, rule `high_reasoning`). No write path exists below `/inference`, and the database was unchanged. The denial is structural; the model's refusal text is irrelevant.

### 7.12 Sandbox Readiness Assessment (§20)

The API never consumes `MAIW_SANDBOX_MODE`. Nothing in `apps/api` imports the sandbox configuration, and host-side agents (copilot, equipment) run in-process. The readiness body states this explicitly (`sandbox_runtime: {status: external, mode: required, critical: false}`).

That is acceptable for an API that the sandbox calls, so sandbox availability should not gate API readiness. The smoke test catches a missing sandbox.

**P2-11:** `.env.example:242` claims "required means every agent task runs in an OpenShell sandbox". The API does not enforce that.

### 7.13 Deployment Scripts (§39)

The scripts used were the candidate's own: preflight, start, status, smoke, restart, status, stop. Logs are under `.reaudit-logs/`.

| Step | Literal runbook | Workaround (`set -a; source .env`) |
|---|---|---|
| preflight | **9 pass / 10 fail** (`.env` not read) | 19/19 |
| start | **exit 1** (preflight runs before `.env` is loaded) | exit 0, READY in 4 s, process `.venv/bin/python -m uvicorn maiw_api.app:app --port 18920` |
| smoke | **targeted default port 8001** (see incident note) | Nano default: 10 pass / 2 fail. After sandbox creation and `NEMOTRON_NANO_ENABLED=false`: **13/13** |
| restart | — | preflight failed on the host GPU check: **NVML "Driver/library version mismatch"** appeared on the host mid-audit (environmental, not caused by the audit); started again with the documented `--skip-preflight`. Durable state was preserved. |
| status ×2 | — | READY; 1 procedure WAITING. Minor: "Provider reachability: not reachable" while inference worked. |
| stop | — | SIGTERM to the pidfile PID; state preserved; sandbox reported, not killed |

**Incident note (disclosed).** Run literally as the runbook says, the smoke test fell back to `http://localhost:8001`, which on this host is the user's pre-existing dev `maiw_api` server. It sent that server the P1-01 trigger payload (`POST /api/v1/chat {"message":"Show me the status of forklift FL-01"}` → 200) and inference requests (401).

A read-only check of that server's database found no new `equipment_assignments` row. FL-01 was already `assigned` since 2026-08-23, so there was no state change. The script hazard is P2-07.

### 7.14 Stop-Script Safety (§40)

Decoys were all the audit's own and harmless:

* **A:** a `sleep` running as `openshell sandbox connect maiw-reaudit-decoy`.
* **B:** a `python -m http.server` on 127.0.0.1:18921, plus a connected client.

| Run | Result |
|---|---|
| Normal stop (pidfile present) | stopped only the deployment PID; all decoys survived; the audit sandbox survived |
| Stop with no pidfile and `MAIW_API_PORT=18921` (server + client) | `lsof -ti` returned 2 PIDs; the quoted multi-line PID failed to parse, so nothing was killed (by accident) |
| Stop with no pidfile and `MAIW_API_PORT=18921` (server only) | **unrelated decoy listener killed** ("Found MAIW API on port 18921 … stopped") |

**P2-01.** The fallback kills *any* process on the port. Because `stop` does not load `.env`, an operator whose root and port live only in `.env` falls back to `/var/lib/maiw` (no pidfile) and port 8001. On this host, port 8001 is the user's dev server.

`qualify_reference_deployment.sh:145-148` still uses `pgrep -f "openshell.*maiw"` with `kill -KILL`, and that pattern matched decoy A. It was not executed against real resources.

All decoys were cleaned up.

### 7.15 Preflight Persistence Root (§41)

* **Missing root under an existing parent:** "will be created" PASS; free space is measured on the nearest existing ancestor (494 GB, no false "0 MB"). Fixed.
* **Root two or more levels missing** (`…/deploy_root/maiw` with `deploy_root` absent): a false **FAIL** ("parent not writable"), even though `mkdir -p` would succeed. P2-12.
* Preflight also prints PASS for "NVIDIA driver: Failed to initialize NVML…".

### 7.16 Runbook Reproducibility (§42) — NEW-P1-02

Undocumented steps that were needed:

1. Export `.env` into the shell before every script (critical).
2. Create the sandbox and its network policy. There is no command, no policy file, and `MAIW_SANDBOX_NAME` is in neither `.env.example` nor the runbook (critical).
3. Provision Postgres or TimescaleDB, load the schema, and set `DATABASE_URL`. `.env.example` has no `DATABASE_URL`; the readiness probe ignores `DB_HOST`/`DB_PORT`, and SQL routes use `PGHOST`/`PGPORT` (default 5435) (critical).
4. Set `NEMOTRON_NANO_ENABLED=false` (critical against the hosted endpoint).
5. Set `MAIW_PYTHON`. Otherwise `start` uses `python3`, and when `maiw_api` is not importable it runs `pip install -e … || true` with whatever `pip` is on `PATH` (P2-13).
6. Set `MAIW_MCP_SERVER_*_URL`. These are undocumented; without them the governed write path cannot work.
7. The persistence root needs `sudo` (`/var/lib/maiw`); there is no runbook step.
8. The stop section of the runbook is stale (it says stop kills the sandbox).

### 7.17 Canonical App Only (§43)

No release-facing path starts `src.api.app`. These use `maiw_api.app:app`: `Dockerfile.backend:96`, `start_reference_deployment.sh`, `start_server.sh`, `start_demo_mode.sh`, the runbook's systemd unit.

* The root `Dockerfile:119` targets `maiw_api.app:app` but never copies `apps/`, `integrations/` or `agents/`, so it cannot import the app (P2-14).
* `Dockerfile.backend`/compose dev would be NOT_READY (`/var/lib/maiw` is not creatable by `appuser`). That goes undetected because CI checks only `/live` and `/health`.

### 7.18 Legacy Read Authentication (§24)

114 GET routes are unauthenticated. They expose:
* the active user list (`/auth/users/public`: id, username, full name, role);
* equipment with `owner_user`; assignments; workforce; incidents with `reported_by`;
* inventory; detailed version (git SHA, build host and user);
* attendance, biometric, ERP financial and employee routes (stock connectors are placeholders, so no real data in a stock deployment).

Side effects:
* The biometric GET makes a blocking `socket.connect` (30 s) on the event loop.
* ERP GETs send outbound requests with placeholder credentials.
* Forecasting GETs can `INSERT INTO model_predictions` and are hard-wired to `localhost:5435`.

These are acceptable for a single-node internal reference deployment only if the network is restricted. That is not stated in the release notes. **P2-06.**

### 7.19 Document Authentication (§23)

`POST /api/v1/document/upload` is unauthenticated. Each upload writes a file that is never deleted, 1 + 5 DB rows, an in-memory status and a job-queue entry with no consumer.

* **Inference cost.** Default config: 0 model calls, because vision is unavailable. With a multimodal model configured, a 12-page PDF makes about 12 gateway calls, each retried up to 3 times.
* **Size limit bypass.** A chunked 60 MB upload with no `Content-Length` bypasses the 50 MB middleware limit; the file was read into memory and left on disk.
* **Rate limiting is off.** The rate limiter fails open on every path: `rate_limiter.py:166-169` catches its own 429. In the agent's probe, 13 uploads and 103 analytics calls were all 200.

DoS and quota abuse are possible from any host that can reach the API. **P2-04** (it would be P1 for an internet-exposed deployment, which the reference deployment is not).

### 7.20 Document Multimodal Limitation (§27)

Explicit `MODEL_UNAVAILABLE` when no approved multimodal model is configured is **acceptable**. The family set is not widened.

However, a configured multimodal model would **still fail**. `NIMClient._generate_cache_key` calls `.strip()` on list-typed multimodal content (`nim_client.py:309`), and `LLM_CACHE_ENABLED` defaults to true, so every IMAGE request fails with `PROVIDER_FAILURE`. The release-note implication that vision works once configured is therefore wrong (P2-08).

---

## 8. Python Tests (§44)

Full CORE CI command (verbatim `ci-cd.yml` selection and ignores; `DATABASE_URL` pointed at the audit DB; Python 3.12.3):

| Run | Result |
|---|---|
| Run 1 | **2720 passed, 0 failed, 5 skipped**, exit 0 |
| Run 2 | **2720 passed, 0 failed, 5 skipped**, exit 0 (139.6 s) |
| Opt-in Postgres tests (`MAIW_TEST_PG_DSN` = audit DB) | 2 passed |
| Capability policy suites | 68 passed |

Skips: legacy migration suite, MAIWSkillAdapter, OpenShell not importable in CI, and the 2 opt-in Postgres tests.

## 9. Test Ordering (§45) — NEW-P1-04

The first permutation run was contaminated by the audit's deployment `.env` in the clone root (the lifespan calls `load_dotenv()`). It was discarded and re-run with no `.env`. Clean results:

| Order | Result |
|---|---|
| CI order | 2720 / 0 |
| Canonical-app tests first | **2720 passed / 0 failed** |
| `test_canonical_shipped_app.py` alone | 53 passed / 0 / 2 skipped |
| ModelGateway tests first | **40 failed** / 2680 passed |
| Reliability first | **40 failed** / 2680 passed |
| Reversed directory order | **158 failed + 6 errors** / 2556 passed |
| Minimal: `tests/unit/test_model_gateway.py tests/unit/demo` | **40 failed** (demo alone: 74 passed) |

Root causes:
* Demo tests call `asyncio.get_event_loop()` after an earlier `asyncio.run()` has cleared the loop ("There is no current event loop").
* In reversed order, `maiw-agents` tests see two `SOPStep` class identities (pydantic "Input should be a valid … instance of SOPStep"). They pass alone (584/584).

The failing test files are not modified by PR #143, so this is pre-existing. The original audit noted that non-CI orders still trip coupling. Per §45 and §58 it is nonetheless **P1**.

## 10. UI Tests and TypeScript (§46)

| Check | Result |
|---|---|
| Jest | **963 passed / 963** |
| ESLint | **0 errors** (1041 warnings) |
| `tsc --noEmit` | **0 errors**, exit 0 |
| `npm run build` | **success** |

## 11. npm Audit (§47)

Fresh `npm audit`: **0 critical, 50 high, 34 moderate, 3 low**. `--omit=dev` gives the same totals, because `react-scripts`, `typescript` and the `@testing-library/*` packages sit in `dependencies`.

* All 50 highs are toolchain: jest/`@jest/*`, `@typescript-eslint/*`, eslint plugins, `react-scripts`, `webpack-dev-server`, `http-proxy-middleware` (dev, `setupProxy.js`), `svgo`/`@svgr`, `tailwindcss`, `chokidar`/`braces`/`micromatch`, `fork-ts-checker`, `react-dev-utils`.
* All are transitive except `react-scripts`. The fix is either non-breaking within the jest/eslint chain or needs a breaking `react-scripts` change.
* `axios` (the production browser client) is 1.20.0 and **not flagged**; the production axios issue is fixed.
* No reachable production high. **P2-15** (build-tool only).

## 12. Python Security Tools (§48)

| Tool | Status |
|---|---|
| pip-audit | **NOT RUN** (not installed; not downloaded per rules) |
| trivy | **NOT RUN** locally |
| gitleaks | **NOT RUN** |

CI evidence (not reproduction): GitHub Trivy and CodeQL (python, js/ts) checks pass on the head. The Trivy step has no `exit-code`, so it does not gate.

## 13. Secret Scan (§49)

A grep scan of the tree and the PR diff covered `nvapi-`, `ghp_`/`gho_`/`github_pat_`, `AKIA`, private keys, JWT-like strings, passwords and connection strings, including notebooks, artifacts, docs, scripts and `.env.example`.

**No real secrets.** Only placeholders (`nvapi-xxx`, `ci_placeholder`, `changeme`) and test fixtures were found. There is a hard-coded dev JWT fallback (`jwt_handler.py:110`), a weak-default risk that is pre-existing (P2-16).

## 14. Release Notes Draft (§52)

Supported by code and reproduction: chat and reasoning unmounted; legacy routes read-only; inference on the API port with 422s; durable stores; restart and replay; readiness for persistence and DB; document pipeline through the gateway; the Nano 410 note; sandbox not part of readiness.

Unsupported or missing:
* the model-family check is on the role label (NEW-P1-01);
* readiness is green with no MCP domain (NEW-P1-03);
* runbook prerequisites (NEW-P1-02);
* "Dockerfile … targets `maiw_api.app`" (the root Dockerfile is broken);
* vision works when configured (it does not);
* unauthenticated legacy reads, upload and governed equipment POSTs;
* `MAIW_SANDBOX_MODE` is not enforced;
* in-memory Approval and Copilot stores;
* no HTTP procedure start;
* the qualify script still pattern-kills;
* the live proofs are asserted, with no raw evidence committed.

**P2-17.**

## 15. v2.0.0 Audit Notice (§53)

The v2.0.0 GitHub Release (published 2026-10-06T18:55:02Z; tag object `0c35a0e`, commit `816ace7`) **starts with the audit notice**: "…v2.0.0 should therefore not be treated as fully deployment-qualified… pending independent re-audit. This tag is unchanged."

The unchanged body below it still says "FULL_END_TO_END_QUALIFIED" and "no silent mock fallback" (P2-18). There is no `v2.0.1` tag or release. Nothing was edited.

## 16. PR #142 Historical Preservation (§54)

PR #142 is OPEN with head `742fd2a0505c63a4835741c66f2e911802202b81`. Both `docs/audits/MAIW_V2_INDEPENDENT_POST_RELEASE_AUDIT.md` and `artifacts/audit/v2_independent_audit.json` still contain the verdict `MAIW V2 INDEPENDENT POST-RELEASE AUDIT FAIL`. PR #143 does not modify them. **Preserved.**

---

## 17. Claim-to-Evidence Matrix (§56)

| Claim | Code evidence | Test evidence | Live evidence | Verdict |
|---|---|---|---|---|
| P1-01 chat / legacy writes removed | `app.py:242-291`, `route_policy.py` | `test_canonical_shipped_app` P1-01 (+PG) | route matrix, DB hash unchanged, sandbox 404 | **Verified** |
| P1-02 inference on the shipped app | `app.py:255`, `inference.py` | P1-02 tests | host + sandbox 200/401/422 | **Verified** |
| P1-03 durable stores | `persistence.py`, `bootstrap.py` | P1-03 tests | separate-process restart, script restart, replay dropped | **Verified** (crash gap P2) |
| P1-04 readiness | `health.py:162-296` | P1-04 tests | injection matrix | **Verified for persistence/DB; false for MCP** (NEW-P1-03) |
| P1-05 document via gateway | `model_gateway_adapter.py`, doc files | doc tests | failure matrix (in-process) | **Verified** (vision bug P2) |
| Sandbox inference only | policy + `inference.py` | real_sandbox (not re-run as such) | live sandbox probe | **Verified** (full API port reachable, P2) |
| Approved model family enforced | `routing.py:280` (label only) | policy tests (label) | fake provider received an unapproved ID | **REFUTED** (NEW-P1-01) |
| Final physical model identity | none | none | configs A, C, D | **REFUTED** |
| Restart durability | JsonFile stores | yes | yes | **Verified** |
| Document auth | none on upload | — | chunked bypass, rate limiter open | **Not authenticated** (P2) |
| Dependency security | lockfile | — | 0 critical / 50 toolchain high | **Verified** (P2 residual) |
| Runbook reproduces deployment | — | — | literal path fails | **REFUTED** (NEW-P1-02) |
| Release tests order-stable | — | ordering runs | — | **REFUTED** (NEW-P1-04) |

## 18. Original P1 Closure Matrix (§59)

| P1 | Reproduced original defect? | Fix independently verified? | Residual risk | Closed? |
|---|---|---|---|---|
| P1-01 ungoverned chat write | Defect absent at the candidate; the audit's FL-01 PG scenario re-run passes | yes (live + PG + sandbox) | Unauthenticated governed equipment POSTs (P2-05) | **CLOSED** |
| P1-02 inference not on the shipped app | yes (now mounted) | yes (host + sandbox) | Model identity (NEW-P1-01) | **CLOSED** |
| P1-03 persistence not wired | yes (now wired) | yes (multi-process + script restart) | Crash gap; no HTTP start; in-memory approvals | **CLOSED** |
| P1-04 readiness false under persistence/DB loss | yes (now 503) | yes (injection matrix) | MCP and governed-write readiness (NEW-P1-03) | **CLOSED** (original scope) |
| P1-05 document direct provider + mock APPROVE | yes (now gateway-only) | yes (failure matrix) | Vision cache crash; stubs | **CLOSED** |

## 19. New P0 Findings

None.

## 20. New P1 Findings

| ID | Finding | Evidence |
|---|---|---|
| NEW-P1-01 | Physical model identity is not policy-checked. An approved role can be bound to any model ID through `NEMOTRON_*_MODEL`; the response falsely attests `approved_family: true`; a provider-substituted model is accepted; preflight and smoke check the unused `LLM_MODEL`. | `registry.py:194-300`, `routing.py:280-286`, `nim.py:72-80`, `inference.py`; `.reaudit-probes/fake_provider.py`, `inference_call.py`; logs `app_A.log`, `app_C.log`, `app_D.log`, `fake_A/C/D.jsonl`, `preflight_unapproved_super.log` |
| NEW-P1-02 | The runbook cannot reproduce the deployment: `.env` is not loaded by preflight or smoke/status/stop/restart; there is no sandbox creation or policy step; there is no DB step; the Nano 410 default makes smoke fail. | `start_reference_deployment.sh:53-88`, `preflight_*.sh`; logs `preflight_literal.log` (9/10), `start_literal.log` (exit 1), `smoke_exported_nano_default.log` |
| NEW-P1-03 | Readiness is READY while the governed write path cannot function: unconfigured MCP domains are reported HEALTHY, and an all-configured-domains `CIRCUIT OPEN` state stays READY, contrary to the runbook. | `health.py:238-248`, `bootstrap.py:250-318`; `ready.sh` rows; `app_F.log` |
| NEW-P1-04 | CORE CI tests are order-dependent (pre-existing; spec §45 classifies this as P1). | `.reaudit-logs/order_*.log`; minimal repro `tests/unit/test_model_gateway.py tests/unit/demo` gives 40 failures |

## 21. P2 Findings

| ID | Finding |
|---|---|
| P2-01 | The stop script's no-pidfile fallback kills any process on `MAIW_API_PORT` (decoy killed). The qualify script still runs `pgrep -f "openshell.*maiw"` with `kill -KILL`. |
| P2-02 | A crash between the governance inbox fsync and resume leaves the procedure permanently WAITING. No recovery path exists. |
| P2-03 | The ExecutionRegistry idempotency layer does nothing for canonical callers (no `idempotency_key`; in-memory only). Duplicate protection rests on one-shot approval. A live crash test was not reproducible. |
| P2-04 | Unauthenticated document upload: chunked uploads bypass the size limit, files are retained without bound, and the rate limiter fails open everywhere. |
| P2-05 | Governed equipment POSTs are unauthenticated and reachable from the sandbox (the policy is port-level). Not exploitable as shipped because the MCP backend is non-functional. |
| P2-06 | Unauthenticated legacy GETs expose users and operational data. One GET blocks the event loop on a socket; ERP GETs make outbound calls; forecasting GETs write. |
| P2-07 | The smoke test, without exported env, targets `localhost:8001` and sends the P1-01 chat trigger to whatever server answers there. |
| P2-08 | Document vision cannot work even when configured (NIM cache-key `.strip()` on list content). |
| P2-09 | `/document/approve` and `/reject` are false-success stubs (accept unknown IDs, record nothing). `/analytics` is shipped and returns hard-coded trends. The typed failure code is not surfaced. |
| P2-10 | No HTTP procedure start or resume route. `ProcedureHost` has no production caller. Runbook "Normal Operation" implies flows an operator cannot trigger. |
| P2-11 | `MAIW_SANDBOX_MODE=required` is not enforced by the API, contrary to `.env.example`. |
| P2-12 | Preflight false-FAILs a persistence root that is two or more levels missing, and passes the driver check on an NVML error string. |
| P2-13 | `start` may `pip install -e … \|\| true` into whatever `python3`/`pip` is on `PATH`. |
| P2-14 | The root Dockerfile cannot import `maiw_api`. `Dockerfile.backend`/compose dev would be NOT_READY. |
| P2-15 | 50 npm highs, all build/test toolchain (0 critical). |
| P2-16 | Hard-coded dev JWT fallback. `.env.example` ships `ENVIRONMENT=development`. |
| P2-17 | Release-notes limitations missing (see §14); live proofs are asserted only. |
| P2-18 | The v2.0.0 release body below the notice still claims full qualification. |
| P2-19 | Readiness probes `DATABASE_URL` while the SQL data path uses `PGHOST`/`PGPORT` (default 5435), so readiness can check a different DB from the one the app uses. |
| P2-20 | No `DeploymentResolver` (docs reference one). Plain-HTTP base URLs to non-localhost addresses only log a warning. |

## 22. Open-Question Matrix (§60)

| # | Question | Answer |
|---|---|---|
| 1 | Is Proof SOP A sufficiently integrated without an HTTP start route? | Yes for current claims: the host-side service is real and durable, and no doc claims HTTP control. P2-10 for runbook wording. |
| 2 | Should sandbox availability affect readiness? | No. The API is called *by* the sandbox, and the body is explicit (`critical: false`). The smoke test covers the sandbox. P2-11 for the `.env.example` overclaim. |
| 3 | Are unauthenticated legacy reads acceptable? | Only on a restricted internal network, which is not documented. P2-06. |
| 4 | Is unauthenticated document upload acceptable? | Not as a default. It is an abuse and DoS vector (chunked size bypass, rate limiter fails open). P2-04 for the internal reference deployment; P1 if exposed. |
| 5 | Is MODEL_UNAVAILABLE for document vision an acceptable explicit limitation? | Yes, the limitation itself. But vision is broken even when configured (P2-08). |
| 6 | Is disabling Nano acceptable? | As an operational workaround, yes; it stays within the family. The registry default and `.env.example` must be corrected, and the runbook must say so (feeds NEW-P1-02). |
| 7 | Is model-family enforcement based on final physical model identity? | **No.** It is based on a role-label generation (NEW-P1-01). |
| 8 | Is the absence of a DeploymentResolver safe? | **No.** Binding is environment-driven and unvalidated; the provider's reported model is not enforced. |
| 9 | Are the remaining npm highs release-blocking? | No. All are toolchain, none reachable in production (P2-15). |
| 10 | Are there hidden direct provider or model paths left? | No reachable ones from the shipped app. The direct-provider modules that remain are not imported by mounted routes. |

## 23. Release Recommendation

Do **not** merge-and-tag PR #143 as v2.0.1 in its current state. Minimum to reach PASS WITH OBSERVATIONS:

1. Enforce approved-family membership on the **physical model ID** before dispatch, using an explicit allowlist of approved IDs or a resolver that maps IDs to generations, and fail closed on unknown IDs. Reject or fail when the provider's reported `model` differs from the dispatched one. Make preflight, smoke and readiness validate the `NEMOTRON_*_MODEL` values that are actually dispatched.
2. Make the runbook reproducible:
   * every script loads `.env` (and preflight runs *after* it is loaded);
   * document sandbox creation with the network policy committed;
   * document the DB, `DATABASE_URL`, `PGHOST`/`PGPORT`, `MAIW_SANDBOX_NAME` and `MAIW_MCP_SERVER_*_URL`;
   * change the registry Nano default, or document the opt-out.
3. Readiness: count only *configured* MCP domains. Fail `governed_write_path` when no equipment domain is configured, or explicitly mark governed writes as unavailable in the reference profile.
4. Fix the event-loop and dual-import ordering couplings so the release suites are order-stable, or obtain an explicit, documented waiver of §45.

P2s should be tracked. P2-01 (stop fallback kill) and P2-07 (smoke default port) are cheap and should be fixed with item 2.

## 24. Audit Artifacts (§61)

* This report: `docs/audits/MAIW_V2.0.1_INDEPENDENT_REAUDIT.md`
* JSON: `artifacts/audit/v2.0.1_independent_reaudit.json`
* Branch: `audit/v2.0.1-independent-reaudit` (from `main` `944507e`; contains only these two files)
* Probes and logs (not committed, kept on the host): `/home/nvidia/maiw-v201-reaudit/.reaudit-probes/`, `/home/nvidia/maiw-v201-reaudit/.reaudit-logs/`
* Cleanup:
  * sandbox `maiw-v201-reaudit-a` deleted;
  * Postgres container `maiw-v201-reaudit-pg-20261008022841` removed;
  * the app, fake provider, MCP server and decoy processes stopped;
  * the token file and the deployment `.env` copy deleted;
  * `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED` was never set.

  `maiw-qual-20c-b`, `nemoclaw-llama-cpp`, `cuopt`, `wms-nim-*`, `nemo-microservices-*` and the user's `:8001` dev server were not modified. One unintended request set hit `:8001`; see §7.13.

## 25. Final Verdict

The candidate SHA was unchanged throughout (`785c420604c3b6a16d6e7531fcab2c73da43f67a`). All five original P1s are closed, there are no P0s, and there are **4 new P1s**.

`MAIW V2.0.1 INDEPENDENT RE-AUDIT FAIL`
