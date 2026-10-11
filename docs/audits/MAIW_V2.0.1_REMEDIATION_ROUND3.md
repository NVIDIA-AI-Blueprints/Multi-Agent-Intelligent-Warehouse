# MAIW v2.0.1 Remediation — Round 3

**Scope:** close the two new P1s (NEW3-P1-01, NEW3-P1-02), the two adjacent
release-critical gaps (N-1 provider identity, N-2 response cache) and the
OpenShell gateway runbook gap (N-9) found by the third independent re-audit of
the frozen PR #143 candidate `86f3004` (`docs/audits/MAIW_V2.0.1_THIRD_INDEPENDENT_REAUDIT.md`
on branch `audit/v2.0.1-third-independent-reaudit`, commit `6205fe6`, verdict
`MAIW V2.0.1 THIRD INDEPENDENT RE-AUDIT FAIL`), on the existing PR #143
branch, and freeze a candidate for a fourth independent re-audit.

This document is remediation evidence, not an audit verdict. It does not edit
PR #142, PR #144, the third-audit branch, `v2.0.0`, or any earlier audit
artifact. Machine-readable companion: `artifacts/audit/v2.0.1_remediation_round3.json`.

| | |
|---|---|
| Repository | NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse |
| PR / branch | #143 / `fix/v2.0.1-canonical-app-remediation` |
| Starting head (audited by the third re-audit) | `86f30040c72f44ee64d52edf135ce61f72851bc2` |
| Last code commit | `608222fc07174355738ca202c18d8292eb6de120` (style-only; the clean-shell runbook ran at `753e3ea`; the governed lifecycle, sandbox probe and lost-response / kill -9 sequence were re-run at `608222f`) |
| Final frozen head | the commit that adds this file, or the later artifact-update commit recorded in the PR and the final report |
| `main` at start | `944507ec914665c6682d39b95e8713355f486598` |
| `v2.0.0` | tag object `0c35a0e` → `816ace73c4561469978094eeedb2641f6db3c4fa` (unchanged; no `v2.0.1` tag) |
| PR #142 / PR #144 heads | `742fd2a` / `80947b0` (unchanged, OPEN) |
| Third-audit branch | `audit/v2.0.1-third-independent-reaudit` @ `6205fe6` (read only; not modified) |
| Host | `epg-tme-smc-h100-02` (shared qualification host; 4 × H100 NVL, driver 580.178.04 healthy) |
| Date | 2026-10-11 |

---

## 1. Executive Summary

| Finding | Status | One line |
|---|---|---|
| **NEW3-P1-01** sandbox reaches operational writes | **CLOSED** | Separate operator write credential checked before governance; sandbox holds only the inference token; OpenShell L7 rule allows only `POST /api/v1/inference`; executors only in governed profiles |
| **NEW3-P1-02** ambiguous MCP write = FAILED, duplicated | **CLOSED** | Real MCP transport classifies post-dispatch failures UNKNOWN; durable journal blocks the target (409) until reconciled; production reconcile route in every profile; write count 1 live |
| **N-1** missing provider identity accepted | **CLOSED** | 502 `MODEL_IDENTITY_UNVERIFIABLE` for missing / empty / non-string; a 200 is always `identity_verified=true` |
| **N-2** cache ignores reasoning / strips timestamps | **CLOSED** | Key = exact prompt + model + thinking mode/budget + routing intent + version; HIGH↔LOW and HIGH↔MEDIUM never share |
| **N-9** gateway prerequisite with no step | **CLOSED** | `reference_gateway.sh start|status|stop`; runbook step 3 + reboot recovery; preflight checks the gateway |

All nine earlier P1s remain closed (§29). No new P0 or P1 known to this
remediation. Live proofs ran against the canonical shipped app
`maiw_api.app:app` on the qualification host with remediation-owned
gateway, sandbox, database, MCP backend and fake provider only.

## 2. Source Identity (§0)

Recorded before any change: PR #143 OPEN at `86f3004…`; branch clean;
`main` `944507e…`; `v2.0.0` → `816ace7…`; no `v2.0.1` tag; PR #142 OPEN at
`742fd2a`, PR #144 OPEN at `80947b0`; third-audit branch `6205fe6` (also on
the remote). Gate passed.

## 3. Historical Evidence Preservation (§1, §2)

No file of PR #142, PR #144 or the third-audit branch was modified; their
branches were not touched; no tag was created or moved; no GitHub Release was
edited. Round 3 adds this document, its JSON, the release-notes draft update,
runbook / `.env.example` changes and code + tests.

Environment: worktree `/home/nvidia/maiw-v201-remediation`, `.venv` (Python
3.12.3); with `env -i` and no `PYTHONPATH`, `maiw_api`, `maiw_models`,
`maiw_agents`, `maiw_execution`, `maiw_mcp`, `maiw_decision`, `maiw_world`,
`maiw_state`, `maiw_skills`, `maiw_contracts` all resolve under the worktree.
The clean-shell reproduction used a separate worktree
`/home/nvidia/maiw-v201-r3-live` (detached at `753e3ea`) whose venv was built
with the runbook's install block verbatim (all ten packages resolve under it).
No `.env` existed in the remediation worktree during any pytest run (the
runner refuses otherwise).

---

## 4. Sandbox Authority Boundary — NEW3-P1-01

Root causes (third re-audit §55): (1) the OpenShell policy granted `access:
full` to the API host:port; (2) the governed equipment write routes had no
caller authentication; (3) `bootstrap.py` built executors whenever an MCP URL
was set, so the plain `reference` profile executed writes while readiness said
`governed_write_path: not_offered`. All three are fixed; the invariant is
layered:

```
sandbox ──(L7 policy: only POST /api/v1/inference)──► API port
                                                        │
          /api/v1/inference ← X-Maiw-Internal-Token (sandbox credential)
          /api/v1/equipment/{assign,release,maintenance},
          /api/v1/executions/** ← X-Maiw-Operator-Token (host operator only)
                                                        │  (auth first, then profile gate)
                                         agent → DecisionEngine → executor → MCP
```

### 4.1 Operational write authentication (§5, §7) — `apps/api/maiw_api/write_auth.py`

* `MAIW_OPERATOR_WRITE_TOKEN` / header `X-Maiw-Operator-Token`; constant-time
  compare; never logged or echoed.
* Route-level dependency (`dependencies=[require_operator_write,
  require_governed_writes_offered]`), so it is resolved before body parsing
  and before any agent, DecisionEngine, ActionExecutor or MCP call (§42).
* Denials: no header → 403 `OPERATOR_WRITE_CREDENTIAL_REQUIRED`; wrong value
  (including the inference token) → 401 `INVALID_OPERATOR_WRITE_CREDENTIAL`;
  unset / < 32 chars / `.env.example` placeholder / **equal to the inference
  token** → 503 `OPERATOR_WRITE_AUTH_NOT_CONFIGURED`; profile without governed
  writes → 503 `GOVERNED_WRITES_NOT_OFFERED` (after auth).
* A missing header is 403 (not 401) so a logged-in UI session is not logged
  out by the UI's 401 handler; a JWT alone never authorises a write.
* Existing infrastructure reused: the same pattern as the inference token
  (fail closed, env-configured), the app's exception handlers; no new IAM.

### 4.2 Route inventory (§6) — canonical app, 150 mounted method/path pairs

| Route | Method | Auth | Governance | Executor path |
|---|---|---|---|---|
| `/api/v1/equipment/assign` | POST | **operator** | DecisionEngine (MEDIUM → human approval) | EquipmentActionExecutor only if APPROVED |
| `/api/v1/equipment/release` | POST | **operator** | DecisionEngine (LOW → auto) | EquipmentActionExecutor if APPROVED |
| `/api/v1/equipment/maintenance` | POST | **operator** | DecisionEngine (always human) | none (never auto-executes) |
| `/api/v1/executions/{id}/reconcile` (+ GET `/executions`, `/executions/{id}`) | POST/GET | **operator** | n/a (records reconciliation; reads only) | none |
| `/api/v1/inference` | POST | inference token | none | none |
| `/api/v1/demo/*` (scenario, tick, inject, analyze, approve, reject, reconcile) | POST | none | demo only — 503 unless `MAIW_DEMO_MODE`; preflight now FAILs `MAIW_DEMO_MODE` for reference deployments | simulation providers (in-memory MCP overrides URLs) |
| `/api/v1/copilot/turn` | POST | none | ACT only with the demo orchestrator | simulation |
| `/api/v1/auth/{login,refresh,register,me,change-password,users/{id}}` | POST/PUT | credentials / JWT / admin | identity | none |
| `/api/v1/document/{upload,approve/{id},reject/{id}}` | POST | none | document-workflow state | none (P2-04/P2-09, §29) |

`tests/api/test_canonical_shipped_app.py::test_p1_01_mutating_route_inventory_is_exactly_classified`
pins the inventory; `tests/api/test_round3_write_auth.py` pins the auth
dependencies and their order.

### 4.3 Profile / behaviour agreement

Executors (equipment, labor, wave) are built only when the active profile
offers governed writes (`reference_governed`, `demo`). Live: `reference` with
`MAIW_MCP_SERVER_EQUIPMENT_URL` set → MCP equipment `READY` (reads),
`governed_write_path: not_offered`, operator-authenticated release → 503
`GOVERNED_WRITES_NOT_OFFERED`. `reference_governed` readiness now also needs a
usable operator credential (`governed_write_path.missing: [operator_write_auth]`).

### 4.4 Sandbox credential isolation (§9)

The sandbox receives only the inference token (stdin, never argv). The
in-sandbox probe reports environment variable **names** matching
KEY/TOKEN/SECRET/PASS/NVAPI/OPERATOR/CRED (live: `[]`) and **SHA-256 digests**
of every value; `reference_sandbox.sh probe` compares them with digests of
`MAIW_OPERATOR_WRITE_TOKEN`, `NVIDIA_API_KEY`, `MAIW_NIM_API_KEY`,
`POSTGRES_PASSWORD`, `JWT_SECRET_KEY` and fails on a match. Live result
(reference and reference_governed): "host secrets present in sandbox = none".
MCP servers have no credentials; the DB password never enters the sandbox.

### 4.5 OpenShell policy semantics (§4, §10)

OpenShell 0.0.116 supports L7 REST rules (`protocol: rest`, `rules: - allow:
{method, path}`; the NemoClaw presets use the same schema). The template now
allows exactly `POST /api/v1/inference` on the API host:port (no `access:`
key). Evidence that it is enforced on plain HTTP:

* fresh sandbox `maiw-v201-r3-a`: inference 200; `GET /api/v1/ready`,
  legacy chat / inventory / migrate and every write route → **403 from the
  sandbox proxy** (the app would have answered 200/404/503/401);
* 33 path / method bypass attempts through the proxy (`/api/v1/inference/../…`,
  `%2e%2e`, upper case, `//`, `./`, query tricks, `%2F`, PUT/GET,
  `X-HTTP-Method-Override`): 29 × 403, 3 × 400 (`%2F` rejected by the proxy),
  1 × 422 (`POST /api/v1/inference?/../../equipment/release` is the inference
  route; body rejected). App refusals 0, DecisionEngine 0, MCP writes 0.

The network rule is one layer. Application authentication is the path-level
authority boundary: with a **deliberately broad** sandbox policy
(`maiw-v201-r3-b`, round-2 template `access: full`) the same probe reached
the app (readiness 200, chat 404) and every write was denied by the app (403
/ 401 for the inference token sent as operator header), 16 refusals logged,
**0 DecisionEngine invocations, 0 MCP writes**.

### 4.6 Live sandbox write-denial proof (§8, §11, §39, §41, §42)

| Caller | Inference | Read | Governed write |
|---|---|---|---|
| Sandbox, inference credential (L7 policy) | 200, Super/Lightning identity verified | 403 (proxy; reads not in the sandbox's allowance) | 403 (proxy) for none / internal-header / operator-header / bearer; `/executions/*/reconcile` 403 |
| Sandbox, broad policy (app layer only) | 200 | 200 (`/ready`) | 403 `OPERATOR_WRITE_CREDENTIAL_REQUIRED` (none, internal header, bearer); 401 `INVALID_OPERATOR_WRITE_CREDENTIAL` (inference token as operator header) |
| Host, unauthenticated | 401 | 200 (legacy reads are unauthenticated — P2-06) | 403 `OPERATOR_WRITE_CREDENTIAL_REQUIRED` |
| Host, inference token (`X-Maiw-Internal-Token`) | 200 | 200 | 403 `OPERATOR_WRITE_CREDENTIAL_REQUIRED` |
| Host, inference token as `X-Maiw-Operator-Token` | 401 | 200 | 401 `INVALID_OPERATOR_WRITE_CREDENTIAL` |
| Host operator (`X-Maiw-Operator-Token`) | 401 (not an inference credential) | 200 | governed: assign → 200 `requires_human_approval` (1 DecisionEngine call, 0 MCP writes); release → executed / UNKNOWN per §5 |
| Internal executor | n/a | n/a | governed execution after APPROVED only |

Denied writes from all non-operator callers: **DecisionEngine invocations
added 0, MCP writes added 0, auth refusals logged 12** (host matrix) — and the
CI test `test_sandbox_credentials_cannot_reach_any_write_path` spies on the
real runtime objects: agent 0, DecisionEngine 0, executor 0, MCP client 0
calls for 18 denied requests (6 credential variants × 3 routes) plus a
malformed body.

### 4.7 Preflight / smoke / UI

* Preflight: `MAIW_OPERATOR_WRITE_TOKEN` checked with the app's own rule
  (FAIL in `reference_governed` when unset, short, placeholder or equal to the
  inference token — both negatives verified live, exit 1); `MAIW_DEMO_MODE`
  must be off.
* Smoke: new "Operational write boundary" section — all three routes denied
  with no credential, the inference token, and the inference token as the
  operator header; in `reference_governed` the operator credential is
  accepted with an empty body (422, nothing proposed). Live: 17/17
  (`reference`), 18/18 (`reference_governed`).
* UI: the operator credential never enters the browser bundle (test scans
  `src/` for `REACT_APP_*` tokens and header setters); the CRA dev proxy
  strips any browser-supplied operator header and, only when
  `MAIW_UI_OPERATOR_WRITE_TOKEN` is set in the dev-server process, adds it
  server-side for the three equipment write routes (localhost operator
  console). `EquipmentNew` now shows write errors (they were silent);
  `describeOperationalWriteError` explains 403 / 503 / 409.

---

## 5. MCP Ambiguous Write Semantics — NEW3-P1-02

Root cause (third re-audit §30): only the test double `AmbiguousWriteError`
mapped to UNKNOWN; every real transport error after dispatch fell into the
generic branch → `FAILED`, `physical_mutation_occurred=False`; reconciliation
existed only behind `/api/v1/demo/reconcile`; no identity reached the backend
(`execution_id: null`) and nothing stopped a retry.

### 5.1 Transport outcome semantics (§13, §14) — `maiw_mcp/client/client.py`, `maiw_mcp/errors.py`

`MAIWMCPClient._call_tool` records the phase of every failure:

| Phase | Failure | Raised | Outcome |
|---|---|---|---|
| connect / session handshake (`tools/call` not yet sent) | refused, TLS/HTTP error, handshake error | `MCPConnectFailed` (`MCPUnavailable` + `MCPNotDispatched`) | FAILED, `MCP_NOT_DISPATCHED` |
| connect / handshake | timeout | `MCPConnectTimeout` (`MCPTimeout` + `MCPNotDispatched`) | FAILED, `MCP_NOT_DISPATCHED` |
| circuit open | — | `MCPCircuitOpen` (`MCPUnavailable` + `MCPNotDispatched`) | FAILED, `MCP_NOT_DISPATCHED` |
| `tools/call` dispatched | reset, EOF, server crash, protocol error | `MCPResponseLost` (`MCPUnavailable` + `MCPDispatchOutcomeUnknown`) | **UNKNOWN**, `MCP_RESPONSE_LOST` |
| `tools/call` dispatched | read timeout | `MCPTimeoutAfterDispatch` (`MCPTimeout` + `MCPDispatchOutcomeUnknown`) | **UNKNOWN** |
| result received | teardown error | logged; result returned | per result |
| result received | unreadable result | `MCPContractError` | **UNKNOWN**, `MCP_RESPONSE_UNREADABLE` |
| result received | tool error (`is_error`) | `MCPToolError` | FAILED, `MCP_TOOL_ERROR` (server-reported) |

The new classes subclass the existing ones, so read paths that catch
`MCPUnavailable` / `MCPTimeout` are unchanged. `maiw_execution.classify_write_failure`
is the single mapping (an unclassified `MCPTimeout` is UNKNOWN; a generic
exception from non-transport code stays FAILED, as before). The UNKNOWN
result has `executed=False` internally (derived) but the HTTP route reports
`"executed": null` with `"status": "unknown"`, `"reconciliation_required": true`,
`"retried": false`, HTTP **202**; `physical_mutation_occurred` is `None`
(unknown), not `False`.

### 5.2 No blind retry; duplicate requests (§15, §23)

* No code path retries a write (the client, skill and executor call once).
* `ExecutionRegistry.begin()` refuses any new write to the same domain target
  (e.g. equipment `FL-01`) while an earlier record is in flight or UNKNOWN and
  not definitively reconciled — even under a new proposal, decision and
  execution_id. The equipment routes check this **before** the agent runs:
  409 `RECONCILIATION_REQUIRED` with the blocking `execution_id` (0
  DecisionEngine invocations, live).

### 5.3 Durable journal; crash / restart (§22)

`JsonFileExecutionRegistry` (`$MAIW_PERSISTENCE_ROOT/executions/<domain>/<execution_id>.json`):
written and fsynced at `begin()` — **before** the MCP request is sent — and on
every transition. On startup a record without an outcome (process died while
the write may have been on the wire) becomes UNKNOWN
(`recovered_after_restart=true`); an unreadable record raises
`ExecutionJournalError` so the executor is not built and readiness fails
(fail closed). Readiness reports `governed_write_path.execution_journal`.

### 5.4 Production reconciliation (§16, §17, §18)

`apps/api/maiw_api/routers/executions.py` (operator credential, every
profile): `GET /api/v1/executions[?status=unresolved|all]`,
`GET /api/v1/executions/{id}`, `POST /api/v1/executions/{id}/reconcile`. The
strategies moved from the demo router to `apps/api/maiw_api/reconciliation.py`
(shared; the demo route delegates). Equipment: the executor records the
asset's pre-write status in the intent (`pre_status`); reconciliation reads
`warehouse.equipment.get_status` through the MCP client:

| Authoritative state | Result |
|---|---|
| intended status (and assignee) | `confirmed_executed` |
| unchanged from `pre_status` | `confirmed_not_executed` |
| changed to anything else / asset missing / read failed | `indeterminate` (target stays blocked) |

The record keeps the original `execution_id`, `proposal_id`, `decision_id`,
`trace_id` and `idempotency_key`; the original `unknown` outcome is never
rewritten; nothing is re-executed. Identity reaching the backend: the MCP
write tools (equipment assign/release/maintenance, labor allocate, wave
reprioritize) now accept and forward `execution_id` (live write log shows the
API's `execution_id`, `proposal_id`, `decision_id`). `X-Trace-Id` and
`Idempotency-Key` headers are honoured (same key after a completed write →
`no_op` replay, no second write — CI).

### 5.5 Live MCP ambiguity matrix (§19–§23, §40) — `reference_governed`, real streamable-HTTP MCP

Backend: the repository's own `mcp_servers.equipment.server` module in a
separate process (`tests/api/round3_mcp_backend.py`) with a durable state file
that applies each write, on 127.0.0.1:18940. API started by the runbook
scripts on :18935.

| Case | Result | Writes applied |
|---|---|---|
| Lost response (`crash_after_write`) | 202 `unknown`, `executed: null`, `MCP_RESPONSE_LOST`, 0.15 s; backend crashed after applying | 1 |
| …identical request before reconciliation | 409 `RECONCILIATION_REQUIRED` (same execution_id), 0 DecisionEngine calls | 1 |
| …reconcile while backend down | `indeterminate` (MCP connect failed), still blocked (retry 409) | 1 |
| …backend back, reconcile | `confirmed_executed`, `effectively_executed`, same proposal/decision/trace ids | **1** |
| Crash/restart: UNKNOWN, then `kill -9` of the API, `start_reference_deployment.sh` | journal lists the execution (same ids), retry 409, reconcile `confirmed_executed` | **1** |
| In-flight crash (`hang_after_write`, API `kill -9` mid-request) | on-disk record `outcome: null` → after start `unknown`, `recovered_after_restart: true`; retry 409; reconcile `confirmed_executed` | **1** |
| Sent, not applied (`crash_before_write`) | 202 `unknown`; reconcile `confirmed_not_executed` (`pre_status: assigned`); a new request then executes once | 0, then 1 |
| MCP down (request never sent) | 400 "State assembly failed … before tools/call was sent"; no record, no write | 0 |
| Never dispatched at the executor (CI, real client → closed port; open circuit) | FAILED `MCP_NOT_DISPATCHED`, `physical_mutation_occurred=False`, target not blocked | 0 |
| Read timeout after dispatch (CI, real client) | `MCPTimeoutAfterDispatch` → UNKNOWN | 1 |
| **Re-run at final code `608222f`**: lost response → duplicate → reconcile (backend down) → API `kill -9` + `start` → duplicate → reconcile (backend up) | 202 `unknown` → 409 (0 DecisionEngine calls) → `indeterminate` → 409 → `confirmed_executed` | **1** |

Per-execution write counts from the backend log: `9fc0db71…` 1,
`20d9a5fc…` 1, `2986cc0f…` 1 (none duplicated).

---

## 6. Provider Identity Fail-Closed — N-1 (§24, §25)

`DeploymentResolver.verify_response_identity` returns True only for the exact
dispatched ID; missing / empty / whitespace → `ModelIdentityUnverifiable`
(`MISSING`), non-string → (`MALFORMED`), any other string →
`ModelIdentityMismatch`. The gateway passes the raw reported value;
`NIMClient` keeps only a non-empty string. `POST /api/v1/inference` → 502
`MODEL_IDENTITY_UNVERIFIABLE`, content discarded. Applies to every profile
(there is no unverified success path).

Live fake-provider matrix (canonical app on :18931, remediation-owned fake
provider on :18901, cache off):

| Provider reports | HTTP / code | Provider calls | Received |
|---|---|---|---|
| dispatched ID (high / low) | 200 / 200, `identity_verified=true` | 1 / 1 | Super / Lightning |
| another approved ID (Lightning for a Super request) | 502 `MODEL_IDENTITY_MISMATCH` | 1 | Super |
| unapproved ID | 502 `MODEL_IDENTITY_MISMATCH` | 1 | Super |
| case variant | 502 `MODEL_IDENTITY_MISMATCH` | 1 | Super |
| no `model` field | 502 `MODEL_IDENTITY_UNVERIFIABLE` | 1 | Super |
| `""`, `"   "`, `null`, `123`, `["x"]`, `{"id": …}` | 502 `MODEL_IDENTITY_UNVERIFIABLE` (each) | 1 | Super |

## 7. Response Cache Isolation — N-2 (§26, §27)

`maiw_models/providers/nim_client.py`: one key for lookup and store over the
exact messages, all sampling parameters, the dispatched model, the resolved
thinking mode and budget, `cache_scope` from `NIMProvider` (reasoning level,
risk level, modality, deployment mode, logical role, generation, resolved
model) and `CACHE_KEY_VERSION`. Timestamp / UUID / date normalisation was
removed.

Live (cache enabled, default TTL):

| Sequence | Provider calls | Routed / answered by |
|---|---|---|
| HIGH, LOW, HIGH, LOW | 1, 1, 0, 0 | Super (thinking), Lightning, Super (cached), Lightning (cached) |
| LOW, HIGH, LOW, HIGH | 1, 1, 0, 0 | Lightning, Super, Lightning (cached), Super (cached) |
| HIGH, MEDIUM, MEDIUM | 1, 1, 0 | Super `thinking=budget`, Super `thinking=off`, cached `off` |
| two prompts differing only by an ISO timestamp | 1, 1 | Lightning, Lightning |

Hosted NIM, in-sandbox after restart: smoke MEDIUM miss → HIGH miss (did not
reuse MEDIUM) → MEDIUM hit → LOW miss (Lightning).

## 8. OpenShell Gateway Reproducibility — N-9 (§28)

`scripts/setup/reference_gateway.sh start|status|stop`, modes `managed`
(default: this deployment's own `openshell-gateway` 0.0.116 on
`127.0.0.1:MAIW_OPENSHELL_GATEWAY_PORT`, docker driver, own sandbox namespace,
docker network, Ed25519 JWT via `openssl`, sqlite state under
`$MAIW_PERSISTENCE_ROOT/openshell-gateway/`) and `external` (verify only;
never starts/stops someone else's gateway). Verification = process (managed)
+ CLI 0.0.116 + `openshell status` + `sandbox list` against
`OPENSHELL_GATEWAY_ENDPOINT`. Stop signals only the recorded PID whose
cmdline names its config; removes its network only when empty. Preflight now
FAILs when the gateway is unreachable.

Live (own gateway `maiw-v201-r3-gw`, :18993): start 0 → status 0 → (whole
runbook) → stop (simulated outage) 0 → status 1 → preflight 1 ("OpenShell
gateway not reachable … run reference_gateway.sh start") → start 0 → status
0. Finding: a stopped gateway leaves its sandbox in `Error` (cannot be
`start`ed) → runbook "Host reboot / OpenShell gateway restart" documents
delete + create; verified (sandbox recreated, preflight 32/32). The user's
gateway `nemoclaw-8991` was never started, stopped, queried or reconfigured.

---

## 9. Prior Physical Model Policy (§30, §31)

Approved families unchanged (Nemotron 3 / 3.5). Round-2 resolver regressions,
live on the canonical app: `NEMOTRON_SUPER_MODEL=example-org/unapproved-model-x`
→ 503 `MODEL_POLICY_VIOLATION`, 0 calls, `/ready` 503; look-alikes (`…-v2`,
upper case) → 503, 0 calls; cross-role (Super ← Lightning ID) → 503, 0 calls;
Ultra enabled with `totally-unknown/model-d` (judge task) → 503, 0 calls;
`LLM_MODEL` / `MAIW_NIM_MODEL` set → not dispatched (Super ID sent); provider
substitution → 502 (§6).

## 10. Runbook Reproduction (§32)

Clean shell (`env -i` with scratch `HOME`, `PATH`, `LANG`, `PIP_CACHE_DIR`),
fresh worktree `/home/nvidia/maiw-v201-r3-live` @ `753e3ea`, commands from the
runbook's clean-host procedure:

| # | Command | Exit |
|---|---|---|
| 1 | `python3 -m venv .venv`; `pip install -r requirements.txt`; 8-package loop; agents + api | 0 / 0 / 0 / 0 |
| 2 | `cp .env.example .env` + edit the listed variables (fresh random tokens; provider key copied, never printed) | 0 |
| — | `bash scripts/validate_reference_runbook.sh` | 0 |
| 3 | `reference_gateway.sh start` / `status` | 0 / 0 |
| 4 | `reference_db.sh up` (`maiw-v201-r3-db`, 127.0.0.1:55463) | 0 |
| 5 | `reference_sandbox.sh create` (`maiw-v201-r3-a`, L7 policy) | 0 |
| 6 | `preflight_reference_deployment.sh` — **32 passed, 0 failed, no skip** | 0 |
| 6 | `start` / `status` / `smoke` (17/17) | 0 / 0 / 0 |
| 7 | `reference_sandbox.sh probe` (inference 200 Super verified; all writes denied; no host secret) | 0 |
| 8 | `restart` (preflight 32/0 first) / `status` / `smoke` (17/17) / `stop` | 0 / 0 / 0 / 0 |
| — | `status` after stop | 1 (NOT RUNNING, as designed) |

`reference_governed` (same deployment, `MAIW_ENV_FILE=governed.env`):
preflight 32/0 (0), negative preflights (token unset / equal to inference
token) exit 1, start 0, status 0, smoke 18/18, probe 0, two restarts after
`kill -9` 0, stop 0.

## 11. Readiness (§33)

Live, canonical app on :18932 (own DB, sandbox, gateway, MCP backend):

| Row | `/ready` | failed_components | `/live` |
|---|---|---|---|
| reference baseline (DB + required sandbox) | 200 | — (`governed_write_path: not_offered`) | 200 |
| DB container paused | 503 | `database` | 200 |
| persistence `governance/` chmod 000 | 503 | `persistence` | 200 |
| required sandbox stopped | 503 | `sandbox_runtime` | 200 |
| reference + optional MCP URL | 200 | — (equipment READY; operator write → 503 `GOVERNED_WRITES_NOT_OFFERED`) | 200 |
| reference_governed, MCP healthy, write token | 200 | — (`governed_write_path: ready`) | 200 |
| reference_governed, write token missing | 503 | `governed_write_path` (`operator_write_auth`); write → 503 `OPERATOR_WRITE_AUTH_NOT_CONFIGURED` | 200 |
| reference_governed, write token == inference token | 503 | `governed_write_path` | 200 |
| reference_governed, required MCP unreachable | 503 | `governed_write_path`, `mcp_domains` (FAILED) | 200 |
| reference_governed, required MCP unset | 503 | `governed_write_path`, `mcp_domains` | 200 |
| unapproved model binding | 503 | `model_gateway` | 200 |
| invalid profile | 503 | `profile` | 200 |
| optional sandbox absent | 200 | — (`sandbox_runtime: degraded`) | 200 |

## 12. Test Order Independence (§34) and Python Tests (§35)

All runs: fresh process, CORE CI selection and ignores from `ci-cd.yml`,
`--timeout=120`, `DATABASE_URL` → remediation-owned disposable Postgres
(`maiw-v201-r3-testpg`, 127.0.0.1:55462), no `.env`, on the last code commit
`608222f`.

| Run / order | Result |
|---|---|
| Full run 1 (CI order) | **2865 passed, 8 skipped, 0 failed** (2873), 285 s |
| Full run 2 (CI order, separate process) | **2865 passed, 8 skipped, 0 failed**, 276 s |
| ModelGateway → demo | 191 passed |
| demo → ModelGateway | 191 passed |
| canonical app → reliability | 442 passed, 2 skipped |
| reliability → canonical app | 442 passed, 2 skipped |
| reversed directories (agents, api, mcp, contract, unit) | 2865 / 8 / 0 |
| ModelGateway first (full) | 2865 / 8 / 0 |
| reliability first (full) | 2865 / 8 / 0 |
| canonical first (full) | 2865 / 8 / 0 |
| round-3 suites first (full) | 2865 / 8 / 0 |
| seeded file shuffle, seed 3301 | 2865 / 8 / 0 |
| seeded file shuffle, seed 4417 | 2865 / 8 / 0 |

The same two full runs at `36b2351` (before the style-only commit) were also
2865 / 8 / 0. Baseline at `86f3004`: 2805 / 8 / 0 — +60 round-3 tests, skip
count unchanged. Opt-in Postgres tests against the remediation reference DB
(`MAIW_TEST_PG_DSN` + `PGHOST`/`PGPORT`/`POSTGRES_PASSWORD`, N-3): 2 passed.

Skips (8, stable): legacy `test_migration_system`; `MAIWSkillAdapter`
unavailable; 3 × opt-in `MAIW_PHASE20B_NIM_URL`; 1 × OpenShell not on the
test PATH; 2 × opt-in `MAIW_TEST_PG_DSN`. New round-3 tests: 60
(`tests/api/test_round3_write_auth.py` 18, `test_round3_unknown_writes.py`
12, `test_round3_identity_and_cache.py` 20, `tests/unit/test_round3_gateway_script.py`
9, +1 lifecycle-script parametrisation); updated: existing equipment/readiness/
identity tests and model-gateway fakes (they now report the dispatched model
identity like a real provider).

## 13. UI, TypeScript, npm (§36, §37)

| Check | Result |
|---|---|
| Jest (`CI=true --watchAll=false`) | **968 / 968** (40 suites; +4 round-3) |
| ESLint | **0 errors** (1043 warnings) |
| `tsc --noEmit` | **0 errors** |
| `npm run build` | OK (compiled with warnings; without `CI=true`, as before) |
| `npm audit` (fresh) | 0 critical, 50 high, 34 moderate, 3 low; `--omit=dev` identical because the toolchain is in `dependencies`; all 50 highs are jest / eslint / react-scripts / webpack-dev-server / svgo / tailwind toolchain; production-reachable: `react-router(-dom)` **moderate** only. No `npm audit fix --force`. |

## 14. Host Safety (§38)

* Listener inventory before any live work (`/proc/net/tcp*`; `ss` not
  permitted): 22, 53 (127.0.0.53/54), 32768, 32769 (nemo-microservices
  postgres / guardrails). Docker: `nemoclaw-llama-cpp` up, everything else
  listed in the audit exited. All off-limits.
* Remediation-owned: API 18935 (runbook), 18931 / 18932 (probe instances),
  gateway 18993 (+ docker bridge callback), reference DB 55463
  (`maiw-v201-r3-db`), test DB 55462 (`maiw-v201-r3-testpg`), MCP backend
  18940, fake provider 18901, closed probe ports 1 / 18949, gateway test 18992,
  CI-style tests on random loopback ports.
* Contamination guard: `/proc/net/tcp*` sampled every 50 ms for the whole
  session (v1: any socket to a watched port; v2 from 03:36Z: client-side
  sockets only). Hits: (a) 03:24:29Z, loopback, *remote* port 32776 — a CI
  test's own ephemeral-port server socket (nothing listens on 32776; the
  container that once published it is exited) — false positive, v2 excludes
  server-side sockets; (b) 03:57:20Z, `10.185.115.61 → 140.82.112.4:22` —
  `git push` to github.com. **No pre-existing host service was contacted; no
  contamination incident.**
* Never touched: `nemoclaw-8991` (no `openshell` call ran without
  `OPENSHELL_GATEWAY_ENDPOINT` pointing at the remediation gateway),
  `maiw-qual-20c-b`, `nemoclaw-llama-cpp`, `cuopt`, `wms-nim-*`,
  `nemo-microservices-*`, Postgres 5435, ports 8000–8020.
* Secrets: fresh random inference / operator / DB / JWT values in 0600 files
  under the session scratchpad; never printed (all probe outputs are asserted
  free of them); `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED` never set; the
  operator token never entered a sandbox.

### Cleanup (spec §39, host safety)

Runbook teardown (clean shell): `reference_sandbox.sh delete` 0,
`reference_db.sh down` 0, `reference_gateway.sh stop` 0 (network removed).
Also removed: sandbox `maiw-v201-r3-b` (broad-policy proof), test DB
`maiw-v201-r3-testpg`, the gateway test instance on :18992, the MCP backend,
the fake provider, every probe app instance, the live worktree and its `.env`,
the governed env file, the generated tokens and the gateway JWT keys. Post-run
listener set and Docker container / network sets are identical to the
pre-run inventory (the pre-existing `nemoclaw-llama-cpp` restart loop is
unchanged).

## 15. Remaining P2 Findings and Observations

Carried (unchanged, recorded per spec §29 — not redesigned): P2-04
(unauthenticated upload, chunked size bypass, rate limiter not enforcing,
oversize → 500 wrapping 413 N-8), P2-06 (unauthenticated legacy reads;
forecasting hard-wired to `localhost:5435`/`:6379`), P2-09 (document
approve/reject stubs, `/document/analytics`), P2-10 (no HTTP procedure start
/ governance submit; `recover_accepted_governance` has no production caller),
P2-14 (root `Dockerfile` omits `apps/`), P2-15 (50 npm toolchain highs),
P2-16 (dev JWT fallback), P2-18 (v2.0.0 release body), P2-20 (plain-HTTP
provider URL warns), N-3 (opt-in PG readiness test needs PGHOST/PGPORT), N-4
(MCP readiness is TCP reachability until the circuit opens), N-5
(react-router moderate), N-6 (build fails with `CI=true`), N-7 (inference
token compared with `!=`), N-10 (`cleanup_for_testing.sh` kills by name), N-11
(`.env.example` port defaults), N-12 (embedding service outside the approved
table; `evaluate_with_model(allow_out_of_policy=True)`), and the
`reference_governed` MCP-server launch command (remaining part of N-9).

Closed this round: N-1, N-2, N-9 (gateway part), P2-03 (execution identity now
forwarded, idempotency key honoured), P2-17 (release-notes staleness and
missing limitations updated).

New observations (P2 / informational):

* **R3-O1** Managed gateway is loopback-only, TLS off, unauthenticated local
  users (single-node reference). Documented; use an external mTLS gateway on
  multi-user hosts.
* **R3-O2** Execution journal and unresolved-target guard are single-node
  (same scope as the procedure store).
* **R3-O3** `MCPToolError` (server answered with a tool error) is treated as a
  definite failure; a backend that partially applies a write and then raises
  would be misreported — backends must be transactional.
* **R3-O4** Demo routes (simulation only, 503 unless `MAIW_DEMO_MODE`) stay
  unauthenticated; preflight now refuses `MAIW_DEMO_MODE` for reference
  deployments; in demo mode the in-memory MCP servers override configured
  URLs, so demo writes cannot reach a real backend.
* **R3-O5** Equipment reconciliation compares status/assignee with the
  recorded pre-write status; a concurrent third-party change yields
  `indeterminate` (safe: the asset stays blocked for an operator).
* **R3-O6** The legacy `src/api/services/llm/nim_client.py` (not on the
  canonical ModelGateway path) keeps its old cache key.

## 16. P0 / P1 Findings

* P0: none.
* P1: none known to this remediation. NEW3-P1-01 and NEW3-P1-02 closed (§4,
  §5).

## 17. Closure Matrices

### Round-3 closure matrix (§45)

| Finding | Root cause | Fix | Regression test | Live evidence | Status |
|---|---|---|---|---|---|
| NEW3-P1-01 sandbox operational-write access | `access: full` policy; no caller auth on write routes; executors wired by MCP URL in any profile | operator write credential (route dependency, before governance); L7 policy `POST /api/v1/inference` only; executors only in governed profiles; probe/preflight/smoke checks | `tests/api/test_round3_write_auth.py` (18) | fresh sandbox: all writes 403 (proxy); broad-policy sandbox: app 403/401, 0 DecisionEngine, 0 MCP; host matrix §4.6; reference+MCP URL → 503 not offered | **CLOSED** |
| NEW3-P1-02 ambiguous MCP write classification | only a test double mapped to UNKNOWN; reconcile demo-only; no identity / duplicate guard | dispatch-phase errors; `classify_write_failure`; durable journal + target guard; production reconcile route; `execution_id` forwarded | `tests/api/test_round3_unknown_writes.py` (12) | §5.5: UNKNOWN → 409 → reconcile CONFIRMED_EXECUTED, write count 1 (×3 incl. kill -9 and in-flight crash); not-applied → CONFIRMED_NOT_EXECUTED; backend down → INDETERMINATE | **CLOSED** |
| N-1 missing provider identity | `None`/`""` returned False and was accepted | `ModelIdentityUnverifiable` (MISSING / MALFORMED) → 502 | `tests/api/test_round3_identity_and_cache.py`, `tests/unit/test_round2_deployment_resolver.py` | §6 matrix (missing + 6 malformed → 502) | **CLOSED** |
| N-2 cross-reasoning cache reuse | key lacked thinking mode/budget; prompts normalised | exact prompt + model + thinking + routing scope + version | `tests/api/test_round3_identity_and_cache.py` | §7 HIGH↔LOW both orders, HIGH→MEDIUM, timestamps | **CLOSED** |
| N-9 OpenShell gateway reproducibility | prerequisite without a step | `reference_gateway.sh`; runbook steps + reboot recovery; preflight gateway check | `tests/unit/test_round3_gateway_script.py` (9) | §8 start/status/stop/outage/recovery; clean-shell runbook | **CLOSED** |

### Prior nine-P1 regression matrix (§46)

| P1 | Re-verified on round 3 | Status |
|---|---|---|
| P1-01 ungoverned chat write | route inventory test; smoke `POST /api/v1/chat` 404; sandbox legacy chat/inventory/migrate 403 (proxy) / 404 (broad) | CLOSED |
| P1-02 inference endpoint | smoke 401 / 401 / 422 / 422 / 200 twice; sandbox 200 with identity | CLOSED |
| P1-03 durable stores | canonical-app CI tests (procedure / governance state survive restart, replay dropped) pass; live: the persistence root survived two `kill -9` restarts (execution journal records, same ids) | CLOSED |
| P1-04 false readiness | §11 matrix (13 rows) | CLOSED |
| P1-05 document ModelGateway | canonical-app tests (typed failures, 1 gateway call) | CLOSED |
| NEW-P1-01 physical model identity | §9 resolver regressions + §6 identity matrix + live Super/Lightning | CLOSED |
| NEW-P1-02 runbook reproducibility | §10 clean shell, full preflight 32/0, no skip | CLOSED |
| NEW-P1-03 readiness vs MCP/sandbox | §11 (now also profile/behaviour agreement) | CLOSED |
| NEW-P1-04 test order | §12 | CLOSED |

## 18. Remediation Artifacts (§44)

* This document; `artifacts/audit/v2.0.1_remediation_round3.json`;
  `RELEASE_NOTES_v2.0.1.md` (round 3 section, known limitations, staleness
  fixed; no PASS claim).
* Code / tests: commits listed in the JSON (`commits`).
* Live logs and probes stay on the host under the session scratchpad (not
  committed): runbook transcript, governed lifecycle, live matrices, fake
  provider matrix, readiness matrix, sandbox probes, contamination guard.

## 19. CI, Review Threads, Freeze (§47, §48)

* Code commits pushed to `nvidia/fix/v2.0.1-canonical-app-remediation`
  (`86f3004..36b2351`, then `608222f`); no Co-Authored-By trailers.
* GitHub CI on `608222f` (run 38110621347): **Test & Quality Checks (3.11,
  22) pass** — `2865 passed, 8 skipped` (Python CORE CI) and Jest `968
  passed`; CodeQL (python, javascript-typescript) pass; Security Scan pass;
  Trivy pass; Semantic Release skipped. `36b2351` (run 38110035166) was also
  green.
* Review threads: the code-quality bot raised two comments on `36b2351`
  (unused local `phase`, unused import `field`); both fixed in `608222f` and
  resolved. 0 unresolved threads.
* The final docs commit(s) adding this file and the JSON are verified green
  and frozen; the frozen head SHA is recorded in the PR and the final report.
  Nothing is pushed after the freeze.

## 20. Fourth Independent Re-Audit Readiness

The candidate is ready for a fourth independent re-audit at the frozen head
recorded in the PR (and in the final report). Suggested re-checks: the
sandbox write probes (both policies), the MCP lost-response / crash / restart
sequence with write counts, the identity and cache matrices, and the
clean-shell runbook including the gateway step.

## 21. Final Verdict

`MAIW V2.0.1 ROUND-3 REMEDIATION COMPLETE — READY FOR FOURTH INDEPENDENT RE-AUDIT`
