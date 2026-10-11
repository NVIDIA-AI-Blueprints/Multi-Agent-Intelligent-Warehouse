# MAIW v2.0.1 Fourth Independent Re-Audit: frozen PR #143 candidate `6ad2cbf`

**Verdict: `MAIW V2.0.1 FOURTH INDEPENDENT RE-AUDIT FAIL`**

| | |
|---|---|
| Repository | NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse |
| Candidate | PR #143, `fix/v2.0.1-canonical-app-remediation` → `main` |
| Candidate head SHA | `6ad2cbf1b4b8233ce6ca8528692ebba8f97eb10c`. Checked at start (06:02Z), midpoint (06:18:50Z), end (15:58:03Z) and again before the push. It did not change. |
| Base (`main`) | `944507ec914665c6682d39b95e8713355f486598` |
| Host | `epg-tme-smc-h100-02`, a shared qualification host |
| Date | 2026-10-11 (UTC) |
| Machine-readable companion | `artifacts/audit/v2.0.1_fourth_independent_reaudit.json` |
| Stance | Independent. The Round-3 report, the PR description, CI and every earlier audit were treated as claims. No product code was modified. |

---

## 1. Executive Summary

Most Round-3 claims reproduce on the exact frozen SHA.

* **Historical P1s.** All 11 historical P1s are closed for the scope in which each was raised.
* **Sandbox authority boundary.** It holds at both layers:
  * The OpenShell L7 rule allows only `POST /api/v1/inference`. This was proven live, including path tricks, CONNECT tunnels and pipelining.
  * The separate operator credential stops every write before governance when the sandbox policy is deliberately permissive. DecisionEngine, executor and MCP-write counters all stayed at 0.
* **Transport ambiguity.** Lost responses, read timeouts and `kill -9` of the API (after UNKNOWN and in flight) all leave the write UNKNOWN. A retry is blocked with 409. Reconciliation works outside demo mode. The backend write count stays at 1.
* **Model and provider controls.**
  * Provider identity fails closed in all 16 cases.
  * The response cache is isolated by reasoning level, both orders.
  * The physical-model policy holds.
* **Gateway and runbook.**
  * The OpenShell gateway starts, stops and recovers through the documented script.
  * Full preflight passes 32/0 with no skip.
  * The clean-shell runbook passes.
* **Tests.** Python 2865/8/0 twice, plus 7 order permutations and shuffles. Jest 968/968, tsc 0, ESLint 0 errors, build OK.

The candidate **fails** for two reasons:

1. **NEW4-P1-01: a server-declared MCP tool error after the mutation is classified as a definite failure (§27, §61).**
   * The auditor's equipment backend runs the repo's own MCP server module over real streamable HTTP. It applied a release and then returned a tool error.
   * MAIW reported `200 status=failed executed=false error_code=MCP_TOOL_ERROR`. The journal recorded `physical_mutation_occurred=false` and `unresolved=false`.
   * The target was not blocked. Readiness showed `unresolved: 0`. Reconciliation was refused (409, "UNKNOWN only").
   * The operator's retry was approved and executed a **second backend write**: 2 writes for one intent.
   * The shipped Postgres adapter makes this case realistic. Its writes are two non-transactional statements, any exception becomes `success=false`, and the adapter raises → MCP `is_error`.
   * The CI suite pins the unsafe mapping as expected behaviour.
2. **§35 live Nemotron 3 Super / 3.5 Lightning: NOT REPRODUCED.**
   * No hosted-provider credential was available to the auditor. The host permission policy refused credential discovery.
   * The canonical in-sandbox path was proven with an auditor-owned OpenAI-compatible provider only.
   * Per the task rules, a mandatory live proof that cannot run is a FAIL condition.

No P0 was found. Six new P2s and the carried P2s are listed in §52.

## 2. Host Qualification (§1)

| Check | Result |
|---|---|
| `nvidia-smi` | exit 0, 4 × NVIDIA H100 NVL |
| Loaded driver (`/proc/driver/nvidia/version`) | 580.178.04 |
| Installed driver (`modinfo nvidia`) | 580.178.04 (match) |
| Kernel | 6.8.0-146-generic |

The host was healthy. The preflight GPU checks also passed: 4 GPUs, driver 580.178.04, compute capability 9.0.

## 3. Candidate Identity (§3, §57)

* PR #143 is OPEN with head `6ad2cbf…`, base `main` @ `944507e`.
  * 32 commits, 125 changed files.
  * Mergeable: `MERGEABLE` / `CLEAN`.
* Review threads: 7 total, 0 unresolved (GraphQL).
* CI on the head:
  * Test & Quality (3.11, 22), CodeQL ×2, Security Scan and Trivy: SUCCESS.
  * Semantic Release: SKIPPED.
  * CI results are recorded as a claim; the audit re-ran the suites.
* Commit hygiene: none of the 32 commits has a `Co-Authored-By` trailer.

## 4. Clean-Room Environment (§4, §6)

* **Test clone.** A fresh `git clone` into `/home/nvidia/maiw-v201-fourth-reaudit`, detached at the candidate SHA.
  * `git status` was clean.
  * Audit directories were excluded through `.git/info/exclude` only.
* **Runbook worktree.** A second detached worktree at the same SHA, `/home/nvidia/maiw-v201-fourth-reaudit-live`. It was used only for the clean-shell runbook and removed at the end.
* **Nothing reused.** No prior worktree, venv, sandbox, database or helper server was read, run or reused.
* **No stray `.env`.**
  * `find . -maxdepth 3 -name .env` was empty before every pytest run.
  * The runbook's `.env` existed only in the live worktree. It was deleted with that worktree.
  * The governed env file was deleted at the end.
* `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED` was never set.

## 5. Package Provenance (§5)

* **Test venv.** Built from an `env -i` shell with a scratch `HOME`, using the CI/runbook install list. CI test tools were added afterwards. Python is 3.12.3 (the host has no 3.11).
* **Test-venv imports.** Imported from `/tmp` with `env -i`, all ten packages resolve under the fresh clone:
  * `maiw_api` → `apps/api/maiw_api/__init__.py`
  * `maiw_models`, `maiw_agents`, `maiw_execution`, `maiw_decision`, `maiw_world`, `maiw_mcp`, `maiw_state`, `maiw_skills`, `maiw_contracts` → `packages/<pkg>/…`
* **Runbook venv.** Built with step 1 copied exactly from the runbook. All ten packages resolve under the live worktree.

## 6. Host Isolation (§2, §39)

The inventory below was taken before anything was started. `ss` is not permitted to the auditor, so listeners were read from `/proc/net/tcp{,6}`; containers and networks came from `docker ps -a` and `docker network ls`.

| Port / service | Owner | Treatment |
|---|---|---|
| 22, 53 | sshd, systemd-resolved | off-limits |
| 3000 | `nemo-microservices-datastore-1`, intermittent (restart loop) | off-limits |
| 32768 / 32769 | nemo-microservices postgres / guardrails | off-limits |
| 8081 (container-internal) | `nemoclaw-llama-cpp` | off-limits |
| 8001, 8002, 8010, 8011, 8080, 5435, 8991 | no listener; user containers exited; gateway `nemoclaw-8991` down | off-limits regardless |

* **Audit-owned ports:**
  * API: 18951 (runbook and governed).
  * Probe API instances: 18952 and 18953.
  * Gateway: 18997.
  * Reference DB: 55482. Test DB: 55481.
  * MCP backends: 18961–18965.
  * Fake provider: 18971.
  * Closed probe ports: 18947–18949.
* **OpenShell isolation.** Every `openshell` invocation ran with `OPENSHELL_GATEWAY_ENDPOINT=http://127.0.0.1:18997` and a scratch `HOME`, so the user's `active_gateway` file was never read.
  * One exception: a local-only `openshell --version` at the very start, which makes no network call.
* **Watcher.** It polled `/proc/net/tcp{,6}` every 20 ms for the whole audit (1561 log lines). Every hit is classified:
  * SSH inbound from the user's client.
  * The audit's own DB (`172.17.0.3:5432`) and sandboxes (`172.23.0.x`).
  * One TIME_WAIT `127.0.0.1:32770→127.0.0.1:50407` during pytest run 2. This was an ephemeral-port pair; nothing listens on 32770.
* **No pre-existing service was contacted.**
  * The forecasting routes (hard-wired to `localhost:5435`) were deliberately never called.
  * The listener, container and network sets at the end are identical to the start inventory (3000 is intermittent and pre-existing).

## 7. Historical Audit Preservation (§7)

| Item | State |
|---|---|
| `v2.0.0` | tag object `0c35a0e` → `816ace7`, unchanged |
| `v2.0.1` tag | absent |
| PR #142 | OPEN @ `742fd2a` |
| PR #144 | OPEN @ `80947b0` |
| PR #145 | OPEN @ `6205fe6` |

None of these was modified. The GitHub Release for v2.0.0 was not touched.

## 8. All 11 P1 Inventory (§8)

1. **P1-01 to P1-05** (PR #142): ungoverned chat write, missing inference endpoint, durable stores not wired, false readiness, document ModelGateway bypass / mock APPROVE.
2. **NEW-P1-01 to NEW-P1-04** (PR #144): physical model identity, runbook not reproducible, readiness ignoring governed writes, test-order dependence.
3. **NEW3-P1-01 and NEW3-P1-02** (PR #145): the sandbox could reach operational writes; an ambiguous MCP write was classified FAILED and could be duplicated.

Each was re-checked independently. See the closure matrix in §51.

## 9. Sandbox Network Policy (§10)

* **Rendered policy.** `deploy/openshell/maiw-inference-only.policy.yaml.tmpl` renders a single endpoint (`10.185.115.61:18951`, `protocol: rest`, `enforcement: enforce`) with one rule: `allow {method: POST, path: /api/v1/inference}`. It has no `access:` key.
* **Live test.** Sandbox `maiw-v201-4th-a`, created by the runbook, ran the auditor's probe `sbx_probe4.py`:
  * Inference with the token returned 200 (LOW → Lightning, HIGH → Super, `identity_verified=true`). Without the token: 401.
  * Every other request on the API port got 403 from the proxy, with `X-OpenShell-Policy: maiw_inference_only`:
    * `GET` and `PUT /api/v1/inference`, and `POST /api/v1/inference/`
    * `GET /ready`, `/equipment`, `/executions`
    * legacy chat, document upload, copilot turn, demo approve
    * all 24 write attempts (4 routes × 6 credential variants)
  * Path variants all returned 403: `..`, `%2e%2e`, `//`, `/./`, upper case, trailing slash, `;`, `?/api/v1/inference`, `%65`, backslash.
  * `%2F` returned 400.
  * `POST /api/v1/inference?/../../equipment/release` reached only the inference route and returned 422.
* **Raw-socket tests through the sandbox proxy:**
  * Pipelined `inference + release` on one connection: only the inference was answered; the release never reached the app.
  * Absolute-form and HTTP/1.0 requests, and duplicate headers: 403.
  * CL.TE smuggling: 400.
  * A `CONNECT` tunnel to the API port was established (200), but the release request inside it got 403 and a reset. **The L7 policy is enforced inside CONNECT tunnels.**
* **Egress.** All other egress was refused: the auditor's DB, gateway, MCP and provider ports on the host IP, loopback, `1.1.1.1:80`, and DNS to `integrate.api.nvidia.com`.

## 10. Application Write Authentication (§11, §12)

* **Permissive-policy sandbox.** `maiw-v201-4th-b` used a deliberately permissive `access: full` policy on the API port. The app was `reference_governed`, READY, with real MCP backends. Results:
  * Inference: 200.
  * `/ready` and `/equipment`: 200 (unauthenticated reads, P2-06).
  * The 24 write attempts:
    * 16 × 403 `OPERATOR_WRITE_CREDENTIAL_REQUIRED`: no credential, the inference token in the internal header, as a bearer, or an empty operator header.
    * 8 × 401 `INVALID_OPERATOR_WRITE_CREDENTIAL`: the inference token as the operator header, raw or whitespace-wrapped.
  * Counters before → after: DecisionEngine 0 → 0, executor 0 → 0, MCP writes 0 → 0, warehouse state hash unchanged, app auth refusals +35.
  * Under the L7 policy the same 24 attempts never reached the app (refusal counter unchanged).
* **Ordering.** Authentication is a route-level dependency (`_WRITE_GUARDS = [require_operator_write, require_governed_writes_offered]`). It runs before body validation, the agent and the DecisionEngine. **Authentication precedes governance.**

## 11. Sandbox Credential Isolation (§13)

* In both sandboxes there were 28 environment variables. None had a name matching `KEY/TOKEN/SECRET/PASS/NVAPI/OPERATOR/CRED/GITHUB/DATABASE/PG/AWS/JWT`.
* No SHA-256 value digest matched any host secret: operator token, inference token, DB passwords or JWT secret.
* The inference token was delivered on stdin only.
* The runbook probe agrees: "host secrets present in sandbox = none".

## 12. Write Route Inventory (§14)

The canonical app has 146 method/path pairs. The inventory was walked with a FastAPI-0.143-aware probe that follows `_IncludedRouter` and collects router-level dependencies. These 25 can mutate:

| Route | Method | Auth | Governance | Executor |
|---|---|---|---|---|
| `/api/v1/equipment/{assign,release,maintenance}` | POST | operator credential + profile gate | DecisionEngine | EquipmentActionExecutor (release LOW auto; assign / maintenance human) |
| `/api/v1/executions/{id}/reconcile` (+ GET journal) | POST/GET | operator credential | none (records reconciliation) | none |
| `/api/v1/inference` | POST | inference token | none | none |
| `/api/v1/demo/*` (10 routes) | POST | none | demo only: 503 outside `MAIW_DEMO_MODE` (verified for approve, reconcile, inject, tick, reset) | simulation |
| `/api/v1/copilot/turn` | POST | none | ACT → "degraded" (orchestrator is not wired outside demo); 0 DecisionEngine, 0 MCP writes (verified) | none |
| `/api/v1/auth/{register,login,refresh,me,change-password,users/{id}}` | POST/PUT | credentials / JWT / admin | identity only | none |
| `/api/v1/document/{upload,approve/{id},reject/{id}}` | POST | none | document workflow | none (P2-04/P2-09) |

Every route that can cause an operational warehouse mutation requires the operator credential before governance.

## 13. Write Auth Bypass Tests (§15)

These host-side tests ran against the governed app.

| Request | Result |
|---|---|
| Missing operator header | 403 |
| Wrong token / inference token as operator / whitespace-wrapped / prefix / suffix | 401 |
| Inference token in internal header / as bearer / empty / `X_Maiw_Operator_Token` | 403 |
| Duplicate headers, wrong first then valid | 401 |
| `GET` | 404 |
| `PUT` / `PATCH` / `DELETE` | 405 |
| Path variants with the inference token | 404 / 405 / 307 / 401 |
| Valid operator token | 422 (authenticated, empty body) |

* The 307 (trailing slash) only redirects to the authenticated route.
* Duplicate headers with the valid token first returned 422: Starlette takes the first value, and that value is the operator's own token.
* DecisionEngine and MCP counters were unchanged. **No inference-only credential authorised a write.**

## 14. Real MCP Ambiguous Write Semantics (§16, §17)

Code, verified by reading:

* `MAIWMCPClient._call_tool` (`packages/maiw-mcp/maiw_mcp/client/client.py:276-319`) tracks the dispatch phase:
  * `connect`, before `Client.__aenter__` completes → `MCPConnectFailed` / `MCPConnectTimeout` (`MCPNotDispatched`).
  * `dispatched`, once `call_tool` is entered → `MCPResponseLost` / `MCPTimeoutAfterDispatch` (`MCPDispatchOutcomeUnknown`).
  * Result received with `is_error` → `MCPToolError`.
  * An open circuit → `MCPCircuitOpen`. This is raised before the coroutine runs.
* `classify_write_failure` (`packages/maiw-execution/maiw_execution/base.py:136-158`) maps these errors:
  * `MCPDispatchOutcomeUnknown`, a bare `MCPTimeout`, or `MCPContractError` → UNKNOWN.
  * `MCPNotDispatched` → FAILED, mutation=false.
  * **`MCPToolError` → FAILED, mutation=false.**

Real-transport probe (`mcp_phase_probe.py`) against the auditor's backend on 18964:

| Case | Exception | Classification | Mutations |
|---|---|---|---|
| Closed port | `MCPConnectFailed` | failed, `MCP_NOT_DISPATCHED`, false | 0 |
| OK | — | — | 1 |
| Error before mutation | `MCPToolError` | failed, false | 0 |
| **Error after mutation** | `MCPToolError` | **failed, `MCP_TOOL_ERROR`, false** | **1** |
| Hang after write (3 s timeout) | `MCPTimeoutAfterDispatch` | unknown, None | 1 |

## 15. UNKNOWN Classification (§19)

* **Setup.**
  * The governed profile was started by `start_reference_deployment.sh` with `MAIW_ENV_FILE`.
  * The equipment backend is the auditor's `adv_mcp.py`, running the repo's own `mcp_servers.equipment.server` over streamable HTTP. State is durable in a JSON file and every write is logged.
* **Lost response.** Mode `crash_after_write` on FL-02 (apply, log, `os._exit`) returned **202** with:
  * `status: unknown`, `executed: null`, `error_code: MCP_RESPONSE_LOST`
  * `reconciliation_required: true`, `retried: false`
* **Backend identity.** The backend log shows the API's `execution_id`, `proposal_id` and `decision_id`.

## 16. No-Blind-Retry Proof (§20)

* An identical request for FL-02 before reconciliation returned 409 `RECONCILIATION_REQUIRED` with the same `execution_id`. DecisionEngine +0, backend writes still 1.
* A concurrent duplicate sent during an in-flight (hanging) write on FL-01 also got 409.

## 17. Durable Write Journal (§26)

* **Ordering.** `JsonFileExecutionRegistry.begin()` persists (fsync, then dir fsync) **before** `_do_execute` dispatches. Every transition is re-persisted.
* **Journal-timing probe.** FL-05 used mode `hang_after_write`.
  * The backend applied the write and then hung.
  * The on-disk record showed `outcome: null`, `pre_status: assigned`.
  * The API was then killed with `kill -9` mid-request.
* **Restart.** After `start_reference_deployment.sh`, the record was `unknown` with `recovered_after_restart: true`. Readiness showed `unresolved: 1`. A retry got 409, and reconcile returned `confirmed_executed`. Writes: 1.
* **Failure windows.** No window was found where a transport-ambiguous write lands without the journal reflecting uncertainty:
  * If `begin` fails to persist, the exception propagates before dispatch.
  * If `complete` fails to persist, the on-disk record stays in flight, which means UNKNOWN after a restart.
  * A cancelled request leaves the record in flight, which blocks the target.
* **The gap is not timing.** It is the server-error branch (§23).

## 18. Reconciliation Outside Demo Mode (§21)

* `POST /api/v1/executions/{id}/reconcile` (operator credential) works in `reference_governed` with `MAIW_DEMO_MODE` off.
* `/api/v1/demo/reconcile` returns 503 in this profile.

## 19. CONFIRMED_EXECUTED (§22)

* FL-02: reconcile with the backend down returned `indeterminate` and the asset stayed blocked.
* After the backend restarted, reconcile returned `confirmed_executed` / `effectively_executed` with the same proposal, decision and trace ids. Backend writes: 1.

## 20. CONFIRMED_NOT_EXECUTED (§23 spec)

* FL-03 used mode `crash_before_write`: the request was received and the backend exited without applying it. The API returned 202 unknown.
* Reconcile returned `confirmed_not_executed` (`pre_status: assigned`). Nothing was retried automatically.
* A new operator request then executed once. Writes: 0, then 1.

## 21. INDETERMINATE (§24)

* With the backend down, reconcile returned `indeterminate` (error "MCP connection failed … before tools/call was sent"). It did not retry, and the asset stayed blocked (409).
* "Another actor set `maintenance`" (FL-11) also returned `indeterminate`.

## 22. Crash / Restart UNKNOWN Recovery (§25)

* FL-04 used `crash_after_write`, giving 202 unknown. The API was then killed with `kill -9` (PID verified by cmdline) and restarted with `start_reference_deployment.sh`.
* After the restart:
  * The journal listed the same execution, proposal, decision and trace id.
  * The retry got 409.
  * Reconcile returned `confirmed_executed`. Backend writes: 1.

## 23. Server-Declared Error Semantics (§27): NEW4-P1-01

| Case | Backend behaviour | MAIW result | Backend writes | Ruling |
|---|---|---|---|---|
| A (FL-06) | rejects before any mutation, raises → MCP `is_error` | 200 `failed` `MCP_TOOL_ERROR`; asset unchanged | 0 | valid definite failure |
| **B (FL-07)** | **applies the release, then raises → `is_error`** | 200 `failed`, `executed: false`, `MCP_TOOL_ERROR`; journal `outcome=failed`, `physical_mutation_occurred=false`, `unresolved=false`; `/ready` unresolved 0; reconcile → **409** (UNKNOWN only); backend asset is `available` | 1 | **unsafe** |
| B retry | same operator request, no reconciliation possible | 200 `executed` (new execution_id) | **2** | duplicate consequential write |

* **Protocol semantics.** MCP `isError` reports a tool-execution error. It does not guarantee that the tool made no side effects.
* **The shipped backend can produce Case B:**
  * `equipment_asset_tools.py` performs assign as INSERT then UPDATE (`:333`/`:347`) and release as UPDATE then UPDATE (`:416`/`:431`). These are separate, non-transactional statements.
  * Any exception becomes `{"success": false}` (`:447-453`).
  * `MAIWEquipmentAdapter` raises `BackendUnavailable` (`maiw_backend.py:257-263`), which the server re-raises as MCP `is_error`.
* **Documentation and tests.** The runbook describes `MCP_TOOL_ERROR` only as "the MCP server answered with an error" (`REFERENCE_DEPLOYMENT_RUNBOOK.md:803`). `tests/api/test_round3_unknown_writes.py:525` pins `MCPToolError → ("failed", False)`.
* **Classification: P1.** This matches the §61 rules "server error after mutation classified definite failure" and "ambiguous write can duplicate".
  * It is not P0. Both writes were operator-authenticated and DecisionEngine-approved. No automatic retry occurs; the duplicate needs a backend failure mode plus an explicit operator resubmission.
* **Remediation direction.** Treat any post-dispatch server error from a write tool as UNKNOWN unless the tool contract proves non-execution (for example, a typed pre-mutation rejection code). Alternatively, make backends transactional and idempotent on the forwarded `execution_id`.

## 24. Reconciliation State-Drift Analysis (§28, §29)

The equipment strategy (`apps/api/maiw_api/reconciliation.py:50-77`) is postcondition-based for success:

* `status == expected_status`, plus the assignee for assign → `CONFIRMED_EXECUTED`.
* `status == pre_status` → `CONFIRMED_NOT_EXECUTED`.
* Anything else → `INDETERMINATE`.

It is not generic inequality, with one exception: when `pre_status` is not recorded, a mismatch falls back to `CONFIRMED_NOT_EXECUTED`.

| Case | Result | Ruling |
|---|---|---|
| A: applied + unrelated `zone` drift (FL-08) | `confirmed_executed` | correct |
| B: not applied + unrelated `zone` drift (FL-09) | `confirmed_not_executed` | correct (drift did not produce false success) |
| C: another actor produced the intended state; MAIW's write not applied (FL-10) | `confirmed_executed` | state-equivalent only; causality not established |
| Another actor → `maintenance` (FL-11) | `indeterminate`, stays blocked | correct |
| Applied, then reverted by another actor (FL-12) | `confirmed_not_executed` → resubmission wrote again (2 backend writes) | false "not executed" |

* MAIW cannot distinguish causality from state equivalence. The backend receives `execution_id`, but reconciliation does not use it.
* Classified **P2 (NEW4-P2-02)**:
  * Unrelated drift never caused a false success.
  * The misattributions need a third party to change the same asset inside the ambiguity window.
  * The FL-12 resubmission re-applies a still-valid operator intent to the current state.
* The labor and wave strategies are weaker (labor: an allocation not `in_progress` → NOT_EXECUTED; wave: any task with the priority → EXECUTED). There is no canonical HTTP route for labor or wave writes in v2.0.1.

## 25. Provider Identity Fail-Closed (§30, §31)

The canonical app on 18951 was pointed at the auditor's fake provider. Each case used a fresh prompt.

| # | Provider reports | HTTP / code | Provider calls |
|---|---|---|---|
| 1 | exact (high; low) | 200 / 200, `identity_verified=true` | 1 / 1 |
| 2 | other string (`…-a12b-fp8`) | 502 `MODEL_IDENTITY_MISMATCH` | 1 |
| 3 | missing `model` | 502 `MODEL_IDENTITY_UNVERIFIABLE` | 1 |
| 4 | `""` | 502 UNVERIFIABLE | 1 |
| 5 | `"   "` | 502 UNVERIFIABLE | 1 |
| 6 | `null` / `123` / `["x"]` / `{"id":…}` | 502 UNVERIFIABLE ×4 | 1 each |
| 7 | U+2010 hyphen look-alike | 502 MISMATCH | 1 |
| 8 | upper-case | 502 MISMATCH | 1 |
| 9 | cross-role approved (Lightning for Super; Super for Lightning) | 502 MISMATCH ×2 | 1 each |
| 10 | unknown model; `-v2` suffix | 502 MISMATCH ×2 | 1 each |

* The dispatched model was always the resolved approved ID.
* Repo-wide, `ModelGateway.generate` is the only producer of `identity_verified`, and `verify_response_identity` either returns True or raises.
* **No successful reference response can have `identity_verified=false`.**

## 26. Cache Isolation (§32, §33)

Cache enabled, default TTL, live:

| Sequence | Provider calls | Answered by |
|---|---|---|
| HIGH, LOW, HIGH, LOW | 1, 1, 0, 0 | Super, Lightning, Super (hit), Lightning (hit) |
| LOW, HIGH, LOW, HIGH | 1, 1, 0, 0 | Lightning, Super, hit, hit |
| HIGH, MEDIUM, MEDIUM, HIGH | 1, 1, 0, 0 | Super thinking, Super `enable_thinking=false`, hit, hit |
| MEDIUM, HIGH, LOW, MEDIUM | 1, 1, 1, 0 | no cross-hit |
| LOW, MEDIUM, HIGH, LOW | 1, 1, 1, 0 | no cross-hit |
| Prompts differing only by an ISO timestamp | 1, 1 | no normalisation |

* **Cache key contents.** The key covers the exact messages, the sampling parameters, the dispatched model, the thinking mode and budget, `cache_scope` (reasoning, risk, modality, deployment mode, role, generation, resolved model ID) and a key version. **The resolved physical model is part of the cache identity.**
* **Observation (NEW4-P2-04).** A response whose identity failed verification is cached before verification. The same prompt keeps returning 502 for the TTL after the provider is fixed. This fails closed; it is not a safety issue.

## 27. Physical Model Policy (§34)

Each case ran on a fresh canonical-app instance on 18952:

| Binding | Result |
|---|---|
| Baseline | `/ready` 200, inference 200 Super |
| `NEMOTRON_SUPER_MODEL` = arbitrary / `-v2` / case variant / U+2010 / unknown / Lightning ID | `/ready` 503 `model_gateway`, inference 503 `MODEL_POLICY_VIOLATION`, **0 provider calls** |
| `NEMOTRON_LIGHTNING_MODEL` = Super ID | same, 0 provider calls |
| Ultra enabled with an unknown ID, judge task | 503 `MODEL_POLICY_VIOLATION`, 0 calls, `/ready` 503 |
| `LLM_MODEL` / `MAIW_NIM_MODEL` = llama | not dispatched (Super ID sent), 200 |
| Provider substitution (reports llama) | 502 `MODEL_IDENTITY_MISMATCH` |

`/live` stayed 200 throughout.

## 28. Live Nemotron 3 Super (§35)

**NOT REPRODUCED.**

* **Why.** No hosted-provider credential was available to the auditor, and the host's permission policy refused credential discovery. No local NIM serving the approved IDs exists that is not a user-owned, off-limits service.
* **What was proven instead.** From fresh sandbox `maiw-v201-4th-a`, through the canonical app, against the auditor's OpenAI-compatible provider: HIGH → `nvidia/nemotron-3-super-120b-a12b`, provider reported the same ID, `identity_verified=true`, 16–31 ms end-to-end against the local provider.
* This is not the real model.

## 29. Live Nemotron 3.5 Lightning (§35)

**NOT REPRODUCED**, for the same reason.

* With the auditor's provider: LOW → `nvidia/nemotron-3.5-lightning-30b-a3b`, `identity_verified=true`, 33–137 ms end-to-end against the local provider.

## 30. OpenShell Gateway Reproducibility (§36)

* **Documented script only.** `scripts/setup/reference_gateway.sh` in `managed` mode started the auditor's own gateway: `maiw-v201-4th-gw`, `openshell-gateway` 0.0.116, `127.0.0.1:18997`, its own namespace, network `maiw-v201-4th-gw-net`, JWT key and sqlite state.
  * start: exit 0 ("Status: Connected, Version 0.0.116")
  * status: exit 0
* **Simulated outage.**
  * stop: exit 0 (network removed); status: exit 1.
  * preflight: exit 1, 30/2 ("OpenShell gateway" and the sandbox fail, with the documented next step).
* **Recovery.**
  * start: exit 0; status: exit 0.
  * The sandbox was in `Error`, as documented. Runbook "Host reboot" recovery: sandbox delete 0 → create 0 → DB status 0 → preflight **32/0**.
* **Final cleanup.** stop: exit 0.
* No undocumented command was needed. The user's `nemoclaw-8991` was never touched.

## 31. Full Preflight (§37)

| Run | Result |
|---|---|
| Reference | **32 passed, 0 failed, no skip** (GPU / driver, Docker, NemoClaw 0.0.124, OpenShell 0.0.116, gateway, bindings + provider `/models`, port, persistence, auth, demo off, sandbox Ready, DB + schema, MCP optional) |
| Governed (`MAIW_ENV_FILE`) | 34 / 0 (adds equipment / labor / wave reachable) |
| During restart | 32 / 0 |
| After recovery | 32 / 0 |

Caveat: the provider probe targeted the auditor's local OpenAI-compatible provider.

## 32. Clean-Shell Runbook (§38)

Every step ran from `env -i` with a scratch `HOME` and `PATH=~/.local/bin:/usr/bin:/bin`, in the detached live worktree, using only runbook commands.

| Step | Exit |
|---|---|
| 1 install (venv, requirements, 8-package loop, agents+api) | 0 / 0 / 0 / 0 |
| 2 `cp .env.example .env` + listed edits | 0 |
| `validate_reference_runbook.sh` | 0 |
| 3 gateway start / status | 0 / 0 |
| 4 `reference_db.sh up` | 0 |
| 5 `reference_sandbox.sh create` (L7 policy) | 0 |
| 6 preflight (32/0) / start / status / smoke (17/17) | 0 / 0 / 0 / 0 |
| 7 `reference_sandbox.sh probe` | 0 |
| 8 restart (preflight 32/0) / status / smoke (17/17) / stop | 0 / 0 / 0 / 0 |
| status after stop | 1 (as designed) |
| 9 teardown: sandbox delete / db down / gateway stop | 0 / 0 / 0 |

* **Deviation.** `MAIW_NIM_BASE_URL` pointed at the auditor's local provider, the runbook's "local NIM" option, because no hosted key was available.
* **`reference_governed`.**
  * preflight 34/0, start 0, smoke 18/18, stop 0.
  * Two `kill -9` restarts via `start_reference_deployment.sh`: 0.
  * The MCP backends had to be auditor-launched. There is no documented launch command, and the shipped equipment backend is non-functional (NEW4-P2-03).

## 33. Readiness (§40)

Fresh canonical-app instances, plus the live governed app:

| Row | `/ready` | failed | `/live` |
|---|---|---|---|
| reference, sandbox disabled | 200 | — (sandbox `not_configured`, gwp `not_offered`) | 200 |
| reference, required sandbox Ready | 200 | — | 200 |
| reference, required sandbox absent | 503 | `sandbox_runtime` | 200 |
| reference, optional sandbox absent | 200 | — (`degraded`) | 200 |
| reference + optional MCP URL + operator token | 200 | — (write → 503 `GOVERNED_WRITES_NOT_OFFERED`) | 200 |
| governed healthy | 200 | — (gwp ready; write auth OK → 422 on empty body) | 200 |
| governed, write token missing | 503 | `governed_write_path` (write → 503 `OPERATOR_WRITE_AUTH_NOT_CONFIGURED`) | 200 |
| governed, token == inference token | 503 | `governed_write_path` | 200 |
| governed, required MCP unreachable | 503 | `governed_write_path`, `mcp_domains` | 200 |
| governed, required MCP unset | 503 | `governed_write_path`, `mcp_domains` | 200 |
| governed, optional inventory MCP unset | 200 | — | 200 |
| invalid profile | 503 | `profile` | 200 |
| DB unreachable / DB container paused (live) | 503 | `database` | 200 |
| persistence `governance/` chmod 000 (live) | 503 | `persistence` | 200 |
| equipment MCP down (live) | 503 | `mcp_domains` FAILED + gwp | 200 |
| equipment circuit open (live) | 503 | `mcp_domains` `CIRCUIT_OPEN` | 200 |
| provider down | 200 | — (inference 503) | 200 |

* **Observation (NEW4-P2-05).** Readiness keeps reporting `CIRCUIT_OPEN` after the cooldown until a request probes the half-open circuit.

## 34. Liveness (§41)

`/api/v1/live` returned 200 in every row above: DB, persistence, MCP, circuit, sandbox, provider, profile and model-policy failures alike.

## 35. Original P1 Regression (§42)

* **FL-01 chat write.**
  * There is no `/api/v1/chat` route. Smoke returns 404; the permissive sandbox gets 404; the L7 sandbox gets 403.
  * Copilot ACT in governed mode → `degraded`, with 0 DecisionEngine calls and 0 MCP writes.
  * Demo write routes → 503 outside demo mode.
* **Canonical regression suite.** `tests/api/test_canonical_shipped_app.py` and the round-2/3 suites pass. Targeted run: 120 passed, 2 skipped.

## 36. Document Pipeline Regression (§43)

* **Through ModelGateway.** Document LLM inference goes through `src/api/agents/document/model_gateway_adapter.py`. Failures are typed (`MODEL_UNAVAILABLE`, `PROVIDER_FAILURE`, `DEADLINE_EXCEEDED`, `MALFORMED_RESPONSE`), and there is no synthetic APPROVE. Canonical-app tests pass.
* **Outside ModelGateway (P2, N-12 class).** Embedding generation uses the legacy `get_nim_client`. NeMo Parse / Retriever OCR calls hosted endpoints directly via `httpx`.

## 37. Document Auth / Abuse (§44)

* **Unauthenticated upload.** Confirmed.
* **Chunked size bypass: confirmed.** A 60 MB chunked upload (limit 50 MB) with no auth was written to `data/uploads/` in full (62,914,568 bytes). The response was 500 "Document validation failed", but the file stayed on disk.
  * A declared oversize `Content-Length` is refused, but as a 500 wrapping 413 (N-8).
* **Rate limiter: never enforces.**
  * `check_rate_limit`'s `except Exception` (`rate_limiter.py:166`) swallows its own `HTTPException(429)` and fails open.
  * 15 logins against a 5/min limit: 15 × 401, 0 × 429. 15 uploads against a 10/min limit: 0 × 429.
  * 15 log lines read "Rate limit check failed: 429".
* **Ruling: P2-04 confirmed, strongest P2.** This is unauthenticated, unthrottled disk-fill and model-cost abuse on a 0.0.0.0-bound API. It is availability and cost only: the sandbox cannot reach it under the L7 policy, and it grants no authority or integrity bypass. It should be fixed before any non-loopback exposure.

## 38. Legacy Read Exposure (§45)

* **Readable without authentication:**
  * `/api/v1/equipment` and `/equipment/assignments` (asset list, employee assignee IDs)
  * `/inventory/items`
  * `/operations/workforce`
  * `/runtime/status`, `/mcp/status`, `/version/detailed`
* `/health` exposes no secrets.
* The forecasting reads are hard-wired to `localhost:5435`; they were not called (host isolation).
* **Ruling: P2-06** (operational data, read-only).

## 39. Multimodal Path (§46)

* `modality=image`, `video` and `audio` → 503 `MODEL_UNAVAILABLE` ("No enabled policy-eligible model … roles ['nano-omni','super']"). There was no crash.
* `text` → 200.

## 40. Governance Crash Recovery (§47)

* `tests/api/test_round2_governance_recovery.py` covers before accept, after accept / before resume, after resume / before the applied marker, and duplicate delivery. It passes in both full runs and the targeted run.
* There is still no production caller of `recover_accepted_governance` (P2-10, carried).

## 41. Duplicate Write Regression (§49)

* **Package level.** The round-3 unknown-write suite and `tests/unit/reliability/test_ambiguous_write.py` pass.
* **Real MCP integration.** The backend write count was exactly 1 for every transport-ambiguity case: FL-02, FL-04, FL-05, FL-01 concurrent.
* **Exception.** The server-declared-error path produced **2 writes** (FL-07, NEW4-P1-01).

## 42. Test Order Independence (§50)

Each run was a separate process with the CORE CI selection and ignores, `--timeout=120`, the auditor's test DB and no `.env`.

| Order | Result |
|---|---|
| ModelGateway → demo | 558 passed |
| demo → ModelGateway | 558 passed |
| canonical → reliability | 442 passed, 2 skipped |
| reliability → canonical | 442 passed, 2 skipped |
| reversed directories | 2865 / 8 / 0 |
| file shuffle, seed 4401 | 2865 / 8 / 0 |
| file shuffle, seed 5502 | 2865 / 8 / 0 |
| round-3 suites first | 2865 / 8 / 0 |

## 43. Python Tests (§51)

| Run | Result | Time |
|---|---|---|
| Full run 1 | **2865 passed, 8 skipped, 0 failed** | 289.8 s |
| Full run 2 (separate process) | **2865 passed, 8 skipped, 0 failed** | 285.6 s |

* This matches the claimed baseline.
* The 8 skips are stable:
  * legacy migration suite
  * `MAIWSkillAdapter` unavailable
  * 3 × opt-in `MAIW_PHASE20B_NIM_URL`
  * 1 × OpenShell not on the test `PATH` (the auditor deliberately excluded `~/.local/bin` so no test could reach the user's gateway)
  * 2 × opt-in `MAIW_TEST_PG_DSN`
* Coverage flags were omitted. They do not change outcomes.

## 44. UI Tests (§52)

| Check | Result |
|---|---|
| `npm ci` | 1572 packages |
| Jest (`CI=true --watchAll=false`) | **968 / 968** (40 suites) |
| ESLint | **0 errors**, 1043 warnings |
| `npm run build` | success (compiled with warnings, without `CI=true`) |

Node is 24.1.0 here; CI uses 22.

## 45. TypeScript (§52)

`npx tsc --noEmit`: exit 0, **0 errors**.

## 46. npm Audit (§53)

* **Totals:** 0 critical, 50 high, 34 moderate, 3 low. `--omit=dev` is identical because the toolchain sits in `dependencies`.
* **The 50 highs** are jest, eslint / @typescript-eslint, react-scripts, webpack-dev-server, http-proxy-middleware, svgo / @svgr and tailwind toolchain.
* **Production-reachable:** `react-router` / `react-router-dom`, moderate only. Classified as P2-15 / N-5.

## 47. Python Security Tools (§54)

| Tool | Status |
|---|---|
| pip-audit 2.10.1 (separate tool venv) | **RUN.** One finding: `pdfminer-six 20251107` PYSEC-2026-1761 (pickle CMap loading; fix 20251230). P2 (NEW4-P2-06). |
| trivy | **NOT AVAILABLE** on the host |
| gitleaks | **NOT AVAILABLE** on the host |

## 48. Secret Scan (§55)

* `git grep` over the tracked tree at HEAD covered code, docs, scripts, artifacts, notebooks and env examples.
* Patterns: `nvapi-`, GitHub PAT/OAuth, AKIA, private keys, Slack, `sk-`, JWT-like strings, and long secret assignments.
* **No real credentials.** Matches were only:
  * the `.env.example` `nvapi-xxx…` placeholders
  * the documented dev JWT fallback string (`src/api/services/auth/jwt_handler.py:110`, `docs/secrets.md:137`, P2-16)

## 49. Commit Hygiene (§56)

There are 32 commits, none with a `Co-Authored-By` trailer.

## 50. CI / Review Status (§57)

* CI is green on `6ad2cbf`, recorded as a claim; the audit's own runs match it.
* There are 0 unresolved review threads.
* The PR is `MERGEABLE` / `CLEAN`.

## 51. 11-P1 Closure Matrix (§58)

| P1 | Origin | Reproduced? | Closed? | Evidence |
|---|---|---|---|---|
| P1-01 ungoverned chat write | #142 | yes | **CLOSED** | no chat route; 404 / 403; copilot ACT degraded; 0 DecisionEngine / MCP |
| P1-02 inference endpoint missing | #142 | yes | **CLOSED** | smoke 401/401/422/422/200; in-sandbox 200 verified |
| P1-03 durable stores not wired | #142 | yes | **CLOSED** | durability tests; journal survived 2 × `kill -9` |
| P1-04 false readiness | #142 | yes | **CLOSED** | §33 matrix |
| P1-05 document MG bypass / mock APPROVE | #142 | yes | **CLOSED** | MG adapter, typed failures (OCR/embedding outside MG: P2) |
| NEW-P1-01 physical model identity | #144 | yes | **CLOSED** | §27 (0 provider calls) + §25 |
| NEW-P1-02 runbook reproducibility | #144 | yes | **CLOSED** | §32 clean shell, preflight 32/0 (local-provider caveat) |
| NEW-P1-03 readiness vs governed writes | #144 | yes | **CLOSED** | §33 governed rows |
| NEW-P1-04 test order | #144 | yes | **CLOSED** | §42 |
| NEW3-P1-01 sandbox → write routes | #145 | yes | **CLOSED** | §9–§13 |
| NEW3-P1-02 ambiguous MCP write | #145 | yes | **CLOSED as raised** (transport ambiguity) | §15–§22; residual server-error branch is **NEW4-P1-01** |

## 52. Remaining P2 Findings

**New P2s (this audit):**

* **NEW4-P2-01.** An `Idempotency-Key` replay of a FAILED write answers `status: no_op` (success semantics) although nothing changed. FL-06; `base.py:561-590`.
* **NEW4-P2-02.** Reconciliation infers causality from state. Another actor's equivalent state gives CONFIRMED_EXECUTED. A write that was applied and then reverted gives CONFIRMED_NOT_EXECUTED, and the resubmission writes again. The forwarded `execution_id` is unused. Labor and wave strategies are weaker (no canonical HTTP write route).
* **NEW4-P2-03.** The shipped equipment MCP server/adapter does not work for `reference_governed`:
  * Its default provider never calls `EquipmentAssetTools.initialize()`, so `sql_retriever` is None.
  * Once initialised, `get_status` fails contract validation against the reference schema (`metadata` is the string `'{}'`, not a dict).
  * labor and wave have no launch entry point.
  * This extends the remaining part of N-9.
* **NEW4-P2-04.** Provider responses are cached before identity verification, so a stale 502 persists for the TTL.
* **NEW4-P2-05.** Readiness shows `CIRCUIT_OPEN` until traffic probes the half-open circuit.
* **NEW4-P2-06.** `pdfminer-six` PYSEC-2026-1761.

**Re-checked P2s:**

* **P2-04 document auth / abuse.** Confirmed and strongest: unauthenticated upload, a chunked 60 MB write persisted past the limit, the rate limiter is self-defeating, and oversize → 500.
* **P2-06 legacy reads.** Confirmed.

**Carried P2s:** P2-09, P2-10, P2-14, P2-15, P2-16, P2-18, P2-20, N-3, N-4 (TCP reachability observed: preflight MCP "reachable" with 0 MCP requests), N-5, N-6, N-7 (`inference.py:323` `!=`), N-10, N-11 (`.env.example` 8001/5435 observed), N-12 (plus document OCR/parse direct `httpx`), R3-O1, R3-O2, R3-O4, R3-O6, and the remaining part of N-9.

## 53. New P0 Findings

None.

## 54. New P1 Findings

* **NEW4-P1-01: server-declared MCP tool error after mutation is classified as a definite failure.**
  * Effect: the target is unblocked, reconciliation is refused, and an operator retry executes a second consequential write (2 backend writes).
  * Evidence: §23 (live FL-07); `packages/maiw-execution/maiw_execution/base.py:154-155`; `packages/maiw-mcp/maiw_mcp/client/client.py:315-317`; `apps/api/maiw_api/routers/executions.py:152-160`; `tests/api/test_round3_unknown_writes.py:525`; the shipped adapter's non-transactional writes.

## 55. Merge Recommendation

**Do not merge PR #143 at `6ad2cbf`.**

* NEW4-P1-01 must be fixed. Classify a post-dispatch server error from a write tool as UNKNOWN unless non-execution is contractually proven, so the target stays blocked and reconcilable. Alternatively, guarantee transactional backends that are idempotent on `execution_id`.
* §35 must be re-run with a hosted or local NIM serving the approved IDs.

## 56. Post-Merge Release-Gate Recommendation

* The candidate is not ready for the post-merge v2.0.1 release gate.
* After the fix, a fifth re-audit should re-run:
  * §27 (Cases A and B, including retry)
  * §19–§26 (regression)
  * §35 with a real provider
  * the full suite and order permutations

## 57. Audit Artifacts

* This document and `artifacts/audit/v2.0.1_fourth_independent_reaudit.json`, on branch `audit/v2.0.1-fourth-independent-reaudit` from `main` @ `944507e`. Only these two files were added.
* **Probes and logs** stay on the host, uncommitted, under `/home/nvidia/maiw-v201-fourth-reaudit/.fourth-probes/` and `.fourth-logs/`. They cover:
  * host inventories (start and end) and the watcher log
  * the runbook transcript (`runbook/exit_codes.txt`)
  * sandbox probes
  * identity, cache, policy and readiness matrices
  * the MCP phase probe
  * MCP backend write logs (`.fourth-state/mcp_live/writes.jsonl`)
  * pytest, Jest, ESLint, tsc, build, npm and pip-audit outputs
* **Cleanup.**
  * Sandboxes `maiw-v201-4th-a` and `-b` deleted.
  * Gateway `maiw-v201-4th-gw` stopped and its network removed.
  * Containers `maiw-v201-4th-db` and `maiw-v201-4th-testpg` removed.
  * All API instances, MCP backends and the fake provider stopped.
  * The runbook `.env` and governed env deleted; the live worktree removed.
  * The final listener, container and network sets equal the start inventory.

## 58. Final Verdict

`MAIW V2.0.1 FOURTH INDEPENDENT RE-AUDIT FAIL`

---

## Appendix: §65 Explicit Answers

| # | Question | Answer |
|---|---|---|
| 1 | Host GPU healthy? | Yes (4 × H100 NVL) |
| 2 | Loaded = installed driver? | Yes, 580.178.04 |
| 3 | Exact SHA `6ad2cbf…` audited? | Yes |
| 4 | SHA unchanged? | Yes (start, mid, end, pre-push) |
| 5 | Fresh clone used? | Yes |
| 6 | All imports from the fresh clone? | Yes (10/10; runbook venv 10/10) |
| 7 | Stray `.env`? | No |
| 8 | All pre-existing listeners inventoried? | Yes |
| 9 | Any off-limits service contacted? | No |
| 10 | Full preflight passed, no skip? | Yes, 32/0 (local-provider caveat) |
| 11 | Clean-shell runbook succeeded? | Yes (local-provider caveat) |
| 12 | Gateway start reproducible from docs? | Yes |
| 13 | Sandbox policy truly inference-only? | Yes (incl. CONNECT / pipelining) |
| 14 | Permissive policy: app auth still blocked writes? | Yes (24/24) |
| 15 | Operator credential absent from sandbox? | Yes |
| 16 | Denied writes stopped before DecisionEngine? | Yes (0) |
| 17 | Denied writes stopped before MCP? | Yes (0) |
| 18 | Warehouse state unchanged on denied writes? | Yes (hash unchanged) |
| 19 | Lost-response real MCP write → UNKNOWN? | Yes (202) |
| 20 | Identical retry blocked? | Yes (409) |
| 21 | Backend write count exactly 1? | Yes for transport ambiguity; **no (2) for the server-error-after-mutation case** |
| 22 | Reconciliation outside demo mode? | Yes |
| 23 | CONFIRMED_EXECUTED correct? | Yes |
| 24 | CONFIRMED_NOT_EXECUTED? | Yes |
| 25 | INDETERMINATE? | Yes |
| 26 | UNKNOWN survived restart? | Yes (after UNKNOWN and in flight) |
| 27 | Duplicate prevented after restart? | Yes |
| 28 | Can a server-returned error happen after mutation? | **Yes** (shown live; the shipped adapter is non-transactional) |
| 29 | If yes, classified safely? | **No: FAILED, mutation=false, unblocked (NEW4-P1-01)** |
| 30 | Reconciliation checks the intended postcondition? | Yes for success (equipment); falls back to NOT_EXECUTED when `pre_status` is missing |
| 31 | Can unrelated drift cause a false CONFIRMED_EXECUTED? | No. Equivalent state from another actor can (P2). |
| 32 | Missing provider model ID fails closed? | Yes |
| 33 | Empty / malformed ID fails closed? | Yes |
| 34 | Mismatched ID fails closed? | Yes |
| 35 | Can a successful reference response have `identity_verified=false`? | No |
| 36 | HIGH / LOW cache entries isolated? | Yes |
| 37 | Resolved physical model in the cache identity? | Yes |
| 38 | Physical-model policy adversarial matrix passed? | Yes |
| 39 | Live Nemotron 3 Super identity matched? | **NOT REPRODUCED** |
| 40 | Live Nemotron 3.5 Lightning identity matched? | **NOT REPRODUCED** |
| 41 | Readiness matrix passed? | Yes |
| 42 | Liveness independent? | Yes |
| 43 | Original FL-01 exploit still closed? | Yes |
| 44 | Document ModelGateway regression passed? | Yes |
| 45 | Unauthenticated document upload still only P2? | Yes (strongest P2) |
| 46 | Chunked upload still bypasses the size limit? | Yes (60 MB persisted) |
| 47 | Rate limiting works? | No (swallows its own 429) |
| 48 | Multimodal path safe? | Yes (`MODEL_UNAVAILABLE`) |
| 49 | Governance crash recovery passed? | Yes (tests) |
| 50 | All order permutations passed? | Yes |
| 51 | Full Python suite passed twice? | Yes, 2865/8/0 ×2 |
| 52 | UI result? | Jest 968/968, ESLint 0 errors, build OK |
| 53 | TypeScript result? | 0 errors |
| 54 | npm critical / high? | 0 / 50 (toolchain) |
| 55 | Production-reachable dependency issue? | react-router moderate; pdfminer-six (P2) |
| 56 | Secret scan result? | Clean (placeholders and dev fallback only) |
| 57 | CI green? | Yes (claim; matches local runs) |
| 58 | Unresolved review threads? | 0 |
| 59 | All 11 P1s closed? | Yes, as raised |
| 60 | New P0? | No |
| 61 | New P1? | **Yes: NEW4-P1-01** |
| 62 | Remaining P2 count? | 6 new + 2 re-checked + 20 carried |
| 63 | PR #143 ready to merge? | **No** |
| 64 | Ready for the post-merge release gate? | **No** |
| 65 | Final verdict? | `MAIW V2.0.1 FOURTH INDEPENDENT RE-AUDIT FAIL` |
